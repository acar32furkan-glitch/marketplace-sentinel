"""Webhook teslimi: adres doğrulama, maskeleme, gövde ve teslim politikası.

Ağ çağrısı ``respx`` ile mock'lanır; hiçbir test gerçek ağa çıkmaz. Kuru çalışma testleri ayrıca
"istek atılmadı" iddiasını taşır — bu, özelliğin varsayılan güvenlik sözüdür.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from sentinel.cli import main
from sentinel.webhook import (
    WEBHOOK_URL_ENV,
    WebhookDelivery,
    WebhookError,
    build_body,
    deliver,
    encode_body,
    mask_url,
    resolve_url,
    validate_url,
)

SUCCESS = 0
FAILED = 1
INPUT_ERROR = 2
SECRET_TOKEN = "abcdefSECRETtoken"
SECRET_URL = f"https://hooks.example.test/services/T000/B000/{SECRET_TOKEN}"
PAYLOAD: dict[str, Any] = {
    "version": "0.1.0",
    "generated_at": "2026-10-06T09:00:00+03:00",
    "counts": {"new": 2, "ongoing": 0, "resolved": 0},
    "alerts": [{"code": "STOK_CAKISMASI", "severity": "critical"}],
}


# --- adres doğrulama -------------------------------------------------------------------------


def test_gecerli_adres_kirpilarak_doner() -> None:
    assert validate_url(f"  {SECRET_URL}  ") == SECRET_URL


def test_http_ve_port_kabul() -> None:
    assert validate_url("http://127.0.0.1:8080/hook") == "http://127.0.0.1:8080/hook"


def test_sema_desteklenmiyorsa_reddedilir() -> None:
    with pytest.raises(WebhookError) as excinfo:
        validate_url(f"ftp://hooks.example.test/{SECRET_TOKEN}")
    message = str(excinfo.value)
    assert "http:// veya https://" in message
    assert SECRET_TOKEN not in message


def test_sunucu_adi_yoksa_reddedilir() -> None:
    with pytest.raises(WebhookError):
        validate_url("https:///hook")


def test_bos_adres_reddedilir() -> None:
    with pytest.raises(WebhookError):
        validate_url("   ")


def test_adrese_gomulu_kimlik_bilgisi_reddedilir() -> None:
    with pytest.raises(WebhookError) as excinfo:
        validate_url("https://kullanici:cokgizli@hooks.example.test/hook")
    message = str(excinfo.value)
    assert "kullanıcı/şifre" in message
    assert "cokgizli" not in message


def test_fragment_reddedilir() -> None:
    with pytest.raises(WebhookError) as excinfo:
        validate_url("https://hooks.example.test/hook#bolum")
    assert "#" in str(excinfo.value)


def test_mask_url_yolu_ve_sorguyu_gizler() -> None:
    masked = mask_url(f"{SECRET_URL}?token={SECRET_TOKEN}")
    assert masked == "https://hooks.example.test/…"
    assert SECRET_TOKEN not in masked


def test_mask_url_kok_adreste_uc_nokta_yok() -> None:
    assert mask_url("https://hooks.example.test") == "https://hooks.example.test"
    assert mask_url("https://hooks.example.test:8443/") == "https://hooks.example.test:8443"


def test_mask_url_cozulemeyen_adres() -> None:
    assert mask_url("http://[gecersiz") == "(adres çözülemedi)"


# --- ortam değişkeni -------------------------------------------------------------------------


def test_bayrak_ortam_degiskenini_ezer() -> None:
    env = {WEBHOOK_URL_ENV: "https://env.example.test/hook"}
    assert resolve_url("https://bayrak.example.test/hook", env) == "https://bayrak.example.test/hook"


def test_bayrak_yoksa_ortam_degiskeni_kullanilir() -> None:
    env = {WEBHOOK_URL_ENV: " https://env.example.test/hook "}
    assert resolve_url(None, env) == "https://env.example.test/hook"


def test_bos_bayrak_ortam_degiskenine_duser() -> None:
    env = {WEBHOOK_URL_ENV: "https://env.example.test/hook"}
    assert resolve_url("   ", env) == "https://env.example.test/hook"


def test_ikisi_de_yoksa_none() -> None:
    assert resolve_url(None, {}) is None


def test_ortam_degiskeni_gecersizse_kaynak_adlandirilir() -> None:
    with pytest.raises(WebhookError) as excinfo:
        resolve_url(None, {WEBHOOK_URL_ENV: "ftp://env.example.test/hook"})
    assert WEBHOOK_URL_ENV in str(excinfo.value)


# --- gövde -----------------------------------------------------------------------------------


def test_build_body_zarf_ekler_ve_payload_korunur() -> None:
    body = build_body(PAYLOAD)
    assert body["event"] == "scan"
    assert body["schema"] == 1
    assert body["counts"] == PAYLOAD["counts"]
    assert body["alerts"] == PAYLOAD["alerts"]


def test_encode_body_turkce_kacissiz_ve_kararli() -> None:
    body = {"message": "KRİTİK", "counts": {"new": 1}}
    raw = encode_body(body)
    assert "KRİTİK".encode() in raw
    assert b"\\u" not in raw
    assert b" " not in raw.replace("KRİTİK".encode(), b"")
    assert hashlib.sha256(raw).hexdigest() == hashlib.sha256(encode_body(body)).hexdigest()


# --- teslim politikası -----------------------------------------------------------------------


@respx.mock
def test_kuru_calisma_istek_atmaz() -> None:
    route = respx.post(SECRET_URL).mock(return_value=httpx.Response(200))
    delivery = deliver(SECRET_URL, PAYLOAD)
    assert route.called is False
    assert delivery.dry_run is True
    assert delivery.sent is False
    assert delivery.attempts == 0
    assert delivery.ok is True
    assert delivery.url == "https://hooks.example.test/…"
    assert delivery.byte_count == len(encode_body(PAYLOAD))
    assert delivery.sha256 == hashlib.sha256(encode_body(PAYLOAD)).hexdigest()


def test_kuru_calisma_http_istemcisi_kurmaz(monkeypatch: pytest.MonkeyPatch) -> None:
    def patlat(*_args: object, **_kwargs: object) -> None:
        msg = "kuru çalışmada HTTP istemcisi kurulmamalı"
        raise AssertionError(msg)

    monkeypatch.setattr(httpx, "Client", patlat)
    assert deliver(SECRET_URL, PAYLOAD, dry_run=True).ok is True


@respx.mock
def test_basarili_teslim_govdeyi_ve_basliklari_tasir() -> None:
    body = build_body(PAYLOAD)
    route = respx.post(SECRET_URL).mock(return_value=httpx.Response(202))
    delivery = deliver(SECRET_URL, body, dry_run=False, backoff_seconds=0)
    request = route.calls[0].request
    assert delivery.sent is True
    assert delivery.attempts == 1
    assert delivery.status_code == 202
    assert delivery.error is None
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["User-Agent"].startswith("marketplace-sentinel/")
    assert request.content == encode_body(body)
    assert json.loads(request.content)["event"] == "scan"


@respx.mock
def test_disaridan_verilen_istemci_kapatilmaz() -> None:
    respx.post(SECRET_URL).mock(return_value=httpx.Response(200))
    client = httpx.Client(timeout=5.0)
    try:
        deliver(SECRET_URL, PAYLOAD, dry_run=False, client=client, backoff_seconds=0)
        assert client.is_closed is False
    finally:
        client.close()


@respx.mock
def test_500_sonrasi_basari_govdeyi_tekrar_yollar() -> None:
    route = respx.post(SECRET_URL).mock(
        side_effect=[httpx.Response(500), httpx.Response(200)],
    )
    delivery = deliver(SECRET_URL, PAYLOAD, dry_run=False, backoff_seconds=0)
    assert delivery.sent is True
    assert delivery.attempts == 2
    assert len(route.calls) == 2
    assert {call.request.content for call in route.calls} == {encode_body(PAYLOAD)}


@respx.mock
def test_429_denemeler_tukenince_hata() -> None:
    route = respx.post(SECRET_URL).mock(return_value=httpx.Response(429))
    delivery = deliver(SECRET_URL, PAYLOAD, dry_run=False, backoff_seconds=0, max_attempts=3)
    assert delivery.sent is False
    assert delivery.attempts == 3
    assert delivery.status_code == 429
    assert delivery.error == "geçici hata: HTTP 429"
    assert len(route.calls) == 3


@respx.mock
@pytest.mark.parametrize(("status", "beklenen"), [(401, "kimlik reddedildi"), (403, "kimlik reddedildi")])
def test_kimlik_reddi_yeniden_denenmez(status: int, beklenen: str) -> None:
    route = respx.post(SECRET_URL).mock(return_value=httpx.Response(status))
    delivery = deliver(SECRET_URL, PAYLOAD, dry_run=False, backoff_seconds=0)
    assert delivery.attempts == 1
    assert len(route.calls) == 1
    assert delivery.error is not None
    assert beklenen in delivery.error
    assert delivery.status_code == status


@respx.mock
def test_diger_4xx_yeniden_denenmez() -> None:
    route = respx.post(SECRET_URL).mock(return_value=httpx.Response(404))
    delivery = deliver(SECRET_URL, PAYLOAD, dry_run=False, backoff_seconds=0)
    assert delivery.attempts == 1
    assert len(route.calls) == 1
    assert delivery.error == "istek reddedildi: HTTP 404"


@respx.mock
def test_yonlendirme_izlenmez() -> None:
    route = respx.post(SECRET_URL).mock(
        return_value=httpx.Response(302, headers={"Location": "https://baska.example/hook"}),
    )
    delivery = deliver(SECRET_URL, PAYLOAD, dry_run=False, backoff_seconds=0)
    assert delivery.sent is False
    assert delivery.attempts == 1
    assert delivery.status_code == 302
    assert delivery.error == "yönlendirme izlenmedi: HTTP 302"
    assert len(route.calls) == 1


@respx.mock
def test_ag_hatasi_denemeleri_tuketir() -> None:
    route = respx.post(SECRET_URL).mock(side_effect=httpx.ConnectError("bağlantı yok"))
    delivery = deliver(SECRET_URL, PAYLOAD, dry_run=False, backoff_seconds=0, max_attempts=2)
    assert delivery.sent is False
    assert delivery.attempts == 2
    assert delivery.status_code is None
    assert delivery.error == "ağ hatası: ConnectError"
    assert len(route.calls) == 2


@respx.mock
def test_tek_deneme_secilebilir() -> None:
    route = respx.post(SECRET_URL).mock(return_value=httpx.Response(503))
    delivery = deliver(SECRET_URL, PAYLOAD, dry_run=False, backoff_seconds=0, max_attempts=1)
    assert delivery.attempts == 1
    assert len(route.calls) == 1


@respx.mock
def test_bekleme_sifir_degilse_de_denemeler_surer() -> None:
    respx.post(SECRET_URL).mock(side_effect=[httpx.Response(503), httpx.Response(204)])
    delivery = deliver(SECRET_URL, PAYLOAD, dry_run=False, backoff_seconds=0.001)
    assert delivery.sent is True
    assert delivery.attempts == 2


def test_to_json_maskeli_ve_tam() -> None:
    delivery = WebhookDelivery(
        url="https://hooks.example.test/…",
        dry_run=False,
        sent=False,
        attempts=3,
        byte_count=10,
        sha256="0" * 64,
        status_code=500,
        error="geçici hata: HTTP 500",
    )
    payload = delivery.to_json()
    assert payload["ok"] is False
    assert payload["status_code"] == 500
    assert set(payload) == {
        "url",
        "dry_run",
        "sent",
        "ok",
        "attempts",
        "status_code",
        "bytes",
        "sha256",
        "error",
    }


# --- CLI sözleşmesi --------------------------------------------------------------------------


@respx.mock
def test_cli_kuru_calisma_varsayilan_ve_maskseli(sandbox_examples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    route = respx.post(SECRET_URL).mock(return_value=httpx.Response(200))
    code = main(["scan", "--fixtures", str(sandbox_examples), "--no-state-write", "--webhook-url", SECRET_URL])
    err = capsys.readouterr().err
    assert code == FAILED
    assert route.called is False
    assert "kuru çalışma" in err
    assert "--webhook-send" in err
    assert "https://hooks.example.test/…" in err
    assert SECRET_TOKEN not in err


@respx.mock
def test_cli_webhook_send_teslim_eder(sandbox_examples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    route = respx.post(SECRET_URL).mock(return_value=httpx.Response(204))
    code = main(
        [
            "scan",
            "--fixtures",
            str(sandbox_examples),
            "--no-state-write",
            "--webhook-url",
            SECRET_URL,
            "--webhook-send",
        ]
    )
    err = capsys.readouterr().err
    assert code == FAILED
    assert len(route.calls) == 1
    assert "teslim edildi — HTTP 204" in err
    assert SECRET_TOKEN not in err


@respx.mock
def test_cli_teslim_hatasi_cikis_kodunu_degistirmez(sandbox_examples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    respx.post(SECRET_URL).mock(return_value=httpx.Response(500))
    code = main(
        [
            "scan",
            "--fixtures",
            str(sandbox_examples),
            "--fail-on",
            "none",
            "--no-state-write",
            "--webhook-url",
            SECRET_URL,
            "--webhook-send",
            "--json",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == SUCCESS
    assert payload["webhook"]["ok"] is False
    assert payload["webhook"]["attempts"] == 3
    assert "teslim edilemedi" in captured.err


def test_cli_webhook_yoksa_json_blok_yok(sandbox_examples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["scan", "--fixtures", str(sandbox_examples), "--no-state-write", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert "webhook" not in payload


def test_cli_gecersiz_adres_girdi_hatasi(sandbox_examples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["scan", "--fixtures", str(sandbox_examples), "--no-state-write", "--webhook-url", "ftp://x.example/h"])
    captured = capsys.readouterr()
    assert code == INPUT_ERROR
    assert "girdi hatası" in captured.err
    assert "--webhook-url" in captured.err
    assert captured.out == ""


@respx.mock
def test_cli_govde_dosyasi_gonderilen_baytlarla_ayni(
    sandbox_examples: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    route = respx.post(SECRET_URL).mock(return_value=httpx.Response(200))
    body_path = tmp_path / "govde" / "webhook.json"
    main(
        [
            "scan",
            "--fixtures",
            str(sandbox_examples),
            "--no-state-write",
            "--webhook-url",
            SECRET_URL,
            "--webhook-send",
            "--webhook-body",
            str(body_path),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    written = body_path.read_bytes()
    assert written == route.calls[0].request.content
    assert hashlib.sha256(written).hexdigest() == payload["webhook"]["sha256"]
    assert json.loads(written)["counts"] == payload["counts"]
    assert "webhook" not in json.loads(written)


@respx.mock
def test_cli_ortam_degiskeninden_adres(
    sandbox_examples: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    route = respx.post(SECRET_URL).mock(return_value=httpx.Response(200))
    monkeypatch.setenv(WEBHOOK_URL_ENV, SECRET_URL)
    code = main(["scan", "--fixtures", str(sandbox_examples), "--no-state-write", "--webhook-send"])
    assert code == FAILED
    assert len(route.calls) == 1
    assert "teslim edildi" in capsys.readouterr().err
