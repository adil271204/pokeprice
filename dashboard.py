"""
pokeprice Web-Dashboard — lokaler HTTP-Server (nur stdlib + sqlite3).

Aufruf: python3 dashboard.py [--port 8080]
"""
import argparse
import http.server
import json
import sqlite3
import urllib.parse
import webbrowser
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────────
# Datenbankabfragen
# ──────────────────────────────────────────────────────────────────────────────

def _db_path() -> str:
    import os
    # .env lesen falls vorhanden
    env = Path(".env")
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("POKEPRICE_DB="):
                return line.split("=", 1)[1].strip().strip('"')
    return os.getenv("POKEPRICE_DB", "pokeprice.db")


def _connect():
    con = sqlite3.connect(_db_path())
    con.row_factory = sqlite3.Row
    return con


def api_cards():
    con = _connect()
    rows = con.execute(
        "SELECT id, name, set_name, number, cardmarket_product_id FROM cards ORDER BY name"
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def api_latest(card_id: int):
    con = _connect()
    rows = con.execute(
        """
        SELECT p.*
        FROM prices p
        INNER JOIN (
            SELECT provider, MAX(captured_at) AS max_ts
            FROM prices WHERE card_id = ?
            GROUP BY provider
        ) latest ON p.provider = latest.provider
                 AND p.captured_at = latest.max_ts
                 AND p.card_id = ?
        ORDER BY p.provider
        """,
        (card_id, card_id),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def api_history(card_id: int, provider: str | None = None, limit: int = 60):
    con = _connect()
    if provider:
        rows = con.execute(
            "SELECT * FROM prices WHERE card_id=? AND provider=? "
            "ORDER BY captured_at ASC LIMIT ?",
            (card_id, provider, limit),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM prices WHERE card_id=? ORDER BY captured_at ASC LIMIT ?",
            (card_id, limit),
        ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def api_summary():
    """Übersicht: Anzahl Karten, letzter Check, Arbitrage-Spannen."""
    con = _connect()
    total_cards = con.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    last_check = con.execute(
        "SELECT MAX(captured_at) FROM prices"
    ).fetchone()[0]

    # Arbitrage: Cardmarket LOW vs. eBay LOW (neueste Werte)
    arbitrage = con.execute(
        """
        SELECT c.id, c.name, c.set_name, c.number,
               mkm.low  AS mkm_low,
               ebay.low AS ebay_low,
               ROUND((ebay.low - mkm.low), 2) AS spread
        FROM cards c
        LEFT JOIN (
            SELECT card_id, low FROM prices
            WHERE provider='cardmarket' OR provider='demo_cardmarket'
            GROUP BY card_id HAVING captured_at = MAX(captured_at)
        ) mkm ON mkm.card_id = c.id
        LEFT JOIN (
            SELECT card_id, low FROM prices
            WHERE provider='ebay' OR provider='demo_ebay'
            GROUP BY card_id HAVING captured_at = MAX(captured_at)
        ) ebay ON ebay.card_id = c.id
        WHERE mkm.low IS NOT NULL AND ebay.low IS NOT NULL
        ORDER BY spread DESC
        """
    ).fetchall()
    con.close()
    return {
        "total_cards": total_cards,
        "last_check": last_check,
        "arbitrage": [dict(r) for r in arbitrage],
    }


# ──────────────────────────────────────────────────────────────────────────────
# HTTP-Handler
# ──────────────────────────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # Konsolenausgabe unterdrücken

    def _json(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, body: str):
        enc = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(enc))
        self.end_headers()
        self.wfile.write(enc)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = dict(urllib.parse.parse_qsl(parsed.query))

        if path == "/":
            self._html(HTML)
        elif path == "/api/cards":
            self._json(api_cards())
        elif path == "/api/summary":
            self._json(api_summary())
        elif path == "/api/latest":
            card_id = int(qs.get("card_id", 0))
            self._json(api_latest(card_id))
        elif path == "/api/history":
            card_id = int(qs.get("card_id", 0))
            provider = qs.get("provider") or None
            limit = int(qs.get("limit", 60))
            self._json(api_history(card_id, provider, limit))
        else:
            self.send_response(404)
            self.end_headers()


# ──────────────────────────────────────────────────────────────────────────────
# Frontend HTML (inline, keine externen Datei-Assets nötig)
# ──────────────────────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>pokeprice Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --surface2: #22263a;
    --border: #2e3250;
    --accent: #6c63ff;
    --accent2: #ff6584;
    --green: #36d399;
    --yellow: #fbbd23;
    --red: #f87272;
    --text: #e2e8f0;
    --muted: #718096;
    --radius: 12px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; font-size: 14px; }

  /* Layout */
  .app { display: grid; grid-template-columns: 260px 1fr; min-height: 100vh; }
  .sidebar { background: var(--surface); border-right: 1px solid var(--border); padding: 24px 0; display: flex; flex-direction: column; }
  .main { padding: 28px; overflow-y: auto; }

  /* Sidebar */
  .logo { padding: 0 20px 20px; font-size: 18px; font-weight: 700; color: var(--accent); letter-spacing: -0.5px; }
  .logo span { color: var(--text); }
  .nav-section { padding: 8px 20px 4px; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); }
  .card-item {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 20px; cursor: pointer; border-left: 3px solid transparent;
    transition: background 0.15s, border-color 0.15s;
  }
  .card-item:hover { background: var(--surface2); }
  .card-item.active { border-left-color: var(--accent); background: var(--surface2); }
  .card-item .badge {
    margin-left: auto; font-size: 11px; background: var(--accent);
    color: #fff; border-radius: 999px; padding: 1px 7px;
  }
  .card-name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .card-set { font-size: 11px; color: var(--muted); }

  /* Topbar */
  .topbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; }
  .topbar h1 { font-size: 20px; font-weight: 700; }
  .last-check { font-size: 12px; color: var(--muted); }

  /* Stats row */
  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
  .stat-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 18px 20px;
  }
  .stat-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
  .stat-value { font-size: 24px; font-weight: 700; }
  .stat-value.green { color: var(--green); }
  .stat-value.yellow { color: var(--yellow); }
  .stat-value.red { color: var(--red); }

  /* Price table */
  .section-title { font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase;
    letter-spacing: 0.8px; margin-bottom: 12px; }
  .price-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px;
    margin-bottom: 28px;
  }
  .price-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 16px;
  }
  .price-card .provider { font-size: 11px; color: var(--muted); margin-bottom: 4px; }
  .price-card .grade-badge {
    display: inline-block; font-size: 10px; background: var(--accent); color: #fff;
    border-radius: 4px; padding: 1px 6px; margin-bottom: 8px;
  }
  .price-card .price-row { display: flex; justify-content: space-between; margin-top: 6px; }
  .price-card .price-label { color: var(--muted); font-size: 12px; }
  .price-card .price-val { font-weight: 600; font-size: 13px; }
  .price-card .listings { font-size: 11px; color: var(--muted); margin-top: 8px; }

  /* Chart area */
  .chart-controls { display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
  .chip {
    padding: 5px 14px; border-radius: 999px; font-size: 12px; cursor: pointer;
    border: 1px solid var(--border); background: var(--surface2); color: var(--muted);
    transition: all 0.15s;
  }
  .chip.active { border-color: var(--accent); color: var(--accent); background: rgba(108,99,255,.12); }
  .chart-wrap { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 28px; }
  canvas { max-height: 280px; }

  /* Arbitrage table */
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 8px 12px; font-size: 11px; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--border); }
  td { padding: 10px 12px; border-bottom: 1px solid var(--border); }
  tr:last-child td { border-bottom: none; }
  .spread-pos { color: var(--green); font-weight: 600; }
  .spread-neg { color: var(--red); font-weight: 600; }

  /* Empty state */
  .empty { text-align: center; color: var(--muted); padding: 48px; }
  .empty .icon { font-size: 40px; margin-bottom: 12px; }

  /* Overview page */
  #page-overview, #page-card { display: none; }
  #page-overview.visible, #page-card.visible { display: block; }
</style>
</head>
<body>
<div class="app">
  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="logo">poke<span>price</span></div>
    <div class="nav-section">Übersicht</div>
    <div class="card-item" id="nav-overview" onclick="showOverview()">
      <div>
        <div class="card-name">Dashboard</div>
        <div class="card-set">Alle Karten</div>
      </div>
    </div>
    <div class="nav-section" style="margin-top:12px">Watchlist</div>
    <div id="card-list"></div>
  </aside>

  <!-- Main -->
  <main class="main">
    <!-- Übersicht -->
    <div id="page-overview">
      <div class="topbar">
        <h1>Übersicht</h1>
        <span class="last-check" id="last-check-label"></span>
      </div>
      <div class="stats">
        <div class="stat-card">
          <div class="stat-label">Karten</div>
          <div class="stat-value" id="stat-cards">—</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Beste Arbitrage-Spanne</div>
          <div class="stat-value green" id="stat-best-spread">—</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Karten im Gewinn</div>
          <div class="stat-value green" id="stat-pos">—</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Karten im Verlust</div>
          <div class="stat-value red" id="stat-neg">—</div>
        </div>
      </div>

      <div class="section-title">Arbitrage-Übersicht (Cardmarket LOW → eBay LOW)</div>
      <div class="chart-wrap">
        <table id="arb-table">
          <thead>
            <tr>
              <th>Karte</th><th>Set</th><th>Cardmarket LOW</th>
              <th>eBay LOW</th><th>Spanne</th>
            </tr>
          </thead>
          <tbody id="arb-body"></tbody>
        </table>
      </div>
    </div>

    <!-- Karten-Detail -->
    <div id="page-card">
      <div class="topbar">
        <div>
          <h1 id="detail-name">—</h1>
          <div class="last-check" id="detail-meta"></div>
        </div>
      </div>

      <div class="section-title">Aktuelle Preise</div>
      <div class="price-grid" id="price-grid"></div>

      <div class="section-title">Preisverlauf</div>
      <div class="chart-controls" id="provider-chips"></div>
      <div class="chart-wrap"><canvas id="history-chart"></canvas></div>
    </div>
  </main>
</div>

<script>
// ── State ────────────────────────────────────────────────────────────────────
let histChart = null;
let activeCardId = null;
let activeProviders = new Set();

// ── Hilfsfunktionen ──────────────────────────────────────────────────────────
const fmt = v => v != null ? v.toFixed(2) + ' €' : '—';
const PROVIDER_COLORS = [
  '#6c63ff','#ff6584','#36d399','#fbbd23','#f87272',
  '#38bdf8','#fb923c','#a78bfa','#34d399','#f472b6',
];

async function get(url) {
  const r = await fetch(url);
  return r.json();
}

// ── Sidebar laden ─────────────────────────────────────────────────────────────
async function loadSidebar() {
  const cards = await get('/api/cards');
  const list = document.getElementById('card-list');
  list.innerHTML = '';
  if (!cards.length) {
    list.innerHTML = '<div class="card-item"><div class="card-set">Keine Karten</div></div>';
    return;
  }
  for (const c of cards) {
    const el = document.createElement('div');
    el.className = 'card-item';
    el.id = `nav-card-${c.id}`;
    el.innerHTML = `
      <div style="overflow:hidden">
        <div class="card-name">${c.name}</div>
        <div class="card-set">${c.set_name} #${c.number}</div>
      </div>`;
    el.onclick = () => showCard(c);
    list.appendChild(el);
  }
}

// ── Übersicht ────────────────────────────────────────────────────────────────
async function showOverview() {
  setActivePage('overview');
  const summary = await get('/api/summary');

  document.getElementById('stat-cards').textContent = summary.total_cards;
  if (summary.last_check) {
    document.getElementById('last-check-label').textContent =
      'Letzter Check: ' + summary.last_check.replace('T', ' ').slice(0, 19);
  }

  const arb = summary.arbitrage || [];
  const pos = arb.filter(r => r.spread > 0).length;
  const neg = arb.filter(r => r.spread <= 0).length;
  const best = arb.length ? arb[0].spread : null;

  document.getElementById('stat-best-spread').textContent = best != null ? fmt(best) : '—';
  document.getElementById('stat-pos').textContent = pos;
  document.getElementById('stat-neg').textContent = neg;

  const tbody = document.getElementById('arb-body');
  tbody.innerHTML = '';
  if (!arb.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:24px">Noch keine Daten — erst check ausführen.</td></tr>';
    return;
  }
  for (const r of arb) {
    const cls = r.spread >= 0 ? 'spread-pos' : 'spread-neg';
    const sign = r.spread >= 0 ? '+' : '';
    tbody.innerHTML += `<tr>
      <td>${r.name}</td>
      <td style="color:var(--muted)">${r.set_name}</td>
      <td>${fmt(r.mkm_low)}</td>
      <td>${fmt(r.ebay_low)}</td>
      <td class="${cls}">${sign}${fmt(r.spread)}</td>
    </tr>`;
  }
}

// ── Karten-Detail ─────────────────────────────────────────────────────────────
async function showCard(card) {
  setActivePage('card');
  activeCardId = card.id;
  document.getElementById('detail-name').textContent = card.name;
  document.getElementById('detail-meta').textContent =
    `${card.set_name} · #${card.number}` +
    (card.cardmarket_product_id ? ` · MKM-ID ${card.cardmarket_product_id}` : '');

  const [quotes, history] = await Promise.all([
    get(`/api/latest?card_id=${card.id}`),
    get(`/api/history?card_id=${card.id}&limit=120`),
  ]);

  renderPriceGrid(quotes);
  renderProviderChips(quotes, history, card.id);
}

function renderPriceGrid(quotes) {
  const grid = document.getElementById('price-grid');
  if (!quotes.length) {
    grid.innerHTML = '<div class="empty"><div class="icon">📭</div><div>Keine Preisdaten — erst check ausführen.</div></div>';
    return;
  }
  grid.innerHTML = quotes.map(q => `
    <div class="price-card">
      <div class="provider">${q.provider}</div>
      ${q.grade ? `<span class="grade-badge">${q.grade}</span>` : ''}
      <div class="price-row"><span class="price-label">Low</span><span class="price-val">${fmt(q.low)}</span></div>
      ${q.trend != null ? `<div class="price-row"><span class="price-label">Trend</span><span class="price-val">${fmt(q.trend)}</span></div>` : ''}
      <div class="price-row"><span class="price-label">Avg</span><span class="price-val">${fmt(q.avg)}</span></div>
      <div class="listings">${q.listings_count} Angebote · ${q.captured_at.slice(0,19).replace('T',' ')}</div>
    </div>`).join('');
}

function renderProviderChips(quotes, history, cardId) {
  const providers = [...new Set(history.map(h => h.provider))];
  activeProviders = new Set(providers);

  const chips = document.getElementById('provider-chips');
  chips.innerHTML = providers.map((p, i) => `
    <span class="chip active" data-provider="${p}" onclick="toggleProvider(this, ${cardId})"
      style="--chip-color:${PROVIDER_COLORS[i % PROVIDER_COLORS.length]};
             border-color:${PROVIDER_COLORS[i % PROVIDER_COLORS.length]};
             color:${PROVIDER_COLORS[i % PROVIDER_COLORS.length]};
             background:${PROVIDER_COLORS[i % PROVIDER_COLORS.length]}22">
      ${p}
    </span>`).join('');

  drawHistoryChart(history, providers);
}

async function toggleProvider(el, cardId) {
  const p = el.dataset.provider;
  if (activeProviders.has(p)) {
    activeProviders.delete(p);
    el.classList.remove('active');
    el.style.background = 'transparent';
  } else {
    activeProviders.add(p);
    el.classList.add('active');
    el.style.background = el.style.getPropertyValue('--chip-color') + '22';
  }
  const history = await get(`/api/history?card_id=${cardId}&limit=120`);
  const providers = [...new Set(history.map(h => h.provider))];
  drawHistoryChart(history, providers);
}

function drawHistoryChart(history, providers) {
  if (histChart) histChart.destroy();

  // Alle Zeitstempel als Labels
  const allTs = [...new Set(history.map(h => h.captured_at.slice(0,19).replace('T',' ')))].sort();

  const datasets = [];
  providers.filter(p => activeProviders.has(p)).forEach((p, i) => {
    const color = PROVIDER_COLORS[i % PROVIDER_COLORS.length];
    const pData = history.filter(h => h.provider === p);
    // avg pro Zeitstempel (falls mehrere Einträge)
    const tsMap = {};
    for (const h of pData) {
      const ts = h.captured_at.slice(0,19).replace('T',' ');
      tsMap[ts] = h.avg ?? h.low;
    }
    datasets.push({
      label: p,
      data: allTs.map(ts => tsMap[ts] ?? null),
      borderColor: color,
      backgroundColor: color + '22',
      tension: 0.3,
      spanGaps: true,
      pointRadius: allTs.length > 30 ? 2 : 4,
    });
  });

  const ctx = document.getElementById('history-chart').getContext('2d');
  histChart = new Chart(ctx, {
    type: 'line',
    data: { labels: allTs, datasets },
    options: {
      responsive: true,
      animation: { duration: 300 },
      plugins: {
        legend: { labels: { color: '#e2e8f0', boxWidth: 12 } },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(2)} €`,
          }
        }
      },
      scales: {
        x: {
          ticks: { color: '#718096', maxTicksLimit: 8 },
          grid: { color: '#2e3250' }
        },
        y: {
          ticks: { color: '#718096', callback: v => v.toFixed(2) + ' €' },
          grid: { color: '#2e3250' }
        }
      }
    }
  });
}

// ── Navigation ────────────────────────────────────────────────────────────────
function setActivePage(page) {
  document.querySelectorAll('.card-item').forEach(el => el.classList.remove('active'));
  document.getElementById('page-overview').classList.remove('visible');
  document.getElementById('page-card').classList.remove('visible');

  if (page === 'overview') {
    document.getElementById('page-overview').classList.add('visible');
    document.getElementById('nav-overview').classList.add('active');
  } else {
    document.getElementById('page-card').classList.add('visible');
    if (activeCardId) {
      const nav = document.getElementById(`nav-card-${activeCardId}`);
      if (nav) nav.classList.add('active');
    }
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
(async () => {
  await loadSidebar();
  await showOverview();
})();
</script>
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────────────
# Einstiegspunkt
# ──────────────────────────────────────────────────────────────────────────────

def main():
    import os
    parser = argparse.ArgumentParser(description="pokeprice Web-Dashboard")
    # Render setzt PORT automatisch; lokal Standard 8080
    default_port = int(os.environ.get("PORT", 8080))
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument("--no-browser", action="store_true",
                        help="Browser nicht automatisch öffnen")
    args = parser.parse_args()

    # Auf Render: 0.0.0.0 binden damit der Reverse-Proxy erreichbar ist.
    # Lokal: 127.0.0.1 reicht.
    host = "0.0.0.0" if os.environ.get("RENDER") else "127.0.0.1"
    server = http.server.HTTPServer((host, args.port), Handler)
    url = f"http://{host}:{args.port}"
    print(f"pokeprice Dashboard läuft auf {url}")
    if not args.no_browser and host == "127.0.0.1":
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer gestoppt.")


if __name__ == "__main__":
    main()
