import json
import io
import csv
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, quote

# Importer la DB depuis l’interface existante
from irc_db_gui import ReleasesDB, DB_PATH


def _json_response(handler: BaseHTTPRequestHandler, obj, status=200):
    data = json.dumps(obj).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _html_response(handler: BaseHTTPRequestHandler, html: str, status=200):
    data = html.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class AppContext:
    def __init__(self, db_path: str, irc_logger=None):
        self.db = ReleasesDB(db_path)
        self.irc = irc_logger


class RequestHandler(BaseHTTPRequestHandler):
    # Contexte partagé (injecté par serveur)
    context: AppContext = None

    def log_message(self, format, *args):
        # Rendre le serveur plus silencieux
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self._serve_index()
        if parsed.path == "/api/releases":
            return self._api_releases(parsed)
        if parsed.path == "/api/count":
            return self._api_count(parsed)
        if parsed.path == "/api/filters":
            return self._api_filters(parsed)
        if parsed.path == "/api/export.csv":
            return self._api_export_csv(parsed)
        if parsed.path == "/api/irc/status":
            return self._api_irc_status()
        if parsed.path == "/api/irc/connect":
            return self._api_irc_connect()
        if parsed.path == "/api/irc/disconnect":
            return self._api_irc_disconnect()
        if parsed.path == "/api/irc/logs":
            return self._api_irc_logs(parsed)

        _html_response(self, "<h1>404 Not Found</h1>", status=404)

    def _serve_index(self):
        html = """
<!doctype html>
<html lang=\"fr\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>IRC Releases - Web UI</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 16px; }
    header { display:flex; justify-content: space-between; align-items:center; }
    .filters { display: grid; grid-template-columns: repeat(9, minmax(120px, 1fr)); gap: 8px; margin: 12px 0; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; font-size: 14px; }
    th { background: #f5f5f5; cursor: pointer; }
    .status { margin-top: 8px; color: #555; }
    .controls { display:flex; gap:8px; align-items:center; }
    input, select, button { padding:6px; font-size: 14px; }
    /* Modal styles */
    .modal { position: fixed; inset: 0; background: rgba(0,0,0,0.45); display: none; align-items: center; justify-content: center; padding: 24px; z-index: 1000; }
    .modal.show { display: flex; }
    .modal-content { background: var(--card); color: var(--text); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 10px 30px rgba(0,0,0,0.25); width: min(900px, 90vw); max-height: 80vh; display: flex; flex-direction: column; }
    .modal-header { display:flex; justify-content: space-between; align-items:center; padding: 12px 16px; border-bottom:1px solid var(--border); }
    .modal-body { padding: 12px 16px; overflow:auto; }
    .close-btn { background: none; border: none; font-size: 20px; cursor: pointer; color: var(--text); opacity: 0.8; }
    .close-btn:hover { opacity: 1; }
    pre#ircLogs { background: var(--table-row); color: var(--text); border:1px solid var(--border); padding:8px; max-height:60vh; overflow:auto; white-space: pre-wrap; word-break: break-word; }
  </style>
  <style>
    :root {
      --bg: #121a2f; /* légèrement plus clair */
      --card: #1a233b; /* éclairci */
      --text: #e5e7eb;
      --muted: #b0b8c6; /* un peu plus clair */
      --accent: #2563eb;
      --accent-hover: #1d4ed8;
      --border: #25354f; /* éclairci */
      --table-header: #16233a; /* éclairci */
      --table-row: #182540; /* éclairci */
      --input-bg: #16233a; /* éclairci */
      --input-text: var(--text);
    }
    .theme-light {
      --bg: #f9fafb;
      --card: #ffffff;
      --text: #111827;
      --muted: #6b7280;
      --accent: #2563eb;
      --accent-hover: #1d4ed8;
      --border: #e9edf3; /* plus léger */
      --table-header: #fafafa; /* plus léger */
      --table-row: #ffffff;
      --input-bg: #ffffff;
      --input-text: #111827;
    }
    html, body { height: 100%; }
    body { margin: 0; background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.5; }
    .container { width: 100%; max-width: none; margin: 0; padding: 16px; }
    header { display:flex; flex-direction: column; align-items: flex-start; gap: 8px; margin-bottom: 12px; }
    h1 { font-size: 20px; margin: 0; font-weight: 600; }
    .controls { gap:8px; }
    .btn { background: var(--accent); color: #fff; border: none; border-radius: 8px; padding: 8px 12px; font-size: 14px; cursor: pointer; box-shadow: 0 1px 0 rgba(0,0,0,0.2); }
    .btn:hover { background: var(--accent-hover); }
    .btn.secondary { background: transparent; color: var(--text); border: 1px solid var(--border); }
    .filters { background: var(--card); border: 1px solid var(--border); border-radius: 12px; }
    input, select { background: var(--input-bg); color: var(--input-text); border: 1px solid var(--border); border-radius: 8px; }
    /* Harmoniser la taille partout */
    input, select, button { font-size: 14px; }
    th, td { font-size: 14px; }
    input::placeholder { color: var(--muted); }
    input[type="date"] { color-scheme: dark; background: var(--input-bg); color: var(--input-text); }
    .theme-light input[type="date"] { color-scheme: light; }
    table { background: var(--card); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
    thead th { position: sticky; top: 0; background: var(--table-header); color: var(--muted); }
    th, td { border-bottom: 1px solid var(--border); }
    tbody tr:nth-child(odd) { background: var(--table-row); }
    tbody tr:hover { background: #0b172a; }
    .sort-indicator { display: inline-block; width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; margin-left: 6px; }
    .sort-asc { border-bottom: 6px solid var(--muted); }
    .sort-desc { border-top: 6px solid var(--muted); }
    /* Toasts */
    .toasts { position: fixed; right: 16px; bottom: 16px; display: flex; flex-direction: column; gap: 8px; z-index: 1100; }
    .toast { background: var(--card); color: var(--text); border: 1px solid var(--border); box-shadow: 0 6px 20px rgba(0,0,0,0.35); border-radius: 12px; padding: 10px 12px; font-size: 13px; min-width: 220px; }
    .toast.success { border-color: #065f46; }
    .toast.error { border-color: #7f1d1d; }
    /* Responsive layout */
    .controls { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-start; gap: 8px; width: 100%; }
    .filters { grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
    .filters input, .filters select, .filters button { width: 100%; box-sizing: border-box; }
    .table-wrapper { overflow-x: auto; border-radius: 12px; }
    table { min-width: 720px; width: 100%; }
    td:nth-child(6), .col-message { word-break: break-word; }
    @media (max-width: 900px) {
      h1 { font-size: 18px; }
      th, td { padding: 6px 8px; font-size: 12px; }
      .btn { padding: 6px 10px; font-size: 12px; }
    }
  </style>
</head>
<body>
    <div class=\"container\">
    <header>
      <h1>IRC Releases - Web UI</h1>
      <div class=\"controls\">
        <button id=\"btnRefresh\" class=\"btn secondary\">Actualiser</button>
        <button id=\"btnExport\" class=\"btn secondary\">Exporter CSV</button>
        <button id=\"btnIrcConnect\" class=\"btn\">Connecter IRC</button>
        <button id=\"btnIrcDisconnect\" class=\"btn\">Déconnecter IRC</button>
        <button id=\"btnOpenLogs\" class=\"btn secondary\">Logs IRC</button>
        <button id=\"btnTheme\" class=\"btn secondary\" title=\"Basculer le thème\">Mode sombre</button>
        <span id=\"ircStatus\" title=\"État IRC\">IRC: (inconnu)</span>
        <span id=\"count\"></span>
      </div>
    </header>

  <section class=\"filters\">
    <input id=\"q\" placeholder=\"Texte\" />
    <select id=\"server\"><option value=\"\">(Tous serveurs)</option></select>
    <select id=\"channel\"><option value=\"\">(Tous channels)</option></select>
    <select id=\"nick\"><option value=\"\">(Tous nicks)</option></select>
    <select id=\"type\"><option value=\"\">(Tous types)</option></select>
    <input id=\"date_from\" type=\"date\" placeholder=\"Du\" />
    <input id=\"date_to\" type=\"date\" placeholder=\"Au\" />
    <select id=\"limit\">
      <option>100</option>
      <option>200</option>
      <option>500</option>
      <option selected>1000</option>
    </select>
    <button id=\"btnReset\">Réinitialiser</button>
  </section>

  <div class=\"table-wrapper\">
  <table id=\"tbl\">
    <thead>
      <tr>
        <th data-col=\"ts_iso\">Date</th>
        <th data-col=\"server\">Serveur</th>
        <th data-col=\"channel\">Channel</th>
        <th data-col=\"nick\">Nick</th>
        <th data-col=\"type\">Type</th>
        <th data-col=\"message\">Message</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>
  </div>

  <div class=\"status\" id=\"status\">Prêt</div>
  <div class=\"toasts\" id=\"toasts\"></div>

  <!-- Modal des logs IRC -->
  <div id=\"logsModal\" class=\"modal\" aria-hidden=\"true\" role=\"dialog\" aria-label=\"Logs IRC\">\n    <div class=\"modal-content\">\n      <div class=\"modal-header\">\n        <h3 style=\"margin:0;\">Logs IRC</h3>\n        <button id=\"btnCloseLogs\" class=\"close-btn\" aria-label=\"Fermer\">&times;</button>\n      </div>\n      <div class=\"modal-body\">\n        <div style=\"display:flex;align-items:center;gap:8px;margin-bottom:8px;\">\n          <label for=\"logsTail\">Lignes:</label>\n          <input id=\"logsTail\" type=\"number\" min=\"50\" max=\"5000\" value=\"200\" />\n          <button id=\"btnShowLogs\">Afficher</button>\n        </div>\n        <pre id=\"ircLogs\"></pre>\n      </div>\n    </div>\n  </div>

  <script>
    const tbl = document.getElementById('tbl');
    const tbody = tbl.querySelector('tbody');
    const limitSel = document.getElementById('limit');
    const status = document.getElementById('status');
    const countEl = document.getElementById('count');
    const dateFrom = document.getElementById('date_from');
    const dateTo = document.getElementById('date_to');
    const serverSel = document.getElementById('server');
    const channelSel = document.getElementById('channel');
    const nickSel = document.getElementById('nick');
    const typeSel = document.getElementById('type');
    const qInput = document.getElementById('q');
    const btnIrcConnect = document.getElementById('btnIrcConnect');
    const btnIrcDisconnect = document.getElementById('btnIrcDisconnect');
    const ircStatus = document.getElementById('ircStatus');
    const btnShowLogs = document.getElementById('btnShowLogs');
    const logsTail = document.getElementById('logsTail');
    const ircLogs = document.getElementById('ircLogs');
    const btnOpenLogs = document.getElementById('btnOpenLogs');
    const logsModal = document.getElementById('logsModal');
    const btnCloseLogs = document.getElementById('btnCloseLogs');
    const toasts = document.getElementById('toasts');
    const btnTheme = document.getElementById('btnTheme');

    let sort = [['ts', 'DESC']]; // col DB, direction

    function getFilters() {
      return {
        q: qInput.value.trim(),
        server: serverSel.value.trim(),
        channel: channelSel.value.trim(),
        nick: nickSel.value.trim(),
        type: typeSel.value.trim(),
        limit: parseInt(limitSel.value, 10) || 1000,
        date_from: dateFrom.value || '',
        date_to: dateTo.value || '',
      };
    }

    async function loadFilters() {
      status.textContent = 'Chargement filtres...';
      try {
        const res = await fetch('/api/filters');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        const fill = (sel, values) => {
          const current = sel.value;
          while (sel.options.length > 1) sel.remove(1);
          (values || []).forEach(v => {
            const opt = document.createElement('option');
            opt.value = v || '';
            opt.textContent = v || '';
            sel.appendChild(opt);
          });
          const has = Array.from(sel.options).some(o => o.value === current);
          sel.value = has ? current : '';
        };
        fill(serverSel, data.server);
        fill(channelSel, data.channel);
        fill(nickSel, data.nick);
        fill(typeSel, data.type);
        status.textContent = 'Filtres chargés';
      } catch (e) {
        console.error('Erreur filtres:', e);
        status.textContent = 'Erreur chargement filtres: ' + e.message;
      }
    }

    async function load(page=1) {
      const f = getFilters();
      const sortParam = sort.map(([c,d]) => `${c}:${d}`).join(',');
      const params = new URLSearchParams({
        page: String(page),
        limit: String(f.limit),
        server: f.server,
        channel: f.channel,
        nick: f.nick,
        type: f.type,
        query: f.q,
        date_from: f.date_from,
        date_to: f.date_to,
        sort: sortParam,
      });
      status.textContent = 'Chargement...';
      try {
        const [listRes, countRes] = await Promise.all([
          fetch('/api/releases?' + params.toString()),
          fetch('/api/count?' + params.toString())
        ]);
        if (!listRes.ok || !countRes.ok) {
          throw new Error(`API HTTP ${listRes.status}/${countRes.status}`);
        }
        const list = await listRes.json();
        const cnt = await countRes.json();
        countEl.textContent = `Total: ${cnt.count}`;
        status.textContent = `OK (${list.length} lignes)`;
        render(list);
      } catch (e) {
        console.error('Erreur de chargement:', e);
        status.textContent = `Erreur de chargement: ${e.message}`;
        tbody.innerHTML = '';
      }
    }

    async function refreshIrcStatus() {
      try {
        const res = await fetch('/api/irc/status');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        if (data.available === false) {
          ircStatus.textContent = 'IRC: indisponible';
        } else if (data.connected === true) {
          ircStatus.textContent = 'IRC: connecté';
        } else {
          ircStatus.textContent = 'IRC: non connecté';
        }
      } catch (e) {
        console.error('Statut IRC erreur:', e);
        ircStatus.textContent = 'IRC: erreur';
      }
    }

    function render(rows) {
      tbody.innerHTML = '';
      for (const r of rows) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${escapeHtml(r.ts_iso || '')}</td>
          <td>${escapeHtml(r.server || '')}</td>
          <td>${escapeHtml(r.channel || '')}</td>
          <td>${escapeHtml(r.nick || '')}</td>
          <td>${escapeHtml(r.type || '')}</td>
          <td>${escapeHtml(r.message || '')}</td>
        `;
        tbody.appendChild(tr);
      }
    }

    function escapeHtml(s) {
      return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
    }

    document.getElementById('btnRefresh').addEventListener('click', () => load(1));
    [serverSel, channelSel, nickSel, typeSel, limitSel, dateFrom, dateTo].forEach(el => {
      el.addEventListener('change', () => load(1));
    });
    const debounce = (fn, ms) => { let t; return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); }; };
    qInput.addEventListener('input', debounce(() => load(1), 400));
    document.getElementById('btnReset').addEventListener('click', () => {
      qInput.value = '';
      serverSel.value = '';
      channelSel.value = '';
      nickSel.value = '';
      typeSel.value = '';
      limitSel.value = '1000';
      dateFrom.value = '';
      dateTo.value = '';
      load(1);
    });
    document.getElementById('btnExport').addEventListener('click', () => {
      const f = getFilters();
      const sortParam = sort.map(([c,d]) => `${c}:${d}`).join(',');
      const params = new URLSearchParams({
        server: f.server,
        channel: f.channel,
        nick: f.nick,
        type: f.type,
        query: f.q,
        date_from: f.date_from,
        date_to: f.date_to,
        sort: sortParam,
      });
      window.open('/api/export.csv?' + params.toString(), '_blank');
    });
    function showToast(text, kind='success', timeout=3000) {
      const div = document.createElement('div');
      div.className = `toast ${kind}`;
      div.textContent = text;
      toasts.appendChild(div);
      setTimeout(() => {
        div.style.opacity = '0';
        div.style.transition = 'opacity 300ms';
        setTimeout(() => div.remove(), 350);
      }, timeout);
    }
    btnIrcConnect.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/irc/connect');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        if (data.started) {
          ircStatus.textContent = 'IRC: connexion en cours...';
          showToast('Connexion IRC démarrée', 'success');
        }
      } catch (e) {
        console.error('Connexion IRC erreur:', e);
        showToast('Erreur connexion IRC', 'error');
      } finally {
        setTimeout(refreshIrcStatus, 1000);
      }
    });
    btnIrcDisconnect.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/irc/disconnect');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        if (data.stopped) {
          ircStatus.textContent = 'IRC: déconnecté';
          showToast('Déconnexion IRC effectuée', 'success');
        }
      } catch (e) {
        console.error('Déconnexion IRC erreur:', e);
        showToast('Erreur déconnexion IRC', 'error');
      } finally {
        setTimeout(refreshIrcStatus, 500);
      }
    });

    async function loadLogs() {
      try {
        const tail = parseInt(logsTail.value, 10) || 200;
        const res = await fetch('/api/irc/logs?tail=' + encodeURIComponent(tail));
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        ircLogs.textContent = data.text || '';
      } catch (e) {
        console.error('Lecture logs IRC erreur:', e);
        ircLogs.textContent = 'Erreur: ' + e.message;
      }
    }
    btnShowLogs.addEventListener('click', loadLogs);
    btnOpenLogs.addEventListener('click', () => {
      logsModal.classList.add('show');
      logsModal.setAttribute('aria-hidden', 'false');
      loadLogs();
    });
    btnCloseLogs.addEventListener('click', () => {
      logsModal.classList.remove('show');
      logsModal.setAttribute('aria-hidden', 'true');
    });
    logsModal.addEventListener('click', (ev) => {
      if (ev.target === logsModal) {
        logsModal.classList.remove('show');
        logsModal.setAttribute('aria-hidden', 'true');
      }
    });
    document.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape') {
        logsModal.classList.remove('show');
        logsModal.setAttribute('aria-hidden', 'true');
      }
    });
    function updateSortIndicators() {
      tbl.querySelectorAll('th').forEach(th => {
        const col = th.dataset.col;
        const dbCol = (col === 'ts_iso') ? 'ts' : col;
        const idx = sort.findIndex(([c]) => c === dbCol);
        th.querySelectorAll('.sort-indicator').forEach(el => el.remove());
        const span = document.createElement('span');
        span.className = 'sort-indicator ' + (idx >= 0 && sort[idx][1] === 'ASC' ? 'sort-asc' : 'sort-desc');
        th.appendChild(span);
      });
    }
    tbl.querySelectorAll('th').forEach(th => {
      th.addEventListener('click', (ev) => {
        const col = th.dataset.col;
        // map UI cols to DB cols where needed
        const dbCol = (col === 'ts_iso') ? 'ts' : col; // tri date par ts
        const existing = sort.findIndex(([c]) => c === dbCol);
        if (existing >= 0) {
          // toggle ASC/DESC
          sort[existing][1] = sort[existing][1] === 'ASC' ? 'DESC' : 'ASC';
        } else {
          // ajoute en tête
          sort.unshift([dbCol, 'DESC']);
        }
        load(1);
        updateSortIndicators();
      });
    });

    // Thème: initialisation et bascule
    (function initTheme(){
      const saved = localStorage.getItem('theme');
      if (saved === 'light') {
        document.documentElement.classList.add('theme-light');
        btnTheme.textContent = 'Mode sombre';
      } else {
        document.documentElement.classList.remove('theme-light');
        btnTheme.textContent = 'Mode clair';
      }
    })();

    btnTheme.addEventListener('click', () => {
      const root = document.documentElement;
      const isLight = root.classList.toggle('theme-light');
      localStorage.setItem('theme', isLight ? 'light' : 'dark');
      btnTheme.textContent = isLight ? 'Mode sombre' : 'Mode clair';
    });

    (async function init(){
      await loadFilters();
      load(1);
      updateSortIndicators();
      refreshIrcStatus();
      setInterval(refreshIrcStatus, 5000);
    })();
  </script>
</div>
</body>
</html>
"""
        _html_response(self, html)

    def _api_releases(self, parsed):
        q = parse_qs(parsed.query)
        limit = int(q.get("limit", [1000])[0])
        page = int(q.get("page", [1])[0])
        offset = max(0, (page - 1) * limit)

        filters = {
            "server": q.get("server", [""])[0],
            "channel": q.get("channel", [""])[0],
            "nick": q.get("nick", [""])[0],
            "type": q.get("type", [""])[0],
            "query": q.get("query", [""])[0],
            # dates non gérées dans l’UI initiale, mais supportées côté DB si fournies
            "date_from": q.get("date_from", [""])[0],
            "date_to": q.get("date_to", [""])[0],
        }

        sort_param = q.get("sort", [""])[0]
        sort_state = []
        if sort_param:
            for part in sort_param.split(","):
                if ":" in part:
                    col, direction = part.split(":", 1)
                    col = col.strip()
                    direction = direction.strip().upper()
                    if direction not in ("ASC", "DESC"):
                        direction = "DESC"
                    # sécurité colonnes tri
                    if col in ("id", "ts", "ts_iso", "server", "channel", "nick", "message", "type"):
                        # préférer tri par ts si ts_iso demandé
                        sort_state.append((("ts" if col == "ts_iso" else col), direction))

        rows = self.context.db.search(filters, limit=limit, offset=offset, order_by=sort_state)
        out = []
        for r in rows:
            out.append({
                "id": r["id"],
                "ts_iso": r["ts_iso"],
                "server": r["server"],
                "channel": r["channel"],
                "nick": r["nick"],
                "message": r["message"],
                "type": r["type"],
            })
        _json_response(self, out)

    def _api_count(self, parsed):
        q = parse_qs(parsed.query)
        filters = {
            "server": q.get("server", [""])[0],
            "channel": q.get("channel", [""])[0],
            "nick": q.get("nick", [""])[0],
            "type": q.get("type", [""])[0],
            "query": q.get("query", [""])[0],
            "date_from": q.get("date_from", [""])[0],
            "date_to": q.get("date_to", [""])[0],
        }
        cnt = self.context.db.count(filters)
        _json_response(self, {"count": cnt})

    def _api_filters(self, parsed):
        out = {
            "server": self.context.db.distinct_values("server"),
            "channel": self.context.db.distinct_values("channel"),
            "nick": self.context.db.distinct_values("nick"),
            "type": self.context.db.distinct_values("type"),
        }
        _json_response(self, out)

    def _api_export_csv(self, parsed):
        # Construit un CSV avec les mêmes filtres et tri que /api/releases,
        # mais sans pagination (export complet)
        q = parse_qs(parsed.query)
        filters = {
            "server": q.get("server", [""])[0],
            "channel": q.get("channel", [""])[0],
            "nick": q.get("nick", [""])[0],
            "type": q.get("type", [""])[0],
            "query": q.get("query", [""])[0],
            "date_from": q.get("date_from", [""])[0],
            "date_to": q.get("date_to", [""])[0],
        }

        sort_param = q.get("sort", [""])[0]
        sort_state = []
        if sort_param:
            for part in sort_param.split(","):
                if ":" in part:
                    col, direction = part.split(":", 1)
                    col = col.strip()
                    direction = direction.strip().upper()
                    if direction not in ("ASC", "DESC"):
                        direction = "DESC"
                    if col in ("id", "ts", "ts_iso", "server", "channel", "nick", "message", "type"):
                        sort_state.append((("ts" if col == "ts_iso" else col), direction))

        rows = self.context.db.search_all(filters, order_by=sort_state)

        # Générer CSV en mémoire
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "ts_iso", "server", "channel", "nick", "type", "message"])
        for r in rows:
            writer.writerow([
                r["id"],
                r["ts_iso"],
                r["server"],
                r["channel"],
                r["nick"],
                r["type"],
                r["message"],
            ])

        data = buf.getvalue().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        # un nom générique; on pourrait ajouter date/filtre dans le nom
        self.send_header("Content-Disposition", "attachment; filename=irc_releases.csv")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _api_irc_status(self):
        ctx = self.context
        if not hasattr(ctx, "irc") or ctx.irc is None:
            return _json_response(self, {"available": False, "connected": False})
        try:
            connected = bool(getattr(ctx.irc, "connected", False))
        except Exception:
            connected = False
        return _json_response(self, {"available": True, "connected": connected})

    def _api_irc_connect(self):
        ctx = self.context
        if not hasattr(ctx, "irc") or ctx.irc is None:
            return _json_response(self, {"ok": False, "error": "IRC indisponible"}, status=400)
        try:
            if getattr(ctx.irc, "connected", False):
                return _json_response(self, {"ok": True, "started": False, "connected": True})
            start = getattr(ctx.irc, "start_connection", None)
            if callable(start):
                start()
                return _json_response(self, {"ok": True, "started": True})
            else:
                return _json_response(self, {"ok": False, "error": "Méthode start_connection absente"}, status=500)
        except Exception as e:
            return _json_response(self, {"ok": False, "error": str(e)}, status=500)

    def _api_irc_disconnect(self):
        ctx = self.context
        if not hasattr(ctx, "irc") or ctx.irc is None:
            return _json_response(self, {"ok": False, "error": "IRC indisponible"}, status=400)
        try:
            stop = getattr(ctx.irc, "stop_connection", None)
            if callable(stop):
                stop()
                return _json_response(self, {"ok": True, "stopped": True})
            else:
                return _json_response(self, {"ok": False, "error": "Méthode stop_connection absente"}, status=500)
        except Exception as e:
            return _json_response(self, {"ok": False, "error": str(e)}, status=500)

    def _api_irc_logs(self, parsed):
        # Retourne la fin du fichier de logs irc_log.txt
        q = parse_qs(parsed.query)
        tail = int(q.get("tail", [200])[0])
        tail = max(50, min(tail, 5000))
        # Le chemin est relatif au script irclog+.py
        base_dir = os.path.dirname(os.path.abspath(__file__))
        log_path = os.path.join(base_dir, "irc_log.txt")
        if not os.path.exists(log_path):
            return _json_response(self, {"ok": True, "text": "(Aucun log)"})
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            text = "".join(lines[-tail:])
            return _json_response(self, {"ok": True, "text": text})
        except Exception as e:
            return _json_response(self, {"ok": False, "error": str(e)}, status=500)


def start_web_server(host: str = "0.0.0.0", port: int = 8000, irc_logger=None):
    context = AppContext(DB_PATH, irc_logger=irc_logger)

    class ContextualHandler(RequestHandler):
        pass

    # Injecter le contexte partagé
    ContextualHandler.context = context

    httpd = HTTPServer((host, port), ContextualHandler)
    print(f"Web UI prêt: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def start_web_server_in_thread(host: str = "0.0.0.0", port: int = 8000, irc_logger=None) -> threading.Thread:
    t = threading.Thread(target=start_web_server, args=(host, port, irc_logger), daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    # Permet lancer seul: python web_server.py
    host = os.environ.get("WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("WEB_PORT", "8000"))
    start_web_server(host=host, port=port)