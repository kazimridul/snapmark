"""Compact, direct annotation controls with visible color and size feedback."""
from PySide6.QtCore import QRectF, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QHBoxLayout, QLabel,
                              QPushButton, QSlider, QVBoxLayout, QWidget)

COLORS = [("Red", "#ef4444"), ("Orange", "#e95420"), ("Yellow", "#ffe14a"),
          ("Green", "#22c55e"), ("Blue", "#3b82f6"), ("Violet", "#a855f7"),
          ("Black", "#171923"), ("White", "#ffffff")]


class ColorSwatch(QAbstractButton):
    def __init__(self, name, color, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.setCheckable(True)
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(name)
        self.setAccessibleName(name + " annotation color")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self.color)
        painter.setPen(QPen(self.palette().mid().color(), 1))
        painter.drawEllipse(QRectF(5, 5, 18, 18))
        if self.isChecked() or self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(self.palette().highlight().color(), 2,
                                Qt.PenStyle.SolidLine if self.isChecked() else Qt.PenStyle.DashLine))
            painter.drawEllipse(QRectF(1.5, 1.5, 25, 25))


class ColorPalette(QWidget):
    color_changed = Signal(str)
    custom_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self.group = QButtonGroup(self)
        self.swatches = {}
        for name, color in COLORS:
            button = ColorSwatch(name, color, self)
            self.group.addButton(button)
            self.swatches[color] = button
            button.clicked.connect(lambda checked=False, c=color: self.color_changed.emit(c))
            layout.addWidget(button)
        self.custom_button = QPushButton("Custom…")
        self.custom_button.setObjectName("customColor")
        self.custom_button.setToolTip("Choose any annotation color")
        self.custom_button.clicked.connect(self.custom_requested)
        layout.addWidget(self.custom_button)

    def set_color(self, color):
        normalized = QColor(color).name()
        self.group.setExclusive(False)
        for value, button in self.swatches.items():
            button.setChecked(value == normalized)
        self.group.setExclusive(True)
        self.custom_button.setStyleSheet(f"border-bottom: 3px solid {normalized};")
        self.custom_button.setAccessibleDescription("Current color: " + normalized)


class ValueSlider(QWidget):
    valueChanged = Signal(int)
    editingFinished = Signal()

    def __init__(self, label, low, high, value, unit="", parent=None):
        super().__init__(parent)
        self.label, self.unit = label, unit
        self.setFixedWidth(138)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 1, 6, 1)
        layout.setSpacing(3)
        self.caption = QLabel()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(low, high)
        self.slider.setValue(value)
        self.slider.setAccessibleName(label)
        self.slider.setToolTip(label)
        self.slider.valueChanged.connect(self.changed)
        self.slider.sliderReleased.connect(self.editingFinished)
        self.slider.actionTriggered.connect(self.action_triggered)
        layout.addWidget(self.caption)
        layout.addWidget(self.slider)
        self.changed(value)

    def action_triggered(self, action):
        if not self.slider.isSliderDown():
            QTimer.singleShot(0, self.editingFinished.emit)

    def changed(self, value):
        self.caption.setText(f"{self.label}  {value}{self.unit}")
        self.valueChanged.emit(value)

    def value(self):
        return self.slider.value()

    def setValue(self, value):
        self.slider.setValue(value)
