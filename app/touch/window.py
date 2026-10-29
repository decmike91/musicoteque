"""Fenêtre plein écran de l'interface tactile (Raspberry Pi ou autre carte + écran tactile)."""
import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QLabel

from ..config import settings, APP_NAME, tool
from ..library import Library
from ..tags import read_tags
from ..audio_engine import AudioHub, MAX_SOURCES
from .. import identify as ident
from ..ui.widgets import Worker
from .common import px, label, button, Toast, ask, info
from .core import PlayQueue, MediaWatcher, has_audio, run_task
from .pages_music import NowPlayingPage, LibraryPage, QueuePage
from .pages_sound import SoundPage
from .pages_tools import ToolsPage


class TouchWindow(QWidget):
    source_changed = Signal()     # lecteur affiché (principal, 2, 3) ou sorties modifiées
    NAV = [("lecture", "▶\nLecture"), ("musique", "🎵\nMusique"), ("file", "☰\nFile"),
           ("son", "🎚\nSon"), ("outils", "🧰\nOutils")]

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.lib = Library()
        # jusqu'à 3 lecteurs indépendants : chacun joue sa musique sur ses propres sorties
        self.hub = AudioHub()
        self.queues = [PlayQueue(self.hub.players[i], self.lib, "" if i == 0 else f"_{i + 1}")
                       for i in range(MAX_SOURCES)]
        for i, q in enumerate(self.queues):
            self.hub.players[i].volume = settings.get(self.volume_key(i), 0.8)
            q.error.connect(lambda m: self.toast.show_msg(m, 5000))
        self.cur_src = 0
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        self.stack = QStackedWidget(); lay.addWidget(self.stack, 1)
        self.toast = Toast(self)
        self.pages = {}
        self.pages["lecture"] = NowPlayingPage(self)
        self.pages["musique"] = LibraryPage(self)
        self.pages["file"] = QueuePage(self)
        self.pages["son"] = SoundPage(self)
        self.pages["outils"] = ToolsPage(self)
        for k, _ in self.NAV:
            self.stack.addWidget(self.pages[k])
        # mini-lecteur (affiché hors de la page Lecture)
        self.mini = QWidget(); self.mini.setObjectName("mini")
        self.mini.setAttribute(Qt.WA_StyledBackground, True)
        self.mini.setStyleSheet("#mini { background: #161b22; border-top: 1px solid #30363d; }")
        ml = QHBoxLayout(self.mini); ml.setContentsMargins(px(10), px(2), px(6), px(2))
        self.mini_lbl = label("", None); self.mini_lbl.setStyleSheet("background:transparent")
        self.mini_play = button("▶", lambda: self.pages["lecture"].play_pause(), obj="small")
        self.mini_next = button("⏭", lambda: self.queue.next(), obj="small")
        ml.addWidget(self.mini_lbl, 1); ml.addWidget(self.mini_play); ml.addWidget(self.mini_next)
        self.mini_lbl.mousePressEvent = lambda e: self.show_page("lecture")
        lay.addWidget(self.mini)
        nav = QHBoxLayout(); nav.setSpacing(0)
        self.nav = {}
        for k, t in self.NAV:
            b = button(t, lambda _=False, k=k: self.show_page(k), obj="nav", checkable=True)
            self.nav[k] = b; nav.addWidget(b, 1)
        lay.addLayout(nav)
        for q in self.queues:
            q.track_changed.connect(lambda path, q=q: q is self.queue and self._mini_track(path))
        self.show_page("lecture" if self.lib.stats()["n"] else "musique")

        self.media = MediaWatcher(self)
        self.media.added.connect(self.media_added)
        self.media.removed.connect(self.media_removed)
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(50)
        QTimer.singleShot(600, self.startup)
        # télécommande (application Android / navigateur du téléphone)
        from ..remote import RemoteServer
        self.remote = RemoteServer(self)
        if settings.get("remote_enabled", True):
            self.remote.start()

    # ------------------------------------------------------------------ lecteurs
    @property
    def queue(self):
        """File du lecteur affiché (celui que pilotent les pages Lecture, Musique et File)."""
        return self.queues[self.cur_src]

    @property
    def player(self):
        return self.hub.players[self.cur_src]

    @staticmethod
    def volume_key(i):
        return "volume" if i == 0 else f"volume_{i + 1}"

    def set_source(self, i):
        self.cur_src = i
        self.source_changed.emit()
        self._mini_track(self.queue.current())

    def pick_source(self, title="Quel lecteur piloter ?"):
        from .common import choose
        opts = [(("▶ " if self.hub.players[i].playing else "") + self.hub.label(i), i) for i in self.hub.used_sources()]
        return choose(self, title, opts, self.cur_src)

    def sources_updated(self):
        if self.cur_src not in self.hub.used_sources():
            self.cur_src = 0
        self.source_changed.emit()

    # ------------------------------------------------------------------ navigation
    def show_page(self, key):
        self.stack.setCurrentWidget(self.pages[key])
        for k, b in self.nav.items():
            b.setChecked(k == key)
        self.mini.setVisible(key != "lecture" and bool(self.queue.current()))
        if key == "outils":
            self.pages["outils"].refresh_stats()
        if key == "file":
            self.pages["file"].refresh()

    def _mini_track(self, path):
        if not path:
            self.mini.setVisible(False); return
        t = read_tags(path)
        src = f"[{self.hub.label(self.cur_src, True)}]  " if len(self.hub.used_sources()) > 1 else ""
        self.mini_lbl.setText(f"♪  {src}{t.title or Path(path).stem}  —  {t.artist or ''}")
        self.mini.setVisible(self.stack.currentWidget() is not self.pages["lecture"])

    def tick(self):
        p = self.player
        cur = self.stack.currentWidget()
        if cur is self.pages["lecture"]:
            self.pages["lecture"].tick()
        else:
            self.mini_play.setText("⏸" if p.playing else "▶")
        if cur is self.pages["son"]:
            self.pages["son"].tick()
        main = self.hub.main
        if main.error:
            self.toast.show_msg(main.error, 6000); main.error = ""
        for i, q in enumerate(self.queues):          # chaque lecteur enchaîne ses propres titres
            sp = self.hub.players[i]
            if sp.finished:
                sp.finished = False; q.next(auto=True)
            if i and sp.error:
                self.toast.show_msg(f"{self.hub.label(i, True)} : {sp.error}", 6000); sp.error = ""

    def library_changed(self):
        self.pages["musique"].refresh(); self.pages["outils"].refresh_stats()

    # ------------------------------------------------------------------ démarrage
    def startup(self):
        if not tool("ffmpeg"):
            info(self, APP_NAME, "ffmpeg est introuvable : relancez l'installateur (install_rpi.sh).")
        root = settings["library_root"]
        Path(root).mkdir(parents=True, exist_ok=True)
        folders = [root] + list(settings.get("watched_folders", []))
        w = Worker(lambda progress, log, cancel: sum(self.lib.scan(f, cancel=cancel) for f in folders if Path(f).is_dir()))
        w.done.connect(lambda n: n and (self.library_changed(), self.toast.show_msg(f"{n} titre(s) ajouté(s)")))
        w.start(); self._startup_worker = w
        if self.lib.stats()["n"] == 0:
            QTimer.singleShot(1500, self.welcome)

    def welcome(self):
        if self.lib.stats()["n"]:
            return
        c = ask(self, "Bienvenue 👋", "La bibliothèque est vide.\nBranchez une clé USB ou un disque contenant de la musique, "
                                     "puis choisissez « Ranger », ou indiquez un dossier.",
                ("Ranger un support", "Choisir un dossier", "Plus tard"))
        if c == 0:
            self.pages["outils"].organize()
        elif c == 1:
            self.pages["outils"].add_folder()

    # ------------------------------------------------------------------ clés USB
    def media_added(self, mp, name):
        if not has_audio(mp):
            self.toast.show_msg(f"« {name} » branché (pas de musique trouvée)"); return
        c = ask(self, f"💾 « {name} » branché", "Ce support contient de la musique.",
                ("Écouter", "Ranger dans ma bibliothèque", "Ignorer"))
        if c == 0:
            lib = self.lib
            run_task(self, f"Lecture de « {name} »…", lambda progress, log, cancel: lib.scan(mp, progress=progress, cancel=cancel))
            rows = [r for r in self.lib.tracks() if r["path"].startswith(mp)]
            self.library_changed()
            if rows:
                self.queue.set([r["path"] for r in rows]); self.show_page("lecture")
        elif c == 1:
            self.pages["outils"].organize(mp)

    def media_removed(self, mp):
        for q in self.queues:
            cur = q.current()
            if cur and cur.startswith(mp):
                q.player.stop()
        self.lib.purge_missing(mp)
        self.library_changed()
        self.toast.show_msg(f"Support retiré : {Path(mp).name}")

    # ------------------------------------------------------------------ identification
    def identify(self, paths):
        def job(progress, log, cancel):
            ok = 0
            for i, p in enumerate(paths):
                if cancel():
                    break
                try:
                    m = ident.auto_identify(p, overwrite=len(paths) == 1)
                except Exception as e:
                    m = None; log(f"Erreur : {e}")
                if m:
                    ok += 1; log("✓ " + m.label()); self.lib.upsert(read_tags(p))
                else:
                    log("✗ non reconnu : " + Path(p).name)
                progress(i + 1, len(paths), p)
            return ok
        if not settings.get("acoustid_key"):
            self.toast.show_msg("Astuce : une clé AcoustID (Outils ▸ Paramètres) améliore la reconnaissance", 6000)
        n = run_task(self, "Identification des titres", job)
        self.library_changed()
        self.toast.show_msg(f"{n or 0} / {len(paths)} titre(s) identifié(s)")

    def closeEvent(self, e):
        settings.save()
        self.remote.stop()
        self.hub.close()
        super().closeEvent(e)
