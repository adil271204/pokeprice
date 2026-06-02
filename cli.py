"""
pokeprice CLI — Befehle: add, check, check-all, list, history

Verwendung:
    python cli.py add "Pikachu ex" "Scarlet & Violet 151" "025/165"
    python cli.py check "Pikachu ex" "Scarlet & Violet 151" "025/165" --demo
    python cli.py check-all --demo
    python cli.py list
    python cli.py history "Pikachu ex" "Scarlet & Violet 151" "025/165"
"""
import argparse
import sys

import db
from config import load_config
from models import CardRef
from providers.cardmarket import CardmarketProvider
from providers.demo import DemoProvider
from providers.ebay import EbayProvider
from tracker import Tracker


def _fmt_price(val) -> str:
    return f"{val:.2f} €" if val is not None else "  —   "


def _print_quotes(quotes) -> None:
    if not quotes:
        print("  (keine Preise gefunden)")
        return
    header = f"  {'Provider':<30} {'Grade':<10} {'Low':>8} {'Trend':>8} {'Avg':>8} {'Anz':>5}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for q in quotes:
        grade = q.grade or "—"
        print(
            f"  {q.provider:<30} {grade:<10} "
            f"{_fmt_price(q.low):>8} {_fmt_price(q.trend):>8} "
            f"{_fmt_price(q.avg):>8} {q.listings_count:>5}"
        )


def _build_tracker(cfg, demo: bool) -> Tracker:
    if demo:
        providers = [DemoProvider()]
    else:
        providers = [
            CardmarketProvider(cfg.cardmarket),
            EbayProvider(cfg.ebay),
        ]
    return Tracker(cfg, providers)


# ------------------------------------------------------------------
# Befehle
# ------------------------------------------------------------------

def cmd_add(args, cfg) -> None:
    card = CardRef(
        name=args.name,
        set_name=args.set_name,
        number=args.number,
        cardmarket_product_id=args.mkm_id,
        search_query=args.query,
    )
    saved = db.upsert_card(cfg.db_path, card)
    print(f"Karte gespeichert: {saved.display()} (DB-ID {saved.id})")


def cmd_check(args, cfg) -> None:
    card = CardRef(
        name=args.name,
        set_name=args.set_name,
        number=args.number,
    )
    tracker = _build_tracker(cfg, args.demo)
    print(f"Prüfe Preise für: {card.display()}")
    quotes = tracker.check_card(card)
    _print_quotes(quotes)


def cmd_check_all(args, cfg) -> None:
    tracker = _build_tracker(cfg, args.demo)
    results = tracker.check_all()
    for card_label, quotes in results.items():
        print(f"\n{card_label}")
        _print_quotes(quotes)


def cmd_list(args, cfg) -> None:
    cards = db.list_cards(cfg.db_path)
    if not cards:
        print("Keine Karten gespeichert.")
        return
    print(f"{'ID':>4}  {'Name':<30} {'Set':<30} {'Nummer':<12}  MKM-ID")
    print("-" * 85)
    for c in cards:
        mkm = str(c.cardmarket_product_id) if c.cardmarket_product_id else "—"
        print(f"{c.id:>4}  {c.name:<30} {c.set_name:<30} {c.number:<12}  {mkm}")


def cmd_history(args, cfg) -> None:
    # Karte per Name + Set + Nummer identifizieren
    all_cards = db.list_cards(cfg.db_path)
    card = next(
        (c for c in all_cards
         if c.name == args.name and c.set_name == args.set_name
         and c.number == args.number),
        None,
    )
    if card is None:
        print("Karte nicht gefunden. Erst 'add' ausführen.")
        sys.exit(1)

    rows = db.price_history(
        cfg.db_path,
        card.id,
        provider=args.provider,
        limit=args.limit,
    )
    if not rows:
        print("Keine Historiedaten vorhanden.")
        return

    print(f"Preishistorie: {card.display()}")
    print(f"  {'Zeitstempel':<22} {'Provider':<30} {'Grade':<10} "
          f"{'Low':>8} {'Trend':>8} {'Avg':>8}")
    print("  " + "-" * 95)
    for q in rows:
        ts = q.captured_at.strftime("%Y-%m-%d %H:%M:%S")
        grade = q.grade or "—"
        print(
            f"  {ts:<22} {q.provider:<30} {grade:<10} "
            f"{_fmt_price(q.low):>8} {_fmt_price(q.trend):>8} {_fmt_price(q.avg):>8}"
        )


# ------------------------------------------------------------------
# Argument-Parser
# ------------------------------------------------------------------

def main() -> None:
    cfg = load_config()
    db.init_db(cfg.db_path)

    parser = argparse.ArgumentParser(
        prog="pokeprice",
        description="Pokémon-Karten Preis-Tracker",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # add
    p_add = sub.add_parser("add", help="Karte zur Watchlist hinzufügen")
    p_add.add_argument("name", help="Kartenname, z.B. 'Pikachu ex'")
    p_add.add_argument("set_name", help="Set-Name, z.B. 'Scarlet & Violet 151'")
    p_add.add_argument("number", help="Kartennummer, z.B. '025/165'")
    p_add.add_argument("--mkm-id", type=int, default=None,
                       dest="mkm_id", help="Cardmarket-Produkt-ID (optional)")
    p_add.add_argument("--query", default=None,
                       help="Eigener Suchbegriff für eBay (optional)")

    # check
    p_check = sub.add_parser("check", help="Aktuelle Preise für eine Karte abrufen")
    p_check.add_argument("name")
    p_check.add_argument("set_name")
    p_check.add_argument("number")
    p_check.add_argument("--demo", action="store_true",
                          help="Demo-Modus: Mock-Daten ohne Credentials")

    # check-all
    p_ca = sub.add_parser("check-all", help="Alle Karten der Watchlist prüfen")
    p_ca.add_argument("--demo", action="store_true")

    # list
    sub.add_parser("list", help="Alle gespeicherten Karten anzeigen")

    # history
    p_hist = sub.add_parser("history", help="Preishistorie einer Karte anzeigen")
    p_hist.add_argument("name")
    p_hist.add_argument("set_name")
    p_hist.add_argument("number")
    p_hist.add_argument("--provider", default=None,
                         help="Auf einen Provider filtern")
    p_hist.add_argument("--limit", type=int, default=20,
                         help="Maximale Anzahl Einträge (Standard: 20)")

    args = parser.parse_args()

    dispatch = {
        "add": cmd_add,
        "check": cmd_check,
        "check-all": cmd_check_all,
        "list": cmd_list,
        "history": cmd_history,
    }
    dispatch[args.command](args, cfg)


if __name__ == "__main__":
    main()
