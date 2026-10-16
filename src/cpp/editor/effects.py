from PIL import Image, ImageFilter
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage
from cpp.editor.document import State
from cpp.editor.model import composite


def privacy_state(state: State, rectangle: QRectF, kind: str, strength: int) -> State:
    image = composite(state.base, state.annotations).convertToFormat(QImage.Format.Format_RGBA8888)
    rect = rectangle.normalized().toAlignedRect().intersected(image.rect())
    if rect.width() < 2 or rect.height() < 2:
        raise ValueError("Select an area at least 2 × 2 pixels.")
    pil = Image.frombytes("RGBA", (image.width(), image.height()), bytes(image.constBits()), "raw", "RGBA", image.bytesPerLine())
    box = (rect.x(), rect.y(), rect.x()+rect.width(), rect.y()+rect.height())
    area = pil.crop(box)
    strength = max(2, min(100, strength))
    if kind == "blur":
        area = area.filter(ImageFilter.GaussianBlur(strength))
    elif kind == "pixelate":
        area = area.resize((max(1, area.width//strength), max(1, area.height//strength)), Image.Resampling.BOX).resize(area.size, Image.Resampling.NEAREST)
    else:
        raise ValueError("Unknown privacy effect.")
    pil.paste(area, box)
    data = pil.tobytes()
    return State(QImage(data, pil.width, pil.height, pil.width*4, QImage.Format.Format_RGBA8888).copy())
