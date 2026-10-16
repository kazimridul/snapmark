"""Native-resolution scene coordinates independent of viewport scale."""
from dataclasses import replace
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView
from cpp.editor.model import Annotation, paint_annotation


class VectorItem(QGraphicsItem):
    def __init__(self, annotation):
        super().__init__()
        self.annotation = annotation

    def boundingRect(self):
        return self.annotation.bounds()

    def paint(self, painter, option, widget=None):
        paint_annotation(painter, self.annotation)


class Canvas(QGraphicsView):
    zoom_changed = Signal(float)
    selection_changed = Signal()
    selected = Signal(object)
    text_requested = Signal(object)
    confirm_requested = Signal()
    tool_cancelled = Signal()

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setBackgroundBrush(QColor("#262932"))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tool = "select"
        self.style = Annotation("pen", ((0, 0),))
        self.preview = None
        self.region = QRectF()
        self.ratio = 0
        self.selected_index = None
        self._drawing = False
        self._panning = False
        self._space = False
        self._drag_handle = None
        self._move_original = None
        self.document.changed.connect(self.rebuild)
        self.rebuild()

    def rebuild(self):
        self.scene().clear()
        self.scene().addPixmap(QPixmap.fromImage(self.document.state.base))
        for annotation in self.document.state.annotations:
            self.scene().addItem(VectorItem(annotation))
        self.scene().setSceneRect(QRectF(self.document.state.base.rect()))
        self.selected_index = None
        self.preview = None
        self.region = QRectF()
        self.selected.emit(None)
        self.viewport().update()

    def set_tool(self, tool):
        self.cancel()
        self.tool = tool
        self.selected_index = None
        self.selected.emit(None)
        self.setCursor(Qt.CursorShape.ArrowCursor if tool == "select" else Qt.CursorShape.CrossCursor)

    def cancel(self):
        self._drawing = False
        self.preview = None
        self.region = QRectF()
        self.viewport().update()
        self.tool_cancelled.emit()

    def zoom(self, factor):
        current = self.transform().m11()
        target = min(12, max(.025, current*factor))
        self.scale(target/current, target/current)
        self.zoom_changed.emit(target)
        self.viewport().update()

    def fit(self):
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.zoom_changed.emit(self.transform().m11())

    def actual_size(self):
        self.resetTransform()
        self.zoom_changed.emit(1)

    def point(self, event):
        p = self.mapToScene(event.position().toPoint())
        b = self.sceneRect()
        return QPointF(max(0, min(b.width(), p.x())), max(0, min(b.height(), p.y())))

    def handles(self):
        r = self.region
        return [r.topLeft(), QPointF(r.center().x(), r.top()), r.topRight(),
                QPointF(r.right(), r.center().y()), r.bottomRight(),
                QPointF(r.center().x(), r.bottom()), r.bottomLeft(), QPointF(r.left(), r.center().y())]

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton or (self._space and event.button() == Qt.MouseButton.LeftButton):
            self._panning = True
            self._last_pan = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        p = self.point(event)
        if not self.sceneRect().contains(self.mapToScene(event.position().toPoint())):
            return
        self._start = p
        self._drawing = True
        if self.tool == "select":
            self.selected_index = None
            for i in reversed(range(len(self.document.state.annotations))):
                if self.document.state.annotations[i].bounds().contains(p):
                    self.selected_index = i
                    self._move_original = self.document.state.annotations[i]
                    self.preview = self._move_original
                    break
            self.selected.emit(self._move_original if self.selected_index is not None else None)
        elif self.tool == "text":
            self._drawing = False
            self.text_requested.emit(p)
        elif self.tool in ("crop", "blur", "pixelate"):
            self._old_region = QRectF(self.region)
            self._drag_handle = None
            tolerance = 9 / self.transform().m11()
            if not self.region.isEmpty():
                for i, h in enumerate(self.handles()):
                    if (h-p).manhattanLength() < tolerance:
                        self._drag_handle = i
                        break
            if self._drag_handle is None:
                self._drag_handle = "move" if self.region.contains(p) else "new"
                if self._drag_handle == "new":
                    self.region = QRectF(p, p)
        else:
            self.preview = replace(self.style, kind=self.tool, points=((p.x(), p.y()),))
        self.viewport().update()

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.position() - self._last_pan
            self._last_pan = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-round(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value()-round(delta.y()))
            return
        if not self._drawing:
            return super().mouseMoveEvent(event)
        p = self.point(event)
        if self.tool == "select" and self.selected_index is not None:
            self.preview = self._move_original.moved(p.x()-self._start.x(), p.y()-self._start.y())
        elif self.tool in ("crop", "blur", "pixelate"):
            old = self._old_region
            if self._drag_handle == "move":
                r = old.translated(p-self._start)
                r.moveLeft(max(0, min(self.sceneRect().width()-r.width(), r.left())))
                r.moveTop(max(0, min(self.sceneRect().height()-r.height(), r.top())))
            elif self._drag_handle == "new":
                end = QPointF(p)
                if self.ratio and self.tool == "crop":
                    dx, dy = end.x()-self._start.x(), end.y()-self._start.y()
                    w = min(abs(dx), abs(dy)*self.ratio)
                    end = self._start + QPointF(w*(1 if dx >= 0 else -1), w/self.ratio*(1 if dy >= 0 else -1))
                r = QRectF(self._start, end).normalized()
            else:
                r = QRectF(old)
                i = self._drag_handle
                if i in (0, 6, 7): r.setLeft(p.x())
                if i in (2, 3, 4): r.setRight(p.x())
                if i in (0, 1, 2): r.setTop(p.y())
                if i in (4, 5, 6): r.setBottom(p.y())
                r = r.normalized()
                if self.ratio and self.tool == "crop":
                    w = min(r.width(), (self.sceneRect().bottom()-r.top())*self.ratio)
                    r.setWidth(w)
                    r.setHeight(w/self.ratio)
            self.region = r.intersected(self.sceneRect())
        elif self.preview is not None:
            pts = self.preview.points
            if self.tool in ("pen", "highlighter"):
                if abs(p.x()-pts[-1][0])+abs(p.y()-pts[-1][1]) > .5:
                    self.preview = replace(self.preview, points=pts+((p.x(), p.y()),))
            else:
                self.preview = replace(self.preview, points=(pts[0], (p.x(), p.y())))
        self.viewport().update()

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor if self.tool == "select" else Qt.CursorShape.CrossCursor)
            return
        if not self._drawing:
            return
        self._drawing = False
        if self.tool in ("crop", "blur", "pixelate"):
            self.selection_changed.emit()
        elif self.tool == "select" and self.selected_index is not None and self.preview is not None:
            index, preview = self.selected_index, self.preview
            if preview != self._move_original:
                self.document.replace_annotation(index, preview)
                self.selected_index = index
                self.selected.emit(preview)
            self.preview = None
        elif self.preview is not None:
            preview = self.preview
            self.preview = None
            if self.tool in ("pen", "highlighter") or len(preview.points) > 1:
                self.document.add(preview)
        self.viewport().update()

    def drawForeground(self, painter, rect):
        if self.preview is not None:
            # Cover the old vector position while dragging by redrawing the base and other vectors.
            if self.tool == "select" and self.selected_index is not None:
                painter.drawImage(QPointF(0, 0), self.document.state.base)
                for i, a in enumerate(self.document.state.annotations):
                    if i != self.selected_index:
                        paint_annotation(painter, a)
            paint_annotation(painter, self.preview)
        scale = self.transform().m11()
        if self.selected_index is not None and self.selected_index < len(self.document.state.annotations):
            bounds = (self.preview or self.document.state.annotations[self.selected_index]).bounds()
            painter.setPen(QPen(QColor("#e95420"), 1/scale, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(bounds)
        if not self.region.isEmpty():
            if self.tool == "crop":
                shade = QPainterPath()
                shade.addRect(self.sceneRect())
                shade.addRect(self.region)
                painter.fillPath(shade, QColor(0, 0, 0, 120))
            painter.setPen(QPen(QColor("#ffffff"), 1.5/scale))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.region)
            painter.setBrush(QColor("#e95420"))
            size = 7/scale
            for h in self.handles():
                painter.drawRect(QRectF(h.x()-size/2, h.y()-size/2, size, size))
            painter.save()
            font = painter.font()
            font.setPixelSize(max(1, round(13/scale)))
            painter.setFont(font)
            label = f"{round(self.region.width())} × {round(self.region.height())} px"
            box = QRectF(self.region.left(), max(0, self.region.top()-26/scale), 180/scale, 23/scale)
            painter.fillRect(box, QColor("#262932"))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, label)
            painter.restore()

    def wheelEvent(self, event):
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.zoom(1.15 if event.angleDelta().y() > 0 else 1/1.15)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self._space = True
            return
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not self.region.isEmpty():
            self.confirm_requested.emit()
            return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.selected_index is not None:
            self.document.remove(self.selected_index)
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self._space = False
        super().keyReleaseEvent(event)
