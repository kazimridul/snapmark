from dataclasses import asdict
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QKeySequenceEdit, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)
from cpp.config import Settings


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.result_settings = None
        self.settings = settings
        self.setWindowTitle("SnapMark settings")
        self.resize(640, 640)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        self.controls = {}
        for title, names in [
            ("General", ["save_directory", "export_format", "auto_editor", "delay", "theme", "tray", "start_minimized", "launch_at_login"]),
            ("Editor defaults", ["highlighter_color", "highlighter_opacity", "pen_color", "pen_width", "arrow_color", "arrow_width", "font_size", "blur_strength"])]:
            page = QWidget()
            form = QFormLayout(page)
            form.setSpacing(14)
            tabs.addTab(page, title)
            labels = {"auto_editor": "Open editor after capture", "tray": "Enable system tray (when available)",
                      "start_minimized": "Start minimized to tray", "launch_at_login": "Launch at login"}
            for name in names:
                value = getattr(settings, name)
                label = labels.get(name, name.replace("_", " ").capitalize())
                if name == "save_directory":
                    control = QLineEdit(value)
                    row = QWidget()
                    box = QHBoxLayout(row)
                    box.setContentsMargins(0, 0, 0, 0)
                    box.addWidget(control)
                    browse = QPushButton("Browse…")
                    browse.clicked.connect(self.browse)
                    box.addWidget(browse)
                    form.addRow(label, row)
                elif type(value) is bool:
                    control = QCheckBox()
                    control.setChecked(value)
                    form.addRow(label, control)
                elif name in ("export_format", "theme", "delay"):
                    control = QComboBox()
                    values = ["png", "jpg", "webp"] if name == "export_format" else ["system", "light", "dark"] if name == "theme" else [0, 3, 5, 10]
                    for option in values:
                        control.addItem(str(option) + (" seconds" if name == "delay" else ""), option)
                    control.setCurrentIndex(values.index(value))
                    form.addRow(label, control)
                elif name.endswith("color"):
                    control = QPushButton(value)
                    control.setStyleSheet(f"border: 3px solid {value}")
                    control.clicked.connect(lambda checked=False, c=control: self.color(c))
                    form.addRow(label, control)
                else:
                    control = QSpinBox()
                    limits = (5, 90) if name == "highlighter_opacity" else (8, 200) if name == "font_size" else (2, 100) if name == "blur_strength" else (1, 80)
                    control.setRange(*limits)
                    control.setValue(value)
                    form.addRow(label, control)
                self.controls[name] = control
            if title == "General":
                note = QLabel("Tray availability depends on your desktop. Closing the main window quits SnapMark.\nLogin startup uses this installation, so keep its virtual environment in place.")
                note.setWordWrap(True)
                form.addRow(note)
            else:
                note = QLabel("Blur and pixelation do not guarantee anonymization. Use an opaque filled rectangle for information that must be hidden.")
                note.setWordWrap(True)
                form.addRow(note)
        page = QWidget()
        form = QFormLayout(page)
        tabs.addTab(page, "Shortcuts")
        note = QLabel("These shortcuts work inside SnapMark.\nFor a system shortcut, open Ubuntu Settings → Keyboard → Custom Shortcuts and assign:\nsnapmark --capture region\nUbuntu will report conflicts with its existing shortcuts.")
        note.setWordWrap(True)
        form.addRow(note)
        self.shortcuts = {}
        for key, value in settings.shortcuts.items():
            edit = QKeySequenceEdit(QKeySequence(value))
            edit.setMaximumSequenceLength(1)
            form.addRow(key.replace("_", " ").capitalize(), edit)
            self.shortcuts[key] = edit
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def browse(self):
        path = QFileDialog.getExistingDirectory(self, "Screenshot directory", self.controls["save_directory"].text())
        if path:
            self.controls["save_directory"].setText(path)

    def color(self, button):
        color = QColorDialog.getColor(QColor(button.text()), self)
        if color.isValid():
            button.setText(color.name())
            button.setStyleSheet(f"border: 3px solid {color.name()}")

    def accept(self):
        from pathlib import Path
        values = asdict(self.settings)
        for key, control in self.controls.items():
            if isinstance(control, QCheckBox): value = control.isChecked()
            elif isinstance(control, QComboBox): value = control.currentData()
            elif isinstance(control, QSpinBox): value = control.value()
            else: value = control.text()
            values[key] = value
        path = Path(values["save_directory"]).expanduser()
        if not path.is_absolute() or "\x00" in str(path) or (path.exists() and not path.is_dir()):
            QMessageBox.warning(self, "Invalid folder", "Choose an absolute path to a screenshot folder.")
            return
        values["save_directory"] = str(path)
        shortcuts = {key: control.keySequence().toString() for key, control in self.shortcuts.items()}
        for group in [("capture_menu", "full", "region", "window"), ("save", "save_as", "copy", "undo", "redo")]:
            seen = set()
            for key in group:
                value = shortcuts[key]
                if not value or value in seen or value in ("Esc", "Ctrl++", "Ctrl+-", "Ctrl+0", "Ctrl+1"):
                    QMessageBox.warning(self, "Shortcut conflict", "Use distinct, nonempty shortcuts in each window. Escape and zoom shortcuts are reserved.")
                    return
                seen.add(value)
        values["shortcuts"] = shortcuts
        self.result_settings = Settings(**values)
        self.result_settings.validate()
        super().accept()
