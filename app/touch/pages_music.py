"""Pages « Lecture », « Musique » (bibliothèque) et « File » de l'interface tactile."""
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QPixmap, QIcon, QColor, QPainter
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QLabel, QSizePolicy

from ..config import settings
from ..tags import read_tags, read_cover
from ..ui.widgets import VUMeter, fmt_time
from .common import (px, label, button, touch_slider, TouchList, ask, info, choose, menu, Keyboard)


def cover_pixmap(path, size):
    data = read_cover(path) if path else None
    pm = QPixmap()
    if data and pm.loadFromData(data):
        return pm.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    pm = QPixmap(size, size); pm.fill(QColor("#161b22"))
    p = QPainter(pm); p.setPen(QColor("#484f58")); f = p.font(); f.setPixelSize(int(size * 0.45)); p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "♪"); p.end()
    return pm


# =================================================================== Lecture
class NowPlayingPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        # choix du lecteur affiché (visible seulement si plusieurs lecteurs ont des sorties)
        self.src_host = QWidget(); self.src_row = QHBoxLayout(self.src_host)
        self.src_row.setContentsMargins(px(8), px(4), px(8), 0); self.src_row.setSpacing(0)
        outer.addWidget(self.src_host)
        self.box = QBoxLayout(QBoxLayout.LeftToRight)
        outer.addLayout(self.box, 1)
        self.box.setContentsMargins(px(16), px(6), px(16), px(6)); self.box.setSpacing(px(18))
        self.cover = QLabel(); self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.box.addWidget(self.cover, 5)
        right = QVBoxLayout(); right.setSpacing(px(8))
        self.title = label("Aucun titre", "h1", wrap=True)
        self.artist = label("", "h2", wrap=True)
        self.album = label("", "dim", wrap=True)
        right.addWidget(self.title); right.addWidget(self.artist); right.addWidget(self.album)
        right.addStretch()
        self.seek = touch_slider(Qt.Horizontal, 0, 1000)
        self.seek.sliderReleased.connect(lambda: self.app.player.seek(self.seek.value() / 1000 * self.app.player.duration))
        t = QHBoxLayout(); self.t_pos = label("0:00", "dim"); self.t_dur = label("0:00", "dim")
        t.addWidget(self.t_pos); t.addStretch(); t.addWidget(self.t_dur)
        right.addWidget(self.seek); right.addLayout(t)
        ctl = QHBoxLayout(); ctl.setSpacing(px(10))
        self.b_shuffle = button("🔀", self.toggle_shuffle, obj="icon", checkable=True)
        self.b_shuffle.setChecked(app.queue.shuffle)
        self.b_prev = button("⏮", lambda: self.app.queue.prev(), obj="icon")
        self.b_play = button("▶", self.play_pause, obj="round")
        self.b_next = button("⏭", lambda: self.app.queue.next(), obj="icon")
        self.b_repeat = button("🔁", self.cycle_repeat, obj="icon", checkable=True)
        self._repeat_ui()
        ctl.addStretch()
        for b in (self.b_shuffle, self.b_prev, self.b_play, self.b_next, self.b_repeat):
            ctl.addWidget(b)
        ctl.addStretch()
        right.addLayout(ctl)
        vol = QHBoxLayout()
        self.b_mute = button("🔊", self.toggle_mute, obj="icon", checkable=True)
        self.vol = touch_slider(Qt.Horizontal, 0, 100, app.player.volume * 100)
        self.vol.valueChanged.connect(self.set_volume); self.set_volume(self.vol.value())
        self.vol_lbl = label(f"{self.vol.value()} %"); self.vol_lbl.setFixedWidth(px(60))
        vol.addWidget(self.b_mute); vol.addWidget(self.vol, 1); vol.addWidget(self.vol_lbl)
        right.addLayout(vol)
        bottom = QHBoxLayout()
        self.vu = VUMeter(); self.vu.setMinimumHeight(px(36))
        self.b_sound = button("🎚 Son", lambda: app.show_page("son"))
        bottom.addWidget(self.vu, 1); bottom.addWidget(self.b_sound)
        right.addLayout(bottom)
        self.box.addLayout(right, 6)
        for q in app.queues:
            q.track_changed.connect(lambda path, q=q: q is self.app.queue and self.show_track(path))
        app.source_changed.connect(self.source_changed)
        self.source_changed()

    def source_changed(self):
        """Affiche le lecteur choisi : titre, volume, aléatoire, répétition."""
        app = self.app
        while self.src_row.count():
            it = self.src_row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        used = app.hub.used_sources()
        for i in used:
            b = button(("▶ " if app.hub.players[i].playing else "") + app.hub.label(i),
                       lambda _=False, i=i: app.set_source(i), obj="seg", checkable=True)
            b.setChecked(i == app.cur_src); self.src_row.addWidget(b, 1)
        self.src_host.setVisible(len(used) > 1)
        self.vol.blockSignals(True); self.vol.setValue(round(app.player.volume * 100)); self.vol.blockSignals(False)
        self.vol_lbl.setText(f"{self.vol.value()} %")
        self.b_shuffle.setChecked(app.queue.shuffle); self._repeat_ui()
        self.b_mute.setChecked(app.player.muted); self.b_mute.setText("🔇" if app.player.muted else "🔊")
        self.show_track(app.queue.current())

    def resizeEvent(self, e):
        portrait = self.height() > self.width() * 1.1
        self.box.setDirection(QBoxLayout.TopToBottom if portrait else QBoxLayout.LeftToRight)
        QTimer.singleShot(0, self._fit_cover)
        super().resizeEvent(e)

    def _fit_cover(self):
        path = self.app.queue.current()
        s = max(px(120), min(self.cover.width(), self.cover.height()) - px(8))
        self.cover.setPixmap(cover_pixmap(path, s))

    def show_track(self, path):
        if not path:
            self.title.setText("Aucun titre"); self.artist.setText(
                "Choisissez de la musique (page Musique)" if self.app.cur_src == 0 else
                f"{self.app.hub.label(self.app.cur_src, True)} : choisissez de la musique (page Musique)")
            self.album.setText(""); self._fit_cover(); return
        t = read_tags(path)
        self.title.setText(t.title or Path(path).stem)
        self.artist.setText(t.artist or "Artiste inconnu")
        self.album.setText(" · ".join(x for x in (t.album, t.year, t.genre) if x))
        self._fit_cover()

    def play_pause(self):
        if not self.app.queue.toggle_play():
            rows = self.app.lib.tracks()
            if rows:
                self.app.queue.set([r["path"] for r in rows], 0)

    def toggle_shuffle(self):
        self.app.queue.set_shuffle(self.b_shuffle.isChecked())

    def cycle_repeat(self):
        self.app.queue.cycle_repeat(); self._repeat_ui()
        self.app.toast.show_msg({"none": "Répétition désactivée", "all": "Répéter toute la file",
                                 "one": "Répéter ce titre"}[self.app.queue.repeat])

    def _repeat_ui(self):
        r = self.app.queue.repeat
        self.b_repeat.setText("🔂" if r == "one" else "🔁"); self.b_repeat.setChecked(r != "none")

    def set_volume(self, v):
        self.app.player.volume = v / 100; settings[self.app.volume_key(self.app.cur_src)] = v / 100
        if hasattr(self, "vol_lbl"):
            self.vol_lbl.setText(f"{v} %")

    def toggle_mute(self):
        on = self.b_mute.isChecked()
        self.app.player.muted = on; self.b_mute.setText("🔇" if on else "🔊")

    def tick(self):
        p = self.app.player
        self.b_play.setText("⏸" if p.playing else "▶")
        if p.duration and not self.seek.isSliderDown():
            self.seek.setValue(int(p.position / p.duration * 1000))
        self.t_pos.setText(fmt_time(p.position)); self.t_dur.setText(fmt_time(p.duration))
        self.vu.set_levels(*(p.levels if p.playing else (0, 0, 0, 0)))
        z = [c for c in (settings.get("zones") or [{}]) if c.get("enabled", True)
             and int(c.get("source", 0) or 0) == self.app.cur_src]
        names = [c.get("profile_name", "") for c in z]
        self.b_sound.setText("🎚 Son"); self.b_sound.setToolTip(", ".join(names))


# =================================================================== Musique
class LibraryPage(QWidget):
    MODES = [("artists", "👤 Artistes"), ("albums", "💿 Albums"), ("tracks", "🎵 Titres"), ("playlists", "📃 Playlists")]

    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self); lay.setContentsMargins(px(8), px(6), px(8), 0); lay.setSpacing(px(4))
        top = QHBoxLayout(); top.setSpacing(0)
        self.b_back = button("←", self.back, obj="icon"); top.addWidget(self.b_back)
        self.seg = {}
        for key, lab in self.MODES:
            b = button(lab, lambda _=False, k=key: self.set_mode(k), obj="seg", checkable=True)
            self.seg[key] = b; top.addWidget(b, 1)
        top.addSpacing(px(6))
        self.b_search = button("🔍", self.search, obj="icon"); top.addWidget(self.b_search)
        lay.addLayout(top)
        head = QHBoxLayout()
        self.crumb = label("", "h2"); head.addWidget(self.crumb, 1)
        self.b_src = button("", self.change_source); head.addWidget(self.b_src)
        self.b_play_all = button("▶ Tout lire", self.play_all); head.addWidget(self.b_play_all)
        self.b_shuffle_all = button("🔀 Aléatoire", self.shuffle_all); head.addWidget(self.b_shuffle_all)
        lay.addLayout(head)
        self.list = TouchList(); lay.addWidget(self.list, 1)
        self.list.tapped.connect(self.tapped)
        self.list.long_pressed.connect(self.long_pressed)
        self.stack = []          # navigation : [(mode, filtre)]
        self.filter = ""
        self.rows = []
        self._icon_jobs = []
        self.icon_timer = QTimer(self); self.icon_timer.timeout.connect(self._load_icons)
        self.set_mode("artists")
        app.source_changed.connect(self._src_chip)
        self._src_chip()

    def _src_chip(self):
        """Indique sur quel lecteur la musique choisie sera jouée (si plusieurs)."""
        used = self.app.hub.used_sources()
        self.b_src.setVisible(len(used) > 1)
        self.b_src.setText(f"🎧 sur : {self.app.hub.label(self.app.cur_src, True)} ▾")

    def change_source(self):
        i = self.app.pick_source("Jouer la musique choisie sur…")
        if i is not None:
            self.app.set_source(i)

    def play_elsewhere(self, paths, add=False):
        others = [i for i in self.app.hub.used_sources() if i != self.app.cur_src]
        if not others:
            info(self, "Autre lecteur", "Pour écouter autre chose sur une autre sortie (casque Bluetooth…) :\n"
                                        "Son ▸ ＋ (ajouter une sortie) ▸ Sortie & volume ▸ Lecteur : Lecteur 2.")
            return
        from .common import choose
        i = others[0] if len(others) == 1 else choose(self, "Sur quel lecteur ?", [(self.app.hub.label(k), k) for k in others])
        if i is None:
            return
        q = self.app.queues[i]
        q.add(paths) if add else q.set(paths)
        self.app.toast.show_msg(f"{len(paths)} titre(s) {'ajouté(s) à' if add else 'lancé(s) sur'} {self.app.hub.label(i)}")
        self.app.source_changed.emit()

    # --- navigation
    def set_mode(self, mode):
        self.stack = [(mode, None)]; self.refresh()

    def open(self, mode, arg):
        self.stack.append((mode, arg)); self.refresh()

    def back(self):
        if len(self.stack) > 1:
            self.stack.pop(); self.refresh()

    def search(self):
        t = Keyboard.get(self, "Rechercher (titre, artiste, album, genre)", self.filter)
        if t is not None:
            self.filter = t.strip()
            if self.filter:
                self.stack = [("tracks", None)]
            self.refresh()

    def refresh(self):
        mode, arg = self.stack[-1]
        for k, b in self.seg.items():
            b.setChecked(k == self.stack[0][0])
        self.b_back.setEnabled(len(self.stack) > 1)
        self.list.clear(); self._icon_jobs = []
        lib = self.app.lib
        show_play = False
        if mode == "artists":
            arts = lib.artists()
            self.crumb.setText(f"{len(arts)} artistes")
            for a in arts:
                n = len(lib.albums(a))
                self.list.add(a, ("artist", a), sub=f"{n} album{'s' if n > 1 else ''}")
        elif mode == "albums":
            albums = lib.albums(arg)
            self.crumb.setText(arg or f"{len(albums)} albums")
            if arg:
                self.list.add("🎵  Tous les titres de l'artiste", ("artist_tracks", arg), color="#58a6ff")
            for al, y, n in albums:
                it = self.list.add(al, ("album", (arg, al)), sub=" · ".join(x for x in (y, f"{n} titres") if x))
                self._icon_jobs.append((it, arg, al))
            self.icon_timer.start(30)
        elif mode in ("tracks", "album_tracks", "artist_tracks", "playlist"):
            if mode == "album_tracks":
                rows = lib.tracks(artist=arg[0], album=arg[1], order="album"); title = arg[1]
            elif mode == "artist_tracks":
                rows = lib.tracks(artist=arg, order="album"); title = arg
            elif mode == "playlist":
                by = {r["path"]: r for r in lib.tracks()}
                rows = [by.get(p) or {"path": p, "title": Path(p).stem, "artist": "", "duration": 0}
                        for p in lib.playlist_paths(arg)]
                title = dict(lib.playlists()).get(arg, "Playlist")
            else:
                rows = lib.tracks(search=self.filter or None); title = (f"« {self.filter} »" if self.filter else "Tous les titres")
            self.rows = rows
            self.crumb.setText(f"{title} — {len(rows)} titres")
            cur = self.app.queue.current()
            for r in rows:
                num = f"{r['track']:>2}. " if mode == "album_tracks" and r.get("track") else ""
                sub = " · ".join(x for x in (r.get("artist"), r.get("album") if mode != "album_tracks" else None,
                                              fmt_time(r.get("duration"))) if x)
                self.list.add(num + (r.get("title") or Path(r["path"]).stem), ("track", r["path"]), sub=sub,
                              color="#58a6ff" if r["path"] == cur else None)
            show_play = bool(rows)
            if self.filter and mode == "tracks":
                self.list.insertItem(0, "✕  Effacer la recherche"); self.list.item(0).setData(Qt.UserRole, ("clear", None))
        elif mode == "playlists":
            pls = lib.playlists()
            self.crumb.setText(f"{len(pls)} playlists")
            self.list.add("＋  Nouvelle playlist", ("new_pl", None), color="#58a6ff")
            for pid, name in pls:
                self.list.add(name, ("playlist", pid), sub=f"{len(lib.playlist_paths(pid))} titres")
        self.b_play_all.setVisible(show_play); self.b_shuffle_all.setVisible(show_play)

    def _load_icons(self):
        for _ in range(6):
            if not self._icon_jobs:
                self.icon_timer.stop(); return
            it, artist, album = self._icon_jobs.pop(0)
            rows = self.app.lib.tracks(artist=artist, album=album)
            if rows:
                it.setIcon(QIcon(cover_pixmap(rows[0]["path"], px(48))))

    # --- actions
    def tapped(self, it):
        kind, val = it.data(Qt.UserRole) or (None, None)
        if kind == "artist":
            self.open("albums", val)
        elif kind == "album":
            self.open("album_tracks", val)
        elif kind == "artist_tracks":
            self.open("artist_tracks", val)
        elif kind == "playlist":
            self.open("playlist", val)
        elif kind == "new_pl":
            self.new_playlist()
        elif kind == "clear":
            self.filter = ""; self.refresh()
        elif kind == "track":
            paths = [r["path"] for r in self.rows]
            self.app.queue.set(paths, paths.index(val))
            self.app.show_page("lecture")

    def long_pressed(self, it):
        kind, val = it.data(Qt.UserRole) or (None, None)
        lib, q = self.app.lib, self.app.queue
        if kind == "track":
            t = read_tags(val)
            menu(self, t.title or Path(val).name, [
                ("▶  Lire maintenant", lambda: q.set([val])),
                ("⏭  Lire ensuite", lambda: (q.add([val], next_=True), self.app.toast.show_msg("Ajouté après le titre en cours"))),
                ("➕  Ajouter à la file", lambda: (q.add([val]), self.app.toast.show_msg("Ajouté à la file"))),
                ("📃  Ajouter à une playlist…", lambda: self.add_to_playlist([val])),
                ("🎧  Lire sur un autre lecteur (autre sortie)", lambda: self.play_elsewhere([val])),
                ("🎵  Identifier / compléter les infos", lambda: self.app.identify([val])),
                ("✕  Retirer de la bibliothèque (le fichier reste)", lambda: (lib.remove(val), self.refresh())),
            ] + ([("➖  Retirer de cette playlist", lambda: self.remove_from_playlist(it))]
                 if self.stack[-1][0] == "playlist" else []))
        elif kind in ("artist", "album", "artist_tracks"):
            rows = (lib.tracks(artist=val, order="album") if kind != "album"
                    else lib.tracks(artist=val[0], album=val[1], order="album"))
            paths = [r["path"] for r in rows]
            menu(self, it.text().split("\n")[0], [
                ("▶  Lire", lambda: q.set(paths)),
                ("🔀  Lire en aléatoire", lambda: (q.set_shuffle(True), q.set(paths))),
                ("➕  Ajouter à la file", lambda: q.add(paths)),
                ("📃  Ajouter à une playlist…", lambda: self.add_to_playlist(paths)),
                ("🎧  Lire sur un autre lecteur (autre sortie)", lambda: self.play_elsewhere(paths)),
                ("🎵  Identifier / compléter les infos", lambda: self.app.identify(paths)),
            ])
        elif kind == "playlist":
            paths = lib.playlist_paths(val)
            name = dict(lib.playlists()).get(val, "")
            menu(self, name, [
                ("▶  Lire", lambda: q.set(paths)),
                ("🔀  Lire en aléatoire", lambda: (q.set_shuffle(True), q.set(paths))),
                ("🎧  Lire sur un autre lecteur (autre sortie)", lambda: self.play_elsewhere(paths)),
                ("✏  Renommer", lambda: self.rename_playlist(val, name)),
                ("🗑  Supprimer", lambda: ask(self, "Supprimer", f"Supprimer la playlist « {name} » ?") == 0
                 and (lib.delete_playlist(val), self.refresh())),
            ])

    def play_all(self):
        self.app.queue.set([r["path"] for r in self.rows]); self.app.show_page("lecture")

    def shuffle_all(self):
        self.app.queue.set_shuffle(True); self.play_all()

    def new_playlist(self, paths=None):
        name = Keyboard.get(self, "Nom de la nouvelle playlist")
        if name and name.strip():
            pid = self.app.lib.create_playlist(name.strip())
            if paths:
                self.app.lib.add_to_playlist(pid, paths)
            self.refresh()
            return pid

    def add_to_playlist(self, paths):
        opts = [("＋ Nouvelle playlist…", "new")] + [(n, pid) for pid, n in self.app.lib.playlists()]
        pid = choose(self, "Ajouter à la playlist", opts)
        if pid == "new":
            self.new_playlist(paths)
        elif pid is not None:
            self.app.lib.add_to_playlist(pid, paths)
        if pid is not None:
            self.app.toast.show_msg(f"{len(paths)} titre(s) ajouté(s)")

    def rename_playlist(self, pid, old):
        name = Keyboard.get(self, "Nouveau nom", old)
        if name and name.strip():
            with self.app.lib._lock:
                self.app.lib.db.execute("UPDATE playlists SET name=? WHERE id=?", (name.strip(), pid))
                self.app.lib.db.commit()
            self.refresh()

    def remove_from_playlist(self, it):
        pid = self.stack[-1][1]
        row = self.list.row(it)
        paths = self.app.lib.playlist_paths(pid)
        if 0 <= row < len(paths):
            paths.pop(row); self.app.lib.set_playlist(pid, paths); self.refresh()


# =================================================================== File de lecture
class QueuePage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self); lay.setContentsMargins(px(8), px(6), px(8), 0)
        top = QHBoxLayout()
        self.head = label("File de lecture", "h2", wrap=True); top.addWidget(self.head, 1)
        from PySide6.QtWidgets import QSizePolicy
        self.head.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        top.addWidget(button("🔀 Mélanger", lambda: self.app.queue.set_shuffle(True)))
        top.addWidget(button("💾 En playlist", self.save))
        top.addWidget(button("🗑 Vider", self.clear))
        lay.addLayout(top)
        self.list = TouchList(); lay.addWidget(self.list, 1)
        self.list.tapped.connect(lambda it: self.app.queue.play_at(self.list.row(it)))
        self.list.long_pressed.connect(self.long)
        for q in app.queues:
            q.changed.connect(self.refresh); q.track_changed.connect(lambda _: self.refresh())
        app.source_changed.connect(self.refresh)

    def refresh(self):
        q = self.app.queue
        self.list.clear()
        by = {r["path"]: r for r in self.app.lib.tracks()}
        for i, p in enumerate(q.paths()):
            r = by.get(p) or {"title": Path(p).stem, "artist": ""}
            cur = i == q.pos
            self.list.add(("▶  " if cur else "     ") + (r.get("title") or Path(p).stem), i,
                          sub="     " + (r.get("artist") or ""), color="#58a6ff" if cur else None)
        multi = len(self.app.hub.used_sources()) > 1
        self.head.setText(f"File{' — ' + self.app.hub.label(self.app.cur_src, True) if multi else ' de lecture'} — {len(q.order)} titres")
        if 0 <= q.pos < self.list.count():
            self.list.scrollToItem(self.list.item(q.pos))

    def long(self, it):
        i = self.list.row(it)
        menu(self, it.text().split("\n")[0].strip("▶ "), [
            ("▶  Lire", lambda: self.app.queue.play_at(i)),
            ("➖  Retirer de la file", lambda: self.app.queue.remove_at(i)),
        ])

    def save(self):
        paths = self.app.queue.paths()
        if not paths:
            return
        name = Keyboard.get(self, "Enregistrer la file comme playlist", "Ma sélection")
        if name and name.strip():
            pid = self.app.lib.create_playlist(name.strip()); self.app.lib.set_playlist(pid, paths)
            self.app.toast.show_msg(f"Playlist « {name.strip()} » créée")

    def clear(self):
        if ask(self, "Vider la file", "Garder seulement le titre en cours ?") == 0:
            self.app.queue.clear()
