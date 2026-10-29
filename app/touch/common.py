"""Briques de l'interface tactile : thème mis à l'échelle de l'écran, clavier virtuel AZERTY,
listes à défilement au doigt (avec appui long), boîtes de dialogue à gros boutons."""
from PySide6.QtCore import Qt, Signal, QTimer, QSize, QPoint, QEvent
from PySide6.QtGui import QColor, QGuiApplication, QFont
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QLineEdit,
    QListWidget, QListWidgetItem, QScroller, QScrollerProperties, QAbstractItemView, QSlider,
    QSizePolicy, QFrame, QScrollArea,
)

U = 1.0  # facteur d'échelle (1 = écran 800×480)


def scale_for(w, h):
    """Échelle d'après la taille réelle : la mise en page de référence fait 800×480.
    En portrait (ex. 720×1280), c'est la largeur qui limite."""
    return max(0.6, min(w / 800, h / 480))


def init_scale(app):
    global U
    g = app.primaryScreen().availableGeometry()
    U = scale_for(g.width(), g.height())
    return U


def px(v):
    return int(round(v * U))


def stylesheet():
    f, f2, f3 = px(17), px(22), px(30)
    return f"""
* {{ font-family: 'Noto Sans', 'DejaVu Sans', 'Segoe UI'; font-size: {f}px; color: #e6edf3; }}
QWidget {{ background: #0d1117; }}
QLabel {{ background: transparent; }}
QLabel#h1 {{ font-size: {f3}px; font-weight: 700; }}
QLabel#h2 {{ font-size: {f2}px; font-weight: 600; }}
QLabel#dim {{ color: #8b949e; }}
QPushButton {{ background: #21262d; border: 1px solid #30363d; border-radius: {px(12)}px;
  padding: {px(5)}px {px(12)}px; min-height: {px(38)}px; }}
QPushButton:pressed {{ background: #30363d; }}
QPushButton:checked {{ background: #1f6feb; border-color: #388bfd; }}
QPushButton:disabled {{ color: #484f58; }}
QPushButton#primary {{ background: #238636; border-color: #2ea043; font-weight: 600; }}
QPushButton#danger {{ background: #8e1519; border-color: #da3633; }}
QPushButton#round {{ border-radius: {px(31)}px; min-width: {px(62)}px; min-height: {px(62)}px;
  max-width: {px(62)}px; max-height: {px(62)}px; font-size: {px(28)}px; background: #238636; padding: 0; }}
QPushButton#icon {{ min-width: {px(56)}px; max-width: {px(64)}px; font-size: {px(22)}px; padding: 0; }}
QPushButton#nav {{ border: none; border-radius: 0; background: #161b22; font-size: {px(15)}px;
  min-height: {px(48)}px; padding: {px(1)}px; }}
QPushButton#nav:checked {{ background: #1f2a3a; color: #58a6ff; border-top: {px(3)}px solid #58a6ff; }}
QPushButton#tile {{ font-size: {px(17)}px; min-height: {px(58)}px; text-align: left; padding-left: {px(18)}px; }}
QPushButton#seg {{ border-radius: 0; min-height: {px(36)}px; padding: {px(3)}px {px(6)}px; }}
QPushButton#small {{ min-height: {px(32)}px; min-width: {px(48)}px; padding: 0; font-size: {px(19)}px; }}
QPushButton#key {{ min-height: {px(30)}px; min-width: {px(10)}px; padding: 0; font-size: {px(20)}px; border-radius: {px(8)}px; }}
QLineEdit {{ background: #010409; border: 1px solid #30363d; border-radius: {px(10)}px; padding: {px(5)}px;
  font-size: {px(20)}px; min-height: {px(34)}px; }}
QListWidget {{ background: #0d1117; border: none; outline: 0; }}
QListWidget::item {{ min-height: {px(54)}px; border-bottom: 1px solid #21262d; padding-left: {px(6)}px; }}
QListWidget::item:selected {{ background: #1f2a3a; color: #58a6ff; }}
QSlider::groove:horizontal {{ height: {px(10)}px; background: #30363d; border-radius: {px(5)}px; }}
QSlider::sub-page:horizontal {{ background: #1f6feb; border-radius: {px(5)}px; }}
QSlider::handle:horizontal {{ background: #e6edf3; width: {px(34)}px; margin: -{px(12)}px 0; border-radius: {px(17)}px; }}
QSlider::groove:vertical {{ width: {px(10)}px; background: #30363d; border-radius: {px(5)}px; }}
QSlider::add-page:vertical {{ background: #1f6feb; border-radius: {px(5)}px; }}
QSlider::handle:vertical {{ background: #e6edf3; height: {px(30)}px; margin: 0 -{px(12)}px; border-radius: {px(15)}px; }}
QProgressBar {{ border: 1px solid #30363d; border-radius: {px(8)}px; text-align: center; min-height: {px(30)}px; }}
QProgressBar::chunk {{ background: #1f6feb; border-radius: {px(8)}px; }}
QPlainTextEdit {{ background: #010409; border: 1px solid #30363d; font-size: {px(14)}px; }}
QScrollBar {{ width: 0px; height: 0px; }}
QFrame#card {{ background: #161b22; border: 1px solid #30363d; border-radius: {px(14)}px; }}
"""


def label(text, obj=None, wrap=False):
    l = QLabel(text)
    if obj:
        l.setObjectName(obj)
    l.setWordWrap(wrap)
    return l


def button(text, slot=None, obj=None, checkable=False):
    b = QPushButton(text)
    if obj:
        b.setObjectName(obj)
    b.setCheckable(checkable)
    b.setFocusPolicy(Qt.NoFocus)
    if slot:
        b.clicked.connect(slot)
    return b


def kinetic(widget):
    """Défilement au doigt (avec inertie) pour une liste ou une zone défilante."""
    vp = widget.viewport() if hasattr(widget, "viewport") else widget
    QScroller.grabGesture(vp, QScroller.LeftMouseButtonGesture)
    sc = QScroller.scroller(vp)
    props = sc.scrollerProperties()
    props.setScrollMetric(QScrollerProperties.DragStartDistance, 0.004)
    props.setScrollMetric(QScrollerProperties.OvershootDragResistanceFactor, 0.3)
    props.setScrollMetric(QScrollerProperties.OvershootScrollDistanceFactor, 0.1)
    sc.setScrollerProperties(props)
    if isinstance(widget, QAbstractItemView):
        widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    return widget


def touch_slider(orient=Qt.Horizontal, lo=0, hi=100, value=0):
    s = QSlider(orient); s.setRange(lo, hi); s.setValue(int(value)); s.setFocusPolicy(Qt.NoFocus)
    s.setPageStep(max(1, (hi - lo) // 10))
    return s


# ------------------------------------------------------------------ liste tactile
class TouchList(QListWidget):
    """Liste à gros éléments, défilement au doigt, appui long = menu."""
    tapped = Signal(QListWidgetItem)
    long_pressed = Signal(QListWidgetItem)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIconSize(QSize(px(48), px(48)))
        self.setUniformItemSizes(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setFocusPolicy(Qt.NoFocus)
        kinetic(self)
        self._press = None
        self._long_done = False
        self._timer = QTimer(self); self._timer.setSingleShot(True); self._timer.timeout.connect(self._long)
        self.viewport().installEventFilter(self)

    def add(self, text, data=None, icon=None, sub=None, color=None):
        it = QListWidgetItem(text if not sub else f"{text}\n{sub}")
        it.setData(Qt.UserRole, data)
        if icon is not None:
            it.setIcon(icon)
        if color:
            it.setForeground(QColor(color))
        self.addItem(it)
        return it

    def eventFilter(self, obj, e):
        t = e.type()
        if t == QEvent.MouseButtonPress:
            self._press = e.position().toPoint(); self._long_done = False
            self._timer.start(650)
        elif t == QEvent.MouseMove and self._press is not None:
            if (e.position().toPoint() - self._press).manhattanLength() > px(14):
                self._timer.stop(); self._press = None
        elif t == QEvent.MouseButtonRelease:
            self._timer.stop()
            if self._press is not None and not self._long_done:
                it = self.itemAt(self._press)
                if it is not None:
                    self.setCurrentItem(it); self.tapped.emit(it)
            self._press = None
        return False

    def _long(self):
        if self._press is not None:
            it = self.itemAt(self._press)
            if it is not None:
                self._long_done = True
                self.setCurrentItem(it); self.long_pressed.emit(it)


# ------------------------------------------------------------------ boîtes de dialogue
class Sheet(QDialog):
    """Panneau modal centré, sans bordure de fenêtre."""

    def __init__(self, parent, title="", width=0.7, height=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        top = parent.window() if parent else None
        if top:
            g = top.geometry()
            w = int(g.width() * width)
            h = int(g.height() * height) if height else None
            self.setFixedWidth(w)
            if h:
                self.setFixedHeight(h)
        self.setStyleSheet(f"QDialog {{ background: #161b22; border: 2px solid #30363d; border-radius: {px(16)}px; }}")
        self.lay = QVBoxLayout(self); self.lay.setContentsMargins(px(18), px(14), px(18), px(14))
        if title:
            self.lay.addWidget(label(title, "h2", wrap=True))
        self.result_value = None

    def showEvent(self, e):
        super().showEvent(e)
        top = self.parent().window() if self.parent() else None
        if top:
            c = top.geometry().center()
            self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)


def ask(parent, title, text, buttons=("Oui", "Non"), primary=0):
    """Question à gros boutons. Renvoie l'index du bouton choisi (ou None)."""
    d = Sheet(parent, title, 0.6)
    if text:
        d.lay.addWidget(label(text, wrap=True))
    row = QHBoxLayout()
    for i, b in enumerate(buttons):
        btn = button(b, obj="primary" if i == primary else None)
        btn.clicked.connect(lambda _=False, i=i: (setattr(d, "result_value", i), d.accept()))
        row.addWidget(btn)
    d.lay.addLayout(row)
    d.exec()
    return d.result_value


def info(parent, title, text):
    ask(parent, title, text, ("OK",))


def choose(parent, title, options, current=None):
    """Liste de choix plein écran. options : [(libellé, valeur)]. Renvoie la valeur ou None."""
    d = Sheet(parent, title, 0.7, 0.85)
    lst = TouchList()
    for lab, val in options:
        it = lst.add(("✓  " if val == current else "     ") + lab, val)
        if val == current:
            lst.setCurrentItem(it)
    lst.tapped.connect(lambda it: (setattr(d, "result_value", ("ok", it.data(Qt.UserRole))), d.accept()))
    d.lay.addWidget(lst, 1)
    d.lay.addWidget(button("Annuler", d.reject))
    d.exec()
    return d.result_value[1] if d.result_value else None


def menu(parent, title, actions):
    """Menu d'actions : [(libellé, fonction)]."""
    opts = [(lab, i) for i, (lab, _) in enumerate(actions)]
    i = choose(parent, title, opts)
    if i is not None:
        actions[i][1]()


# ------------------------------------------------------------------ clavier virtuel
LAYOUTS = {
    "abc": ["1234567890", "azertyuiop", "qsdfghjklm", "⇧wxcvbn'⌫", "@?.,␣-✓"],
    "ABC": ["1234567890", "AZERTYUIOP", "QSDFGHJKLM", "⇧WXCVBN'⌫", "@?.,␣-✓"],
    "éà": ["éèêëàâäîïô", "ùûüçœæÉÈÀÇ", "«»“”…–—’°€", "⇧¿¡ñß§µ²⌫", "@?.,␣-✓"],
    "#+=": ["1234567890", "@#&_-+()/:", ";!?'\"=%*<>", "⇧[]{}|\\~^⌫", "@?.,␣-✓"],
}


class Keyboard(Sheet):
    """Clavier AZERTY à l'écran, avec accents et symboles (adresses web, clés…)."""

    def __init__(self, parent, title, text="", placeholder="", password=False):
        super().__init__(parent, title, 0.98, 0.96)
        self.edit = QLineEdit(text); self.edit.setPlaceholderText(placeholder)
        if password:
            self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setFocusPolicy(Qt.StrongFocus)
        top = QHBoxLayout(); top.addWidget(self.edit, 1)
        b_paste = button("Coller", self.paste); top.addWidget(b_paste)
        b_clear = button("Effacer", self.edit.clear); top.addWidget(b_clear)
        self.lay.addLayout(top)
        self.grid_host = QWidget(); self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(px(5)); self.grid.setContentsMargins(0, 0, 0, 0)
        self.lay.addWidget(self.grid_host, 1)
        mode_row = QHBoxLayout()
        for m in ("abc", "éà", "#+="):
            b = button(m, lambda _=False, m=m: self.set_mode(m)); b.setMinimumWidth(px(90)); mode_row.addWidget(b)
        mode_row.addStretch()
        mode_row.addWidget(button("Annuler", self.reject))
        mode_row.addWidget(button("Valider ✓", self.accept, obj="primary"))
        self.lay.addLayout(mode_row)
        self.mode = "abc"; self.shift_once = False
        self.set_mode("abc")
        self.edit.setFocus(); self.edit.deselect(); self.edit.end(False)

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, lambda: (self.edit.deselect(), self.edit.end(False)))

    def paste(self):
        t = QGuiApplication.clipboard().text()
        if t:
            self.edit.insert(t.strip())

    def set_mode(self, m):
        self.mode = m
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        for r, row in enumerate(LAYOUTS[m]):
            c = 0
            for ch in row:
                span = 4 if ch == "␣" else 2 if ch in "⇧⌫✓" else 1
                txt = {"␣": "espace", "⌫": "⌫", "⇧": "⇧", "✓": "OK"}.get(ch, ch)
                b = button(txt, lambda _=False, ch=ch: self.key(ch), obj="primary" if ch == "✓" else "key")
                b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                self.grid.addWidget(b, r, c, 1, span); c += span

    def key(self, ch):
        if ch == "⌫":
            self.edit.backspace()
        elif ch == "⇧":
            self.set_mode("abc" if self.mode == "ABC" else "ABC"); self.shift_once = self.mode == "ABC"
        elif ch == "✓":
            self.accept()
        else:
            self.edit.insert(" " if ch == "␣" else ch)
            if self.shift_once:
                self.shift_once = False; self.set_mode("abc")
        self.edit.setFocus()

    @classmethod
    def get(cls, parent, title, text="", placeholder="", password=False):
        k = cls(parent, title, text, placeholder, password)
        if k.exec():
            return k.edit.text()
        return None


class Toast(QLabel):
    """Petit message temporaire en bas de l'écran."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setStyleSheet(f"background:#1f6feb;color:white;border-radius:{px(12)}px;padding:{px(10)}px {px(18)}px;")
        self.hide()
        self.t = QTimer(self); self.t.setSingleShot(True); self.t.timeout.connect(self.hide)

    def show_msg(self, text, ms=3500):
        self.setText(text); self.adjustSize()
        p = self.parent()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - px(80))
        self.raise_(); self.show(); self.t.start(ms)
