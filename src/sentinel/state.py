"""Durum takibi: yalnızca **yeni** durumları bildirir, alarm fırtınasını önler.

Durum dosyası, her uyarının imzasından (``KOD:sku``) ilk görülme anına bir eşleme tutar. Bir tur
sonunda yalnızca yeni imzalar "yeni", önceki turda da görülen imzalar "devam eden" olur; kaybolan
imzalar bir kez "çözüldü" olarak duyurulur. Dosya insan tarafından okunabilecek sıralı JSON'dur.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sentinel.models import Alert, AlertStatus, Severity
from sentinel.rules import alert_sort_key

STATE_VERSION = 1
ALERTS_KEY = "alerts"


def load_state(path: Path) -> dict[str, str]:
    """İmza → ilk görülme (ISO) eşlemesini yükle; dosya yoksa boş sözlük döndür.

    Raises:
        ValueError: Dosya JSON değilse veya beklenen ``alerts`` nesnesi yoksa.
    """
    if not path.is_file():
        return {}
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"durum dosyası bir nesne olmalı: {path}"
        raise ValueError(msg)
    records = raw.get(ALERTS_KEY, raw)
    if not isinstance(records, dict):
        msg = f"durum dosyasında '{ALERTS_KEY}' nesnesi yok: {path}"
        raise ValueError(msg)
    state: dict[str, str] = {}
    for signature, value in records.items():
        first_seen = value.get("first_seen") if isinstance(value, dict) else value
        if isinstance(first_seen, str) and first_seen:
            state[str(signature)] = first_seen
    return state


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


__all__ = ["classify", "load_state", "save_state"]
