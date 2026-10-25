"""Shared on-disk file properties and explicitly confirmed deletion."""
from datetime import datetime
import mimetypes
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout


def delete_file(parent,path,extra=''):
    if not path or not Path(path).is_file():
        QMessageBox.warning(parent,'File unavailable','The saved file is missing or has not been saved yet.')
        return False
    target=Path(path)
    answer=QMessageBox.question(parent,'Delete from storage?',f'Permanently delete {target.name}?\n\n{target}\n\n'+extra,
        QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
    if answer!=QMessageBox.StandardButton.Yes:
        return False
    try:
        target.unlink()
    except OSError as exc:
        QMessageBox.warning(parent,'Could not delete file',str(exc))
        return False
    return True

class MediaFileDialog(QDialog):
    deleted=Signal(str)
    def __init__(self,path,details,parent=None):
        super().__init__(parent)
        self.path=str(path) if path else None
        self.setWindowTitle('File properties')
        self.resize(570,380)
        layout=QVBoxLayout(self)
        form=QFormLayout()
        layout.addLayout(form)
        rows={}
        if path:
            target=Path(path)
            rows.update({'Name':target.name,'Location':str(target.resolve()),'Type':mimetypes.guess_type(str(target))[0] or target.suffix.upper().lstrip('.') or 'Unknown'})
            try:
                stat=target.stat()
                rows['Size']=f'{stat.st_size/1024/1024:.2f} MB ({stat.st_size:,} bytes)'
                rows['Modified']=datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            except OSError:
                rows['Storage']='File is missing'
        else:
            rows['Storage']='Not saved to a file'
        rows.update(details)
        for name,value in rows.items():
            label=QLabel(str(value))
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(name,label)
        buttons=QHBoxLayout()
        folder=QPushButton('Open folder')
        folder.setEnabled(bool(path))
        folder.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).resolve().parent))))
        buttons.addWidget(folder)
        remove=QPushButton('Delete from storage…')
        remove.setEnabled(bool(path and Path(path).is_file()))
        remove.clicked.connect(self.remove)
        buttons.addWidget(remove)
        buttons.addStretch()
        close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)
    def remove(self):
        if delete_file(self,self.path,'Any open edits or projects referencing this file will lose their source.'):
            self.deleted.emit(self.path)
            self.accept()
