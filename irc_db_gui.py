import os
import sqlite3
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import json
import urllib.parse
try:
    from tkcalendar import Calendar
    TKCALENDAR_AVAILABLE = True
except Exception:
    TKCALENDAR_AVAILABLE = False


# Emplacement de la base SQLite (à côté de ce script)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "irc_logs.db")


class ReleasesDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        # check_same_thread=False pour permettre la mise à jour depuis callbacks
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.ensure_schema()

    def ensure_schema(self):
        # Crée la table si elle n'existe pas (selon le schéma observé)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS releases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                ts_iso TEXT NOT NULL,
                server TEXT,
                channel TEXT,
                nick TEXT,
                message TEXT,
                type TEXT
            )
            """
        )
        # Index utile pour recherche par message
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_message ON releases(message)
            """
        )
        self.conn.commit()

    def distinct_values(self, column: str):
        if column not in ("server", "channel", "nick", "type"):
            return []
        cur = self.conn.execute(f"SELECT DISTINCT {column} FROM releases WHERE {column} IS NOT NULL AND {column} <> '' ORDER BY {column} ASC")
        return [row[0] for row in cur.fetchall()]

    def search(self, filters: dict, limit: int = 500, offset: int = 0, order_by: list | None = None):
        where = []
        params = []

        # Filtres exacts
        for key in ("server", "channel", "nick", "type"):
            val = filters.get(key)
            if val:
                where.append(f"{key} = ?")
                params.append(val)

        # Recherche texte dans message (contient)
        q = filters.get("query")
        if q:
            where.append("message LIKE ?")
            params.append(f"%{q}%")

        # Plage de dates (ISO) – simple, basé sur ts_iso préfixe YYYY-MM-DD
        date_from = filters.get("date_from")
        date_to = filters.get("date_to")
        if date_from:
            where.append("ts_iso >= ?")
            params.append(f"{date_from} 00:00:00")
        if date_to:
            where.append("ts_iso <= ?")
            params.append(f"{date_to} 23:59:59")

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        # ORDER BY multi-colonnes
        valid_cols = {"id", "ts", "ts_iso", "server", "channel", "nick", "message", "type"}
        order_clauses = []
        if order_by:
            for col, direction in order_by:
                col = str(col)
                direction = str(direction).upper()
                if col in valid_cols and direction in ("ASC", "DESC"):
                    order_clauses.append(f"{col} {direction}")
        order_sql = f"ORDER BY {', '.join(order_clauses)}" if order_clauses else "ORDER BY ts DESC"
        sql = f"""
            SELECT id, ts_iso, server, channel, nick, message, type, ts
            FROM releases
            {where_sql}
            {order_sql}
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        cur = self.conn.execute(sql, params)
        return cur.fetchall()

    def search_all(self, filters: dict, order_by: list | None = None):
        where = []
        params = []

        for key in ("server", "channel", "nick", "type"):
            val = filters.get(key)
            if val:
                where.append(f"{key} = ?")
                params.append(val)

        q = filters.get("query")
        if q:
            where.append("message LIKE ?")
            params.append(f"%{q}%")

        date_from = filters.get("date_from")
        date_to = filters.get("date_to")
        if date_from:
            where.append("ts_iso >= ?")
            params.append(f"{date_from} 00:00:00")
        if date_to:
            where.append("ts_iso <= ?")
            params.append(f"{date_to} 23:59:59")

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        valid_cols = {"id", "ts", "ts_iso", "server", "channel", "nick", "message", "type"}
        order_clauses = []
        if order_by:
            for col, direction in order_by:
                col = str(col)
                direction = str(direction).upper()
                if col in valid_cols and direction in ("ASC", "DESC"):
                    order_clauses.append(f"{col} {direction}")
        order_sql = f"ORDER BY {', '.join(order_clauses)}" if order_clauses else "ORDER BY ts DESC"
        sql = f"""
            SELECT id, ts_iso, server, channel, nick, message, type, ts
            FROM releases
            {where_sql}
            {order_sql}
        """
        cur = self.conn.execute(sql, params)
        return cur.fetchall()

    def count(self, filters: dict) -> int:
        where = []
        params = []

        for key in ("server", "channel", "nick", "type"):
            val = filters.get(key)
            if val:
                where.append(f"{key} = ?")
                params.append(val)

        q = filters.get("query")
        if q:
            where.append("message LIKE ?")
            params.append(f"%{q}%")

        date_from = filters.get("date_from")
        date_to = filters.get("date_to")
        if date_from:
            where.append("ts_iso >= ?")
            params.append(f"{date_from} 00:00:00")
        if date_to:
            where.append("ts_iso <= ?")
            params.append(f"{date_to} 23:59:59")

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        sql = f"SELECT COUNT(*) AS cnt FROM releases {where_sql}"
        cur = self.conn.execute(sql, params)
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def add(self, data: dict):
        ts_iso = data.get("ts_iso")
        ts = data.get("ts")
        if not ts_iso and not ts:
            now = datetime.now()
            ts_iso = now.strftime("%Y-%m-%d %H:%M:%S")
            ts = int(now.timestamp())
        elif ts_iso and not ts:
            ts = int(datetime.strptime(ts_iso, "%Y-%m-%d %H:%M:%S").timestamp())
        elif ts and not ts_iso:
            ts_iso = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")

        self.conn.execute(
            """
            INSERT INTO releases (ts, ts_iso, server, channel, nick, message, type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                ts_iso,
                data.get("server", ""),
                data.get("channel", ""),
                data.get("nick", ""),
                data.get("message", ""),
                data.get("type", ""),
            ),
        )
        self.conn.commit()

    def update(self, row_id: int, data: dict):
        # Recalcule ts/ts_iso si l'un des deux est modifié
        ts_iso = data.get("ts_iso")
        ts = data.get("ts")
        if ts_iso and not ts:
            ts = int(datetime.strptime(ts_iso, "%Y-%m-%d %H:%M:%S").timestamp())
        elif ts and not ts_iso:
            ts_iso = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")

        self.conn.execute(
            """
            UPDATE releases
            SET ts = ?, ts_iso = ?, server = ?, channel = ?, nick = ?, message = ?, type = ?
            WHERE id = ?
            """,
            (
                ts,
                ts_iso,
                data.get("server", ""),
                data.get("channel", ""),
                data.get("nick", ""),
                data.get("message", ""),
                data.get("type", ""),
                row_id,
            ),
        )
        self.conn.commit()

    def delete_many(self, ids):
        if not ids:
            return
        qmarks = ",".join(["?"] * len(ids))
        self.conn.execute(f"DELETE FROM releases WHERE id IN ({qmarks})", ids)
        self.conn.commit()


class AddEditDialog(tk.Toplevel):
    def __init__(self, parent, title: str, initial: dict | None = None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result = None
        self.initial = initial or {}

        frm = ttk.Frame(self, padding=12)
        frm.grid(row=0, column=0, sticky="nsew")

        # Champs
        labels = [
            ("Date/Heure (ts_iso)", "ts_iso"),
            ("Serveur", "server"),
            ("Channel", "channel"),
            ("Nick", "nick"),
            ("Message", "message"),
            ("Type", "type"),
        ]

        self.entries = {}
        for i, (lbl, key) in enumerate(labels):
            ttk.Label(frm, text=lbl).grid(row=i, column=0, sticky="w", pady=(0, 6))
            ent = ttk.Entry(frm, width=60)
            ent.grid(row=i, column=1, sticky="ew", pady=(0, 6))
            ent.insert(0, self.initial.get(key, ""))
            self.entries[key] = ent

        # ts_iso par défaut si ajout
        if not self.initial.get("ts_iso"):
            self.entries["ts_iso"].delete(0, tk.END)
            self.entries["ts_iso"].insert(0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        # Boutons
        btns = ttk.Frame(frm)
        btns.grid(row=len(labels), column=0, columnspan=2, sticky="e")
        ttk.Button(btns, text="Annuler", command=self._on_cancel).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(btns, text="Enregistrer", command=self._on_ok).grid(row=0, column=1)

        self.bind("<Escape>", lambda e: self._on_cancel())
        self.bind("<Return>", lambda e: self._on_ok())

    def _on_cancel(self):
        self.result = None
        self.destroy()

    def _on_ok(self):
        data = {k: ent.get().strip() for k, ent in self.entries.items()}
        # Validation minimale
        if data.get("ts_iso"):
            try:
                datetime.strptime(data["ts_iso"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                messagebox.showerror("Erreur", "Format de date invalide. Utiliser YYYY-MM-DD HH:MM:SS")
                return
        self.result = data
        self.destroy()


class ReleasesGUI:
    def __init__(self, root: tk.Tk, container: tk.Widget | None = None):
        self.root = root
        # Conteneur pour intégration; par défaut la racine
        self.container = container if container is not None else root
        # Définir titre/geometry uniquement en mode standalone
        try:
            if self.container is self.root and isinstance(root, (tk.Tk, tk.Toplevel)):
                self.root.title("Gestion des releases IRC")
                self.root.geometry("1100x650")
        except Exception:
            pass

        # Style moderne Windows si disponible
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            style.theme_use("clam")

        self.db = ReleasesDB(DB_PATH)
        # Debounce pour mises à jour des filtres
        self._filter_after_id = None

        # Pagination
        self.page_limit_var = tk.IntVar(value=500)
        self.page_offset = 0
        self.total_count = 0

        # Tri multi-colonnes: liste de tuples (col, direction)
        self.sort_state = [("ts", "DESC")]
        self._shift_down = False
        self.root.bind_all("<KeyPress-Shift_L>", lambda e: self._set_shift(True))
        self.root.bind_all("<KeyRelease-Shift_L>", lambda e: self._set_shift(False))
        self.root.bind_all("<KeyPress-Shift_R>", lambda e: self._set_shift(True))
        self.root.bind_all("<KeyRelease-Shift_R>", lambda e: self._set_shift(False))

        # Filtres
        self.filter_vars = {
            "server": tk.StringVar(),
            "channel": tk.StringVar(),
            "nick": tk.StringVar(),
            "type": tk.StringVar(),
            "query": tk.StringVar(),
            "date_from": tk.StringVar(),
            "date_to": tk.StringVar(),
        }

        # Construction UI
        self._build_filters()
        self._build_actions()
        self._build_table()
        self._build_status()
        self._build_pagination()

        self.refresh_filters_sources()
        self.load_data()

    def _on_filter_change(self, *args):
        # Planifie un rechargement après une courte temporisation
        # Reset sur première page quand les filtres changent
        self.page_offset = 0
        self.schedule_load_data()

    def schedule_load_data(self, delay: int = 300):
        if self._filter_after_id:
            try:
                self.root.after_cancel(self._filter_after_id)
            except Exception:
                pass
            self._filter_after_id = None
        self._filter_after_id = self.root.after(delay, self._do_load_data)

    def _do_load_data(self):
        self._filter_after_id = None
        self.load_data()

    def _build_filters(self):
        frm = ttk.Frame(self.container, padding=(12, 8))
        frm.pack(fill="x")

        # Combos pour valeurs distinctes
        ttk.Label(frm, text="Serveur").grid(row=0, column=0, sticky="w")
        self.cmb_server = ttk.Combobox(frm, textvariable=self.filter_vars["server"], width=24, values=[], state="readonly")
        self.cmb_server.grid(row=0, column=1, padx=(6, 12))

        ttk.Label(frm, text="Channel").grid(row=0, column=2, sticky="w")
        self.cmb_channel = ttk.Combobox(frm, textvariable=self.filter_vars["channel"], width=24, values=[], state="readonly")
        self.cmb_channel.grid(row=0, column=3, padx=(6, 12))

        ttk.Label(frm, text="Nick").grid(row=0, column=4, sticky="w")
        self.cmb_nick = ttk.Combobox(frm, textvariable=self.filter_vars["nick"], width=18, values=[], state="readonly")
        self.cmb_nick.grid(row=0, column=5, padx=(6, 12))

        ttk.Label(frm, text="Type").grid(row=0, column=6, sticky="w")
        self.cmb_type = ttk.Combobox(frm, textvariable=self.filter_vars["type"], width=18, values=[], state="readonly")
        self.cmb_type.grid(row=0, column=7, padx=(6, 12))

        ttk.Label(frm, text="Recherche texte").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frm, textvariable=self.filter_vars["query"], width=40).grid(row=1, column=1, columnspan=3, sticky="ew", padx=(6, 12), pady=(8, 0))

        ttk.Label(frm, text="Du (YYYY-MM-DD)").grid(row=1, column=4, sticky="w", pady=(8, 0))
        frm_from = ttk.Frame(frm)
        frm_from.grid(row=1, column=5, padx=(6, 12), pady=(8, 0), sticky="w")
        ent_from = ttk.Entry(frm_from, textvariable=self.filter_vars["date_from"], width=12)
        ent_from.pack(side="left")
        ttk.Button(frm_from, text="📅", width=3, command=lambda: self.open_calendar_dialog("date_from")).pack(side="left", padx=(6, 0))

        ttk.Label(frm, text="Au (YYYY-MM-DD)").grid(row=1, column=6, sticky="w", pady=(8, 0))
        frm_to = ttk.Frame(frm)
        frm_to.grid(row=1, column=7, padx=(6, 12), pady=(8, 0), sticky="w")
        ent_to = ttk.Entry(frm_to, textvariable=self.filter_vars["date_to"], width=12)
        ent_to.pack(side="left")
        ttk.Button(frm_to, text="📅", width=3, command=lambda: self.open_calendar_dialog("date_to")).pack(side="left", padx=(6, 0))

        for i in range(8):
            frm.columnconfigure(i, weight=1)

        # Mise à jour automatique lors de la modification des filtres
        for key in ("server", "channel", "nick", "type", "query", "date_from", "date_to"):
            try:
                self.filter_vars[key].trace_add("write", self._on_filter_change)
            except Exception:
                pass

        # Assure aussi la mise à jour sur sélection de combobox
        for cmb in (self.cmb_server, self.cmb_channel, self.cmb_nick, self.cmb_type):
            cmb.bind("<<ComboboxSelected>>", lambda e: (self._reset_to_first_page(), self.load_data()))

    def open_calendar_dialog(self, field_key: str):
        # Ouvre une boîte calendrier pour sélectionner la date, écrit AAAA-MM-JJ
        if not TKCALENDAR_AVAILABLE:
            messagebox.showinfo(
                "Calendrier indisponible",
                "Le module tkcalendar n'est pas installé. Saisissez la date au format AAAA-MM-JJ, ou installez-le via: pip install tkcalendar",
            )
            return
        top = tk.Toplevel(self.root)
        top.title("Choisir une date")
        top.transient(self.root)
        top.grab_set()
        frm = ttk.Frame(top, padding=12)
        frm.pack(fill="both", expand=True)
        cal = Calendar(frm, selectmode='day', date_pattern='yyyy-mm-dd')
        cal.pack(pady=(0, 8))
        btns = ttk.Frame(frm)
        btns.pack()

        def on_clear():
            self.filter_vars[field_key].set("")
            top.destroy()

        def on_ok():
            try:
                val = cal.get_date()
                # tkcalendar retourne déjà la chaîne selon date_pattern
                self.filter_vars[field_key].set(val)
            except Exception:
                pass
            top.destroy()

        ttk.Button(btns, text="Effacer", command=on_clear).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="OK", command=on_ok).pack(side="left")

    def _build_actions(self):
        bar = ttk.Frame(self.container, padding=(12, 0))
        bar.pack(fill="x")

        ttk.Button(bar, text="Rechercher", command=self.load_data).pack(side="left")
        ttk.Button(bar, text="Réinitialiser", command=self.reset_filters).pack(side="left", padx=(8, 0))

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=12)

        ttk.Button(bar, text="Ajouter", command=self.on_add).pack(side="left")
        ttk.Button(bar, text="Éditer", command=self.on_edit).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="Supprimer", command=self.on_delete).pack(side="left", padx=(8, 0))

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=12)
        ttk.Button(bar, text="Exporter CSV", command=self.on_export_csv).pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=12)
        ttk.Button(bar, text="Exporter Queue WinSCP", command=self.on_export_winscp_queue).pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=12)
        ttk.Button(bar, text="Exporter URLs CrossFTP", command=self.on_export_crossftp_urls).pack(side="left")

    def _build_table(self):
        frm = ttk.Frame(self.container, padding=(12, 8))
        frm.pack(fill="both", expand=True)

        columns = ("id", "ts_iso", "server", "channel", "nick", "message", "type")
        self.tree = ttk.Treeview(frm, columns=columns, show="headings", selectmode="extended")
        self._header_texts = {
            "id": "ID",
            "ts_iso": "Date",
            "server": "Serveur",
            "channel": "Channel",
            "nick": "Nick",
            "message": "Message",
            "type": "Type",
        }
        self.tree.heading("id", text=self._header_texts["id"], command=lambda: self.on_sort_click("id"))
        self.tree.heading("ts_iso", text=self._header_texts["ts_iso"], command=lambda: self.on_sort_click("ts_iso"))
        self.tree.heading("server", text=self._header_texts["server"], command=lambda: self.on_sort_click("server"))
        self.tree.heading("channel", text=self._header_texts["channel"], command=lambda: self.on_sort_click("channel"))
        self.tree.heading("nick", text=self._header_texts["nick"], command=lambda: self.on_sort_click("nick"))
        self.tree.heading("message", text=self._header_texts["message"], command=lambda: self.on_sort_click("message"))
        self.tree.heading("type", text=self._header_texts["type"], command=lambda: self.on_sort_click("type"))

        self.tree.column("id", width=60, anchor="center")
        self.tree.column("ts_iso", width=150)
        self.tree.column("server", width=180)
        self.tree.column("channel", width=160)
        self.tree.column("nick", width=140)
        self.tree.column("message", width=600)
        self.tree.column("type", width=120)

        vsb = ttk.Scrollbar(frm, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(frm, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", lambda e: self.on_edit())
        self._update_heading_texts()

    def _build_status(self):
        self.status_var = tk.StringVar(value="Prêt")
        bar = ttk.Frame(self.container, padding=(12, 6))
        bar.pack(fill="x")
        ttk.Label(bar, textvariable=self.status_var).pack(side="left")

    def _build_pagination(self):
        bar = ttk.Frame(self.container, padding=(12, 0))
        bar.pack(fill="x")
        ttk.Separator(bar, orient="horizontal").pack(fill="x", pady=4)

        controls = ttk.Frame(bar)
        controls.pack(fill="x")

        self.btn_prev = ttk.Button(controls, text="Précédent", command=self.on_prev_page)
        self.btn_next = ttk.Button(controls, text="Suivant", command=self.on_next_page)
        self.page_info_var = tk.StringVar(value="Page 1")

        ttk.Label(controls, text="Taille de page").pack(side="left")
        try:
            self.spin_page_size = ttk.Spinbox(controls, from_=50, to=2000, increment=50, textvariable=self.page_limit_var, width=6)
        except Exception:
            # Fallback si ttk.Spinbox indisponible
            self.spin_page_size = tk.Spinbox(controls, from_=50, to=2000, increment=50, textvariable=self.page_limit_var, width=6)
        self.spin_page_size.pack(side="left", padx=(6, 12))
        ttk.Separator(controls, orient="vertical").pack(side="left", fill="y", padx=6)
        self.btn_prev.pack(side="left")
        self.btn_next.pack(side="left", padx=(6, 12))
        ttk.Label(controls, textvariable=self.page_info_var).pack(side="left")

        # Quand la taille de page change, revenir à la première page et recharger
        def _on_page_size_change(*args):
            try:
                val = int(self.page_limit_var.get())
                if val <= 0:
                    self.page_limit_var.set(100)
                self._reset_to_first_page()
                self.load_data()
            except Exception:
                pass
        try:
            self.page_limit_var.trace_add("write", _on_page_size_change)
        except Exception:
            pass

    def _reset_to_first_page(self):
        self.page_offset = 0

    def refresh_filters_sources(self):
        servers = [""] + self.db.distinct_values("server")
        channels = [""] + self.db.distinct_values("channel")
        nicks = [""] + self.db.distinct_values("nick")
        types = [""] + self.db.distinct_values("type")

        self.cmb_server.configure(values=servers)
        self.cmb_channel.configure(values=channels)
        self.cmb_nick.configure(values=nicks)
        self.cmb_type.configure(values=types)

    def reset_filters(self):
        for v in self.filter_vars.values():
            v.set("")
        self._reset_to_first_page()
        self.load_data()

    def load_data(self):
        filters = {k: v.get().strip() for k, v in self.filter_vars.items()}
        try:
            # Total filtré
            self.total_count = self.db.count(filters)
            limit = int(self.page_limit_var.get())
            offset = int(self.page_offset)
            # Sécurité bornes
            if offset < 0:
                offset = 0
            if offset >= max(self.total_count - 1, 0):
                # Aligner offset sur dernière page si dépassement
                pages = (self.total_count + max(limit, 1) - 1) // max(limit, 1)
                offset = max((pages - 1) * limit, 0)
                self.page_offset = offset
            rows = self.db.search(filters, limit=limit, offset=offset, order_by=self.sort_state)
        except Exception as e:
            messagebox.showerror("Erreur", f"Recherche impossible: {e}")
            return

        for item in self.tree.get_children():
            self.tree.delete(item)

        for r in rows:
            self.tree.insert("", "end", values=(r["id"], r["ts_iso"], r["server"], r["channel"], r["nick"], r["message"], r["type"]))

        # Mettre à jour infos de pagination et statut
        self.update_pagination_state(len(rows))
        self._update_heading_texts()

    def _set_shift(self, down: bool):
        self._shift_down = bool(down)

    def on_sort_click(self, col_key: str):
        sort_map = {
            "id": "id",
            "ts_iso": "ts",  # utiliser ts pour tri
            "server": "server",
            "channel": "channel",
            "nick": "nick",
            "message": "message",
            "type": "type",
        }
        col = sort_map.get(col_key, col_key)
        existing_index = next((i for i, (c, d) in enumerate(self.sort_state) if c == col), None)
        if self._shift_down:
            if existing_index is None:
                self.sort_state.append((col, "ASC"))
            else:
                c, d = self.sort_state[existing_index]
                self.sort_state[existing_index] = (c, "DESC" if d == "ASC" else "ASC")
        else:
            if existing_index is None:
                self.sort_state = [(col, "ASC")]
            else:
                c, d = self.sort_state[existing_index]
                self.sort_state = [(c, "DESC" if d == "ASC" else "ASC")]
        self._reset_to_first_page()
        self.load_data()

    def _update_heading_texts(self):
        arrows = {"ASC": "▲", "DESC": "▼"}
        texts = dict(self._header_texts)
        rev_map = {
            "id": "id",
            "ts": "ts_iso",
            "server": "server",
            "channel": "channel",
            "nick": "nick",
            "message": "message",
            "type": "type",
        }
        for col, direction in self.sort_state:
            key = rev_map.get(col, col)
            base = texts.get(key, key)
            texts[key] = f"{base} {arrows.get(direction, '')}"
        for key, text in texts.items():
            try:
                self.tree.heading(key, text=text)
            except Exception:
                pass

    def on_export_csv(self):
        filters = {k: v.get().strip() for k, v in self.filter_vars.items()}
        filename = filedialog.asksaveasfilename(
            title="Exporter en CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Tous les fichiers", "*.*")],
            initialfile="irc_releases_export.csv",
        )
        if not filename:
            return
        try:
            rows = self.db.search_all(filters, order_by=self.sort_state)
            headers = ["id", "ts_iso", "server", "channel", "nick", "message", "type"]
            with open(filename, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for r in rows:
                    writer.writerow([r["id"], r["ts_iso"], r["server"], r["channel"], r["nick"], r["message"], r["type"]])
            self.status_var.set(f"Exporté {len(rows)} lignes vers {filename}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Export CSV impossible: {e}")

    def on_export_winscp_queue(self):
        filters = {k: v.get().strip() for k, v in self.filter_vars.items()}
        # Charger config FTP
        cfg_path = os.path.join(BASE_DIR, "ftp_sites.json")
        if not os.path.exists(cfg_path):
            messagebox.showwarning(
                "Config manquante",
                "Aucun fichier ftp_sites.json trouvé. Un exemple va être créé. \n"
                "Renseignez hôte, identifiants, chemins distants et dossier local, puis relancez l’export.")
            try:
                sample = {
                    "default_site": "example",
                    "sites": {
                        "example": {
                            "protocol": "ftp",
                            "host": "ftp.example.com",
                            "user": "username",
                            "pass": "password",
                            "local_base_dir": "C:\\Downloads",
                            "name_transform": "raw",  # raw|underscores|dots
                            "base_paths": {
                                "default": "/incoming",
                                "GAMES": "/incoming/games",
                                "MOVIES": "/incoming/movies"
                            }
                        }
                    }
                }
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(sample, f, indent=2)
            except Exception:
                pass
            return
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            messagebox.showerror("Erreur", f"Lecture config FTP impossible: {e}")
            return

        site_name = cfg.get("default_site")
        sites = cfg.get("sites", {})
        site = sites.get(site_name or "", {})
        if not site:
            messagebox.showerror("Erreur", "Site par défaut introuvable dans ftp_sites.json")
            return

        protocol = site.get("protocol", "ftp")
        host = site.get("host", "")
        user = site.get("user", "")
        password = site.get("pass", "")
        port = site.get("port")
        local_base = site.get("local_base_dir", "C:\\Downloads")
        name_transform = site.get("name_transform", "raw")
        base_paths = site.get("base_paths", {})

        if not host or not user or not password:
            messagebox.showerror("Erreur", "Veuillez renseigner host/user/pass dans ftp_sites.json")
            return

        filename = filedialog.asksaveasfilename(
            title="Exporter script WinSCP",
            defaultextension=".txt",
            filetypes=[("Script WinSCP", "*.txt"), ("Tous les fichiers", "*.*")],
            initialfile="winscp_queue.txt",
        )
        if not filename:
            return

        try:
            rows = self.db.search_all(filters, order_by=self.sort_state)
            # Construire script WinSCP
            lines = []
            lines.append("option batch on")
            lines.append("option confirm off")
            # Mot de passe avec caractères spéciaux: WinSCP supporte URL encodée, ici on suppose simple
            # Construire URL d'ouverture WinSCP avec protocole (ftp/sftp/ftps/ftpes) et port
            open_host = f"{host}:{port}" if port else host
            lines.append(f"open {protocol}://{user}:{password}@{open_host}")
            # Pour chaque release, construire chemin distant et destination locale
            def transform_name(name: str) -> str:
                if name_transform == "underscores":
                    return name.replace(" ", "_")
                if name_transform == "dots":
                    return name.replace(" ", ".")
                return name
            for r in rows:
                rel_type = (r["type"] or "").strip() or "default"
                base_remote = base_paths.get(rel_type, base_paths.get("default", "/"))
                release_name = transform_name((r["message"] or "").strip())
                remote_path = f"{base_remote.rstrip('/')}/{release_name}"
                local_dest = os.path.join(local_base, rel_type)
                # S'assurer du dossier local à la récupération
                lines.append(f"lcd {local_dest}")
                # Télécharger récursivement (si le nom est un répertoire)
                lines.append(f"get -transfer=automatic -resume \"{remote_path}\"")
            lines.append("exit")

            with open(filename, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            self.status_var.set(f"Script WinSCP exporté avec {len(rows)} entrées: {filename}")
            messagebox.showinfo(
                "Export réussi",
                "Script créé. Exécutez: \n\nwinscp.com /script=\"" + filename + "\"\n\n"
                "Ajustez ftp_sites.json pour adapter hôte, chemins et format des noms.")
        except Exception as e:
            messagebox.showerror("Erreur", f"Export WinSCP impossible: {e}")
            
    def on_export_crossftp_urls(self):
        filters = {k: v.get().strip() for k, v in self.filter_vars.items()}
        # Charger config FTP
        cfg_path = os.path.join(BASE_DIR, "ftp_sites.json")
        if not os.path.exists(cfg_path):
            messagebox.showwarning(
                "Config manquante",
                "Aucun fichier ftp_sites.json trouvé. Un exemple va être créé. \n"
                "Renseignez hôte, identifiants, chemins distants et dossier local, puis relancez l’export.")
            try:
                sample = {
                    "default_site": "example",
                    "sites": {
                        "example": {
                            "protocol": "ftp",
                            "host": "ftp.example.com",
                            "user": "username",
                            "pass": "password",
                            "local_base_dir": "C:\\Downloads",
                            "name_transform": "raw",  # raw|underscores|dots
                            "base_paths": {
                                "default": "/incoming",
                                "GAMES": "/incoming/games",
                                "MOVIES": "/incoming/movies"
                            }
                        }
                    }
                }
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(sample, f, indent=2)
            except Exception:
                pass
            return
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            messagebox.showerror("Erreur", f"Lecture config FTP impossible: {e}")
            return

        site_name = cfg.get("default_site")
        sites = cfg.get("sites", {})
        site = sites.get(site_name or "", {})
        if not site:
            messagebox.showerror("Erreur", "Site par défaut introuvable dans ftp_sites.json")
            return

        protocol = site.get("protocol", "ftp")
        host = site.get("host", "")
        user = site.get("user", "")
        password = site.get("pass", "")
        port = site.get("port")
        local_base = site.get("local_base_dir", "C:\\Downloads")
        name_transform = site.get("name_transform", "raw")
        base_paths = site.get("base_paths", {})

        if not host or not user or not password:
            messagebox.showerror("Erreur", "Veuillez renseigner host/user/pass dans ftp_sites.json")
            return

        filename = filedialog.asksaveasfilename(
            title="Exporter URLs pour CrossFTP",
            defaultextension=".txt",
            filetypes=[("Fichier texte", "*.txt"), ("Tous les fichiers", "*.*")],
            initialfile="crossftp_urls.txt",
        )
        if not filename:
            return

        try:
            rows = self.db.search_all(filters, order_by=self.sort_state)
            # Construire liste d'URLs FTP/SFTP
            def transform_name(name: str) -> str:
                if name_transform == "underscores":
                    return name.replace(" ", "_")
                if name_transform == "dots":
                    return name.replace(" ", ".")
                return name

            user_enc = urllib.parse.quote(user, safe="")
            pass_enc = urllib.parse.quote(password, safe="")
            host_part = f"{host}:{port}" if port else host

            lines = []
            for r in rows:
                rel_type = (r["type"] or "").strip() or "default"
                base_remote = base_paths.get(rel_type, base_paths.get("default", "/"))
                release_name = transform_name((r["message"] or "").strip())
                remote_path = f"{base_remote.rstrip('/')}/{release_name}"
                # Encoder le chemin pour URL (préserver les slashs)
                remote_path_enc = urllib.parse.quote(remote_path, safe="/-._~")
                # sftp://user:pass@host/path ou ftp(s)/ftpes://user:pass@host/path
                url = f"{protocol}://{user_enc}:{pass_enc}@{host_part}{remote_path_enc}"
                lines.append(url)

            with open(filename, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            self.status_var.set(f"URLs CrossFTP exportées: {len(rows)} entrées vers {filename}")
            messagebox.showinfo(
                "Export réussi",
                "Liste d’URLs créée. Dans CrossFTP, importez ou collez ces URLs pour les ajouter à la file de téléchargement.\n\n"
                "Astuce: vous pouvez aussi enregistrer une variante CSV si besoin pour associer des dossiers locaux.")
        except Exception as e:
            messagebox.showerror("Erreur", f"Export CrossFTP impossible: {e}")

    def update_pagination_state(self, shown_count: int):
        try:
            limit = int(self.page_limit_var.get())
        except Exception:
            limit = 500
        offset = int(self.page_offset)
        total = int(self.total_count)
        # Calcul des pages
        total_pages = (total + max(limit, 1) - 1) // max(limit, 1) if total > 0 else 1
        current_page = (offset // max(limit, 1)) + 1 if total > 0 else 1

        # Mettre à jour libellés
        self.page_info_var.set(f"Page {current_page}/{total_pages}")
        self.status_var.set(f"{shown_count} éléments affichés sur {total} — limite {limit}")

        # État des boutons
        if hasattr(self, 'btn_prev') and hasattr(self, 'btn_next'):
            # Désactiver/activer via ttk state
            if current_page <= 1:
                self.btn_prev.state(["disabled"])
            else:
                self.btn_prev.state(["!disabled"])
            if current_page >= total_pages:
                self.btn_next.state(["disabled"])
            else:
                self.btn_next.state(["!disabled"])

    def on_prev_page(self):
        try:
            limit = int(self.page_limit_var.get())
        except Exception:
            limit = 500
        self.page_offset = max(self.page_offset - limit, 0)
        self.load_data()

    def on_next_page(self):
        try:
            limit = int(self.page_limit_var.get())
        except Exception:
            limit = 500
        next_offset = self.page_offset + limit
        if next_offset < self.total_count:
            self.page_offset = next_offset
        self.load_data()

    def on_add(self):
        dlg = AddEditDialog(self.root, "Ajouter une release")
        self.root.wait_window(dlg)
        if dlg.result:
            try:
                self.db.add(dlg.result)
                self.status_var.set("Élément ajouté")
                self.refresh_filters_sources()
                self.load_data()
            except Exception as e:
                messagebox.showerror("Erreur", f"Ajout impossible: {e}")

    def _selected_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        vals = self.tree.item(sel[0], "values")
        return int(vals[0])

    def on_edit(self):
        row_id = self._selected_id()
        if not row_id:
            messagebox.showinfo("Info", "Sélectionnez une ligne à éditer.")
            return

        # Charger valeurs actuelles
        cur = self.db.conn.execute(
            "SELECT id, ts_iso, server, channel, nick, message, type FROM releases WHERE id = ?",
            (row_id,),
        )
        row = cur.fetchone()
        if not row:
            messagebox.showerror("Erreur", "Ligne introuvable.")
            return

        initial = {
            "ts_iso": row["ts_iso"],
            "server": row["server"],
            "channel": row["channel"],
            "nick": row["nick"],
            "message": row["message"],
            "type": row["type"],
        }
        dlg = AddEditDialog(self.root, "Éditer la release", initial)
        self.root.wait_window(dlg)
        if dlg.result:
            try:
                self.db.update(row_id, dlg.result)
                self.status_var.set("Élément modifié")
                self.refresh_filters_sources()
                self.load_data()
            except Exception as e:
                messagebox.showerror("Erreur", f"Modification impossible: {e}")

    def on_delete(self):
        sels = self.tree.selection()
        if not sels:
            messagebox.showinfo("Info", "Sélectionnez une ou plusieurs lignes à supprimer.")
            return
        ids = []
        for item in sels:
            vals = self.tree.item(item, "values")
            ids.append(int(vals[0]))

        if messagebox.askyesno("Confirmer", f"Supprimer {len(ids)} élément(s) ?"):
            try:
                self.db.delete_many(ids)
                self.status_var.set("Élément(s) supprimé(s)")
                self.refresh_filters_sources()
                self.load_data()
            except Exception as e:
                messagebox.showerror("Erreur", f"Suppression impossible: {e}")


def main():
    # Vérifie la présence de la base
    if not os.path.exists(DB_PATH):
        messagebox.showwarning(
            "Base absente",
            f"La base n'a pas été trouvée à:\n{DB_PATH}\nElle sera créée vide.",
        )
    root = tk.Tk()
    app = ReleasesGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()