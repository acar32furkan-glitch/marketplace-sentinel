"""Rapor biçimleri: konsol metni, Markdown ve GitHub iş özeti."""

from __future__ import annotations

from collections.abc import Mapping

from sentinel.channels import Channel
from sentinel.models import AlertStatus, ScanResult
from sentinel.render import render_github_summary, render_markdown, render_scan_text
from sentinel.scan import run_scan
from tests.factories import ANCHOR_TEXT, dt

PREVIOUS = {
    "LISTE_YOK:sku-104": "2026-10-04T09:00:00+03:00",
    "FIYAT_SAPMASI:sku-999": "2026-10-05T09:00:00+03:00",
}


def _demo(channels: Mapping[str, Channel]) -> ScanResult:
    return run_scan(channels, now=dt(ANCHOR_TEXT), previous_state=PREVIOUS)


def test_konsol_raporu_uc_baslik_ve_durum_satirlari(channels: Mapping[str, Channel]) -> None:
    text = render_scan_text(_demo(channels))
    assert "KANAL ÇAKIŞMASI NÖBETÇİSİ" in text
    assert "YENİ (5)" in text
    assert "DEVAM EDEN (1)" in text
    assert "ÇÖZÜLDÜ (1)" in text
    assert "[KRİTİK]" in text
    assert "durum  :" in text
    assert "aksiyon:" in text
    assert "kanal  :" in text


def test_konsol_raporu_max_alerts_siniri(channels: Mapping[str, Channel]) -> None:
    text = render_scan_text(_demo(channels), max_alerts=1)
    assert "YENİ (5)" in text
    assert "uyarı daha var" in text


def test_konsol_raporu_kanal_hatasi_not_satiri() -> None:
    result = ScanResult(
        generated_at=dt(ANCHOR_TEXT),
        channels=("kanal_a", "kanal_b"),
        listings=0,
        alerts=(),
        new=(),
        ongoing=(),
        resolved=(),
        errors=("kanal_b: veri alınamadı",),
    )
    text = render_scan_text(result)
    assert "not: kanal_b: veri alınamadı" in text
    assert "Bildirilecek bir şey yok" in text


def test_konsol_raporu_bos_sonuc() -> None:
    result = ScanResult(
        generated_at=dt(ANCHOR_TEXT),
        channels=("kanal_a",),
        listings=0,
        alerts=(),
        new=(),
        ongoing=(),
        resolved=(),
    )
    assert "Bildirilecek bir şey yok" in render_scan_text(result)


def test_markdown_tablo_ve_altbilgi(channels: Mapping[str, Channel]) -> None:
    markdown = render_markdown(_demo(channels))
    assert markdown.startswith("### Kanal çakışması nöbetçisi")
    assert "| Durum | Önem | Kod | SKU | Kanallar |" in markdown
    assert "**Çözülen:**" in markdown
    assert "marketplace-sentinel" in markdown


def test_markdown_kanal_hatalari_bolumu() -> None:
    result = ScanResult(
        generated_at=dt(ANCHOR_TEXT),
        channels=("kanal_a",),
        listings=0,
        alerts=(),
        new=(),
        ongoing=(),
        resolved=(),
        errors=("kanal_a: 401",),
    )
    markdown = render_markdown(result)
    assert "**Kanal hataları:**" in markdown
    assert "- kanal_a: 401" in markdown


def test_markdown_durum_etiketi_ve_cozulen_imza(channels: Mapping[str, Channel]) -> None:
    markdown = render_markdown(_demo(channels))
    assert "`FIYAT_SAPMASI:sku-999`" in markdown


def test_github_ozeti_markdown_ile_ayni(channels: Mapping[str, Channel]) -> None:
    result = _demo(channels)
    assert render_github_summary(result) == render_markdown(result)


def test_durum_etiketleri_kullanilir(channels: Mapping[str, Channel]) -> None:
    result = _demo(channels)
    assert result.new[0].status is AlertStatus.NEW
    assert result.ongoing[0].status is AlertStatus.ONGOING
    assert result.resolved[0].status is AlertStatus.RESOLVED
    assert "yeni" in render_markdown(result)
