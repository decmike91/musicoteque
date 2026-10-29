"""Télécommande à distance : petit serveur web sur le Raspberry Pi (port 8080 par défaut).

- L'application Android (ou n'importe quel navigateur du réseau Wi-Fi) affiche la télécommande
  servie depuis app/remote_web/ et dialogue avec l'API JSON ci-dessous.
- Sécurité : un téléphone doit d'abord être appairé avec le code à 4 chiffres affiché sur l'écran
  du Pi (Outils ▸ Télécommande). Il reçoit alors un jeton conservé sur le téléphone.
- Les commandes sont exécutées dans le fil principal de l'interface (Qt), jamais en parallèle.
"""
import json
import mimetypes
import secrets
import socket
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from PySide6.QtCore import QObject, Signal, Slot

from .config import settings, APP_NAME
from .tags import read_tags, read_cover
from . import profiles as P

WEB_DIR = Path(__file__).resolve().parent / "remote_web"
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")


def local_ips() -> list[str]:
    """Adresses IP de la machine sur le réseau local."""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))       # aucun paquet n'est envoyé
        ips.append(s.getsockname()[0]); s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


def ensure_pin() -> str:
    if not settings.get("remote_pin"):
        settings["remote_pin"] = f"{secrets.randbelow(10000):04d}"
        settings.save()
    return settings["remote_pin"]


def new_pin() -> str:
    """Nouveau code : les téléphones déjà appairés devront se réappairer."""
    settings["remote_pin"] = f"{secrets.randbelow(10000):04d}"
    settings["remote_tokens"] = []
    settings.save()
    return settings["remote_pin"]


class MainThreadBridge(QObject):
    """Fait exécuter une fonction par le fil principal Qt et attend son résultat."""
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._run)

    @Slot(object)
    def _run(self, job):
        fn, box, ev = job
        try:
            box["result"] = fn()
        except Exception as e:          # renvoyé au téléphone sous forme d'erreur
            box["error"] = str(e)
        ev.set()

    def run(self, fn, timeout=8.0):
        if threading.current_thread() is threading.main_thread():
            return fn()
        box, ev = {}, threading.Event()
        self.call.emit((fn, box, ev))
        if not ev.wait(timeout):
            raise TimeoutError("l'application ne répond pas")
        if "error" in box:
            raise RuntimeError(box["error"])
        return box.get("result")


class RemoteServer:
    """API JSON + fichiers de la télécommande. `app` est la fenêtre tactile (TouchWindow)."""

    def __init__(self, app, port=None):
        self.app = app
        self.port = int(port or settings.get("remote_port", 8080))
        self.bridge = MainThreadBridge()
        self.httpd = None
        self.thread = None
        self.fails = []                 # tentatives d'appairage ratées (anti-essais en série)
        self.clients = {}               # jeton -> dernier contact
        ensure_pin()

    # ------------------------------------------------------------------ démarrage
    def start(self):
        if self.httpd:
            return True
        server = self

        class Handler(RemoteHandler):
            srv = server
        try:
            self.httpd = ThreadingHTTPServer(("0.0.0.0", self.port), Handler)
        except OSError as e:
            self.error = f"port {self.port} indisponible : {e}"
            self.httpd = None
            return False
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        if self.httpd:
            self.httpd.shutdown(); self.httpd.server_close(); self.httpd = None

    @property
    def running(self):
        return self.httpd is not None

    def urls(self):
        return [f"http://{ip}:{self.port}" for ip in local_ips()]

    def connected_phones(self, within=30):
        now = time.time()
        return sum(1 for t in self.clients.values() if now - t < within)

    # ------------------------------------------------------------------ appairage
    def pair(self, pin, client_ip):
        now = time.time()
        self.fails = [t for t in self.fails if now - t < 60]
        if len(self.fails) >= 5:
            return None, "Trop d'essais : patientez une minute."
        if str(pin).strip() != ensure_pin():
            self.fails.append(now)
            return None, "Code incorrect."
        token = secrets.token_urlsafe(18)
        toks = list(settings.get("remote_tokens") or [])[-19:] + [token]
        settings["remote_tokens"] = toks
        self.bridge.run(settings.save)
        return token, None

    def authorized(self, token):
        ok = bool(token) and token in (settings.get("remote_tokens") or [])
        if ok:
            self.clients[token] = time.time()
        return ok

    # ------------------------------------------------------------------ état
    def state(self):
        app = self.app
        hub = app.hub
        used = hub.used_sources()
        srcs = []
        for i, q in enumerate(app.queues):
            p = hub.players[i]
            path = q.current()
            t = read_tags(path) if path else None
            srcs.append({
                "id": i, "label": hub.label(i), "short": hub.label(i, True), "used": i in used,
                "playing": bool(p.playing), "position": round(p.position, 1), "duration": round(p.duration or 0, 1),
                "path": path or "", "title": (t.title or Path(path).stem) if t else "", "artist": t.artist if t else "",
                "album": t.album if t else "", "year": t.year if t else "", "has_cover": bool(t and t.has_cover),
                "volume": round(p.volume, 2), "muted": bool(p.muted), "shuffle": bool(q.shuffle), "repeat": q.repeat,
                "queue_len": len(q.order), "pos": q.pos,
            })
        outs = []
        from .audio_engine import device_label, zone_source
        for i, c in enumerate(settings.get("zones") or []):
            outs.append({"index": i, "label": device_label(c.get("device") or "") or "Sortie par défaut",
                         "source": zone_source(c), "enabled": bool(c.get("enabled", True)),
                         "volume": round(float(c.get("volume", 1.0)), 2), "profile": c.get("profile_name", "Par défaut")})
        return {"name": APP_NAME, "sources": srcs, "outputs": outs, "profiles": P.list_profiles(),
                "used": used}

    def queue(self, src):
        q = self.app.queues[src]
        by = {r["path"]: r for r in self.app.lib.tracks()}
        out = []
        for k, p in enumerate(q.paths()):
            r = by.get(p) or {}
            out.append({"k": k, "path": p, "title": r.get("title") or Path(p).stem, "artist": r.get("artist") or "",
                        "current": k == q.pos})
        return out

    def library(self, kind, args):
        lib = self.app.lib
        if kind == "artists":
            return [{"name": a, "albums": len(lib.albums(a))} for a in lib.artists()]
        if kind == "albums":
            artist = args.get("artist")
            return [{"name": al, "year": y, "count": n, "artist": artist} for al, y, n in lib.albums(artist)]
        if kind == "playlists":
            return [{"id": pid, "name": n, "count": len(lib.playlist_paths(pid))} for pid, n in lib.playlists()]
        if kind == "playlist":
            by = {r["path"]: r for r in lib.tracks()}
            rows = [by.get(p) or {"path": p, "title": Path(p).stem} for p in lib.playlist_paths(int(args["id"]))]
        elif kind == "tracks":
            rows = lib.tracks(artist=args.get("artist"), album=args.get("album"), search=args.get("q") or None,
                              order="album" if args.get("album") or args.get("artist") else "artist")
        else:
            raise ValueError("liste inconnue")
        return [{"path": r["path"], "title": r.get("title") or Path(r["path"]).stem, "artist": r.get("artist") or "",
                 "album": r.get("album") or "", "track": r.get("track") or 0, "duration": r.get("duration") or 0}
                for r in rows[:2000]]

    # ------------------------------------------------------------------ commandes
    def command(self, d):
        app = self.app
        src = int(d.get("src", 0))
        q, p = app.queues[src], app.hub.players[src]
        a, v = d.get("action"), d.get("value")
        if a == "play_pause":
            if not q.toggle_play():
                raise RuntimeError("Rien à lire : choisissez de la musique.")
        elif a == "next":
            q.next()
        elif a == "prev":
            q.prev()
        elif a == "stop":
            p.stop()
        elif a == "seek":
            p.seek(float(v))
        elif a == "volume":
            p.volume = max(0.0, min(1.0, float(v))); settings[app.volume_key(src)] = p.volume
        elif a == "mute":
            p.muted = not p.muted
        elif a == "shuffle":
            q.set_shuffle(bool(v))
        elif a == "repeat":
            q.cycle_repeat()
        elif a == "jump":
            q.play_at(int(v))
        elif a == "clear":
            q.clear()
        else:
            raise ValueError(f"commande inconnue : {a}")
        if src == app.cur_src:
            app.source_changed.emit()
        return True

    def play(self, d):
        src = int(d.get("src", 0))
        paths = [x for x in d.get("paths", []) if isinstance(x, str)]
        if not paths:
            raise ValueError("aucun titre")
        q = self.app.queues[src]
        mode = d.get("mode", "now")
        if mode == "now":
            q.set(paths, int(d.get("start", 0)))
        elif mode == "next":
            q.add(paths, next_=True)
        else:
            q.add(paths)
        self.app.source_changed.emit()
        return True

    def output(self, d):
        """Réglages d'une sortie depuis le téléphone (volume, lecteur, activation, profil)."""
        page = self.app.pages["son"]
        i = int(d["index"])
        page.remote_set_output(i, d)
        return True


class RemoteHandler(BaseHTTPRequestHandler):
    srv: RemoteServer = None
    server_version = "Musicotheque"

    def log_message(self, *args):       # pas de journal dans la console
        pass

    # --- réponses
    def _send(self, code, body, ctype="application/json; charset=utf-8", cache=False):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 2_000_000:
            raise ValueError("requête trop grande")
        return json.loads(self.rfile.read(n) or b"{}")

    def _token(self, qs):
        return self.headers.get("X-Token") or (qs.get("t") or [""])[0]

    # --- routes
    def do_GET(self):
        u = urlparse(self.path); qs = parse_qs(u.query)
        if not u.path.startswith("/api/"):
            return self._static(u.path)
        if not self.srv.authorized(self._token(qs)):
            return self._send(401, {"error": "non appairé"})
        args = {k: v[0] for k, v in qs.items()}
        try:
            if u.path == "/api/state":
                return self._send(200, self.srv.bridge.run(self.srv.state))
            if u.path == "/api/queue":
                return self._send(200, self.srv.bridge.run(lambda: self.srv.queue(int(args.get("src", 0)))))
            if u.path == "/api/library":
                return self._send(200, self.srv.library(args.get("kind", "artists"), args))
            if u.path == "/api/cover":
                path = args.get("path") or self.srv.app.queues[int(args.get("src", 0))].current()
                data = read_cover(path) if path else None
                if not data:
                    return self._send(404, {"error": "pas de pochette"})
                ctype = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
                return self._send(200, data, ctype, cache=True)
            return self._send(404, {"error": "inconnu"})
        except Exception as e:
            return self._send(500, {"error": str(e)})

    def do_POST(self):
        u = urlparse(self.path); qs = parse_qs(u.query)
        try:
            d = self._json_body()
        except Exception:
            return self._send(400, {"error": "requête invalide"})
        if u.path == "/api/pair":
            token, err = self.srv.pair(d.get("pin", ""), self.client_address[0])
            return self._send(200 if token else 403, {"token": token, "name": APP_NAME} if token else {"error": err})
        if not self.srv.authorized(self._token(qs)):
            return self._send(401, {"error": "non appairé"})
        routes = {"/api/cmd": self.srv.command, "/api/play": self.srv.play, "/api/output": self.srv.output}
        fn = routes.get(u.path)
        if not fn:
            return self._send(404, {"error": "inconnu"})
        try:
            self.srv.bridge.run(lambda: fn(d))
            return self._send(200, {"ok": True})
        except Exception as e:
            return self._send(400, {"error": str(e)})

    def _static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        f = (WEB_DIR / rel).resolve()
        if WEB_DIR not in f.parents and f != WEB_DIR or not f.is_file():
            return self._send(404, {"error": "introuvable"})
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith(("javascript", "json")):
            ctype += "; charset=utf-8"
        return self._send(200, f.read_bytes(), ctype, cache=f.suffix == ".png")
