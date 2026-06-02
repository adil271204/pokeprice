#!/usr/bin/env bash
# Render-Startskript: DB initialisieren und Dashboard starten
set -e

# Datenbank und Tabellen anlegen falls nicht vorhanden
python -c "from config import load_config; import db; cfg = load_config(); db.init_db(cfg.db_path); print(f'DB bereit: {cfg.db_path}')"

# Dashboard starten
exec python dashboard.py --no-browser
