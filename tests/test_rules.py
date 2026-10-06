"""Kural motoru: dört kuralın davranışı, kapsam bildirimi ve sınır durumları."""

from __future__ import annotations

from sentinel.models import Severity
from sentinel.rules import (
    RULE_LABELS,
    RULES,
    Thresholds,
    alert_sort_key,
    check_missing_listing,
    check_price_divergence,
    check_stale_data,
    check_stock_conflict,
    normalize_sku,
)
from tests.factories import make_alert, make_context, make_listing

# ------------------------------------------------------------- stok çakışması


def test_stok_tukenmis_kanal_kritik() -> None:
    listings = [
        make_listing("sku-1", marketplace="kanal_a", stock=0),
        make_listing("sku-1", marketplace="kanal_b", stock=24),
    ]
    outcome = check_stock_conflict(make_context(listings))
    assert outcome.rule == "stock_conflict"
    assert outcome.checked == 1
    assert len(outcome.alerts) == 1
    alert = outcome.alerts[0]
    assert alert.severity is Severity.CRITICAL
    assert alert.code == "STOK_CAKISMASI"
    assert alert.signature == "STOK_CAKISMASI:sku-1"
    assert alert.marketplaces == ("kanal_a", "kanal_b")


def test_stok_farki_uyari_tukenmislik_kritik_degil() -> None:
    listings = [
        make_listing("sku-1", marketplace="kanal_a", stock=1),
        make_listing("sku-1", marketplace="kanal_b", stock=9),
    ]
    outcome = check_stock_conflict(make_context(listings))
    assert outcome.alerts[0].severity is Severity.WARNING


def test_stok_esitlikte_tetiklenmez() -> None:
    listings = [
        make_listing("sku-1", marketplace="kanal_a", stock=10),
        make_listing("sku-1", marketplace="kanal_b", stock=15),
    ]
    outcome = check_stock_conflict(make_context(listings))
    assert outcome.checked == 1
    assert outcome.alerts == ()


def test_stok_tek_kanal_denetlenmez() -> None:
    outcome = check_stock_conflict(make_context([make_listing("sku-1")]))
    assert outcome.checked == 0
    assert outcome.alerts == ()


def test_stok_pasif_liste_yok_sayilir() -> None:
    listings = [
        make_listing("sku-1", marketplace="kanal_a", stock=0),
        make_listing("sku-1", marketplace="kanal_b", stock=24, active=False),
    ]
    outcome = check_stock_conflict(make_context(listings))
    assert outcome.checked == 0


def test_stok_sku_buyuk_kucuk_harf_duyarsiz() -> None:
    listings = [
        make_listing("SKU-1", marketplace="kanal_a", stock=0),
        make_listing("sku-1", marketplace="kanal_b", stock=50),
    ]
    outcome = check_stock_conflict(make_context(listings))
    assert len(outcome.alerts) == 1
    assert outcome.alerts[0].sku == "sku-1"


# ------------------------------------------------------------- fiyat sapması


def test_fiyat_sapmasi_uyari() -> None:
    listings = [
        make_listing("sku-1", marketplace="kanal_a", price="100.00"),
        make_listing("sku-1", marketplace="kanal_b", price="118.00"),
    ]
    outcome = check_price_divergence(make_context(listings))
    assert outcome.checked == 1
    alert = outcome.alerts[0]
    assert alert.severity is Severity.WARNING
    assert alert.code == "FIYAT_SAPMASI"
    assert "kanal_a 100.00" in alert.message_tr
    assert "kanal_b 118.00" in alert.message_tr
    assert "%18.0" in alert.message_tr


def test_fiyat_iki_katinda_kritik() -> None:
    listings = [
        make_listing("sku-1", marketplace="kanal_a", price="100.00"),
        make_listing("sku-1", marketplace="kanal_b", price="200.00"),
    ]
    outcome = check_price_divergence(make_context(listings))
    assert outcome.alerts[0].severity is Severity.CRITICAL


def test_fiyat_esik_degerinde_tetiklenir() -> None:
    listings = [
        make_listing("sku-1", marketplace="kanal_a", price="100.00"),
        make_listing("sku-1", marketplace="kanal_b", price="105.00"),
    ]
    outcome = check_price_divergence(make_context(listings, thresholds=Thresholds()))
    assert len(outcome.alerts) == 1


def test_fiyat_esik_altinda_tetiklenmez() -> None:
    listings = [
        make_listing("sku-1", marketplace="kanal_a", price="100.00"),
        make_listing("sku-1", marketplace="kanal_b", price="104.99"),
    ]
    assert check_price_divergence(make_context(listings)).alerts == ()


def test_fiyat_sifir_fiyat_atlanir() -> None:
    listings = [
        make_listing("sku-1", marketplace="kanal_a", price="0"),
        make_listing("sku-1", marketplace="kanal_b", price="100"),
    ]
    assert check_price_divergence(make_context(listings)).alerts == ()


def test_fiyat_esitse_tetiklenmez() -> None:
    listings = [
        make_listing("sku-1", marketplace="kanal_a", price="50"),
        make_listing("sku-1", marketplace="kanal_b", price="50"),
    ]
    assert check_price_divergence(make_context(listings)).alerts == ()


# --------------------------------------------------------------- eksik liste


def test_eksik_liste_uyarisi() -> None:
    listings = [
        make_listing("sku-1", marketplace="kanal_a"),
        make_listing("sku-2", marketplace="kanal_a"),
        make_listing("sku-1", marketplace="kanal_b"),
    ]
    outcome = check_missing_listing(make_context(listings, channels=("kanal_a", "kanal_b")))
    assert outcome.checked == 1
    alert = outcome.alerts[0]
    assert alert.code == "LISTE_YOK"
    assert alert.severity is Severity.WARNING
    assert alert.sku == "sku-2"
    assert alert.marketplaces == ("kanal_b",)
    assert "kanal_b" in alert.message_tr


def test_eksik_liste_bos_kanal_atlanir() -> None:
    listings = [make_listing("sku-1", marketplace="kanal_a")]
    outcome = check_missing_listing(make_context(listings, channels=("kanal_a", "kanal_b")))
    assert outcome.alerts == ()


def test_eksik_liste_hepsi_varsa_sessiz() -> None:
    listings = [
        make_listing("sku-1", marketplace="kanal_a"),
        make_listing("sku-1", marketplace="kanal_b"),
    ]
    outcome = check_missing_listing(make_context(listings, channels=("kanal_a", "kanal_b")))
    assert outcome.checked == 0
    assert outcome.alerts == ()


def test_eksik_liste_uc_kanalda_tum_kombinasyonlar() -> None:
    listings = [
        make_listing("sku-1", marketplace="kanal_a"),
        make_listing("sku-2", marketplace="kanal_b"),
        make_listing("sku-3", marketplace="kanal_c"),
    ]
    outcome = check_missing_listing(make_context(listings, channels=("kanal_a", "kanal_b", "kanal_c")))
    assert outcome.checked == 6
    assert {alert.sku for alert in outcome.alerts} == {"sku-1", "sku-2", "sku-3"}


# ----------------------------------------------------------------- bayat veri


def test_bayat_veri_bilgi() -> None:
    outcome = check_stale_data(make_context([make_listing(updated_at="2026-10-03T09:00:00+03:00")]))
    alert = outcome.alerts[0]
    assert alert.code == "VERI_BAYAT"
    assert alert.severity is Severity.INFO
    assert outcome.checked == 1


def test_bayat_veri_uyari_iki_kat() -> None:
    outcome = check_stale_data(make_context([make_listing(updated_at="2026-10-01T09:00:00+03:00")]))
    assert outcome.alerts[0].severity is Severity.WARNING


def test_bayat_veri_esik_altinda_tetiklenmez() -> None:
    outcome = check_stale_data(make_context([make_listing(updated_at="2026-10-05T09:00:00+03:00")]))
    assert outcome.alerts == ()


def test_bayat_veri_gelecek_zaman_tetiklenmez() -> None:
    outcome = check_stale_data(make_context([make_listing(updated_at="2026-10-06T10:00:00+03:00")]))
    assert outcome.alerts == ()


def test_bayat_veri_sku_basina_tek_uyari() -> None:
    listings = [
        make_listing("sku-1", marketplace="kanal_a", updated_at="2026-10-01T09:00:00+03:00"),
        make_listing("sku-1", marketplace="kanal_b", updated_at="2026-10-02T09:00:00+03:00"),
    ]
    outcome = check_stale_data(make_context(listings))
    assert len(outcome.alerts) == 1
    assert outcome.alerts[0].marketplaces == ("kanal_a", "kanal_b")


def test_bayat_veri_esik_degerinde_bilgi() -> None:
    outcome = check_stale_data(make_context([make_listing(updated_at="2026-10-04T09:00:00+03:00")]))
    assert outcome.alerts[0].severity is Severity.INFO


# --------------------------------------------------------------- kayıt/sıra


def test_normalize_sku_kirpar_ve_kucultur() -> None:
    assert normalize_sku("  SKU-1 ") == "sku-1"


def test_kural_kayitlari_ve_etiketleri_tutarlidir() -> None:
    assert set(RULES) == {"stock_conflict", "price_divergence", "missing_listing", "stale_data"}
    assert set(RULE_LABELS) == set(RULES)
    assert all(label for label in RULE_LABELS.values())


def test_her_kural_kendi_adiyla_outcome_dondurur() -> None:
    context = make_context([make_listing()])
    for name, check in RULES.items():
        assert check(context).rule == name


def test_alert_sort_key_onem_kod_sku_sirasi() -> None:
    alerts = [
        make_alert("VERI_BAYAT:sku-1", severity=Severity.INFO, code="VERI_BAYAT"),
        make_alert("STOK_CAKISMASI:sku-9", severity=Severity.WARNING, code="STOK_CAKISMASI", sku="sku-9"),
        make_alert("FIYAT_SAPMASI:sku-1", severity=Severity.CRITICAL, code="FIYAT_SAPMASI"),
    ]
    ordered = sorted(alerts, key=alert_sort_key)
    assert [alert.severity for alert in ordered] == [Severity.CRITICAL, Severity.WARNING, Severity.INFO]


def test_kurallar_ayni_girdiye_ayni_cikti_verir() -> None:
    listings = [
        make_listing("sku-1", marketplace="kanal_a", stock=0),
        make_listing("sku-1", marketplace="kanal_b", stock=99),
    ]
    first = check_stock_conflict(make_context(listings))
    second = check_stock_conflict(make_context(listings))
    assert first == second
