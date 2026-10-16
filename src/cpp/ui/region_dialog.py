from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout
from cpp.editor.canvas import Canvas
from cpp.editor.document import Document


class RegionDialog(QDialog):
    """Fallback selection: one drag captures immediately on mouse release."""
    def __init__(self, image, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select region — SnapMark")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.image = image
        self.rectangle = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.document = Document(image)
        self.canvas = Canvas(self.document)
        self.canvas.set_tool("crop")
        self.canvas.selection_changed.connect(self.accept_region)
        self.canvas.confirm_requested.connect(self.accept_region)
        self.canvas.tool_cancelled.connect(self.reject)
        layout.addWidget(self.canvas)
        self.hint = QLabel("Drag to capture an area · Escape to cancel", self)
        self.hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hint.setStyleSheet("background: #252733; color: white; padding: 12px 18px; border-radius: 8px;")
        self.hint.adjustSize()
        self.resize(1100, 760)

    def showEvent(self, event):
        super().showEvent(event)
        self.canvas.fit()
        self.canvas.setFocus()
        self.hint.move(max(12, (self.width()-self.hint.width())//2), 20)
        self.hint.raise_()

    def accept_region(self):
        rect = self.canvas.region.toAlignedRect().intersected(self.image.rect())
        if rect.width() >= 2 and rect.height() >= 2:
            self.rectangle = rect
            self.accept()
