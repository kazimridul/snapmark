from dataclasses import replace
import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage
from cpp.editor.document import Document, State, crop_state
from cpp.editor.model import Annotation, composite
from cpp.editor.effects import privacy_state


def test_crop_clamps_normalizes_and_updates_pixels(image):
    image.setPixelColor(10, 20, QColor("red"))
    result = crop_state(State(image), QRectF(10, 20, 500, 500))
    assert (result.base.width(), result.base.height()) == (190, 100)
    assert result.base.pixelColor(0, 0) == QColor("red")
    assert crop_state(State(image), QRectF(50, 40, -40, -20)).base.size().toTuple() == (40, 20)
    with pytest.raises(ValueError):
        crop_state(State(image), QRectF(-20, -20, 2, 2))


def test_highlighter_translucency_and_single_stroke_overlap(image):
    a = Annotation("highlighter", ((10, 40), (180, 40)), "#ffff00", 20, .4)
    rendered = composite(image, (a,))
    color = rendered.pixelColor(80, 40)
    assert color.red() == 255 and color.green() == 255
    assert 150 <= color.blue() <= 155
    assert image.pixelColor(80, 40) == QColor("white")


@pytest.mark.parametrize("kind,points,sample", [
    ("pen", ((10, 30), (160, 30)), (80, 30)),
    ("arrow", ((10, 60), (170, 60)), (165, 60)),
    ("rectangle", ((20, 20), (100, 80)), (20, 50)),
    ("ellipse", ((20, 20), (100, 80)), (60, 20)),
    ("highlight_rect", ((20, 20), (100, 80)), (60, 50)),
])
def test_vectors_render(image, kind, points, sample):
    result = composite(image, (Annotation(kind, points, "#ff0000", 4),))
    color = result.pixelColor(*sample)
    assert color.red() > 230 and color.green() < 30


def test_text_multiline_renders_and_moves(image):
    text = Annotation("text", ((10, 5),), color="#000000", text="Hello\nUbuntu", font_size=24, bold=True)
    output = composite(image, (text,))
    assert any(output.pixelColor(x, y).red() < 100 for x in range(15, 90) for y in range(8, 30))
    assert any(output.pixelColor(x, y).red() < 100 for x in range(15, 110) for y in range(35, 60))
    moved = text.moved(40, 20)
    assert moved.points == ((50, 25),)
    assert moved.bounds().width() == text.bounds().width()


def test_undo_redo_for_every_kind_and_properties(image):
    document = Document(image)
    annotation = Annotation("arrow", ((10, 10), (80, 40)))
    document.add(annotation)
    document.undo.setClean()
    moved = annotation.moved(25, 15)
    document.replace_annotation(0, moved)
    assert not document.undo.isClean()
    document.undo.undo()
    assert document.state.annotations == (annotation,)
    assert document.undo.isClean()
    document.undo.redo()
    assert document.state.annotations == (moved,)
    document.remove(0)
    assert document.state.annotations == ()
    document.undo.undo()
    assert document.state.annotations == (moved,)
    document.commit(crop_state(document.state, QRectF(5, 5, 100, 60)), "Crop")
    assert document.state.base.width() == 100
    document.undo.undo()
    assert document.state.base.width() == 200
    assert document.state.annotations == (moved,)


@pytest.mark.parametrize("kind", ["blur", "pixelate"])
def test_privacy_changes_pixels_in_bounds_and_is_undoable(app, kind):
    image = QImage(100, 80, QImage.Format.Format_ARGB32)
    for x in range(100):
        for y in range(80):
            image.setPixelColor(x, y, QColor("black" if (x+y) % 2 else "white"))
    document = Document(image)
    state = privacy_state(document.state, QRectF(20, 20, 50, 40), kind, 12)
    assert state.base.pixelColor(0, 0) == image.pixelColor(0, 0)
    assert 50 < state.base.pixelColor(40, 40).red() < 205
    document.commit(state, kind)
    document.undo.undo()
    assert document.state.base == image
    document.undo.redo()
    assert document.state.base == state.base


def test_privacy_flattens_annotations_and_crop_clips_them(image):
    state = State(image, (Annotation("rectangle", ((0, 0), (150, 90)), "#ff0000", fill=True),))
    protected = privacy_state(state, QRectF(20, 20, 40, 40), "pixelate", 20)
    assert protected.annotations == ()
    assert protected.base.pixelColor(30, 30) == QColor("#ff0000")
    crop = crop_state(state, QRectF(10, 10, 30, 30))
    assert crop.annotations == ()
    assert crop.base.pixelColor(10, 10) == QColor("#ff0000")
