"""Application entry point; all screenshots and processing stay local."""
import argparse
import logging
from pathlib import Path
import sys
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from cpp import __version__
from cpp.config import Settings
from cpp.ui.main_window import MainWindow
from cpp.ui.theme import apply_theme


def main(argv=None):
    parser = argparse.ArgumentParser(description="SnapMark — Ubuntu screenshot and quick image editor")
    parser.add_argument("image", nargs="?", help="Image to open")
    parser.add_argument("--capture", choices=["full", "region", "window"], help="Start capture after launch")
    parser.add_argument("--minimized", action="store_true", help="Start in the system tray if available")
    parser.add_argument("--version", action="version", version=f"SnapMark {__version__}")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    app = QApplication([sys.argv[0]])
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("SnapMark")
    app.setApplicationDisplayName("SnapMark")
    app.setOrganizationName("SnapMark")
    app.setDesktopFileName("io.github.snapmark.SnapMark")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "snapmark.svg")))
    settings = Settings.load()
    apply_theme(settings.theme)
    window = MainWindow(settings)
    if not ((args.minimized or settings.start_minimized) and window.tray_icon):
        window.show()
    if args.image:
        QTimer.singleShot(0, lambda: window.open_path(args.image))
    if args.capture:
        def capture_when_ready():
            if not window.capabilities_checked:
                QTimer.singleShot(100, capture_when_ready)
            else:
                window.start_capture(args.capture)
        QTimer.singleShot(100, capture_when_ready)
    return app.exec()
