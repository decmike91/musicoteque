"""Panneau « Son » : une sortie audio par onglet (jusqu'à 3), chacune avec son périphérique,
son profil audio (égaliseur, ambiance, effets, audiogramme), son volume et son alignement.
Contient aussi l'éditeur d'audiogramme et le test auditif."""
import copy
import math
import random
import time

from PySide6.QtCore import Qt, Signal, QTimer, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QPainterPath, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLabel, QPushButton, QToolButton,
    QComboBox, QCheckBox, QSlider, QSpinBox, QGroupBox, QTabWidget, QMessageBox, QInputDialog,
    QFileDialog, QMenu, QDialog, QTableWidget, QTableWidgetItem, QHeaderView, QRadioButton, QButtonGroup, QProgressBar,
    QSizePolicy, QAbstractSpinBox,
)

from ..config import settings
from .. import profiles as P
from ..audio_engine import (EQ_PRESETS, EQ_LABELS, AMBIANCES, MAX_ZONES, CHANNEL_MODES, output_devices,
                            device_label, SOURCE_NAMES, zone_source)
from .widgets import Knob, VUMeter, fit_to_screen, scrolled

EAR_COLORS = {"right": QColor("#f85149"), "left": QColor("#58a6ff")}
import sys
DEFAULT_DEVICE = "Périphérique par défaut" + (" de Windows" if sys.platform == "win32" else " du système")


# =================================================================== égaliseur & effets
class EffectsPanel(QWidget):
    """Égaliseur 10 bandes, préréglages, ambiances, basses, surround, réverbération, balance."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        eqbox = QGroupBox("Égaliseur"); eql = QVBoxLayout(eqbox)
        top = QHBoxLayout()
        self.cb_on = QCheckBox("Activé"); self.cb_on.setChecked(True); self.cb_on.toggled.connect(self._emit)
        self.preset = QComboBox(); self.preset.addItems(list(EQ_PRESETS) + ["Personnalisé"])
        self.preset.currentTextChanged.connect(self.apply_preset)
        reset = QPushButton("Réinitialiser"); reset.clicked.connect(self.reset)
        top.addWidget(self.cb_on); top.addWidget(QLabel("Préréglage :")); top.addWidget(self.preset)
        top.addStretch(); top.addWidget(reset)
        eql.addLayout(top)
        grid = QGridLayout(); self.sliders = []
        for i, lab in enumerate(EQ_LABELS):
            s = QSlider(Qt.Vertical); s.setRange(-120, 120); s.setTickPosition(QSlider.TicksBothSides)
            s.setTickInterval(30); s.setMinimumHeight(70)
            v = QLabel("0"); v.setAlignment(Qt.AlignCenter); v.setStyleSheet("font-size:10px")
            s.valueChanged.connect(lambda val, v=v: (v.setText(f"{val / 10:+.0f}"), self.eq_changed()))
            grid.addWidget(v, 0, i); grid.addWidget(s, 1, i, Qt.AlignHCenter)
            l = QLabel(lab); l.setAlignment(Qt.AlignCenter); grid.addWidget(l, 2, i)
            self.sliders.append(s)
        eql.addLayout(grid); lay.addWidget(eqbox, 3)

        fx = QGroupBox("Son && ambiance"); fl = QVBoxLayout(fx)
        r = QHBoxLayout(); r.addWidget(QLabel("Ambiance :"))
        self.amb = QComboBox(); self.amb.addItems(AMBIANCES); self.amb.currentTextChanged.connect(self.apply_ambiance)
        r.addWidget(self.amb); fl.addLayout(r)
        knobs = QHBoxLayout()
        self.k_bass = Knob("Basses", 0, 12, 0, lambda v: f"+{v} dB")
        self.k_sur = Knob("Surround", 0, 100, 0, lambda v: f"{v} %")
        self.k_rev = Knob("Réverbe", 0, 100, 0, lambda v: f"{v} %")
        self.k_room = Knob("Taille salle", 0, 100, 50, lambda v: f"{v} %")
        for k in (self.k_bass, self.k_sur, self.k_rev, self.k_room):
            knobs.addWidget(k); k.valueChanged.connect(self._emit)
        fl.addLayout(knobs)
        br = QHBoxLayout(); br.addWidget(QLabel("G"))
        self.balance = QSlider(Qt.Horizontal); self.balance.setRange(-100, 100)
        self.balance.setTickPosition(QSlider.TicksBelow); self.balance.setTickInterval(50)
        self.balance.valueChanged.connect(self._emit)
        br.addWidget(self.balance); br.addWidget(QLabel("D"))
        bc = QPushButton("Centre"); bc.setFixedWidth(64); bc.clicked.connect(lambda: self.balance.setValue(0)); br.addWidget(bc)
        fl.addWidget(QLabel("Balance")); fl.addLayout(br)
        lay.addWidget(fx, 2)

    def _emit(self, *_):
        if not self._loading:
            self.changed.emit()

    def set_profile(self, p):
        self._loading = True
        self.cb_on.setChecked(p["eq_enabled"])
        for s, g in zip(self.sliders, p["eq_gains"]):
            s.setValue(int(round(g * 10)))
        self.preset.setCurrentText(p["eq_preset"] if p["eq_preset"] in EQ_PRESETS else "Personnalisé")
        self.amb.setCurrentText(p["ambiance"])
        self.k_bass.setValue(p["bass"]); self.k_sur.setValue(round(p["surround"] * 100))
        self.k_rev.setValue(round(p["reverb_mix"] * 100)); self.k_room.setValue(round(p["reverb_room"] * 100))
        self.balance.setValue(round(p["balance"] * 100))
        self._loading = False

    def read_into(self, p):
        p.update(eq_enabled=self.cb_on.isChecked(), eq_preset=self.preset.currentText(),
                 eq_gains=[s.value() / 10 for s in self.sliders], ambiance=self.amb.currentText(),
                 bass=self.k_bass.value(), surround=self.k_sur.value() / 100,
                 reverb_mix=self.k_rev.value() / 100, reverb_room=self.k_room.value() / 100,
                 balance=self.balance.value() / 100)

    def apply_preset(self, name):
        if name in EQ_PRESETS and not self._loading:
            self._loading = True
            for s, g in zip(self.sliders, EQ_PRESETS[name]):
                s.setValue(int(g * 10))
            self._loading = False
            self.changed.emit()

    def eq_changed(self):
        if self._loading:
            return
        gains = [s.value() / 10 for s in self.sliders]
        if gains != [float(x) for x in EQ_PRESETS.get(self.preset.currentText(), [])]:
            self.preset.blockSignals(True); self.preset.setCurrentText("Personnalisé"); self.preset.blockSignals(False)
        self.changed.emit()

    def apply_ambiance(self, name):
        if self._loading:
            return
        a = AMBIANCES.get(name)
        self._loading = True
        if a is None:
            self.k_rev.setValue(0); self.k_sur.setValue(0)
        else:
            room, mix, damp, sur = a
            self.k_room.setValue(round(room * 100)); self.k_rev.setValue(round(mix * 100)); self.k_sur.setValue(round(sur * 100))
        self._loading = False
        self.changed.emit()

    def reset(self):
        self.set_profile(P.normalize({})); self.changed.emit()


# =================================================================== audiogramme
class AudiogramChart(QWidget):
    """Audiogramme cliquable : glisser les points pour régler la perte (pas de 5 dB).
    Convention : oreille droite = O rouge, oreille gauche = X bleue."""
    changed = Signal()
    DB_MIN, DB_MAX = -10, 120
    BANDS = [(-10, 20, "Normale", "#1a2f1f"), (20, 40, "Légère", "#2a2a17"), (40, 70, "Moyenne", "#33261a"),
             (70, 90, "Sévère", "#3a1f1f"), (90, 120, "Profonde", "#2d1a2d")]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.left = [0] * len(P.AUDIOGRAM_FREQS)
        self.right = [0] * len(P.AUDIOGRAM_FREQS)
        self.edit = "right"
        self.gains = None
        self._drag = None
        self.setMinimumSize(280, 150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

    def set_values(self, left, right):
        self.left, self.right = list(left), list(right); self.update()

    def _plot(self):
        return QRectF(44, 22, self.width() - 44 - 74, self.height() - 22 - 26)

    def _x(self, i, r):
        # échelle logarithmique, comme sur un audiogramme papier
        return r.left() + 12 + (math.log2(P.AUDIOGRAM_FREQS[i] / 125) / math.log2(8000 / 125)) * (r.width() - 24)

    def _y(self, db, r):
        return r.top() + (db - self.DB_MIN) / (self.DB_MAX - self.DB_MIN) * r.height()

    def _db_at(self, y, r):
        db = self.DB_MIN + (y - r.top()) / r.height() * (self.DB_MAX - self.DB_MIN)
        return int(max(self.DB_MIN, min(self.DB_MAX, round(db / 5) * 5)))

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#0d1117"))
        r = self._plot()
        f = QFont("Segoe UI", 8); p.setFont(f)
        for lo, hi, name, col in self.BANDS:
            band = QRectF(r.left(), self._y(lo, r), r.width(), self._y(hi, r) - self._y(lo, r))
            p.fillRect(band, QColor(col))
            p.setPen(QColor("#8b949e"))
            p.drawText(QRectF(r.right() + 6, band.top(), 70, band.height()), Qt.AlignVCenter | Qt.AlignLeft, name)
        p.setPen(QPen(QColor("#30363d"), 1))
        for db in range(self.DB_MIN, self.DB_MAX + 1, 10):
            y = self._y(db, r); p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(QColor("#8b949e")); p.drawText(QRectF(0, y - 8, 40, 16), Qt.AlignRight | Qt.AlignVCenter, str(db))
            p.setPen(QPen(QColor("#30363d"), 1))
        for i, lab in enumerate(P.AUDIOGRAM_LABELS):
            x = self._x(i, r); p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            p.setPen(QColor("#8b949e")); p.drawText(QRectF(x - 20, r.bottom() + 4, 40, 16), Qt.AlignCenter, lab)
            p.setPen(QPen(QColor("#30363d"), 1))
        p.setPen(QColor("#8b949e"))
        p.drawText(QRectF(0, 2, 200, 16), Qt.AlignLeft, "Perte (dB HL)")
        p.drawText(QRectF(r.right() - 120, 2, 120, 16), Qt.AlignRight, "Fréquence (Hz)")
        # courbes : l'oreille en cours d'édition est dessinée par-dessus
        for ear in (("left", "right") if self.edit == "right" else ("right", "left")):
            vals = self.left if ear == "left" else self.right
            col = EAR_COLORS[ear]
            pen = QPen(col, 2 if ear == self.edit else 1.2)
            if ear != self.edit:
                col = QColor(col); col.setAlpha(150); pen.setColor(col)
            p.setPen(pen)
            pts = [QPointF(self._x(i, r), self._y(v, r)) for i, v in enumerate(vals)]
            for a, b in zip(pts, pts[1:]):
                p.drawLine(a, b)
            for pt in pts:
                if ear == "right":
                    p.setBrush(QColor("#0d1117")); p.drawEllipse(pt, 6, 6)
                else:
                    p.drawLine(QPointF(pt.x() - 5, pt.y() - 5), QPointF(pt.x() + 5, pt.y() + 5))
                    p.drawLine(QPointF(pt.x() - 5, pt.y() + 5), QPointF(pt.x() + 5, pt.y() - 5))
        p.end()

    def _nearest(self, pos):
        r = self._plot()
        i = min(range(len(P.AUDIOGRAM_FREQS)), key=lambda k: abs(self._x(k, r) - pos.x()))
        return i if abs(self._x(i, r) - pos.x()) < 30 else None

    def mousePressEvent(self, e):
        i = self._nearest(e.position())
        if i is not None:
            self._drag = i; self._set(i, e.position().y())

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self._set(self._drag, e.position().y())
        else:
            self.setCursor(Qt.SizeVerCursor if self._nearest(e.position()) is not None else Qt.ArrowCursor)

    def mouseReleaseEvent(self, e):
        self._drag = None

    def _set(self, i, y):
        v = self._db_at(y, self._plot())
        vals = self.left if self.edit == "left" else self.right
        if vals[i] != v:
            vals[i] = v; self.update(); self.changed.emit()


class AudiogramPanel(QWidget):
    changed = Signal()
    test_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        left = QVBoxLayout()
        top = QHBoxLayout()
        self.cb_on = QCheckBox("Corriger le son d'après cet audiogramme")
        self.cb_on.toggled.connect(self._emit)
        top.addWidget(self.cb_on); top.addStretch()
        top.addWidget(QLabel("Modifier :"))
        self.rb_r = QRadioButton("Oreille droite (O)"); self.rb_l = QRadioButton("Oreille gauche (X)")
        self.rb_r.setStyleSheet("color:#f85149"); self.rb_l.setStyleSheet("color:#58a6ff")
        self.rb_r.setChecked(True)
        g = QButtonGroup(self); g.addButton(self.rb_r); g.addButton(self.rb_l)
        self.rb_r.toggled.connect(lambda on: self._edit_ear("right" if on else "left"))
        top.addWidget(self.rb_r); top.addWidget(self.rb_l)
        left.addLayout(top)
        self.chart = AudiogramChart(); self.chart.changed.connect(self._chart_changed)
        left.addWidget(self.chart, 1)
        # tableau des valeurs (saisie d'un audiogramme fait chez un audioprothésiste / ORL)
        self.table = QTableWidget(2, len(P.AUDIOGRAM_FREQS))
        self.table.setHorizontalHeaderLabels([f"{l} Hz" for l in P.AUDIOGRAM_LABELS])
        self.table.setVerticalHeaderLabels(["Droite (O)", "Gauche (X)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setFixedHeight(26 * 2 + self.table.horizontalHeader().sizeHint().height() + 6)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setToolTip("Double-cliquez sur une case pour saisir la valeur (dB HL)")
        for row, ear in enumerate(("right", "left")):
            for i in range(len(P.AUDIOGRAM_FREQS)):
                it = QTableWidgetItem("0"); it.setTextAlignment(Qt.AlignCenter)
                it.setForeground(EAR_COLORS[ear])
                self.table.setItem(row, i, it)
        self.table.itemChanged.connect(self._cell_changed)
        left.addWidget(self.table)
        self.corr = QLabel(); self.corr.setStyleSheet("color:#8b949e;font-size:11px"); self.corr.setWordWrap(True)
        left.addWidget(self.corr)
        lay.addLayout(left, 3)

        side = QGroupBox("Correction"); sl = QVBoxLayout(side)
        sl.addWidget(QLabel("Intensité de la correction"))
        self.strength = QSlider(Qt.Horizontal); self.strength.setRange(0, 100)
        self.strength_lbl = QLabel()
        self.strength.valueChanged.connect(lambda v: (self.strength_lbl.setText(
            f"{v} %" + ("  (règle du demi-gain)" if v == 50 else "")), self._emit()))
        sl.addWidget(self.strength); sl.addWidget(self.strength_lbl)
        sl.addWidget(QLabel("Correction maximale"))
        self.maxgain = QSpinBox(); self.maxgain.setRange(5, 40); self.maxgain.setSuffix(" dB")
        self.maxgain.valueChanged.connect(self._emit); sl.addWidget(self.maxgain)
        b_test = QPushButton("👂 Faire un test auditif…"); b_test.clicked.connect(self.test_requested)
        sl.addWidget(b_test)
        b_copy = QToolButton(); b_copy.setText("Copier une oreille sur l'autre ▾"); b_copy.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(b_copy)
        m.addAction("Droite → Gauche", lambda: self._copy("right", "left"))
        m.addAction("Gauche → Droite", lambda: self._copy("left", "right"))
        b_copy.setMenu(m); sl.addWidget(b_copy)
        b_zero = QPushButton("Remettre à zéro"); b_zero.clicked.connect(self._zero); sl.addWidget(b_zero)
        sl.addStretch()
        note = QLabel("Saisissez les valeurs de votre audiogramme (ORL, audioprothésiste) ou faites le test intégré. "
                      "Ce réglage améliore le confort d'écoute ; il ne remplace pas un examen ni un appareil auditif.")
        note.setWordWrap(True); note.setStyleSheet("color:#8b949e;font-size:11px"); sl.addWidget(note)
        lay.addWidget(side, 1)

    # --- synchro graphique / tableau
    def _edit_ear(self, ear):
        self.chart.edit = ear; self.chart.update()

    EARS_ROWS = (("right", 0), ("left", 1))

    def _fill_table(self):
        self._loading = True
        for ear, row in self.EARS_ROWS:
            for i, v in enumerate(getattr(self.chart, ear)):
                self.table.item(row, i).setText(str(int(v)))
        self._loading = False

    def _chart_changed(self):
        self._fill_table()
        self._emit()

    def _cell_changed(self, item):
        if self._loading:
            return
        ear = "right" if item.row() == 0 else "left"
        try:
            v = int(max(-10, min(120, round(float(item.text().replace(",", ".").replace("dB", "").strip())))))
        except ValueError:
            v = getattr(self.chart, ear)[item.column()]
        getattr(self.chart, ear)[item.column()] = v
        self.chart.update()
        self._fill_table()
        self._emit()

    def _copy(self, src, dst):
        vals = list(getattr(self.chart, src))
        self.chart.set_values(vals if dst == "left" else self.chart.left, vals if dst == "right" else self.chart.right)
        self._chart_changed()

    def _zero(self):
        n = len(P.AUDIOGRAM_FREQS)
        self.chart.set_values([0] * n, [0] * n); self._chart_changed()

    def set_values(self, left, right):
        self.chart.set_values(left, right); self._chart_changed()

    def _emit(self, *_):
        if not self._loading:
            self._update_corr()
            self.changed.emit()

    def _update_corr(self):
        ag = {}; self.read_into(ag)
        gl, gr = P.audiogram_gains(ag)
        if not ag["enabled"]:
            self.corr.setText("Correction désactivée.")
            return
        fmt = lambda g: " ".join(f"{v:+.0f}" for v in g)
        self.corr.setText(f"Correction appliquée (dB, de 125 Hz à 8 kHz) — droite : {fmt(gr)}   ·   gauche : {fmt(gl)}")

    # --- profil
    def set_audiogram(self, ag):
        self._loading = True
        self.cb_on.setChecked(bool(ag["enabled"]))
        self.strength.setValue(round(ag["strength"] * 100)); self.maxgain.setValue(int(ag["max_gain"]))
        self.chart.set_values(ag["left"], ag["right"])
        self._loading = False
        self._fill_table()
        self._loading = True
        self.strength_lbl.setText(f"{self.strength.value()} %" + ("  (règle du demi-gain)" if self.strength.value() == 50 else ""))
        self._loading = False
        self._update_corr()

    def read_into(self, ag):
        ag.update(enabled=self.cb_on.isChecked(), left=list(self.chart.left), right=list(self.chart.right),
                  strength=self.strength.value() / 100, max_gain=self.maxgain.value())


# =================================================================== test auditif
# Seuil d'audition normal approximatif (dB SPL, ISO 389-7) : sert à corriger la sensibilité
# naturelle de l'oreille selon la fréquence, pour que le résultat ressemble à un audiogramme.
NORMAL_THRESHOLD = {125: 22, 250: 11, 500: 4, 1000: 2, 2000: -1, 3000: -6, 4000: -5, 6000: 4, 8000: 13}
TEST_ORDER = [1000, 2000, 3000, 4000, 6000, 8000, 500, 250, 125]


class HearingTestDialog(QDialog):
    """Méthode ascendante : un bip pulsé monte doucement ; on appuie dès qu'on l'entend.
    Deux passages par fréquence (rapide puis fin) pour chaque oreille."""
    START_DB, CAP_DB = -95.0, -6.0

    def __init__(self, device_name="", tone_factory=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Test auditif"); fit_to_screen(self, 620, 430)
        self.device_name = device_name
        self.tone_factory = tone_factory
        self.gen = None
        self.result = None
        self.steps = [(ear, f) for ear in ("right", "left") for f in TEST_ORDER]
        self.thr = {"left": {}, "right": {}}
        lay = QVBoxLayout(self)
        self.info = QLabel(
            "<b>Avant de commencer</b><ul>"
            "<li>Mettez le casque ou les écouteurs que vous utilisez sur cette sortie, dans un endroit calme.</li>"
            "<li>Réglez le volume de Windows à votre niveau d'écoute habituel, puis <b>n'y touchez plus</b> pendant le test.</li>"
            "<li>Un bip très faible va monter progressivement : appuyez sur <b>J'entends</b> (ou Espace) dès que vous le percevez.</li>"
            "<li>Le test dure 5 à 8 minutes (9 fréquences × 2 oreilles).</li></ul>"
            "<span style='color:#d29922'>Ce test est indicatif : il ne remplace pas un audiogramme réalisé par un "
            "professionnel. En cas de gêne, de douleur ou d'acouphène, arrêtez immédiatement.</span>")
        self.info.setWordWrap(True); lay.addWidget(self.info)
        self.status = QLabel(""); self.status.setStyleSheet("font-size:18px;font-weight:600"); self.status.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.status)
        self.bar = QProgressBar(); self.bar.setMaximum(len(self.steps)); lay.addWidget(self.bar)
        self.b_hear = QPushButton("J'entends !"); self.b_hear.setMinimumHeight(70)
        self.b_hear.setStyleSheet("font-size:22px;background:#238636"); self.b_hear.setEnabled(False)
        self.b_hear.clicked.connect(self.heard); lay.addWidget(self.b_hear)
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=lambda: self.b_hear.isEnabled() and self.heard())
        row = QHBoxLayout()
        self.b_start = QPushButton("Commencer"); self.b_start.clicked.connect(self.start)
        self.b_cancel = QPushButton("Annuler"); self.b_cancel.clicked.connect(self.reject)
        row.addStretch(); row.addWidget(self.b_start); row.addWidget(self.b_cancel)
        lay.addLayout(row)
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick)

    def start(self):
        try:
            if self.tone_factory:
                self.gen = self.tone_factory(self.device_name)
            else:
                from ..audio_engine import ToneGenerator
                self.gen = ToneGenerator(self.device_name)
        except Exception as e:
            QMessageBox.warning(self, "Test auditif", f"Impossible d'ouvrir la sortie audio : {e}"); return
        self.b_start.setEnabled(False); self.b_hear.setEnabled(True); self.b_hear.setFocus()
        self.idx = 0
        self._begin_step()

    def _begin_step(self):
        if self.idx >= len(self.steps):
            self.finish(); return
        ear, f = self.steps[self.idx]
        self.status.setText(f"{'Oreille droite' if ear == 'right' else 'Oreille gauche'} — {f} Hz")
        self.bar.setValue(self.idx)
        self.phase = 1                      # 1 = montée rapide, 2 = montée fine
        self.level = self.START_DB
        self.gen.freq, self.gen.ear, self.gen.db, self.gen.on = float(f), ear, self.level, False
        self.wait_until = time.monotonic() + random.uniform(0.8, 2.0)   # pause aléatoire : évite d'anticiper
        self.last_step = self.wait_until
        self.timer.start(50)

    def tick(self):
        now = time.monotonic()
        if now < self.wait_until:
            return
        self.gen.on = True
        step, every = (5.0, 0.45) if self.phase == 1 else (2.0, 0.6)
        if now - self.last_step >= every:
            self.last_step = now
            self.level += step
            if self.level > self.CAP_DB:          # rien entendu jusqu'au niveau maximal autorisé
                self._record(self.CAP_DB + 10); return
            self.gen.db = self.level

    def heard(self):
        if not self.gen or not self.gen.on:
            return
        if self.phase == 1:
            self.phase = 2
            self.level = max(self.START_DB, self.level - 12)
            self.gen.on, self.gen.db = False, self.level
            self.wait_until = time.monotonic() + random.uniform(0.8, 1.6)
            self.last_step = self.wait_until
        else:
            self._record(self.level)

    def _record(self, db):
        ear, f = self.steps[self.idx]
        self.thr[ear][f] = db
        self.gen.on = False
        self.timer.stop()
        self.idx += 1
        self._begin_step()

    def finish(self):
        self.timer.stop()
        if self.gen:
            self.gen.on = False; self.gen.close(); self.gen = None
        self.result = self.to_audiogram(self.thr)
        self.bar.setValue(len(self.steps))
        fmt = lambda e: "  ".join(f"{l}:{v}" for l, v in zip(P.AUDIOGRAM_LABELS, self.result[e]))
        self.status.setText("Test terminé ✓")
        self.info.setText(f"<b>Résultat (perte relative en dB)</b><br><span style='color:#f85149'>Droite : {fmt('right')}</span>"
                          f"<br><span style='color:#58a6ff'>Gauche : {fmt('left')}</span><br><br>"
                          "Cliquez sur <b>Appliquer</b> pour reporter ces valeurs dans l'audiogramme de cette sortie.")
        self.b_hear.setEnabled(False)
        self.b_start.setText("Appliquer"); self.b_start.setEnabled(True)
        self.b_start.clicked.disconnect(); self.b_start.clicked.connect(self.accept)

    @staticmethod
    def to_audiogram(thr):
        """Seuils (dBFS) -> pertes relatives (dB), arrondies à 5 dB.
        La meilleure fréquence (après correction de la sensibilité naturelle) sert de référence 0."""
        rel = {e: {f: thr[e].get(f, 0) - NORMAL_THRESHOLD[f] for f in P.AUDIOGRAM_FREQS} for e in thr}
        ref = min(v for e in rel for v in rel[e].values())
        return {e: [int(min(120, max(0, round((rel[e][f] - ref) / 5) * 5))) for f in P.AUDIOGRAM_FREQS]
                for e in ("left", "right")}

    def reject(self):
        self.timer.stop()
        if self.gen:
            self.gen.on = False; self.gen.close(); self.gen = None
        super().reject()


# =================================================================== une sortie
class ZoneTab(QWidget):
    """Réglages d'une sortie : périphérique, profil, volume, alignement, égaliseur, audiogramme."""
    structure_changed = Signal()      # périphérique / activation : il faut rouvrir les sorties
    live_changed = Signal()           # volume, voies, profil : appliqué à chaud
    delay_changed = Signal()
    remove_requested = Signal()
    title_changed = Signal()

    def __init__(self, cfg, index, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.index = index
        self._loading = True
        lay = QVBoxLayout(self); lay.setContentsMargins(6, 6, 6, 6)

        # --- ligne 1 : sortie
        r1 = QHBoxLayout()
        self.cb_on = QCheckBox("Active"); self.cb_on.setChecked(cfg.get("enabled", True))
        self.cb_on.toggled.connect(self._structure)
        self.device = QComboBox(); self.device.setMinimumContentsLength(16)
        self.device.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.refresh_devices()
        self.device.currentIndexChanged.connect(self._structure)
        b_ref = QToolButton(); b_ref.setText("⟳"); b_ref.setToolTip("Actualiser la liste des périphériques")
        b_ref.clicked.connect(self.refresh_devices)
        self.b_test = QToolButton(); self.b_test.setText("🔔"); self.b_test.setToolTip("Bip de test sur ce périphérique")
        self.b_test.clicked.connect(self.test_sound)
        self.channels = QComboBox()
        for k, v in CHANNEL_MODES.items():
            self.channels.addItem(v, k)
        self.channels.setCurrentIndex(max(0, list(CHANNEL_MODES).index(cfg.get("channels", "stereo"))))
        self.channels.currentIndexChanged.connect(self._live)
        self.vol = QSlider(Qt.Horizontal); self.vol.setRange(0, 100); self.vol.setMinimumWidth(90); self.vol.setMaximumWidth(200)
        self.vol.setValue(round(cfg.get("volume", 1.0) * 100))
        self.vol_lbl = QLabel(f"{self.vol.value()} %"); self.vol_lbl.setFixedWidth(40)
        self.vol.valueChanged.connect(lambda v: (self.vol_lbl.setText(f"{v} %"), self._live()))
        self.delay = QSpinBox(); self.delay.setRange(0, 1000); self.delay.setSuffix(" ms"); self.delay.setSingleStep(5)
        self.delay.setValue(int(cfg.get("delay_ms", 0)))
        self.delay.setToolTip("Retarde cette sortie pour l'aligner sur les autres\n"
                              "(ex. enceinte Bluetooth en retard : retardez les autres sorties de 150 à 250 ms)")
        self.delay_timer = QTimer(self); self.delay_timer.setSingleShot(True); self.delay_timer.timeout.connect(self._delay)
        self.delay.valueChanged.connect(lambda: self.delay_timer.start(500))
        self.vu = VUMeter(); self.vu.setMinimumSize(120, 34); self.vu.setMaximumSize(240, 40)
        self.source = QComboBox()
        for i, n in enumerate(SOURCE_NAMES):
            self.source.addItem(n, i)
        self.source.setCurrentIndex(zone_source(cfg))
        self.source.setToolTip("Lecteur dont cette sortie diffuse la musique.\n"
                               "Choisissez « Lecteur 2 » pour écouter un autre titre sur cette sortie\n"
                               "(ex. casque Bluetooth) pendant que le lecteur principal continue ailleurs.")
        self.source.currentIndexChanged.connect(self._structure)
        for w in (self.cb_on, QLabel("Périphérique :"), self.device, b_ref, self.b_test, QLabel("Lecteur :"), self.source,
                  QLabel("Voies :"), self.channels):
            r1.addWidget(w)
        r1.addStretch()
        if index > 0:
            b_rm = QToolButton(); b_rm.setText("✕"); b_rm.setToolTip("Retirer cette sortie")
            b_rm.clicked.connect(self.remove_requested); r1.addWidget(b_rm)
        lay.addLayout(r1)
        r1b = QHBoxLayout()
        for w in (QLabel("Volume :"), self.vol, self.vol_lbl, QLabel("Retard :"), self.delay):
            r1b.addWidget(w)
        r1b.addStretch(); r1b.addWidget(self.vu)
        lay.addLayout(r1b)

        # --- ligne 2 : profil audio
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Profil audio :"))
        self.profile = QComboBox(); self.profile.setMinimumContentsLength(14)
        self.profile.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.profile.activated.connect(self._load_selected)
        self.modified = QLabel(""); self.modified.setStyleSheet("color:#d29922")
        b_save = QPushButton("💾 Enregistrer"); b_save.clicked.connect(self.save)
        b_save_as = QPushButton("Enregistrer sous…"); b_save_as.clicked.connect(self.save_as)
        b_more = QToolButton(); b_more.setText("⋯"); b_more.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(b_more)
        m.addAction("Renommer…", self.rename); m.addAction("Supprimer ce profil", self.delete)
        m.addSeparator()
        m.addAction("Importer un profil…", self.import_); m.addAction("Exporter ce profil…", self.export)
        m.addSeparator()
        self.copy_menu = m.addMenu("Copier les réglages vers une autre sortie")
        b_more.setMenu(m)
        for w in (self.profile, self.modified, b_save, b_save_as, b_more):
            r2.addWidget(w)
        r2.addStretch()
        lay.addLayout(r2)

        # --- réglages
        self.tabs = QTabWidget()
        self.fx = EffectsPanel(); self.fx.changed.connect(self._profile_edited)
        self.ag = AudiogramPanel(); self.ag.changed.connect(self._profile_edited)
        self.ag.test_requested.connect(self.hearing_test)
        self.tabs.addTab(self.fx, "🎚 Égaliseur && ambiance")
        self.tabs.addTab(self.ag, "👂 Audiogramme")
        lay.addWidget(self.tabs, 1)

        self.refresh_profiles()
        self._show_profile()
        self._loading = False

    # --- titre de l'onglet
    def title(self):
        dev = device_label(self.cfg.get("device") or "") or "Par défaut"
        if len(dev) > 26:
            dev = dev[:25] + "…"
        src = zone_source(self.cfg)
        return (f"{'🔊' if self.cfg.get('enabled', True) else '🔈'} Sortie {self.index + 1} · {dev}"
                + (f"  [{SOURCE_NAMES[src]}]" if src else ""))

    # --- périphériques
    def refresh_devices(self):
        cur = self.cfg.get("device", "")
        self.device.blockSignals(True)
        self.device.clear(); self.device.addItem(DEFAULT_DEVICE, "")
        names = output_devices()
        for n in names:
            self.device.addItem(device_label(n), n)
        if cur and cur not in names:
            self.device.addItem(f"{device_label(cur)} (débranché)", cur)
        self.device.setCurrentIndex(max(0, self.device.findData(cur)))
        self.device.blockSignals(False)

    def test_sound(self):
        from ..audio_engine import test_tone
        try:
            test_tone(self.device.currentData() or "")
        except Exception as e:
            QMessageBox.warning(self, "Test", f"Impossible d'utiliser ce périphérique : {e}")

    def _structure(self, *_):
        if self._loading:
            return
        self.cfg["enabled"] = self.cb_on.isChecked()
        self.cfg["device"] = self.device.currentData() or ""
        self.cfg["source"] = self.source.currentData() or 0
        self.title_changed.emit(); self.structure_changed.emit()

    def _live(self, *_):
        if self._loading:
            return
        self.cfg["volume"] = self.vol.value() / 100
        self.cfg["channels"] = self.channels.currentData()
        self.live_changed.emit()

    def _delay(self):
        self.cfg["delay_ms"] = self.delay.value()
        self.delay_changed.emit()

    # --- profils
    def refresh_profiles(self):
        self.profile.blockSignals(True)
        self.profile.clear(); self.profile.addItems(P.list_profiles())
        name = self.cfg.get("profile_name", "Par défaut")
        if self.profile.findText(name) < 0:
            self.profile.addItem(name)
        self.profile.setCurrentText(name)
        self.profile.blockSignals(False)

    def _show_profile(self):
        p = P.normalize(self.cfg.get("profile"))
        self.cfg["profile"] = p
        self.fx.set_profile(p); self.ag.set_audiogram(p["audiogram"])
        self._update_modified()

    def current_profile(self):
        p = P.normalize(self.cfg.get("profile"))
        self.fx.read_into(p); self.ag.read_into(p["audiogram"])
        return p

    def _profile_edited(self):
        if self._loading:
            return
        self.cfg["profile"] = self.current_profile()
        self._update_modified()
        self.live_changed.emit()

    def _update_modified(self):
        saved = P.load_profile(self.cfg.get("profile_name", "Par défaut"))
        self.modified.setText("● modifié (non enregistré)" if saved != P.normalize(self.cfg["profile"]) else "")

    def _load_selected(self, *_):
        name = self.profile.currentText()
        if self.modified.text() and QMessageBox.question(
                self, "Profil audio", f"Les réglages actuels n'ont pas été enregistrés.\nCharger « {name} » quand même ?") != QMessageBox.Yes:
            self.profile.setCurrentText(self.cfg.get("profile_name", "Par défaut")); return
        self.load_profile(name)

    def load_profile(self, name):
        self.cfg["profile_name"] = name
        self.cfg["profile"] = P.load_profile(name)
        self._loading = True
        self.refresh_profiles(); self._show_profile()
        self._loading = False
        self.live_changed.emit()

    def save(self):
        name = self.cfg.get("profile_name", "Par défaut")
        if P.is_builtin(name):
            if QMessageBox.question(self, "Profil audio",
                                    f"« {name} » est un profil fourni avec le logiciel.\n"
                                    "Le remplacer par vos réglages ? (Non = l'enregistrer sous un autre nom)") != QMessageBox.Yes:
                self.save_as(); return
        P.save_profile(name, self.current_profile())
        self._after_save(name)

    def save_as(self):
        name, ok = QInputDialog.getText(self, "Enregistrer le profil audio", "Nom du profil :",
                                        text=f"Mon profil {len(P.list_profiles()) + 1}")
        name = name.strip()
        if not ok or not name:
            return
        if name in P.list_profiles() and QMessageBox.question(self, "Profil audio", f"Remplacer le profil « {name} » ?") != QMessageBox.Yes:
            return
        P.save_profile(name, self.current_profile())
        self._after_save(name)

    def _after_save(self, name):
        self.cfg["profile_name"] = name
        self.refresh_profiles(); self._update_modified()
        if hasattr(self.window(), "statusBar"):
            self.window().statusBar().showMessage(f"Profil « {name} » enregistré", 4000)
        self.parent_panel().refresh_all_profiles()

    def rename(self):
        old = self.cfg.get("profile_name", "Par défaut")
        name, ok = QInputDialog.getText(self, "Renommer le profil", "Nouveau nom :", text=old)
        name = name.strip()
        if ok and name and name != old:
            P.save_profile(name, P.load_profile(old)); P.delete_profile(old)
            self.cfg["profile_name"] = name
            self.parent_panel().refresh_all_profiles(renamed=(old, name))

    def delete(self):
        name = self.cfg.get("profile_name", "Par défaut")
        if P.is_builtin(name) and name in P.BUILTIN:
            QMessageBox.information(self, "Profil audio", "Les profils fournis avec le logiciel ne peuvent pas être supprimés."); return
        if QMessageBox.question(self, "Profil audio", f"Supprimer le profil « {name} » ?\n(les réglages actuels de la sortie sont conservés)") != QMessageBox.Yes:
            return
        P.delete_profile(name)
        self.cfg["profile_name"] = "Par défaut"
        self.parent_panel().refresh_all_profiles()

    def import_(self):
        f, _ = QFileDialog.getOpenFileName(self, "Importer un profil audio", "", "Profil audio (*.json)")
        if f:
            try:
                name = P.import_profile(f)
            except (OSError, ValueError) as e:
                QMessageBox.warning(self, "Importer", f"Fichier invalide : {e}"); return
            self.parent_panel().refresh_all_profiles()
            self.load_profile(name)

    def export(self):
        name = self.cfg.get("profile_name", "profil")
        f, _ = QFileDialog.getSaveFileName(self, "Exporter le profil audio", f"{name}.json", "Profil audio (*.json)")
        if f:
            P.export_profile(name, self.current_profile(), f)

    def parent_panel(self):
        w = self.parent()
        while w is not None and not isinstance(w, SoundPanel):
            w = w.parent()
        return w

    # --- test auditif
    def hearing_test(self):
        panel = self.parent_panel()
        if panel and panel.hub:
            panel.hub.pause_all()
        d = HearingTestDialog(self.cfg.get("device", ""), getattr(panel, "tone_factory", None), self)
        if d.exec() and d.result:
            self.ag.cb_on.setChecked(True)
            self.ag.set_values(d.result["left"], d.result["right"])


# =================================================================== panneau complet
class SoundPanel(QWidget):
    """Onglets des sorties + bouton d'ajout. Sauvegarde dans settings['zones']."""
    sources_changed = Signal()

    def __init__(self, hub, parent=None):
        super().__init__(parent)
        self.hub = hub
        self.player = hub.main
        self.tone_factory = None
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(); self.tabs.setDocumentMode(True)
        corner = QWidget(); cl = QHBoxLayout(corner); cl.setContentsMargins(0, 0, 6, 0)
        self.b_add = QPushButton("＋ Ajouter une sortie"); self.b_add.clicked.connect(lambda: self.add_zone())
        self.b_add.setToolTip("Nouvelle sortie qui diffuse la même musique (lecteur principal)")
        self.b_player = QPushButton("＋ Ajouter un lecteur")
        self.b_player.setToolTip("Nouveau lecteur indépendant (Lecteur 2 puis 3) avec sa propre sortie :\n"
                                 "une autre musique sur un autre périphérique")
        self.b_player.clicked.connect(self.add_player)
        cl.addWidget(self.b_add); cl.addWidget(self.b_player)
        self.tabs.setCornerWidget(corner)
        lay.addWidget(self.tabs)
        self.zones = self._load_cfgs()
        self.rebuild_tabs()
        try:
            self.hub.set_zones(self.zones)
        except Exception:
            pass

    @staticmethod
    def _load_cfgs():
        zones = settings.get("zones")
        if not zones:  # migration depuis la version à une seule sortie
            old = {"eq_preset": settings.get("eq_preset", "Plat"), "eq_gains": settings.get("eq_gains", [0] * 10),
                   "ambiance": settings.get("ambiance", "Aucune"), "bass": settings.get("bass_boost", 0),
                   "surround": settings.get("surround", 0), "reverb_mix": settings.get("reverb_mix", 0),
                   "reverb_room": settings.get("reverb_room", 0.5), "balance": settings.get("balance", 0)}
            zones = [{"enabled": True, "device": "", "volume": 1.0, "delay_ms": 0, "channels": "stereo",
                      "profile_name": "Par défaut", "profile": P.normalize(old)}]
        for z in zones:
            z["profile"] = P.normalize(z.get("profile"))
        settings["zones"] = zones
        return zones

    def rebuild_tabs(self):
        cur = self.tabs.currentIndex()
        self.tabs.clear()
        self.tab_widgets = []
        for i, cfg in enumerate(self.zones):
            t = ZoneTab(cfg, i)
            t.structure_changed.connect(lambda t=t: self.apply_structure(t.cfg))
            t.live_changed.connect(lambda t=t: self.apply_live(t))
            t.delay_changed.connect(lambda t=t: self.apply_delay(t.cfg))
            t.remove_requested.connect(lambda i=i: self.remove_zone(i))
            t.title_changed.connect(self.update_titles)
            self.tabs.addTab(t, t.title()); self.tab_widgets.append(t)
        self.tabs.setCurrentIndex(max(0, min(cur, len(self.zones) - 1)))
        self.b_add.setEnabled(len(self.zones) < MAX_ZONES)
        self.b_player.setEnabled(len(self.zones) < MAX_ZONES and self.hub.free_source() is not None)
        self._fill_copy_menus()

    def update_titles(self):
        for i, t in enumerate(self.tab_widgets):
            self.tabs.setTabText(i, t.title())

    def _fill_copy_menus(self):
        for i, t in enumerate(self.tab_widgets):
            t.copy_menu.clear()
            for j, other in enumerate(self.tab_widgets):
                if j != i:
                    t.copy_menu.addAction(f"Vers la sortie {j + 1}", lambda i=i, j=j: self.copy_profile(i, j))
            t.copy_menu.setEnabled(len(self.tab_widgets) > 1)

    def copy_profile(self, i, j):
        src, dst = self.tab_widgets[i], self.tab_widgets[j]
        dst.cfg["profile"] = copy.deepcopy(src.current_profile())
        dst.cfg["profile_name"] = src.cfg.get("profile_name", "Par défaut")
        dst._loading = True; dst.refresh_profiles(); dst._show_profile(); dst._loading = False
        self.apply_live(dst)

    def refresh_all_profiles(self, renamed=None):
        for t in self.tab_widgets:
            if renamed and t.cfg.get("profile_name") == renamed[0]:
                t.cfg["profile_name"] = renamed[1]
            t.refresh_profiles(); t._update_modified()
        self.save()

    # --- changements
    def add_player(self):
        src = self.hub.free_source()
        if src is None:
            QMessageBox.information(self, "Lecteurs", "Les 3 lecteurs sont déjà utilisés."); return
        self.add_zone(src)
        QMessageBox.information(self, "Nouveau lecteur",
                                f"{SOURCE_NAMES[src]} créé avec la sortie {len(self.zones)}.\n\n"
                                "1. Choisissez son périphérique dans l'onglet de la sortie.\n"
                                "2. Clic droit sur des titres ▸ « Lire sur un autre lecteur » ▸ " + SOURCE_NAMES[src] + ".")

    def add_zone(self, source=0):
        if len(self.zones) >= MAX_ZONES:
            return
        used = {z.get("device") for z in self.zones}
        free = [d for d in output_devices() if d not in used]
        self.zones.append({"enabled": True, "device": free[0] if free else "", "volume": 1.0, "delay_ms": 0,
                           "channels": "stereo", "source": source,
                           "profile_name": "Par défaut", "profile": P.normalize({})})
        self.rebuild_tabs(); self.tabs.setCurrentIndex(len(self.zones) - 1)
        self.apply_structure(self.zones[-1])

    def remove_zone(self, i):
        if len(self.zones) <= 1:
            return
        if QMessageBox.question(self, "Sorties audio", f"Retirer la sortie {i + 1} ?") != QMessageBox.Yes:
            return
        removed = self.zones.pop(i)
        self.rebuild_tabs(); self.apply_structure(removed)

    def apply_structure(self, changed=None):
        try:
            self.hub.set_zones(self.zones, changed)
        except Exception as e:
            QMessageBox.warning(self, "Sorties audio", str(e))
        self.save()
        self.b_player.setEnabled(len(self.zones) < MAX_ZONES and self.hub.free_source() is not None)
        self.sources_changed.emit()

    def apply_live(self, tab):
        z = self.hub.zone_for(tab.cfg)
        if z is not None:
            z.apply_profile(tab.cfg["profile"])
        self.save()

    def apply_delay(self, cfg=None):
        self.hub.realign(cfg)
        self.save()

    def save(self):
        settings["zones"] = self.zones
        settings.save()

    def update_meters(self):
        for t in self.tab_widgets:
            z = self.hub.zone_for(t.cfg)
            t.vu.set_levels(*(z.levels if z is not None and z.player.playing else (0, 0, 0, 0)))
