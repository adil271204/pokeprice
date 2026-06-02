"""
Zentrale Datenmodelle. Alle Provider normalisieren ihre Antworten auf
PriceQuote – downstream wird nur damit gearbeitet.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class CardRef:
    """Eine zu trackende Karte."""
    name: str
    set_name: str
    number: str                          # Set-interne Kartennummer, z.B. "025/165"
    cardmarket_product_id: Optional[int] = None
    search_query: Optional[str] = None   # Überschreibt auto-Query auf eBay/Suche
    id: Optional[int] = None             # DB-Primärschlüssel (nach Insert gesetzt)

    def display(self) -> str:
        return f"{self.name} [{self.set_name} #{self.number}]"


@dataclass
class PriceQuote:
    """Eine einzelne Preisbeobachtung von einem Provider."""
    provider: str            # z.B. "cardmarket", "ebay", "ebay_graded_psa10"
    currency: str            # ISO-4217, z.B. "EUR"
    low: Optional[float]     # günstigstes Angebot
    trend: Optional[float]   # 7-Tage-Trendpreis (Cardmarket) / None bei eBay
    avg: Optional[float]     # Durchschnittspreis
    listings_count: int      # Anzahl gesehener Angebote
    grade: Optional[str]     # z.B. "PSA 10", None für Rohkarten
    url: Optional[str]       # Link zur Quelle
    captured_at: datetime = field(default_factory=datetime.utcnow)
    card_id: Optional[int] = None  # FK zur cards-Tabelle (nach DB-Insert)
