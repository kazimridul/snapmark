#!/usr/bin/env python3
"""Probe desktop capabilities and optionally editor activation; never capture the screen."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QIcon, QImage
from PySide6.QtWidgets import QApplication
from cpp import __file__ as package_file
from cpp.config import Settings
from cpp.ui.main_window import MainWindow
from cpp.ui.theme import apply_theme


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--editor", action="store_true", help="Also check foreground activation using a blank test image")
    args = parser.parse_args()
    app = QApplication([])
    app.setApplicationName("SnapMark")
    app.setApplicationDisplayName("SnapMark")
    app.setOrganizationName("SnapMark")
    app.setDesktopFileName("io.github.snapmark.SnapMark")
    app.setWindowIcon(QIcon(str(Path(package_file).parent / "assets" / "snapmark.svg")))
    apply_theme("system")
    window = MainWindow(Settings(tray=False))
    window.show()
    editor = None

    def open_test_editor():
        window.hidden_windows = [window]
        window.hide()
        QTimer.singleShot(350, restore_and_open)

    def restore_and_open():
        nonlocal editor
        window.finish_capture()
        image = QImage(640, 360, QImage.Format.Format_ARGB32)
        image.fill(QColor("#ffffff"))
        editor = window.open_editor(image)
        editor.choose_tool("pen")

    def finish():
        if window.jobs.active:
            QTimer.singleShot(100, finish)
            return
        print(json.dumps(asdict(window.caps), indent=2))
        if editor:
            print(json.dumps({"editor_active": editor.isActiveWindow(),
                              "transient_parent_is_main": editor.windowHandle().transientParent() is window.windowHandle()}))
            editor.fresh = False
            editor.document.undo.setClean()
        window.close()

    if args.editor:
        QTimer.singleShot(400, open_test_editor)
    QTimer.singleShot(2500 if args.editor else 1500, finish)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
