"""Tarama: kısmi kanal hatası, durum takibi ve kapı kararı."""

from __future__ import annotations

from collections.abc import Mapping

from sentinel.channels import Channel, ChannelError
from sentinel.models import Alert, Listing, ScanResult, Severity
from sentinel.scan import FailPolicy, decide, run_scan
from tests.factories import ANCHOR_TEXT, dt, make_alert, make_listing


class StaticChannel:
    """Sabit bir liste döndüren sahte kanal."""

    def __init__(self, name: str, listings: list[Listing]) -> None:
        self.name = name
        self._listings = listings

    def fetch_listings(self, *, limit: int = 500) -> list[Listing]:
        return list(self._listings)[:limit]


class BrokenChannel:
    """Her çağrıda hata veren sahte kanal."""

    name = "kanal_b"

    def fetch_listings(self, *, limit: int = 500) -> list[Listing]:
        raise ChannelError("veri alınamadı")


def _result_with(alerts: list[Alert]) -> ScanResult:
    return ScanResult(
        generated_at=dt(ANCHOR_TEXT),
        channels=("kanal_a",),
        listings=1,
        alerts=tuple(alerts),
        new=tuple(alerts),
        ongoing=(),
        resolved=(),
    )


def test_run_scan_ornek_kanallarla(channels: Mapping[str, Channel]) -> None:
    result = run_scan(channels, now=dt(ANCHOR_TEXT))
    assert set(result.by_code()) == {"STOK_CAKISMASI", "FIYAT_SAPMASI", "LISTE_YOK", "VERI_BAYAT"}
    assert result.channels == ("kanal_a", "kanal_b")
    assert result.listings == 14
    assert result.errors == ()
    assert len(result.alerts) == 6
    assert len(result.new) == 6  # durum verilmezse hepsi yeni


def test_run_scan_onceki_durumla_ayirir(channels: Mapping[str, Channel]) -> None:
    previous = {
        "LISTE_YOK:sku-104": "2026-10-04T09:00:00+03:00",
        "FIYAT_SAPMASI:sku-999": "2026-10-05T09:00:00+03:00",
    }
    result = run_scan(channels, now=dt(ANCHOR_TEXT), previous_state=previous)
    assert len(result.new) == 5
    assert len(result.ongoing) == 1
    assert result.ongoing[0].signature == "LISTE_YOK:sku-104"
    assert len(result.resolved) == 1
    assert result.resolved[0].signature == "FIYAT_SAPMASI:sku-999"
    assert result.count(Severity.CRITICAL) == 1


def test_run_scan_kanal_hatasi_digerleriyle_devam_eder() -> None:
    good = StaticChannel("kanal_a", [make_listing("sku-1", marketplace="kanal_a")])
    result = run_scan({"kanal_a": good, "kanal_b": BrokenChannel()}, now=dt(ANCHOR_TEXT))
    assert result.errors == ("kanal_b: veri alınamadı",)
    assert result.channels == ("kanal_a", "kanal_b")
    assert all(alert.code != "LISTE_YOK" for alert in result.alerts)
    assert all("kanal_b" not in alert.marketplaces for alert in result.alerts)


def test_run_scan_hata_veren_kanal_stok_uyarisi_uretmez() -> None:
    good = StaticChannel("kanal_a", [make_listing("sku-1", marketplace="kanal_a", stock=0)])
    result = run_scan({"kanal_a": good, "kanal_b": BrokenChannel()}, now=dt(ANCHOR_TEXT))
    assert result.alerts == ()


def test_run_scan_hicbir_kanal_yoksa_bos() -> None:
    result = run_scan({}, now=dt(ANCHOR_TEXT))
    assert result.alerts == ()
    assert result.listings == 0
    assert result.channels == ()
    assert result.errors == ()


def test_decide_none_her_zaman_gecer() -> None:
    result = run_scan({}, now=dt(ANCHOR_TEXT))
    assert decide(result, FailPolicy.NONE) == (True, [])


def test_decide_yeni_kritik_kapiyi_dusurur() -> None:
    result = _result_with([make_alert("A:1", severity=Severity.CRITICAL, code="A")])
    passed, reasons = decide(result, FailPolicy.NEW_CRITICAL)
    assert passed is False
    assert reasons
    assert "kritik" in reasons[0]


def test_decide_kritik_yoksa_gecer() -> None:
    result = _result_with([make_alert("A:1", severity=Severity.WARNING, code="A")])
    assert decide(result, FailPolicy.NEW_CRITICAL) == (True, [])


def test_decide_any_new_yeni_varsa_dusurur() -> None:
    result = _result_with([make_alert("A:1", severity=Severity.WARNING, code="A")])
    passed, reasons = decide(result, FailPolicy.ANY_NEW)
    assert passed is False
    assert reasons
    assert "any-new" in reasons[0]


def test_decide_any_new_yeni_yoksa_gecer() -> None:
    result = run_scan({}, now=dt(ANCHOR_TEXT))
    assert decide(result, FailPolicy.ANY_NEW) == (True, [])
