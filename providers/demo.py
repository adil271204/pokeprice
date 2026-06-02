"""
Demo-Provider: liefert plausible Mock-Quotes ohne Credentials.
Nützlich für Tests der kompletten Pipeline (CLI --demo).
"""
import random
from typing import List

from models import CardRef, PriceQuote
from providers.base import PriceProvider


class DemoProvider(PriceProvider):
    """Gibt synthetische Preise zurück — immer verfügbar, keine API-Keys nötig."""

    @property
    def available(self) -> bool:
        return True

    def quotes_for(self, card: CardRef) -> List[PriceQuote]:
        # Deterministischer Basis-Preis aus dem Kartennamen ableiten
        seed = sum(ord(c) for c in card.name + card.set_name)
        rng = random.Random(seed)
        base = round(rng.uniform(0.50, 120.00), 2)

        quotes = [
            PriceQuote(
                provider="demo_cardmarket",
                currency="EUR",
                low=round(base * 0.85, 2),
                trend=round(base, 2),
                avg=round(base * 1.05, 2),
                listings_count=rng.randint(5, 200),
                grade=None,
                url="https://www.cardmarket.com/de/Pokemon",
            ),
            PriceQuote(
                provider="demo_ebay",
                currency="EUR",
                low=round(base * 0.90, 2),
                trend=None,
                avg=round(base * 1.10, 2),
                listings_count=rng.randint(2, 80),
                grade=None,
                url="https://www.ebay.de",
            ),
            PriceQuote(
                provider="demo_ebay_graded_psa10",
                currency="EUR",
                low=round(base * 2.5, 2),
                trend=None,
                avg=round(base * 3.0, 2),
                listings_count=rng.randint(1, 15),
                grade="PSA 10",
                url="https://www.ebay.de",
            ),
        ]
        return quotes
