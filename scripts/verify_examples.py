"""Örnek veri kümesinin nöbetçiyle tutarlı olduğunu doğrulayan küçük CI kontrolü.

Kullanım: ``uv run python scripts/verify_examples.py``

Dört kural kodunun da örnek veride tetiklendiğini ve kanal hatası olmadığını kontrol eder; veri
bozulursa (örneğin bir SKU'nun fiyatı değişirse) CI kırmızıya döner.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sentinel.channels.fixture import FixtureChannel
from sentinel.parsing import DEMO_NOW
from sentinel.profiles import load_profiles
from sentinel.rules import RULES
from sentinel.scan import run_scan

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "examples" / "data"
EXPECTED_CODES = frozenset({"STOK_CAKISMASI", "FIYAT_SAPMASI", "LISTE_YOK", "VERI_BAYAT"})


def main() -> int:
    """Örnek veriyi tara ve beklenen tüm kural kodlarının tetiklendiğini doğrula."""
    profiles = load_profiles(FIXTURES / "profiles")
    channels = {name: FixtureChannel(profile, FIXTURES / f"{name}.json") for name, profile in profiles.items()}
    result = run_scan(channels, now=DEMO_NOW)
    codes = set(result.by_code())
    missing = sorted(EXPECTED_CODES - codes)
    print(f"kanal: {', '.join(result.channels)}  ·  listelenen ürün: {result.listings}")
    print(f"kural: {len(RULES)}  ·  uyarı: {len(result.alerts)}  ·  kodlar: {', '.join(sorted(codes))}")
    if result.errors:
        print("kanal hataları: " + "; ".join(result.errors), file=sys.stderr)
        return 1
    if missing:
        print(f"HATA: şu kodlar örnek veride bulunamadı: {', '.join(missing)}", file=sys.stderr)
        return 1
    print("tamam: örnek veri beklenen tüm kural kodlarını tetikliyor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
