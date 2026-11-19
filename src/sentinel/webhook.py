"""Webhook teslimi: tarama gövdesini JSON olarak dışarı POST eder.

Ölçüm katmanının **salt okunur** sözleşmesini bozmamak için teslim ayrı bir modüldür ve
varsayılanı **kuru çalışmadır**: gövde hazırlanır, bayt sayısı ve sha256 özeti yazılır, ağa
hiç çıkılmaz. Gerçek ``POST`` yalnızca açık ``--webhook-send`` bayrağıyla yapılır
(gerekçe: `docs/adr/0004-webhook-teslimi.md`).

Teslim politikası:

* webhook adresi bir **sırdır** (Slack/Discord adreslerinde belirteç yolun içinde durur), bu yüzden
  hiçbir çıktıda tam adres görünmez; `mask_url` yalnızca şema + sunucu bırakır,
* yalnızca ``http``/``https``; adrese gömülü kullanıcı/şifre ve ``#`` parçası reddedilir,
* yönlendirme izlenmez — ``3xx`` teslim hatasıdır (imzalı gövde başka bir adrese taşınmasın),
* ``429``/``5xx`` üstel geri çekilmeyle yeniden denenir, ``401``/``403`` ve diğer ``4xx``
  yeniden denenmez,
* teslim hatası **çıkış kodunu değiştirmez** (çıkış kodu tarama kararını anlatır); hata stderr'e
  ve ``--json`` çıktısındaki ``webhook`` bloğuna yazılır.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlsplit

import httpx

from sentinel import __version__

WEBHOOK_URL_ENV: Final = "SENTINEL_WEBHOOK_URL"
BODY_SCHEMA: Final = 1
DEFAULT_TIMEOUT: Final = 10.0
DEFAULT_ATTEMPTS: Final = 3
DEFAULT_BACKOFF_SECONDS: Final = 0.5
RETRY_STATUS_CODES: Final = frozenset({429, 500, 502, 503, 504})
USER_AGENT: Final = f"marketplace-sentinel/{__version__} (+https://github.com/acar32furkan-glitch/marketplace-sentinel)"
ALLOWED_SCHEMES: Final = frozenset({"http", "https"})


class WebhookError(ValueError):
    """Webhook yapılandırması geçersiz (adres biçimi, ortam değişkeni)."""


@dataclass(frozen=True)
class WebhookDelivery:
    """Bir teslim denemesinin sonucu.

    ``url`` alanı **maskelenmiş** adresi taşır; tam adres hiçbir yere yazılmaz.
    """

    url: str
    dry_run: bool
    sent: bool
    attempts: int
    byte_count: int
    sha256: str
    status_code: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Teslim başarılı mı (kuru çalışma da başarı sayılır: gövde hazır)."""
        return self.sent or (self.dry_run and self.error is None)

    def to_json(self) -> dict[str, Any]:
        """``--json`` sözleşmesindeki ``webhook`` bloğu."""
        return {
            "url": self.url,
            "dry_run": self.dry_run,
            "sent": self.sent,
            "ok": self.ok,
            "attempts": self.attempts,
            "status_code": self.status_code,
            "bytes": self.byte_count,
            "sha256": self.sha256,
            "error": self.error,
        }


def mask_url(raw: str) -> str:
    """Adresi yayınlanabilir biçime indir: ``https://host/…``.

    Yol ve sorgu **her zaman** gizlenir: sağlayıcılar belirteci yolun içine koyar (Discord, Slack,
    Teams) ve CI günlüğü herkese açıktır. Adres hiç çözülemiyorsa sabit bir etiket döner.
    """
    try:
        parts = urlsplit(raw)
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return "(adres çözülemedi)"
    if not parts.hostname:
        return "(adres çözülemedi)"
    has_tail = (parts.path not in {"", "/"}) or bool(parts.query)
    return f"{parts.scheme or '?'}://{parts.hostname}{port}{'/…' if has_tail else ''}"


def validate_url(raw: str) -> str:
    """Adresi doğrula ve kırpılmış hâlini döndür.

    Raises:
        WebhookError: Şema desteklenmiyorsa, sunucu adı yoksa, adrese kimlik bilgisi veya
            ``#`` parçası gömülüyse.
    """
    text = raw.strip()
    if not text:
        msg = "webhook adresi boş"
        raise WebhookError(msg)
    try:
        parts = urlsplit(text)
    except ValueError as exc:  # pragma: no cover - urlsplit çok az metinde fırlatır
        msg = f"webhook adresi çözülemedi: {mask_url(text)}"
        raise WebhookError(msg) from exc
    if parts.scheme not in ALLOWED_SCHEMES:
        seen = parts.scheme or "(şema yok)"
        msg = f"webhook adresi http:// veya https:// ile başlamalı (görülen: {seen}): {mask_url(text)}"
        raise WebhookError(msg)
    if not parts.hostname:
        msg = f"webhook adresinde sunucu adı yok: {mask_url(text)}"
        raise WebhookError(msg)
    if parts.username or parts.password:
        msg = "webhook adresine kullanıcı/şifre gömülmemeli: adres günlüğe sızar, kimlik bilgisi başlıkla verilir"
        raise WebhookError(msg)
    if parts.fragment:
        msg = "webhook adresinde '#' parçası olmamalı: sunucuya hiç gitmez, yanlış adrese POST sanılır"
        raise WebhookError(msg)
    return text


def resolve_url(flag_value: str | None, env: Mapping[str, str]) -> str | None:
    """Bayrak, yoksa ``SENTINEL_WEBHOOK_URL`` ortam değişkeni; ikisi de yoksa ``None``.

    Ortam değişkeni tercih edilir çünkü adres bir sırdır: komut satırına yazılan adres kabuk
    geçmişine ve CI iş tanımına düşer.

    Raises:
        WebhookError: Verilen (bayrak veya ortam) adres geçersizse.
    """
    for source, candidate in (("--webhook-url", flag_value), (WEBHOOK_URL_ENV, env.get(WEBHOOK_URL_ENV))):
        if candidate is not None and candidate.strip():
            try:
                return validate_url(candidate)
            except WebhookError as exc:
                msg = f"{source}: {exc}"
                raise WebhookError(msg) from exc
    return None


def build_body(payload: Mapping[str, Any], *, event: str = "scan") -> dict[str, Any]:
    """``--json``/``--report`` gövdesini olay zarfına sar.

    Gövde ayrı bir şema uydurmaz: aynı sözleşme (``counts``, ``codes``, ``alerts`` …) taşınır,
    üstüne alıcının ayırt edebilmesi için ``event`` ve ``schema`` eklenir.
    """
    return {"event": event, "schema": BODY_SCHEMA, **payload}


def encode_body(body: Mapping[str, Any]) -> bytes:
    """Gövdeyi telde gidecek baytlara çevir (UTF-8, ayırıcısız, Türkçe kaçışsız).

    ``ensure_ascii=False`` bilinçli: ``KRİTİK`` gibi etiketler kaçış dizisine dönüşmediğinde
    gövde hem daha küçük hem de alıcıda okunur kalır; sha256 bu yüzden kararlıdır.
    """
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def deliver(
    url: str,
    body: Mapping[str, Any],
    *,
    dry_run: bool = True,
    client: httpx.Client | None = None,
    max_attempts: int = DEFAULT_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    timeout: float = DEFAULT_TIMEOUT,
) -> WebhookDelivery:
    """Gövdeyi ``url``'e POST et (varsayılan: kuru çalışma, ağa çıkmaz).

    Args:
        url: Doğrulanmış adres; çıktıda maskelenir.
        body: Gönderilecek JSON nesnesi (``build_body`` çıktısı).
        dry_run: ``True`` ise istek atılmaz; yalnızca bayt sayısı ve sha256 hesaplanır.
        client: Dışarıdan verilen HTTP istemcisi (testler); verilmezse kendi istemcisi açılır.
        max_attempts: En fazla deneme sayısı (``429``/``5xx``/ağ hatasında).
        backoff_seconds: İlk bekleme; her denemede iki katına çıkar.
        timeout: Tek isteğin zaman aşımı (saniye).

    Returns:
        Deneme sayısı, durum kodu ve hata metnini taşıyan :class:`WebhookDelivery`.
    """
    raw = encode_body(body)
    masked = mask_url(url)
    digest = hashlib.sha256(raw).hexdigest()

    def outcome(
        *,
        sent: bool,
        attempts: int,
        status_code: int | None = None,
        error: str | None = None,
    ) -> WebhookDelivery:
        """Teslim sonucunu maskelenmiş adres ve gövde özetiyle kur."""
        return WebhookDelivery(
            url=masked,
            dry_run=dry_run,
            sent=sent,
            attempts=attempts,
            byte_count=len(raw),
            sha256=digest,
            status_code=status_code,
            error=error,
        )

    if dry_run:
        return outcome(sent=False, attempts=0)

    owns_client = client is None
    http = client if client is not None else httpx.Client(timeout=timeout, follow_redirects=False)
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT, "Accept": "application/json"}
    last_error = ""
    last_status: int | None = None
    attempts = max(1, max_attempts)
    try:
        for attempt in range(1, attempts + 1):
            try:
                response = http.post(url, content=raw, headers=headers)
            except httpx.HTTPError as exc:
                last_error = f"ağ hatası: {exc.__class__.__name__}"
            else:
                last_status = response.status_code
                if 200 <= last_status < 300:
                    return outcome(sent=True, attempts=attempt, status_code=last_status)
                if last_status in RETRY_STATUS_CODES:
                    last_error = f"geçici hata: HTTP {last_status}"
                elif 300 <= last_status < 400:
                    last_error = f"yönlendirme izlenmedi: HTTP {last_status}"
                    return outcome(sent=False, attempts=attempt, status_code=last_status, error=last_error)
                elif last_status in {401, 403}:
                    last_error = f"kimlik reddedildi: HTTP {last_status}"
                    return outcome(sent=False, attempts=attempt, status_code=last_status, error=last_error)
                else:
                    last_error = f"istek reddedildi: HTTP {last_status}"
                    return outcome(sent=False, attempts=attempt, status_code=last_status, error=last_error)
            if attempt < attempts and backoff_seconds > 0:
                time.sleep(backoff_seconds * (2 ** (attempt - 1)))
    finally:
        if owns_client:
            http.close()
    return outcome(
        sent=False,
        attempts=attempts,
        status_code=last_status,
        error=last_error,
    )


__all__ = [
    "WEBHOOK_URL_ENV",
    "WebhookDelivery",
    "WebhookError",
    "build_body",
    "deliver",
    "encode_body",
    "mask_url",
    "resolve_url",
    "validate_url",
]
