from pathlib import Path
import time
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from cpp.capture.backend import Capabilities
from cpp.config import Settings
from cpp.storage import History, read_image
from cpp.ui.main_window import MainWindow


def wait_for(app, predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(10)
    assert predicate()


def make_main(app, image, monkeypatch, tmp_path, auto_editor=True):
    monkeypatch.setattr("cpp.ui.main_window.capabilities", lambda: Capabilities("x11", True, True, True, "Mock desktop"))
    monkeypatch.setattr("cpp.ui.main_window.capture", lambda mode, caps, cancelled: image)
    window = MainWindow(Settings(tray=False, auto_editor=auto_editor, save_directory=str(tmp_path)))
    window.history = History(tmp_path / "history.json")
    window.show()
    wait_for(app, lambda: not window.jobs.active)
    return window


def close_main(app, window):
    wait_for(app, lambda: not window.jobs.active)
    for editor in list(window.editors):
        editor.fresh = False
        editor.document.undo.setClean()
        editor.close()
    window.close()
    app.processEvents()


def test_mock_capture_opens_editor_and_restores_window(app, image, monkeypatch, tmp_path):
    window = make_main(app, image, monkeypatch, tmp_path)
    window.start_capture("full")
    wait_for(app, lambda: len(window.editors) == 1 and not window.jobs.active)
    editor = next(iter(window.editors))
    assert editor.document.state.base == image
    assert window.isVisible() and not window.capturing
    close_main(app, window)


def test_delayed_capture_is_cancellable_and_does_not_block(app, image, monkeypatch, tmp_path):
    window = make_main(app, image, monkeypatch, tmp_path)
    window.delay.setCurrentIndex(2)
    window.start_capture("full")
    assert window.remaining == 5 and window.timer.isActive()
    window.countdown_tick()
    assert window.remaining == 4 and not window.editors
    window.cancel_capture()
    assert not window.capturing and not window.timer.isActive()
    assert window.capture_buttons["full"].isEnabled()
    close_main(app, window)


def test_quick_capture_saved_and_recent_reopens(app, image, monkeypatch, tmp_path):
    window = make_main(app, image, monkeypatch, tmp_path, False)
    window.start_capture("full")
    wait_for(app, lambda: not window.capturing and not window.jobs.active)
    paths = window.history.entries()
    assert len(paths) == 1 and Path(paths[0]).exists()
    assert read_image(paths[0]).size() == image.size()
    window.open_path(paths[0])
    wait_for(app, lambda: len(window.editors) == 1 and not window.jobs.active)
    assert next(iter(window.editors)).path == paths[0]
    close_main(app, window)


def test_capture_failure_leaves_controls_usable(app, image, monkeypatch, tmp_path):
    window = make_main(app, image, monkeypatch, tmp_path)
    messages = []
    monkeypatch.setattr(window, "error", messages.append)
    def failed(*args):
        raise RuntimeError("Permission denied")
    monkeypatch.setattr("cpp.ui.main_window.capture", failed)
    window.start_capture("full")
    wait_for(app, lambda: not window.capturing and not window.jobs.active)
    assert messages == ["Permission denied"]
    assert window.isVisible() and window.capture_buttons["full"].isEnabled()
    close_main(app, window)


def test_wayland_selected_region_opens_editor_without_second_selector(app, image, monkeypatch, tmp_path):
    window = make_main(app, image, monkeypatch, tmp_path)
    window.capabilities_ready(Capabilities("wayland", True, True, False, "Native selector", 2))
    def unexpected_selector(*args):
        raise AssertionError("The portal's selected region must not be selected again")
    monkeypatch.setattr("cpp.ui.main_window.RegionDialog", unexpected_selector)
    window.start_capture("region")
    wait_for(app, lambda: len(window.editors) == 1 and not window.jobs.active)
    assert next(iter(window.editors)).document.state.base == image
    close_main(app, window)


def test_capture_editor_is_activated_above_its_main_window(app, image, monkeypatch, tmp_path):
    window = make_main(app, image, monkeypatch, tmp_path)
    window.capabilities_ready(Capabilities("wayland", True, True, False, "Native selector", 2))
    window.start_capture("region")
    wait_for(app, lambda: len(window.editors) == 1 and not window.jobs.active)
    editor = next(iter(window.editors))
    wait_for(app, editor.isActiveWindow)
    assert editor.isWindow()
    assert editor.parentWidget() is window
    assert editor.windowHandle().transientParent() is window.windowHandle()
    assert not editor.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert editor.capture_badge_action.isVisible()
    assert editor.capture_badge.text() == "Screenshot captured"
    close_main(app, window)


def test_capture_hides_existing_editor_and_cancels_its_activation_retry(app, image, monkeypatch, tmp_path):
    window = make_main(app, image, monkeypatch, tmp_path)
    editor = window.open_editor(image)
    assert editor.presentation_timer.isActive()
    window.start_capture("full")
    assert not editor.presentation_timer.isActive()
    assert not editor.isVisible()
    wait_for(app, lambda: len(window.editors) == 2 and not window.jobs.active)
    assert editor.isVisible()
    close_main(app, window)
