from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def apply_theme(theme: str):
    app = QApplication.instance()
    app.styleHints().setColorScheme({"system": Qt.ColorScheme.Unknown, "light": Qt.ColorScheme.Light,
                                   "dark": Qt.ColorScheme.Dark}[theme])
    dark = theme == "dark" or (theme == "system" and app.styleHints().colorScheme() == Qt.ColorScheme.Dark)
    palette = QPalette()
    if dark:
        for role, color in [(QPalette.ColorRole.Window, "#202229"), (QPalette.ColorRole.WindowText, "#f1f1f3"),
                (QPalette.ColorRole.Base, "#292c34"), (QPalette.ColorRole.AlternateBase, "#30343d"),
                (QPalette.ColorRole.Text, "#f1f1f3"), (QPalette.ColorRole.Button, "#30343d"),
                (QPalette.ColorRole.ButtonText, "#f1f1f3"), (QPalette.ColorRole.ToolTipBase, "#30343d"),
                (QPalette.ColorRole.ToolTipText, "#ffffff")]:
            palette.setColor(role, QColor(color))
    else:
        for role, color in [(QPalette.ColorRole.Window, "#f8f8fa"), (QPalette.ColorRole.Base, "#ffffff"),
                (QPalette.ColorRole.WindowText, "#252733"), (QPalette.ColorRole.Text, "#252733"),
                (QPalette.ColorRole.Button, "#ffffff"), (QPalette.ColorRole.ButtonText, "#252733")]:
            palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#e95420"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    app.setPalette(palette)
    app.setStyleSheet('''
        QWidget { font-family: "Ubuntu", "Noto Sans", sans-serif; font-size: 13px; }
        QToolBar { border: none; spacing: 5px; padding: 8px; }
        QToolButton, QPushButton { padding: 8px 12px; border: 1px solid palette(mid); border-radius: 6px; }
        QToolBar#mainToolbar QToolButton { padding: 0; margin: 0; border: 1px solid transparent; border-radius: 8px; }
        QToolBar#mainToolbar QToolButton:hover { background: palette(alternate-base); border-color: #e95420; }
        QToolBar#mainToolbar QToolButton:focus { border: 2px solid #e95420; }
        QToolBar#toolPalette { spacing: 5px; padding: 9px; border-right: 1px solid palette(mid); }
        QToolBar#toolPalette QToolButton { padding: 0; margin: 0; border: 1px solid transparent; border-radius: 8px; }
        QToolBar#toolPalette QToolButton:hover { background: palette(alternate-base); border-color: #e95420; }
        QToolBar#toolPalette QToolButton:checked { background: #e95420; border-color: #e95420; }
        QToolBar#toolPalette QToolButton:focus { border: 2px solid #e95420; }
        QToolButton:hover, QPushButton:hover { border-color: #e95420; }
        QToolButton:checked, QPushButton:default { background: #e95420; color: white; border-color: #e95420; }
        QPushButton:focus, QToolButton:focus, QLineEdit:focus, QSpinBox:focus { border: 2px solid #e95420; }
        QLineEdit, QSpinBox, QComboBox, QKeySequenceEdit { padding: 6px; border: 1px solid palette(mid); border-radius: 4px; }
        QToolBar#contextToolbar { padding: 9px 12px; spacing: 12px; border-bottom: 1px solid palette(mid); }
        QLabel#toolTitle { font-weight: 600; padding-right: 8px; }
        QLabel#captureBadge { background: #dcfce7; color: #166534; border-radius: 6px; padding: 7px 10px; font-weight: 600; }
        QLabel#toolHint { color: palette(text); padding-left: 8px; }
        QPushButton#customColor { padding: 5px 8px; }
        QPushButton#primaryAction { background: #e95420; color: white; border-color: #e95420; }
        QSlider::groove:horizontal { height: 4px; background: palette(mid); border-radius: 2px; }
        QSlider::sub-page:horizontal { background: #e95420; border-radius: 2px; }
        QSlider::handle:horizontal { background: palette(base); border: 2px solid #e95420; width: 10px; margin: -5px 0; border-radius: 7px; }
        QStatusBar { padding: 4px; }
        QLabel#brand { font-size: 30px; font-weight: 700; }
        QLabel#section { font-size: 16px; font-weight: 600; }
        QPushButton#capture { padding: 22px 14px; text-align: left; font-size: 16px; font-weight: 600; }
        QListWidget { border: 1px solid palette(mid); border-radius: 8px; padding: 4px; }
        QListWidget::item { padding: 6px; border-radius: 4px; }
    ''')
