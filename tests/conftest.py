import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QImage


@pytest.fixture(scope="session")
def app():
    application = QApplication.instance() or QApplication([])
    application.setApplicationName("cpp-tests")
    yield application
    application.clipboard().clear()
    application.processEvents()


@pytest.fixture
def image(app):
    image = QImage(200, 120, QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    return image
