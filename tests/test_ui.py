from dataclasses import replace
import time
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from cpp.config import Settings
from cpp.editor.model import Annotation
from cpp.jobs import Jobs
from cpp.ui.editor_window import EditorWindow
from cpp.ui.region_dialog import RegionDialog


def wait_for(app, predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(10)
    assert predicate()


@pytest.fixture
def editor(app, image):
    window = EditorWindow(image, Settings())
    window.show()
    app.processEvents()
    yield window
    wait_for(app, lambda: not window.jobs.active)
    window.fresh = False
    window.document.undo.setClean()
    window.close()
    app.processEvents()


@pytest.mark.parametrize("zoom", [.5, 1, 2])
def test_zoom_does_not_change_annotation_coordinates(app, editor, zoom):
    canvas = editor.canvas
    canvas.actual_size()
    canvas.zoom(zoom)
    editor.choose_tool("rectangle")
    start = canvas.mapFromScene(20, 20)
    end = canvas.mapFromScene(100, 80)
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    points = editor.document.state.annotations[0].points
    assert points[0][0] == pytest.approx(20, abs=2)
    assert points[-1][0] == pytest.approx(100, abs=2)
    assert points[-1][1] == pytest.approx(80, abs=2)


def test_select_move_and_edit_annotation(app, editor):
    editor.document.add(Annotation("rectangle", ((20, 20), (80, 60))))
    canvas = editor.canvas
    canvas.actual_size()
    start = canvas.mapFromScene(40, 40)
    end = canvas.mapFromScene(60, 50)
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    assert editor.document.state.annotations[0].points[0] == (40, 30)
    editor.color = "#00ff00"
    editor.change_style()
    assert editor.document.state.annotations[0].color == "#00ff00"
    editor.document.undo.undo()
    assert editor.document.state.annotations[0].color != "#00ff00"


def test_crop_handles_move_confirm_and_undo(app, editor):
    editor.choose_tool("crop")
    canvas = editor.canvas
    canvas.actual_size()
    def drag(x1, y1, x2, y2):
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(x1, y1))
        QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(x2, y2))
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(x2, y2))
    drag(20, 20, 100, 80)
    assert canvas.region.width() == 80
    drag(100, 80, 120, 90)
    assert canvas.region.width() == 100
    drag(60, 50, 70, 60)
    assert canvas.region.left() == 30
    editor.apply_selection()
    wait_for(app, lambda: not editor.busy and not editor.jobs.active)
    assert editor.document.state.base.size().toTuple() == (100, 70)
    editor.document.undo.undo()
    assert editor.document.state.base.size().toTuple() == (200, 120)


def test_worker_completion_on_gui_thread(app):
    from PySide6.QtCore import QThread
    jobs = Jobs()
    results = []
    jobs.run(lambda: 42, lambda value: results.append((value, QThread.currentThread())), pytest.fail)
    wait_for(app, lambda: not jobs.active)
    assert results == [(42, app.thread())]


@pytest.mark.parametrize("kind", ["blur", "pixelate"])
def test_privacy_applies_on_release_and_undo_restores_pixels(app, editor, kind):
    editor.document.add(Annotation("rectangle", ((40, 20), (80, 80)), "#000000", fill=True))
    before = editor.document.render()
    editor.choose_tool(kind)
    assert not editor.option_actions["apply"].isVisible()
    assert not editor.option_actions["cancel"].isVisible()
    canvas = editor.canvas
    canvas.actual_size()
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(20, 10))
    QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(120, 100))
    assert editor.document.undo.count() == 1
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(120, 100))
    wait_for(app, lambda: not editor.busy and not editor.jobs.active)
    assert editor.document.undo.count() == 2
    assert editor.document.render() != before
    assert editor.canvas.region.isEmpty()
    assert editor.confirm_pending()
    editor.document.undo.undo()
    assert editor.document.render() == before


@pytest.mark.parametrize("kind", ["blur", "pixelate"])
def test_escape_cancels_unfinished_privacy_drag(app, editor, kind):
    editor.choose_tool(kind)
    canvas = editor.canvas
    canvas.actual_size()
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(20, 20))
    QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(100, 80))
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(100, 80))
    assert editor.document.undo.count() == 0
    assert canvas.region.isEmpty()


def test_pen_color_size_and_opacity_survive_switching_tools(app, editor):
    editor.choose_tool("pen")
    QTest.mouseClick(editor.colors.swatches["#3b82f6"], Qt.MouseButton.LeftButton)
    editor.width.setValue(12)
    editor.opacity.setValue(65)
    assert editor.canvas.style.color == "#3b82f6"
    assert editor.canvas.style.width == 12
    assert editor.canvas.style.opacity == .65
    editor.choose_tool("arrow")
    editor.choose_tool("highlighter")
    editor.choose_tool("pen")
    assert editor.color == "#3b82f6"
    assert editor.colors.swatches["#3b82f6"].isChecked()
    assert editor.width.value() == 12 and editor.opacity.value() == 65
    canvas = editor.canvas
    canvas.actual_size()
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(20, 20))
    QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(100, 80))
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(100, 80))
    annotation = editor.document.state.annotations[0]
    assert annotation.color == "#3b82f6" and annotation.width == 12 and annotation.opacity == .65


def test_editor_save_copy_and_clean_state(app, editor, monkeypatch, tmp_path):
    from cpp.storage import read_image
    editor.document.add(Annotation("arrow", ((10, 20), (160, 60)), "#ff0000", 5))
    expected = editor.document.render()
    path = tmp_path / "edited.png"
    monkeypatch.setattr("cpp.ui.editor_window.QFileDialog.getSaveFileName", lambda *args: (str(path), "PNG image (*.png)"))
    editor.save()
    wait_for(app, lambda: not editor.busy and not editor.jobs.active)
    assert path.exists()
    assert read_image(path).convertToFormat(expected.format()) == expected
    assert editor.document.undo.isClean() and not editor.fresh
    editor.copy()
    wait_for(app, lambda: not editor.busy and not editor.jobs.active)
    assert app.clipboard().image().convertToFormat(expected.format()) == expected
    editor.document.undo.undo()
    assert not editor.document.undo.isClean()


def test_text_add_and_edit_dialog(app, editor, monkeypatch):
    from PySide6.QtCore import QPointF
    monkeypatch.setattr("cpp.ui.editor_window.QInputDialog.getMultiLineText", lambda *args: ("First\nSecond", True))
    editor.choose_tool("text")
    editor.add_text(QPointF(10, 10))
    annotation = editor.document.state.annotations[0]
    assert annotation.kind == "text" and annotation.text == "First\nSecond"
    editor.canvas.selected_index = 0
    monkeypatch.setattr("cpp.ui.editor_window.QInputDialog.getMultiLineText", lambda *args: ("Changed", True))
    editor.edit_text()
    assert editor.document.state.annotations[0].text == "Changed"
    editor.document.undo.undo()
    assert editor.document.state.annotations[0].text == "First\nSecond"


def test_unsaved_close_can_cancel_or_discard(app, editor, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr("cpp.ui.editor_window.QMessageBox.question", lambda *args: QMessageBox.StandardButton.Cancel)
    assert not editor.close()
    assert editor.isVisible()
    monkeypatch.setattr("cpp.ui.editor_window.QMessageBox.question", lambda *args: QMessageBox.StandardButton.Discard)
    assert editor.close()


def test_tool_palette_has_aligned_icons_and_descriptive_tooltips(app, editor):
    from PySide6.QtGui import QIcon
    editor.resize(1000, 760)
    app.processEvents()
    positions = []
    for kind, action in editor.tool_actions.items():
        button = editor.tools.widgetForAction(action)
        assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
        assert button.size().toTuple() == (44, 44)
        assert not action.icon().isNull()
        assert not action.icon().pixmap(24, 24, QIcon.Mode.Normal, QIcon.State.On).isNull()
        assert action.text() in action.toolTip()
        assert "—" in action.toolTip()
        assert button.accessibleName() == action.text()
        positions.append(button.geometry().x())
    assert len(set(positions)) == 1


def test_fallback_region_captures_on_mouse_release(app, image):
    from PySide6.QtWidgets import QDialog
    dialog = RegionDialog(image)
    dialog.show()
    app.processEvents()
    canvas = dialog.canvas
    canvas.actual_size()
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(20, 20))
    QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(100, 80))
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(100, 80))
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.rectangle.size().toTuple() == (80, 60)
    assert not dialog.isVisible()
    dialog.deleteLater()


def test_snapmark_branding(editor):
    assert editor.windowTitle().endswith("— SnapMark")
