from pathlib import Path
from PySide6.QtWidgets import QLabel, QMessageBox
from cpp.ui.media_file import MediaFileDialog,delete_file


def test_properties_include_saved_file_and_metadata(app,tmp_path):
    path=tmp_path/'capture.webm'
    path.write_bytes(b'video')
    dialog=MediaFileDialog(path,{'Video dimensions':'1920 × 1080 px','Duration':'12.0s'})
    text=' '.join(label.text() for label in dialog.findChildren(QLabel))
    assert str(path) in text and '1920 × 1080' in text and '5 bytes' in text
    dialog.deleteLater()


def test_storage_deletion_requires_confirmation(app,tmp_path,monkeypatch):
    path=tmp_path/'shot.png'
    path.write_bytes(b'image')
    monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.StandardButton.No)
    assert not delete_file(None,path) and path.exists()
    monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.StandardButton.Yes)
    assert delete_file(None,path) and not path.exists()


def test_missing_file_delete_reports_error(app,tmp_path,monkeypatch):
    warnings=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda *a:warnings.append(a[-1]))
    assert not delete_file(None,tmp_path/'missing.mp4')
    assert warnings
