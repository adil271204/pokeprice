"""
Cardmarket-Provider — nutzt die offizielle API v2.0 mit OAuth 1.0a / HMAC-SHA1.

Wichtige Architektur-Entscheidungen:
- Kein Scraping (verstößt gegen Cardmarket-AGB).
- OAuth wird manuell implementiert (kein externes Paket).
- Der realm-Parameter im Authorization-Header ist die rohe, unkodierte URL
  und fließt NICHT in den Signatur-Base-String ein (RFC 5849 §3.4.1.3.1).
"""
import hashlib
import hmac
import json
import time
import urllib.parse
import uuid
from typing import List, Optional

import requests

from config import CardmarketConfig
from models import CardRef, PriceQuote
from providers.base import PriceProvider


def _pct(value: str) -> str:
    """RFC-3986-Percent-Encoding mit safe='~' wie von OAuth 1.0a gefordert."""
    return urllib.parse.quote(str(value), safe="~")


def _build_auth_header(
    method: str,
    url: str,
    cfg: CardmarketConfig,
    extra_params: Optional[dict] = None,
) -> str:
    """
    Erzeugt den OAuth 1.0a Authorization-Header für eine Cardmarket-Anfrage.

    Ablauf:
    1. OAuth-Pflichtparameter zusammenstellen (oauth_*).
    2. Query-Parameter der URL + oauth_*-Parameter alphabetisch sortiert
       zusammenführen → Signatur-Parameter.
    3. Signatur-Base-String = METHOD & pct(URL ohne Query) & pct(param_string).
    4. Signing-Key = pct(consumer_secret) & pct(token_secret).
    5. HMAC-SHA1 → base64 → oauth_signature.
    6. Authorization-Header zusammensetzen: realm (roh, unkodiert) zuerst,
       dann alle oauth_*-Werte in Anführungszeichen.
    """
    # Schritt 1: OAuth-Parameter
    oauth_params = {
        "oauth_consumer_key": cfg.app_token,
        "oauth_nonce": uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": cfg.access_token,
        "oauth_version": "1.0",
    }

    # Schritt 2: Query-String der URL parsen und mit oauth_* zusammenführen
    parsed = urllib.parse.urlparse(url)
    # Basis-URL für Signatur = Schema + Host + Pfad (ohne Query-String)
    base_url = urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, "", "", "")
    )

    query_params = dict(urllib.parse.parse_qsl(parsed.query))
    all_params = {**query_params, **(extra_params or {}), **oauth_params}

    # Alphabetisch sortiert, Key und Value jeweils RFC-3986-kodiert
    sorted_params = sorted(
        (_pct(k), _pct(v)) for k, v in all_params.items()
    )
    param_string = "&".join(f"{k}={v}" for k, v in sorted_params)

    # Schritt 3: Signatur-Base-String
    base_string = "&".join([
        method.upper(),
        _pct(base_url),
        _pct(param_string),
    ])

    # Schritt 4: Signing-Key
    signing_key = (
        _pct(cfg.app_secret) + "&" + _pct(cfg.access_secret)
    ).encode("ascii")

    # Schritt 5: HMAC-SHA1
    import base64
    raw_signature = hmac.new(
        signing_key,
        base_string.encode("ascii"),
        hashlib.sha1,
    ).digest()
    signature = base64.b64encode(raw_signature).decode("ascii")

    oauth_params["oauth_signature"] = signature

    # Schritt 6: Header aufbauen.
    # realm = rohe (unkodierte) Request-URL (inkl. Query-String) — darf NICHT
    # in den Base-String einfließen, steht aber im Header (RFC 5849 §3.5.1).
    header_parts = [f'realm="{url}"']
    for key in sorted(oauth_params):
        header_parts.append(f'{key}="{_pct(oauth_params[key])}"')

    return "OAuth " + ", ".join(header_parts)


class CardmarketProvider(PriceProvider):
    """Holt Preise von Cardmarket über die offizielle REST-API."""

    GAME_ID_POKEMON = 6  # Cardmarket-interne ID für Pokémon TCG

    def __init__(self, cfg: CardmarketConfig) -> None:
        self._cfg = cfg
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    @property
    def available(self) -> bool:
        return self._cfg.is_configured

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """Sendet einen authentifizierten GET-Request an die Cardmarket-API."""
        base = self._cfg.base_url.rstrip("/")
        # URL mit Query-Parametern zusammensetzen (für realm und Base-String)
        query_string = urllib.parse.urlencode(params or {})
        full_url = f"{base}{path}"
        if query_string:
            full_url = f"{full_url}?{query_string}"

        auth_header = _build_auth_header("GET", full_url, self._cfg)
        resp = self._session.get(full_url, headers={"Authorization": auth_header})
        resp.raise_for_status()
        return resp.json()

    def _find_product_id(self, card: CardRef) -> Optional[int]:
        """Sucht die Cardmarket-Produkt-ID für eine Karte (falls nicht gecacht)."""
        if card.cardmarket_product_id:
            return card.cardmarket_product_id

        query = card.search_query or f"{card.name} {card.set_name}"
        data = self._get(
            "/products/find",
            params={"search": query, "exact": "false", "idGame": self.GAME_ID_POKEMON},
        )
        products = data.get("product", [])
        if not products:
            return None
        # Ersten Treffer nehmen; für bessere Genauigkeit Kartennummer abgleichen
        for p in products:
            if str(p.get("number", "")).lower() == card.number.lower():
                return int(p["idProduct"])
        return int(products[0]["idProduct"])

    def quotes_for(self, card: CardRef) -> List[PriceQuote]:
        product_id = self._find_product_id(card)
        if product_id is None:
            return []

        data = self._get(f"/products/{product_id}")
        product = data.get("product", {})
        guide = product.get("priceGuide", {})

        # Cardmarket liefert LOW, TREND, AVG in EUR
        low = guide.get("LOW") or guide.get("LOWEX") or None
        trend = guide.get("TREND") or None
        avg = guide.get("AVG") or None
        url = f"https://www.cardmarket.com/de/Pokemon/Products/Singles/{product_id}"

        return [
            PriceQuote(
                provider="cardmarket",
                currency="EUR",
                low=float(low) if low is not None else None,
                trend=float(trend) if trend is not None else None,
                avg=float(avg) if avg is not None else None,
                listings_count=int(product.get("countArticles", 0)),
                grade=None,
                url=url,
            )
        ]
