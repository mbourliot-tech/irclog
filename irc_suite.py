import tkinter as tk
from tkinter import ttk
import os
import importlib.util

from irc_db_gui import ReleasesGUI
from web_server import start_web_server_in_thread


def load_irclog_plus_class():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    plus_path = os.path.join(base_dir, "irclog+.py")
    spec = importlib.util.spec_from_file_location("irclog_plus", plus_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return getattr(mod, "IRCLoggerGUI")


def main():
    root = tk.Tk()
    root.title("Suite IRC")
    root.geometry("1200x800")

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True)

    # Onglet irclog+
    tab_logger = ttk.Frame(nb)
    nb.add(tab_logger, text="Logger IRC")
    # Instancier l’app dans le frame
    IRCLoggerPlusGUI = load_irclog_plus_class()
    logger_app = IRCLoggerPlusGUI(root, container=tab_logger)

    # Onglet Base releases
    tab_db = ttk.Frame(nb)
    nb.add(tab_db, text="Base releases")
    db_app = ReleasesGUI(root, container=tab_db)

    # Démarrer le serveur web en tâche de fond
    try:
        # Injecte l’instance IRC dans le serveur web pour exposer statut/connexion
        start_web_server_in_thread(host="0.0.0.0", port=8000, irc_logger=logger_app)
    except Exception:
        pass

    root.mainloop()


if __name__ == "__main__":
    main()