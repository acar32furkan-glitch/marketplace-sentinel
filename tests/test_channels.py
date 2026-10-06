"""Kanal uygulamaları: örnek (fixture) kanal ve HTTP kanalı.

HTTP testleri ``respx`` ile mock'lanır; hiçbir test gerçek ağa çıkmaz.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx

from sentinel.channels import Channel, ChannelError, NotConfiguredError
from sentinel.channels.fixture import FixtureChannel
from sentinel.channels.http import HttpChannel
from sentinel.profiles import AuthStyle, FieldMap, MarketplaceProfile, load_profiles
from tests.factories import make_profile

# ---------------------------------------------------------------- örnek kanal


def _write_listings(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_fixture_kanal_profille_okur(examples_dir: Path) -> None:
    profiles = load_profiles(examples_dir / "profiles")
    channel = FixtureChannel(profiles["kanal_a"], examples_dir / "kanal_a.json")
    listings = channel.fetch_listings()
    assert channel.name == "kanal_a"
    assert len(listings) == 7
    first = next(listing for listing in listings if listing.sku == "sku-101")
    assert first.marketplace == "kanal_a"
    assert first.price == Decimal("249.90")
    assert first.stock == 40
    assert first.active is True


def test_fixture_kanal_ad_ile_kanonik_alanlar(tmp_path: Path) -> None:
    path = _write_listings(
        tmp_path / "kanal_x.json",
        {"marketplace": "kanal_x", "listings": [{"sku": "s1", "title": "Ü", "price": "9.90", "stock": 3}]},
    )
    channel = FixtureChannel("kanal_x", path)
    listings = channel.fetch_listings()
    assert channel.name == "kanal_x"
    assert listings[0].sku == "s1"
    assert listings[0].stock == 3


def test_fixture_kanal_limit_uygular(examples_dir: Path) -> None:
    profiles = load_profiles(examples_dir / "profiles")
    channel = FixtureChannel(profiles["kanal_a"], examples_dir / "kanal_a.json")
    assert len(channel.fetch_listings(limit=2)) == 2


def test_fixture_kanal_protokol_uyumu(tmp_path: Path) -> None:
    path = _write_listings(tmp_path / "kanal_x.json", {"marketplace": "kanal_x", "listings": []})
    assert isinstance(FixtureChannel("kanal_x", path), Channel)


def test_fixture_kanal_dosya_yoksa(tmp_path: Path) -> None:
    with pytest.raises(ChannelError, match="örnek dosya bulunamadı"):
        FixtureChannel("kanal_x", tmp_path / "yok.json").fetch_listings()


def test_fixture_kanal_bozuk_json(tmp_path: Path) -> None:
    path = tmp_path / "bozuk.json"
    path.write_text("{bu json degil", encoding="utf-8")
    with pytest.raises(ChannelError, match="JSON olarak çözülemedi"):
        FixtureChannel("kanal_x", path).fetch_listings()


def test_fixture_kanal_kok_nesne_degil(tmp_path: Path) -> None:
    path = _write_listings(tmp_path / "liste.json", [1, 2, 3])
    with pytest.raises(ChannelError, match="nesne"):
        FixtureChannel("kanal_x", path).fetch_listings()


def test_fixture_kanal_listings_yok(tmp_path: Path) -> None:
    path = _write_listings(tmp_path / "bos.json", {"marketplace": "kanal_x"})
    with pytest.raises(ChannelError, match="'listings' listesi yok"):
        FixtureChannel("kanal_x", path).fetch_listings()


def test_fixture_kanal_kayit_nesne_degil(tmp_path: Path) -> None:
    path = _write_listings(tmp_path / "kayit.json", {"marketplace": "kanal_x", "listings": [1]})
    with pytest.raises(ChannelError, match="kayıt nesne değil"):
        FixtureChannel("kanal_x", path).fetch_listings()


def test_fixture_kanal_skusuz_kayit(tmp_path: Path) -> None:
    body = {"marketplace": "kanal_x", "listings": [{"title": "Ü"}]}
    path = _write_listings(tmp_path / "skusuz.json", body)
    with pytest.raises(ChannelError, match="SKU alanı boş"):
        FixtureChannel("kanal_x", path).fetch_listings()


# ----------------------------------------------------------------- HTTP kanal

TOKEN = "cok-gizli-token"
LIST_PAYLOAD = {
    "payload": {
        "items": [
            {
                "sku": "sku-1",
                "title": "Ürün",
                "price": 129.9,
                "stock": "7",
                "modifiedAt": 1_759_645_200_000,
                "barcode": "B-1",
            },
            {
                "sku": "sku-2",
                "title": "Ürün 2",
                "price": "49.95",
                "stock": 2,
                "modifiedAt": "2026-10-06T09:00:00Z",
            },
        ]
    }
}


def _channel(
    profile: MarketplaceProfile,
    *,
    env: dict[str, str] | None = None,
    client: httpx.Client | None = None,
    backoff_seconds: float = 0.0,
    max_retries: int = 3,
) -> HttpChannel:
    resolved_client = client or httpx.Client(base_url=profile.base_url, timeout=5.0)
    return HttpChannel(
        profile,
        env=env if env is not None else {"KANAL_B_TOKEN": TOKEN},
        client=resolved_client,
        backoff_seconds=backoff_seconds,
        max_retries=max_retries,
    )


@pytest.fixture
def http_channel() -> Iterator[HttpChannel]:
    profile = make_profile(
        field_map=FieldMap(
            sku="sku",
            title="title",
            price="price",
            stock="stock",
            updated_at="modifiedAt",
            barcode="barcode",
        )
    )
    client = httpx.Client(base_url=profile.base_url, timeout=5.0)
    channel = HttpChannel(profile, env={"KANAL_B_TOKEN": TOKEN}, client=client, backoff_seconds=0.0)
    yield channel
    client.close()


def _mock(profile: MarketplaceProfile) -> respx.Route:
    return respx.get(url__startswith=f"{profile.base_url}{profile.products_path}")


@respx.mock
def test_http_esleme_items_path_ve_tarih_cozumleme(http_channel: HttpChannel) -> None:
    _mock(http_channel.profile).mock(return_value=httpx.Response(200, json=LIST_PAYLOAD))
    listings = http_channel.fetch_listings()
    assert [listing.sku for listing in listings] == ["sku-1", "sku-2"]
    first, second = listings
    assert first.price == Decimal("129.90")
    assert first.stock == 7
    assert first.barcode == "B-1"
    assert first.updated_at.year == 2025  # epoch milis doğru çevrildi
    assert second.price == Decimal("49.95")
    assert second.updated_at.utcoffset() is not None


@respx.mock
def test_http_kok_liste_items_path_yok() -> None:
    profile = make_profile(items_path=None)
    client = httpx.Client(base_url=profile.base_url, timeout=5.0)
    channel = _channel(profile, client=client)
    respx.get(url__startswith=f"{profile.base_url}{profile.products_path}").mock(
        return_value=httpx.Response(200, json=[{"sku": "sku-1", "title": "Ü", "price": 1, "stock": 1}])
    )
    try:
        assert [listing.sku for listing in channel.fetch_listings()] == ["sku-1"]
    finally:
        client.close()


@respx.mock
def test_http_401_net_hata_ve_gizli_sizdirilmaz(http_channel: HttpChannel) -> None:
    _mock(http_channel.profile).mock(return_value=httpx.Response(401, json={}))
    with pytest.raises(ChannelError, match="HTTP 401") as excinfo:
        http_channel.fetch_listings()
    assert TOKEN not in str(excinfo.value)


@respx.mock
def test_http_429_sonra_basari_yeniden_dener(http_channel: HttpChannel) -> None:
    route = _mock(http_channel.profile)
    route.side_effect = [httpx.Response(429, json={}), httpx.Response(200, json=LIST_PAYLOAD)]
    assert len(http_channel.fetch_listings()) == 2
    assert route.call_count == 2


@respx.mock
def test_http_3_denemede_pes_eder(http_channel: HttpChannel) -> None:
    route = _mock(http_channel.profile)
    route.mock(return_value=httpx.Response(503, json={}))
    with pytest.raises(ChannelError, match="3 denemede başarısız oldu"):
        http_channel.fetch_listings()
    assert route.call_count == 3


@respx.mock
def test_http_400_yeniden_denemez(http_channel: HttpChannel) -> None:
    route = _mock(http_channel.profile)
    route.mock(return_value=httpx.Response(400, json={}))
    with pytest.raises(ChannelError, match="HTTP 400"):
        http_channel.fetch_listings()
    assert route.call_count == 1


@respx.mock
def test_http_ag_hatasi_sarmalanir(http_channel: HttpChannel) -> None:
    _mock(http_channel.profile).mock(side_effect=httpx.ConnectError("koptu"))
    with pytest.raises(ChannelError, match="ağ hatası"):
        http_channel.fetch_listings()


@respx.mock
def test_http_bozuk_json_sarmalanir(http_channel: HttpChannel) -> None:
    _mock(http_channel.profile).mock(return_value=httpx.Response(200, text="<html>"))
    with pytest.raises(ChannelError, match="JSON olarak çözülemedi"):
        http_channel.fetch_listings()


@respx.mock
def test_http_items_path_yolu_yoksa(http_channel: HttpChannel) -> None:
    _mock(http_channel.profile).mock(return_value=httpx.Response(200, json={"payload": {}}))
    with pytest.raises(ChannelError, match="yolu yanıtta bulunamadı"):
        http_channel.fetch_listings()


@respx.mock
def test_http_items_path_liste_degilse(http_channel: HttpChannel) -> None:
    _mock(http_channel.profile).mock(return_value=httpx.Response(200, json={"payload": {"items": "x"}}))
    with pytest.raises(ChannelError, match="bir liste değil"):
        http_channel.fetch_listings()


@respx.mock
def test_http_kayit_nesne_degilse(http_channel: HttpChannel) -> None:
    _mock(http_channel.profile).mock(return_value=httpx.Response(200, json={"payload": {"items": [1]}}))
    with pytest.raises(ChannelError, match="nesne değil"):
        http_channel.fetch_listings()


@respx.mock
def test_http_kanal_protokol_uyumu(http_channel: HttpChannel) -> None:
    _mock(http_channel.profile).mock(return_value=httpx.Response(200, json=LIST_PAYLOAD))
    assert isinstance(http_channel, Channel)


def test_http_kimlik_bilgisi_yoksa_not_configured() -> None:
    profile = make_profile()
    client = httpx.Client(base_url=profile.base_url, timeout=5.0)
    channel = _channel(profile, env={}, client=client)
    try:
        with pytest.raises(NotConfiguredError, match="KANAL_B_TOKEN"):
            channel.fetch_listings()
    finally:
        client.close()


@respx.mock
def test_http_yol_sablonu_ve_user_agent() -> None:
    profile = make_profile(
        name="kanal_a",
        base_url="https://ornek-a.example/api",
        products_path="/listings/merchantid/{merchant_id}",
        params={"merchant_id": "1001"},
        user_agent="satici-bot/9",
        auth=AuthStyle.NONE,
        token_env=None,
    )
    client = httpx.Client(base_url=profile.base_url, timeout=5.0)
    route = respx.get(url__startswith="https://ornek-a.example/api/listings/merchantid/1001").mock(
        return_value=httpx.Response(200, json=LIST_PAYLOAD)
    )
    channel = _channel(profile, client=client)
    try:
        assert len(channel.fetch_listings()) == 2
    finally:
        client.close()
    request = route.calls.last.request
    assert request.url.path == "/api/listings/merchantid/1001"
    assert request.headers["user-agent"] == "satici-bot/9"
    assert "authorization" not in request.headers


@respx.mock
def test_http_sayfalama_ikinci_sayfayi_ceker() -> None:
    profile = make_profile(page_size=2)
    client = httpx.Client(base_url=profile.base_url, timeout=5.0)
    page_one = {
        "payload": {
            "items": [
                {"sku": "s1", "title": "a", "price": 1, "stock": 1},
                {"sku": "s2", "title": "b", "price": 1, "stock": 1},
            ]
        }
    }
    page_two = {"payload": {"items": [{"sku": "s3", "title": "c", "price": 1, "stock": 1}]}}
    route = respx.get(url__startswith=f"{profile.base_url}{profile.products_path}")
    route.side_effect = [httpx.Response(200, json=page_one), httpx.Response(200, json=page_two)]
    channel = _channel(profile, client=client)
    try:
        listings = channel.fetch_listings()
    finally:
        client.close()
    assert [listing.sku for listing in listings] == ["s1", "s2", "s3"]
    assert route.call_count == 2


@respx.mock
def test_http_bos_sayfa_durur() -> None:
    profile = make_profile()
    client = httpx.Client(base_url=profile.base_url, timeout=5.0)
    route = respx.get(url__startswith=f"{profile.base_url}{profile.products_path}").mock(
        return_value=httpx.Response(200, json={"payload": {"items": []}})
    )
    channel = _channel(profile, client=client)
    try:
        assert channel.fetch_listings() == []
    finally:
        client.close()
    assert route.call_count == 1


def test_http_yol_sablonunda_parametre_yoksa() -> None:
    profile = make_profile(auth=AuthStyle.NONE, token_env=None, products_path="/x/{eksik}")
    client = httpx.Client(base_url=profile.base_url, timeout=5.0)
    channel = _channel(profile, client=client)
    try:
        with pytest.raises(NotConfiguredError, match="eksik"):
            channel.fetch_listings()
    finally:
        client.close()


@respx.mock
def test_http_limit_asildiginda_durur() -> None:
    profile = make_profile(page_size=100)
    client = httpx.Client(base_url=profile.base_url, timeout=5.0)
    route = respx.get(url__startswith=f"{profile.base_url}{profile.products_path}").mock(
        return_value=httpx.Response(200, json=LIST_PAYLOAD)
    )
    channel = _channel(profile, client=client)
    try:
        assert len(channel.fetch_listings(limit=1)) == 1
    finally:
        client.close()
    assert route.call_count == 1


def test_http_kendi_istemcisini_kapatir() -> None:
    channel = HttpChannel(make_profile(), env={"KANAL_B_TOKEN": TOKEN})
    channel.close()
