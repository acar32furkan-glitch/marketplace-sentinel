"""Durum takibi: yalnızca **yeni** durumları bildirir, alarm fırtınasını önler.

Durum dosyası, her uyarının imzasından (``KOD:sku``) ilk görülme anına bir eşleme tutar. Bir tur
sonunda yalnızca yeni imzalar "yeni", önceki turda da görülen imzalar "devam eden" olur; kaybolan
imzalar bir kez "çözüldü" olarak duyurulur. Dosya insan tarafından okunabilecek sıralı JSON'dur.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sentinel.models import Alert, AlertStatus, Severity
from sentinel.rules import alert_sort_key

STATE_VERSION = 1
ALERTS_KEY = "alerts"
STATE_METADATA_KEYS = frozenset({"version", "generated_at"})


class StateFileError(ValueError):
    """Durum dosyası bir durum dosyası olarak okunamadı (bozuk JSON, eksik alan, yanlış tür).

    ``ValueError`` alt sınıfıdır: CLI bunu girdi hatasına (çıkış kodu 2) eşler.
    """


def load_state(path: Path, *, warn: Callable[[str], None] | None = None) -> dict[str, str]:
    """İmza → ilk görülme (ISO) eşlemesini yükle; dosya yoksa boş sözlük döndür.

    Dosya yapısal olarak bozuksa (JSON değil, kök nesne değil, ``alerts`` alanı yok, kayıt şekli
    tanınmıyor) tahmin yürütülmez: ``StateFileError`` yükseltilir. Tek tek değer bozukluğu (ISO
    olmayan ``first_seen``) ise alarmı yutmayı gerektirmez — kayıt korunur, ``warn`` verilmişse
    çağıran bilgilendirilir ve zamanlama ``classify`` içinde ``now``a düşer.

    Args:
        path: Durum dosyası yolu; yoksa boş sözlük döner (ilk koşu).
        warn: İnsan okunur uyarı metni alıcısı (CLI bunu stderr'e yazar). ``None`` ise sessiz.

    Raises:
        StateFileError: Dosya JSON değilse, kök nesne değilse, ``alerts`` alanı yoksa veya bir kayıt
            beklenen şekilde değilse.
    """
    if not path.is_file():
        return {}
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"durum dosyası geçerli JSON değil: {path} (satır {exc.lineno}, sütun {exc.colno}: {exc.msg})"
        raise StateFileError(msg) from exc
    if not isinstance(raw, dict):
        msg = f"durum dosyası bir nesne olmalı: {path}"
        raise StateFileError(msg)
    records = _records_of(raw, path=path)
    state: dict[str, str] = {}
    for signature, value in records.items():
        first_seen = _first_seen_of(signature, value, path=path, warn=warn)
        state[str(signature)] = first_seen
    return state


def _records_of(raw: dict[str, Any], *, path: Path) -> dict[str, Any]:
    """Kök nesneden imza kayıtlarını çıkar (iç içe ``alerts`` ya da düz eşleme biçimi)."""
    if ALERTS_KEY in raw:
        records = raw[ALERTS_KEY]
        if not isinstance(records, dict):
            msg = f"durum dosyasında '{ALERTS_KEY}' nesnesi yok: {path}"
            raise StateFileError(msg)
        return records
    flat = {key: value for key, value in raw.items() if key not in STATE_METADATA_KEYS}
    if not flat:
        msg = f"durum dosyasında '{ALERTS_KEY}' alanı yok: {path}"
        raise StateFileError(msg)
    return flat


def _first_seen_of(
    signature: str,
    value: Any,
    *,
    path: Path,
    warn: Callable[[str], None] | None,
) -> str:
    """Tek bir kaydın ``first_seen`` değerini doğrula; metin değilse ya da yoksa hata ver."""
    if isinstance(value, dict):
        if "first_seen" not in value:
            msg = f"durum dosyasında '{signature}' kaydının 'first_seen' alanı yok: {path}"
            raise StateFileError(msg)
        candidate = value["first_seen"]
    else:
        candidate = value
    if not isinstance(candidate, str) or not candidate:
        msg = f"durum dosyasında '{signature}' kaydının 'first_seen' değeri boş olmayan metin olmalı: {path}"
        raise StateFileError(msg)
    if warn is not None and not _is_iso(candidate):
        warn(
            f"durum dosyasında '{signature}' kaydının 'first_seen' değeri ISO zaman damgası değil "
            f"({candidate!r}); ilk görülme bu turun anı sayılacak: {path}"
        )
    return candidate


def _is_iso(value: str) -> bool:
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def save_state(path: Path, alerts: Iterable[Alert], *, now: datetime) -> None:
    """Aktif uyarıları (yeni + devam eden) sıralı, insan okunabilir JSON olarak yaz."""
    records: dict[str, dict[str, str]] = {}
    for alert in sorted(alerts, key=lambda item: item.signature):
        first_seen = (alert.first_seen or now).isoformat()
        records[alert.signature] = {"first_seen": first_seen, "last_seen": now.isoformat()}
    payload = {
        "version": STATE_VERSION,
        "generated_at": now.isoformat(),
        ALERTS_KEY: records,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def classify(
    current: list[Alert],
    previous: dict[str, str],
    *,
    now: datetime,
) -> tuple[list[Alert], list[Alert], list[Alert]]:
    """Mevcut uyarıları önceki duruma göre (yeni, devam eden, çözüldü) olarak ayır.

    ``first_seen`` / ``last_seen`` / ``status`` alanları burada doldurulur; dönüş değeri her zaman
    deterministik sırada (önem, kod, sku) olur.
    """
    new: list[Alert] = []
    ongoing: list[Alert] = []
    seen: set[str] = set()
    for alert in current:
        seen.add(alert.signature)
        if alert.signature in previous:
            first_seen = _parse_iso(previous[alert.signature], fallback=now)
            ongoing.append(
                alert.model_copy(update={"status": AlertStatus.ONGOING, "first_seen": first_seen, "last_seen": now})
            )
        else:
            new.append(alert.model_copy(update={"status": AlertStatus.NEW, "first_seen": now, "last_seen": now}))
    resolved = [
        _resolved_alert(signature, first_seen, now=now)
        for signature, first_seen in previous.items()
        if signature not in seen
    ]
    return (
        sorted(new, key=alert_sort_key),
        sorted(ongoing, key=alert_sort_key),
        sorted(resolved, key=alert_sort_key),
    )


def _parse_iso(value: str, *, fallback: datetime) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return fallback
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _resolved_alert(signature: str, first_seen: str, *, now: datetime) -> Alert:
    code, _, sku = signature.partition(":")
    label = sku or signature
    return Alert(
        severity=Severity.INFO,
        code=code or signature,
        sku=label,
        marketplaces=(),
        message_tr=f"{label} uyarısı bu turda kayboldu (çözüldü)",
        detail_tr="önceki turda bildirilen durum artık geçerli değil",
        hint_tr="Ek aksiyon gerekmez; kaydı arşivleyebilirsiniz.",
        signature=signature,
        status=AlertStatus.RESOLVED,
        first_seen=_parse_iso(first_seen, fallback=now),
        last_seen=now,
    )


__all__ = ["StateFileError", "classify", "load_state", "save_state"]
