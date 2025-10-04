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

CONFIG_FILE = "irc_config.json"

class IRCLoggerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("IRC Logger avec onglets et SSL/TLS")

        # --- Variables de configuration ---
        self.server_var = tk.StringVar(value="irc.libera.chat")
        self.port_var = tk.IntVar(value=6697)
        self.ssl_var = tk.BooleanVar(value=True)
        self.nick_var = tk.StringVar(value="LoggerBot")
        self.realname_var = tk.StringVar(value="IRC Logger")
        self.channels_var = tk.StringVar(value="#testchan")

        self.keywords_var = tk.StringVar(value="[GAMES]")
        self.regex_var = tk.StringVar(value="")
        self.whitelist_var = tk.StringVar(value="")

        # --- Interface ---
        self.create_widgets()

        # --- DB ---
        self.conn = sqlite3.connect("irc_logs.db")
        self.create_table()

        # --- IRC ---
        self.client = None
        self.reactor = irc.client.Reactor()
        self.connected = False

        # --- Charger config si existante ---
        self.load_config()

    # ---------------- UI ----------------
    def create_widgets(self):
        # Onglets
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        # --- Onglet Configuration ---
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

        # --- Filtres ---
        ttk.Label(config_frame, text="Mots-clés (, séparés):").grid(row=3, column=0, sticky="w")
        ttk.Entry(config_frame, textvariable=self.keywords_var, width=50).grid(row=3, column=1, columnspan=3)
        ttk.Label(config_frame, text="Regex (, séparés):").grid(row=4, column=0, sticky="w")
        ttk.Entry(config_frame, textvariable=self.regex_var, width=50).grid(row=4, column=1, columnspan=3)
        ttk.Label(config_frame, text="Whitelist nicks (, séparés):").grid(row=5, column=0, sticky="w")
        ttk.Entry(config_frame, textvariable=self.whitelist_var, width=50).grid(row=5, column=1, columnspan=3)

        # Boutons
        ttk.Button(config_frame, text="Se connecter", command=self.start_connection).grid(row=6, column=0, pady=5)
        ttk.Button(config_frame, text="Sauvegarder config", command=self.save_config).grid(row=6, column=1)
        ttk.Button(config_frame, text="Quitter", command=self.root.quit).grid(row=6, column=2)

        # --- Onglet Logs IRC ---
        self.logs_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.logs_frame, text="Logs IRC")
        self.logs_text = scrolledtext.ScrolledText(self.logs_frame, wrap=tk.WORD, state="disabled", height=20)
        self.logs_text.pack(fill="both", expand=True)

        # --- Onglet Messages filtrés ---
        self.msgs_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.msgs_frame, text="Messages filtrés")
        self.msgs_text = scrolledtext.ScrolledText(self.msgs_frame, wrap=tk.WORD, state="disabled", height=20)
        self.msgs_text.pack(fill="both", expand=True)

    # ---------------- DB ----------------
    def create_table(self):
        cursor = self.conn.cursor()
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nick TEXT,
                message TEXT,
                channel TEXT
            )"""
        )
        self.conn.commit()

    def log_filtered_message(self, nick, message, channel):
        self.msgs_text.config(state="normal")
        self.msgs_text.insert(tk.END, f"[{nick}@{channel}] {message}\n")
        self.msgs_text.see(tk.END)
        self.msgs_text.config(state="disabled")

        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO logs (nick, message, channel) VALUES (?, ?, ?)", (nick, message, channel))
        self.conn.commit()

    # ---------------- Filters ----------------
    def apply_filters(self, nick, message):
        whitelist = [n.strip() for n in self.whitelist_var.get().split(",") if n.strip()]
        if whitelist and nick not in whitelist:
            self.log_irc_event(f"Ignoré (nick non whitelisté) {nick}: {message}")
            return False

        keywords = [k.strip().lower() for k in self.keywords_var.get().split(",") if k.strip()]
        if any(k in message.lower() for k in keywords):
            return True

        regexes = [r.strip() for r in self.regex_var.get().split(",") if r.strip()]
        for reg in regexes:
            try:
                if re.search(reg, message, re.I):
                    return True
            except re.error as e:
                self.log_irc_event(f"Erreur regex '{reg}': {e}")
        return False

    # ---------------- Config ----------------
    def save_config(self):
        cfg = {
            "server": self.server_var.get(),
            "port": self.port_var.get(),
            "ssl": self.ssl_var.get(),
            "nick": self.nick_var.get(),
            "realname": self.realname_var.get(),
            "channels": self.channels_var.get(),
            "keywords": self.keywords_var.get(),
            "regex": self.regex_var.get(),
            "whitelist": self.whitelist_var.get()
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
        messagebox.showinfo("Info", "Configuration sauvegardée.")

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            self.server_var.set(cfg.get("server", self.server_var.get()))
            self.port_var.set(cfg.get("port", self.port_var.get()))
            self.ssl_var.set(cfg.get("ssl", self.ssl_var.get()))
            self.nick_var.set(cfg.get("nick", self.nick_var.get()))
            self.realname_var.set(cfg.get("realname", self.realname_var.get()))
            self.channels_var.set(cfg.get("channels", self.channels_var.get()))
            self.keywords_var.set(cfg.get("keywords", self.keywords_var.get()))
            self.regex_var.set(cfg.get("regex", self.regex_var.get()))
            self.whitelist_var.set(cfg.get("whitelist", self.whitelist_var.get()))

    # ---------------- IRC ----------------
    def start_connection(self):
        if self.connected:
            messagebox.showinfo("Info", "Déjà connecté.")
            return
        threading.Thread(target=self.irc_loop, daemon=True).start()

    def irc_loop(self):
        server = self.server_var.get()
        port = self.port_var.get()
        use_ssl = self.ssl_var.get()
        nick = self.nick_var.get()
        realname = self.realname_var.get()
        channels = [c.strip() for c in self.channels_var.get().split(",") if c.strip()]

        self.log_irc_event(f"Tentative de connexion à {server}:{port} (SSL={use_ssl})...")

        try:
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
            c.add_global_handler("all_events", self.on_event)

            self.client = c
            self.connected = True
            self.reactor.process_forever()

        except Exception as e:
            self.log_irc_event(f"Erreur de connexion: {e}")

    def on_connect(self, connection, event):
        self.log_irc_event(f"Connecté au serveur {self.server_var.get()}:{self.port_var.get()}")
        for chan in [c.strip() for c in self.channels_var.get().split(",") if c.strip()]:
            self.log_irc_event(f"Tentative de join sur {chan}")
            connection.join(chan)

    def on_pubmsg(self, connection, event):
        nick = event.source.nick
        message = event.arguments[0]
        chan = event.target
        self.log_irc_event(f"Message reçu de {nick}@{chan}: {message}")

        if self.apply_filters(nick, message):
            self.log_filtered_message(nick, message, chan)

    def on_event(self, connection, event):
        self.log_irc_event(f"[EVENT] {event.type} | Source: {event.source} | Target: {event.target} | Args: {event.arguments}")

    def log_irc_event(self, text):
        self.logs_text.config(state="normal")
        self.logs_text.insert(tk.END, text + "\n")
        self.logs_text.see(tk.END)
        self.logs_text.config(state="disabled")
        print(text)


if __name__ == "__main__":
    root = tk.Tk()
    app = IRCLoggerGUI(root)
    root.mainloop()
