"""Test kurucuları: kısa ve okunur listing/context/alert üretimi.

Testler üretim kodundaki örnek dosyalara bağlı değildir; burada kurulan minik girdiler her kuralın
sınır davranışını tek bakışta görünür kılar.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from sentinel.models import Alert, Listing, Severity
from sentinel.profiles import AuthStyle, FieldMap, MarketplaceProfile
from sentinel.rules import RuleContext, Thresholds

ANCHOR_TEXT = "2026-10-06T09:00:00+03:00"


def dt(text: str) -> datetime:
    """ISO metnini farkındalıklı ``datetime``'e çevir."""
    return datetime.fromisoformat(text)


ANCHOR: datetime = dt(ANCHOR_TEXT)


def make_listing(
    sku: str = "sku-1",
    *,
    marketplace: str = "kanal_a",
    price: str = "100.00",
    stock: int = 10,
    active: bool = True,
    updated_at: str = ANCHOR_TEXT,
    title: str = "Ürün",
    list_price: str | None = None,
    barcode: str | None = None,
) -> Listing:
    """Tek bir normalize liste üret."""
    return Listing(
        marketplace=marketplace,
        sku=sku,
        title=title,
        price=Decimal(price),
        list_price=Decimal(list_price) if list_price is not None else None,
        stock=stock,
        active=active,
        updated_at=dt(updated_at),
        barcode=barcode,
    )


def make_context(
    listings: list[Listing],
    *,
    channels: tuple[str, ...] | None = None,
    thresholds: Thresholds | None = None,
    now: datetime = ANCHOR,
) -> RuleContext:
    """Verilen listeler için kural bağlamı üret (kanallar verilmezse listelerden türetilir)."""
    resolved_channels = tuple(sorted({listing.marketplace for listing in listings})) if channels is None else channels
    return RuleContext(
        listings=tuple(listings),
        thresholds=thresholds or Thresholds(),
        now=now,
        channels=resolved_channels,
    )


def make_alert(
    signature: str = "STOK_CAKISMASI:sku-1",
    *,
    severity: Severity = Severity.WARNING,
    code: str = "STOK_CAKISMASI",
    sku: str = "sku-1",
    marketplaces: tuple[str, ...] = ("kanal_a", "kanal_b"),
) -> Alert:
    """Deterministik bir uyarı üret (imza varsayılan olarak kod+sku ile tutarlıdır)."""
    return Alert(
        severity=severity,
        code=code,
        sku=sku,
        marketplaces=marketplaces,
        message_tr="mesaj",
        detail_tr="detay",
        hint_tr="ipucu",
        signature=signature,
    )


def make_profile(
    name: str = "kanal_b",
    *,
    base_url: str = "https://ornek-b.example",
    products_path: str = "/v2/catalog/products",
    auth: AuthStyle = AuthStyle.BEARER,
    token_env: str | None = "KANAL_B_TOKEN",
    username_env: str | None = None,
    password_env: str | None = None,
    header_name: str | None = None,
    field_map: FieldMap | None = None,
    items_path: str | None = "payload.items",
    params: dict[str, str] | None = None,
    user_agent: str | None = None,
    page_size: int = 100,
) -> MarketplaceProfile:
    """HTTP kanal testleri için küçük bir pazaryeri profili üret."""
    return MarketplaceProfile(
        name=name,
        base_url=base_url,
        products_path=products_path,
        auth=auth,
        token_env=token_env,
        username_env=username_env,
        password_env=password_env,
        header_name=header_name,
        user_agent=user_agent,
        field_map=field_map or FieldMap(sku="sku", title="title", price="price", stock="stock"),
        params=params or {},
        items_path=items_path,
        page_size=page_size,
    )


def codes(alerts: Iterable[Alert]) -> list[str]:
    """Uyarıların kodlarını sıralı ve tekrarsız döndür (karşılaştırmayı okunur kılar)."""
    return sorted({alert.code for alert in alerts})


def signatures(alerts: Iterable[Alert]) -> list[str]:
    """Uyarıların imzalarını sıralı döndür."""
    return sorted(alert.signature for alert in alerts)
