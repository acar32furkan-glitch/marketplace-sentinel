"""Örnek veri kanalı — kimlik bilgisi gerekmeden demoyu ve testleri mümkün kılar.

Dosya biçimi kasıtlı olarak basittir::

    {"marketplace": "kanal_a", "listings": [{"urun_kodu": "sku-101", ...}]}

``listings`` kayıtları profildeki ``field_map`` ile normalize edilir; yani örnek veri de canlı
kanalla aynı çevrim yolundan geçer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sentinel.channels import ChannelError
from sentinel.models import Listing
from sentinel.parsing import build_listing
from sentinel.profiles import FieldMap, MarketplaceProfile

CANONICAL_FIELD_MAP = FieldMap(sku="sku", title="title", price="price", stock="stock")
MARKETPLACE_KEY = "marketplace"
LISTINGS_KEY = "listings"


class FixtureChannel:
    """``{"marketplace": ..., "listings": [...]}`` biçimindeki JSON dosyasından okuyan kanal.

    Profil verilirse pazaryeri adı ve alan eşlemesi ondan gelir; kısa yol olarak yalnızca bir ad
    verilirse kanonik alan adları kullanılır.
    """

    def __init__(self, profile: MarketplaceProfile | str, path: Path) -> None:
        self._path = path
        if isinstance(profile, MarketplaceProfile):
            self.name = profile.name
            self._field_map = profile.field_map
        else:
            self.name = profile
            self._field_map = CANONICAL_FIELD_MAP

    def fetch_listings(self, *, limit: int = 500) -> list[Listing]:
        """Örnek dosyayı oku ve ``field_map`` ile normalize et.

        Raises:
            ChannelError: Dosya yok, JSON bozuk veya beklenen ``listings`` listesi yoksa.
        """
        if not self._path.is_file():
            msg = f"örnek dosya bulunamadı: {self._path}"
            raise ChannelError(msg)
        try:
            payload: Any = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            msg = f"{self._path.name} JSON olarak çözülemedi: {exc.msg}"
            raise ChannelError(msg) from exc
        if not isinstance(payload, dict):
            msg = f"{self._path.name} bir nesne (map) içermeli"
            raise ChannelError(msg)
        marketplace = str(payload.get(MARKETPLACE_KEY) or self.name)
        rows = payload.get(LISTINGS_KEY)
        if not isinstance(rows, list):
            msg = f"{self._path.name}: '{LISTINGS_KEY}' listesi yok"
            raise ChannelError(msg)
        listings: list[Listing] = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                msg = f"{self._path.name}: {index}. kayıt nesne değil"
                raise ChannelError(msg)
            try:
                listings.append(build_listing(row, field_map=self._field_map, marketplace=marketplace))
            except ValueError as exc:  # build_listing SKU'suz satırı reddeder
                raise ChannelError(f"{self._path.name}: {exc}") from exc
        return listings[:limit]
