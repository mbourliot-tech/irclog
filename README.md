# IRC Logger Suite — README (FR)

Ce projet fournit une suite d’outils pour logger des messages IRC, les stocker dans une base SQLite, les consulter/exporter via une interface graphique (Tkinter) et une interface Web locale.

## Aperçu des composants

- `irclog+.py` (recommandé) et `irclog.py` — Logger IRC avec configuration, reconnexion, enregistrement en base (`irc_logs.db`) et dans un fichier texte (`irc_log.txt`).
- `irc_db_gui.py` — Interface graphique (Tkinter) pour parcourir, filtrer, trier, éditer et exporter les releases depuis la base SQLite.
- `web_server.py` — Serveur HTTP local exposant une Web UI et des endpoints API pour lister/filtrer/trier/exporter les releases et piloter le logger IRC.
- `irc_suite.py` — Lance une application « Suite » avec deux onglets (Logger IRC, Base releases) et démarre le serveur Web en tâche de fond.
- `irc_config.json` — Fichier de configuration du logger IRC.
- `ftp_sites.json` — Configuration pour les exports FTP/WinSCP/CrossFTP.
- `irc_logs.db` — Base SQLite des releases (créée automatiquement si absente).
- `irc_log.txt` — Journal texte des événements IRC (pour consultation rapide côté Web).

## Prérequis

- Python 3.10 ou plus (testé avec Python standard sur Windows).
- Tkinter (fourni par l’installateur officiel Python pour Windows).
- Dépendances Python:
  - `irc` (client IRC)
  - `tkcalendar` (optionnel; améliore les champs de date dans la GUI)

Installez les paquets:

```bash
pip install irc tkcalendar
```

> `tkcalendar` est optionnel: si non installé, la GUI fonctionne sans calendrier intégré.

## Configuration

### Fichier `irc_config.json`

Exemple fourni:

```json
{
  "server": "tardis.swiftirc.net",
  "port": 6697,
  "ssl": true,
  "nick": "LoggerBot_",
  "realname": "IRC Logger",
  "channels": "#dupefr-pre",
  "keywords": "",
  "regex": "",
  "whitelist": "",
  "max_reconnect_attempts": 5
}
```

- `server` — Hôte IRC.
- `port` — Port (ex. `6697` pour TLS).
- `ssl` — `true` pour activer SSL/TLS.
- `nick` — Pseudo utilisé par le bot.
- `realname` — Nom complet (champ realname IRC).
- `channels` — Un ou plusieurs salons à rejoindre (une chaîne; si vous utilisez plusieurs salons, séparez-les par des espaces). 
- `keywords` — Mots-clés utilisés pour filtrer/identifier des releases (facultatif).
- `regex` — Expression régulière pour filtrer/typer des messages (facultatif).
- `whitelist` — Liste blanche (nicks, channels, etc.) selon votre logique (facultatif).
- `max_reconnect_attempts` — Nombre maximum de tentatives consécutives avant abandon (par défaut `5`).

Vous pouvez créer/modifier ce fichier depuis la GUI du logger (`Sauvegarder la configuration`).

### Fichier `ftp_sites.json`

Utilisé par `irc_db_gui.py` pour générer des exports (WinSCP queue, URLs CrossFTP). Exemple:

```json
{
  "default_site": "example",
  "sites": {
    "example": {
      "protocol": "ftps",
      "host": "ftp.example.com",
      "port": 21,
      "user": "username",
      "pass": "password",
      "local_base_dir": "C:\\Downloads",
      "name_transform": "raw",
      "base_paths": {
        "default": "/incoming",
        "GAMES": "/incoming/games",
        "MOVIES": "/incoming/movies"
      }
    }
  }
}
```

- `default_site` — Nom du site par défaut.
- `sites` — Dictionnaire de sites configurés.
- Par site:
  - `protocol` — `ftp`, `ftps`, `ftpes` ou `sftp`.
  - `host`, `port`, `user`, `pass` — Paramètres de connexion.
  - `local_base_dir` — Dossier local de base pour les téléchargements/scripts.
  - `name_transform` — Transformation du nom (`raw` | `underscores` | `dots`).
  - `base_paths` — Chemins distants par type de release (`default`, `GAMES`, `MOVIES`, etc.).

La GUI crée un exemple si `ftp_sites.json` est absent et vous guide pour le compléter.

## Démarrage et utilisation

### Lancer le Logger IRC (version étendue)

```bash
python irclog+.py
```

- Configurez les champs (serveur, port, SSL, nick, salons…).
- Cliquez pour vous connecter; le bot rejoindra les salons et peuplera la base `irc_logs.db`.
- Les logs bruts sont également écrits dans `irc_log.txt` (consultables via la Web UI).

> Alternative: `python irclog.py` lance une version plus simple du logger.

### Lancer la GUI Base Releases

```bash
python irc_db_gui.py
```

- Filtrez par `server`, `channel`, `nick`, `type`, recherche texte (`query`), et dates (`date_from`, `date_to`).
- Triez en cliquant sur les en-têtes de colonnes.
- Actions disponibles: `Ajouter`, `Éditer`, `Supprimer`, `Exporter CSV`, `Exporter Queue WinSCP`, `Exporter URLs CrossFTP`.

### Lancer la Suite (GUI + Web + Logger)

```bash
python irc_suite.py
```

- Ouvre une fenêtre avec deux onglets: Logger IRC et Base releases.
- Démarre le serveur Web en tâche de fond et lui injecte le logger pour exposer le statut et les actions connect/disconnect.

### Lancer uniquement le Serveur Web

```bash
python web_server.py
```

- Par défaut: accessible sur `http://localhost:8000/`.
- Variables d’environnement:
  - `WEB_HOST` — hôte d’écoute (par défaut `0.0.0.0`).
  - `WEB_PORT` — port (par défaut `8000`).

#### Endpoints principaux

- `GET /api/releases` — Liste paginée/triée des releases.
  - Paramètres: `limit`, `page`, `server`, `channel`, `nick`, `type`, `query`, `date_from`, `date_to`, `sort` (ex: `ts:DESC,channel:ASC`).
- `GET /api/count` — Nombre total correspondant aux filtres courants.
- `GET /api/filters` — Valeurs distinctes pour alimenter les listes de filtres.
- `GET /api/export.csv` — Export CSV des releases filtrées.
- `GET /api/irc/status` — Statut du logger IRC (`available`, `connected`).
- `GET /api/irc/connect` — Demande de connexion (si logger injecté).
- `GET /api/irc/disconnect` — Demande de déconnexion.
- `GET /api/irc/logs?tail=200` — Dernières lignes de `irc_log.txt`.
- `POST /api/irc/nfo` — Envoie une commande NFO et détecte automatiquement les URLs NFO dans les logs IRC.

#### Fonctionnalité NFO

L'interface Web inclut une **fonctionnalité NFO avancée** :

- **Bouton NFO** : Disponible sur chaque ligne de release pour envoyer automatiquement la commande `!nfo <release_name>` sur IRC.
- **Détection d'URL automatique** : Analyse les logs IRC en temps réel pour détecter les URLs NFO (ex: `https://dupefr.fr/nfo7/...`).
- **Nettoyage des URLs** : Supprime automatiquement les codes de couleur IRC (`\x03xx`) et autres caractères parasites des URLs détectées.
- **Ouverture automatique** : Ouvre directement l'URL NFO dans un nouvel onglet du navigateur.
- **Notifications toast** : Affiche l'URL détectée avant ouverture et confirme l'action.

Cette fonctionnalité permet de consulter rapidement les fichiers NFO des releases sans manipulation manuelle.

L'interface Web inclut également filtrage, tri par clic sur en-têtes, pagination, affichage des logs IRC et bascule du thème (clair/sombre), avec un layout responsive.

## Base de données (SQLite)

- Fichier: `irc_logs.db` (créé à côté des scripts si absent).
- Table `releases` (créée/assurée par `ReleasesDB`): colonnes utilisées par l’UI `id`, `ts`, `ts_iso`, `server`, `channel`, `nick`, `message`, `type`.
- Les insertions sont réalisées par le logger IRC (via les callbacks d’événements).

## Dépannage

- Aucun résultat dans la Web UI:
  - Vérifiez que `irc_logs.db` existe et contient des données (lancez le logger ou ajoutez des entrées via la GUI).
  - Confirmez que la Web UI pointe sur le bon fichier (elle utilise `DB_PATH` de `irc_db_gui.py`).
- Connection IRC échoue:
  - Vérifiez `server`, `port`, `ssl`, `nick` dans `irc_config.json`.
  - Assurez-vous que le port 6697 est accessible (TLS). Essayez un autre serveur ou port.
- Web UI inaccessible:
  - Port `8000` déjà utilisé? Lancez avec `WEB_PORT=8080`.
  - Pare-feu Windows: autorisez Python sur le port choisi.
- Export FTP/WinSCP/CrossFTP:
  - Complétez `ftp_sites.json` (host/user/pass) et vérifiez les chemins `base_paths` selon le `type` des releases.
- Fonctionnalité NFO:
  - **URLs NFO incorrectes** : Les codes de couleur IRC (`\x03xx`) sont automatiquement supprimés. Si le problème persiste, vérifiez les logs IRC.
  - **Bouton NFO ne fonctionne pas** : Assurez-vous que le logger IRC est connecté et que le canal supporte les commandes `!nfo`.
  - **Navigateur bloqué** : Si votre navigateur ou extension (ad blocker) bloque l'ouverture, désactivez temporairement les extensions ou testez en mode incognito.

## Bonnes pratiques / Sécurité

- Ne commitez pas `irc_config.json` et `ftp_sites.json` s’ils contiennent des identifiants.
- Réservez un utilisateur FTP dédié avec permissions limitées.
- Sauvegardez régulièrement `irc_logs.db`.

## Licence

Ce projet n’inclut pas de licence explicite. Si besoin, ajoutez votre fichier de licence séparément.