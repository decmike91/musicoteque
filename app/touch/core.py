"""Logique partagée de l'interface tactile : file de lecture, détection des clés USB,
tâches longues avec progression, explorateur de dossiers au doigt."""
import json
import os
import random
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QTimer, Qt
from PySide6.QtWidgets import QHBoxLayout, QProgressBar, QPlainTextEdit

from ..config import settings, AUDIO_EXTS
from ..tags import read_tags
from ..ui.widgets import Worker
from .common import Sheet, TouchList, button, label, px


from ..playqueue import PlayQueue  # noqa: F401  (partagée avec la version Windows)


# ------------------------------------------------------------------ clés USB / disques
MEDIA_ROOTS = ("/media", "/run/media", "/mnt")


def mounted_media() -> dict[str, str]:
    """{point de montage: nom} des supports amovibles montés (clés USB, disques externes, cartes SD)."""
    out = {}
    try:
        lines = Path("/proc/mounts").read_text().splitlines()
    except OSError:
        return out
    for ln in lines:
        parts = ln.split()
        if len(parts) < 2:
            continue
        mp = parts[1].replace("\\040", " ")
        if mp.startswith(MEDIA_ROOTS) and mp not in MEDIA_ROOTS:
            out[mp] = Path(mp).name
    return out


def has_audio(path, limit=4000) -> bool:
    n = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith((".", "$")) and d != "System Volume Information"]
        for f in files:
            if Path(f).suffix.lower() in AUDIO_EXTS:
                return True
            n += 1
            if n > limit:
                return False
    return False


class MediaWatcher(QObject):
    """Surveille le branchement / débranchement des supports. Monte automatiquement les clés
    USB (via udisks) quand aucun bureau ne le fait (Raspberry Pi OS Lite)."""
    added = Signal(str, str)
    removed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.known = mounted_media()
        self.tried = set()
        self.t = QTimer(self); self.t.timeout.connect(self.poll); self.t.start(3000)

    def automount(self):
        if not shutil.which("lsblk") or not shutil.which("udisksctl"):
            return
        try:
            r = subprocess.run(["lsblk", "-J", "-o", "NAME,RM,HOTPLUG,MOUNTPOINT,FSTYPE,TYPE"],
                               capture_output=True, text=True, timeout=5)
            devs = json.loads(r.stdout).get("blockdevices", [])
        except (OSError, ValueError, subprocess.SubprocessError):
            return
        truthy = lambda v: v in (True, "1", 1, "true")

        def walk(nodes, removable=False):
            for d in nodes:
                rm = removable or truthy(d.get("rm")) or truthy(d.get("hotplug"))
                if rm and d.get("fstype") and d.get("fstype") != "swap" and not d.get("mountpoint") \
                        and d.get("type") in ("part", "disk") and d["name"] not in self.tried:
                    self.tried.add(d["name"])
                    subprocess.run(["udisksctl", "mount", "-b", f"/dev/{d['name']}", "--no-user-interaction"],
                                   capture_output=True, timeout=20)
                walk(d.get("children", []), rm)
        walk(devs)

    def poll(self):
        self.automount()
        now = mounted_media()
        for mp, name in now.items():
            if mp not in self.known:
                self.added.emit(mp, name)
        for mp in list(self.known):
            if mp not in now:
                self.removed.emit(mp)
                self.tried.clear()   # le support pourra être remonté s'il est rebranché
        self.known = now

    @staticmethod
    def eject(mountpoint) -> str:
        """Démonte puis met hors tension le support (retrait sans risque)."""
        dev = None
        for ln in Path("/proc/mounts").read_text().splitlines():
            p = ln.split()
            if len(p) > 1 and p[1].replace("\\040", " ") == mountpoint:
                dev = p[0]
        if not dev:
            return "Support introuvable."
        r = subprocess.run(["udisksctl", "unmount", "-b", dev], capture_output=True, text=True)
        if r.returncode != 0:
            r2 = subprocess.run(["umount", mountpoint], capture_output=True, text=True)
            if r2.returncode != 0:
                return "Impossible de l'éjecter (fichier en cours d'utilisation ?)"
        disk = dev.rstrip("0123456789")
        if disk.endswith("p") and disk[:-1][-1:].isdigit():
            disk = disk[:-1]
        subprocess.run(["udisksctl", "power-off", "-b", disk], capture_output=True)
        return ""


# ------------------------------------------------------------------ tâches longues
class ProgressSheet(Sheet):
    """Exécute une tâche en arrière-plan avec barre de progression et journal."""

    def __init__(self, parent, title, fn, *args, on_done=None, **kw):
        super().__init__(parent, title, 0.9, 0.85)
        self.bar = QProgressBar(); self.bar.setRange(0, 0); self.lay.addWidget(self.bar)
        self.now = label("", "dim"); self.lay.addWidget(self.now)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(2000)
        self.lay.addWidget(self.log, 1)
        row = QHBoxLayout()
        self.b_stop = button("Arrêter", self.stop, obj="danger")
        self.b_close = button("Fermer", self.accept); self.b_close.setEnabled(False)
        row.addWidget(self.b_stop); row.addStretch(); row.addWidget(self.b_close)
        self.lay.addLayout(row)
        self.result = None
        self.on_done = on_done
        self.w = Worker(fn, *args, **kw)
        self.w.progress.connect(self._progress)
        self.w.log.connect(self.log.appendPlainText)
        self.w.done.connect(self._done)
        self.w.failed.connect(self._failed)
        self.w.start()

    def _progress(self, a, b, txt):
        self.bar.setRange(0, max(1, b)); self.bar.setValue(a)
        self.now.setText(f"{a} / {b}   {Path(txt).name if txt else ''}")

    def _finish(self):
        self.b_stop.setEnabled(False); self.b_close.setEnabled(True)
        self.bar.setRange(0, 1); self.bar.setValue(1)

    def _done(self, r):
        self.result = r; self._finish()
        if self.on_done:
            msg = self.on_done(r)
            if msg:
                self.log.appendPlainText(msg)
        self.log.appendPlainText("Terminé ✓")

    def _failed(self, e):
        self._finish(); self.log.appendPlainText("Erreur : " + e)

    def stop(self):
        self.w.cancel(); self.log.appendPlainText("Arrêt demandé…")

    def reject(self):
        if self.w.isRunning():
            self.stop(); return
        super().reject()


def run_task(parent, title, fn, *args, on_done=None, **kw):
    d = ProgressSheet(parent, title, fn, *args, on_done=on_done, **kw)
    d.exec()
    return d.result


# ------------------------------------------------------------------ explorateur de dossiers
def browse_folder(parent, title, start=None):
    """Choix d'un dossier au doigt. Renvoie le chemin ou None."""
    d = Sheet(parent, title, 0.85, 0.9)
    cur = [Path(start) if start and Path(start).is_dir() else Path.home()]
    path_lbl = label("", "dim", wrap=True); d.lay.addWidget(path_lbl)
    lst = TouchList(); d.lay.addWidget(lst, 1)

    def fill():
        lst.clear(); path_lbl.setText(str(cur[0]))
        if cur[0].parent != cur[0]:
            lst.add("⬆  Dossier parent", cur[0].parent)
        for mp, name in mounted_media().items():
            if cur[0] == Path.home():
                lst.add(f"💾  {name} (support amovible)", Path(mp))
        try:
            subs = sorted((p for p in cur[0].iterdir() if p.is_dir() and not p.name.startswith(".")),
                          key=lambda p: p.name.lower())
        except OSError:
            subs = []
        for p in subs:
            lst.add(f"📁  {p.name}", p)

    def go(it):
        cur[0] = it.data(Qt.UserRole); fill()
    lst.tapped.connect(go)
    row = QHBoxLayout()
    row.addWidget(button("🏠 Dossier personnel", lambda: (cur.__setitem__(0, Path.home()), fill())))
    row.addStretch()
    row.addWidget(button("Annuler", d.reject))
    row.addWidget(button("Choisir ce dossier", lambda: (setattr(d, "result_value", str(cur[0])), d.accept()), obj="primary"))
    d.lay.addLayout(row)
    fill()
    d.exec()
    return d.result_value
