"""Page « Outils » tactile : rangement d'une clé USB / d'un disque, identification,
CD → MP3, YouTube → MP3, paramètres, extinction."""
import glob
import os
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout

from ..config import settings
from .. import organizer, identify, converters
from ..tags import read_tags
from ..ui.dialogs import task_plan, task_execute, BatchIdentifyDialog
from .common import px, label, button, touch_slider, Sheet, ask, info, choose, menu, Keyboard
from .core import run_task, browse_folder, mounted_media, MediaWatcher


class ToolsPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self); lay.setContentsMargins(px(10), px(8), px(10), px(4))
        lay.addWidget(label("Outils", "h2"))
        g = QGridLayout(); g.setSpacing(px(10))
        tiles = [
            ("🗂  Ranger une clé USB\n     ou un disque", self.organize),
            ("🎵  Compléter les infos\n     manquantes", self.identify_all),
            ("💿  CD audio → MP3", self.rip_cd),
            ("▶  YouTube → MP3", self.youtube),
            ("🔄  Actualiser la\n     bibliothèque", self.rescan),
            ("⏏  Éjecter un support", self.eject),
            ("📶  Bluetooth\n     (casque, enceinte)", self.bluetooth),
            ("📱  Télécommande\n     (téléphone Android)", self.remote_panel),
            ("❓  Aide\n     (mode d'emploi)", self.show_help),
            ("⚙  Paramètres", self.settings_menu),
            ("⏻  Éteindre /\n     redémarrer", self.power),
        ]
        self.grid = g
        self.tiles = [button(t, fn, obj="tile") for t, fn in tiles]
        from PySide6.QtWidgets import QSizePolicy
        for b in self.tiles:   # les tuiles grandissent avec l'écran, sans excès
            b.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding); b.setMaximumHeight(px(150))
        self._cols = 0
        self._layout_tiles(3)
        lay.addLayout(g, 1)
        self.stats = label("", "dim", wrap=True); lay.addWidget(self.stats)
        self.refresh_stats()

    def _layout_tiles(self, cols):
        """Nombre de colonnes selon la largeur de l'écran (2 en portrait, jusqu'à 4 en grand écran)."""
        if cols == self._cols:
            return
        self._cols = cols
        for b in self.tiles:
            self.grid.removeWidget(b)
        for i, b in enumerate(self.tiles):
            self.grid.addWidget(b, i // cols, i % cols)

    def resizeEvent(self, e):
        self._layout_tiles(max(2, min(4, self.width() // px(250))))
        super().resizeEvent(e)

    def refresh_stats(self):
        s = self.app.lib.stats()
        h = int(s["d"] // 3600)
        self.stats.setText(f"Bibliothèque : {s['n']} titres · {s['a'] or 0} artistes · {s['al'] or 0} albums · "
                           f"{h} h de musique · {s['inc'] or 0} titres aux infos incomplètes")
        self.stats.setToolTip(settings["library_root"])

    # ------------------------------------------------------------------ rangement
    def organize(self, source=None):
        if not source:
            opts = [(f"💾  {name}   ({mp})", mp) for mp, name in mounted_media().items()]
            opts += [("📁  Ma bibliothèque (la réorganiser)", settings["library_root"]),
                     ("📂  Choisir un autre dossier…", "__browse__")]
            source = choose(self, "Que faut-il ranger ?", opts)
            if source == "__browse__":
                source = browse_folder(self, "Dossier à ranger")
        if not source:
            return
        lib_root = settings["library_root"]
        is_lib = Path(source).resolve() == Path(lib_root).resolve()
        # options
        d = Sheet(self, f"Ranger « {Path(source).name or source} »", 0.75)
        if not is_lib:
            d.lay.addWidget(label("Où ranger la musique ?"))
            r = QHBoxLayout()
            b_lib = button("Dans ma bibliothèque", checkable=True); b_here = button("Sur le support lui-même", checkable=True)
            b_lib.setChecked(True)
            b_lib.clicked.connect(lambda: (b_lib.setChecked(True), b_here.setChecked(False)))
            b_here.clicked.connect(lambda: (b_here.setChecked(True), b_lib.setChecked(False)))
            r.addWidget(b_lib); r.addWidget(b_here); d.lay.addLayout(r)
            d.lay.addWidget(label("Les fichiers d'origine :"))
            r = QHBoxLayout()
            b_copy = button("Copier (garder les originaux)", checkable=True); b_move = button("Déplacer", checkable=True)
            b_copy.setChecked(True)
            b_copy.clicked.connect(lambda: (b_copy.setChecked(True), b_move.setChecked(False)))
            b_move.clicked.connect(lambda: (b_move.setChecked(True), b_copy.setChecked(False)))
            r.addWidget(b_copy); r.addWidget(b_move); d.lay.addLayout(r)
        b_id = button("Identifier en ligne les titres sans infos (plus long)", checkable=True)
        b_id.setChecked(bool(settings.get("acoustid_key")))
        r = QHBoxLayout()
        b_dup = button("Supprimer les doublons", checkable=True); b_dup.setChecked(settings.get("dup_delete", True))
        b_wav = button("WAV/OGG/WMA → MP3", checkable=True); b_wav.setChecked(settings.get("convert_wav", True))
        r.addWidget(b_dup, 2); r.addWidget(b_wav, 1); d.lay.addLayout(r)
        d.lay.addWidget(b_id)
        r = QHBoxLayout(); r.addWidget(button("Annuler", d.reject)); r.addStretch()
        r.addWidget(button("Analyser ▸", d.accept, obj="primary")); d.lay.addLayout(r)
        if not d.exec():
            return
        if is_lib:
            dest, copy = lib_root, False
        else:
            dest = lib_root if b_lib.isChecked() else str(Path(source) / "Musique classée")
            copy = b_copy.isChecked()
        ident = b_id.isChecked()
        settings["dup_delete"], settings["convert_wav"] = b_dup.isChecked(), b_wav.isChecked(); settings.save()
        # en déplacement on identifie avant de ranger ; en copie, après (on ne modifie pas les originaux)
        moves = run_task(self, "Analyse en cours…", task_plan, source, dest, settings["rename_pattern"],
                         ident and not copy, dup_mode="delete" if b_dup.isChecked() else "aside",
                         convert_wav=b_wav.isChecked(), existing=self.app.lib.tracks())
        if not moves:
            info(self, "Rangement", "Aucun fichier audio trouvé."); return
        cnt = {}
        for m in moves:
            cnt[m.status] = cnt.get(m.status, 0) + 1
        todo = sum(m.src != m.dst and bool(m.dst) for m in moves)
        ndup = cnt.get("doublon", 0) + cnt.get("déjà présent", 0)
        nwav = sum(m.convert for m in moves)
        dup_txt = ("ne seront pas copiés" if copy else "iront à la corbeille") if b_dup.isChecked() else "mis à part dans « _Doublons »"
        txt = (f"{len(moves)} fichiers trouvés.\n"
               f"• {cnt.get('déplacer', 0)} complets, {cnt.get('incomplet', 0)} aux infos incomplètes\n"
               f"• {ndup} doublons ou déjà dans la bibliothèque : {dup_txt}\n"
               + (f"• {cnt.get('remplace', 0)} remplaceront une version de moins bonne qualité\n" if cnt.get("remplace") else "")
               + (f"• {nwav} WAV / OGG / WMA transformés en MP3\n" if nwav else "")
               + f"• {cnt.get('déjà rangé', 0)} déjà rangés\n"
               + (f"• {cnt.get('erreur', 0)} illisibles (accès refusé…) : laissés en place\n" if cnt.get("erreur") else "")
               + (f"• {cnt.get('à vérifier', 0)} aux infos endommagées : placés dans « _Fichiers à vérifier »\n"
                  if cnt.get("à vérifier") else "")
               + "\n"
               f"{'Copier' if copy else 'Déplacer'} {todo} fichiers vers « {dest} » ?")
        while True:
            c = ask(self, "Prêt à ranger", txt, ("Ranger", "Voir le détail", "Annuler"))
            if c == 1:
                choose(self, "Aperçu (rien n'est encore modifié)",
                       [(f"{Path(m.src).name}  →  " + (os.path.relpath(m.dst, dest) if m.dst else ("non copié" if copy else "corbeille"))
                         + (f"   ({m.reason})" if m.reason else "") + ("   [MP3]" if m.convert else ""), None)
                        for m in moves[:400]])
                continue
            break
        if c != 0:
            return
        lib = self.app.lib

        def job(progress, log, cancel):
            lp = task_execute(moves, copy, lib, progress, log, cancel)
            log("Mise à jour de la bibliothèque…")
            lib.scan(dest, progress=progress, cancel=cancel)
            if copy and ident:
                todo_id = [m.dst for m in moves if m.status == "incomplet" and os.path.exists(m.dst)]
                for i, f in enumerate(todo_id):
                    if cancel():
                        break
                    try:
                        r = identify.auto_identify(f)
                        log(("✓ " + r.label()) if r else ("✗ " + Path(f).name))
                    except Exception as e:
                        log(f"⚠ {Path(f).name} : {organizer.friendly_error(e)}")
                    progress(i + 1, len(todo_id), f)
            return lp
        run_task(self, "Rangement en cours…", job)
        self.app.library_changed()

    # ------------------------------------------------------------------ identification
    def identify_all(self):
        from .. import setaside
        n_aside = setaside.count()
        if n_aside:
            what = choose(self, "Compléter les infos", [
                ("Compléter tous les titres incomplets", "all"),
                (f"Réessayer les {n_aside} fichier(s) mis de côté", "retry"),
                ("Voir les fichiers mis de côté", "list"),
                ("Vider la liste des fichiers mis de côté", "clear")])
            if what is None:
                return
            if what == "retry":
                self.app.identify(setaside.paths()); return
            if what == "list":
                items = setaside.load()
                txt = "\n".join(f"• {Path(i['path']).name} — {i.get('reason', '')}\n   {Path(i['path']).parent}"
                                for i in items[:12])
                if len(items) > 12:
                    txt += f"\n… et {len(items) - 12} autre(s)"
                info(self, f"Fichiers mis de côté ({len(items)})",
                     txt + "\n\nFermez le programme qui les utilise ou déverrouillez la clé USB, puis « Réessayer ».")
                return
            if what == "clear":
                setaside.clear(); self.app.toast.show_msg("Liste vidée"); return
        paths = [r["path"] for r in self.app.lib.tracks(incomplete_only=True)]
        if not paths:
            info(self, "Identifier", "Tous les titres ont déjà leurs informations. 👍"); return
        if not settings.get("acoustid_key"):
            if ask(self, "Identifier", "Sans clé AcoustID (Paramètres), la recherche se fait seulement "
                                       "à partir du nom des fichiers. Continuer ?") != 0:
                return
        self.app.identify(paths)

    # ------------------------------------------------------------------ CD
    def rip_cd(self):
        drives = converters.cd_drives()
        if not drives:
            info(self, "CD audio", "Aucun lecteur CD détecté. Branchez un lecteur USB (avec alimentation suffisante)."); return
        drive = drives[0] if len(drives) == 1 else choose(self, "Lecteur CD", [(d, d) for d in drives])
        if not drive:
            return
        album = artist = None
        for attempt in range(2):
            def job(progress, log, cancel, album=album, artist=artist):
                files = converters.rip_cd(drive, settings["mp3_bitrate"], log=log, cancel=cancel,
                                          album=album, artist=artist)
                log(f"{len(files)} pistes extraites, rangement…")
                moves = organizer.plan(Path(files[0]).parent, settings["library_root"], settings["rename_pattern"]) if files else []
                organizer.execute(moves, library=self.app.lib)
                return [m.dst for m in moves]
            res = run_task(self, "Extraction du CD en MP3", job)
            if res:
                self.app.library_changed(); return
            if attempt == 0 and ask(self, "CD non reconnu ?",
                                    "Si le CD est inconnu de la base MusicBrainz, saisissez l'album et l'artiste.",
                                    ("Saisir", "Annuler")) == 0:
                album = Keyboard.get(self, "Nom de l'album")
                artist = Keyboard.get(self, "Artiste")
                if not album:
                    return
            else:
                return

    # ------------------------------------------------------------------ YouTube
    def youtube(self):
        url = Keyboard.get(self, "Lien YouTube (vidéo ou playlist)", "", "https://www.youtube.com/watch?v=…")
        if not url or not url.strip():
            return
        url = url.strip()
        pl = "list=" in url and ask(self, "Playlist", "Ce lien contient une playlist. Tout télécharger ?",
                                    ("Toute la playlist", "Seulement cette vidéo")) == 0
        dl = Path(settings["library_root"]) / "_Téléchargements"
        lib = self.app.lib

        def job(progress, log, cancel):
            files = converters.youtube_to_mp3(url, dl, settings["mp3_bitrate"], log=log, progress=progress, playlist=pl)
            for f in files:
                m = identify.auto_identify(f, min_score=0.7)
                log(("Reconnu : " + m.label()) if m else f"Infos YouTube conservées : {Path(f).name}")
            moves = [m for m in organizer.plan(dl, settings["library_root"], settings["rename_pattern"]) if m.src in files]
            organizer.execute(moves, library=lib)
            return [m.dst for m in moves]
        res = run_task(self, "Conversion YouTube → MP3", job)
        self.app.library_changed()
        if res:
            self.app.toast.show_msg(f"{len(res)} titre(s) ajouté(s)")

    # ------------------------------------------------------------------ bibliothèque
    def rescan(self):
        folders = [settings["library_root"]] + list(settings.get("watched_folders", []))
        lib = self.app.lib

        def job(progress, log, cancel):
            n = 0
            for f in folders:
                if Path(f).is_dir():
                    log(f"Lecture de {f}…")
                    n += lib.scan(f, progress=progress, cancel=cancel)
            return n
        n = run_task(self, "Actualisation de la bibliothèque", job)
        self.app.library_changed()
        self.app.toast.show_msg(f"{n or 0} titre(s) ajouté(s) ou mis à jour")

    def eject(self):
        media = mounted_media()
        if not media:
            info(self, "Éjecter", "Aucun support amovible branché."); return
        mp = choose(self, "Éjecter quel support ?", [(f"⏏  {n}", m) for m, n in media.items()])
        if mp:
            for q in self.app.queues:
                if q.current() and q.current().startswith(mp):
                    q.player.stop()
            err = MediaWatcher.eject(mp)
            self.app.toast.show_msg(err or "Vous pouvez retirer le support en toute sécurité ✓", 5000)

    # ------------------------------------------------------------------ aide
    def show_help(self, topic="tactile"):
        """Manuel d'utilisation affiché à l'écran : défilement au doigt, liens entre chapitres."""
        from PySide6.QtWidgets import QScroller
        from .. import help as H
        d = Sheet(self, "❓ Aide de Musicothèque", 0.96, 0.96)
        view = H.make_browser(d, topic)
        view.setStyleSheet(f"font-size:{px(17)}px; background:#0d1117; color:#e6edf3; border:none")
        view.document().setDefaultStyleSheet(
            f"body{{font-size:{px(17)}px}} h1{{font-size:{px(26)}px}} h2{{font-size:{px(22)}px}} "
            f"h3{{font-size:{px(19)}px}} td,th{{padding:{px(4)}px}} "
            ".cap{color:#8b949e} .nav{color:#8b949e} code{color:#d2a8ff}")
        if H.html_path(topic).exists():
            view.setSource(H._url(topic))  # recharge avec la feuille de style tactile
        QScroller.grabGesture(view.viewport(), QScroller.LeftMouseButtonGesture)
        d.lay.addWidget(view, 1)
        row = QHBoxLayout(); d.lay.addLayout(row)
        row.addWidget(button("◀ Retour", view.backward))
        row.addWidget(button("☰ Sommaire", lambda: view.setSource(H._url("accueil"))))
        row.addWidget(button("📱 Version tactile", lambda: view.setSource(H._url("tactile"))))
        row.addWidget(button("Fermer", d.accept, obj="primary"))
        d.exec()

    # ------------------------------------------------------------------ télécommande
    def remote_panel(self):
        """QR code + adresse + code d'appairage pour piloter Musicothèque depuis un téléphone."""
        from .. import remote as R
        srv = self.app.remote
        d = Sheet(self, "📱 Télécommande depuis un téléphone", 0.92, 0.92)
        body = QHBoxLayout(); d.lay.addLayout(body, 1)
        qr = QrWidget(); body.addWidget(qr, 2)
        right = QVBoxLayout(); body.addLayout(right, 3)
        txt = label("", None, wrap=True); right.addWidget(txt, 1)
        row = QHBoxLayout(); right.addLayout(row)
        b_on = button("", checkable=True); b_pin = button("Nouveau code")
        row.addWidget(b_on); row.addWidget(b_pin)
        right.addWidget(button("Fermer", d.accept, obj="primary"))

        def refresh():
            on = srv.running
            b_on.setChecked(on); b_on.setText("Activée ✓" if on else "Désactivée")
            pin = R.ensure_pin()
            urls = srv.urls()
            qr.set_text(f"{urls[0]}/#pin={pin}" if on else "")
            txt.setText(
                (f"Code d'appairage : <span style='font-size:{px(34)}px;font-weight:700'>{pin}</span><br><br>"
                 "<b>Appli Android</b> : elle trouve ce Pi toute seule sur le Wi-Fi.<br>"
                 "<b>Sans appli</b> : scannez le QR code, ou ouvrez :<br>" + "<br>".join(f"<b>{u}</b>" for u in urls) +
                 f"<br><br>Téléphones connectés : {srv.connected_phones()}  "
                 "<span style='color:#8b949e'>(même Wi-Fi que le Pi)</span>")
                if on else "La télécommande est désactivée. Touchez « Désactivée » pour l'activer.")

        def toggle():
            if srv.running:
                srv.stop(); settings["remote_enabled"] = False
            else:
                if not srv.start():
                    info(self, "Télécommande", getattr(srv, "error", "Démarrage impossible"))
                settings["remote_enabled"] = srv.running
            settings.save(); refresh()

        def change_pin():
            if ask(self, "Nouveau code", "Les téléphones déjà appairés devront saisir le nouveau code. Continuer ?") == 0:
                R.new_pin(); refresh()
        b_on.clicked.connect(toggle); b_pin.clicked.connect(change_pin)
        refresh()
        d.exec()

    # ------------------------------------------------------------------ Bluetooth
    def bluetooth(self):
        """Appairer un casque ou une enceinte Bluetooth, puis l'ajouter aux sorties audio."""
        if not shutil.which("bluetoothctl"):
            info(self, "Bluetooth", "Bluetooth non installé : relancez install_rpi.sh et répondez « o » à la question Bluetooth."); return

        def bt(*args, timeout=20):
            r = subprocess.run(["bluetoothctl", *args], capture_output=True, text=True, timeout=timeout)
            return r.stdout

        def scan(progress, log, cancel):
            log("Mettez le casque ou l'enceinte en mode appairage…")
            bt("power", "on")
            log("Recherche des appareils (12 s)…")
            bt("--timeout", "12", "scan", "on", timeout=20)
            out = []
            for ln in bt("devices").splitlines():
                p = ln.split(" ", 2)
                if len(p) == 3 and p[0] == "Device":
                    out.append((p[2], p[1]))
            paired = {ln.split(" ", 2)[1] for ln in bt("devices", "Paired").splitlines() if ln.startswith("Device")}
            log(f"{len(out)} appareil(s) trouvé(s).")
            return [(("✓ " if mac in paired else "") + name, mac) for name, mac in out]
        devs = run_task(self, "Bluetooth", scan)
        if not devs:
            return
        mac = choose(self, "Quel appareil ?", devs)
        if not mac:
            return

        def connect(progress, log, cancel):
            for step in (("pair", mac), ("trust", mac), ("connect", mac)):
                log(f"{step[0]}…"); log(bt(*step, timeout=30).strip()[-300:])
            from .. import setup_audio, audio_engine
            r = setup_audio.install(); audio_engine._labels = None
            return r
        r = run_task(self, "Connexion Bluetooth", connect)
        if r:
            self.app.toast.show_msg("Appareil prêt : Son ▸ ＋ pour l'ajouter comme sortie", 6000)

    # ------------------------------------------------------------------ paramètres
    def settings_menu(self):
        key = settings.get("acoustid_key") or ""
        bl = backlight()
        acts = [
            (f"🔑  Clé AcoustID (reconnaissance) : {'••••' + key[-4:] if key else 'non renseignée'}", self.set_key),
            (f"📁  Dossier de la bibliothèque : {settings['library_root']}", self.set_root),
            ("➕  Référencer un autre dossier (sans le ranger)…", self.add_folder),
            (f"🎧  Qualité MP3 : {settings['mp3_bitrate']} kbit/s", self.set_bitrate),
            ("🔊  Rechercher les sorties audio", lambda: self.app.pages["son"].rescan_devices()),
        ]
        if bl:
            acts.append(("☀  Luminosité de l'écran", self.brightness))
        acts.append(("ℹ  Où obtenir une clé AcoustID ?", lambda: info(
            self, "Clé AcoustID", "Sur un ordinateur ou un téléphone, créez une clé gratuite sur\n"
                                  "https://acoustid.org/new-application\npuis saisissez-la ici.")))
        acts.append(("✕  Quitter l'application (retour à la console / au bureau)", self.quit_app))
        menu(self, "Paramètres", acts)

    def quit_app(self):
        from ..config import data_dir
        (data_dir() / ".quitter").write_text("1")   # la borne ne relance pas l'application
        self.app.close()

    def set_key(self):
        k = Keyboard.get(self, "Clé AcoustID", settings.get("acoustid_key") or "")
        if k is not None:
            settings["acoustid_key"] = k.strip(); settings.save()

    def set_root(self):
        d = browse_folder(self, "Dossier de la bibliothèque", settings["library_root"])
        if d:
            settings["library_root"] = d; settings.save(); self.rescan()

    def add_folder(self):
        d = browse_folder(self, "Dossier de musique à référencer")
        if d:
            if d not in settings["watched_folders"]:
                settings["watched_folders"].append(d); settings.save()
            self.rescan()

    def set_bitrate(self):
        v = choose(self, "Qualité MP3", [(f"{b} kbit/s", b) for b in (320, 256, 192, 128)], settings["mp3_bitrate"])
        if v:
            settings["mp3_bitrate"] = v; settings.save()

    def brightness(self):
        path, mx = backlight()
        d = Sheet(self, "Luminosité de l'écran", 0.7)
        try:
            cur = int(Path(path, "brightness").read_text())
        except (OSError, ValueError):
            cur = mx
        s = touch_slider(Qt.Horizontal, max(1, mx // 20), mx, cur)

        def setb(v):
            try:
                Path(path, "brightness").write_text(str(v))
            except OSError as e:
                d.setWindowTitle(str(e))
        s.valueChanged.connect(setb)
        d.lay.addWidget(s); d.lay.addWidget(button("OK", d.accept, obj="primary"))
        d.exec()

    def power(self):
        c = ask(self, "Éteindre", "Que voulez-vous faire ?", ("Éteindre", "Redémarrer", "Annuler"), primary=2)
        if c in (0, 1):
            self.app.hub.close(); settings.save()
            cmd = "poweroff" if c == 0 else "reboot"
            r = subprocess.run(["systemctl", cmd], capture_output=True)
            if r.returncode != 0:
                subprocess.run(["sudo", "-n", cmd])


class QrWidget(QWidget):
    """QR code dessiné directement (module « qrcode »), sans fichier image."""

    def __init__(self):
        super().__init__()
        self.matrix = []
        self.setMinimumSize(px(160), px(160))

    def set_text(self, text):
        self.matrix = []
        if text:
            try:
                import qrcode
                q = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
                q.add_data(text); q.make(fit=True)
                self.matrix = q.get_matrix()
            except ImportError:
                self.matrix = []
        self.update()

    def paintEvent(self, e):
        from PySide6.QtGui import QPainter, QColor
        p = QPainter(self)
        side = min(self.width(), self.height())
        x0, y0 = (self.width() - side) // 2, (self.height() - side) // 2
        if not self.matrix:
            p.setPen(QColor("#8b949e")); p.drawText(self.rect(), Qt.AlignCenter, "QR code\nindisponible")
            return
        n = len(self.matrix); cell = side / n
        p.fillRect(x0, y0, side, side, QColor("white"))
        for r, row in enumerate(self.matrix):
            for c, v in enumerate(row):
                if v:
                    p.fillRect(int(x0 + c * cell), int(y0 + r * cell), int(cell) + 1, int(cell) + 1, QColor("black"))
        p.end()


def backlight():
    for d in glob.glob("/sys/class/backlight/*"):
        try:
            mx = int(Path(d, "max_brightness").read_text())
            if os.access(Path(d, "brightness"), os.W_OK):
                return d, mx
        except (OSError, ValueError):
            continue
    return None
