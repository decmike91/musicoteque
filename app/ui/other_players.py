"""Panneau « Autres lecteurs » (version Windows / bureau) : lecteurs 2 et 3, chacun diffusant
sa propre musique sur les sorties qui lui sont rattachées (casque Bluetooth, autre pièce…)."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QToolButton, QSlider,
                               QMenu, QPushButton)

from ..config import settings
from ..tags import read_tags, read_cover
from .widgets import VUMeter, fmt_time


class SourceBox(QGroupBox):
    def __init__(self, hub, queue, index, parent=None):
        super().__init__(parent)
        self.hub, self.q, self.i = hub, queue, index
        self.p = hub.players[index]
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.cover = QLabel(); self.cover.setFixedSize(48, 48)
        self.cover.setStyleSheet("background:#0d1117;border-radius:6px")
        info = QVBoxLayout()
        self.title = QLabel("Aucun titre"); self.title.setStyleSheet("font-weight:600")
        self.artist = QLabel(""); self.artist.setStyleSheet("color:#8b949e")
        for l in (self.title, self.artist):
            l.setMinimumWidth(60)
        info.addWidget(self.title); info.addWidget(self.artist)
        top.addWidget(self.cover); top.addLayout(info, 1)
        lay.addLayout(top)
        btns = QHBoxLayout()
        self.b_shuffle = QToolButton(); self.b_shuffle.setText("🔀"); self.b_shuffle.setCheckable(True)
        self.b_shuffle.setChecked(queue.shuffle); self.b_shuffle.toggled.connect(queue.set_shuffle)
        self.b_prev = QToolButton(); self.b_prev.setText("⏮"); self.b_prev.clicked.connect(queue.prev)
        self.b_play = QToolButton(); self.b_play.setText("▶"); self.b_play.clicked.connect(self.toggle)
        self.b_next = QToolButton(); self.b_next.setText("⏭"); self.b_next.clicked.connect(queue.next)
        self.b_stop = QToolButton(); self.b_stop.setText("⏹"); self.b_stop.clicked.connect(self.p.stop)
        self.b_queue = QToolButton(); self.b_queue.setText("☰ File"); self.b_queue.setPopupMode(QToolButton.InstantPopup)
        self.qmenu = QMenu(self.b_queue); self.b_queue.setMenu(self.qmenu)
        self.qmenu.aboutToShow.connect(self.fill_menu)
        for b in (self.b_shuffle, self.b_prev, self.b_play, self.b_next, self.b_stop):
            btns.addWidget(b)
        btns.addStretch(); btns.addWidget(self.b_queue)
        lay.addLayout(btns)
        seek = QHBoxLayout()
        self.t_pos = QLabel("0:00")
        self.seek = QSlider(Qt.Horizontal); self.seek.setRange(0, 1000)
        self.seek.sliderReleased.connect(lambda: self.p.seek(self.seek.value() / 1000 * self.p.duration))
        seek.addWidget(self.t_pos); seek.addWidget(self.seek, 1)
        lay.addLayout(seek)
        vol = QHBoxLayout(); vol.addWidget(QLabel("🔊"))
        self.vol = QSlider(Qt.Horizontal); self.vol.setRange(0, 100)
        self.vol.setValue(int(settings.get(f"volume_{index + 1}", 0.8) * 100))
        self.vol.valueChanged.connect(self.set_volume); self.set_volume(self.vol.value())
        vol.addWidget(self.vol, 1)
        self.vu = VUMeter(); self.vu.setMinimumSize(100, 28); self.vu.setMaximumHeight(34)
        vol.addWidget(self.vu, 1)
        lay.addLayout(vol)
        queue.track_changed.connect(self.show_track)

    def set_volume(self, v):
        self.p.volume = v / 100; settings[f"volume_{self.i + 1}"] = v / 100

    def toggle(self):
        if not self.q.toggle_play():
            self.window().statusBar().showMessage(
                f"{self.hub.label(self.i, True)} : faites un clic droit sur des titres ▸ « Lire sur un autre lecteur »", 6000)

    def show_track(self, path):
        t = read_tags(path)
        self.title.setText(t.title or Path(path).stem); self.artist.setText(t.artist or "")
        pm = QPixmap(); data = read_cover(path)
        if data and pm.loadFromData(data):
            self.cover.setPixmap(pm.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.cover.clear()

    def fill_menu(self):
        self.qmenu.clear()
        paths = self.q.paths()
        if not paths:
            self.qmenu.addAction("(file vide)").setEnabled(False)
        for k, pth in enumerate(paths[:60]):
            t = read_tags(pth)
            a = self.qmenu.addAction(("▶ " if k == self.q.pos else "   ") + f"{t.artist or '?'} — {t.title or Path(pth).stem}")
            a.triggered.connect(lambda _=False, k=k: self.q.play_at(k))
        if paths:
            self.qmenu.addSeparator()
            self.qmenu.addAction("Vider la file (garder le titre en cours)", self.q.clear)

    def tick(self):
        p = self.p
        self.setTitle(self.hub.label(self.i))
        self.b_play.setText("⏸" if p.playing else "▶")
        if p.duration and not self.seek.isSliderDown():
            self.seek.setValue(int(p.position / p.duration * 1000))
        self.t_pos.setText(f"{fmt_time(p.position)} / {fmt_time(p.duration)}")
        self.vu.set_levels(*(p.levels if p.playing else (0, 0, 0, 0)))
        self.b_queue.setText(f"☰ File ({len(self.q.order)})")


class OtherPlayersPanel(QWidget):
    def __init__(self, hub, queues, parent=None):
        super().__init__(parent)
        self.hub, self.queues = hub, queues
        lay = QVBoxLayout(self); lay.setContentsMargins(6, 6, 6, 6)
        self.help = QLabel(
            "Écoutez <b>autre chose sur une autre sortie</b> (casque Bluetooth, autre pièce…) :<br>"
            "1. panneau <b>Son</b> ▸ <b>＋ Ajouter une sortie</b>, choisissez le périphérique ;<br>"
            "2. dans <b>Lecteur</b>, choisissez <b>Lecteur 2</b> ;<br>"
            "3. clic droit sur des titres ▸ <b>Lire sur un autre lecteur</b>.")
        self.help.setWordWrap(True); self.help.setStyleSheet("color:#8b949e")
        lay.addWidget(self.help)
        self.boxes = {i: SourceBox(hub, q, i) for i, q in queues.items()}
        for b in self.boxes.values():
            lay.addWidget(b)
        lay.addStretch()
        self.refresh()

    def refresh(self):
        used = self.hub.used_sources()
        for i, b in self.boxes.items():
            b.setVisible(i in used)
        self.help.setVisible(not any(i in used for i in self.boxes))

    def tick(self):
        for i, b in self.boxes.items():
            if b.isVisible():
                b.tick()
