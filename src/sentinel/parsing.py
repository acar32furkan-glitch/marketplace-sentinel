"""Pazaryeri yanıtlarını normalize etmek için paylaşılan yardımcılar.

Pazaryerleri aynı alanı farklı adlarla ve farklı tiplerle gönderir ("129.9" / 129.9 / epoch milis /
ISO metin). Bu yardımcılar o farkı tek yerde soğurur; hem örnek hem HTTP kanalı aynı kod yolunu
kullanır, böylece iki kanal tipi arasında davranış farkı oluşmaz.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from sentinel.models import Listing
from sentinel.profiles import FieldMap

KURUS = Decimal("0.01")
EPOCH_MILLIS_THRESHOLD = 100_000_000_000
TRUE_TEXT = frozenset({"true", "1", "yes", "evet", "aktif", "active"})
FALSE_TEXT = frozenset({"false", "0", "no", "hayir", "hayır", "pasif", "inactive"})

#: Örnek verinin yazıldığı sabit referans anı. Nöbetçi saati kendisi okumaz; CLI `--now`
#: verilmediğinde bu çapayı kullanır, eksik zaman damgaları da bu ana düşer (deterministik demo).
DEMO_NOW_TEXT = "2026-10-06T09:00:00+03:00"
DEMO_NOW: datetime = datetime.fromisoformat(DEMO_NOW_TEXT)


def first_value(mapping: dict[str, Any], *keys: str) -> Any:
    """``keys`` arasında ilk dolu (``None`` olmayan) değeri döndür."""
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def as_decimal(value: Any, default: str = "0") -> Decimal:
    """Para değerini kuruşa yuvarlanmış ``Decimal``'e çevir.

    Dönüşüm her zaman ``str`` üzerinden yapılır; böylece ikili kayan nokta artıkları fiyatlara
    sızmaz. Yuvarlama yarım-yukarı (para geleneği), bankacı yuvarlaması değil.
    """
    if isinstance(value, Decimal):
        candidate = value
    elif isinstance(value, bool):  # bool, int'in alt sınıfıdır — açıkça reddedilir
        return Decimal(default)
    elif isinstance(value, int | float | str):
        text = str(value).strip().replace(",", ".")
        try:
            candidate = Decimal(text)
        except InvalidOperation:
            return Decimal(default)
    else:
        return Decimal(default)
    return candidate.quantize(KURUS, rounding=ROUND_HALF_UP)


def as_int(value: Any, default: int = 0) -> int:
    """``"3"`` veya ``3.0`` gibi sağlayıcı değerlerini hata vermeden ``int``'e çevir."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip().replace(",", ".")))
        except ValueError:
            return default
    return default


def as_bool(value: Any, default: bool = True) -> bool:
    """``true``/``1``/``"evet"`` gibi sağlayıcı metinlerini bool'a çevir."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        text = value.strip().casefold()
        if text in TRUE_TEXT:
            return True
        if text in FALSE_TEXT:
            return False
    return default


def as_optional_str(value: Any) -> str | None:
    """Kırpılmış bir metin döndür; değer boşsa ``None``."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_datetime(value: Any, fallback: datetime) -> datetime:
    """Epoch milis, epoch saniye, ISO metin veya ``datetime`` çöz (naive → UTC).

    Çözülemeyen değer ``fallback`` ile döner; saat okunmaz.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, int | float) and not isinstance(value, bool):
        number = float(value)
        if number > EPOCH_MILLIS_THRESHOLD:  # milis
            number /= 1000.0
        return datetime.fromtimestamp(number, tz=UTC)
    if isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed = None
        if parsed is not None:
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return fallback


def select_path(payload: Any, path: str | None) -> Any:
    """``"data.listings"`` gibi nokta yolunu çöz; ``path`` ``None`` ise kökü döndür.

    Yol bulunamazsa ``None`` döner — çağıran taraf bunu kendi hata mesajına çevirir.
    """
    if path is None:
        return payload
    current = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def build_listing(
    row: dict[str, Any],
    *,
    field_map: FieldMap,
    marketplace: str,
    fallback: datetime = DEMO_NOW,
) -> Listing:
    """Bir ham satırı ``field_map`` ile ``Listing``'e çevir.

    Eşlenen alan adının yanında kanonik İngilizce ad da denenir; böylece sağlayıcı alanı yeniden
    adlandırdığında nöbetçi sessizce boş değer üretmek yerine veriyi bulmaya devam eder.

    Raises:
        ValueError: satırda SKU alanı boşsa.
    """
    sku = as_optional_str(first_value(row, field_map.sku, "sku"))
    if sku is None:
        msg = f"{marketplace}: satırda zorunlu SKU alanı boş ({field_map.sku})"
        raise ValueError(msg)
    title = as_optional_str(first_value(row, field_map.title, "title")) or sku
    price = as_decimal(first_value(row, field_map.price, "price"))
    stock = as_int(first_value(row, field_map.stock, "stock"))
    list_price = None
    if field_map.list_price:
        raw_list_price = first_value(row, field_map.list_price)
        if raw_list_price is not None:
            list_price = as_decimal(raw_list_price)
    active = as_bool(first_value(row, field_map.active), default=True) if field_map.active else True
    updated_raw = first_value(row, field_map.updated_at) if field_map.updated_at else None
    barcode = as_optional_str(first_value(row, field_map.barcode)) if field_map.barcode else None
    return Listing(
        marketplace=marketplace,
        sku=sku,
        title=title,
        price=price,
        list_price=list_price,
        stock=stock,
        active=active,
        updated_at=parse_datetime(updated_raw, fallback),
        barcode=barcode,
    )
