"""Kanal sözleşmesi: bir pazaryerinden liste çekmenin tek arayüzü.

Kanal **salt okunurdur**: protokolde yazma üyesi yoktur, dolayısıyla nöbetçi satıcının hesabında
yanlışlıkla hiçbir şeyi değiştiremez.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sentinel.models import Listing


class ChannelError(RuntimeError):
    """Kanal veriyi okuyamadı (ağ, kimlik, biçim veya sözleşme hatası)."""


class NotConfiguredError(ChannelError):
    """Kanal, gereken kimlik bilgisi ortamda yokken kullanılmak istendi."""


@runtime_checkable
class Channel(Protocol):
    """Nöbetçinin bir pazaryerinden beklediği minimal okuma yüzeyi."""

    name: str

    def fetch_listings(self, *, limit: int = 500) -> list[Listing]:
        """Pazaryerinin güncel listelerini normalize edilmiş hâlde döndür."""
        ...
