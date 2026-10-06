"""Pazaryeri profilleri: yeni bir kanal eklemek kod değil, bir dosya eklemektir.

Profil tamamen veriyle tanımlanır (YAML/JSON): alan eşlemesi, kimlik doğrulama biçimi, sayfalama
parametreleri ve liste yolunun nerede olduğu dosyadan okunur. Bu project'in ayırt edici tasarım
kararıdır — ``sentinel`` kodu değişmeden yeni bir pazaryeri eklenebilir.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

PROFILE_SUFFIXES = frozenset({".yaml", ".yml", ".json"})


class ProfileError(ValueError):
    """Profil dosyası okunamadı, tutarsız veya gereken kimlik bilgisi ortamda yok."""


class AuthStyle(StrEnum):
    """Pazaryerinin beklediği kimlik doğrulama biçimi."""

    NONE = "none"
    BASIC = "basic"
    BEARER = "bearer"
    HEADER = "header"


class FieldMap(BaseModel):
    """Pazaryeri alan adları → nöbetçi alanları eşlemesi (JSON anahtar adları)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sku: str
    title: str
    price: str
    stock: str
    list_price: str | None = None
    active: str | None = None
    updated_at: str | None = None
    barcode: str | None = None


class MarketplaceProfile(BaseModel):
    """Tek bir pazaryeri kanalının veriyle tanımlanmış tanımı."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    base_url: str
    products_path: str
    auth: AuthStyle = AuthStyle.NONE
    username_env: str | None = None
    password_env: str | None = None
    token_env: str | None = None
    header_name: str | None = None
    user_agent: str | None = None
    field_map: FieldMap
    params: dict[str, str] = Field(default_factory=dict)
    page_param: str | None = "page"
    size_param: str | None = "size"
    page_size: int = 100
    items_path: str | None = None


def load_profiles(directory: Path) -> dict[str, MarketplaceProfile]:
    """``directory`` içindeki YAML/JSON profilleri ad → profil sözlüğü olarak yükle.

    Args:
        directory: Profil dosyalarının bulunduğu klasör.

    Returns:
        Profil adına göre sıralı, ad → profil eşlemesi.

    Raises:
        FileNotFoundError: Klasör yoksa.
        ProfileError: Aynı ada sahip iki profil varsa veya hiç profil bulunamazsa.
        ValueError: Bir dosya şemaya uymuyorsa (pydantic doğrulaması).
    """
    if not directory.is_dir():
        msg = f"profil klasörü bulunamadı: {directory}"
        raise FileNotFoundError(msg)
    profiles: dict[str, MarketplaceProfile] = {}
    sources: dict[str, str] = {}
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in PROFILE_SUFFIXES:
            continue
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            msg = f"{path.name}: profil bir nesne (map) olmalı"
            raise ProfileError(msg)
        profile = MarketplaceProfile.model_validate(raw)
        if profile.name in profiles:
            msg = f"aynı adlı iki profil: {profile.name} ({sources[profile.name]} ve {path.name})"
            raise ProfileError(msg)
        profiles[profile.name] = profile
        sources[profile.name] = path.name
    if not profiles:
        msg = f"hiç profil bulunamadı: {directory}"
        raise ProfileError(msg)
    return profiles


def resolve_secret(profile: MarketplaceProfile, env: Mapping[str, str]) -> dict[str, str]:
    """Profilin kimlik doğrulama başlığını üret.

    Gizli değerin kendisi hata mesajına **asla** yazılmaz; yalnızca eksik ortam değişkeninin adı
    bildirilir.

    Args:
        profile: Kimlik doğrulama biçimini ve ortam değişkeni adlarını taşıyan profil.
        env: Ortam değişkenleri (testlerde ``monkeypatch`` veya sözlük ile verilir).

    Returns:
        İsteğe eklenecek başlıklar (``AuthStyle.NONE`` için boş sözlük).

    Raises:
        ProfileError: Gereken ortam değişkeni tanımlı değilse.
    """
    if profile.auth is AuthStyle.NONE:
        return {}
    if profile.auth is AuthStyle.BEARER:
        token = _required_env(profile, env, profile.token_env, "token")
        return {"Authorization": f"Bearer {token}"}
    if profile.auth is AuthStyle.BASIC:
        username = _required_env(profile, env, profile.username_env, "kullanıcı adı")
        password = _required_env(profile, env, profile.password_env, "şifre")
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}
    token = _required_env(profile, env, profile.token_env, "anahtar")
    return {profile.header_name or "X-API-Key": token}


def _required_env(
    profile: MarketplaceProfile,
    env: Mapping[str, str],
    variable: str | None,
    label: str,
) -> str:
    if not variable:
        msg = f"{profile.name}: {label} için ortam değişkeni adı profilde tanımlı değil"
        raise ProfileError(msg)
    value = env.get(variable, "").strip()
    if not value:
        msg = f"{profile.name}: {label} için {variable} ortam değişkeni boş (değeri loglanmaz)"
        raise ProfileError(msg)
    return value
