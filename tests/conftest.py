"""Ortak pytest fixture'ları ve örnek veri yolları.

Depodaki ``examples/data`` kümesi sistemin kendisidir: sabit bir zaman çapasına göre yazılmıştır,
bu yüzden her kural deterministik olarak doğrulanabilir. Testler bu klasörü asla yerinde
değiştirmez; yazan testler ``sandbox_examples`` kopyasını kullanır.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from sentinel.channels import Channel
from sentinel.channels.fixture import FixtureChannel
from sentinel.profiles import load_profiles
from tests.factories import ANCHOR

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples" / "data"

__all__ = ["ANCHOR", "EXAMPLES_DIR", "channels", "examples_dir", "sandbox_examples"]


@pytest.fixture(scope="session")
def examples_dir() -> Path:
    return EXAMPLES_DIR


@pytest.fixture(scope="session")
def channels(examples_dir: Path) -> dict[str, Channel]:
    """Örnek profillerden kurulmuş örnek kanallar (durum yazmaz)."""
    profiles = load_profiles(examples_dir / "profiles")
    return {name: FixtureChannel(profile, examples_dir / f"{name}.json") for name, profile in profiles.items()}


@pytest.fixture
def sandbox_examples(tmp_path: Path) -> Path:
    """Örnek verinin geçici kopyası — CLI testleri depodaki ``state.json``'ı bozmaz."""
    target = tmp_path / "data"
    shutil.copytree(EXAMPLES_DIR, target)
    return target
