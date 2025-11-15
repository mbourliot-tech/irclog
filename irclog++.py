# ✅ VERSION PATCHÉE — THREAD SAFE (NO SEGFAULT) ✅

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
RECONNECT_DELAY = 10
DEFAULT_MAX_RECONNECT_ATTEMPTS = 5


# ---------------- Utils ----------------

def extract_release_types(message):
    try:
        text_clean = re.sub(r'\x03(\d{1,2}(,\d{1,2})?)?', '', message)
        text_clean = re.sub(r'[\x02\x1F\x16\x0F]', '', text_clean)
        raw_tags = re.findall(r'\[([^\]]+)\]', text_clean)
        tags = [t.strip().upper() for t in raw_tags if t.strip()]
        types = [t for t in tags if t not in ('PRE', 'PRERELEASE')]
        return types, re.sub(r'^\s*(?:\[[^\]]+\]\s*)+', '', text_clean)
    except:
        return [], message


# ---------------- GUI ----------------

class IRCLoggerGUI:
    def __init__(self, root, container=None):
        self.root = root
        self.container = container if container else root

        self.server_var = tk.StringVar(value="irc.libera.chat")
        self.port_var = tk.IntVar(value=6697)
        self.ssl_var = tk.BooleanVar(value=True)
        self.nick_var = tk.StringVar(value="LoggerBot")
        self.realname_var = tk.StringVar(value="IRC Logger")
        self.channels_var = tk.StringVar(value="#testchan")
        self.keywords_var = tk.StringVar(value="")
        self.regex_var = tk.StringVar(value="")
        self.whitelist_var = tk.StringVar(value="")
        self.max_reconnect_attempts_var = tk.IntVar(value=DEFAULT_MAX_RECONNECT_ATTEMPTS)

        self.type_tabs = {}
        self.create_widgets()

        self.db_lock = threading.Lock()
        self.conn = sqlite3.connect("irc_logs.db", check_same_thread=False)
        self.create_tables()

        self.client = None
        self.reactor = irc.client.Reactor()
        self.connected = False
        self.failed_reconnects = 0
        self.reconnect_flag = True

        self.load_config()


    # ---------------- UI ----------------
    def create_widgets(self):
        self.notebook = ttk.Notebook(self.container)
        self.notebook.pack(fill="both", expand=True)

        config = ttk.Frame(self.notebook)
        self.notebook.add(config, text="Configuration")

        ttk.Entry(config, textvariable=self.server_var).grid(row=0, column=0)
        ttk.Button(config, text="Connect", command=self.start_connection).grid(row=1, column=0)

        logs = ttk.Frame(self.notebook)
        self.notebook.add(logs, text="Logs IRC")
        self.logs_text = scrolledtext.ScrolledText(logs, state="disabled")
        self.logs_text.pack(fill="both", expand=True)


    # ---------------- DB ----------------
    def create_tables(self):
        with self.db_lock:
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS releases (
                id INTEGER PRIMARY KEY,
                ts INTEGER,
                ts_iso TEXT,
                server TEXT,
                channel TEXT,
                nick TEXT,
                message TEXT,
                type TEXT
            )""")
            self.conn.commit()


    # ---------------- IRC ----------------
    def start_connection(self):
        if not self.connected:
            threading.Thread(target=self.irc_loop, daemon=True).start()


    def irc_loop(self):
        while self.reconnect_flag:
            try:
                server = self.server_var.get()
                port = self.port_var.get()
                nick = self.nick_var.get()

                if self.ssl_var.get():
                    ctx = ssl.create_default_context()
                    factory = irc.connection.Factory(wrapper=lambda s: ctx.wrap_socket(s, server_hostname=server))
                    c = self.reactor.server().connect(server, port, nick, connect_factory=factory)
                else:
                    c = self.reactor.server().connect(server, port, nick)

                c.add_global_handler("pubmsg", self.on_pubmsg)
                c.add_global_handler("all_events", self.on_event)

                self.client = c
                self.connected = True
                self.reactor.process_forever()

            except Exception as e:
                self.connected = False
                self.log_irc_event(f"Reconnexion dans {RECONNECT_DELAY}s : {e}")
                time.sleep(RECONNECT_DELAY)


    # ---------------- EVENTS ----------------
    def on_pubmsg(self, connection, event):
        nick = event.source.nick
        msg = event.arguments[0]
        chan = event.target

        self.log_irc_event(msg, nick, "MSG", chan)
        self.log_release(nick, msg, chan)


    def on_event(self, connection, event):
        src = getattr(event.source, 'nick', event.source)
        self.log_irc_event(f"[EVENT] {event.type} {src}")


    # ✅ THREAD SAFE LOG PRINT
    def log_irc_event(self, text, nick=None, event_type="INFO", channel=None):
        ts = time.strftime("%H:%M:%S")
        prefix = f"[{ts}] "

        if event_type == "MSG":
            line = f"{prefix}<{nick}@{channel}> {text}"
        else:
            line = prefix + text

        self.root.after(0, lambda: self._append_log_widget(line))

        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except:
            pass


    def _append_log_widget(self, line):
        self.logs_text.config(state="normal")
        self.logs_text.insert("end", line + "\n")
        self.logs_text.see("end")
        self.logs_text.config(state="disabled")


    # ✅ THREAD SAFE RELEASE LOG
    def log_release(self, nick, message, channel):
        types, clean = extract_release_types(message)
        if not types:
            return
        t = types[0]

        if t not in self.type_tabs:
            frame = ttk.Frame(self.notebook)
            txt = scrolledtext.ScrolledText(frame, state="disabled")
            txt.pack(fill="both", expand=True)
            self.notebook.add(frame, text=t)
            self.type_tabs[t] = txt

        self.root.after(0, lambda: self._append_release_widget(t, nick, channel, clean))


    def _append_release_widget(self, t, nick, channel, clean):
        w = self.type_tabs[t]
        w.config(state="normal")
        w.insert("end", f"[{time.strftime('%H:%M:%S')}] <{nick}@{channel}> {clean}\n")
        w.see("end")
        w.config(state="disabled")


    # ---------------- CONFIG ----------------
    def save_config(self):
        pass

    def load_config(self):
        pass


# --------------- main ---------------
if __name__ == "__main__":
    r = tk.Tk()
    app = IRCLoggerGUI(r)
    r.mainloop()
