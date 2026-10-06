"""Durum takibi: yükleme/kaydetme ve yeni/devam eden/çözüldü ayrımı."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from sentinel.models import AlertStatus, Severity
from sentinel.state import classify, load_state, save_state
from tests.factories import ANCHOR, make_alert


def test_load_state_dosya_yoksa_bos(tmp_path: Path) -> None:
    assert load_state(tmp_path / "yok.json") == {}


def test_load_state_ic_ice_ve_duz_bicim(tmp_path: Path) -> None:
    nested = tmp_path / "nested.json"
    nested.write_text(
        json.dumps({"alerts": {"A:sku-1": {"first_seen": "2026-10-01T09:00:00+03:00"}}}), encoding="utf-8"
    )
    assert load_state(nested) == {"A:sku-1": "2026-10-01T09:00:00+03:00"}
    flat = tmp_path / "flat.json"
    flat.write_text(json.dumps({"B:sku-2": "2026-10-02T09:00:00+03:00"}), encoding="utf-8")
    assert load_state(flat) == {"B:sku-2": "2026-10-02T09:00:00+03:00"}


def test_load_state_bozuk_json(tmp_path: Path) -> None:
    path = tmp_path / "bozuk.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_state(path)


def test_load_state_nesne_degilse(tmp_path: Path) -> None:
    path = tmp_path / "liste.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError, match="nesne olmalı"):
        load_state(path)


def test_save_state_sirali_ve_yuvarlak_yolculuk(tmp_path: Path) -> None:
    path = tmp_path / "alt" / "state.json"
    save_state(path, [make_alert("LISTE_YOK:sku-2"), make_alert("LISTE_YOK:sku-1")], now=ANCHOR)
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert text.index("sku-1") < text.index("sku-2")
    assert load_state(path) == {"LISTE_YOK:sku-1": ANCHOR.isoformat(), "LISTE_YOK:sku-2": ANCHOR.isoformat()}


def test_save_state_first_seen_yoksa_now_kullanilir(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    save_state(path, [make_alert()], now=ANCHOR)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["alerts"]["STOK_CAKISMASI:sku-1"]["first_seen"] == ANCHOR.isoformat()
    assert payload["alerts"]["STOK_CAKISMASI:sku-1"]["last_seen"] == ANCHOR.isoformat()


def test_classify_yeni_uyari() -> None:
    new, ongoing, resolved = classify([make_alert()], {}, now=ANCHOR)
    assert len(new) == 1
    assert new[0].status is AlertStatus.NEW
    assert new[0].first_seen == ANCHOR
    assert new[0].last_seen == ANCHOR
    assert ongoing == []
    assert resolved == []


def test_classify_devam_eden_ilk_gorulmeyi_korur() -> None:
    previous = {"STOK_CAKISMASI:sku-1": "2026-10-01T09:00:00+03:00"}
    new, ongoing, resolved = classify([make_alert()], previous, now=ANCHOR)
    assert new == []
    assert ongoing[0].status is AlertStatus.ONGOING
    assert ongoing[0].first_seen == datetime.fromisoformat("2026-10-01T09:00:00+03:00")
    assert ongoing[0].last_seen == ANCHOR
    assert resolved == []


def test_classify_cozulen_uyari_uretir() -> None:
    previous = {"FIYAT_SAPMASI:sku-999": "2026-10-01T09:00:00+03:00"}
    new, ongoing, resolved = classify([], previous, now=ANCHOR)
    assert new == []
    assert ongoing == []
    assert len(resolved) == 1
    alert = resolved[0]
    assert alert.status is AlertStatus.RESOLVED
    assert alert.code == "FIYAT_SAPMASI"
    assert alert.sku == "sku-999"
    assert alert.severity is Severity.INFO
    assert alert.first_seen == datetime.fromisoformat("2026-10-01T09:00:00+03:00")


def test_classify_bozuk_ilk_gorulme_now_duser() -> None:
    _, ongoing, _ = classify([make_alert()], {"STOK_CAKISMASI:sku-1": "bozuk"}, now=ANCHOR)
    assert ongoing[0].first_seen == ANCHOR


def test_classify_deterministik_siralama() -> None:
    current = [
        make_alert("VERI_BAYAT:sku-3", severity=Severity.INFO, code="VERI_BAYAT", sku="sku-3"),
        make_alert("FIYAT_SAPMASI:sku-1", severity=Severity.CRITICAL, code="FIYAT_SAPMASI"),
        make_alert("LISTE_YOK:sku-2", severity=Severity.WARNING, code="LISTE_YOK", sku="sku-2"),
    ]
    first = classify(current, {}, now=ANCHOR)[0]
    second = classify(current, {}, now=ANCHOR)[0]
    assert [alert.severity for alert in first] == [Severity.CRITICAL, Severity.WARNING, Severity.INFO]
    assert [alert.signature for alert in first] == [alert.signature for alert in second]


def test_classify_cozulenler_de_siralidir() -> None:
    previous = {
        "VERI_BAYAT:sku-2": ANCHOR.isoformat(),
        "FIYAT_SAPMASI:sku-1": ANCHOR.isoformat(),
    }
    _, _, resolved = classify([], previous, now=ANCHOR)
    assert [alert.signature for alert in resolved] == ["FIYAT_SAPMASI:sku-1", "VERI_BAYAT:sku-2"]


def test_classify_ayni_imza_tekrarlanmaz() -> None:
    new, ongoing, _ = classify([make_alert()], {"STOK_CAKISMASI:sku-1": ANCHOR.isoformat()}, now=ANCHOR)
    assert new == []
    assert len(ongoing) == 1
