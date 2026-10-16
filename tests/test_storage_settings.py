import json
import pytest
from PySide6.QtGui import QColor
from cpp.clipboard import copy_image
from cpp.config import Settings
from cpp.editor.model import Annotation, composite
from cpp.storage import History, read_image, save_image


def test_export_matches_compositor_and_clipboard(image, tmp_path, app):
    rendered = composite(image, (Annotation("arrow", ((10, 20), (160, 70))),
                                 Annotation("highlighter", ((20, 90), (150, 90)), "#ffff00", 20, .4)))
    path = tmp_path / "result.png"
    save_image(rendered, path)
    assert read_image(path).convertToFormat(rendered.format()) == rendered
    copy_image(rendered)
    assert app.clipboard().mimeData().hasImage()
    assert app.clipboard().image().convertToFormat(rendered.format()) == rendered


@pytest.mark.parametrize("suffix", ["jpg", "webp"])
def test_other_exports(image, tmp_path, suffix):
    path = tmp_path / ("image." + suffix)
    save_image(image, path)
    assert read_image(path).size() == image.size()


def test_invalid_files_and_write_failure(image, tmp_path):
    path = tmp_path / "broken.png"
    path.write_bytes(b"not an image")
    with pytest.raises(ValueError):
        read_image(path)
    with pytest.raises(OSError):
        save_image(image, tmp_path / "missing" / "out.png")
    with pytest.raises(ValueError):
        save_image(image, tmp_path / "out.txt")
    with pytest.raises(ValueError):
        copy_image(type(image)())


def test_settings_persist_and_recover(app, tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(pen_width=14, theme="dark", auto_editor=False)
    settings.save(path)
    restored = Settings.load(path)
    assert restored.pen_width == 14 and restored.theme == "dark" and not restored.auto_editor
    path.write_text(json.dumps({"pen_width": -1, "theme": "broken", "auto_editor": "false",
        "save_directory": "relative", "highlighter_color": "invalid", "shortcuts": {"save": 99}}))
    restored = Settings.load(path)
    assert restored.pen_width == 4 and restored.theme == "system" and restored.auto_editor
    assert restored.highlighter_color == "#ffe14a"
    assert restored.shortcuts["save"] == "Ctrl+S"
    path.write_text("{ corrupt")
    assert Settings.load(path).pen_width == 4


def test_history_is_local_bounded_and_removal_keeps_file(app, tmp_path):
    history = History(tmp_path / "history.json")
    path = tmp_path / "image.png"
    path.write_bytes(b"test")
    history.add(str(path))
    history.add(str(path))
    assert history.entries() == [str(path)]
    history.remove(str(path))
    assert history.entries() == [] and path.exists()
    history.write([str(tmp_path / str(i)) for i in range(100)])
    assert len(history.entries()) == 30
    history.path.write_text('null')
    assert history.entries() == []


def test_rename_preserves_settings_and_history(app, tmp_path, monkeypatch):
    new = tmp_path / "SnapMark"
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "settings.json").write_text(json.dumps({"pen_width": 12}))
    monkeypatch.setattr("cpp.config.config_root", lambda: new)
    monkeypatch.setattr("cpp.config.legacy_config_root", lambda: legacy)
    assert Settings.load().pen_width == 12
    settings = Settings.load()
    settings.save()
    assert (new / "settings.json").exists()
    assert (legacy / "settings.json").exists()
    (legacy / "history.json").write_text('["/tmp/previous.png"]')
    history = History(new / "history.json", legacy / "history.json")
    assert history.entries() == ["/tmp/previous.png"]
    history.remove("/tmp/previous.png")
    assert history.entries() == []
    assert json.loads((legacy / "history.json").read_text()) == ["/tmp/previous.png"]
