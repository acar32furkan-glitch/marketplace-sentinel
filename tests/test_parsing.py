"""Paylaşılan normalize yardımcıları: tip farklılıklarına dayanıklılık ve determinizm."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from sentinel.parsing import (
    DEMO_NOW,
    as_bool,
    as_decimal,
    as_int,
    as_optional_str,
    build_listing,
    first_value,
    parse_datetime,
    select_path,
)
from sentinel.profiles import FieldMap
from tests.factories import ANCHOR_TEXT

FIELD_MAP = FieldMap(sku="kod", title="ad", price="fiyat", stock="stok", active="aktif")


def test_first_value_ilk_dolu_degeri_alir() -> None:
    assert first_value({"a": None, "b": "x"}, "a", "b") == "x"
    assert first_value({}, "a", "b") is None
    assert first_value({"a": 0}, "a") == 0


def test_as_decimal_str_ondalik_ve_yuvarlama() -> None:
    assert as_decimal("129.90") == Decimal("129.90")
    assert as_decimal("129,9") == Decimal("129.90")
    assert as_decimal(129.9) == Decimal("129.90")
    assert as_decimal("10.005") == Decimal("10.01")  # yarım-yukarı, bankacı değil


def test_as_decimal_gecersiz_ve_bool_reddedilir() -> None:
    assert as_decimal("yok") == Decimal("0")
    assert as_decimal(None, "7") == Decimal("7")
    assert as_decimal(value=True) == Decimal("0")


def test_as_int_cesitli_girdiler() -> None:
    assert as_int("3") == 3
    assert as_int(3.0) == 3
    assert as_int("3,0") == 3
    assert as_int("yok") == 0
    assert as_int(value=True) == 0
    assert as_int(None, 5) == 5


def test_as_bool_metin_varyasyonlari() -> None:
    assert as_bool("true") is True
    assert as_bool("EVET") is True
    assert as_bool("hayır") is False
    assert as_bool("0") is False
    assert as_bool(0) is False
    assert as_bool(None) is True
    assert as_bool("belirsiz", default=False) is False


def test_as_optional_str_bos_deger_none() -> None:
    assert as_optional_str("  x ") == "x"
    assert as_optional_str("   ") is None
    assert as_optional_str(None) is None


def test_parse_datetime_epoch_milis_ve_saniye() -> None:
    millis = parse_datetime(1_759_645_200_000, fallback=DEMO_NOW)
    seconds = parse_datetime(1_759_645_200, fallback=DEMO_NOW)
    assert millis == seconds
    assert millis.tzinfo is not None


def test_parse_datetime_iso_ve_z() -> None:
    parsed = parse_datetime("2026-10-06T09:00:00Z", fallback=DEMO_NOW)
    assert parsed == datetime(2026, 10, 6, 9, 0, tzinfo=UTC)
    naive = parse_datetime("2026-10-06T09:00:00", fallback=DEMO_NOW)
    assert naive.tzinfo is UTC


def test_parse_datetime_gecersiz_deger_fallback() -> None:
    assert parse_datetime("dün", fallback=DEMO_NOW) == DEMO_NOW
    assert parse_datetime(None, fallback=DEMO_NOW) == DEMO_NOW
    aware = datetime(2026, 1, 1, tzinfo=UTC)
    assert parse_datetime(aware, fallback=DEMO_NOW) is aware


def test_select_path_nokta_yolu() -> None:
    payload = {"data": {"listings": [1, 2]}}
    assert select_path(payload, "data.listings") == [1, 2]
    assert select_path(payload, "data.yok") is None
    assert select_path(payload, None) is payload


def test_build_listing_alan_eslemesi_ile() -> None:
    row = {"kod": "sku-9", "ad": "Ürün", "fiyat": "19.90", "stok": "4", "aktif": "hayır"}
    listing = build_listing(row, field_map=FIELD_MAP, marketplace="kanal_a")
    assert listing.sku == "sku-9"
    assert listing.price == Decimal("19.90")
    assert listing.stock == 4
    assert listing.active is False
    assert listing.updated_at == DEMO_NOW


def test_build_listing_kanonik_ada_duser() -> None:
    mapping = FieldMap(sku="urun_kodu", title="baslik", price="fiyat", stock="stok")
    row = {"sku": "sku-7", "title": "Ürün", "fiyat": 5, "stok": 2}
    listing = build_listing(row, field_map=mapping, marketplace="kanal_a")
    assert listing.sku == "sku-7"
    assert listing.title == "Ürün"


def test_build_listing_skusuz_satir_reddedilir() -> None:
    with pytest.raises(ValueError, match="SKU alanı boş"):
        build_listing({"ad": "Ürün"}, field_map=FIELD_MAP, marketplace="kanal_a")


def test_build_listing_verilen_zaman_damgasi_kullanilir() -> None:
    row = {"kod": "sku-9", "ad": "Ürün", "fiyat": "1", "stok": 1, "guncelleme": ANCHOR_TEXT}
    mapping = FieldMap(sku="kod", title="ad", price="fiyat", stock="stok", updated_at="guncelleme")
    listing = build_listing(row, field_map=mapping, marketplace="kanal_a")
    assert listing.updated_at == datetime.fromisoformat(ANCHOR_TEXT)
