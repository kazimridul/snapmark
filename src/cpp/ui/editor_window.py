from dataclasses import replace
from pathlib import Path
from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFileDialog, QHBoxLayout,
    QInputDialog, QLabel, QMainWindow, QMessageBox, QPushButton, QSizePolicy, QSpinBox, QToolBar, QVBoxLayout, QWidget)
from cpp.clipboard import copy_image
from cpp.editor.canvas import Canvas
from cpp.editor.document import Document, State, crop_state
from cpp.editor.effects import privacy_state
from cpp.editor.model import Annotation, composite
from cpp.jobs import Jobs
from cpp.storage import save_image, suggested_name
from cpp.ui.icons import tool_icon
from cpp.ui.tool_options import ColorPalette, ValueSlider

TOOLS = [("select", "Select / move", "Select and drag annotations; Delete removes the selected annotation"),
         ("pen", "Pen", "Draw a freehand line"),
         ("highlighter", "Highlighter", "Highlight with a translucent freehand stroke"),
         ("highlight_rect", "Highlight area", "Highlight a rectangular area"),
         ("arrow", "Arrow", "Draw an arrow pointing to a detail"),
         ("rectangle", "Rectangle", "Draw an outlined or filled rectangle"),
         ("ellipse", "Ellipse", "Draw an outlined or filled ellipse"),
         ("text", "Text", "Click to add a text annotation"),
         ("blur", "Blur", "Select an area to blur private details"),
         ("pixelate", "Pixelate", "Select an area to pixelate private details"),
         ("crop", "Crop", "Select and adjust the image crop")]



class EditorWindow(QMainWindow):
    saved = Signal(str)
    closed = Signal(object)

    def __init__(self, image, settings, path=None, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.settings = settings
        self.path = path
        self.fresh = path is None
        self.document = Document(image)
        self.jobs = Jobs(self)
        self.busy = False
        self.tool_styles = {}
        self.presentation_timer = QTimer(self)
        self.presentation_timer.setSingleShot(True)
        self.presentation_timer.timeout.connect(self.present)
        self.resize(1200, 800)
        self.setMinimumSize(780, 520)
        self.canvas = Canvas(self.document)
        self.setCentralWidget(self.canvas)
        self.toolbar = QToolBar("File and history", self)
        self.toolbar.setObjectName("mainToolbar")
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.toolbar.setIconSize(QSize(24, 24))
        self.toolbar.setMovable(False)
        self.toolbar_actions = {}
        self.addToolBar(self.toolbar)
        self.undo_action = self.document.undo.createUndoAction(self, "Undo")
        self.redo_action = self.document.undo.createRedoAction(self, "Redo")
        self.undo_action.setShortcut(settings.shortcuts["undo"])
        self.redo_action.setShortcut(settings.shortcuts["redo"])
        self.toolbar.addActions([self.undo_action, self.redo_action])
        self.decorate_toolbar_action(self.undo_action, "undo", "Undo", "Undo the last edit")
        self.decorate_toolbar_action(self.redo_action, "redo", "Redo", "Restore the last undone edit")
        self.toolbar.addSeparator()
        self.action("Crop", lambda: self.choose_tool("crop"), icon_kind="crop", purpose="Crop the image")
        self.toolbar.addSeparator()
        self.action("Save", self.save, settings.shortcuts["save"], "save", "Save the edited image")
        self.action("Save As…", lambda: self.save(True), settings.shortcuts["save_as"], "save_as", "Save to a new file")
        self.action("Copy", self.copy, settings.shortcuts["copy"], "copy", "Copy the edited image to the clipboard")
        self.toolbar.addSeparator()
        self.action("Zoom out", lambda: self.canvas.zoom(1/1.2), "Ctrl+-", "zoom_out", "Zoom out of the image")
        self.action("Zoom in", lambda: self.canvas.zoom(1.2), "Ctrl++", "zoom_in", "Zoom into the image")
        self.action("Fit to window", self.canvas.fit, "Ctrl+0", "fit", "Fit the entire image in the window")
        self.action("Actual size (100%)", self.canvas.actual_size, "Ctrl+1", "actual_size", "Show the image at 100% zoom")
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.toolbar.addWidget(spacer)
        self.capture_badge = QLabel("Screenshot captured")
        self.capture_badge.setObjectName("captureBadge")
        self.capture_badge_action = self.toolbar.addWidget(self.capture_badge)
        self.capture_badge_action.setVisible(path is None)
        self.document.changed.connect(lambda: self.capture_badge_action.setVisible(False))
        self.tools = QToolBar("Annotation tools", self)
        self.tools.setOrientation(Qt.Orientation.Vertical)
        self.tools.setObjectName("toolPalette")
        self.tools.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.tools.setIconSize(QSize(24, 24))
        self.tools.setFixedWidth(64)
        self.tools.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self.tools)
        group = QActionGroup(self)
        self.tool_actions = {}
        for kind, label, purpose in TOOLS:
            action = QAction(tool_icon(kind), label, self)
            action.setCheckable(True)
            action.setToolTip(f"{label} — {purpose}")
            action.setStatusTip(purpose)
            action.triggered.connect(lambda checked=False, k=kind: self.choose_tool(k))
            group.addAction(action)
            self.tools.addAction(action)
            button = self.tools.widgetForAction(action)
            button.setFixedSize(44, 44)
            button.setAccessibleName(label)
            button.setAccessibleDescription(purpose)
            self.tool_actions[kind] = action
        self.options = QToolBar("Tool options", self)
        self.options.setObjectName("contextToolbar")
        self.options.setMovable(False)
        self.addToolBarBreak()
        self.addToolBar(self.options)
        self.options_title = QLabel("Select")
        self.options_title.setObjectName("toolTitle")
        self.options.addWidget(self.options_title)
        self.color = settings.pen_color
        self.colors = ColorPalette()
        self.colors.color_changed.connect(self.set_color)
        self.colors.custom_requested.connect(self.pick_color)
        self.color_button = self.colors.custom_button
        self.width = ValueSlider("Size", 1, 80, settings.pen_width, " px")
        self.opacity = ValueSlider("Opacity", 5, 100, 100, "%")
        self.font_size = self.spin(8, 200, settings.font_size, "Text size", " px")
        self.strength = ValueSlider("Strength", 2, 100, settings.blur_strength, " px")
        self.fill = QCheckBox("Fill")
        self.bold = QCheckBox("Bold")
        self.background = QCheckBox("Text background")
        self.aspect = QComboBox()
        for label, ratio in [("Freeform", 0), ("1:1", 1), ("4:3", 4/3), ("16:9", 16/9)]:
            self.aspect.addItem(label, ratio)
        self.aspect.currentIndexChanged.connect(self.aspect_changed)
        self.option_actions = {}
        for name, widget in [("color", self.colors), ("width", self.width), ("opacity", self.opacity),
                ("font", self.font_size), ("strength", self.strength), ("fill", self.fill), ("bold", self.bold),
                ("background", self.background), ("aspect", self.aspect)]:
            self.option_actions[name] = self.options.addWidget(widget)
        self.apply_button = QPushButton("Crop image")
        self.apply_button.setObjectName("primaryAction")
        self.apply_button.setToolTip("Crop to this area (Enter)")
        self.apply_button.clicked.connect(self.apply_selection)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setToolTip("Cancel crop (Escape)")
        self.cancel_button.clicked.connect(self.canvas.cancel)
        self.option_actions["apply"] = self.options.addWidget(self.apply_button)
        self.option_actions["cancel"] = self.options.addWidget(self.cancel_button)
        self.edit_text_action = self.options.addAction("Edit text…", self.edit_text)
        for widget in (self.width, self.opacity, self.font_size):
            widget.editingFinished.connect(self.change_style)
        self.width.valueChanged.connect(lambda value: self.update_style())
        self.opacity.valueChanged.connect(lambda value: self.update_style())
        self.options_hint = QLabel()
        self.options_hint.setObjectName("toolHint")
        self.options.addWidget(self.options_hint)
        for widget in (self.fill, self.bold, self.background):
            widget.toggled.connect(self.change_style)
        self.canvas.selected.connect(self.annotation_selected)
        self.canvas.text_requested.connect(self.add_text)
        self.canvas.selection_changed.connect(self.selection_ready)
        self.canvas.confirm_requested.connect(self.apply_selection)
        self.canvas.tool_cancelled.connect(self.selection_cancelled)
        self.document.changed.connect(self.update_status)
        self.document.undo.cleanChanged.connect(self.update_status)
        self.document.changed.connect(self.selection_cancelled)
        self.dimensions = QLabel()
        self.zoom_label = QLabel("100%")
        self.statusBar().addPermanentWidget(self.dimensions)
        self.statusBar().addPermanentWidget(self.zoom_label)
        self.canvas.zoom_changed.connect(lambda z: self.zoom_label.setText(f"{z:.0%}"))
        self.choose_tool("select")
        self.update_status()
        QTimer.singleShot(0, self.canvas.fit)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            for collection in ("tool_actions", "toolbar_actions"):
                for kind, action in getattr(self, collection, {}).items():
                    action.setIcon(tool_icon(kind))

    def spin(self, low, high, value, label, suffix):
        widget = QSpinBox()
        widget.setRange(low, high)
        widget.setValue(value)
        widget.setPrefix(label+"  ")
        widget.setSuffix(suffix)
        widget.setToolTip(label)
        widget.setKeyboardTracking(False)
        return widget

    def decorate_toolbar_action(self, action, kind, name, purpose):
        action.setIcon(tool_icon(kind))
        shortcut = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
        action.setToolTip(f"{name} — {purpose}" + (f" ({shortcut})" if shortcut else ""))
        action.setStatusTip(purpose)
        button = self.toolbar.widgetForAction(action)
        button.setFixedSize(44, 44)
        button.setAccessibleName(name)
        button.setAccessibleDescription(purpose)
        self.toolbar_actions[kind] = action

    def action(self, name, callback, shortcut=None, icon_kind=None, purpose=""):
        action = self.toolbar.addAction(name)
        action.triggered.connect(lambda checked=False: callback())
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if icon_kind:
            self.decorate_toolbar_action(action, icon_kind, name, purpose)
        return action

    def choose_tool(self, kind):
        previous = self.canvas.tool
        if previous != "select":
            self.tool_styles[previous] = self.style()
        self.canvas.set_tool(kind)
        self.tool_actions[kind].setChecked(True)
        marker = kind in ("highlighter", "highlight_rect")
        default = Annotation(kind, ((0, 0),),
            self.settings.highlighter_color if marker else self.settings.arrow_color if kind == "arrow" else self.settings.pen_color,
            22 if marker else self.settings.arrow_width if kind == "arrow" else self.settings.pen_width,
            self.settings.highlighter_opacity/100 if marker else 1, font_size=self.settings.font_size)
        self.load_style(self.tool_styles.get(kind, default))
        self.show_options(kind)
        self.statusBar().showMessage({"select": "Drag annotations to move · Delete removes · Space + drag pans",
            "crop": "Drag to crop, adjust the handles, then choose Crop image or press Enter",
            "blur": "Drag over an area to blur it instantly · Ctrl+Z to undo",
            "pixelate": "Drag over an area to pixelate it instantly · Ctrl+Z to undo",
            "text": "Click the image to add text"}.get(kind, "Choose a color and draw · mouse wheel zooms"))

    def load_style(self, annotation):
        widgets = (self.width, self.opacity, self.font_size, self.fill, self.bold, self.background)
        for widget in widgets:
            widget.blockSignals(True)
        self.color = annotation.color
        self.width.setValue(round(annotation.width))
        self.opacity.setValue(round(annotation.opacity*100))
        self.font_size.setValue(annotation.font_size)
        self.fill.setChecked(annotation.fill)
        self.bold.setChecked(annotation.bold)
        self.background.setChecked(annotation.background)
        for widget in widgets:
            widget.blockSignals(False)
        self.update_style()

    def show_options(self, kind):
        visible = set()
        if kind in ("pen", "highlighter", "highlight_rect", "arrow", "rectangle", "ellipse", "text"):
            visible |= {"color", "opacity"}
        if kind in ("pen", "highlighter", "arrow", "rectangle", "ellipse"):
            visible.add("width")
        if kind in ("rectangle", "ellipse"):
            visible.add("fill")
        if kind == "text":
            visible |= {"font", "bold", "background"}
        if kind == "crop":
            visible.add("aspect")
            if not self.canvas.region.isEmpty():
                visible |= {"apply", "cancel"}
        if kind in ("blur", "pixelate"):
            visible.add("strength")
        for key, action in self.option_actions.items():
            action.setVisible(key in visible)
        labels = {tool: label for tool, label, purpose in TOOLS}
        self.options_title.setText(labels[kind])
        self.options_hint.setText({"select": "Click an annotation to edit it",
            "blur": "Drag to blur · Undo to restore", "pixelate": "Drag to pixelate · Undo to restore",
            "crop": "Adjust the area, then crop" if not self.canvas.region.isEmpty() else "Drag to select a crop"}.get(kind, ""))
        self.edit_text_action.setVisible(kind == "text" and self.canvas.selected_index is not None)
        self.apply_button.setEnabled(not self.canvas.region.isEmpty())

    def style(self):
        return Annotation(self.canvas.tool, ((0, 0),), self.color, self.width.value(), self.opacity.value()/100,
                          font_size=self.font_size.value(), fill=self.fill.isChecked(),
                          bold=self.bold.isChecked(), background=self.background.isChecked())

    def update_style(self):
        self.canvas.style = self.style()
        self.colors.set_color(self.color)

    def change_style(self):
        self.update_style()
        index = self.canvas.selected_index
        if self.canvas.tool == "select" and index is not None:
            original = self.document.state.annotations[index]
            style = self.style()
            annotation = replace(original, color=style.color, width=style.width, opacity=style.opacity,
                                 font_size=style.font_size, fill=style.fill, bold=style.bold, background=style.background)
            if annotation != original:
                self.document.replace_annotation(index, annotation)
                self.canvas.selected_index = index
                self.annotation_selected(annotation)
                self.canvas.viewport().update()

    def set_color(self, color):
        self.color = color
        self.change_style()

    def pick_color(self):
        color = QColorDialog.getColor(QColor(self.color), self, "Annotation color")
        if color.isValid():
            self.color = color.name()
            self.change_style()

    def annotation_selected(self, annotation):
        if annotation is None:
            self.edit_text_action.setVisible(False)
            return
        self.load_style(annotation)
        self.show_options(annotation.kind)
        self.edit_text_action.setVisible(annotation.kind == "text")
        self.update_style()

    def add_text(self, point):
        text, ok = QInputDialog.getMultiLineText(self, "Add text", "Text")
        if ok and text.strip():
            self.document.add(replace(self.style(), kind="text", points=((point.x(), point.y()),), text=text))

    def edit_text(self):
        index = self.canvas.selected_index
        if index is None:
            return
        annotation = self.document.state.annotations[index]
        text, ok = QInputDialog.getMultiLineText(self, "Edit text", "Text", annotation.text)
        if ok and text.strip():
            self.document.replace_annotation(index, replace(annotation, text=text))

    def aspect_changed(self):
        self.canvas.ratio = self.aspect.currentData()
        self.canvas.cancel()

    def selection_cancelled(self):
        self.apply_button.setEnabled(False)
        if hasattr(self, "options_hint"):
            self.show_options(self.canvas.tool)

    def selection_ready(self):
        rect = self.canvas.region
        valid = rect.width() >= 2 and rect.height() >= 2
        self.show_options(self.canvas.tool)
        self.apply_button.setEnabled(valid)
        if not valid or self.canvas.tool not in ("blur", "pixelate") or self.busy:
            return
        state, kind, strength = self.document.state, self.canvas.tool, self.strength.value()
        self.set_busy(True, "Applying " + kind + "…")
        def ready(result):
            self.set_busy(False)
            self.document.commit(result, kind.title())
            self.statusBar().showMessage(kind.title() + " applied · Drag another area or use Undo", 5000)
        self.jobs.run(lambda: privacy_state(state, rect, kind, strength), ready, self.operation_failed)

    def apply_selection(self):
        if self.busy or self.canvas.region.isEmpty() or self.canvas.tool != "crop":
            return
        state, rect = self.document.state, self.canvas.region
        self.set_busy(True, "Cropping…")
        def ready(result):
            self.set_busy(False)
            self.document.commit(result, "Crop")
            self.canvas.fit()
        self.jobs.run(lambda: crop_state(state, rect), ready, self.operation_failed)

    def present_after_capture(self):
        self.present()
        # Wait for restored windows/the portal to finish mapping, once only.
        self.presentation_timer.start(150)

    def present(self):
        """Raise only this editor when it opens, without making it always-on-top."""
        self.showNormal()
        self.raise_()
        self.activateWindow()
        handle = self.windowHandle()
        if handle:
            handle.requestActivate()
        self.canvas.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def update_status(self, *args):
        image = self.document.state.base
        dirty = self.fresh or not self.document.undo.isClean()
        name = Path(self.path).name if self.path else "Untitled screenshot"
        self.setWindowTitle(f"{'● ' if dirty else ''}{name} — SnapMark")
        self.dimensions.setText(f"{image.width()} × {image.height()} px  {'· Unsaved' if dirty else '· Saved'}")

    def set_busy(self, busy, message=""):
        self.busy = busy
        self.centralWidget().setEnabled(not busy)
        self.toolbar.setEnabled(not busy)
        self.tools.setEnabled(not busy)
        self.options.setEnabled(not busy)
        self.statusBar().showMessage(message, 4000 if not busy else 0)

    def operation_failed(self, message):
        self.set_busy(False)
        self.canvas.cancel()
        QMessageBox.warning(self, "SnapMark", message)

    def confirm_pending(self):
        if self.canvas.preview is not None or not self.canvas.region.isEmpty():
            QMessageBox.information(self, "Finish selection", "Crop or cancel the selected area before saving or copying.")
            return False
        return True

    def save(self, save_as=False, after=None):
        if self.busy or not self.confirm_pending():
            return
        path = self.path
        if path and Path(path).suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            save_as = True
        if save_as or path is None:
            directory = Path(self.settings.save_directory)
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self.operation_failed("Cannot create the screenshot folder: " + str(exc))
                return
            path, selected = QFileDialog.getSaveFileName(self, "Save image", str(directory/suggested_name(self.settings.export_format)),
                "PNG image (*.png);;JPEG image (*.jpg *.jpeg);;WebP image (*.webp)")
            if not path:
                return
            if not Path(path).suffix:
                path += ".jpg" if selected.startswith("JPEG") else ".webp" if selected.startswith("WebP") else ".png"
                if Path(path).exists() and QMessageBox.question(self, "Replace file?", f"Replace {Path(path).name}?") != QMessageBox.StandardButton.Yes:
                    return
        state = self.document.state
        self.set_busy(True, "Saving image…")
        def work():
            save_image(composite(state.base, state.annotations), path)
            return path
        def ready(saved_path):
            self.path = saved_path
            self.fresh = False
            self.document.undo.setClean()
            self.set_busy(False, "Image saved")
            self.update_status()
            self.saved.emit(saved_path)
            if after:
                QTimer.singleShot(0, after)
        self.jobs.run(work, ready, self.operation_failed)

    def copy(self):
        if self.busy or not self.confirm_pending():
            return
        state = self.document.state
        self.set_busy(True, "Preparing clipboard image…")
        def ready(image):
            self.set_busy(False)
            try:
                copy_image(image)
                self.statusBar().showMessage("Edited image copied · keep SnapMark open until pasted", 6000)
            except Exception as exc:
                self.operation_failed(str(exc))
        self.jobs.run(lambda: composite(state.base, state.annotations), ready, self.operation_failed)

    def closeEvent(self, event):
        self.presentation_timer.stop()
        if self.busy or self.jobs.active:
            event.ignore()
            self.statusBar().showMessage("Please wait for the current operation to finish.", 4000)
            return
        if self.fresh or not self.document.undo.isClean():
            answer = QMessageBox.question(self, "Unsaved image", "Save changes before closing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save)
            if answer == QMessageBox.StandardButton.Save:
                event.ignore()
                self.save(after=self.close)
                return
            if answer != QMessageBox.StandardButton.Discard:
                event.ignore()
                return
        self.closed.emit(self)
        event.accept()
