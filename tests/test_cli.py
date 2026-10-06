"""CLI sözleşmesi: çıkış kodları, JSON çıktısı, rapor dosyası, durum ve iş özeti."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest

from sentinel.cli import main

SUCCESS = 0
FAILED = 1
INPUT_ERROR = 2


def test_scan_demo_kapiyi_dusurur(sandbox_examples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["scan", "--fixtures", str(sandbox_examples)])
    out = capsys.readouterr().out
    assert code == FAILED
    assert "STOK_CAKISMASI" in out
    assert "KARAR: KALDI" in out


def test_scan_fail_on_none_kapiyi_gecirir(sandbox_examples: Path) -> None:
    assert main(["scan", "--fixtures", str(sandbox_examples), "--fail-on", "none", "--no-state-write"]) == SUCCESS


def test_scan_state_dosyasi_olmadan_hepsi_yeni(sandbox_examples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (sandbox_examples / "state.json").unlink()
    main(["scan", "--fixtures", str(sandbox_examples), "--fail-on", "none", "--no-state-write"])
    assert "DEVAM EDEN 0" in capsys.readouterr().out


def test_scan_no_state_write_dosyayi_degistirmez(sandbox_examples: Path) -> None:
    before = (sandbox_examples / "state.json").read_text(encoding="utf-8")
    main(["scan", "--fixtures", str(sandbox_examples), "--no-state-write"])
    assert (sandbox_examples / "state.json").read_text(encoding="utf-8") == before


def test_scan_state_dosyasini_gunceller(sandbox_examples: Path) -> None:
    main(["scan", "--fixtures", str(sandbox_examples), "--fail-on", "none"])
    payload = json.loads((sandbox_examples / "state.json").read_text(encoding="utf-8"))
    assert "STOK_CAKISMASI:sku-102" in payload["alerts"]


def test_scan_json_sozlesmesi(sandbox_examples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["scan", "--fixtures", str(sandbox_examples), "--json", "--no-state-write"])
    payload = json.loads(capsys.readouterr().out)
    assert code == FAILED
    assert set(payload) >= {
        "version",
        "generated_at",
        "channels",
        "listings",
        "policy",
        "passed",
        "reasons",
        "counts",
        "codes",
        "errors",
        "new",
        "ongoing",
        "resolved",
        "alerts",
    }
    assert payload["passed"] is False
    assert payload["counts"] == {"new": 5, "ongoing": 1, "resolved": 1}
    assert payload["policy"] == "new-critical"
    assert any(item["code"] == "STOK_CAKISMASI" for item in payload["new"])
    assert payload["listings"] == 14


def test_scan_rapor_dosyasi_yazilir(sandbox_examples: Path, tmp_path: Path) -> None:
    target = tmp_path / "out" / "rapor.json"
    main(["scan", "--fixtures", str(sandbox_examples), "--report", str(target), "--json", "--no-state-write"])
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["listings"] == 14
    assert payload["passed"] is False


def test_scan_github_ozeti_yazilir(sandbox_examples: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    main(["scan", "--fixtures", str(sandbox_examples), "--github-summary", "--no-state-write"])
    text = summary.read_text(encoding="utf-8")
    assert "### Kanal çakışması nöbetçisi" in text


def test_scan_github_ozeti_ortam_degiskeni_yoksa(
    sandbox_examples: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    main(["scan", "--fixtures", str(sandbox_examples), "--github-summary", "--no-state-write"])
    assert "GITHUB_STEP_SUMMARY tanımlı değil" in capsys.readouterr().err


def test_scan_max_alerts_siniri(sandbox_examples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["scan", "--fixtures", str(sandbox_examples), "--max-alerts", "1", "--no-state-write"])
    assert "uyarı daha var" in capsys.readouterr().out


def test_scan_now_ile_bayat_veri_cogalir(sandbox_examples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(
        [
            "scan",
            "--fixtures",
            str(sandbox_examples),
            "--now",
            "2026-10-26T09:00:00+03:00",
            "--json",
            "--no-state-write",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["codes"].get("VERI_BAYAT", 0) >= 6


def test_scan_gecersiz_now_girdi_hatasi(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["scan", "--now", "dün"])
    assert code == INPUT_ERROR
    assert "girdi hatası" in capsys.readouterr().err


def test_scan_eksik_fixtures_girdi_hatasi(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["scan", "--fixtures", str(tmp_path / "yok")])
    assert code == INPUT_ERROR
    assert "girdi hatası" in capsys.readouterr().err


def test_scan_ayni_adli_iki_profil_girdi_hatasi(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    profiles = tmp_path / "data" / "profiles"
    profiles.mkdir(parents=True)
    body = "name: ayni\nbase_url: x\nproducts_path: /p\nfield_map: {sku: a, title: b, price: c, stock: d}\n"
    (profiles / "bir.yaml").write_text(body, encoding="utf-8")
    (profiles / "iki.yaml").write_text(body, encoding="utf-8")
    code = main(["scan", "--fixtures", str(tmp_path / "data")])
    assert code == INPUT_ERROR
    assert "aynı adlı iki profil" in capsys.readouterr().err


def test_state_show(sandbox_examples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["state", "show", "--state", str(sandbox_examples / "state.json")])
    out = capsys.readouterr().out
    assert code == SUCCESS
    assert "kayıtlı imza: 2" in out
    assert "LISTE_YOK:sku-104" in out


def test_state_show_json(sandbox_examples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["state", "show", "--state", str(sandbox_examples / "state.json"), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == SUCCESS
    assert payload["count"] == 2


def test_state_show_dosya_yoksa(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["state", "show", "--state", str(tmp_path / "yok.json")])
    assert code == INPUT_ERROR
    assert "bulunamadı" in capsys.readouterr().err


def test_state_alt_komut_yoksa(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["state"])
    assert code == INPUT_ERROR
    assert "'show'" in capsys.readouterr().err


def test_watch_iki_tur_ve_devam_edenler(sandbox_examples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["watch", "--fixtures", str(sandbox_examples), "--interval", "0", "--iterations", "2"])
    out = capsys.readouterr().out
    assert code == SUCCESS
    assert "tur 1/2" in out
    assert "tur 2/2" in out
    assert "DEVAM EDEN 6" in out


def test_watch_state_dosyasini_gunceller(sandbox_examples: Path) -> None:
    target = sandbox_examples / "watch-state.json"
    main(
        [
            "watch",
            "--fixtures",
            str(sandbox_examples),
            "--interval",
            "0",
            "--iterations",
            "1",
            "--state",
            str(target),
        ]
    )
    assert target.is_file()


def test_profiles_komutu(examples_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["profiles", "--fixtures", str(examples_dir)])
    out = capsys.readouterr().out
    assert code == SUCCESS
    assert "kanal_a" in out
    assert "basic" in out
    assert "bearer" in out
    assert "alan eşlemesi" in out


def test_profiles_json(examples_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["profiles", "--fixtures", str(examples_dir), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == SUCCESS
    assert {profile["name"] for profile in payload["profiles"]} == {"kanal_a", "kanal_b"}
    assert payload["profiles"][0]["field_map"]["sku"]


def test_surum_bayragi(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "sentinel" in capsys.readouterr().out


def test_komut_yoksa_yardim_ve_hata_kodu(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([])
    assert code == INPUT_ERROR
    assert "sentinel" in capsys.readouterr().out


@pytest.mark.integration
def test_main_modulu_giris_noktasi(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["sentinel", "--version"])
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("sentinel.__main__", run_name="__main__")
    assert excinfo.value.code == SUCCESS
    assert "sentinel" in capsys.readouterr().out
