"""
Orchestrator: fragt alle verfügbaren Provider ab, isoliert Fehler und
speichert die Ergebnisse in der Datenbank.
"""
import time
from typing import List, Optional

from config import AppConfig
from db import list_cards, save_quotes, upsert_card
from models import CardRef, PriceQuote
from providers.base import PriceProvider


class Tracker:
    def __init__(
        self,
        config: AppConfig,
        providers: List[PriceProvider],
    ) -> None:
        self._cfg = config
        self._providers = [p for p in providers if p.available]

    def check_card(self, card: CardRef) -> List[PriceQuote]:
        """
        Fragt alle verfügbaren Provider für eine Karte ab.
        Provider-Fehler werden isoliert — eine ausgefallene Plattform
        bricht den gesamten Lauf nicht ab.
        """
        db_card = upsert_card(self._cfg.db_path, card)
        all_quotes: List[PriceQuote] = []

        for provider in self._providers:
            try:
                quotes = provider.quotes_for(db_card)
                for q in quotes:
                    q.card_id = db_card.id
                all_quotes.extend(quotes)
            except Exception as exc:
                print(f"  [WARNUNG] Provider {provider.__class__.__name__} "
                      f"für '{card.display()}' fehlgeschlagen: {exc}")

            # Rate-Limit-Pause zwischen Provider-Calls
            time.sleep(self._cfg.request_delay)

        if all_quotes:
            save_quotes(self._cfg.db_path, db_card.id, all_quotes)

        return all_quotes

    def check_all(self) -> dict:
        """
        Prüft alle gespeicherten Karten — geeignet für cron-Jobs.
        Gibt ein Dict {card.display(): [quotes]} zurück.
        """
        cards = list_cards(self._cfg.db_path)
        results = {}
        for card in cards:
            print(f"Prüfe: {card.display()}")
            quotes = self.check_card(card)
            results[card.display()] = quotes
        return results
