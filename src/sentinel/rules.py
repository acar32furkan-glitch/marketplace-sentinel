"""Saf kural fonksiyonları: aynı girdi her zaman aynı uyarıları üretir.

Kurallar birbirinden bağımsızdır ve her biri kendi **kapsamını** (`checked`) bildirir; böylece
"hiç bakılmayan" bir kural sıfır bulgu ile sessizce geçemez. Zaman tek bir yerden gelir
(``RuleContext.now``) — hiçbir kural saati kendisi okumaz.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

from pydantic import BaseModel, ConfigDict

from sentinel.models import Alert, Listing, Severity

SEVERITY_ORDER: Final[dict[Severity, int]] = {
    Severity.CRITICAL: 0,
    Severity.WARNING: 1,
    Severity.INFO: 2,
}

CODE_STOCK_CONFLICT = "STOK_CAKISMASI"
CODE_PRICE_DIVERGENCE = "FIYAT_SAPMASI"
CODE_MISSING_LISTING = "LISTE_YOK"
CODE_STALE_DATA = "VERI_BAYAT"

CRITICAL_PRICE_RATIO = 1.0  # fiyat iki katına çıktıysa (>= 2×) kritik sayılır
HOURS_PER_DAY = 24.0


class Thresholds(BaseModel):
    """Nöbetçinin politik eşikleri (profil değil; kod değişmeden ayarlanabilir)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_price_gap_ratio: float = 0.05
    max_stock_gap: int = 5
    stale_hours: int = 48
    sold_out_other_stock: int = 10


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Bir kuralın ihtiyaç duyduğu her şey (IO yok, saat yok → deterministik)."""

    listings: tuple[Listing, ...]
    thresholds: Thresholds
    now: datetime
    channels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    """Bir kuralın çıktısı: kapsam (`checked`) ve uyarılar."""

    rule: str
    checked: int
    alerts: tuple[Alert, ...]


def normalize_sku(sku: str) -> str:
    """SKU'yu karşılaştırma için normalize et (kırpılmış, küçük harf)."""
    return sku.strip().casefold()


def alert_sort_key(alert: Alert) -> tuple[int, str, str]:
    """Uyarıları (önem, kod, sku) ile deterministik sıralamak için anahtar."""
    return (SEVERITY_ORDER[alert.severity], alert.code, alert.sku)


def _alert(
    severity: Severity,
    code: str,
    sku: str,
    marketplaces: tuple[str, ...],
    message_tr: str,
    detail_tr: str,
    hint_tr: str,
) -> Alert:
    return Alert(
        severity=severity,
        code=code,
        sku=sku,
        marketplaces=marketplaces,
        message_tr=message_tr,
        detail_tr=detail_tr,
        hint_tr=hint_tr,
        signature=f"{code}:{sku}",
    )


def _active_by_sku(listings: tuple[Listing, ...]) -> dict[str, dict[str, Listing]]:
    """Aktif listeleri normalize SKU → (kanal → liste) olarak grupla."""
    grouped: dict[str, dict[str, Listing]] = {}
    for listing in listings:
        if not listing.active:
            continue
        grouped.setdefault(normalize_sku(listing.sku), {}).setdefault(listing.marketplace, listing)
    return grouped


def check_stock_conflict(context: RuleContext) -> RuleOutcome:
    """Aynı SKU'nun kanallar arası stok farkını denetle; tükenmişlik kritik sayılır."""
    alerts: list[Alert] = []
    checked = 0
    for sku, by_channel in _active_by_sku(context.listings).items():
        if len(by_channel) < 2:
            continue
        checked += 1
        stocks = {channel: listing.stock for channel, listing in by_channel.items()}
        low = min(stocks.values())
        high = max(stocks.values())
        gap = high - low
        if gap <= context.thresholds.max_stock_gap:
            continue
        channels = tuple(sorted(stocks))
        detail = ", ".join(f"{channel} {stocks[channel]}" for channel in channels)
        sold_out = low == 0 and high >= context.thresholds.sold_out_other_stock
        if sold_out:
            severity = Severity.CRITICAL
            message = f"{sku} bir kanalda tükendi, diğerinde satışta (stok farkı {gap})"
            hint = "Stok senkronizasyonunu hemen düzeltin: tükenmiş kanaldan sipariş gelirse iptal ve ceza riski doğar."
        else:
            severity = Severity.WARNING
            message = f"{sku} stoğu kanallar arasında {gap} adet farklı"
            hint = "Stokları tek kaynaktan besleyin; fark büyürse tükendi/az kaldı uyarıları doğurur."
        alerts.append(_alert(severity, CODE_STOCK_CONFLICT, sku, channels, message, detail, hint))
    return RuleOutcome("stock_conflict", checked, tuple(sorted(alerts, key=alert_sort_key)))


def _price_ratio(high: Decimal, low: Decimal) -> float | None:
    if low <= 0:
        return None
    return float((high - low) / low)


def check_price_divergence(context: RuleContext) -> RuleOutcome:
    """Aynı SKU'nun fiyatının kanallar arasında sapmasını denetle."""
    alerts: list[Alert] = []
    checked = 0
    for sku, by_channel in _active_by_sku(context.listings).items():
        if len(by_channel) < 2:
            continue
        checked += 1
        cheap_channel, cheap = min(by_channel.items(), key=lambda item: (item[1].price, item[0]))
        expensive_channel, expensive = max(by_channel.items(), key=lambda item: (item[1].price, item[0]))
        ratio = _price_ratio(expensive.price, cheap.price)
        if ratio is None or ratio < context.thresholds.max_price_gap_ratio:
            continue
        severity = Severity.CRITICAL if ratio >= CRITICAL_PRICE_RATIO else Severity.WARNING
        percent = ratio * 100
        channels = tuple(sorted(by_channel))
        message = (
            f"{sku} fiyatı {cheap_channel} {cheap.price} ile {expensive_channel} {expensive.price} "
            f"arasında %{percent:.1f} farklı"
        )
        detail = f"en düşük {cheap_channel} {cheap.price} · en yüksek {expensive_channel} {expensive.price}"
        hint = (
            "Ucuz kanal satışı pahalı kanala kaydırıyor; marj kaybını önlemek için fiyatları eşitleyin "
            "ya da sapmayı bilinçli bir kampanya olarak işaretleyin."
        )
        alerts.append(_alert(severity, CODE_PRICE_DIVERGENCE, sku, channels, message, detail, hint))
    return RuleOutcome("price_divergence", checked, tuple(sorted(alerts, key=alert_sort_key)))


def check_missing_listing(context: RuleContext) -> RuleOutcome:
    """Bir kanalda aktifken başka bir kanalda hiç bulunmayan SKU'ları bildir."""
    grouped = _active_by_sku(context.listings)
    seen: dict[str, set[str]] = {channel: set() for channel in context.channels}
    for sku, by_channel in grouped.items():
        for channel in by_channel:
            if channel in seen:
                seen[channel].add(sku)
    non_empty = {channel for channel, skus in seen.items() if skus}
    alerts: list[Alert] = []
    checked = 0
    for sku, by_channel in grouped.items():
        present = set(by_channel)
        for channel in context.channels:
            if channel in present or channel not in non_empty:
                continue
            checked += 1
            message = f"{sku} {channel} kanalında hiç listelenmiyor"
            detail = f"aktif olduğu kanallar: {', '.join(sorted(present))}"
            hint = (
                f"{channel} kanalında ürünü açın; bilinçli olarak kapatıldıysa diğer kanallardan da "
                "çıkarın — eksik liste ciro kaybı demektir."
            )
            alerts.append(_alert(Severity.WARNING, CODE_MISSING_LISTING, sku, (channel,), message, detail, hint))
    return RuleOutcome("missing_listing", checked, tuple(sorted(alerts, key=alert_sort_key)))


def check_stale_data(context: RuleContext) -> RuleOutcome:
    """``updated_at`` alanı eşiğe göre bayat olan listeleri bildir."""
    stale: dict[str, dict[str, float]] = {}
    checked = 0
    for listing in context.listings:
        checked += 1
        age_hours = (context.now - listing.updated_at).total_seconds() / 3600.0
        if age_hours < context.thresholds.stale_hours:
            continue
        stale.setdefault(normalize_sku(listing.sku), {})[listing.marketplace] = age_hours
    alerts: list[Alert] = []
    for sku, by_channel in stale.items():
        worst = max(by_channel.values())
        channels = tuple(sorted(by_channel))
        severity = Severity.WARNING if worst >= 2 * context.thresholds.stale_hours else Severity.INFO
        days = worst / HOURS_PER_DAY
        message = f"{sku} verisi {days:.1f} gün önce güncellenmiş"
        detail = f"en eski kayıt {worst:.0f} saatlik · kanallar: {', '.join(channels)}"
        hint = "Bu listeyi bir kez elle tazeleyin; bayat veri stok ve fiyat karşılaştırmasını güvenilmez kılar."
        alerts.append(_alert(severity, CODE_STALE_DATA, sku, channels, message, detail, hint))
    return RuleOutcome("stale_data", checked, tuple(sorted(alerts, key=alert_sort_key)))


RuleFn = Callable[[RuleContext], RuleOutcome]

RULES: dict[str, RuleFn] = {
    "stock_conflict": check_stock_conflict,
    "price_divergence": check_price_divergence,
    "missing_listing": check_missing_listing,
    "stale_data": check_stale_data,
}

RULE_LABELS: dict[str, str] = {
    "stock_conflict": "Stok çakışması",
    "price_divergence": "Fiyat sapması",
    "missing_listing": "Eksik liste",
    "stale_data": "Bayat veri",
}

__all__ = [
    "RULES",
    "RULE_LABELS",
    "RuleContext",
    "RuleFn",
    "RuleOutcome",
    "Thresholds",
    "alert_sort_key",
    "normalize_sku",
]
