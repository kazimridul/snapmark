"""Frame-coordinate video preview; the existing image annotation painter is reused."""
from dataclasses import replace
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget, QInputDialog
from cpp.editor.model import Annotation, paint_annotation

class VideoCanvas(QWidget):
    annotation_selected = Signal(str)
    drawn = Signal(object)
    region = Signal(object)
    moved = Signal(str, float, float)
    def __init__(self):
        super().__init__()
        self.setMinimumSize(320, 200)
        self.frame = QImage()
        self.project = None
        self.position = 0
        self.tool = 'select'
        self.style = Annotation('pen', ((0,0),), color='#ffff00', width=12, opacity=.4)
        self.points = []
        self.preview = None
        self.selection = None
        self.drag_id = None
        self.selected_id = None
        self.move_preview = None
        self.target = QRectF()
        self.view_rect = QRectF()
        self.preview_crop = False
        self.timeline_position=0.
        self.animation_preview=None
        self.setMouseTracking(True)
    def set_tool(self, tool):
        from cpp.ui.icons import tool_cursor
        if self.tool==tool:
            self.setCursor(tool_cursor(tool))
            return
        self.tool=tool
        self.points=[]
        self.preview=None
        self.selection=None
        self.setCursor(tool_cursor(tool))
        self.update()

    def point(self, event):
        p = event.position()
        return (max(0,min(self.project.width,self.view_rect.x()+(p.x()-self.target.x())/max(1,self.target.width())*self.view_rect.width())),
                max(0,min(self.project.height,self.view_rect.y()+(p.y()-self.target.y())/max(1,self.target.height())*self.view_rect.height())))
    def paintEvent(self,event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#191b22'))
        if self.frame.isNull() or not self.project:
            p.setPen(QColor('white'))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Loading video…')
            return
        self.view_rect = QRectF(*self.project.crop) if self.preview_crop and self.project.crop else QRectF(0,0,self.project.width,self.project.height)
        size = self.view_rect.size().toSize().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        self.target = QRectF((self.width()-size.width())/2,(self.height()-size.height())/2,size.width(),size.height())
        animation_project=self.animation_preview or self.project
        animated=animation_project.has_animations
        if animated:
            from cpp.video.animation_render import composite_frame
            if self.move_preview:
                import copy
                animation_project=copy.copy(animation_project)
                animation_project.annotations=[replace(a,drawing=self.move_preview[1]) if a.id==self.move_preview[0] else a for a in animation_project.annotations]
            frame=composite_frame(self.frame,animation_project,self.position,self.timeline_position)
        else:
            frame=self.frame
        p.drawImage(self.target,frame,self.view_rect)
        p.save()
        p.translate(self.target.topLeft())
        p.scale(self.target.width()/self.view_rect.width(),self.target.height()/self.view_rect.height())
        p.translate(-self.view_rect.x(),-self.view_rect.y())
        p.setClipRect(self.view_rect)
        for item in ([] if animated else self.project.annotations):
            if self.move_preview and item.id==self.move_preview[0]:
                item=replace(item,drawing=self.move_preview[1])
            if item.active(self.position):
                if item.drawing.kind in ('blur','pixelate'):
                    from cpp.editor.document import State
                    from cpp.editor.effects import privacy_state
                    a,b = item.drawing.points[0],item.drawing.points[-1]
                    r = QRectF(QPointF(*a),QPointF(*b)).normalized().intersected(QRectF(self.frame.rect()))
                    if r.width() >= 2 and r.height() >= 2:
                        # Effects are computed only for the selected region, not the whole video.
                        patch = self.frame.copy(r.toAlignedRect())
                        effect = privacy_state(State(patch), QRectF(patch.rect()),item.drawing.kind,item.strength).base
                        p.drawImage(r.topLeft(),effect)
                else:
                    paint_annotation(p,item.drawing)
        if self.selected_id and self.tool=='select' and self.animation_preview is None:
            selected=next((a for a in self.project.annotations if a.id==self.selected_id and a.active(self.position)),None)
            if selected:
                drawing=self.move_preview[1] if self.move_preview and self.move_preview[0]==selected.id else selected.drawing
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor('#ffffff'),max(1,1/self.target.width()*self.view_rect.width()),Qt.PenStyle.DashLine))
                if selected.animations.enabled:
                    from cpp.video.animation_render import state_for,animation_transform
                    from cpp.video.animation_render import video_matrix
                    matrix,_=video_matrix(self.project,self.timeline_position)
                    p.save();p.setTransform(animation_transform(drawing,state_for(selected.animations,self.position-selected.start,selected.end-selected.start,drawing.text))*matrix,True);p.drawRect(drawing.bounds());p.restore()
                elif self.project.has_animations:
                    from cpp.video.animation_render import video_matrix
                    matrix,_=video_matrix(self.project,self.timeline_position)
                    p.save();p.setTransform(matrix,True);p.drawRect(drawing.bounds());p.restore()
                else:p.drawRect(drawing.bounds())
        if self.preview:
            paint_annotation(p,self.preview)
        if self.project.crop:
            x,y,w,h = self.project.crop
            p.setPen(QPen(QColor('#e95420'),2))
            p.drawRect(QRectF(x,y,w,h))
        if self.selection:
            a,b = self.selection
            r = QRectF(QPointF(*a),QPointF(*b)).normalized()
            p.setPen(QPen(QColor('#ffffff'),2))
            p.drawRect(r)
            p.drawText(r.topLeft()+QPointF(0,-5),f'{int(r.width())} × {int(r.height())}')
        p.restore()
    def mousePressEvent(self,event):
        if not self.project or self.frame.isNull() or not self.target.contains(event.position()):
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = self.point(event)
        self.points = [point]
        self.drag_id = None
        self.drag_origin=event.globalPosition()
        self.drag_scale=max(.001,self.target.width()/self.view_rect.width())
        self.move_preview=None
        if self.tool == 'select':
            for item in reversed(self.project.annotations):
                hit=QPointF(*point)
                visible=item.active(self.position)
                if visible and self.project.has_animations:
                    from cpp.video.animation_render import video_matrix
                    matrix,shown=video_matrix(self.project,self.timeline_position)
                    inverse,ok=matrix.inverted()
                    visible=shown and ok
                    if ok:hit=inverse.map(hit)
                if visible and item.animations.enabled:
                    from cpp.video.animation_render import state_for,animation_transform
                    state=state_for(item.animations,self.position-item.start,item.end-item.start,item.drawing.text)
                    matrix,ok=animation_transform(item.drawing,state).inverted()
                    visible=ok and state['opacity']>0 and state['reveal']>0
                    if ok:hit=matrix.map(hit)
                if visible and item.drawing.bounds().contains(hit):
                    self.drag_id = item.id
                    self.selected_id=item.id
                    self.annotation_selected.emit(item.id)
                    break
            if self.drag_id is None:
                self.selected_id=None
                self.annotation_selected.emit('')
        elif self.tool == 'text':
            text,ok = QInputDialog.getMultiLineText(self,'Video text','Text')
            if ok and text:
                self.drawn.emit(replace(self.style,kind='text',points=(point,),text=text))
            self.points = []
    def mouseMoveEvent(self,event):
        if not self.points:
            return
        point = self.point(event)
        if self.tool=='select' and self.drag_id:
            item=next(a for a in self.project.annotations if a.id==self.drag_id)
            xs,ys=zip(*item.drawing.points)
            delta=event.globalPosition()-self.drag_origin
            dx=max(-min(xs),min(delta.x()/self.drag_scale,self.project.width-max(xs)))
            dy=max(-min(ys),min(delta.y()/self.drag_scale,self.project.height-max(ys)))
            self.move_preview=(item.id,item.drawing.moved(dx,dy))
        if self.tool in ('pen','highlighter'):
            self.points.append(point)
        elif len(self.points)==1:
            self.points.append(point)
        else:
            self.points[-1] = point
        if self.tool in ('crop','blur','pixelate'):
            self.selection = (self.points[0], point)
        elif self.tool != 'select':
            self.preview = replace(self.style,kind=self.tool,points=tuple(self.points))
        self.update()
    def mouseReleaseEvent(self,event):
        if not self.points:
            return
        point = self.point(event)
        if self.tool == 'select' and self.drag_id:
            delta=event.globalPosition()-self.drag_origin
            self.moved.emit(self.drag_id,delta.x()/self.drag_scale,delta.y()/self.drag_scale)
        elif self.tool in ('crop','blur','pixelate'):
            self.region.emit((self.tool,self.points[0],point))
        elif self.tool != 'select' and self.preview:
            self.drawn.emit(self.preview)
        self.points = []
        self.preview = None
        self.move_preview = None
        self.selection = None
        self.update()
