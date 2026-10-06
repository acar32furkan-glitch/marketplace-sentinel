"""Nöbetçi raporunun veri modelleri.

Bulgular Türkçe yazılır (raporu okuyan kişi satıcıdır); kod, alan adları ve sabitler İngilizcedir —
böylece hem satıcı hem CI kaydı aynı kaydı okuyabilir. Modeller saftır: ağ, saat ve rastgelelik
içermez, dolayısıyla aynı girdi her zaman aynı çıktıyı üretir.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Severity(StrEnum):
    """Bulgu ağırlığı; `critical` bulgular `--fail-on` politikasına göre kapıyı düşürebilir."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"

    @property
    def severity_tr(self) -> str:
        """Türkçe önem etiketi (konsol ve Markdown raporlarında kullanılır)."""
        return {"critical": "KRİTİK", "warning": "UYARI", "info": "BİLGİ"}[self.value]


class AlertStatus(StrEnum):
    """Bir uyarının durum takibindeki yeri."""

    NEW = "new"
    ONGOING = "ongoing"
    RESOLVED = "resolved"


class Listing(BaseModel):
    """Bir pazaryerinin tek listesi (normalize edilmiş hâli).

    Alan adları pazaryerinden bağımsızdır; kanal katmanı sağlayıcı yanıtını bu sözlüğe çevirir.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    marketplace: str
    sku: str
    title: str
    price: Decimal
    list_price: Decimal | None = None
    stock: int
    active: bool = True
    updated_at: datetime
    barcode: str | None = None


class Alert(BaseModel):
    """Tek bir kural ihlali; `signature` deterministik dedupe anahtarıdır."""

    model_config = ConfigDict(frozen=True)

    severity: Severity
    code: str
    sku: str
    marketplaces: tuple[str, ...]
    message_tr: str
    detail_tr: str
    hint_tr: str
    signature: str
    status: AlertStatus = AlertStatus.NEW
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class Snapshot(BaseModel):
    """Bir turun ham uyarı listesi (durum takibi uygulanmadan önceki hâli)."""

    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    alerts: tuple[Alert, ...]

    def signatures(self) -> tuple[str, ...]:
        """Uyarıların deterministik dedupe anahtarlarını sıralı döndür."""
        return tuple(alert.signature for alert in self.alerts)

    def by_code(self) -> dict[str, int]:
        """Kod → uyarı sayısı dağılımı."""
        codes: dict[str, int] = {}
        for alert in self.alerts:
            codes[alert.code] = codes.get(alert.code, 0) + 1
        return codes


class ScanResult(BaseModel):
    """Bir taramanın tam çıktısı: uyarılar, durum kırılımı ve kanal hataları."""

    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    channels: tuple[str, ...]
    listings: int
    alerts: tuple[Alert, ...]
    new: tuple[Alert, ...]
    ongoing: tuple[Alert, ...]
    resolved: tuple[Alert, ...]
    errors: tuple[str, ...] = ()

    def count(self, severity: Severity) -> int:
        """Verilen önem düzeyindeki **yeni ve devam eden** uyarı sayısını döndür."""
        return sum(1 for alert in (*self.new, *self.ongoing) if alert.severity is severity)

    def by_code(self) -> dict[str, int]:
        """Kod → uyarı sayısı dağılımı (yeni + devam eden)."""
        codes: dict[str, int] = {}
        for alert in (*self.new, *self.ongoing):
            codes[alert.code] = codes.get(alert.code, 0) + 1
        return codes
