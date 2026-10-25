"""Import completed native GNOME recordings without controlling its recorder.

Linux close-write/atomic-move notifications distinguish final files from a
recording still being written. Existing videos are never imported on startup.
"""
import ctypes
import os
from pathlib import Path
import struct
from PySide6.QtCore import QObject, QSocketNotifier, QStandardPaths, QTimer, Signal

class SystemRecordings(QObject):
    ready = Signal(str)
    unavailable = Signal(str)
    def __init__(self, parent=None, directory=None):
        super().__init__(parent)
        self.directory = Path(directory or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation) or Path.home()/'Videos')
        self.known = set()
        self.watches = {}
        self.fd = -1
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.libc.inotify_init1.argtypes = [ctypes.c_int]
        self.libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        self.fd = self.libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            QTimer.singleShot(0, lambda: self.unavailable.emit('Automatic import is unavailable; use Open video.'))
            return
        self.scan(initial=True)
        self.notifier = QSocketNotifier(self.fd, QSocketNotifier.Type.Read, self)
        self.notifier.activated.connect(self.receive)
        fd = self.fd
        self.destroyed.connect(lambda: os.close(fd))
        self.retry = QTimer(self)
        self.retry.timeout.connect(self.scan)
        self.retry.start(3000)  # The native recorder can create its folder later.

    def scan(self, initial=False):
        for folder in (self.directory, self.directory/'Screencasts'):
            if not folder.is_dir() or folder in self.watches.values():
                continue
            if initial:
                self.known.update(p.resolve() for p in folder.iterdir() if p.is_file())
            wd = self.libc.inotify_add_watch(self.fd, os.fsencode(folder), 0x8 | 0x80 | 0x100 | 0x400 | 0x800)
            if wd >= 0:
                self.watches[wd] = folder

    def receive(self, *_):
        try:
            data = os.read(self.fd, 65536)
        except BlockingIOError:
            return
        offset = 0
        while offset+16 <= len(data):
            wd, mask, cookie, length = struct.unpack_from('iIII', data, offset)
            name = os.fsdecode(data[offset+16:offset+16+length].split(b'\0',1)[0])
            offset += 16+length
            folder = self.watches.get(wd)
            if not folder:
                continue
            if mask & (0x400 | 0x800 | 0x8000):
                self.watches.pop(wd, None)
                continue
            if mask & 0x40000000:
                if mask & (0x100 | 0x80):
                    self.scan()
                continue
            path = (folder/name).resolve()
            if mask & (0x8 | 0x80) and path not in self.known and path.suffix.lower() in ('.webm','.mp4','.mkv'):
                self.known.add(path)
                self.ready.emit(str(path))
