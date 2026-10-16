"""Atomic export, bounded image decoding and local recent metadata."""
import json
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QIODevice, QSaveFile
from PySide6.QtGui import QImage, QImageReader, QImageWriter

FORMATS = {".png": b"png", ".jpg": b"jpeg", ".jpeg": b"jpeg", ".webp": b"webp"}


def read_image(path: str | Path) -> QImage:
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and size.width()*size.height() > 100_000_000:
        raise ValueError("Image exceeds the 100 megapixel editing limit.")
    image = reader.read()
    if image.isNull():
        raise ValueError("Cannot open image: " + reader.errorString())
    image.setDevicePixelRatio(1)
    return image


def save_image(image: QImage, path: str | Path):
    path = Path(path)
    fmt = FORMATS.get(path.suffix.lower())
    if fmt is None:
        raise ValueError("Use a .png, .jpg, .jpeg or .webp filename.")
    file = QSaveFile(str(path))
    if not file.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(file.errorString())
    writer = QImageWriter(file, fmt)
    writer.setQuality(95)
    if not writer.write(image):
        file.cancelWriting()
        raise OSError(writer.errorString())
    if not file.commit():
        raise OSError(file.errorString())


def suggested_name(fmt="png") -> str:
    return "snapmark_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f") + "." + fmt


class History:
    def __init__(self, path: Path, fallback: Path | None = None):
        self.path = path
        self.fallback = fallback

    def entries(self) -> list[str]:
        try:
            source = self.path if self.path.exists() or self.fallback is None else self.fallback
            data = json.loads(source.read_text())
            return [s for s in data if isinstance(s, str)][:30] if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def write(self, paths: list[str]):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file = QSaveFile(str(self.path))
        if not file.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(file.errorString())
        if file.write(json.dumps(paths[:30]).encode()) < 0 or not file.commit():
            raise OSError(file.errorString())

    def add(self, path: str):
        path = str(Path(path).resolve())
        self.write([path] + [p for p in self.entries() if p != path])

    def remove(self, path: str):
        self.write([p for p in self.entries() if p != path])
