"""Musicothèque — bibliothèque, lecteur et rangement de musique (Windows, Linux, Raspberry Pi avec souris)."""
import sys

from app.config import setup_path, APP_NAME


def main():
    setup_path()
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    from app.ui.main_window import MainWindow
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Musicotheque.App")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    # écrans haute densité (150 %, 200 %…) : mise à l'échelle exacte de Windows
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    w = MainWindow()
    w.show_adapted()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
