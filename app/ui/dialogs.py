"""Fenêtres : rangement, identification, éditeur de tags, CD, YouTube, paramètres, effets."""
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap, QColor, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QComboBox, QCheckBox, QTableWidget, QTableWidgetItem, QProgressBar, QPlainTextEdit,
    QListWidget, QListWidgetItem, QSpinBox, QMessageBox, QHeaderView, QSlider, QGroupBox, QWidget,
    QDialogButtonBox, QRadioButton,
)

from ..config import settings, tool
from .. import organizer, identify, converters, setaside
from ..tags import read_tags, write_tags, read_cover
from .widgets import Worker, Knob, fit_to_screen

PATTERNS = {
    "Artiste / Album (Année) / 01 - Titre": "{artist}/{album}/{track:02d} - {title}",
    "Artiste / Album / Artiste - Titre": "{artist}/{album}/{track_artist} - {title}",
    "Genre / Artiste / Album / 01 - Titre": "{genre}/{artist}/{album}/{track:02d} - {title}",
    "Artiste / Artiste - Titre (sans album)": "{artist}/{track_artist} - {title}",
}


def pick_dir(parent, title, start=""):
    return QFileDialog.getExistingDirectory(parent, title, start or str(Path.home()))


class LogMixin:
    def _make_log(self, layout):
        self.bar = QProgressBar(); self.bar.setVisible(False)
        self.logbox = QPlainTextEdit(); self.logbox.setReadOnly(True); self.logbox.setMaximumBlockCount(3000)
        layout.addWidget(self.bar); layout.addWidget(self.logbox)

    def log(self, s):
        self.logbox.appendPlainText(s)

    def on_progress(self, a, b, txt):
        self.bar.setVisible(True); self.bar.setMaximum(max(b, 1)); self.bar.setValue(a)
        self.bar.setFormat(f"%v / %m   {Path(txt).name if txt else ''}")


# =============================================================== Rangement
class OrganizeDialog(QDialog, LogMixin):
    """On donne un emplacement (disque, clé USB) : le logiciel analyse, identifie et range."""
    finished_ok = Signal()

    def __init__(self, library, parent=None, source=""):
        super().__init__(parent)
        self.lib, self.moves, self.worker = library, [], None
        self.setWindowTitle("Ranger et classer un emplacement"); fit_to_screen(self, 1050, 680)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.src = QLineEdit(source); b1 = QPushButton("Parcourir…"); b1.clicked.connect(self.choose_src)
        row = QHBoxLayout(); row.addWidget(self.src); row.addWidget(b1)
        form.addRow("Emplacement à ranger (disque, clé USB, dossier) :", row)
        self.dst = QLineEdit(); self.dst.setPlaceholderText("(par défaut : <emplacement>\\Musique classée)")
        b2 = QPushButton("Parcourir…"); b2.clicked.connect(lambda: self.dst.setText(pick_dir(self, "Destination") or self.dst.text()))
        b3 = QPushButton("Ma bibliothèque"); b3.clicked.connect(lambda: self.dst.setText(settings["library_root"]))
        row2 = QHBoxLayout(); row2.addWidget(self.dst); row2.addWidget(b2); row2.addWidget(b3)
        form.addRow("Ranger dans :", row2)
        self.pattern = QComboBox(); self.pattern.addItems(PATTERNS)
        cur = [k for k, v in PATTERNS.items() if v == settings["rename_pattern"]]
        if cur:
            self.pattern.setCurrentText(cur[0])
        form.addRow("Classement :", self.pattern)
        opts = QHBoxLayout()
        self.rb_move = QRadioButton("Déplacer les fichiers"); self.rb_move.setChecked(True)
        self.rb_copy = QRadioButton("Copier (laisser les originaux)")
        self.cb_ident = QCheckBox("Identifier en ligne les titres incomplets avant de ranger")
        self.cb_ident.setChecked(bool(settings.get("acoustid_key")))
        self.cb_lib = QCheckBox("Ajouter à la bibliothèque"); self.cb_lib.setChecked(True)
        for w in (self.rb_move, self.rb_copy, self.cb_ident, self.cb_lib):
            opts.addWidget(w)
        form.addRow("Options :", opts)
        opts2 = QHBoxLayout()
        self.cb_dups = QCheckBox("Supprimer automatiquement les doublons (le meilleur exemplaire est gardé, les autres vont à la corbeille)")
        self.cb_dups.setChecked(settings.get("dup_delete", True))
        self.cb_wav = QCheckBox("Transformer les WAV, OGG et WMA en MP3")
        self.cb_wav.setChecked(settings.get("convert_wav", True))
        opts2.addWidget(self.cb_dups); opts2.addWidget(self.cb_wav); opts2.addStretch()
        form.addRow("", opts2)
        lay.addLayout(form)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["État", "Fichier actuel", "Nouvel emplacement", "Remarque"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table, 1)
        self.summary = QLabel(""); lay.addWidget(self.summary)
        self._make_log(lay); self.logbox.setMaximumHeight(110)
        btns = QHBoxLayout()
        self.b_scan = QPushButton("1. Analyser"); self.b_scan.clicked.connect(self.analyse)
        self.b_go = QPushButton("2. Ranger"); self.b_go.setEnabled(False); self.b_go.clicked.connect(self.apply)
        self.b_undo = QPushButton("Annuler le dernier rangement"); self.b_undo.clicked.connect(self.undo)
        self.b_stop = QPushButton("Stop"); self.b_stop.clicked.connect(lambda: self.worker and self.worker.cancel())
        for b in (self.b_scan, self.b_go, self.b_undo, self.b_stop):
            btns.addWidget(b)
        btns.addStretch(); close = QPushButton("Fermer"); close.clicked.connect(self.accept); btns.addWidget(close)
        lay.addLayout(btns)
        self.last_log = None

    def choose_src(self):
        d = pick_dir(self, "Emplacement à ranger")
        if d:
            self.src.setText(d)

    def _dest(self):
        return self.dst.text().strip() or str(Path(self.src.text()) / "Musique classée")

    def _run(self, fn, done, *args, **kw):
        self.worker = Worker(fn, *args, **kw)
        self.worker.progress.connect(self.on_progress); self.worker.log.connect(self.log)
        self.worker.done.connect(done)
        self.worker.failed.connect(lambda e: (QMessageBox.warning(self, "Erreur", e), self._busy(False)))
        self._busy(True); self.worker.start()

    def _busy(self, b):
        self.b_scan.setEnabled(not b); self.b_go.setEnabled(not b and bool(self.moves)); self.b_undo.setEnabled(not b)

    def analyse(self):
        src = self.src.text().strip()
        if not src or not Path(src).is_dir():
            QMessageBox.information(self, "Rangement", "Choisissez d'abord un emplacement."); return
        settings["rename_pattern"] = PATTERNS[self.pattern.currentText()]
        settings["dup_delete"] = self.cb_dups.isChecked(); settings["convert_wav"] = self.cb_wav.isChecked()
        settings.save()
        self._run(task_plan, self.show_plan, src, self._dest(), settings["rename_pattern"], self.cb_ident.isChecked(),
                  dup_mode="delete" if self.cb_dups.isChecked() else "aside", convert_wav=self.cb_wav.isChecked(),
                  existing=self.lib.tracks())

    def show_plan(self, moves):
        self._busy(False)
        self.moves = moves
        colors = {"déplacer": "#2ea043", "déjà rangé": "#8b949e", "doublon": "#f85149", "incomplet": "#f0883e",
                  "erreur": "#ff7b72",
                  "déjà présent": "#f85149", "remplace": "#58a6ff"}
        gone = "(non copié)" if self.rb_copy.isChecked() else "(supprimé → corbeille)"
        self.table.setRowCount(len(moves))
        src_root = self.src.text()
        for i, m in enumerate(moves):
            it = QTableWidgetItem(m.status); it.setForeground(QColor(colors.get(m.status, "#fff")))
            self.table.setItem(i, 0, it)
            self.table.setItem(i, 1, QTableWidgetItem(str(Path(m.src).relative_to(src_root)) if m.src.startswith(src_root) else m.src))
            dst_root = self._dest()
            dst_txt = "(laissé en place)" if m.status == "erreur" else gone if not m.dst else (str(Path(m.dst).relative_to(dst_root)) if m.dst.startswith(dst_root) else m.dst)
            self.table.setItem(i, 2, QTableWidgetItem(dst_txt))
            self.table.setItem(i, 3, QTableWidgetItem((f"{Path(m.src).suffix[1:].upper()} → MP3  " if m.convert else "") + m.reason))
        cnt = {}
        for m in moves:
            cnt[m.status] = cnt.get(m.status, 0) + 1
        self.summary.setText(f"{len(moves)} fichiers — " + ", ".join(f"{v} {k}" for k, v in cnt.items()) +
                             ("   (incomplet = rangé avec les infos disponibles ; complétez-les via « Identifier »)"
                              if cnt.get("incomplet") else ""))
        self.b_go.setEnabled(bool(moves))

    def apply(self):
        if not self.moves:
            return
        n = sum(m.src != m.dst and bool(m.dst) for m in self.moves)
        dups = sum(not m.dst for m in self.moves)
        verb = "copier" if self.rb_copy.isChecked() else "déplacer"
        extra = ""
        if dups:
            extra = (f"\n{dups} doublon(s) ne seront pas copiés." if self.rb_copy.isChecked()
                     else f"\n{dups} doublon(s) seront envoyés à la corbeille.")
        if QMessageBox.question(self, "Ranger", f"{verb.capitalize()} {n} fichiers ?{extra}") != QMessageBox.Yes:
            return
        lib = self.lib if self.cb_lib.isChecked() else None
        self._run(task_execute, self.applied, self.moves, self.rb_copy.isChecked(), lib)

    def applied(self, log_path):
        self._busy(False); self.last_log = log_path
        if self.cb_lib.isChecked():
            self.lib.scan(self._dest())
        self.log(f"Rangement terminé. Journal : {log_path}")
        self.moves = []; self.b_go.setEnabled(False)
        self.finished_ok.emit()
        QMessageBox.information(self, "Rangement", "Rangement terminé.")

    def undo(self):
        from ..config import data_dir
        logs = sorted(data_dir().glob("rangement_*.json"))
        if not logs:
            QMessageBox.information(self, "Annuler", "Aucun rangement à annuler."); return
        if QMessageBox.question(self, "Annuler", f"Remettre les fichiers à leur place d'origine ?\n({logs[-1].name})") != QMessageBox.Yes:
            return
        n = organizer.undo(logs[-1], self.lib)
        logs[-1].rename(logs[-1].with_suffix(".annule"))
        self.log(f"{n} fichiers remis en place."); self.finished_ok.emit()


def task_plan(src, dest, pattern, ident, progress, log, cancel, dup_mode="delete", convert_wav=True, existing=None):
    from ..library import iter_audio_files
    if ident:
        todo = []
        for f in iter_audio_files(src):
            try:
                if read_tags(f).is_incomplete:
                    todo.append(f)
            except Exception:              # illisible : l'analyse le signalera, on continue
                pass
        log(f"Identification en ligne de {len(todo)} titres incomplets…")
        aside = []
        for i, f in enumerate(todo):
            if cancel():
                break
            m, why = identify.identify_or_set_aside(f, log=log)
            if why:
                aside.append(f)
                log(f"⏸ mis de côté : {Path(f).name} — {why}")
            else:
                log(("✓ " + m.label()) if m else ("✗ non reconnu : " + Path(f).name))
            progress(i + 1, len(todo), f)
        if aside:
            log(f"{len(aside)} fichier(s) mis de côté, les autres ont été traités. "
                "Liste : menu Identifier ▸ Fichiers mis de côté.")
    log("Analyse des fichiers…")
    return organizer.plan(src, dest, pattern, progress=progress, cancel=cancel, dup_mode=dup_mode,
                          convert_wav=convert_wav, existing=existing)


def task_execute(moves, copy, lib, progress, log, cancel):
    return organizer.execute(moves, copy=copy, library=lib, progress=progress, cancel=cancel,
                             bitrate=settings.get("mp3_bitrate", 320), log_fn=log)


# =============================================================== Identification
class IdentifyDialog(QDialog):
    """Reconnaissance d'un titre par empreinte audio (ou nom de fichier) et choix de la proposition."""
    changed = Signal()

    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.paths, self.i, self.skipped = list(paths), 0, 0
        self.setWindowTitle("Identifier le titre (empreinte audio)"); fit_to_screen(self, 760, 520)
        lay = QVBoxLayout(self)
        self.head = QLabel(); self.head.setWordWrap(True); lay.addWidget(self.head)
        self.cur = QLabel(); self.cur.setStyleSheet("color:#8b949e"); lay.addWidget(self.cur)
        self.list = QListWidget(); lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.cb_over = QCheckBox("Remplacer les infos existantes"); self.cb_over.setChecked(True); self.cb_cover = QCheckBox("Ajouter la pochette")
        self.cb_cover.setChecked(True); row.addWidget(self.cb_over); row.addWidget(self.cb_cover); row.addStretch()
        lay.addLayout(row)
        manual = QHBoxLayout()
        self.q_artist = QLineEdit(); self.q_artist.setPlaceholderText("Artiste")
        self.q_title = QLineEdit(); self.q_title.setPlaceholderText("Titre")
        bq = QPushButton("Chercher"); bq.clicked.connect(self.search_text)
        manual.addWidget(QLabel("Recherche manuelle :")); manual.addWidget(self.q_artist); manual.addWidget(self.q_title); manual.addWidget(bq)
        lay.addLayout(manual)
        btns = QHBoxLayout()
        self.b_apply = QPushButton("Appliquer"); self.b_apply.clicked.connect(self.apply)
        b_skip = QPushButton("Passer"); b_skip.clicked.connect(self.next)
        b_close = QPushButton("Fermer"); b_close.clicked.connect(self.accept)
        btns.addStretch(); btns.addWidget(self.b_apply); btns.addWidget(b_skip); btns.addWidget(b_close)
        lay.addLayout(btns)
        self.list.itemDoubleClicked.connect(lambda _: self.apply())
        self.load()

    def load(self):
        if self.i >= len(self.paths):
            self.accept(); return
        p = self.paths[self.i]; t = read_tags(p)
        self.head.setText(f"<b>{self.i + 1}/{len(self.paths)}</b> — {Path(p).name}")
        self.cur.setText(f"Actuellement : {t.artist or '?'} — {t.title or '?'} [{t.album or '?'}]")
        self.q_artist.setText(t.artist); self.q_title.setText(t.title)
        self.list.clear()
        unlocked = []
        why = setaside.check_access(p, on_unlock=unlocked.append)
        if why:
            self.set_aside(why); return
        if unlocked:
            self.list.addItem("🔓 Lecture seule retirée pour pouvoir compléter ce fichier.")
        self.list.addItem("Écoute et recherche en cours…")
        if not settings.get("acoustid_key"):
            self.head.setText(self.head.text() + "<br><span style='color:#d29922'>Sans clé AcoustID (Paramètres), "
                              "la reconnaissance se fait seulement par le nom de fichier.</span>")
        self.w = Worker(lambda path, progress, log, cancel: identify.candidates(path), p)
        self.w.done.connect(self.show_cands)
        self.w.failed.connect(lambda e: self.list.addItem("Recherche impossible : " + organizer.friendly_error(Exception(e))
                                                          + ". Essayez la recherche manuelle ou « Passer »."))
        self.w.start()

    def set_aside(self, why):
        """Fichier protégé : noté dans « Fichiers mis de côté », puis passage automatique au suivant."""
        p = self.paths[self.i]
        setaside.add(p, why, "identification")
        why = setaside.short_reason(why)
        self.skipped += 1
        self.list.clear()
        self.list.addItem(f"⏸ {Path(p).name} est mis de côté : {why}.")
        self.list.addItem("Passage au titre suivant…" if self.i + 1 < len(self.paths) else
                          "C'était le dernier titre. Liste : menu Identifier ▸ Fichiers mis de côté.")
        self.b_apply.setEnabled(True)
        idx = self.i     # « Passer » cliqué entre-temps : ne pas sauter un titre de plus
        QTimer.singleShot(1800 if self.i + 1 < len(self.paths) else 3500,
                          lambda: self.next() if self.i == idx and self.isVisible() else None)

    def search_text(self):
        self.list.clear(); self.list.addItem("Recherche…")
        self.w = Worker(lambda a, t, progress, log, cancel: identify.by_text(a, t, 10),
                        self.q_artist.text(), self.q_title.text())
        self.w.done.connect(self.show_cands); self.w.start()

    def show_cands(self, cands):
        self.list.clear()
        if not cands:
            self.list.addItem("Aucun résultat. Essayez la recherche manuelle."); return
        for c in cands:
            it = QListWidgetItem(c.label()); it.setData(Qt.UserRole, c); self.list.addItem(it)
        self.list.setCurrentRow(0)

    def apply(self):
        it = self.list.currentItem()
        m = it.data(Qt.UserRole) if it else None
        if m is None:
            return
        self.b_apply.setEnabled(False); self.list.clear(); self.list.addItem("Récupération de l'album et de la pochette…")
        p = self.paths[self.i]

        def job(progress, log, cancel):
            try:
                full = identify.complete(m, read_tags(p).album)
                identify.apply_match(p, full, overwrite=self.cb_over.isChecked(), with_cover=self.cb_cover.isChecked())
            except Exception as e:          # noqa: BLE001 - accès refusé… : mis de côté, on continue
                return organizer.friendly_error(e)
            setaside.remove([p])
            return None
        self.w = Worker(job)
        self.w.done.connect(lambda why: self.set_aside(why) if why else
                            (self.b_apply.setEnabled(True), self.changed.emit(), self.next()))
        self.w.failed.connect(lambda e: self.set_aside(organizer.friendly_error(Exception(e))))
        self.w.start()

    def next(self):
        if self.i < len(self.paths):
            self.i += 1
            self.load()


class BatchIdentifyDialog(QDialog, LogMixin):
    changed = Signal()

    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compléter automatiquement les métadonnées"); fit_to_screen(self, 720, 460)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"{len(paths)} titres à identifier. Seules les correspondances sûres (≥ 80 %) sont appliquées ;"
                             " les autres restent à faire à la main via « Identifier… »."))
        self._make_log(lay)
        b = QPushButton("Arrêter"); lay.addWidget(b)
        self.w = Worker(self.job, paths)
        b.clicked.connect(self.w.cancel)
        self.w.progress.connect(self.on_progress); self.w.log.connect(self.log)
        self.w.done.connect(lambda r: (self.log(f"Terminé : {r[0]} identifiés, {r[1]} non reconnus"
                                                 + (f", {r[2]} mis de côté (menu Identifier ▸ Fichiers mis de côté)."
                                                    if r[2] else ".")), self.changed.emit()))
        self.w.failed.connect(lambda e: self.log("Arrêt inattendu : " + e))
        self.w.start()

    @staticmethod
    def job(paths, progress, log, cancel):
        ok = ko = aside = 0
        if not settings.get("acoustid_key"):
            log("Pas de clé AcoustID : recherche par nom de fichier uniquement (moins fiable).")
        for i, p in enumerate(paths):
            if cancel():
                break
            m, why = identify.identify_or_set_aside(p, log=log)
            if why:
                aside += 1; log(f"⏸ mis de côté : {Path(p).name} — {why}")
            elif m:
                ok += 1; log("✓ " + m.label())
            else:
                ko += 1; log("✗ " + Path(p).name)
            progress(i + 1, len(paths), p)
        return ok, ko, aside


class SetAsideDialog(QDialog):
    """Liste des fichiers mis de côté pendant l'identification, avec Réessayer / Ouvrir le dossier / Retirer."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fichiers mis de côté"); fit_to_screen(self, 1050, 480)
        lay = QVBoxLayout(self)
        intro = QLabel("Ces fichiers ont été sautés parce qu'ils n'ont pas pu être lus ou modifiés : fichier ouvert "
                       "dans un autre programme, en lecture seule, dossier ou clé USB protégés… "
                       "Fermez le programme concerné (lecteur, explorateur de fichiers, antivirus…) puis cliquez "
                       "sur « Réessayer ».")
        intro.setWordWrap(True); lay.addWidget(intro)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Fichier", "Raison", "Date", "Dossier"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemDoubleClicked.connect(lambda _: self.open_folder())
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        for text, fn in (("Réessayer tout", self.retry_all), ("Réessayer la sélection", self.retry_sel),
                         ("Ouvrir le dossier", self.open_folder), ("Retirer de la liste", self.remove_sel)):
            b = QPushButton(text); b.clicked.connect(fn); row.addWidget(b)
        row.addStretch()
        b = QPushButton("Fermer"); b.clicked.connect(self.accept); row.addWidget(b)
        lay.addLayout(row)
        self.refresh()

    def refresh(self):
        items = setaside.load()
        self.table.setRowCount(len(items))
        for r, it in enumerate(items):
            p = Path(it["path"])
            for c, v in enumerate((p.name, it.get("reason", ""), it.get("date", ""), str(p.parent))):
                cell = QTableWidgetItem(v); cell.setData(Qt.UserRole, it["path"]); cell.setToolTip(it["path"])
                self.table.setItem(r, c, cell)
        self.table.resizeColumnsToContents()
        self.setWindowTitle(f"Fichiers mis de côté ({len(items)})")

    def selected(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        return [self.table.item(r, 0).data(Qt.UserRole) for r in sorted(rows)]

    def retry(self, paths):
        if not paths:
            return
        d = BatchIdentifyDialog(paths, self)
        d.changed.connect(lambda: (self.refresh(), self.changed.emit()))
        d.exec()
        self.refresh()

    def retry_all(self):
        self.retry(setaside.paths())

    def retry_sel(self):
        self.retry(self.selected())

    def open_folder(self):
        sel = self.selected()
        if sel:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(sel[0]).parent)))

    def remove_sel(self):
        setaside.remove(self.selected()); self.refresh(); self.changed.emit()


# =============================================================== Éditeur de tags
class TagEditor(QDialog):
    FIELDS = [("title", "Titre"), ("artist", "Artiste"), ("album_artist", "Artiste de l'album"),
              ("album", "Album"), ("track", "N° de piste"), ("disc", "Disque"), ("year", "Année"), ("genre", "Genre")]

    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.paths, self.cover = list(paths), None
        multi = len(paths) > 1
        self.setWindowTitle(f"Modifier les informations ({len(paths)} fichier{'s' if multi else ''})")
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        self.pic = QLabel(); self.pic.setFixedSize(200, 200); self.pic.setAlignment(Qt.AlignCenter)
        self.pic.setStyleSheet("background:#161b22;border:1px solid #30363d")
        c = read_cover(paths[0])
        self._show_cover(c)
        bc = QPushButton("Changer la pochette…"); bc.clicked.connect(self.pick_cover)
        left.addWidget(self.pic); left.addWidget(bc); left.addStretch(); lay.addLayout(left)
        right = QVBoxLayout(); form = QFormLayout(); self.edits = {}
        infos = [read_tags(p) for p in paths]
        for key, lab in self.FIELDS:
            vals = {str(getattr(t, key) or "") for t in infos}
            e = QLineEdit(vals.pop() if len(vals) == 1 else "")
            if multi and len(vals) >= 1:
                e.setPlaceholderText("(valeurs différentes — laisser vide pour ne pas changer)")
            if multi and key in ("title", "track"):
                e.setEnabled(False); e.setPlaceholderText("(propre à chaque fichier)")
            form.addRow(lab, e); self.edits[key] = e
        right.addLayout(form)
        if not multi:
            right.addWidget(QLabel(f"<small>{paths[0]}<br>{infos[0].bitrate} kbit/s</small>"))
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.save); bb.rejected.connect(self.reject); right.addWidget(bb)
        lay.addLayout(right)

    def _show_cover(self, data):
        pm = QPixmap()
        if data and pm.loadFromData(data):
            self.pic.setPixmap(pm.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.pic.setText("Pas de pochette")

    def pick_cover(self):
        f, _ = QFileDialog.getOpenFileName(self, "Image de pochette", "", "Images (*.jpg *.jpeg *.png)")
        if f:
            self.cover = Path(f).read_bytes(); self._show_cover(self.cover)

    def save(self):
        vals = {k: (e.text().strip() or None) for k, e in self.edits.items() if e.isEnabled()}
        for k in ("track", "disc"):
            if vals.get(k):
                try:
                    vals[k] = int(vals[k])
                except ValueError:
                    vals[k] = None
        failed = []
        for p in self.paths:
            try:
                write_tags(p, cover=self.cover, **vals)
            except Exception as e:
                failed.append(f"{Path(p).name} : {organizer.friendly_error(e)}")
        if failed:
            QMessageBox.warning(self, "Informations", "Ces fichiers n'ont pas pu être modifiés :\n\n" + "\n".join(failed[:15]))
        self.accept()


# =============================================================== CD -> MP3
class CdDialog(QDialog, LogMixin):
    imported = Signal(list)

    def __init__(self, library, parent=None):
        super().__init__(parent)
        self.lib = library
        self.setWindowTitle("Extraire un CD audio en MP3"); fit_to_screen(self, 720, 520)
        lay = QVBoxLayout(self); form = QFormLayout()
        self.drive = QComboBox(); self.drive.addItems(converters.cd_drives() or ["(aucun lecteur détecté)"])
        self.drive.setEditable(True)
        form.addRow("Lecteur CD :", self.drive)
        self.bitrate = QComboBox(); self.bitrate.addItems(["320", "256", "192", "128"])
        self.bitrate.setCurrentText(str(settings["mp3_bitrate"])); form.addRow("Qualité MP3 (kbit/s) :", self.bitrate)
        self.album = QLineEdit(); self.album.setPlaceholderText("Seulement si le CD n'est pas reconnu")
        self.artist = QLineEdit(); self.artist.setPlaceholderText("Seulement si le CD n'est pas reconnu")
        form.addRow("Album :", self.album); form.addRow("Artiste :", self.artist)
        self.dest = QLineEdit(settings["library_root"]); form.addRow("Ranger dans :", self.dest)
        lay.addLayout(form)
        lay.addWidget(QLabel("Les titres, l'album, l'année et la pochette sont récupérés automatiquement sur MusicBrainz."))
        self._make_log(lay)
        btns = QHBoxLayout()
        b_info = QPushButton("Lire les infos du disque"); b_info.clicked.connect(self.info)
        self.b_rip = QPushButton("Extraire en MP3"); self.b_rip.clicked.connect(self.rip)
        b_stop = QPushButton("Stop"); b_stop.clicked.connect(lambda: getattr(self, "w", None) and self.w.cancel())
        btns.addWidget(b_info); btns.addWidget(self.b_rip); btns.addWidget(b_stop); btns.addStretch()
        lay.addLayout(btns)
        if not tool("cyanrip"):
            self.log("⚠ L'outil d'extraction (cyanrip) est absent : lancez installer.bat.")

    def info(self):
        self.w = Worker(lambda d, progress, log, cancel: converters.cd_info(d, log=log), self.drive.currentText())
        self.w.log.connect(self.log); self.w.failed.connect(self.log); self.w.start()

    def rip(self):
        self.b_rip.setEnabled(False)
        drive, br, dest = self.drive.currentText(), int(self.bitrate.currentText()), self.dest.text()
        album, artist = self.album.text().strip() or None, self.artist.text().strip() or None

        def job(progress, log, cancel):
            files = converters.rip_cd(drive, br, log=log, cancel=cancel, album=album, artist=artist)
            log(f"{len(files)} pistes extraites. Rangement dans la bibliothèque…")
            moves = organizer.plan(Path(files[0]).parent, dest, settings["rename_pattern"]) if files else []
            organizer.execute(moves, library=self.lib)
            return [m.dst for m in moves]
        self.w = Worker(job)
        self.w.log.connect(self.log); self.w.progress.connect(self.on_progress)
        self.w.done.connect(lambda r: (self.b_rip.setEnabled(True), self.log("Terminé ✓"), self.imported.emit(r)))
        self.w.failed.connect(lambda e: (self.b_rip.setEnabled(True), self.log("Erreur : " + e)))
        self.w.start()


# =============================================================== YouTube -> MP3
class YoutubeDialog(QDialog, LogMixin):
    imported = Signal(list)

    def __init__(self, library, parent=None):
        super().__init__(parent)
        self.lib = library
        self.setWindowTitle("Convertir un lien YouTube en MP3"); fit_to_screen(self, 720, 480)
        lay = QVBoxLayout(self); form = QFormLayout()
        self.url = QLineEdit(); self.url.setPlaceholderText("https://www.youtube.com/watch?v=…  (vidéo ou playlist)")
        form.addRow("Lien :", self.url)
        self.bitrate = QComboBox(); self.bitrate.addItems(["320", "256", "192", "128"])
        self.bitrate.setCurrentText(str(settings["mp3_bitrate"])); form.addRow("Qualité MP3 (kbit/s) :", self.bitrate)
        self.cb_pl = QCheckBox("Télécharger toute la playlist si le lien en contient une")
        self.cb_id = QCheckBox("Compléter les métadonnées (album, année, pochette) en ligne")
        self.cb_id.setChecked(True)
        self.cb_rank = QCheckBox("Ranger dans la bibliothèque"); self.cb_rank.setChecked(True)
        form.addRow("", self.cb_pl); form.addRow("", self.cb_id); form.addRow("", self.cb_rank)
        lay.addLayout(form)
        lay.addWidget(QLabel("<small>À utiliser pour des contenus que vous avez le droit de télécharger "
                             "(vos vidéos, contenus libres de droits ou autorisés).</small>"))
        self._make_log(lay)
        self.b_go = QPushButton("Convertir"); self.b_go.clicked.connect(self.go); lay.addWidget(self.b_go)

    def go(self):
        url = self.url.text().strip()
        if not url:
            return
        self.b_go.setEnabled(False)
        br, pl, ident, rank = int(self.bitrate.currentText()), self.cb_pl.isChecked(), self.cb_id.isChecked(), self.cb_rank.isChecked()
        dl_dir = Path(settings["library_root"]) / "_Téléchargements"

        def job(progress, log, cancel):
            files = converters.youtube_to_mp3(url, dl_dir, br, log=log, progress=progress, playlist=pl)
            if ident:
                for f in files:
                    m = identify.auto_identify(f, min_score=0.7)
                    log(("Reconnu : " + m.label()) if m else f"Non reconnu (infos YouTube conservées) : {Path(f).name}")
            if rank and files:
                moves = [m for m in organizer.plan(dl_dir, settings["library_root"], settings["rename_pattern"])
                         if m.src in files]
                organizer.execute(moves, library=self.lib)
                return [m.dst for m in moves]
            for f in files:
                self.lib.upsert(read_tags(f))
            return files
        self.w = Worker(job)
        self.w.log.connect(self.log); self.w.progress.connect(self.on_progress)
        self.w.done.connect(lambda r: (self.b_go.setEnabled(True), self.log(f"Terminé ✓ ({len(r)} fichier(s))"), self.imported.emit(r)))
        self.w.failed.connect(lambda e: (self.b_go.setEnabled(True), self.log("Erreur : " + e)))
        self.w.start()


# =============================================================== Paramètres
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paramètres"); fit_to_screen(self, 640, 260)
        lay = QVBoxLayout(self); form = QFormLayout()
        self.root = QLineEdit(settings["library_root"])
        b = QPushButton("…"); b.clicked.connect(lambda: self.root.setText(pick_dir(self, "Dossier de la bibliothèque") or self.root.text()))
        r = QHBoxLayout(); r.addWidget(self.root); r.addWidget(b)
        form.addRow("Dossier de la bibliothèque :", r)
        self.key = QLineEdit(settings["acoustid_key"])
        link = QLabel('<a href="https://acoustid.org/new-application">Obtenir une clé gratuite</a>')
        link.setOpenExternalLinks(True)
        r2 = QHBoxLayout(); r2.addWidget(self.key); r2.addWidget(link)
        form.addRow("Clé AcoustID (reconnaissance) :", r2)
        self.bitrate = QComboBox(); self.bitrate.addItems(["320", "256", "192", "128"])
        self.bitrate.setCurrentText(str(settings["mp3_bitrate"])); form.addRow("Qualité MP3 par défaut :", self.bitrate)
        lay.addLayout(form)
        status = []
        for name, what in (("ffmpeg", "lecture/conversion"), ("fpcalc", "empreinte audio"), ("cyanrip", "extraction CD")):
            status.append(f"{'✓' if tool(name) else '✗'} {name} ({what})")
        lay.addWidget(QLabel("Outils : " + "   ".join(status)))
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.save); bb.rejected.connect(self.reject); lay.addWidget(bb)

    def save(self):
        settings["library_root"] = self.root.text().strip()
        settings["acoustid_key"] = self.key.text().strip()
        settings["mp3_bitrate"] = int(self.bitrate.currentText())
        settings.save(); self.accept()
