"""Musicothèque — interface tactile plein écran (Raspberry Pi ou autre carte + écran tactile).

  python3 touch_main.py                 plein écran (borne)
  python3 touch_main.py --fenetre 800x480   dans une fenêtre, pour essayer sur un ordinateur
  python3 touch_main.py --curseur       garde le pointeur de la souris visible
"""
import argparse
import os
import sys

from app.config import setup_path, APP_NAME


def main():
    ap = argparse.ArgumentParser(description=APP_NAME)
    ap.add_argument("--fenetre", metavar="LxH", help="taille de fenêtre, ex. 800x480 (sinon plein écran)")
    ap.add_argument("--curseur", action="store_true", help="afficher le pointeur de souris")
    args, qt_args = ap.parse_known_args()
    setup_path()
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from app.touch import common
    app = QApplication([sys.argv[0]] + qt_args)
    app.setApplicationName(APP_NAME)
    from app.help import install_french
    install_french(app)
    app.setAttribute(Qt.AA_SynthesizeMouseForUnhandledTouchEvents, True)
    common.init_scale(app)
    if args.fenetre:
        w_, h_ = (int(x) for x in args.fenetre.lower().split("x"))
        common.U = common.scale_for(w_, h_)
    app.setStyleSheet(common.stylesheet())
    if not args.curseur and not args.fenetre:
        app.setOverrideCursor(Qt.BlankCursor)
    from app.touch.window import TouchWindow
    w = TouchWindow()
    if args.fenetre:
        w.resize(w_, h_); w.show()
    else:
        w.showFullScreen()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
