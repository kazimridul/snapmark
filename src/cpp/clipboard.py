from PySide6.QtCore import QMimeData
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication


def copy_image(image: QImage):
    if image.isNull():
        raise ValueError("There is no image to copy.")
    clipboard = QApplication.clipboard()
    mime = QMimeData()
    mime.setImageData(image)
    clipboard.setMimeData(mime)
    if not clipboard.mimeData().hasImage():
        raise RuntimeError("The desktop did not accept image clipboard data.")
