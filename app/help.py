"""Aide de Musicothèque : manuel .chm sous Windows, pages HTML ailleurs, et traduction française de Qt.

Fichiers (créés par docs/build_aide.py) :
  aide/Musicotheque.chm      aide Windows (sommaire, index, recherche)
  aide/html/index.html       mêmes pages en HTML (Linux, Raspberry Pi, version tactile)
  aide/Musicotheque_Manuel.pdf   manuel à imprimer
"""
import os
import subprocess
import sys

from .config import app_dir

# page d'aide de chaque partie du logiciel (nom du fichier dans aide/html et dans le .chm)
TOPICS = {
    "accueil": "index.html",
    "installation": "02-installation.html",
    "bibliotheque": "04-bibliotheque.html",
    "ranger": "05-ranger.html",
    "identifier": "06-identifier.html",
    "son": "07-son.html",
    "audiogramme": "08-audiogramme.html",
    "sorties": "09-sorties.html",
    "tactile": "10-tactile.html",
    "telecommande": "11-telecommande.html",
    "depannage": "12-depannage.html",
}


def help_dir():
    return app_dir() / "aide"


def chm_path():
    return help_dir() / "Musicotheque.chm"


def html_path(topic="accueil"):
    return help_dir() / "html" / TOPICS.get(topic, "index.html")


def pdf_path():
    return help_dir() / "Musicotheque_Manuel.pdf"


def install_french(app):
    """Boutons standard de Qt en français (Enregistrer, Annuler, Oui, Non…)."""
    from PySide6.QtCore import QTranslator, QLibraryInfo, QLocale
    path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    app._translators = []
    for name in ("qtbase_fr", "qt_fr"):
        t = QTranslator(app)
        if t.load(name, path):
            app.installTranslator(t)
            app._translators.append(t)
    QLocale.setDefault(QLocale(QLocale.French, QLocale.France))


def open_help(parent=None, topic="accueil"):
    """Ouvre l'aide à la bonne page. Renvoie False si l'aide n'est pas installée."""
    page = TOPICS.get(topic, "index.html")
    chm = chm_path()
    if sys.platform == "win32" and chm.exists():
        try:
            # hh.exe ouvre directement la page voulue ; sinon, l'aide s'ouvre à l'accueil
            subprocess.Popen(["hh.exe", f"{chm}::/{page}"])
        except OSError:
            os.startfile(str(chm))
        return True
    html = html_path(topic)
    if html.exists():
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(html))):
            return True
        show_in_window(parent, topic)
        return True
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.information(parent, "Aide", "L'aide n'est pas installée.\n"
                            "Le manuel est disponible sur https://github.com/decmike91/musicoteque")
    return False


def show_in_window(parent=None, topic="accueil"):
    """Aide affichée dans une fenêtre de Musicothèque (sans navigateur, comme sur la borne)."""
    from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton
    d = QDialog(parent)
    d.setWindowTitle("Aide de Musicothèque")
    lay = QVBoxLayout(d)
    view = make_browser(d, topic)
    lay.addWidget(view, 1)
    row = QHBoxLayout()
    for text, fn in (("◀ Retour", view.backward), ("Sommaire", lambda: view.setSource(_url("accueil")))):
        b = QPushButton(text); b.clicked.connect(fn); row.addWidget(b)
    row.addStretch()
    close = QPushButton("Fermer"); close.clicked.connect(d.accept); row.addWidget(close)
    lay.addLayout(row)
    from .ui.widgets import fit_to_screen
    fit_to_screen(d, 900, 700)
    d.exec()


def _url(topic):
    from PySide6.QtCore import QUrl
    return QUrl.fromLocalFile(str(html_path(topic)))


def make_browser(parent, topic="accueil"):
    """QTextBrowser qui affiche les pages d'aide, suit les liens internes et ajuste les captures à la largeur."""
    from PySide6.QtWidgets import QTextBrowser
    from PySide6.QtGui import QDesktopServices, QImage, QPalette, QColor, QTextDocument
    from PySide6.QtCore import Qt

    class HelpBrowser(QTextBrowser):
        def loadResource(self, kind, url):
            if kind == QTextDocument.ImageResource:
                path = url.toLocalFile() if url.isLocalFile() else self.source().resolved(url).toLocalFile()
                img = QImage(path)
                if not img.isNull():
                    w = max(200, int(self.viewport().width() * 0.92))
                    if img.width() > w:
                        img = img.scaledToWidth(w, Qt.SmoothTransformation)
                    return img
            return super().loadResource(kind, url)

    v = HelpBrowser(parent)
    pal = v.palette()
    pal.setColor(QPalette.Link, QColor("#58a6ff")); pal.setColor(QPalette.LinkVisited, QColor("#a5d6ff"))
    v.setPalette(pal)
    v.setOpenLinks(False)

    def follow(url):
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
        else:
            v.setSource(v.source().resolved(url) if url.isRelative() else url)
    v.anchorClicked.connect(follow)
    if html_path(topic).exists():
        v.setSource(_url(topic))
    else:
        v.setHtml("<h2>Aide non installée</h2><p>Le manuel est disponible sur "
                  "github.com/decmike91/musicoteque</p>")
    return v
