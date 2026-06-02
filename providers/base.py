"""
Abstrakte Basisklasse für alle Preis-Provider.
"""
from abc import ABC, abstractmethod
from typing import List

from models import CardRef, PriceQuote


class PriceProvider(ABC):
    """Jeder Provider implementiert diese Schnittstelle."""

    @property
    @abstractmethod
    def available(self) -> bool:
        """True wenn der Provider konfiguriert und einsatzbereit ist."""

    @abstractmethod
    def quotes_for(self, card: CardRef) -> List[PriceQuote]:
        """Liefert eine oder mehrere PriceQuotes für die angegebene Karte."""
