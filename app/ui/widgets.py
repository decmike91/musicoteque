"""Composants graphiques : vumètre, bouton rotatif, modèle de tableau, tâches de fond."""
import math
import traceback

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QThread, Signal, QRectF, QPointF, QSize
from PySide6.QtGui import QColor, QPainter, QLinearGradient, QPen, QFont
from PySide6.QtWidgets import QWidget, QDial, QVBoxLayout, QLabel


def screen_geometry(widget=None):
    """Zone utilisable de l'écran (sans la barre des tâches)."""
    from PySide6.QtGui import QGuiApplication
    scr = (widget.screen() if widget is not None and widget.screen() else None) or QGuiApplication.primaryScreen()
    return scr.availableGeometry()


def fit_to_screen(widget, w, h, fw=0.95, fh=0.9):
    """Taille souhaitée, réduite si l'écran est plus petit."""
    g = screen_geometry(widget)
    widget.resize(min(w, int(g.width() * fw)), min(h, int(g.height() * fh)))


def scrolled(widget):
    """Place un panneau dans une zone défilante : il ne force plus la hauteur de la fenêtre."""
    from PySide6.QtWidgets import QScrollArea, QFrame
    sa = QScrollArea(); sa.setWidget(widget); sa.setWidgetResizable(True); sa.setFrameShape(QFrame.NoFrame)
    return sa


def fmt_time(s: float) -> str:
    s = int(s or 0)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


# ------------------------------------------------------------------ Vumètre
class VUMeter(QWidget):
    """Vumètre stéréo à LED avec maintien de crête. Échelle -48 dB … +3 dB."""
    DB_MIN, DB_MAX = -48.0, 3.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(120, 30)
        self.rms = [self.DB_MIN, self.DB_MIN]
        self.peak = [self.DB_MIN, self.DB_MIN]
        self.hold = [self.DB_MIN, self.DB_MIN]
        self.hold_t = [0, 0]

    @staticmethod
    def to_db(v):
        return 20 * math.log10(v) if v > 1e-6 else -120.0

    def set_levels(self, pk_l, pk_r, rms_l, rms_r):
        for i, (pk, rms) in enumerate(((pk_l, rms_l), (pk_r, rms_r))):
            db_r, db_p = self.to_db(rms * 1.414), self.to_db(pk)
            # attaque rapide, retombée douce
            self.rms[i] = db_r if db_r > self.rms[i] else max(db_r, self.rms[i] - 1.2)
            self.peak[i] = db_p if db_p > self.peak[i] else max(db_p, self.peak[i] - 1.8)
            if db_p >= self.hold[i]:
                self.hold[i], self.hold_t[i] = db_p, 45
            elif self.hold_t[i] > 0:
                self.hold_t[i] -= 1
            else:
                self.hold[i] = max(self.DB_MIN, self.hold[i] - 0.6)
        self.update()

    def _x(self, db, w):
        f = (min(max(db, self.DB_MIN), self.DB_MAX) - self.DB_MIN) / (self.DB_MAX - self.DB_MIN)
        return f * w

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width() - 18, self.height()
        p.fillRect(self.rect(), QColor("#0d1117"))
        bar_h = (h - 16) / 2
        seg = 3
        nseg = int(w / (seg + 1))
        p.setFont(QFont("Segoe UI", 7))
        for ch in range(2):
            y = 3 + ch * (bar_h + 3)
            p.setPen(QColor("#8b949e"))
            p.drawText(QRectF(0, y, 14, bar_h), Qt.AlignCenter, "GD"[ch])
            lit = self._x(self.peak[ch], w)
            for k in range(nseg):
                x = 16 + k * (seg + 1)
                db = self.DB_MIN + (k / nseg) * (self.DB_MAX - self.DB_MIN)
                col = QColor("#2ea043") if db < -9 else QColor("#d29922") if db < -1 else QColor("#f85149")
                if x - 16 > lit:
                    col = col.darker(400)
                p.fillRect(QRectF(x, y, seg, bar_h), col)
            hx = 16 + self._x(self.hold[ch], w)
            p.fillRect(QRectF(hx - 1, y, 2, bar_h), QColor("#ffffff"))
        p.setPen(QColor("#6e7681"))
        for db in (-40, -30, -20, -10, -6, -3, 0, 3):
            x = 16 + self._x(db, w)
            p.drawText(QRectF(x - 12, h - 12, 24, 12), Qt.AlignCenter, str(db))
        p.end()


# ------------------------------------------------------------------ Bouton rotatif
class Knob(QWidget):
    def __init__(self, label, lo=0, hi=100, value=0, fmt=lambda v: f"{v}", parent=None):
        super().__init__(parent)
        self.fmt = fmt
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        self.dial = QDial(); self.dial.setRange(lo, hi); self.dial.setValue(value)
        self.dial.setNotchesVisible(True); self.dial.setWrapping(False)
        self.dial.setFixedSize(QSize(56, 56))
        self.val = QLabel(fmt(value)); self.val.setAlignment(Qt.AlignCenter)
        self.lab = QLabel(label); self.lab.setAlignment(Qt.AlignCenter)
        self.lab.setStyleSheet("color:#8b949e;font-size:11px")
        lay.addWidget(self.dial, 0, Qt.AlignCenter); lay.addWidget(self.val); lay.addWidget(self.lab)
        self.dial.valueChanged.connect(lambda v: self.val.setText(self.fmt(v)))

    @property
    def valueChanged(self):
        return self.dial.valueChanged

    def value(self):
        return self.dial.value()

    def setValue(self, v):
        self.dial.setValue(int(v))


# ------------------------------------------------------------------ Modèle de tableau
class TrackModel(QAbstractTableModel):
    COLS = [("track", "N°"), ("title", "Titre"), ("artist", "Artiste"), ("album", "Album"),
            ("year", "Année"), ("genre", "Genre"), ("duration", "Durée"), ("bitrate", "kbit/s"),
            ("plays", "Écoutes")]

    def __init__(self):
        super().__init__()
        self.rows: list[dict] = []
        self.playing_path = None

    def set_rows(self, rows):
        self.beginResetModel(); self.rows = rows; self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLS)

    def headerData(self, s, o, role=Qt.DisplayRole):
        if o == Qt.Horizontal and role == Qt.DisplayRole:
            return self.COLS[s][1]

    def data(self, idx, role=Qt.DisplayRole):
        r = self.rows[idx.row()]
        key = self.COLS[idx.column()][0]
        if role == Qt.DisplayRole:
            v = r.get(key)
            if key == "duration":
                return fmt_time(v)
            if key == "title" and not v:
                from pathlib import Path
                return Path(r["path"]).stem
            if key in ("track", "bitrate", "plays") and not v:
                return ""
            return v or ""
        if role == Qt.ForegroundRole:
            if r["path"] == self.playing_path:
                return QColor("#58a6ff")
            if key in ("title", "artist", "album") and not r.get(key):
                return QColor("#d29922")
        if role == Qt.FontRole and r["path"] == self.playing_path:
            f = QFont(); f.setBold(True); return f
        if role == Qt.ToolTipRole:
            return r["path"]
        if role == Qt.TextAlignmentRole and key in ("track", "duration", "bitrate", "plays", "year"):
            return int(Qt.AlignRight | Qt.AlignVCenter)

    def sort(self, column, order=Qt.AscendingOrder):
        key = self.COLS[column][0]
        self.layoutAboutToBeChanged.emit()
        self.rows.sort(key=lambda r: (r.get(key) is None, r.get(key) or (0 if key in ("track", "duration", "bitrate", "plays") else "")),
                       reverse=order == Qt.DescendingOrder)
        self.layoutChanged.emit()


# ------------------------------------------------------------------ Tâches de fond
class Worker(QThread):
    """Exécute fn(*args, progress=..., log=..., cancel=...) dans un thread."""
    progress = Signal(int, int, str)
    log = Signal(str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            res = self.fn(*self.args, progress=lambda a, b, c="": self.progress.emit(int(a), int(b), str(c)),
                          log=self.log.emit, cancel=lambda: self._cancel, **self.kwargs)
            self.done.emit(res)
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(str(e))
