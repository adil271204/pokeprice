"""
eBay-Provider — nutzt die Browse API für aktive Angebote.

WICHTIG: Die Browse API liefert aktive Angebotspreise (Ask-Prices),
KEINE echten Verkaufspreise. Für echte Sold-Comps benötigt man die
Marketplace Insights API (erfordert separate eBay-Freigabe) oder
einen Dritt-Aggregator (z.B. 130point.com). Die hier ermittelten
Preise eignen sich für Preisorientierung, nicht für genaue
Marktpreisanalysen.
"""
import base64
import time
import urllib.parse
from typing import List, Optional

import requests

from config import EbayConfig
from models import CardRef, PriceQuote
from providers.base import PriceProvider

_EBAY_AUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
_EBAY_BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_EBAY_SCOPE = "https://api.ebay.com/oauth/api_scope"

# Graded-Suchen: Suchterm-Zusatz → Grade-Label
_GRADED_QUERIES = {
    "PSA 10": "PSA 10",
    "PSA 9": "PSA 9",
    "CGC 10": "CGC 10 Pristine",
}


class EbayProvider(PriceProvider):
    """Holt Preise von eBay (aktive Angebote, Marktplatz Deutschland)."""

    def __init__(self, cfg: EbayConfig) -> None:
        self._cfg = cfg
        self._session = requests.Session()
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    @property
    def available(self) -> bool:
        return self._cfg.is_configured

    # ------------------------------------------------------------------
    # OAuth 2.0 Client Credentials
    # ------------------------------------------------------------------

    def _ensure_token(self) -> str:
        """Gibt einen gültigen Bearer-Token zurück; holt bei Bedarf einen neuen."""
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        credentials = base64.b64encode(
            f"{self._cfg.client_id}:{self._cfg.client_secret}".encode()
        ).decode()

        resp = requests.post(
            _EBAY_AUTH_URL,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials",
                "scope": _EBAY_SCOPE,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + int(data.get("expires_in", 7200))
        return self._token

    # ------------------------------------------------------------------
    # Suche
    # ------------------------------------------------------------------

    def _search(self, query: str, limit: int = 50) -> List[dict]:
        """Führt eine Browse-API-Suche durch und gibt itemSummaries zurück."""
        token = self._ensure_token()
        resp = self._session.get(
            _EBAY_BROWSE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": self._cfg.marketplace_id,
            },
            params={"q": query, "limit": limit},
        )
        resp.raise_for_status()
        return resp.json().get("itemSummaries", [])

    def _items_to_quote(
        self,
        items: List[dict],
        provider_name: str,
        grade: Optional[str],
        query: str,
    ) -> Optional[PriceQuote]:
        if not items:
            return None

        prices = []
        for item in items:
            price_obj = item.get("price", {})
            try:
                prices.append(float(price_obj.get("value", 0)))
            except (TypeError, ValueError):
                pass

        if not prices:
            return None

        low = min(prices)
        avg = sum(prices) / len(prices)
        url = (
            "https://www.ebay.de/sch/i.html?_nkw="
            + urllib.parse.quote_plus(query)
        )
        return PriceQuote(
            provider=provider_name,
            currency="EUR",
            low=round(low, 2),
            trend=None,   # eBay liefert keinen Trend-Preis
            avg=round(avg, 2),
            listings_count=len(prices),
            grade=grade,
            url=url,
        )

    def quotes_for(self, card: CardRef) -> List[PriceQuote]:
        base_query = card.search_query or f"{card.name} {card.set_name} {card.number}"
        results: List[PriceQuote] = []

        # 1. Rohkarte (ungraduiert)
        items = self._search(base_query)
        q = self._items_to_quote(items, "ebay", None, base_query)
        if q:
            results.append(q)

        # 2. Graduierte Exemplare (PSA 10, PSA 9, CGC 10)
        for grade_label, grade_suffix in _GRADED_QUERIES.items():
            grade_query = f"{base_query} {grade_suffix}"
            grade_items = self._search(grade_query, limit=20)
            provider_id = "ebay_graded_" + grade_label.lower().replace(" ", "")
            gq = self._items_to_quote(grade_items, provider_id, grade_label, grade_query)
            if gq:
                results.append(gq)

        return results
