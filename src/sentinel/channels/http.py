"""Dayanıklı, salt okunur HTTP kanalı.

Politika örnek kanalla aynıdır:

* yalnızca ``GET``,
* 429/5xx → üstel geri çekilme ile yeniden dene,
* 401 → net Türkçe hata (anahtar değeri asla loglanmaz / mesaja yazılmaz),
* diğer 4xx → yeniden denemeden anlaşılır hata,
* ``items_path`` nokta yolu ile liste çıkar, ``field_map`` ile normalize et.
"""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from typing import Any, Final

import httpx

from sentinel.channels import ChannelError, NotConfiguredError
from sentinel.models import Listing
from sentinel.parsing import build_listing, select_path
from sentinel.profiles import MarketplaceProfile, ProfileError, resolve_secret

RETRY_STATUS_CODES: Final = frozenset({429, 500, 502, 503, 504})
MAX_PAGES: Final = 50
DEFAULT_USER_AGENT: Final = "marketplace-sentinel/0.1.0 (+https://github.com/acar32furkan-glitch/marketplace-sentinel)"


class HttpChannel:
    """Profilde tanımlı pazaryeri API'sinden sayfalayarak liste çeker."""

    def __init__(
        self,
        profile: MarketplaceProfile,
        env: Mapping[str, str] | None = None,
        client: httpx.Client | None = None,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
    ) -> None:
        self.profile = profile
        self.name = profile.name
        self._env: Mapping[str, str] = dict(os.environ) if env is None else env
        self._client = client if client is not None else httpx.Client(base_url=profile.base_url, timeout=10.0)
        self._owns_client = client is None
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

    def close(self) -> None:
        """Kendi açtığı HTTP istemcisini kapat (dışarıdan verilen istemciye dokunma)."""
        if self._owns_client:
            self._client.close()

    def headers(self) -> dict[str, str]:
        """İstek başlıklarını üret (kimlik bilgisi değeri asla dışa yazılmaz).

        Raises:
            NotConfiguredError: Gereken ortam değişkeni boşsa.
        """
        headers = {
            "Accept": "application/json",
            "User-Agent": self.profile.user_agent or DEFAULT_USER_AGENT,
        }
        try:
            headers.update(resolve_secret(self.profile, self._env))
        except ProfileError as exc:
            raise NotConfiguredError(str(exc)) from exc
        return headers

    def fetch_listings(self, *, limit: int = 500) -> list[Listing]:
        """Sayfaları gezerek en fazla ``limit`` listeyi normalize edilmiş hâlde döndür.

        Raises:
            NotConfiguredError: Kimlik bilgisi eksikse veya yol şablonu çözülemezse.
            ChannelError: İstek başarısızsa ya da yanıt beklenen biçimde değilse.
        """
        headers = self.headers()
        path = self._path()
        listings: list[Listing] = []
        page = 1
        while len(listings) < limit and page <= MAX_PAGES:
            size = min(self.profile.page_size, limit - len(listings))
            params = dict(self.profile.params)
            if self.profile.page_param:
                params[self.profile.page_param] = str(page)
            if self.profile.size_param:
                params[self.profile.size_param] = str(size)
            payload = self._get(path, params, headers)
            rows = self._rows(payload)
            if not rows:
                break
            for row in rows:
                if not isinstance(row, dict):
                    msg = f"{self.name}: liste kaydı nesne değil"
                    raise ChannelError(msg)
                try:
                    listings.append(build_listing(row, field_map=self.profile.field_map, marketplace=self.name))
                except ValueError as exc:
                    raise ChannelError(f"{self.name}: {exc}") from exc
                if len(listings) >= limit:
                    break
            if len(rows) < size:
                break
            page += 1
        return listings

    def _rows(self, payload: Any) -> list[Any]:
        rows = select_path(payload, self.profile.items_path)
        if rows is None:
            location = self.profile.items_path or "kök"
            msg = f"{self.name}: '{location}' yolu yanıtta bulunamadı"
            raise ChannelError(msg)
        if not isinstance(rows, list):
            msg = f"{self.name}: '{self.profile.items_path}' bir liste değil"
            raise ChannelError(msg)
        return rows

    def _path(self) -> str:
        template = self.profile.products_path
        if "{" not in template:
            return template
        try:
            return template.format(**self.profile.params)
        except KeyError as exc:
            msg = f"{self.name}: products_path içindeki {{{exc.args[0]}}} için params'ta değer yok"
            raise NotConfiguredError(msg) from exc

    def _get(self, path: str, params: dict[str, str], headers: dict[str, str]) -> Any:
        last_error = ""
        for attempt in range(self._max_retries):
            try:
                response = self._client.get(path, params=params, headers=headers)
            except httpx.HTTPError as exc:
                last_error = f"ağ hatası: {exc.__class__.__name__}"
            else:
                status = response.status_code
                if status == 401:
                    msg = (
                        f"{self.name}: kimlik bilgileri reddedildi (HTTP 401). "
                        "Sağlayıcı panelinden üretilen anahtar/şifre değerlerini kontrol edin."
                    )
                    raise ChannelError(msg)
                if status in RETRY_STATUS_CODES:
                    last_error = f"geçici hata: HTTP {status}"
                elif status >= 400:
                    msg = f"{self.name}: {path} isteği başarısız: HTTP {status}"
                    raise ChannelError(msg)
                else:
                    try:
                        return response.json()
                    except ValueError as exc:
                        msg = f"{self.name}: {path} yanıtı JSON olarak çözülemedi"
                        raise ChannelError(msg) from exc
            if attempt + 1 < self._max_retries:
                time.sleep(self._backoff_seconds * (2**attempt))
        msg = f"{self.name}: {path} isteği {self._max_retries} denemede başarısız oldu ({last_error})"
        raise ChannelError(msg)
