# pokeprice — Pokémon-Karten Preis-Tracker

Gewerblicher Preis-Tracker für Pokémon-Sammelkarten. Fragt Preise von
Cardmarket (EU) und eBay ab und baut eine lokale Preishistorie in einer
SQLite-Datenbank auf.

---

## Voraussetzungen

- Python 3.10+
- `pip install -r requirements.txt` (nur `requests` als externe Abhängigkeit)

---

## Setup

### 1. Repository klonen / Projektordner anlegen

```bash
cd pokeprice
pip install -r requirements.txt
cp .env.example .env
```

### 2. Cardmarket Dedicated App einrichten

1. Auf [cardmarket.com](https://www.cardmarket.com) einloggen.
2. **Konto → Account → Apps (Dedicated Apps)** aufrufen.
3. Neue Dedicated App erstellen (kostenfrei, sofort aktiv).
4. Die vier Werte in `.env` eintragen:
   - `MKM_APP_TOKEN` → **App Token** (= OAuth Consumer Key)
   - `MKM_APP_SECRET` → **App Secret** (= OAuth Consumer Secret)
   - `MKM_ACCESS_TOKEN` → **Access Token**
   - `MKM_ACCESS_SECRET` → **Access Token Secret**

> **Hinweis:** Dedicated Apps nutzen einen festen Access Token ohne
> Login-Redirect. Der Endpunkt ist `https://apiv2.cardmarket.com/ws/v2.0`
> (der alte `api.cardmarket.com` läuft Mai 2026 aus).

### 3. eBay Developer Keyset einrichten

1. Auf [developer.ebay.com](https://developer.ebay.com) registrieren/einloggen.
2. **Application Keys → Production Keyset** aufrufen (oder neu erstellen).
3. **Browse API** in den App Policies aktivieren (OAuth Scope
   `https://api.ebay.com/oauth/api_scope` genügt für die Client Credentials).
4. In `.env` eintragen:
   - `EBAY_CLIENT_ID` → **App ID (Client ID)**
   - `EBAY_CLIENT_SECRET` → **Cert ID (Client Secret)**

> **Wichtig:** Die Browse API liefert **aktive Angebotspreise**, keine echten
> Verkaufspreise. Für Sold-Comps benötigt man die Marketplace Insights API
> (separate eBay-Freigabe erforderlich) oder einen Aggregator.

---

## Schnellstart ohne Credentials (Demo-Modus)

```bash
# Karte hinzufügen
python cli.py add "Pikachu ex" "Scarlet & Violet 151" "025/165"

# Preise im Demo-Modus abrufen (synthetische Mock-Daten)
python cli.py check "Pikachu ex" "Scarlet & Violet 151" "025/165" --demo

# Alle Karten prüfen
python cli.py check-all --demo

# Watchlist anzeigen
python cli.py list

# Preishistorie anzeigen
python cli.py history "Pikachu ex" "Scarlet & Violet 151" "025/165"
```

---

## Befehlsübersicht

| Befehl | Beschreibung |
|---|---|
| `add <name> <set> <nummer>` | Karte zur Watchlist hinzufügen |
| `check <name> <set> <nummer>` | Aktuelle Preise abrufen & speichern |
| `check-all` | Alle Karten der Watchlist prüfen |
| `list` | Gespeicherte Karten anzeigen |
| `history <name> <set> <nummer>` | Preishistorie einer Karte anzeigen |

### Optionen für `add`

| Option | Beschreibung |
|---|---|
| `--mkm-id ID` | Cardmarket-Produkt-ID direkt angeben (überspringt Suche) |
| `--query "..."` | Eigener Suchbegriff für eBay |

### Optionen für `check` / `check-all`

| Option | Beschreibung |
|---|---|
| `--demo` | Demo-Modus: keine echten API-Calls |

### Optionen für `history`

| Option | Beschreibung |
|---|---|
| `--provider NAME` | Auf einen Provider filtern (z.B. `cardmarket`) |
| `--limit N` | Maximale Anzahl Einträge (Standard: 20) |

---

## Cron-Beispiel (tägliche Prüfung um 8:00 Uhr)

```cron
0 8 * * * cd /pfad/zu/pokeprice && /usr/bin/python3 cli.py check-all >> /var/log/pokeprice.log 2>&1
```

Oder mit virtualenv:

```cron
0 8 * * * /pfad/zu/pokeprice/venv/bin/python /pfad/zu/pokeprice/cli.py check-all >> /var/log/pokeprice.log 2>&1
```

---

## Preisquellen & Einschränkungen

| Quelle | Datentyp | Hinweis |
|---|---|---|
| **Cardmarket** | LOW, TREND, AVG (EUR) | Offizielle API, beste Datenqualität |
| **eBay** | Angebotspreise (aktiv) | Keine Verkaufspreise! |
| **eBay Graded** | PSA 10 / PSA 9 / CGC 10 | Dieselbe Browse API, nach Grade gefiltert |

**Kein Scraping:** Cardmarket-Scraping verstößt gegen die AGB und ist nicht
implementiert. Nur die offizielle OAuth-API wird genutzt.

---

## Architektur

```
pokeprice/
├── cli.py              # Einstiegspunkt, Argument-Parser
├── tracker.py          # Orchestrator (fragt alle Provider ab)
├── db.py               # SQLite-Schicht (cards + prices)
├── config.py           # .env-Loader, Config-Objekte
├── models.py           # CardRef, PriceQuote (Dataclasses)
├── providers/
│   ├── base.py         # Abstrakte PriceProvider-Klasse
│   ├── cardmarket.py   # OAuth 1.0a / HMAC-SHA1
│   ├── ebay.py         # OAuth 2.0 Client Credentials
│   └── demo.py         # Mock-Provider ohne Credentials
├── .env.example
├── .gitignore
└── requirements.txt
```

---

## Datenbankschema

```sql
cards  (id, name, set_name, number, cardmarket_product_id, search_query)
prices (id, card_id, provider, currency, low, trend, avg,
        listings_count, grade, url, captured_at)
```

Jeder `check`-Lauf fügt neue Zeilen in `prices` ein — die Historiedaten
werden nie überschrieben, sodass sich Preistrends über Zeit verfolgen lassen.
