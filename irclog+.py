import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import re
import sqlite3
import ssl
import irc.client
import irc.connection
import json
import os
import time

CONFIG_FILE = "irc_config.json"
LOG_FILE = "irc_log.txt"
RECONNECT_DELAY = 10  # secondes avant tentative de reconnexion

# ---------------- Utils ----------------
def extract_release_types(message):
    clean = re.sub(r'\x03(\d{1,2}(,\d{1,2})?)?', '', message)  
    clean = re.sub(r'[\x02\x1F\x16\x0F]', '', clean)          
    clean = re.sub(r'\d+\[|\]\d+', '[', clean)
    types = re.findall(r'\[(\w+)\]', clean)
    text_clean = re.sub(r'\[(\w+)\]', '', clean).strip()
    return [t.upper() for t in types], text_clean

# ---------------- GUI ----------------
class IRCLoggerGUI:
    def __init__(self, root, container=None):
        self.root = root
        # Conteneur d'intégration (onglet) si fourni, sinon la racine
        self.container = container if container is not None else root
        # Titre uniquement si lancé en mode standalone (pas de conteneur)
        try:
            if self.container is self.root and isinstance(root, (tk.Tk, tk.Toplevel)):
                self.root.title("IRC Logger - Releases par type")
        except Exception:
            pass

        self.server_var = tk.StringVar(value="irc.libera.chat")
        self.port_var = tk.IntVar(value=6697)
        self.ssl_var = tk.BooleanVar(value=True)
        self.nick_var = tk.StringVar(value="LoggerBot")
        self.realname_var = tk.StringVar(value="IRC Logger")
        self.channels_var = tk.StringVar(value="#testchan")
        self.keywords_var = tk.StringVar(value="")
        self.regex_var = tk.StringVar(value="")
        self.whitelist_var = tk.StringVar(value="")

        self.type_tabs = {}
        self.create_widgets()

        self.db_lock = threading.Lock()
        self.conn = sqlite3.connect("irc_logs.db", check_same_thread=False)
        self.create_tables()

        self.client = None
        self.reactor = irc.client.Reactor()
        self.connected = False

        self.load_config()
        self.reconnect_flag = True

    # ---------------- UI ----------------
    def create_widgets(self):
        # Monte toute l'interface dans le conteneur fourni
        self.notebook = ttk.Notebook(self.container)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        config_frame = ttk.Frame(self.notebook)
        self.notebook.add(config_frame, text="Configuration")
        ttk.Label(config_frame, text="Serveur:").grid(row=0, column=0, sticky="w")
        ttk.Entry(config_frame, textvariable=self.server_var, width=20).grid(row=0, column=1)
        ttk.Label(config_frame, text="Port:").grid(row=0, column=2, sticky="w")
        ttk.Entry(config_frame, textvariable=self.port_var, width=6).grid(row=0, column=3)
        ttk.Checkbutton(config_frame, text="SSL/TLS", variable=self.ssl_var).grid(row=0, column=4, padx=5)
        ttk.Label(config_frame, text="Nick:").grid(row=1, column=0, sticky="w")
        ttk.Entry(config_frame, textvariable=self.nick_var, width=15).grid(row=1, column=1)
        ttk.Label(config_frame, text="Realname:").grid(row=1, column=2, sticky="w")
        ttk.Entry(config_frame, textvariable=self.realname_var, width=15).grid(row=1, column=3)
        ttk.Label(config_frame, text="Channels (, séparés):").grid(row=2, column=0, sticky="w")
        ttk.Entry(config_frame, textvariable=self.channels_var, width=30).grid(row=2, column=1, columnspan=3, sticky="we")
        ttk.Button(config_frame, text="Se connecter", command=self.start_connection).grid(row=6, column=0, pady=5)
        ttk.Button(config_frame, text="Sauvegarder config", command=self.save_config).grid(row=6, column=1)
        ttk.Button(config_frame, text="Quitter", command=self.root.quit).grid(row=6, column=2)
        ttk.Button(config_frame, text="Tester un message", command=self.test_message).grid(row=7, column=0, pady=5)

        self.logs_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.logs_frame, text="Logs IRC")
        self.logs_text = scrolledtext.ScrolledText(self.logs_frame, wrap=tk.WORD, state="disabled", height=20)
        self.logs_text.pack(fill="both", expand=True)

    # ---------------- DB ----------------
    def create_tables(self):
        with self.db_lock:
            cursor = self.conn.cursor()
            cursor.execute("""
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
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_message ON releases(message)")
            self.conn.commit()

    # ---------------- Logging releases ----------------
    def log_release(self, nick, message, channel):
        types, text_clean = extract_release_types(message)
        if not types:
            return
        type_to_log = types[-1]
        ts = int(time.time())
        ts_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))

        with self.db_lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO releases (ts, ts_iso, server, channel, nick, message, type) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts, ts_iso, self.server_var.get(), channel, nick, text_clean, type_to_log)
            )
            self.conn.commit()

        if type_to_log not in self.type_tabs:
            frame = ttk.Frame(self.notebook)
            text_widget = scrolledtext.ScrolledText(frame, wrap=tk.WORD, state="disabled", height=20)
            text_widget.pack(fill="both", expand=True)
            self.notebook.add(frame, text=type_to_log)
            self.type_tabs[type_to_log] = text_widget

        self.type_tabs[type_to_log].config(state="normal")
        self.type_tabs[type_to_log].insert(tk.END, f"[{time.strftime('%H:%M:%S')}] <{nick}@{channel}> {text_clean}\n")
        self.type_tabs[type_to_log].see(tk.END)
        self.type_tabs[type_to_log].config(state="disabled")

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts_iso}] <{nick}@{channel}> [{type_to_log}] {text_clean}\n")

    # ---------------- Filters ----------------
    def apply_filters(self, nick, message):
        whitelist = [n.strip() for n in self.whitelist_var.get().split(",") if n.strip()]
        if whitelist and nick not in whitelist:
            return False
        keywords = [k.strip().lower() for k in self.keywords_var.get().split(",") if k.strip()]
        if keywords and any(k in message.lower() for k in keywords):
            return True
        regexes = [r.strip() for r in self.regex_var.get().split(",") if r.strip()]
        for reg in regexes:
            try:
                if re.search(reg, message, re.I):
                    return True
            except re.error:
                continue
        if not keywords and not regexes and not whitelist:
            return True
        return False

    # ---------------- Config ----------------
    def save_config(self):
        cfg = {var: getattr(self, f"{var}_var").get() for var in ["server","port","ssl","nick","realname","channels","keywords","regex","whitelist"]}
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
        messagebox.showinfo("Info", "Configuration sauvegardée.")

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            for var, val in cfg.items():
                getattr(self, f"{var}_var").set(val)

    # ---------------- IRC ----------------
    def start_connection(self):
        if self.connected:
            return
        # Réactiver la boucle de reconnexion si elle a été stoppée
        self.reconnect_flag = True
        # Lancer la boucle IRC en tâche de fond
        threading.Thread(target=self.irc_loop, daemon=True).start()

    def stop_connection(self):
        # Demande d'arrêt de la boucle et fermeture de la connexion
        try:
            self.reconnect_flag = False
            if self.client is not None:
                # Tenter un QUIT gracieux, sinon une déconnexion directe
                quit_fn = getattr(self.client, "quit", None)
                if callable(quit_fn):
                    try:
                        quit_fn("Déconnexion demandée")
                    except Exception:
                        pass
                disconnect_fn = getattr(self.client, "disconnect", None)
                if callable(disconnect_fn):
                    try:
                        disconnect_fn("Déconnexion")
                    except Exception:
                        pass
            self.connected = False
            self.client = None
            self.log_irc_event("Déconnexion demandée", event_type="INFO")
        except Exception:
            # Ne pas bloquer sur erreur de déconnexion
            self.connected = False
            self.client = None

    def irc_loop(self):
        while self.reconnect_flag:
            server = self.server_var.get()
            port = self.port_var.get()
            use_ssl = self.ssl_var.get()
            nick = self.nick_var.get()
            realname = self.realname_var.get()
            try:
                self.log_irc_event(f"Tentative de connexion à {server}:{port} (SSL={use_ssl})...", event_type="INFO")
                if use_ssl:
                    context = ssl.create_default_context()
                    def ssl_wrapper(sock):
                        return context.wrap_socket(sock, server_hostname=server)
                    ssl_factory = irc.connection.Factory(wrapper=ssl_wrapper)
                    c = self.reactor.server().connect(server, port, nick, ircname=realname, connect_factory=ssl_factory)
                else:
                    c = self.reactor.server().connect(server, port, nick, ircname=realname)
                c.add_global_handler("welcome", self.on_connect)
                c.add_global_handler("pubmsg", self.on_pubmsg)
                c.add_global_handler("join", self.on_join)
                c.add_global_handler("part", self.on_part)
                c.add_global_handler("quit", self.on_quit)
                c.add_global_handler("all_events", self.on_event)
                self.client = c
                self.connected = True
                self.reactor.process_forever()
            except Exception as e:
                self.log_irc_event(f"Erreur de connexion: {e}. Reconnexion dans {RECONNECT_DELAY}s...", event_type="INFO")
                self.connected = False
                time.sleep(RECONNECT_DELAY)

    # ---------------- Handlers ----------------
    def on_connect(self, connection, event):
        self.log_irc_event(f"Connecté au serveur {self.server_var.get()}:{self.port_var.get()}", event_type="INFO")
        for chan in [c.strip() for c in self.channels_var.get().split(",") if c.strip()]:
            connection.join(chan)

    def on_pubmsg(self, connection, event):
        nick = event.source.nick
        raw_message = event.arguments[0]
        chan = event.target
        self.log_irc_event(raw_message, nick=nick, event_type="MSG", channel=chan)
        message_clean = re.sub(r'\x03(\d{1,2}(,\d{1,2})?)?','', raw_message)
        message_clean = re.sub(r'[\x02\x1F\x16\x0F]','', message_clean)
        no_filters = not self.keywords_var.get().strip() and not self.regex_var.get().strip() and not self.whitelist_var.get().strip()
        types, _ = extract_release_types(raw_message)
        if no_filters and types:
            self.log_release(nick, raw_message, chan)
            return
        if self.apply_filters(nick, message_clean):
            self.log_release(nick, raw_message, chan)

    def on_join(self, connection, event):
        self.log_irc_event("", nick=event.source.nick, event_type="JOIN", channel=event.target)

    def on_part(self, connection, event):
        self.log_irc_event("", nick=event.source.nick, event_type="PART", channel=event.target)

    def on_quit(self, connection, event):
        self.log_irc_event("", nick=event.source.nick, event_type="QUIT")

    def on_event(self, connection, event):
        self.log_irc_event(f"[DEBUG] {event.type} | Source: {event.source} | Target: {event.target} | Args: {event.arguments}", event_type="INFO")

    # ---------------- Logs colorés ----------------
    def log_irc_event(self, text, nick=None, event_type="INFO", channel=None):
        ts = time.strftime("%H:%M:%S", time.localtime())
        if event_type == "MSG" and nick and channel:
            line = f"[{ts}] <{nick}> {text}"
            color = "blue"
        elif event_type == "JOIN" and nick and channel:
            line = f"[{ts}] -!- {nick} joined {channel}"
            color = "green"
        elif event_type == "PART" and nick and channel:
            line = f"[{ts}] -!- {nick} left {channel}"
            color = "orange"
        elif event_type == "QUIT" and nick:
            line = f"[{ts}] -!- {nick} quit"
            color = "red"
        else:
            line = f"[{ts}] *** {text}"
            color = "black"

        self.logs_text.config(state="normal")
        self.logs_text.insert(tk.END, line + "\n", event_type)
        self.logs_text.tag_config(event_type, foreground=color)
        self.logs_text.see(tk.END)
        self.logs_text.config(state="disabled")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ---------------- Test message ----------------
    def test_message(self):
        sample_msg = "4[14PRE4] 15[8TV15] 0Simon.Coleman.S03E02.FRENCH.720p.WEB.H264-AMB3R"
        nick = "DupeFR"
        channel = "#testchan"
        self.log_irc_event(sample_msg, nick=nick, event_type="MSG", channel=channel)
        message_clean = re.sub(r'\x03(\d{1,2}(,\d{1,2})?)?','', sample_msg)
        message_clean = re.sub(r'[\x02\x1F\x16\x0F]','', message_clean)
        types, _ = extract_release_types(sample_msg)
        no_filters = not self.keywords_var.get().strip() and not self.regex_var.get().strip() and not self.whitelist_var.get().strip()
        if no_filters and types:
            self.log_release(nick, sample_msg, channel)
            return
        if self.apply_filters(nick, message_clean):
            self.log_release(nick, sample_msg, channel)


if __name__ == "__main__":
    root = tk.Tk()
    app = IRCLoggerGUI(root)
    root.mainloop()
