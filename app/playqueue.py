"""File de lecture d'un lecteur (utilisée par la version tactile et par les lecteurs 2 et 3)."""
import os
import random
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .config import settings
from .tags import read_tags


class PlayQueue(QObject):
    """File de lecture d'un lecteur : ordre, aléatoire, répétition, titre suivant.
    `key` distingue les réglages de chaque lecteur ("" = principal, "_2", "_3")."""
    changed = Signal()
    track_changed = Signal(str)
    error = Signal(str)

    def __init__(self, player, lib, key=""):
        super().__init__()
        self.player, self.lib, self.key = player, lib, key
        self.queue: list[str] = []
        self.order: list[int] = []
        self.pos = -1
        self.shuffle = bool(settings.get("shuffle" + key))

    @property
    def repeat(self):
        return settings.get("repeat" + self.key, "none")

    def paths(self):
        return [self.queue[i] for i in self.order]

    def current(self):
        return self.queue[self.order[self.pos]] if 0 <= self.pos < len(self.order) else None

    def _make_order(self, first=None):
        idx = list(range(len(self.queue)))
        if self.shuffle:
            random.shuffle(idx)
            if first is not None:
                idx.remove(first); idx.insert(0, first)
            self.order = idx
            return 0
        self.order = idx
        return first or 0

    def set(self, paths, start=0):
        if not paths:
            return
        self.queue = list(paths)
        self.pos = self._make_order(start)
        self.changed.emit(); self._play()

    def add(self, paths, next_=False):
        start = len(self.queue)
        self.queue += list(paths)
        new = list(range(start, len(self.queue)))
        if next_ and self.pos >= 0:
            self.order[self.pos + 1:self.pos + 1] = new
        else:
            if self.shuffle:
                random.shuffle(new)
            self.order += new
        self.changed.emit()
        if self.pos < 0:
            self.pos = 0; self._play()

    def remove_at(self, pos):
        if 0 <= pos < len(self.order) and pos != self.pos:
            self.order.pop(pos)
            if pos < self.pos:
                self.pos -= 1
            self.changed.emit()

    def clear(self):
        cur = self.current()
        self.queue = [cur] if cur else []
        self.order = [0] if cur else []
        self.pos = 0 if cur else -1
        self.changed.emit()

    def play_at(self, pos):
        if 0 <= pos < len(self.order):
            self.pos = pos; self._play()

    def _play(self):
        path = self.current()
        if not path:
            return
        if not os.path.exists(path):
            self.error.emit(f"Fichier introuvable : {Path(path).name}")
            return
        try:
            self.player.load(path, read_tags(path).duration)
        except Exception as e:
            self.error.emit(f"Lecture impossible : {e}")
            return
        self.lib.count_play(path)
        self.track_changed.emit(path)

    def next(self, auto=False):
        if not self.order:
            return
        rep = self.repeat
        if auto and rep == "one":
            self._play(); return
        if self.pos + 1 < len(self.order):
            self.pos += 1
        elif rep == "all" or not auto:
            self.pos = self._make_order() if self.shuffle else 0
            self.changed.emit()
        else:
            self.player.stop(); return
        self._play()

    def prev(self):
        if self.player.position > 3:
            self.player.seek(0); return
        if self.pos > 0:
            self.pos -= 1; self._play()

    def toggle_play(self):
        if not self.player.path:
            return False
        try:
            self.player.toggle()
        except Exception as e:
            self.error.emit(str(e))
        return True

    def set_shuffle(self, on):
        self.shuffle = on; settings["shuffle" + self.key] = on
        if self.queue:
            cur = self.order[self.pos] if 0 <= self.pos < len(self.order) else None
            idx = list(range(len(self.queue)))
            if on:
                random.shuffle(idx)
                if cur is not None:
                    idx.remove(cur); idx.insert(0, cur)
                self.pos = 0
            else:
                self.pos = cur or 0
            self.order = idx
            self.changed.emit()

    def cycle_repeat(self):
        settings["repeat" + self.key] = {"none": "all", "all": "one", "one": "none"}[self.repeat]
        return self.repeat
