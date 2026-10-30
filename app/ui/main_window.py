"""Fenêtre principale : bibliothèque (artistes / albums / playlists), lecteur, effets."""
import os
import random
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QAction, QPixmap, QKeySequence, QShortcut
from ..help import open_help, pdf_path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget, QTreeWidgetItem,
    QTableView, QLineEdit, QComboBox, QLabel, QPushButton, QSlider, QToolButton, QMenu,
    QFileDialog, QMessageBox, QInputDialog, QAbstractItemView, QDockWidget, QStatusBar, QStyle,
    QProgressBar, QCheckBox,
)

from ..config import settings, APP_NAME, tool
from ..library import Library
from ..tags import read_tags, read_cover
from ..audio_engine import AudioHub, MAX_SOURCES
from ..playqueue import PlayQueue
from .other_players import OtherPlayersPanel
from .widgets import VUMeter, Knob, TrackModel, Worker, fmt_time, screen_geometry, scrolled
from . import dialogs
from .sound_panel import SoundPanel

STYLE = """
* { font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow, QDialog, QWidget { background: #0d1117; color: #e6edf3; }
QTreeWidget, QTableView, QListWidget, QPlainTextEdit, QTableWidget {
  background: #161b22; border: 1px solid #30363d; alternate-background-color: #1b2129;
  selection-background-color: #1f6feb; }
QHeaderView::section { background: #21262d; color: #8b949e; border: none; padding: 5px; }
QLineEdit, QComboBox, QSpinBox { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 5px; }
QPushButton, QToolButton { background: #21262d; border: 1px solid #30363d; border-radius: 6px; padding: 6px 12px; }
QPushButton:hover, QToolButton:hover { background: #30363d; }
QPushButton:disabled { color: #484f58; }
QToolButton:checked { background: #1f6feb; border-color: #388bfd; }
QPushButton#play { background: #238636; border-radius: 22px; min-width: 44px; min-height: 44px; font-size: 18px; }
QSlider::groove:horizontal { height: 6px; background: #30363d; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #1f6feb; border-radius: 3px; }
QSlider::handle:horizontal { background: #e6edf3; width: 14px; margin: -5px 0; border-radius: 7px; }
QSlider::groove:vertical { width: 6px; background: #30363d; border-radius: 3px; }
QSlider::add-page:vertical { background: #1f6feb; border-radius: 3px; }
QSlider::handle:vertical { background: #e6edf3; height: 14px; margin: 0 -5px; border-radius: 7px; }
QGroupBox { border: 1px solid #30363d; border-radius: 8px; margin-top: 12px; padding: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #8b949e; }
QMenuBar, QMenu { background: #161b22; } QMenu::item:selected, QMenuBar::item:selected { background: #1f6feb; }
QProgressBar { border: 1px solid #30363d; border-radius: 5px; text-align: center; }
QProgressBar::chunk { background: #1f6feb; }
QDial { background: #21262d; }
QDockWidget::title { background: #161b22; padding: 6px; }
QCheckBox::indicator, QRadioButton::indicator { width: 14px; height: 14px; border: 1px solid #6e7681;
  background: #0d1117; border-radius: 3px; }
QRadioButton::indicator { border-radius: 8px; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked { background: #1f6feb; border-color: #58a6ff; }
"""

NODE_ALL, NODE_ARTIST, NODE_ALBUM, NODE_INCOMPLETE, NODE_PLAYLIST, NODE_QUEUE = range(6)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        g = screen_geometry()
        self.small_screen = g.height() < 820 or g.width() < 1300
        # pochette : plus petite sur les petits écrans
        self.cover_size = 260 if g.height() >= 1000 else max(140, int(g.height() * 0.22))
        self.setStyleSheet(STYLE)
        self.lib = Library()
        self.hub = AudioHub()
        self.player = self.hub.main            # lecteur principal
        # lecteurs 2 et 3 : chacun sa file de lecture, pour d'autres sorties (casque Bluetooth…)
        self.queues = {i: PlayQueue(self.hub.players[i], self.lib, f"_{i + 1}") for i in range(1, MAX_SOURCES)}
        for q in self.queues.values():
            q.error.connect(lambda m: self.statusBar().showMessage(m, 6000))
        self.queue: list[str] = []
        self.order: list[int] = []
        self.qpos = -1
        self.current_node = (NODE_ALL, None)
        self.scan_worker = None

        self._build_menu()
        self._build_central()
        self._build_player_bar()
        self._build_effects_dock()
        self.setStatusBar(QStatusBar())
        self.scan_bar = QProgressBar(); self.scan_bar.setMaximumWidth(260); self.scan_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.scan_bar)

        self.timer = QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(33)
        self._place_window()
        self.refresh_tree(); self.refresh_tracks()
        if not tool("ffmpeg"):
            QTimer.singleShot(500, lambda: QMessageBox.warning(
                self, APP_NAME, "ffmpeg est introuvable : la lecture et les conversions ne fonctionneront pas.\n"
                                "Lancez installer.bat pour installer les outils."))
        elif self.lib.stats()["n"] == 0:
            QTimer.singleShot(400, self.welcome)

    # ------------------------------------------------------------------ taille de la fenêtre
    def _place_window(self):
        """Adapte la fenêtre à l'écran : taille enregistrée si elle tient, sinon 95 % de l'écran."""
        g = screen_geometry(self)
        restored = False
        try:
            import base64
            geo, state = settings.get("win_geometry"), settings.get("win_state")
            if geo:
                restored = self.restoreGeometry(base64.b64decode(geo))
            if state:
                self.restoreState(base64.b64decode(state))
        except Exception:
            restored = False
        if not restored or self.width() > g.width() or self.height() > g.height():
            w, h = min(1500, int(g.width() * 0.95)), min(980, int(g.height() * 0.93))
            self.resize(w, h)
            self.move(g.x() + (g.width() - w) // 2, g.y() + (g.height() - h) // 2)
            self.start_maximized = self.small_screen
            # panneau Son : environ 40 % de la hauteur (masqué au départ sur les petits écrans)
            QTimer.singleShot(0, lambda: self.resizeDocks([self.fx_dock], [int(h * 0.45)], Qt.Vertical))
            if self.small_screen:
                self.fx_dock.hide()
        else:
            self.start_maximized = bool(settings.get("win_maximized"))

    def _dock_shown(self, visible):
        """Sur un petit écran, le panneau Son prend la majeure partie de la hauteur quand on l'ouvre."""
        if visible and self.small_screen and not self.fx_dock.isFloating():
            QTimer.singleShot(0, lambda: self.resizeDocks([self.fx_dock], [int(self.height() * 0.62)], Qt.Vertical))

    def show_adapted(self):
        self.showMaximized() if self.start_maximized else self.show()

    # ------------------------------------------------------------------ construction
    def _build_menu(self):
        mb = self.menuBar()
        m = mb.addMenu("&Fichier")
        self._act(m, "Ajouter un dossier à la bibliothèque…", self.add_folder, "Ctrl+O")
        self._act(m, "Ajouter des fichiers…", self.add_files)
        self._act(m, "Actualiser la bibliothèque", self.rescan, "F5")
        m.addSeparator()
        self._act(m, "Paramètres…", self.open_settings)
        m.addSeparator(); self._act(m, "Quitter", self.close, "Ctrl+Q")
        m = mb.addMenu("&Ranger")
        self._act(m, "Ranger / classer un emplacement (disque, clé USB)…", self.organize, "Ctrl+R")
        self._act(m, "Ranger ma bibliothèque", lambda: self.organize(settings["library_root"]))
        self._act(m, "Supprimer les doublons et transformer les WAV / OGG / WMA en MP3 (bibliothèque)…",
                  lambda: self.organize(settings["library_root"]))
        m = mb.addMenu("&Identifier")
        self._act(m, "Identifier la sélection (empreinte audio)…", self.identify_selected, "Ctrl+I")
        self._act(m, "Compléter automatiquement tous les titres incomplets", self.identify_all_incomplete)
        self._act(m, "Modifier les informations de la sélection…", self.edit_tags, "Ctrl+E")
        m = mb.addMenu("&Convertir")
        self._act(m, "CD audio → MP3…", self.open_cd)
        self._act(m, "Lien YouTube → MP3…", self.open_youtube, "Ctrl+Y")
        m = mb.addMenu("&Playlists")
        self._act(m, "Nouvelle playlist…", self.new_playlist, "Ctrl+N")
        self._act(m, "Importer une playlist (M3U)…", self.import_m3u)
        self._act(m, "Exporter la playlist affichée (M3U)…", self.export_m3u)
        m = mb.addMenu("&Lecture")
        self._act(m, "Lecture / Pause", self.play_pause, "Space")
        self._act(m, "Suivant", self.next_track, "Ctrl+Right")
        self._act(m, "Précédent", self.prev_track, "Ctrl+Left")
        m = mb.addMenu("&Son")
        self._act(m, "Afficher / masquer le panneau Son (sorties, profils, égaliseur, audiogramme)",
                  lambda: self.fx_dock.setVisible(not self.fx_dock.isVisible()), "Ctrl+G")
        self._act(m, "Ajouter une sortie audio (même musique)", lambda: (self.fx_dock.show(), self.sound.add_zone()))
        self._act(m, "Ajouter un lecteur indépendant (Lecteur 2 / Lecteur 3)", lambda: (self.fx_dock.show(), self.sound.add_player()))
        self._act(m, "Afficher les autres lecteurs (autre musique sur une autre sortie)",
                  lambda: (self.others_dock.show(), self.others.refresh()))
        self._act(m, "Audiogramme de la sortie affichée", lambda: self._sound_tab(1))
        self._act(m, "Test auditif…", lambda: (self._sound_tab(1), self.sound.tabs.currentWidget().hearing_test()))
        m = mb.addMenu("&Aide")
        self._act(m, "Manuel d'utilisation", lambda: open_help(self), "F1")
        self._act(m, "Ranger et classer : mode d'emploi", lambda: open_help(self, "ranger"))
        self._act(m, "Réglages du son et profils", lambda: open_help(self, "son"))
        self._act(m, "Audiogramme et test auditif", lambda: open_help(self, "audiogramme"))
        self._act(m, "Plusieurs sorties et lecteurs", lambda: open_help(self, "sorties"))
        self._act(m, "Dépannage et raccourcis clavier", lambda: open_help(self, "depannage"))
        m.addSeparator()
        self._act(m, "Manuel à imprimer (PDF)", self.open_pdf_manual)
        self._act(m, "À propos de Musicothèque", self.about)

    def open_pdf_manual(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        p = pdf_path()
        if p.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
        else:
            QMessageBox.information(self, "Manuel", "Le manuel PDF n'est pas installé.")

    def about(self):
        QMessageBox.about(self, "À propos de Musicothèque",
                          "<b>Musicothèque</b><br>Bibliothèque, rangement, identification, conversion "
                          "et lecture de musique.<br><br>Aide : touche F1.<br>"
                          "<a href='https://github.com/decmike91/musicoteque'>github.com/decmike91/musicoteque</a>")

    def _act(self, menu, text, fn, sc=None):
        a = QAction(text, self); a.triggered.connect(fn)
        if sc:
            a.setShortcut(QKeySequence(sc))
            a.setShortcutContext(Qt.WindowShortcut)
        menu.addAction(a); return a

    def _build_central(self):
        split = QSplitter()
        # arbre
        self.tree = QTreeWidget(); self.tree.setHeaderHidden(True); self.tree.setMinimumWidth(170)
        self.tree.itemClicked.connect(self.tree_clicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.tree_menu)
        split.addWidget(self.tree)
        # liste
        mid = QWidget(); ml = QVBoxLayout(mid); ml.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("🔍  Rechercher un titre, un artiste, un album, un genre…")
        self.search.textChanged.connect(lambda: self.search_timer.start(250))
        self.search_timer = QTimer(self); self.search_timer.setSingleShot(True); self.search_timer.timeout.connect(self.refresh_tracks)
        self.sort = QComboBox(); self.sort.addItems(["Trier par artiste", "par album", "par titre", "par année", "les plus écoutés"])
        self.sort.currentIndexChanged.connect(self.refresh_tracks)
        b_org = QPushButton("🗂  Ranger un emplacement"); b_org.clicked.connect(self.organize)
        b_id = QPushButton("🎵  Identifier"); b_id.clicked.connect(self.identify_selected)
        bar.addWidget(self.search, 1); bar.addWidget(self.sort); bar.addWidget(b_id); bar.addWidget(b_org)
        ml.addLayout(bar)
        self.title_lbl = QLabel(); self.title_lbl.setStyleSheet("font-size:18px;font-weight:600;padding:4px")
        ml.addWidget(self.title_lbl)
        self.model = TrackModel()
        self.table = QTableView(); self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True); self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False); self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setStretchLastSection(False)
        for c, w in enumerate([45, 280, 200, 220, 60, 110, 65, 65, 65]):
            self.table.setColumnWidth(c, w)
        self.table.doubleClicked.connect(self.play_from_table)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.table_menu)
        self.table.setDragEnabled(True)
        ml.addWidget(self.table, 1)
        split.addWidget(mid)
        # panneau « en cours »
        cs = self.cover_size
        right = QWidget(); rl = QVBoxLayout(right); right.setMinimumWidth(cs + 20); right.setMaximumWidth(320)
        self.cover = QLabel(); self.cover.setFixedSize(cs, cs); self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setStyleSheet("background:#161b22;border-radius:10px;color:#484f58;font-size:60px"); self.cover.setText("♪")
        self.np_title = QLabel(""); self.np_title.setWordWrap(True); self.np_title.setStyleSheet("font-size:16px;font-weight:600")
        self.np_info = QLabel(""); self.np_info.setWordWrap(True); self.np_info.setStyleSheet("color:#8b949e")
        rl.addWidget(self.cover, 0, Qt.AlignHCenter); rl.addWidget(self.np_title); rl.addWidget(self.np_info)
        rl.addWidget(QLabel("File de lecture"))
        from PySide6.QtWidgets import QListWidget
        self.queue_list = QListWidget(); self.queue_list.itemDoubleClicked.connect(lambda it: self.play_index(self.queue_list.row(it)))
        self.queue_list.setMinimumHeight(40)
        rl.addWidget(self.queue_list, 1)
        split.addWidget(right)
        split.setSizes([260, 900, 280])
        self.setCentralWidget(split)

    def _build_player_bar(self):
        bar = QWidget(); bar.setObjectName("pbar"); bar.setAttribute(Qt.WA_StyledBackground, True)
        bar.setStyleSheet("#pbar{background:#161b22;border-top:1px solid #30363d} #pbar QLabel{background:transparent}")
        bar.setFixedHeight(96)
        lay = QHBoxLayout(bar); lay.setContentsMargins(12, 6, 12, 6)
        self.mini_cover = QLabel(); self.mini_cover.setFixedSize(56, 56)
        self.mini_title = QLabel("Aucun titre"); self.mini_title.setStyleSheet("font-weight:600")
        self.mini_artist = QLabel(""); self.mini_artist.setStyleSheet("color:#8b949e")
        info = QVBoxLayout(); info.addWidget(self.mini_title); info.addWidget(self.mini_artist)
        iw = QWidget(); iw.setLayout(info); iw.setMinimumWidth(110); iw.setMaximumWidth(230)
        lay.addWidget(self.mini_cover); lay.addWidget(iw)

        center = QVBoxLayout()
        btns = QHBoxLayout(); btns.addStretch()
        self.b_shuffle = QToolButton(); self.b_shuffle.setText("🔀"); self.b_shuffle.setCheckable(True)
        self.b_shuffle.setToolTip("Lecture aléatoire"); self.b_shuffle.setChecked(settings["shuffle"])
        self.b_shuffle.toggled.connect(self.set_shuffle)
        self.b_prev = QToolButton(); self.b_prev.setText("⏮"); self.b_prev.clicked.connect(self.prev_track)
        self.b_play = QPushButton("▶"); self.b_play.setObjectName("play"); self.b_play.clicked.connect(self.play_pause)
        self.b_next = QToolButton(); self.b_next.setText("⏭"); self.b_next.clicked.connect(self.next_track)
        self.b_stop = QToolButton(); self.b_stop.setText("⏹"); self.b_stop.clicked.connect(self.stop)
        self.b_repeat = QToolButton(); self.b_repeat.setToolTip("Répéter : non / tout / un titre")
        self.b_repeat.clicked.connect(self.cycle_repeat); self._update_repeat_btn()
        for b in (self.b_shuffle, self.b_prev, self.b_play, self.b_next, self.b_stop, self.b_repeat):
            btns.addWidget(b)
        btns.addStretch(); center.addLayout(btns)
        seek = QHBoxLayout()
        self.t_pos = QLabel("0:00"); self.t_dur = QLabel("0:00")
        self.seek = QSlider(Qt.Horizontal); self.seek.setRange(0, 1000)
        self.seek.sliderReleased.connect(lambda: self.player.seek(self.seek.value() / 1000 * self.player.duration))
        seek.addWidget(self.t_pos); seek.addWidget(self.seek, 1); seek.addWidget(self.t_dur)
        center.addLayout(seek)
        lay.addLayout(center, 1)

        self.vu = VUMeter(); self.vu.setMinimumSize(130, 50); self.vu.setMaximumSize(300, 62)
        lay.addWidget(self.vu)
        self.b_mute = QToolButton(); self.b_mute.setText("🔊"); self.b_mute.setCheckable(True)
        self.b_mute.toggled.connect(self.set_mute)
        lay.addWidget(self.b_mute)
        self.vol = Knob("Volume", 0, 100, int(settings["volume"] * 100), lambda v: f"{v} %")
        self.vol.valueChanged.connect(self.set_volume); self.set_volume(self.vol.value())
        lay.addWidget(self.vol)
        self.b_fx = QPushButton("🎛 Son"); self.b_fx.setCheckable(True); self.b_fx.setChecked(True)
        lay.addWidget(self.b_fx)
        central = QWidget(); cl = QVBoxLayout(central); cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)
        cl.addWidget(self.centralWidget(), 1); cl.addWidget(bar)
        self.setCentralWidget(central)

    def _build_effects_dock(self):
        self.sound = SoundPanel(self.hub)
        self.fx_dock = QDockWidget("Son — sorties audio, profils, égaliseur, ambiance, audiogramme", self)
        self.fx_dock.setObjectName("dock_son")
        self.fx_dock.setWidget(scrolled(self.sound))   # défile si la place manque
        self.addDockWidget(Qt.BottomDockWidgetArea, self.fx_dock)
        self.b_fx.toggled.connect(self.fx_dock.setVisible)
        self.fx_dock.visibilityChanged.connect(self._dock_shown)
        self.fx_dock.visibilityChanged.connect(self.b_fx.setChecked)
        # lecteurs 2 et 3
        self.others = OtherPlayersPanel(self.hub, self.queues)
        self.others_dock = QDockWidget("Autres lecteurs (autres sorties)", self)
        self.others_dock.setObjectName("dock_lecteurs")
        self.others_dock.setWidget(scrolled(self.others))
        self.addDockWidget(Qt.RightDockWidgetArea, self.others_dock)
        self.others_dock.setVisible(len(self.hub.used_sources()) > 1)
        self.sound.sources_changed.connect(self._sources_changed)

    def _sources_changed(self):
        self.others.refresh()
        if len(self.hub.used_sources()) > 1:
            self.others_dock.show()

    def _sound_tab(self, page):
        self.fx_dock.show()
        w = self.sound.tabs.currentWidget()
        if w:
            w.tabs.setCurrentIndex(page)

    # ------------------------------------------------------------------ arbre / liste
    def refresh_tree(self):
        self.tree.clear()
        st = self.lib.stats()
        root = QTreeWidgetItem(self.tree, [f"🎵  Tous les titres ({st['n']})"]); root.setData(0, Qt.UserRole, (NODE_ALL, None))
        art = QTreeWidgetItem(self.tree, ["👤  Artistes"]); art.setData(0, Qt.UserRole, (NODE_ALL, None))
        for a in self.lib.artists():
            it = QTreeWidgetItem(art, [a]); it.setData(0, Qt.UserRole, (NODE_ARTIST, a))
            for al, y, n in self.lib.albums(a):
                sub = QTreeWidgetItem(it, [f"💿 {al}" + (f" ({y})" if y else "")])
                sub.setData(0, Qt.UserRole, (NODE_ALBUM, (a, al)))
        alb = QTreeWidgetItem(self.tree, ["💿  Albums"]); alb.setData(0, Qt.UserRole, (NODE_ALL, None))
        for al, y, n in self.lib.albums():
            it = QTreeWidgetItem(alb, [f"{al}" + (f" ({y})" if y else "") + f"  · {n}"])
            it.setData(0, Qt.UserRole, (NODE_ALBUM, (None, al)))
        inc = QTreeWidgetItem(self.tree, [f"⚠  Infos incomplètes ({st['inc'] or 0})"])
        inc.setData(0, Qt.UserRole, (NODE_INCOMPLETE, None))
        pl = QTreeWidgetItem(self.tree, ["📃  Playlists"]); pl.setData(0, Qt.UserRole, ("playlists", None))
        for pid, name in self.lib.playlists():
            it = QTreeWidgetItem(pl, [name]); it.setData(0, Qt.UserRole, (NODE_PLAYLIST, pid))
        pl.setExpanded(True)
        q = QTreeWidgetItem(self.tree, ["▶  File de lecture"]); q.setData(0, Qt.UserRole, (NODE_QUEUE, None))
        self.statusBar().showMessage(
            f"{st['n']} titres · {st['a'] or 0} artistes · {st['al'] or 0} albums · {fmt_time(st['d'])} de musique")

    def tree_clicked(self, item):
        node = item.data(0, Qt.UserRole)
        if node and node[0] != "playlists":
            self.current_node = node; self.refresh_tracks()

    def refresh_tracks(self):
        kind, val = self.current_node
        order = ["artist", "album", "title", "year", "plays"][self.sort.currentIndex()]
        s = self.search.text().strip() or None
        if kind == NODE_ARTIST:
            rows, title = self.lib.tracks(artist=val, search=s, order="album"), val
        elif kind == NODE_ALBUM:
            rows, title = self.lib.tracks(artist=val[0], album=val[1], search=s, order="album"), val[1]
        elif kind == NODE_INCOMPLETE:
            rows, title = self.lib.tracks(incomplete_only=True, search=s), "Titres aux informations incomplètes"
        elif kind == NODE_PLAYLIST:
            by_path = {r["path"]: r for r in self.lib.tracks()}
            rows = [by_path.get(p) or {"path": p, "title": Path(p).stem} for p in self.lib.playlist_paths(val)]
            title = dict(self.lib.playlists()).get(val, "Playlist")
        elif kind == NODE_QUEUE:
            by_path = {r["path"]: r for r in self.lib.tracks()}
            rows = [by_path.get(p) or read_tags(p).as_dict() for p in self.queue]; title = "File de lecture"
        else:
            rows, title = self.lib.tracks(search=s, order=order), "Tous les titres"
        self.model.set_rows(rows)
        self.title_lbl.setText(f"{title}  <span style='color:#8b949e;font-size:13px'>{len(rows)} titres · "
                               f"{fmt_time(sum((r.get('duration') or 0) for r in rows))}</span>")

    def selected_paths(self):
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        return [self.model.rows[r]["path"] for r in rows]

    # ------------------------------------------------------------------ menus contextuels
    def table_menu(self, pos):
        paths = self.selected_paths()
        if not paths:
            return
        m = QMenu(self)
        m.addAction("▶ Lire", lambda: self.play_paths(paths))
        m.addAction("➕ Ajouter à la file de lecture", lambda: self.enqueue(paths))
        self._other_menu(m, paths)
        m.addAction("⏭ Lire ensuite", lambda: self.enqueue(paths, next_=True))
        pm = m.addMenu("📃 Ajouter à la playlist")
        for pid, name in self.lib.playlists():
            pm.addAction(name, lambda pid=pid: (self.lib.add_to_playlist(pid, paths), self.refresh_tracks()))
        pm.addSeparator(); pm.addAction("Nouvelle playlist…", lambda: self.new_playlist(paths))
        m.addSeparator()
        m.addAction("🎵 Identifier (empreinte audio)…", self.identify_selected)
        m.addAction("✏ Modifier les informations…", self.edit_tags)
        m.addAction("🗂 Afficher dans l'Explorateur", lambda: self.reveal(paths[0]))
        if self.current_node[0] == NODE_PLAYLIST:
            m.addSeparator(); m.addAction("Retirer de la playlist", lambda: self.remove_from_playlist(paths))
        else:
            m.addSeparator(); m.addAction("Retirer de la bibliothèque (le fichier est conservé)", lambda: self.remove_tracks(paths))
        m.exec(self.table.viewport().mapToGlobal(pos))

    def _other_menu(self, m, paths):
        """Sous-menu « Lire sur un autre lecteur » (autre sortie : casque Bluetooth, autre pièce…)."""
        sm = m.addMenu("🎧 Lire sur un autre lecteur")
        for i in self.queues:
            sub = sm.addMenu(self.hub.label(i))
            sub.addAction("▶ Lire maintenant", lambda i=i: self.play_on(i, paths))
            sub.addAction("➕ Ajouter à sa file", lambda i=i: self.play_on(i, paths, add=True))
        sm.addSeparator()
        sm.addAction("Rattacher une sortie à un lecteur…", lambda: (self.fx_dock.show(), self.statusBar().showMessage(
            "Panneau Son : choisissez la sortie, puis « Lecteur : Lecteur 2 »", 8000)))

    def play_on(self, i, paths, add=False):
        if i not in self.hub.used_sources():
            r = QMessageBox.question(self, "Autre lecteur",
                                     f"Aucune sortie n'est encore rattachée au « {self.hub.label(i, True)} ».\n\n"
                                     "Ouvrir le panneau Son pour en choisir une ?\n"
                                     "(onglet de la sortie ▸ Lecteur ▸ " + self.hub.label(i, True) + ")")
            if r == QMessageBox.Yes:
                self.fx_dock.show()
            return
        q = self.queues[i]
        q.add(paths) if add else q.set(paths)
        self.others_dock.show(); self.others.refresh()
        self.statusBar().showMessage(f"{len(paths)} titre(s) {'ajouté(s) à' if add else 'joué(s) sur'} {self.hub.label(i)}", 5000)

    def tree_menu(self, pos):
        it = self.tree.itemAt(pos)
        node = it.data(0, Qt.UserRole) if it else None
        m = QMenu(self)
        if node and node[0] == NODE_PLAYLIST:
            pid = node[1]
            m.addAction("▶ Lire", lambda: self.play_paths(self.lib.playlist_paths(pid)))
            m.addAction("🔀 Lire en aléatoire", lambda: (self.b_shuffle.setChecked(True), self.play_paths(self.lib.playlist_paths(pid))))
            m.addAction("Renommer…", lambda: self.rename_playlist(pid))
            m.addAction("Exporter (M3U)…", lambda: self.export_m3u(pid))
            m.addAction("Supprimer", lambda: (self.lib.delete_playlist(pid), self.refresh_tree()))
        elif node and node[0] in (NODE_ARTIST, NODE_ALBUM):
            self.current_node = node; self.refresh_tracks()
            paths = [r["path"] for r in self.model.rows]
            m.addAction("▶ Lire", lambda: self.play_paths(paths))
            m.addAction("➕ Ajouter à la file", lambda: self.enqueue(paths))
            self._other_menu(m, paths)
            m.addAction("✏ Modifier les informations…", lambda: self._edit(paths))
            m.addAction("🎵 Identifier…", lambda: self._identify(paths))
        else:
            m.addAction("Nouvelle playlist…", self.new_playlist)
        m.exec(self.tree.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ lecture
    def play_from_table(self, idx):
        paths = [r["path"] for r in self.model.rows]
        self.set_queue(paths, start=idx.row())

    def play_paths(self, paths):
        self.set_queue(list(paths), start=0)

    def set_queue(self, paths, start=0):
        if not paths:
            return
        self.queue = list(paths)
        self.qpos = self._make_order(first=start)
        self._refresh_queue_list()
        self._play_current()

    def _make_order(self, first=None) -> int:
        """Construit l'ordre de lecture ; renvoie la position du premier titre à jouer."""
        idx = list(range(len(self.queue)))
        if self.b_shuffle.isChecked():
            random.shuffle(idx)
            if first is not None:
                idx.remove(first); idx.insert(0, first)
            self.order = idx
            return 0
        self.order = idx
        return first or 0

    def enqueue(self, paths, next_=False):
        start = len(self.queue)
        self.queue += list(paths)
        new = list(range(start, len(self.queue)))
        if next_ and self.qpos >= 0:
            self.order[self.qpos + 1:self.qpos + 1] = new
        else:
            if self.b_shuffle.isChecked():
                random.shuffle(new)
            self.order += new
        self._refresh_queue_list()
        if self.qpos < 0:
            self.qpos = 0; self._play_current()

    def _refresh_queue_list(self):
        self.queue_list.clear()
        by_path = {r["path"]: r for r in self.lib.tracks()}
        for i in self.order:
            p = self.queue[i]; r = by_path.get(p)
            self.queue_list.addItem(f"{r['artist'] or '?'} — {r['title'] or Path(p).stem}" if r else Path(p).stem)
        self._highlight_queue()

    def _highlight_queue(self):
        if 0 <= self.qpos < self.queue_list.count():
            self.queue_list.setCurrentRow(self.qpos)

    def _play_current(self):
        if not (0 <= self.qpos < len(self.order)):
            return
        path = self.queue[self.order[self.qpos]]
        if not os.path.exists(path):
            self.statusBar().showMessage(f"Fichier introuvable : {path}", 5000); return
        try:
            t = read_tags(path)
            self.player.load(path, t.duration)
        except Exception as e:
            QMessageBox.warning(self, "Lecture impossible", f"{e}\n\nVérifiez la carte son et que ffmpeg est installé.")
            return
        self.lib.count_play(path)
        self.model.playing_path = path; self.model.layoutChanged.emit()
        self.mini_title.setText(t.title or Path(path).stem); self.mini_artist.setText(t.artist or "")
        self.np_title.setText(t.title or Path(path).stem)
        self.np_info.setText(f"{t.artist or 'Artiste inconnu'}\n{t.album or ''} {('(' + t.year + ')') if t.year else ''}\n"
                             f"{t.bitrate} kbit/s · {fmt_time(t.duration)}")
        pm = QPixmap(); data = read_cover(path)
        if data and pm.loadFromData(data):
            self.cover.setPixmap(pm.scaled(self.cover_size, self.cover_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.mini_cover.setPixmap(pm.scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.cover.clear(); self.cover.setText("♪"); self.mini_cover.clear()
        self.setWindowTitle(f"{t.title or Path(path).stem} — {APP_NAME}")
        self._highlight_queue()

    def play_index(self, row):
        if 0 <= row < len(self.order):
            self.qpos = row; self._play_current()

    def play_pause(self):
        if not self.player.path:
            if self.model.rows:
                self.set_queue([r["path"] for r in self.model.rows], 0)
            return
        try:
            self.player.toggle()
        except Exception as e:
            QMessageBox.warning(self, "Audio", str(e))

    def stop(self):
        self.player.stop()

    def next_track(self, auto=False):
        if not self.order:
            return
        repeat = settings["repeat"]
        if auto and repeat == "one":
            self._play_current(); return
        if self.qpos + 1 < len(self.order):
            self.qpos += 1
        elif repeat == "all" or not auto:
            self.qpos = self._make_order() if self.b_shuffle.isChecked() else 0
        else:
            self.player.stop(); return
        self._play_current()

    def prev_track(self):
        if self.player.position > 3:
            self.player.seek(0); return
        if self.qpos > 0:
            self.qpos -= 1; self._play_current()

    def set_shuffle(self, on):
        settings["shuffle"] = on
        if self.queue:
            cur = self.order[self.qpos] if 0 <= self.qpos < len(self.order) else None
            idx = list(range(len(self.queue)))
            if on:
                random.shuffle(idx)
                if cur is not None:
                    idx.remove(cur); idx.insert(0, cur)
                self.qpos = 0
            else:
                self.qpos = cur or 0
            self.order = idx
            self._refresh_queue_list()

    def cycle_repeat(self):
        settings["repeat"] = {"none": "all", "all": "one", "one": "none"}[settings["repeat"]]
        self._update_repeat_btn()

    def _update_repeat_btn(self):
        r = settings["repeat"]
        self.b_repeat.setText({"none": "🔁", "all": "🔁", "one": "🔂"}[r])
        self.b_repeat.setCheckable(True); self.b_repeat.setChecked(r != "none")

    def set_volume(self, v):
        self.player.volume = v / 100; settings["volume"] = v / 100

    def set_mute(self, on):
        self.player.muted = on; self.b_mute.setText("🔇" if on else "🔊")

    def tick(self):
        p = self.player
        self.b_play.setText("⏸" if p.playing else "▶")
        if p.duration and not self.seek.isSliderDown():
            self.seek.setValue(int(p.position / p.duration * 1000))
        self.t_pos.setText(fmt_time(p.position)); self.t_dur.setText(fmt_time(p.duration))
        self.vu.set_levels(*(p.levels if p.playing else (0, 0, 0, 0)))
        if self.fx_dock.isVisible():
            self.sound.update_meters()
        if p.error:
            self.statusBar().showMessage(p.error, 8000); p.error = ""
        if p.finished:
            p.finished = False; self.next_track(auto=True)
        for i, q in self.queues.items():
            sp = self.hub.players[i]
            if sp.error:
                self.statusBar().showMessage(f"{self.hub.label(i, True)} : {sp.error}", 8000); sp.error = ""
            if sp.finished:
                sp.finished = False; q.next(auto=True)
        if self.others_dock.isVisible():
            self.others.tick()

    # ------------------------------------------------------------------ bibliothèque
    def welcome(self):
        r = QMessageBox.question(
            self, "Bienvenue",
            "Votre bibliothèque est vide.\n\nVoulez-vous indiquer un emplacement (disque, clé USB, dossier) "
            "à ranger et classer automatiquement ?\n\n(Non = simplement ajouter un dossier sans le réorganiser)",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if r == QMessageBox.Yes:
            self.organize()
        elif r == QMessageBox.No:
            self.add_folder()

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Dossier de musique à ajouter")
        if d:
            if d not in settings["watched_folders"]:
                settings["watched_folders"].append(d); settings.save()
            self.scan([d])

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Fichiers audio", "", "Audio (*.mp3 *.flac *.m4a *.ogg *.wav *.opus *.wma)")
        for f in files:
            self.lib.upsert(read_tags(f))
        if files:
            self.refresh_tree(); self.refresh_tracks()

    def rescan(self):
        folders = list(settings["watched_folders"])
        if Path(settings["library_root"]).is_dir():
            folders.append(settings["library_root"])
        self.scan(folders)

    def scan(self, folders):
        def job(progress, log, cancel):
            n = 0
            for f in folders:
                n += self.lib.scan(f, progress=progress, cancel=cancel)
            return n
        self.scan_worker = Worker(job)
        self.scan_bar.setVisible(True)
        self.scan_worker.progress.connect(lambda a, b, t: (self.scan_bar.setMaximum(max(b, 1)), self.scan_bar.setValue(a),
                                                          self.scan_bar.setFormat(f"Référencement %v/%m")))
        self.scan_worker.done.connect(lambda n: (self.scan_bar.setVisible(False), self.refresh_tree(), self.refresh_tracks(),
                                                 self.statusBar().showMessage(f"{n} titres ajoutés ou mis à jour", 6000)))
        self.scan_worker.failed.connect(lambda e: (self.scan_bar.setVisible(False), QMessageBox.warning(self, "Erreur", e)))
        self.scan_worker.start()

    def remove_tracks(self, paths):
        for p in paths:
            self.lib.remove(p)
        self.refresh_tree(); self.refresh_tracks()

    def reveal(self, path):
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            subprocess.Popen(["xdg-open", str(Path(path).parent)])

    def _reload_paths(self, paths):
        for p in paths:
            if os.path.exists(p):
                self.lib.upsert(read_tags(p))
        self.refresh_tree(); self.refresh_tracks()

    # ------------------------------------------------------------------ outils
    def organize(self, source=""):
        d = dialogs.OrganizeDialog(self.lib, self, source if isinstance(source, str) else "")
        d.finished_ok.connect(lambda: (self.refresh_tree(), self.refresh_tracks()))
        d.exec()

    def identify_selected(self):
        self._identify(self.selected_paths())

    def _identify(self, paths):
        if not paths:
            QMessageBox.information(self, "Identifier", "Sélectionnez un ou plusieurs titres dans la liste."); return
        d = dialogs.IdentifyDialog(paths, self)
        d.changed.connect(lambda: self._reload_paths(paths)); d.exec()

    def identify_all_incomplete(self):
        paths = [r["path"] for r in self.lib.tracks(incomplete_only=True)]
        if not paths:
            QMessageBox.information(self, "Identifier", "Tous les titres ont déjà leurs informations. 👍"); return
        d = dialogs.BatchIdentifyDialog(paths, self)
        d.changed.connect(lambda: self._reload_paths(paths)); d.exec()

    def edit_tags(self):
        self._edit(self.selected_paths())

    def _edit(self, paths):
        if paths and dialogs.TagEditor(paths, self).exec():
            self._reload_paths(paths)

    def open_cd(self):
        d = dialogs.CdDialog(self.lib, self)
        d.imported.connect(lambda _: (self.refresh_tree(), self.refresh_tracks())); d.exec()

    def open_youtube(self):
        d = dialogs.YoutubeDialog(self.lib, self)
        d.imported.connect(lambda _: (self.refresh_tree(), self.refresh_tracks())); d.exec()

    def open_settings(self):
        dialogs.SettingsDialog(self).exec()

    # ------------------------------------------------------------------ playlists
    def new_playlist(self, paths=None):
        name, ok = QInputDialog.getText(self, "Nouvelle playlist", "Nom :")
        if ok and name.strip():
            pid = self.lib.create_playlist(name.strip())
            if paths:
                self.lib.add_to_playlist(pid, paths)
            self.refresh_tree()

    def rename_playlist(self, pid):
        name, ok = QInputDialog.getText(self, "Renommer", "Nouveau nom :", text=dict(self.lib.playlists())[pid])
        if ok and name.strip():
            with self.lib._lock:
                self.lib.db.execute("UPDATE playlists SET name=? WHERE id=?", (name.strip(), pid)); self.lib.db.commit()
            self.refresh_tree()

    def remove_from_playlist(self, paths):
        pid = self.current_node[1]
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        keep = [p for i, p in enumerate(self.lib.playlist_paths(pid)) if i not in rows]
        self.lib.set_playlist(pid, keep); self.refresh_tracks()

    def import_m3u(self):
        f, _ = QFileDialog.getOpenFileName(self, "Importer une playlist", "", "Playlist (*.m3u *.m3u8)")
        if f:
            paths = Library.import_m3u(f)
            pid = self.lib.create_playlist(Path(f).stem)
            for p in paths:
                if os.path.exists(p):
                    self.lib.upsert(read_tags(p))
            self.lib.set_playlist(pid, paths); self.refresh_tree()

    def export_m3u(self, pid=None):
        if pid is None or pid is False:
            if self.current_node[0] != NODE_PLAYLIST:
                QMessageBox.information(self, "Exporter", "Affichez d'abord une playlist."); return
            pid = self.current_node[1]
        name = dict(self.lib.playlists()).get(pid, "playlist")
        f, _ = QFileDialog.getSaveFileName(self, "Exporter", f"{name}.m3u8", "Playlist (*.m3u8 *.m3u)")
        if f:
            Library.export_m3u(self.lib.playlist_paths(pid), f)

    # ------------------------------------------------------------------
    def closeEvent(self, e):
        import base64
        settings["win_geometry"] = base64.b64encode(bytes(self.saveGeometry())).decode()
        settings["win_state"] = base64.b64encode(bytes(self.saveState())).decode()
        settings["win_maximized"] = self.isMaximized()
        settings.save()
        self.hub.close()
        super().closeEvent(e)
