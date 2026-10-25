"""Gap-free edited-sequence timeline with draggable clips and annotation layers."""
from dataclasses import replace
import math
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QScrollArea

class TimelineScroll(QScrollArea):
    zoom_requested=Signal(float,float)
    resized=Signal()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.resized.emit()
    def wheelEvent(self,event):
        delta=event.angleDelta()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            amount=delta.y() or delta.x()
            if amount:
                self.zoom_requested.emit(2**(amount/480),event.position().x())
            event.accept()
        elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier or delta.x():
            bar=self.horizontalScrollBar()
            pixels=event.pixelDelta().x() or event.pixelDelta().y()
            bar.setValue(bar.value()-(pixels if pixels else delta.x() or delta.y()))
            event.accept()
        else:
            super().wheelEvent(event)

class Timeline(QWidget):
    seek=Signal(float)
    trimmed=Signal(float,float)
    annotation_changed=Signal(str,float,float)
    reordered=Signal(int,int)
    selected=Signal(str)
    segment_selected=Signal(int)
    segment_moved=Signal(int,int)
    LABEL=140
    HEADER=30
    ROW=42
    def __init__(self):
        super().__init__()
        self.project=None
        self.position=0
        self.drag=None
        self.bounds=[0,1]
        self.selected_id=None
        self.selected_segment=0
        self._preview=None
        self._clip_slot=None
        self.setMinimumHeight(116)
        self.setMouseTracking(True)
        self.setToolTip('Drag video clips to reorder; deleted clips close up automatically. Drag annotation bars/edges to edit timing, or layer names to reorder overlays. Ctrl+wheel zooms; Shift+wheel scrolls horizontally.')
    def set_project(self,project):
        self.project=project
        self.bounds=[0,project.output_duration]
        self.setMinimumHeight(self.HEADER+self.ROW*(1+len(project.annotations))+12)
        self.update()
    def x(self,seconds):
        return self.LABEL+seconds/self.project.output_duration*max(1,self.width()-self.LABEL-16)
    def seconds(self,x):
        return max(0,min(self.project.output_duration,(x-self.LABEL)/max(1,self.width()-self.LABEL-16)*self.project.output_duration))
    def row_rect(self,row):
        return QRectF(self.LABEL,self.HEADER+row*self.ROW+6,self.width()-self.LABEL-16,self.ROW-12)
    def insertion_slot(self,time):
        return sum(time>(span.start+span.end)/2 for span in self.project.spans)
    def paintEvent(self,event):
        p=QPainter(self)
        p.fillRect(event.rect(),QColor('#20232c'))
        if not self.project:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QColor('#aeb6c7'))
        p.drawText(12,20,'LAYERS')
        pixels=max(1,self.width()-self.LABEL-16)/self.project.output_duration
        choices=(.01,.02,.05,.1,.2,.5,1,2,5,10,15,30,60,120,300,600,1800,3600,7200,14400)
        step=next((s for s in choices if s*pixels>=90),max(14400,self.project.output_duration/5))
        first=max(0,math.floor(self.seconds(event.rect().left())/step))
        last=math.ceil(self.seconds(event.rect().right())/step)
        for index in range(first,last+1):
            t=index*step
            if t>self.project.output_duration:
                break
            px=self.x(t)
            p.setPen(QColor('#aeb6c7'))
            label=f'{int(t)//60}:{t%60:05.2f}' if t>=60 else f'{t:.2f}s'
            p.drawText(int(px)+3,20,label)
            p.setPen(QColor('#303645'))
            p.drawLine(int(px),self.HEADER,int(px),self.height())
        for row in range(1+len(self.project.annotations)):
            y=self.HEADER+row*self.ROW
            p.fillRect(0,y,self.LABEL,self.ROW,QColor('#282d38'))
            p.setPen(QColor('#394150'))
            p.drawLine(0,y+self.ROW,self.width(),y+self.ROW)
            p.setPen(QColor('#e6e9f0'))
            label='Video' if row==0 else self.project.annotations[row-1].drawing.kind.replace('_',' ').title()
            p.drawText(12,y+26,label)
        for span in self.project.spans:
            r=QRectF(self.x(span.start)+1,self.HEADER+6,max(2,self.x(span.end)-self.x(span.start)-2),self.ROW-12)
            p.setPen(QPen(QColor('#f8ad7b') if span.index==self.selected_segment else QColor('#7587a8'),2 if span.index==self.selected_segment else 1))
            p.setBrush(QColor('#526d9f'))
            p.drawRoundedRect(r,4,4)
            p.setPen(QColor('white'))
            p.drawText(r.adjusted(8,0,-4,0),Qt.AlignmentFlag.AlignVCenter,f'Clip {span.index+1} · {span.source_start:.2f}–{span.source_end:.2f}s')
        for i,item in enumerate(self.project.annotations):
            if self._preview and self._preview[0]==item.id:
                item=replace(item,start=self._preview[1],end=self._preview[2])
            for _,start,end in self.project.annotation_spans(item):
                r=QRectF(self.x(start),self.HEADER+(i+1)*self.ROW+6,max(4,self.x(end)-self.x(start)),self.ROW-12)
                color=QColor(item.drawing.color)
                color.setAlpha(150)
                p.setBrush(color)
                p.setPen(QPen(QColor('#f8ad7b') if item.id==self.selected_id else QColor('#6a7387'),2 if item.id==self.selected_id else 1))
                p.drawRoundedRect(r,4,4)
                p.setPen(QColor('white'))
                p.drawText(r.adjusted(7,0,-3,0),Qt.AlignmentFlag.AlignVCenter,f'{start:.2f} – {end:.2f}s')
                for px in (r.left()+3,r.right()-3):
                    p.drawLine(int(px),int(r.top()+7),int(px),int(r.bottom()-7))
        if self._clip_slot is not None:
            spans=self.project.spans
            t=spans[self._clip_slot].start if self._clip_slot<len(spans) else self.project.output_duration
            p.setPen(QPen(QColor('#ffb080'),4))
            p.drawLine(int(self.x(t)),self.HEADER,int(self.x(t)),self.HEADER+self.ROW)
        for t in self.bounds:
            p.fillRect(int(self.x(t))-3,self.HEADER+3,6,self.ROW-6,QColor('#e95420'))
        p.setPen(QPen(QColor('#f7f8fc'),2))
        p.drawLine(int(self.x(self.position)),self.HEADER,int(self.x(self.position)),self.height())
    def annotation_hit(self,row,x):
        if not 1<=row<=len(self.project.annotations):
            return None
        item=self.project.annotations[row-1]
        for clip,start,end in self.project.annotation_spans(item):
            if self.x(start)-7<=x<=self.x(end)+7:
                edge='start' if abs(x-self.x(start))<7 else 'end' if abs(x-self.x(end))<7 else 'move'
                return item,clip,edge
        return None
    def mousePressEvent(self,event):
        if not self.project or event.button()!=Qt.MouseButton.LeftButton:
            return
        x,y=event.position().x(),event.position().y()
        row=int((y-self.HEADER)//self.ROW)
        if 1<=row<=len(self.project.annotations) and x<self.LABEL:
            self.drag=('order',row-1)
        elif (hit:=self.annotation_hit(row,x)):
            item,clip,edge=hit
            span=self.project.spans[clip]
            self.drag=(edge,item.id,span.source_start+self.seconds(x)-span.start,item.start,item.end,clip)
            self.selected_id=item.id
            self.selected.emit(item.id)
        elif row==0:
            handle=next((i for i,t in enumerate(self.bounds) if abs(self.x(t)-x)<8),None)
            if handle is not None:
                self.drag=('trim',handle)
            else:
                span=next((s for s in self.project.spans if self.x(s.start)<=x<=self.x(s.end)),None)
                self.drag=('clip',span.index,x) if span else ('seek',)
                if span:
                    self.selected_segment=span.index
                    self.segment_selected.emit(span.index)
                self.seek.emit(self.seconds(x))
        else:
            self.drag=('seek',)
        self.mouseMoveEvent(event)
    def mouseMoveEvent(self,event):
        if not self.project:
            return
        x,y=event.position().x(),event.position().y()
        if not self.drag:
            row=int((y-self.HEADER)//self.ROW)
            cursor=Qt.CursorShape.PointingHandCursor
            if 1<=row<=len(self.project.annotations) and x<self.LABEL:
                cursor=Qt.CursorShape.SizeVerCursor
            elif (hit:=self.annotation_hit(row,x)):
                cursor=Qt.CursorShape.OpenHandCursor if hit[2]=='move' else Qt.CursorShape.SizeHorCursor
            elif row==0:
                cursor=Qt.CursorShape.SizeHorCursor if min(abs(x-self.x(t)) for t in self.bounds)<8 else Qt.CursorShape.OpenHandCursor
            self.setCursor(cursor)
            return
        t=self.seconds(x)
        kind=self.drag[0]
        if kind=='seek':
            self.seek.emit(t)
        elif kind=='clip':
            if abs(x-self.drag[2])>=5:
                self._clip_slot=self.insertion_slot(t)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif kind=='trim':
            i=self.drag[1]
            epsilon=min(1/self.project.fps,self.bounds[1]-self.bounds[0])
            self.bounds[i]=min(t,self.bounds[1]-epsilon) if i==0 else max(t,self.bounds[0]+epsilon)
        elif kind in ('move','start','end'):
            _,id,origin,a,b,clip=self.drag
            _,source=self.project.source_at(t)
            if kind=='move':
                delta=max(-a,min(source-origin,self.project.duration-b))
                a,b=a+delta,b+delta
            elif kind=='start':
                a=max(0,min(source,b-min(1/self.project.fps,b-a)))
            else:
                b=min(self.project.duration,max(source,a+min(1/self.project.fps,b-a)))
            self._preview=(id,a,b)
        self.update()
    def mouseReleaseEvent(self,event):
        if not self.drag:
            return
        drag,preview,slot=self.drag,self._preview,self._clip_slot
        self._preview=None
        self._clip_slot=None
        self.drag=None
        if drag[0]=='clip' and slot is not None:
            source=drag[1]
            destination=max(0,min(len(self.project.segments)-1,slot-int(source<slot)))
            if source!=destination:
                self.segment_moved.emit(source,destination)
        elif drag[0]=='trim':
            self.trimmed.emit(*self.bounds)
        elif drag[0]=='order':
            destination=max(0,min(len(self.project.annotations)-1,int((event.position().y()-self.HEADER)//self.ROW)-1))
            if destination!=drag[1]:
                self.reordered.emit(drag[1],destination)
        elif preview:
            self.annotation_changed.emit(*preview)
        self.update()
