from datetime import datetime
from pathlib import Path
import threading
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMainWindow, QTabWidget, QMenu, QMessageBox, QPushButton, QSystemTrayIcon, QVBoxLayout, QWidget)
from cpp.capture.backend import Capabilities, capabilities, capture, needs_local_region_selection
from cpp.config import Settings, config_root, legacy_config_root, set_autostart
from cpp.jobs import Jobs
from cpp.storage import History, read_image, save_image, suggested_name
from cpp.ui.editor_window import EditorWindow
from cpp.ui.region_dialog import RegionDialog
from cpp.ui.settings_dialog import SettingsDialog
from cpp.ui.theme import apply_theme


class MainWindow(QMainWindow):
    def __init__(self, settings, standalone=False):
        super().__init__()
        self.standalone = standalone
        self.settings = settings
        self.jobs = Jobs(self)
        self.editors = set()
        self.history = History(config_root() / "history.json", legacy_config_root() / "history.json")
        self.caps = Capabilities("none", False, False, False, "Checking desktop capture capabilities…")
        self.cancelled = threading.Event()
        self.capturing = False
        self.capabilities_checked = False
        self.hidden_windows = []
        self.setWindowTitle("SnapMark — Capture & annotate")
        self.resize(720, 740)
        self.setMinimumWidth(560)
        root = QWidget()
        root.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        tabs = QTabWidget()
        tabs.addTab(root, "Screenshot")
        from cpp.video.panel import RecordingPanel
        self.recording_panel = RecordingPanel(self)
        self.recording_panel.editors_changed.connect(lambda:QTimer.singleShot(0,self.maybe_quit_standalone))
        tabs.addTab(self.recording_panel, "Screen Recording")
        self.setCentralWidget(tabs)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)
        header = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(QApplication.windowIcon().pixmap(48, 48))
        header.addWidget(icon)
        brand = QLabel("SnapMark")
        brand.setObjectName("brand")
        header.addWidget(brand)
        header.addStretch()
        settings_button = QPushButton("Settings")
        settings_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        settings_button.clicked.connect(self.open_settings)
        header.addWidget(settings_button)
        layout.addLayout(header)
        subtitle = QLabel("Capture a moment. Make your point.")
        layout.addWidget(subtitle)
        self.capture_buttons = {}
        for mode, text, tooltip in [("full", "▣   Full Screen", "Capture the full desktop using its supported screenshot API"),
                ("region", "⌗   Select Region", "Select a region using the system dialog or a frozen screenshot"),
                ("window", "▤   Active Window", "Capture the active window, or a system-selected window when supported")]:
            button = QPushButton(text)
            button.setObjectName("capture")
            button.setToolTip(tooltip)
            button.setEnabled(False)
            button.clicked.connect(lambda checked=False, m=mode: self.start_capture(m))
            self.capture_buttons[mode] = button
            layout.addWidget(button)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Capture delay"))
        self.delay = QComboBox()
        for seconds in (0, 3, 5, 10):
            self.delay.addItem("No delay" if not seconds else f"{seconds} seconds", seconds)
        self.delay.setCurrentIndex((0, 3, 5, 10).index(settings.delay))
        controls.addWidget(self.delay)
        controls.addStretch()
        open_button = QPushButton("Open image…")
        open_button.clicked.connect(self.open_file)
        controls.addWidget(open_button)
        layout.addLayout(controls)
        self.capture_status = QLabel(self.caps.description)
        self.capture_status.setWordWrap(True)
        layout.addWidget(self.capture_status)
        self.cancel_button = QPushButton("Cancel capture")
        self.cancel_button.clicked.connect(self.cancel_capture)
        self.cancel_button.hide()
        layout.addWidget(self.cancel_button)
        recent_header = QHBoxLayout()
        heading = QLabel("Recent screenshots")
        heading.setObjectName("section")
        recent_header.addWidget(heading)
        recent_header.addStretch()
        remove = QPushButton("Remove from list")
        remove.setToolTip("Removes the history entry. The image file stays on disk.")
        remove.clicked.connect(self.remove_recent)
        recent_header.addWidget(remove)
        layout.addLayout(recent_header)
        self.recent = QListWidget()
        self.recent.setIconSize(QSize(88, 58))
        self.recent.itemDoubleClicked.connect(lambda item: self.open_path(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.recent, 1)
        footer = QLabel("All images stay on your computer. No uploads. No telemetry.")
        layout.addWidget(footer)
        self.shortcuts = []
        self.install_shortcuts()
        self.tray_icon = None
        self.setup_tray()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.countdown_tick)
        self.history_generation = 0
        self.refresh_history()
        self.jobs.run(capabilities, self.capabilities_ready, self.error)
        self.statusBar().showMessage("Ready")
        # Start with a neutral surface, not a highlighted Settings button.
        # Keyboard navigation still reaches every action, capture actions first.
        navigation = [root, *self.capture_buttons.values(), self.delay, open_button,
                      remove, self.recent, settings_button]
        for previous, following in zip(navigation, navigation[1:]):
            QWidget.setTabOrder(previous, following)
        root.setFocus(Qt.FocusReason.OtherFocusReason)

    def install_shortcuts(self):
        for action in self.shortcuts:
            self.removeAction(action)
            action.deleteLater()
        self.shortcuts = []
        for key, function in {"capture_menu": self.reveal, "full": lambda: self.start_capture("full"),
                "region": lambda: self.start_capture("region"), "window": lambda: self.start_capture("window")}.items():
            action = QAction(self)
            action.setShortcut(self.settings.shortcuts[key])
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            action.triggered.connect(function)
            self.addAction(action)
            self.shortcuts.append(action)
        cancel = QAction(self)
        cancel.setShortcut("Esc")
        cancel.triggered.connect(self.cancel_capture)
        self.addAction(cancel)
        self.shortcuts.append(cancel)

    def setup_tray(self):
        if self.tray_icon:
            self.tray_icon.hide()
            self.tray_icon.deleteLater()
            self.tray_icon = None
        if self.standalone or not self.settings.tray or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(QApplication.windowIcon(), self)
        tray.setToolTip("SnapMark — Capture & annotate")
        menu = QMenu(self)
        menu.addAction("Take Screenshot…", self.reveal)
        menu.addAction("Capture Region", lambda: self.start_capture("region"))
        menu.addAction("Capture Full Screen", lambda: self.start_capture("full"))
        menu.addAction("Open Recent Screenshot", self.open_latest)
        menu.addSeparator()
        menu.addAction("Settings", self.open_settings)
        menu.addAction("Quit", self.close)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda reason: self.reveal() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        tray.show()
        self.tray_icon = tray
        if not hasattr(self, "minimize_button"):
            self.minimize_button = QPushButton("Hide to tray")
            self.minimize_button.clicked.connect(self.hide)
            self.statusBar().addPermanentWidget(self.minimize_button)
        self.minimize_button.setVisible(True)

    def reveal(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def capabilities_ready(self, caps):
        self.capabilities_checked = True
        self.caps = caps
        self.capture_status.setText(caps.description)
        select_window = caps.session == "wayland" and not caps.targets & 8
        self.capture_buttons["window"].setText("▤   Select Window" if select_window else "▤   Active Window")
        tooltips = {
            "full": "Choose Screen in the system capture dialog" if caps.session=="wayland" else "Capture the full desktop using its supported screenshot API",
            "region": "Select a region using the system dialog or a frozen screenshot",
            "window": ("Open the system screenshot chooser, choose Window, then click the window to capture"
                       if caps.session == "wayland" and caps.portal_version == 2 else
                       "Choose a window in the system selector" if select_window else "Capture the active window"),
        }
        for mode, button in self.capture_buttons.items():
            button.setEnabled(getattr(caps, mode))
            button.setToolTip(tooltips[mode] if getattr(caps, mode) else caps.description)

    def start_capture(self, mode):
        if self.capturing:
            return
        if not getattr(self.caps, mode):
            self.error(self.caps.description)
            return
        self.capture_mode = mode
        self.capturing = True
        self.cancelled.clear()
        self.remaining = self.delay.currentData()
        self.cancel_button.show()
        for button in self.capture_buttons.values():
            button.setEnabled(False)
        if self.remaining:
            self.capture_status.setText(f"Capturing in {self.remaining} seconds…")
            self.timer.start()
        else:
            self.perform_capture()

    def countdown_tick(self):
        self.remaining -= 1
        if self.remaining <= 0:
            self.timer.stop()
            self.perform_capture()
        else:
            self.capture_status.setText(f"Capturing in {self.remaining} seconds…")

    def perform_capture(self):
        self.capture_status.setText("Waiting for screenshot permission or capture…")
        self.portal_permission_window = self.caps.session == "wayland" and not self.isVisible()
        if self.caps.session == "wayland":
            # GNOME permits access dialogs only for the focused application.
            # Keep a requesting window mapped until the portal finishes.
            self.reveal()
        self.hidden_windows = [w for w in [self, *self.editors] if w.isVisible() and (self.caps.session != "wayland" or w is not self)]
        for window in self.hidden_windows:
            if isinstance(window, EditorWindow):
                window.presentation_timer.stop()
            window.hide()
        QTimer.singleShot(350, self.launch_capture_worker)

    def launch_capture_worker(self):
        if not self.capturing or self.cancelled.is_set():
            self.finish_capture()
            return
        mode, caps = self.capture_mode, self.caps
        self.jobs.run(lambda: capture(mode, caps, self.cancelled), self.capture_ready, self.capture_failed)

    def finish_capture(self):
        self.timer.stop()
        self.capturing = False
        self.cancel_button.hide()
        for window in self.hidden_windows:
            previous = window.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            window.show()
            window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, previous)
        self.hidden_windows = []
        if getattr(self,"portal_permission_window",False) and self.standalone:
            self.hide()
        self.capabilities_ready(self.caps)
        QTimer.singleShot(0, self.maybe_quit_standalone)

    def cancel_capture(self):
        if not self.capturing:
            return
        self.cancelled.set()
        if self.timer.isActive():
            self.finish_capture()
            self.statusBar().showMessage("Capture cancelled", 4000)
        else:
            self.capture_status.setText("Cancelling capture…")

    def capture_failed(self, message):
        self.finish_capture()
        if self.cancelled.is_set() or "cancelled" in message.lower():
            self.statusBar().showMessage(message, 5000)
        else:
            self.error(message)

    def capture_ready(self, image):
        cancelled = self.cancelled.is_set()
        mode = self.capture_mode
        self.finish_capture()
        if cancelled:
            return
        if mode == "region" and needs_local_region_selection(self.caps):
            dialog = RegionDialog(image, self)
            dialog.showFullScreen()
            if not dialog.exec():
                return
            image = image.copy(dialog.rectangle)
        directory = Path(self.settings.save_directory)
        path = directory / suggested_name(self.settings.export_format)
        auto_editor = self.settings.auto_editor
        self.statusBar().showMessage("Saving screenshot…")
        def work():
            directory.mkdir(parents=True, exist_ok=True)
            save_image(image, path)
            return str(path)
        def ready(saved_path):
            self.record_saved(saved_path)
            if auto_editor:
                self.open_editor(image, saved_path, captured=True)
        def failed(message):
            self.open_editor(image)
            self.error("Screenshot could not be saved automatically. It is open in the editor for recovery: " + message)
        self.jobs.run(work, ready, failed)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open image", self.settings.save_directory,
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff);;All files (*)")
        if path:
            self.open_path(path)

    def open_path(self, path):
        if not path:
            return
        if Path(path).suffix.lower() in ('.mp4','.webm','.mkv','.mov','.avi','.m4v'):
            self.recording_panel.load(path)
            return
        if str(path).lower().endswith('.snapmark.json'):
            from cpp.video.model import Project
            self.recording_panel.jobs.run(lambda:Project.load(path),lambda p:self.recording_panel.editor(p,project_path=path),self.error)
            return
        self.statusBar().showMessage("Opening image…")
        self.jobs.run(lambda: read_image(path), lambda image: self.open_editor(image, path), self.error)

    def open_editor(self, image, path=None, captured=False):
        window = EditorWindow(image, self.settings, path, parent=self)
        self.editors.add(window)
        window.saved.connect(self.record_saved)
        window.file_deleted.connect(self.image_deleted)
        if captured:
            window.capture_badge_action.setVisible(True)
        window.closed.connect(self.editor_closed)
        window.present_after_capture()
        QApplication.alert(window, 3000)
        window.statusBar().showMessage("Screenshot saved — ready to edit" if captured else "Screenshot captured — ready to edit" if path is None else "Image opened", 5000)
        self.statusBar().showMessage("Image opened", 3000)
        return window

    def image_deleted(self,path):
        try:
            self.history.remove(path)
            self.refresh_history()
        except OSError as exc:
            self.error('File deleted, but history could not be updated: '+str(exc))

    def editor_closed(self, window):
        self.editors.discard(window)
        QTimer.singleShot(0, self.maybe_quit_standalone)

    def maybe_quit_standalone(self):
        if not self.standalone or self.editors or self.capturing or self.recording_panel.windows:
            return
        if self.jobs.active or self.recording_panel.busy:
            QTimer.singleShot(100, self.maybe_quit_standalone)
            return
        QApplication.instance().quit()

    def record_saved(self, path):
        try:
            self.history.add(path)
            self.refresh_history()
            self.statusBar().showMessage("Saved " + Path(path).name, 5000)
        except OSError as exc:
            self.error("Image saved, but recent history could not be updated: " + str(exc))

    def refresh_history(self):
        self.history_generation += 1
        generation = self.history_generation
        paths = self.history.entries()
        def load():
            result = []
            for path in paths:
                file = Path(path)
                reader = QImageReader(path)
                reader.setAutoTransform(True)
                size = reader.size()
                if size.isValid():
                    reader.setScaledSize(size.scaled(88, 58, Qt.AspectRatioMode.KeepAspectRatio))
                image = reader.read()
                try:
                    timestamp = datetime.fromtimestamp(file.stat().st_mtime).strftime("%d %b %Y · %H:%M")
                except OSError:
                    timestamp = "File moved or deleted"
                result.append((path, timestamp, image))
            return result
        def ready(rows):
            if generation != self.history_generation:
                return
            self.recent.clear()
            if not rows:
                item = QListWidgetItem("Your saved screenshots will appear here.")
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.recent.addItem(item)
            for path, timestamp, image in rows:
                item = QListWidgetItem(f"{Path(path).name}\n{timestamp}")
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setToolTip(path + "\nDouble-click to open")
                if not image.isNull():
                    item.setIcon(QIcon(QPixmap.fromImage(image)))
                self.recent.addItem(item)
        self.jobs.run(load, ready, self.error)

    def remove_recent(self):
        item = self.recent.currentItem()
        if item and (path := item.data(Qt.ItemDataRole.UserRole)):
            try:
                self.history.remove(path)
                self.refresh_history()
            except OSError as exc:
                self.error(str(exc))

    def open_latest(self):
        entries = self.history.entries()
        if entries:
            self.open_path(entries[0])
        else:
            self.reveal()
            self.statusBar().showMessage("No recent screenshot yet", 4000)

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            settings = dialog.result_settings
            try:
                if settings.launch_at_login != self.settings.launch_at_login:
                    set_autostart(settings.launch_at_login)
                if settings.print_screen != self.settings.print_screen:
                    from cpp.desktop_shortcut import set_print_screen
                    set_print_screen(settings.print_screen)
                settings.save()
            except OSError as exc:
                self.error("Could not save settings: " + str(exc))
                return
            self.settings = settings
            apply_theme(settings.theme)
            self.delay.setCurrentIndex((0, 3, 5, 10).index(settings.delay))
            self.install_shortcuts()
            if hasattr(self, "minimize_button"):
                self.minimize_button.hide()
            self.setup_tray()
            self.statusBar().showMessage("Settings saved · editor defaults apply to newly opened editors", 6000)

    def error(self, message):
        if not self.standalone:
            self.reveal()
        QMessageBox.warning(None if self.standalone else self, "SnapMark", message)
        QTimer.singleShot(0, self.maybe_quit_standalone)

    def closeEvent(self, event):
        if self.recording_panel.busy:
            self.recording_panel.stop()
            event.ignore()
            self.statusBar().showMessage("Finalizing video operation. Please close again when it finishes.", 5000)
            return
        for video in list(self.recording_panel.windows):
            if not video.close():
                event.ignore()
                return
        if self.capturing or self.jobs.active:
            self.cancel_capture()
            event.ignore()
            self.statusBar().showMessage("Please wait for the current operation to finish, then quit.", 5000)
            return
        for editor in list(self.editors):
            if not editor.close():
                event.ignore()
                return
        if self.tray_icon:
            self.tray_icon.hide()
        event.accept()
        QApplication.instance().quit()
