"""
SQLite-Datenbankschicht.

Tabellen:
  cards  — Stammdaten der zu trackenden Karten (eine Zeile pro Karte)
  prices — Preisbeobachtungen (jeder Lauf fügt neue Zeilen hinzu → Historiedaten)
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Generator, List, Optional

from models import CardRef, PriceQuote

_DDL = """
CREATE TABLE IF NOT EXISTS cards (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    name                    TEXT    NOT NULL,
    set_name                TEXT    NOT NULL,
    number                  TEXT    NOT NULL,
    cardmarket_product_id   INTEGER,
    search_query            TEXT,
    UNIQUE(name, set_name, number)
);

CREATE TABLE IF NOT EXISTS prices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id         INTEGER NOT NULL REFERENCES cards(id),
    provider        TEXT    NOT NULL,
    currency        TEXT    NOT NULL DEFAULT 'EUR',
    low             REAL,
    trend           REAL,
    avg             REAL,
    listings_count  INTEGER NOT NULL DEFAULT 0,
    grade           TEXT,
    url             TEXT,
    captured_at     TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prices_card_id     ON prices(card_id);
CREATE INDEX IF NOT EXISTS idx_prices_captured_at ON prices(captured_at);
"""


def init_db(db_path: str) -> None:
    """Erstellt die Datenbank und alle Tabellen (idempotent)."""
    with sqlite3.connect(db_path) as con:
        con.executescript(_DDL)


@contextmanager
def _connect(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def upsert_card(db_path: str, card: CardRef) -> CardRef:
    """
    Fügt eine Karte ein oder gibt die bestehende zurück.
    Aktualisiert cardmarket_product_id und search_query falls gesetzt.
    """
    with _connect(db_path) as con:
        con.execute(
            """
            INSERT INTO cards (name, set_name, number, cardmarket_product_id, search_query)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name, set_name, number) DO UPDATE SET
                cardmarket_product_id = COALESCE(excluded.cardmarket_product_id,
                                                  cards.cardmarket_product_id),
                search_query = COALESCE(excluded.search_query, cards.search_query)
            """,
            (card.name, card.set_name, card.number,
             card.cardmarket_product_id, card.search_query),
        )
        row = con.execute(
            "SELECT id FROM cards WHERE name=? AND set_name=? AND number=?",
            (card.name, card.set_name, card.number),
        ).fetchone()
        return CardRef(
            name=card.name,
            set_name=card.set_name,
            number=card.number,
            cardmarket_product_id=card.cardmarket_product_id,
            search_query=card.search_query,
            id=row["id"],
        )


def list_cards(db_path: str) -> List[CardRef]:
    """Gibt alle gespeicherten Karten zurück."""
    with _connect(db_path) as con:
        rows = con.execute(
            "SELECT id, name, set_name, number, cardmarket_product_id, search_query "
            "FROM cards ORDER BY name, set_name"
        ).fetchall()
    return [
        CardRef(
            name=r["name"],
            set_name=r["set_name"],
            number=r["number"],
            cardmarket_product_id=r["cardmarket_product_id"],
            search_query=r["search_query"],
            id=r["id"],
        )
        for r in rows
    ]


def save_quotes(db_path: str, card_id: int, quotes: List[PriceQuote]) -> None:
    """Speichert neue Preiszeilen (immer INSERT, nie UPDATE — für Historiedaten)."""
    with _connect(db_path) as con:
        for q in quotes:
            con.execute(
                """
                INSERT INTO prices
                    (card_id, provider, currency, low, trend, avg,
                     listings_count, grade, url, captured_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card_id,
                    q.provider,
                    q.currency,
                    q.low,
                    q.trend,
                    q.avg,
                    q.listings_count,
                    q.grade,
                    q.url,
                    q.captured_at.isoformat(),
                ),
            )


def latest_quotes(db_path: str, card_id: int) -> List[PriceQuote]:
    """Gibt die neuesten Preiszeilen pro Provider zurück."""
    with _connect(db_path) as con:
        rows = con.execute(
            """
            SELECT p.*
            FROM prices p
            INNER JOIN (
                SELECT provider, MAX(captured_at) AS max_ts
                FROM prices
                WHERE card_id = ?
                GROUP BY provider
            ) latest ON p.provider = latest.provider
                     AND p.captured_at = latest.max_ts
                     AND p.card_id = ?
            ORDER BY p.provider
            """,
            (card_id, card_id),
        ).fetchall()
    return [_row_to_quote(r) for r in rows]


def price_history(
    db_path: str,
    card_id: int,
    provider: Optional[str] = None,
    limit: int = 50,
) -> List[PriceQuote]:
    """Liefert die Preishistorie für eine Karte, optional nach Provider gefiltert."""
    with _connect(db_path) as con:
        if provider:
            rows = con.execute(
                "SELECT * FROM prices WHERE card_id=? AND provider=? "
                "ORDER BY captured_at DESC LIMIT ?",
                (card_id, provider, limit),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM prices WHERE card_id=? "
                "ORDER BY captured_at DESC LIMIT ?",
                (card_id, limit),
            ).fetchall()
    return [_row_to_quote(r) for r in rows]


def _row_to_quote(row: sqlite3.Row) -> PriceQuote:
    return PriceQuote(
        provider=row["provider"],
        currency=row["currency"],
        low=row["low"],
        trend=row["trend"],
        avg=row["avg"],
        listings_count=row["listings_count"],
        grade=row["grade"],
        url=row["url"],
        captured_at=datetime.fromisoformat(row["captured_at"]),
        card_id=row["card_id"],
    )
