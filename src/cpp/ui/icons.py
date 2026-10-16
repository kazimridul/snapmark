"""Consistent vector tool icons, independent of installed icon themes or fonts."""
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

PATHS = {
    "select": '<path d="m5 3 14 9-7 1-3 7Z"/><path d="m12 13 5 7"/>',
    "pen": '<path d="m4 16-1 5 5-1L20 8a2.1 2.1 0 0 0-4-4Z"/><path d="m14 6 4 4M4 16l4 4"/>',
    "highlighter": '<path d="m6 14 8-10 6 5-8 10Z"/><path d="m6 14-2 5 3 2 5-2M3 22h17M12 7l6 5"/>',
    "highlight_rect": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M6 12h12" stroke-width="6" opacity=".4"/>',
    "arrow": '<path d="M4 20 20 4M9 4h11v11"/>',
    "rectangle": '<rect x="3" y="5" width="18" height="14" rx="1"/>',
    "ellipse": '<ellipse cx="12" cy="12" rx="9" ry="7"/>',
    "text": '<path d="M4 6V3h16v3M12 3v18M8 21h8"/>',
    "blur": '<path d="M12 3C10 7 5 11 5 15a7 7 0 0 0 14 0c0-4-5-8-7-12Z"/><path d="M8 15a4 4 0 0 0 4 4" stroke-dasharray="1 3"/>',
    "pixelate": '<rect x="3" y="3" width="18" height="18" rx="1"/><path d="M9 3v18M15 3v18M3 9h18M3 15h18"/><path d="M9 9h6v6H9Z" fill="{color}"/>',
    "crop": '<path d="M7 3v14h14M3 7h14v14"/>',
    "undo": '<path d="m8 4-5 5 5 5M3 9h10a7 7 0 0 1 0 14" transform="translate(0 -2)"/>',
    "redo": '<path d="m16 4 5 5-5 5M21 9H11a7 7 0 0 0 0 14" transform="translate(0 -2)"/>',
    "save": '<path d="M5 3h12l4 4v14H3V3Z"/><path d="M7 3v6h10V3M7 21v-8h10v8"/>',
    "save_as": '<path d="M11 21H3V3h14l4 4v4M7 3v6h10V3"/><path d="m14 18-1 4 4-1 5-5-3-3Z"/>',
    "copy": '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
    "zoom_in": '<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6M7 10h6M10 7v6"/>',
    "zoom_out": '<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6M7 10h6"/>',
    "fit": '<path d="M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5"/><rect x="7" y="7" width="10" height="10" rx="1"/>',
    "actual_size": '<rect x="2" y="3" width="20" height="18" rx="2"/><path d="m5 10 2-2v8M5 16h4m6-6 2-2v8M15 16h4"/><circle cx="12" cy="10" r=".5"/><circle cx="12" cy="15" r=".5"/>',
}


def tool_icon(kind: str) -> QIcon:
    icon = QIcon()
    palette = QApplication.palette()
    colors = [(QIcon.Mode.Normal, QIcon.State.Off, palette.color(QPalette.ColorRole.WindowText).name()),
              (QIcon.Mode.Normal, QIcon.State.On, "#ffffff"),
              (QIcon.Mode.Disabled, QIcon.State.Off, palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText).name())]
    for mode, state, color in colors:
        body = PATHS[kind].replace("{color}", color)
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
        pixmap = QPixmap(48, 48)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        QSvgRenderer(QByteArray(svg.encode())).render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(2)
        icon.addPixmap(pixmap, mode, state)
    return icon
