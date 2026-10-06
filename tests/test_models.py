"""Model sözleşmeleri: dondurulmuşluk, türetilmiş etiketler ve sayım yardımcıları."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sentinel.models import AlertStatus, Listing, ScanResult, Severity, Snapshot
from tests.factories import ANCHOR, make_alert, make_listing


def test_severity_tr_etiketleri() -> None:
    assert Severity.CRITICAL.severity_tr == "KRİTİK"
    assert Severity.WARNING.severity_tr == "UYARI"
    assert Severity.INFO.severity_tr == "BİLGİ"


def test_listing_dondurulmus_ve_fazla_alan_yasak() -> None:
    assert Listing.model_config["frozen"] is True
    assert Listing.model_config["extra"] == "forbid"


def test_listing_fazla_alan_reddedilir() -> None:
    payload = {
        "marketplace": "a",
        "sku": "s",
        "title": "t",
        "price": "1",
        "stock": 1,
        "updated_at": ANCHOR.isoformat(),
        "bilinmeyen_alan": 1,
    }
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Listing.model_validate(payload)


def test_listing_fiyat_ondalik_olarak_tutulur() -> None:
    listing = make_listing(price="129.90")
    assert str(listing.price) == "129.90"
    assert listing.list_price is None


def test_alert_varsayilanlari() -> None:
    alert = make_alert()
    assert alert.status is AlertStatus.NEW
    assert alert.first_seen is None
    assert alert.last_seen is None


def test_snapshot_imzalar_ve_kod_dagilimi() -> None:
    snapshot = Snapshot(
        generated_at=ANCHOR,
        alerts=(make_alert("STOK_CAKISMASI:sku-1"), make_alert("STOK_CAKISMASI:sku-2")),
    )
    assert snapshot.signatures() == ("STOK_CAKISMASI:sku-1", "STOK_CAKISMASI:sku-2")
    assert snapshot.by_code() == {"STOK_CAKISMASI": 2}


def test_scan_result_count_ve_by_code_cozulenleri_saymaz() -> None:
    new = [
        make_alert("FIYAT_SAPMASI:sku-1", severity=Severity.CRITICAL, code="FIYAT_SAPMASI"),
        make_alert("LISTE_YOK:sku-2", severity=Severity.WARNING, code="LISTE_YOK"),
    ]
    ongoing = [make_alert("VERI_BAYAT:sku-3", severity=Severity.INFO, code="VERI_BAYAT")]
    resolved = [
        make_alert(
            "LISTE_YOK:sku-9",
            severity=Severity.INFO,
            code="LISTE_YOK",
            marketplaces=(),
        )
    ]
    result = ScanResult(
        generated_at=ANCHOR,
        channels=("kanal_a", "kanal_b"),
        listings=7,
        alerts=(*new, *ongoing, *resolved),
        new=tuple(new),
        ongoing=tuple(ongoing),
        resolved=tuple(resolved),
    )
    assert result.count(Severity.CRITICAL) == 1
    assert result.count(Severity.WARNING) == 1
    assert result.count(Severity.INFO) == 1
    assert result.by_code() == {"FIYAT_SAPMASI": 1, "LISTE_YOK": 1, "VERI_BAYAT": 1}
    assert result.errors == ()
