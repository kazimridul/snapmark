"""Immutable vector annotations and shared rendering for canvas and export."""
from dataclasses import dataclass, replace
import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF


@dataclass(frozen=True)
class Annotation:
    kind: str
    points: tuple[tuple[float, float], ...]
    color: str = "#e95420"
    width: float = 4
    opacity: float = 1
    text: str = ""
    font_size: int = 24
    fill: bool = False
    bold: bool = False
    background: bool = False

    def moved(self, dx: float, dy: float) -> "Annotation":
        return replace(self, points=tuple((x + dx, y + dy) for x, y in self.points))

    def bounds(self) -> QRectF:
        xs, ys = zip(*self.points)
        if self.kind == "text":
            from PySide6.QtGui import QFontMetricsF
            font = QFont("Sans Serif")
            font.setPixelSize(self.font_size)
            font.setBold(self.bold)
            metrics = QFontMetricsF(font)
            lines = self.text.split("\n")
            return QRectF(xs[0], ys[0], max(metrics.horizontalAdvance(s) for s in lines) + 10,
                          metrics.height() * len(lines) + 8)
        return QRectF(min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)).adjusted(
            -self.width*3, -self.width*3, self.width*3, self.width*3)


def paint_annotation(painter: QPainter, a: Annotation) -> None:
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setOpacity(a.opacity)
    color = QColor(a.color)
    painter.setPen(QPen(color, a.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                        Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(color if a.fill or a.kind == "highlight_rect" else Qt.BrushStyle.NoBrush)
    points = [QPointF(x, y) for x, y in a.points]
    rect = QRectF(points[0], points[-1]).normalized()
    if a.kind in ("pen", "highlighter"):
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        if len(points) == 1:
            painter.drawPoint(points[0])
        else:
            painter.drawPath(path)
    elif a.kind == "arrow":
        painter.drawLine(points[0], points[-1])
        angle = math.atan2(points[-1].y()-points[0].y(), points[-1].x()-points[0].x())
        size = max(12, a.width*4)
        tip = points[-1]
        painter.setBrush(color)
        painter.drawPolygon(QPolygonF([tip, QPointF(tip.x()-size*math.cos(angle-.45), tip.y()-size*math.sin(angle-.45)),
                                       QPointF(tip.x()-size*math.cos(angle+.45), tip.y()-size*math.sin(angle+.45))]))
    elif a.kind in ("rectangle", "highlight_rect"):
        if a.kind == "highlight_rect":
            painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(rect)
    elif a.kind == "ellipse":
        painter.drawEllipse(rect)
    elif a.kind == "text":
        font = QFont("Sans Serif")
        font.setPixelSize(a.font_size)
        font.setBold(a.bold)
        painter.setFont(font)
        if a.background:
            painter.fillRect(a.bounds(), QColor("#ffffff"))
        painter.drawText(a.bounds().adjusted(4, 2, -4, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, a.text)
    painter.restore()


def composite(base: QImage, annotations: tuple[Annotation, ...]) -> QImage:
    output = base.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(output)
    for annotation in annotations:
        paint_annotation(painter, annotation)
    painter.end()
    return output
