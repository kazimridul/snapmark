"""Undoable document. QImage implicit sharing avoids pixel copies for vector edits."""
from dataclasses import dataclass
from PySide6.QtCore import QObject, Signal, QRectF
from PySide6.QtGui import QImage, QUndoCommand, QUndoStack
from cpp.editor.model import Annotation, composite


@dataclass(frozen=True)
class State:
    base: QImage
    annotations: tuple[Annotation, ...] = ()


class Edit(QUndoCommand):
    def __init__(self, document: "Document", after: State, title: str):
        super().__init__(title)
        self.document, self.before, self.after = document, document.state, after

    def redo(self):
        self.document.state = self.after
        self.document.changed.emit()

    def undo(self):
        self.document.state = self.before
        self.document.changed.emit()


class Document(QObject):
    changed = Signal()

    def __init__(self, image: QImage):
        super().__init__()
        if image.isNull():
            raise ValueError("The image is empty or unsupported.")
        image = QImage(image)
        image.setDevicePixelRatio(1)
        self.state = State(image)
        self.undo = QUndoStack(self)
        self.undo.setUndoLimit(100)

    def commit(self, state: State, title: str):
        self.undo.push(Edit(self, state, title))

    def add(self, annotation: Annotation):
        self.commit(State(self.state.base, self.state.annotations + (annotation,)), "Add " + annotation.kind)

    def replace_annotation(self, index: int, annotation: Annotation):
        items = list(self.state.annotations)
        items[index] = annotation
        self.commit(State(self.state.base, tuple(items)), "Change annotation")

    def remove(self, index: int):
        self.commit(State(self.state.base, self.state.annotations[:index] + self.state.annotations[index+1:]), "Remove annotation")

    def render(self) -> QImage:
        return composite(self.state.base, self.state.annotations)


def crop_state(state: State, rectangle: QRectF) -> State:
    rect = rectangle.normalized().toAlignedRect().intersected(state.base.rect())
    if rect.width() < 2 or rect.height() < 2:
        raise ValueError("Select an area at least 2 × 2 pixels.")
    # Flatten at the crop boundary so out-of-bounds vectors cannot reappear later.
    return State(composite(state.base, state.annotations).copy(rect))
