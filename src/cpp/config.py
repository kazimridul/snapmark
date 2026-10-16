"""Validated, versioned settings. Invalid individual values fall back safely."""
from dataclasses import asdict, dataclass, field, fields
import json
import os
from pathlib import Path
from PySide6.QtCore import QIODevice, QSaveFile, QStandardPaths
from PySide6.QtGui import QColor, QKeySequence

DEFAULT_SHORTCUTS = {
    "capture_menu": "Ctrl+Shift+S", "full": "Ctrl+Shift+F", "region": "Ctrl+Shift+R",
    "window": "Ctrl+Shift+W", "save": "Ctrl+S", "save_as": "Ctrl+Shift+S",
    "copy": "Ctrl+C", "undo": "Ctrl+Z", "redo": "Ctrl+Y",
}


def config_root() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation))


def legacy_config_root() -> Path:
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericConfigLocation)
    return Path(root) / "cpp-screenshot" / "cpp"


def screenshots_dir() -> str:
    pictures = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    return str(Path(pictures or str(Path.home() / "Pictures")) / "Screenshots")


@dataclass
class Settings:
    save_directory: str = field(default_factory=screenshots_dir)
    export_format: str = "png"
    highlighter_color: str = "#ffe14a"
    highlighter_opacity: int = 40
    pen_color: str = "#e95420"
    pen_width: int = 4
    arrow_color: str = "#e95420"
    arrow_width: int = 4
    font_size: int = 24
    blur_strength: int = 16
    auto_editor: bool = True
    delay: int = 0
    start_minimized: bool = False
    launch_at_login: bool = False
    tray: bool = True
    theme: str = "system"
    shortcuts: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SHORTCUTS))

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        defaults = cls()
        try:
            target = path or config_root() / "settings.json"
            if path is None and not target.exists():
                target = legacy_config_root() / "settings.json"
            data = json.loads(target.read_text())
        except (OSError, ValueError):
            return defaults
        if not isinstance(data, dict):
            return defaults
        for f in fields(defaults):
            value = data.get(f.name)
            current = getattr(defaults, f.name)
            if type(value) is type(current):
                setattr(defaults, f.name, value)
        defaults.validate()
        return defaults

    def validate(self):
        for name, low, high, default in [("highlighter_opacity", 5, 90, 40), ("pen_width", 1, 80, 4),
                ("arrow_width", 1, 80, 4), ("font_size", 8, 200, 24), ("blur_strength", 2, 100, 16)]:
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                setattr(self, name, default)
        for name in ("pen_color", "arrow_color", "highlighter_color"):
            if not QColor(getattr(self, name)).isValid():
                setattr(self, name, "#ffe14a" if name == "highlighter_color" else "#e95420")
        if self.theme not in ("system", "light", "dark"):
            self.theme = "system"
        if self.delay not in (0, 3, 5, 10):
            self.delay = 0
        if self.export_format not in ("png", "jpg", "webp"):
            self.export_format = "png"
        if not self.save_directory or not Path(self.save_directory).is_absolute() or "\x00" in self.save_directory:
            self.save_directory = screenshots_dir()
        self.shortcuts = {key: value if isinstance(value := self.shortcuts.get(key), str)
                          and value and not QKeySequence(value).isEmpty() else default
                          for key, default in DEFAULT_SHORTCUTS.items()}

    def save(self, path: Path | None = None):
        self.validate()
        path = path or config_root() / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        output = QSaveFile(str(path))
        if not output.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(output.errorString())
        data = {"schema_version": 1, **asdict(self)}
        if output.write(json.dumps(data, indent=2).encode()) < 0 or not output.commit():
            raise OSError(output.errorString())


def set_autostart(enabled: bool):
    """Only called when the user changes the login setting."""
    import sys
    path = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "autostart" / "cpp-screenshot.desktop"
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    def quote(value):
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'
    command = quote(sys.executable) + ("" if getattr(sys, "frozen", False) else " -m cpp")
    contents = "[Desktop Entry]\nType=Application\nName=SnapMark\nExec=" + command + " --minimized\nTerminal=false\nX-GNOME-Autostart-enabled=true\n"
    path.write_text(contents)
