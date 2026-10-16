"""Workers own their lifetimes; callbacks always run on the Qt main thread."""
from PySide6.QtCore import QObject, QThread, Signal, Slot


class Worker(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.result.emit(self.function())
        except Exception as exc:
            self.failed.emit(str(exc) or type(exc).__name__)


class Jobs(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = {}

    def run(self, function, success, failure):
        worker = Worker(function, self)
        self.active[worker] = (success, failure)
        worker.result.connect(self.receive)
        worker.failed.connect(self.fail)
        worker.finished.connect(self.release)
        worker.start()

    @Slot(object)
    def receive(self, result):
        self.active[self.sender()][0](result)

    @Slot(str)
    def fail(self, message):
        self.active[self.sender()][1](message)

    @Slot()
    def release(self):
        worker = self.sender()
        self.active.pop(worker, None)
        worker.deleteLater()
