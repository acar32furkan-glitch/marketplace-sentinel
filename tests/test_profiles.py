"""Pazaryeri profilleri: yükleme, şema doğrulaması ve kimlik bilgisi çözümleme."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from sentinel.profiles import (
    AuthStyle,
    FieldMap,
    ProfileError,
    load_profiles,
    resolve_secret,
)
from tests.factories import make_profile

PROFILE_BODY = {
    "name": "kanal_c",
    "base_url": "https://ornek-c.example",
    "products_path": "/products",
    "auth": "none",
    "field_map": {"sku": "sku", "title": "title", "price": "price", "stock": "stock"},
}


def test_ornek_profiller_yuklenir(examples_dir: Path) -> None:
    profiles = load_profiles(examples_dir / "profiles")
    assert set(profiles) == {"kanal_a", "kanal_b"}
    assert profiles["kanal_a"].auth is AuthStyle.BASIC
    assert profiles["kanal_b"].auth is AuthStyle.BEARER
    assert profiles["kanal_a"].field_map.sku == "urun_kodu"
    assert profiles["kanal_b"].items_path == "payload.items"


def test_json_profil_de_yuklenir(tmp_path: Path) -> None:
    (tmp_path / "profil.json").write_text(json.dumps(PROFILE_BODY), encoding="utf-8")
    profiles = load_profiles(tmp_path)
    assert profiles["kanal_c"].base_url == "https://ornek-c.example"


def test_profil_klasoru_yoksa_dosya_hatasi(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="profil klasörü bulunamadı"):
        load_profiles(tmp_path / "yok")


def test_bos_klasor_profil_hatasi(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match="hiç profil bulunamadı"):
        load_profiles(tmp_path)


SIMPLE_YAML = "name: ayni\nbase_url: x\nproducts_path: /p\nfield_map: {sku: a, title: b, price: c, stock: d}\n"


def test_ayni_adli_iki_profil_reddedilir(tmp_path: Path) -> None:
    (tmp_path / "bir.yaml").write_text(SIMPLE_YAML, encoding="utf-8")
    (tmp_path / "iki.json").write_text(json.dumps(PROFILE_BODY | {"name": "ayni"}), encoding="utf-8")
    with pytest.raises(ProfileError, match="aynı adlı iki profil: ayni"):
        load_profiles(tmp_path)


def test_bozuk_sema_girdi_hatasi(tmp_path: Path) -> None:
    (tmp_path / "eksik.yaml").write_text("name: eksik\nbase_url: x\nproducts_path: /p\n", encoding="utf-8")
    with pytest.raises(ValueError, match="field_map"):
        load_profiles(tmp_path)


def test_nesne_olmayan_profil_reddedilir(tmp_path: Path) -> None:
    (tmp_path / "liste.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="nesne"):
        load_profiles(tmp_path)


def test_pyproject_ile_ayni_alan_adlari_korunur() -> None:
    profile = make_profile(field_map=FieldMap(sku="s", title="t", price="p", stock="k"))
    assert profile.field_map.stock == "k"
    assert profile.auth is AuthStyle.BEARER


def test_resolve_secret_none_bos_sozluk() -> None:
    assert resolve_secret(make_profile(auth=AuthStyle.NONE, token_env=None), {}) == {}


def test_resolve_secret_bearer() -> None:
    headers = resolve_secret(make_profile(auth=AuthStyle.BEARER), {"KANAL_B_TOKEN": "abc"})
    assert headers == {"Authorization": "Bearer abc"}


def test_resolve_secret_basic_base64() -> None:
    profile = make_profile(auth=AuthStyle.BASIC, token_env=None, username_env="U", password_env="P")
    headers = resolve_secret(profile, {"U": "kullanici", "P": "sifre"})
    expected = base64.b64encode(b"kullanici:sifre").decode("ascii")
    assert headers == {"Authorization": f"Basic {expected}"}


def test_resolve_secret_header_ozel_ve_varsayilan_ad() -> None:
    ozel = make_profile(auth=AuthStyle.HEADER, header_name="X-Firma-Anahtar")
    assert resolve_secret(ozel, {"KANAL_B_TOKEN": "k"}) == {"X-Firma-Anahtar": "k"}
    varsayilan = make_profile(auth=AuthStyle.HEADER, header_name=None)
    assert resolve_secret(varsayilan, {"KANAL_B_TOKEN": "k"}) == {"X-API-Key": "k"}


def test_resolve_secret_eksik_ortam_degiskeni_deger_sizdirilmaz() -> None:
    profile = make_profile(auth=AuthStyle.BEARER)
    with pytest.raises(ProfileError, match="KANAL_B_TOKEN") as excinfo:
        resolve_secret(profile, {})
    assert "Bearer" not in str(excinfo.value)


def test_resolve_secret_degisken_adi_tanimli_degilse() -> None:
    profile = make_profile(auth=AuthStyle.BEARER, token_env=None)
    with pytest.raises(ProfileError, match="ortam değişkeni adı profilde tanımlı değil"):
        resolve_secret(profile, {"KANAL_B_TOKEN": "k"})


def test_profil_fazla_alan_reddedilir(tmp_path: Path) -> None:
    body = PROFILE_BODY | {"bilinmeyen_alan": True}
    (tmp_path / "fazla.json").write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        load_profiles(tmp_path)
