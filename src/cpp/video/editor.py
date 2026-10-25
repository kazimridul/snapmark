"""Dedicated non-destructive video workspace."""
import copy
from dataclasses import replace
from pathlib import Path
import threading
from PySide6.QtCore import Qt, QUrl, QSize, Signal, QTimer
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QDockWidget, QToolBar, QToolButton, QButtonGroup, QSizePolicy, QMainWindow, QMessageBox, QPushButton,
    QProgressBar, QSpinBox, QSplitter, QScrollArea, QVBoxLayout, QWidget, QLineEdit, QAbstractSpinBox, QTextEdit)
from cpp.ui.icons import tool_icon
from cpp.jobs import Jobs
from cpp.video.canvas import VideoCanvas
from cpp.video.model import History, Project, TimedAnnotation
from cpp.video.player import Player, timestamp
from cpp.video.render import ExportSettings, export
from cpp.video.timeline import Timeline, TimelineScroll

class VideoEditor(QMainWindow):
    export_progress = Signal(int)
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('SnapMark — '+Path(project.source).name)
        self.resize(1320,900)
        self.history=History(project)
        self.jobs=Jobs(self)
        self.cancelled=threading.Event()
        self.dirty=False
        self.clean_project=copy.deepcopy(project)
        self.project_path=None
        self.exported=None
        self.setDockNestingEnabled(True)
        self.setCorner(Qt.Corner.BottomLeftCorner,Qt.DockWidgetArea.BottomDockWidgetArea)
        self.setCorner(Qt.Corner.BottomRightCorner,Qt.DockWidgetArea.BottomDockWidgetArea)

        header=QToolBar('Project',self)
        header.setObjectName('mainToolbar')
        header.setIconSize(QSize(22,22))
        header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        header.setMovable(False)
        self.addToolBar(header)
        self.header_actions={}
        for name,label,fn in [('save','Save project · Ctrl+S',self.save_project),('undo','Undo · Ctrl+Z',self.undo),('redo','Redo · Ctrl+Y',self.redo),('fullscreen','Full screen · Escape to exit',self.fullscreen)]:
            action=header.addAction(tool_icon(name),label)
            action.triggered.connect(fn)
            self.header_actions[name]=action
        header.addSeparator()
        filename=QLabel(Path(project.source).name)
        filename.setToolTip(project.source+'\nThe source is preserved; export writes a separate file.')
        filename.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)
        filename.setMargin(8)
        header.addWidget(filename)
        self.animation_action=header.addAction(tool_icon('animation'),'Animations and clip transitions…')
        self.animation_action.triggered.connect(lambda:self.open_animations())
        self.file_properties_action=header.addAction(tool_icon('info'),'File properties')
        self.file_properties_action.triggered.connect(self.file_properties)
        self.delete_file_action=header.addAction(tool_icon('delete'),'Delete source video from storage…')
        self.delete_file_action.triggered.connect(self.delete_from_storage)
        self.export_action=header.addAction(tool_icon('save_as'),'Export separate MP4…')
        self.export_action.triggered.connect(self.export)

        center=QWidget()
        center_layout=QVBoxLayout(center)
        center_layout.setContentsMargins(8,8,8,4)
        self.canvas=VideoCanvas()
        self.canvas.project=project
        self.canvas.drawn.connect(self.add_annotation)
        self.canvas.region.connect(self.region)
        self.canvas.moved.connect(self.move_annotation)
        self.canvas.annotation_selected.connect(self.select_id)
        center_layout.addWidget(self.canvas,1)
        self.player=Player(self,self.canvas)
        self.player.media.errorOccurred.connect(lambda _,message:self.error(message))
        self.player.sequence.changed.connect(self.position)
        center_layout.addWidget(self.player.controls)
        self.setCentralWidget(center)

        # The compatibility selector is hidden: tool choice comes from the icon rail.
        self.tool=QComboBox(self)
        kinds=['select','crop','highlighter','highlight_rect','pen','arrow','rectangle','ellipse','text','blur','pixelate']
        self.tool.addItems(kinds)
        self.tool.hide()
        self.tool.currentTextChanged.connect(self.set_tool)
        self.tools_dock=self.dock('Tools','videoTools',Qt.DockWidgetArea.LeftDockWidgetArea)
        tools_surface=QWidget()
        tools_layout=QHBoxLayout(tools_surface)
        tools_layout.setContentsMargins(5,8,5,8)
        rail=QVBoxLayout()
        rail.setSpacing(5)
        rail.setContentsMargins(0,0,0,0)
        self.tool_buttons={}
        self.tool_group=QButtonGroup(self)
        self.tool_group.setExclusive(True)
        labels={'select':'Select / move','crop':'Crop video','highlighter':'Freehand highlighter','highlight_rect':'Highlight rectangle','pen':'Pen','arrow':'Arrow','rectangle':'Rectangle','ellipse':'Ellipse','text':'Text','blur':'Blur region','pixelate':'Pixelate region'}
        for kind in kinds:
            button=QToolButton()
            button.setIcon(tool_icon(kind))
            button.setIconSize(QSize(23,23))
            button.setFixedSize(42,42)
            button.setCheckable(True)
            button.setToolTip(labels[kind])
            button.setAccessibleName(labels[kind])
            button.clicked.connect(lambda checked=False,k=kind:self.tool.setCurrentText(k))
            self.tool_group.addButton(button)
            rail.addWidget(button)
            self.tool_buttons[kind]=button
        self.tool_buttons['select'].setChecked(True)
        rail.addStretch()
        rail_surface=QWidget()
        rail_surface.setLayout(rail)
        rail_scroll=QScrollArea()
        rail_scroll.setWidgetResizable(True)
        rail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rail_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        rail_scroll.setFixedWidth(64)
        rail_scroll.setWidget(rail_surface)
        tools_layout.addWidget(rail_scroll,0,Qt.AlignmentFlag.AlignLeft)

        self.properties=QWidget()
        prop=QVBoxLayout(self.properties)
        prop.setContentsMargins(6,0,2,0)
        self.property_title=QLabel('Tool properties')
        self.property_title.setObjectName('section')
        prop.addWidget(self.property_title)
        self.property_rows={}
        self.width_control=self.spin(1,100,12)
        self.opacity=self.spin(0,100,40)
        self.font=self.spin(6,200,24)
        self.strength=self.spin(2,100,20)
        self.fill=QCheckBox('Fill shape')
        self.background=QCheckBox('Text background')
        color_button=QPushButton('Color…')
        color_button.clicked.connect(self.color)
        for key,label,widget in [('color','Color',color_button),('width','Thickness',self.width_control),('opacity','Opacity %',self.opacity),('font','Text size',self.font),('strength','Privacy strength',self.strength),('fill','',self.fill),('background','',self.background)]:
            row=QWidget()
            box=QVBoxLayout(row)
            box.setContentsMargins(0,2,0,2)
            if label:
                box.addWidget(QLabel(label))
            box.addWidget(widget)
            prop.addWidget(row)
            self.property_rows[key]=row
        for widget in (self.width_control,self.opacity,self.font,self.strength):
            widget.valueChanged.connect(self.style)
        self.fill.toggled.connect(self.style)
        self.background.toggled.connect(self.style)
        self.timing_properties=QWidget()
        timing=QFormLayout(self.timing_properties)
        timing.setContentsMargins(0,6,0,2)
        self.start,self.end=self.time_spin(0),self.time_spin(min(3,project.duration))
        timing.addRow('From (s)',self.start)
        timing.addRow('Until (s)',self.end)
        prop.addWidget(self.timing_properties)
        self.apply_properties=QPushButton('Apply to selected layer')
        self.apply_properties.clicked.connect(self.update_annotation)
        prop.addWidget(self.apply_properties)
        self.text_button=QPushButton('Edit text…')
        self.text_button.clicked.connect(self.edit_text)
        prop.addWidget(self.text_button)
        self.geometry_box=QWidget()
        geometry=QFormLayout(self.geometry_box)
        geometry.setContentsMargins(0,6,0,2)
        self.geometry_controls=[]
        for label,limit in [('X',project.width),('Y',project.height),('Width',project.width),('Height',project.height)]:
            control=QDoubleSpinBox()
            control.setRange(0,limit)
            control.setDecimals(1)
            control.setKeyboardTracking(False)
            control.editingFinished.connect(self.resize_annotation)
            geometry.addRow(label,control)
            self.geometry_controls.append(control)
        self.buttons(geometry,[('Move / resize',self.resize_annotation)])
        prop.addWidget(self.geometry_box)
        self.delete_button=QPushButton('Delete selected layer')
        self.delete_button.setIcon(tool_icon('delete'))
        self.delete_button.clicked.connect(self.delete_annotation)
        prop.addWidget(self.delete_button)
        self.crop_properties=QWidget()
        crop_layout=QVBoxLayout(self.crop_properties)
        crop_layout.setContentsMargins(0,4,0,4)
        self.crop_preview=QCheckBox('Preview cropped frame')
        self.crop_preview.toggled.connect(self.preview_crop)
        crop_layout.addWidget(self.crop_preview)
        self.buttons(crop_layout,[('Adjust crop…',self.open_crop_dialog),('Clear crop',lambda:self.edit(lambda p:setattr(p,'crop',None)))])
        prop.addWidget(self.crop_properties)
        self.tool_hint=QLabel('Pause, then draw on the preview. Layer timing uses the original video.')
        self.tool_hint.setWordWrap(True)
        prop.addWidget(self.tool_hint)
        prop.addStretch()
        property_scroll=QScrollArea()
        property_scroll.setWidgetResizable(True)
        property_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        property_scroll.setMinimumWidth(175)
        property_scroll.setWidget(self.properties)
        self.property_scroll=property_scroll
        tools_layout.addWidget(property_scroll,1)
        self.tools_dock.setWidget(tools_surface)

        self.outline_dock=self.dock('Outline','videoOutline',Qt.DockWidgetArea.RightDockWidgetArea)
        outline=QWidget()
        outline_layout=QVBoxLayout(outline)
        outline_layout.setContentsMargins(10,8,10,8)
        outline_layout.addWidget(QLabel('Layers'))
        self.annotations=QListWidget()
        self.annotations.setToolTip('Select a layer to show its properties on the left. Drag timeline bars to change timing.')
        self.annotations.currentRowChanged.connect(self.select_annotation)
        self.annotations.itemClicked.connect(lambda _:self.activate_select())
        outline_layout.addWidget(self.annotations,2)
        outline_layout.addWidget(QLabel('Changes'))
        self.changes=QListWidget()
        self.changes.setToolTip('Edit history for this session; Undo/Redo updates this outline.')
        outline_layout.addWidget(self.changes,1)
        self.outline_dock.setWidget(outline)

        self.timeline_dock=self.dock('Timeline','videoTimeline',Qt.DockWidgetArea.BottomDockWidgetArea)
        bottom=QWidget()
        bottom_layout=QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(10,6,10,8)
        actions=QHBoxLayout()
        for icon,label,fn in [('previous','Previous frame',lambda:self.step(-1)),('next','Next frame',lambda:self.step(1)),('split','Split at playhead',self.split),('delete','Remove selected video segment',self.remove_segment),('zoom_out','Zoom timeline out',lambda:self.zoom_timeline(.5)),('zoom_in','Zoom timeline in',lambda:self.zoom_timeline(2)),('fit','Fit full edited sequence',self.fit_timeline)]:
            button=QToolButton()
            button.setIcon(tool_icon(icon))
            button.setIconSize(QSize(20,20))
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.clicked.connect(fn)
            actions.addWidget(button)
        self.segments=QComboBox()
        self.segments.setToolTip('Selected video segment')
        actions.addWidget(self.segments)
        actions.addWidget(QLabel('Drag clips to reorder · Ctrl+wheel to zoom · Shift+wheel to scroll'))
        actions.addStretch()
        bottom_layout.addLayout(actions)
        self.timeline=Timeline()
        self.timeline.seek.connect(self.player.seek_timeline)
        self.timeline.trimmed.connect(lambda a,b:self.edit(lambda p:p.trim_timeline(a,b)))
        self.timeline.annotation_changed.connect(self.change_timing)
        self.timeline.reordered.connect(self.reorder_layers)
        self.timeline.selected.connect(self.select_id)
        self.timeline.segment_selected.connect(self.segments.setCurrentIndex)
        self.timeline.segment_moved.connect(self.move_segment)
        self.timeline.join_selected.connect(lambda index:self.open_animations(('join',index)))
        self.timeline.edge_selected.connect(lambda phase:self.open_animations(('video',None),phase))
        self.timeline.animation_requested.connect(lambda id:self.open_animations(('annotation',id)))
        self.segments.currentIndexChanged.connect(self.select_segment)
        self.timeline_zoom=1.
        self.timeline_scroll=TimelineScroll()
        self.timeline_scroll.setWidgetResizable(True)
        self.timeline_scroll.setMinimumHeight(100)
        self.timeline_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.timeline_scroll.setWidget(self.timeline)
        self.timeline_scroll.zoom_requested.connect(self.zoom_timeline)
        self.timeline_scroll.resized.connect(self.resize_timeline)
        bottom_layout.addWidget(self.timeline_scroll,1)
        trims=QHBoxLayout()
        self.trim_start,self.trim_end=self.time_spin(0),self.time_spin(project.duration)
        trims.addWidget(QLabel('Trim from'))
        trims.addWidget(self.trim_start)
        trims.addWidget(QLabel('to'))
        trims.addWidget(self.trim_end)
        self.buttons(trims,[('Apply trim',lambda:self.edit(lambda p:p.trim_timeline(self.trim_start.value(),self.trim_end.value())))])
        trims.addStretch()
        self.quality=QComboBox()
        self.quality.addItems(['Draft','Standard','High'])
        self.quality.setCurrentIndex(1)
        self.quality.setToolTip('MP4 export quality')
        trims.addWidget(self.quality)
        self.export_button=QPushButton('Export MP4…')
        self.export_button.setIcon(tool_icon('save_as'))
        self.export_button.clicked.connect(self.export)
        trims.addWidget(self.export_button)
        bottom_layout.addLayout(trims)
        self.export_progress_row=QWidget()
        progress_row=QHBoxLayout(self.export_progress_row)
        progress_row.setContentsMargins(0,0,0,0)
        self.progress=QProgressBar()
        self.progress.setMaximumHeight(16)
        self.export_progress.connect(self.progress.setValue)
        progress_row.addWidget(self.progress,1)
        self.buttons(progress_row,[('Cancel export',self.cancelled.set)])
        self.export_progress_row.hide()
        bottom_layout.addWidget(self.export_progress_row)
        self.timeline_dock.setWidget(bottom)
        self.resizeDocks([self.tools_dock,self.outline_dock],[270,240],Qt.Orientation.Horizontal)
        self.resizeDocks([self.timeline_dock],[360],Qt.Orientation.Vertical)
        self.show_properties('select')
        self.canvas.set_tool('select')
        self.refresh()
        self.player.open(project.source)

    def dock(self,title,name,area):
        dock=QDockWidget(title,self)
        dock.setObjectName(name)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable|QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.addDockWidget(area,dock)
        return dock

    def resize_timeline(self):
        base=max(1,self.timeline_scroll.viewport().width())
        self.timeline.setMinimumWidth(min(128000,round(base*self.timeline_zoom)))

    def zoom_timeline(self,factor,anchor=None):
        view=self.timeline_scroll
        anchor=view.viewport().width()/2 if anchor is None else anchor
        bar=view.horizontalScrollBar()
        seconds=self.timeline.seconds(bar.value()+anchor)
        self.timeline_zoom=max(1,min(128,self.timeline_zoom*factor))
        self.resize_timeline()
        # Qt updates the scrollbar range on the following layout pass.
        QTimer.singleShot(0,lambda:bar.setValue(round(self.timeline.x(seconds)-anchor)))

    def fit_timeline(self):
        self.timeline_zoom=1.
        self.resize_timeline()
        self.timeline_scroll.horizontalScrollBar().setValue(0)

    def select_segment(self,index):
        self.timeline.selected_segment=index
        self.timeline.update()

    def move_segment(self,source,destination):
        self.edit(lambda p:p.move_segment(source,destination))
        self.segments.setCurrentIndex(destination)

    def show_properties(self,kind,selected=False):
        visible=kind!='select' or selected
        was_visible=not self.property_scroll.isHidden()
        self.property_scroll.setVisible(visible)
        if was_visible!=visible:
            self.resizeDocks([self.tools_dock],[300 if visible else 82],Qt.Orientation.Horizontal)
        self.property_title.setText(kind.replace('_',' ').title())
        privacy=kind in ('blur','pixelate')
        shapes=kind in ('rectangle','ellipse')
        for key,row in self.property_rows.items():
            row.setVisible({'color':kind not in ('select','crop','blur','pixelate'),'width':kind in ('pen','highlighter','arrow','rectangle','ellipse'),'opacity':kind not in ('select','crop','blur','pixelate'),'font':kind=='text','strength':privacy,'fill':shapes,'background':kind=='text'}[key])
        self.timing_properties.setVisible(kind not in ('select','crop'))
        self.apply_properties.setVisible(selected)
        self.text_button.setVisible(selected and kind=='text')
        self.geometry_box.setVisible(selected)
        self.delete_button.setVisible(selected)
        self.crop_properties.setVisible(kind=='crop')
        self.tool_hint.setText('Static privacy region; it does not track moving objects. Weak blur may leave details readable.' if privacy else 'Adjust crop opens the crop workspace. Preview shows the resulting frame.' if kind=='crop' else 'Pause, then drag on the preview. Geometry fields apply when you finish editing a value.')

    def activate_select(self):
        self.player.pause()
        self.tool.blockSignals(True)
        self.tool.setCurrentText('select')
        self.tool.blockSignals(False)
        self.tool_buttons['select'].setChecked(True)
        self.canvas.set_tool('select')

    def select_id(self,id,preserve_tool=False):
        if not preserve_tool:
            self.activate_select()
        if not id:
            self.annotations.setCurrentRow(-1)
            self.timeline.selected_id=None
            self.canvas.selected_id=None
            self.canvas.update()
            self.timeline.update()
            return
        for i,item in enumerate(self.history.project.annotations):
            if item.id==id:
                self.annotations.setCurrentRow(i)
                self.select_annotation(i)
                self.timeline.selected_id=id
                self.timeline.update()
                break

    def change_timing(self,id,start,end):
        def update(p):
            item=next(a for a in p.annotations if a.id==id)
            item.start,item.end=start,end
        self.edit(update)
        self.select_id(id)

    def reorder_layers(self,source,destination):
        def reorder(p):
            item=p.annotations.pop(source)
            p.annotations.insert(destination,item)
        self.edit(reorder)
        self.annotations.setCurrentRow(destination)
    @staticmethod
    def buttons(layout,items):
        for text,fn in items:
            button = QPushButton(text)
            button.clicked.connect(fn)
            layout.addWidget(button)
    @staticmethod
    def spin(low,high,value):
        spin = QSpinBox()
        spin.setRange(low,high)
        spin.setValue(value)
        return spin
    def time_spin(self,value):
        spin = QDoubleSpinBox()
        spin.setDecimals(3)
        spin.setRange(0,self.history.project.duration)
        spin.setValue(value)
        spin.setSingleStep(1/self.history.project.fps)
        return spin
    def error(self,message):
        QMessageBox.warning(self,'SnapMark video',str(message))
    def edit(self,fn):
        try:
            if not self.history.edit(fn):
                return
            self.dirty = self.history.project != self.clean_project
            self.refresh()
        except (ValueError,TypeError) as exc:
            self.error(exc)
    def refresh(self):
        p = self.history.project
        self.canvas.project = p
        self.canvas.update()
        self.timeline.set_project(p)
        self.player.sequence.set_project(p)
        selected_id=self.timeline.selected_id
        self.annotations.blockSignals(True)
        row = self.annotations.currentRow()
        self.annotations.clear()
        for a in p.annotations:
            item=QListWidgetItem(tool_icon(a.drawing.kind),f'{a.drawing.kind.replace("_"," ").title()}{" ✦" if a.animations.enabled else ""}  {a.start:.2f}–{a.end:.2f}s')
            item.setToolTip(f'Layer {a.id} · original-frame coordinates')
            self.annotations.addItem(item)
        restored=next((i for i,a in enumerate(p.annotations) if a.id==selected_id),-1)
        self.annotations.setCurrentRow(restored)
        if restored<0:
            self.timeline.selected_id=None
            self.show_properties(self.canvas.tool)
        self.annotations.blockSignals(False)
        self.changes.clear()
        self.changes.addItem('Opened '+Path(p.source).name)
        states=self.history.past+[p]
        for before,after in zip(states,states[1:]):
            if before.video_animations!=after.video_animations or before.transitions!=after.transitions:
                label='Changed video animations / transitions'
            elif before.crop!=after.crop:
                label='Changed crop' if after.crop else 'Cleared crop'
            elif before.segments!=after.segments:
                label='Changed video segments / trim'
            elif len(before.annotations)<len(after.annotations):
                label='Added '+after.annotations[-1].drawing.kind.replace('_',' ')
            elif len(before.annotations)>len(after.annotations):
                label='Deleted annotation layer'
            elif [a.id for a in before.annotations]!=[a.id for a in after.annotations]:
                label='Reordered layers'
            else:
                label='Changed layer timing / properties'
            self.changes.addItem(label)
        self.changes.scrollToBottom()
        self.header_actions['undo'].setEnabled(bool(self.history.past))
        self.header_actions['redo'].setEnabled(bool(self.history.future))
        segment_index=max(0,self.segments.currentIndex())
        self.segments.blockSignals(True)
        self.segments.clear()
        for i,(a,b) in enumerate(p.segments):
            self.segments.addItem(f'{i+1}: {a:.3f}–{b:.3f}s')
        self.segments.setCurrentIndex(min(segment_index,len(p.segments)-1))
        self.segments.blockSignals(False)
        self.select_segment(self.segments.currentIndex())
        self.trim_start.setRange(0,p.output_duration)
        self.trim_end.setRange(0,p.output_duration)
        self.trim_start.setValue(0)
        self.trim_end.setValue(p.output_duration)
        if self.annotations.currentRow()>=0:
            self.select_annotation(self.annotations.currentRow())
        self.statusBar().showMessage(f'Output duration {p.output_duration:.3f}s · Frame {round(self.player.media.position()/1000*p.fps)} · {p.width} × {p.height}')
    def undo(self):
        self.history.undo()
        self.dirty=self.history.project != self.clean_project
        self.refresh()
    def redo(self):
        self.history.redo()
        self.dirty=self.history.project != self.clean_project
        self.refresh()
    def set_tool(self,tool):
        self.player.pause()
        self.canvas.set_tool(tool)
        self.tool_buttons[tool].setChecked(True)
        self.annotations.setCurrentRow(-1)
        self.canvas.selected_id=None
        self.timeline.selected_id=None
        self.timeline.update()
        self.show_properties(tool)
        if tool in ('highlighter','highlight_rect'):
            self.canvas.style=replace(self.canvas.style,color='#ffff00')
            self.opacity.setValue(40)
        elif tool not in ('select','crop','blur','pixelate'):
            self.opacity.setValue(100)
        if tool=='crop':
            self.canvas.set_tool('select')
            self.open_crop_dialog()
        if not self.annotations.currentItem():
            start=self.player.media.position()/1000
            self.start.setValue(start)
            self.end.setValue(min(self.history.project.duration,start+3))
    def style(self,*_):
        if hasattr(self,'canvas'):
            self.canvas.style=replace(self.canvas.style,width=self.width_control.value(),opacity=self.opacity.value()/100,font_size=self.font.value(),fill=self.fill.isChecked(),background=self.background.isChecked())
    def color(self):
        color=QColorDialog.getColor(QColor(self.canvas.style.color),self)
        if color.isValid():
            self.canvas.style=replace(self.canvas.style,color=color.name())
    def add_annotation(self,drawing):
        item=TimedAnnotation(drawing,self.start.value(),self.end.value(),strength=self.strength.value())
        self.edit(lambda p:p.annotations.append(item))
        self.select_id(item.id,preserve_tool=True)
    def region(self,region):
        tool,a,b=region
        x,y=int(min(a[0],b[0])),int(min(a[1],b[1]))
        w,h=int(abs(b[0]-a[0])),int(abs(b[1]-a[1]))
        if w<2 or h<2:
            return
        if tool=='crop':
            self.open_crop_dialog()
        else:
            self.add_annotation(replace(self.canvas.style,kind=tool,points=(a,b)))
    def selected(self):
        row=self.annotations.currentRow()
        return row if 0<=row<len(self.history.project.annotations) else None
    def select_annotation(self,row):
        if not 0<=row<len(self.history.project.annotations):
            if hasattr(self,"property_scroll"):
                self.show_properties(self.canvas.tool)
            return
        a=self.history.project.annotations[row]
        if not a.active(self.player.sequence.source):
            spans=self.history.project.annotation_spans(a)
            if spans:
                self.player.pause()
                self.player.seek_timeline(spans[0][1])
        self.show_properties(a.drawing.kind,selected=True)
        self.timeline.selected_id=a.id
        self.canvas.selected_id=a.id
        self.canvas.update()
        self.timeline.update()
        self.start.setValue(a.start)
        self.end.setValue(a.end)
        self.canvas.style=a.drawing
        controls=[self.width_control,self.opacity,self.font,self.strength,self.fill,self.background]
        for control in controls:
            control.blockSignals(True)
        self.width_control.setValue(round(a.drawing.width))
        self.opacity.setValue(round(a.drawing.opacity*100))
        self.font.setValue(a.drawing.font_size)
        self.strength.setValue(a.strength)
        self.fill.setChecked(a.drawing.fill)
        self.background.setChecked(a.drawing.background)
        for control in controls:
            control.blockSignals(False)
        x,y,w,h=self.annotation_geometry(a.drawing)
        for control,value in zip(self.geometry_controls,[x,y,w,h]):
            control.setValue(value)
        self.geometry_loaded=tuple(c.value() for c in self.geometry_controls)
    def preview_crop(self,checked):
        self.canvas.preview_crop=checked
        self.canvas.update()
    def open_crop_dialog(self):
        if self.canvas.frame.isNull():
            self.statusBar().showMessage('Wait for the video frame to load, then choose Crop.',5000)
            return
        from cpp.video.crop_dialog import VideoCropDialog
        dialog=VideoCropDialog(self.canvas.frame,self.history.project.crop,self)
        if dialog.exec():
            crop=dialog.crop
            if crop==(0,0,self.history.project.width,self.history.project.height):
                crop=None
            self.edit(lambda p:setattr(p,'crop',crop))
            self.crop_preview.setChecked(True)

    @staticmethod
    def annotation_geometry(drawing):
        if drawing.kind=='text':
            r=drawing.bounds()
            return r.x(),r.y(),r.width(),r.height()
        xs,ys=zip(*drawing.points)
        return min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)

    def resize_annotation(self):
        row=self.selected()
        if row is None:
            return
        item=self.history.project.annotations[row]
        requested=tuple(c.value() for c in self.geometry_controls)
        loaded=getattr(self,'geometry_loaded',None)
        if requested==loaded:
            return
        original=self.annotation_geometry(item.drawing)
        x,y,w,h=[old if loaded and value==base else value for value,base,old in zip(requested,loaded or requested,original)]
        p=self.history.project
        w,h=min(w,p.width-x),min(h,p.height-y)
        ox,oy,ow,oh=original
        drawing=item.drawing
        if drawing.kind=='text':
            ratio=w/ow if abs(w-ow)>.1 else h/oh if oh else 1
            drawing=replace(drawing,points=((x,y),),font_size=max(1,min(1000,round(drawing.font_size*ratio))))
        else:
            count=max(1,len(drawing.points)-1)
            points=tuple((x+(px-ox)*w/ow if ow else x+i/count*w,y+(py-oy)*h/oh if oh else y+i/count*h) for i,(px,py) in enumerate(drawing.points))
            drawing=replace(drawing,points=points)
        self.edit(lambda p:p.annotations.__setitem__(row,replace(item,drawing=drawing)))

    def update_annotation(self):
        row=self.selected()
        if row is not None:
            old=self.history.project.annotations[row]
            new=replace(old,start=self.start.value(),end=self.end.value(),strength=self.strength.value(),drawing=replace(self.canvas.style,kind=old.drawing.kind,points=old.drawing.points,text=old.drawing.text))
            self.edit(lambda p:p.annotations.__setitem__(row,new))
    def edit_text(self):
        from PySide6.QtWidgets import QInputDialog
        row=self.selected()
        if row is not None:
            a=self.history.project.annotations[row]
            if a.drawing.kind=='text':
                text,ok=QInputDialog.getMultiLineText(self,'Edit text','Text',a.drawing.text)
                if ok:
                    self.edit(lambda p:p.annotations.__setitem__(row,replace(a,drawing=replace(a.drawing,text=text))))
    def delete_annotation(self):
        row=self.selected()
        if row is not None:
            self.edit(lambda p:p.annotations.pop(row))
    def move_annotation(self,id,dx,dy):
        def move(p):
            item=next(a for a in p.annotations if a.id==id)
            xs,ys=zip(*item.drawing.points)
            dx2=max(-min(xs),min(dx,p.width-max(xs)))
            dy2=max(-min(ys),min(dy,p.height-max(ys)))
            item.drawing=item.drawing.moved(dx2,dy2)
        self.edit(move)
    def split(self):
        self.edit(lambda p:p.split_timeline(self.player.sequence.position))
    def remove_segment(self):
        index=self.segments.currentIndex()
        if index>=0:
            self.edit(lambda p:p.segments.pop(index))
    def position(self,seconds,source):
        if getattr(self,'animation_preview_end',None) is not None and seconds>=self.animation_preview_end:
            self.player.pause()
            self.animation_preview_end=None
        self.statusBar().showMessage(f'Edited {seconds:.3f}s / {self.history.project.output_duration:.3f}s · Source frame {round(source*self.history.project.fps)}')
        self.timeline.position=seconds
        self.timeline.update()
        if self.player.sequence.playing:
            scrollbar=self.timeline_scroll.horizontalScrollBar()
            x=self.timeline.x(seconds)
            width=self.timeline_scroll.viewport().width()
            if x>scrollbar.value()+width-30 or x<scrollbar.value():
                scrollbar.setValue(max(0,round(x-width/3)))
    def step(self,direction):
        self.player.pause()
        self.player.seek(round(direction*1000/self.history.project.fps))
    def fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()
    def keyPressEvent(self,event):
        if isinstance(QApplication.focusWidget(),(QLineEdit,QAbstractSpinBox,QTextEdit)):
            return super().keyPressEvent(event)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            shortcuts={Qt.Key.Key_Z:self.undo,Qt.Key.Key_Y:self.redo,Qt.Key.Key_S:self.save_project}
            if event.key() in shortcuts:
                shortcuts[event.key()]()
                event.accept()
                return
        keys={Qt.Key.Key_Space:self.player.toggle,Qt.Key.Key_Left:lambda:self.player.seek(-5000),Qt.Key.Key_Right:lambda:self.player.seek(5000),Qt.Key.Key_Home:lambda:self.player.seek_timeline(0),Qt.Key.Key_End:lambda:self.player.seek_timeline(self.history.project.output_duration),Qt.Key.Key_Escape:self.showNormal}
        if event.key() in keys:
            keys[event.key()]()
            event.accept()
        else:
            super().keyPressEvent(event)
    def save_project(self):
        path,_=QFileDialog.getSaveFileName(self,'Save editable video project',self.project_path or str(Path(self.history.project.source).with_suffix('.snapmark.json')),'SnapMark project (*.snapmark.json)')
        if path:
            try:
                self.history.project.save(path)
                self.project_path=path
                self.clean_project=copy.deepcopy(self.history.project)
                self.dirty=False
            except (ValueError,OSError) as exc:
                self.error(exc)
    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'Export separate MP4',str(Path(self.history.project.source).with_name(Path(self.history.project.source).stem+'_edited.mp4')),'MP4 video (*.mp4)')
        if not path:
            return
        self.cancelled.clear()
        self.progress.setValue(0)
        self.export_progress_row.show()
        self.export_button.setEnabled(False)
        self.export_action.setEnabled(False)
        project=copy.deepcopy(self.history.project)
        settings=ExportSettings(self.quality.currentText())
        def ready(path):
            self.exported=path
            self.export_button.setEnabled(True)
            self.export_action.setEnabled(True)
            self.export_progress_row.hide()
            self.statusBar().showMessage('Export complete',5000)
            QMessageBox.information(self,'SnapMark','Export complete')
        def failed(message):
            self.export_progress_row.hide()
            self.export_button.setEnabled(True)
            self.export_action.setEnabled(True)
            self.error(message)
        self.jobs.run(lambda:export(project,path,settings,self.cancelled,self.export_progress.emit),ready,failed)
    def open_export(self):
        if self.exported:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.exported))
    def open_animations(self,target=None,phase=None):
        from cpp.video.animation_dialog import AnimationDialog
        self.player.pause()
        if target is None:
            row=self.selected()
            target=('annotation',self.history.project.annotations[row].id) if row is not None else ('video',None)
        dialog=AnimationDialog(self.history.project,target,self,phase)
        original_position=self.player.sequence.position
        self.animation_preview_end=None
        def stop():
            self.player.pause()
            self.canvas.animation_preview=None
            self.animation_preview_end=None
            self.canvas.update()
        def preview(project,context,key,phase):
            from cpp.video.animations import window
            self.player.pause()
            self.canvas.animation_preview=project
            if context=='annotation':
                item=next(a for a in project.annotations if a.id==key)
                a,b,cycle=window(getattr(item.animations,phase),phase,item.end-item.start,item.drawing.text)
                source_a=item.start+max(0,a-.25);source_b=item.start+b
                pieces=[]
                for span in project.spans:
                    lo,hi=max(source_a,item.start,span.source_start),min(source_b,item.end,span.source_end)
                    if lo<hi:pieces.append((span.start+lo-span.source_start,span.start+hi-span.source_start))
                if not pieces:
                    self.canvas.animation_preview=None
                    QMessageBox.information(dialog,'Animation preview','This animation window is outside the kept footage. Adjust its timing to preview it.')
                    return
                start,end=pieces[0]
                if phase=='emphasis':end=min(end,start+max(2,min(6,cycle*2)))
            elif context=='join':
                t=project.spans[key].start;half=max(.5,project.join_half(key));start,end=max(0,t-half),min(project.output_duration,t+half)
            else:
                spec=getattr(project.video_animations,phase)
                a,b,_=window(spec,phase,project.output_duration)
                start,end=max(0,a-.25),min(project.output_duration,b+.25)
                if spec.kind=='None':start,end=(max(0,project.output_duration-3),project.output_duration) if phase=='exit' else (0,min(3,project.output_duration))
            self.animation_preview_end=end
            self.player.seek_timeline(start)
            self.player.sequence.play()
        dialog.preview_requested.connect(preview)
        dialog.preview_stopped.connect(stop)
        if dialog.exec():
            def commit(project):
                project.video_animations=copy.deepcopy(dialog.draft.video_animations)
                project.transitions=copy.deepcopy(dialog.draft.transitions)
                for item,draft in zip(project.annotations,dialog.draft.annotations):item.animations=copy.deepcopy(draft.animations)
            self.edit(commit)
        stop()
        self.player.seek_timeline(min(original_position,self.history.project.output_duration))
        dialog.deleteLater()

    def file_properties(self):
        if self.jobs.active:
            self.statusBar().showMessage('Wait for export to finish before changing source files.',5000)
            return
        from cpp.ui.media_file import MediaFileDialog
        p=self.history.project
        details={'Video dimensions':f'{p.width} × {p.height} px','Source duration':f'{p.duration:.3f}s','Edited duration':f'{p.output_duration:.3f}s','Frame rate':f'{p.fps:.3f} FPS','Audio':'Yes' if p.audio else 'No'}
        dialog=MediaFileDialog(p.source,details,self)
        dialog.deleted.connect(self.storage_deleted)
        dialog.exec()
    def storage_deleted(self,path):
        self.player.sequence.pause()
        self.player.media.setSource(QUrl())
        self.dirty=False
        QTimer.singleShot(0,self.close)
    def delete_from_storage(self):
        if self.jobs.active:
            return
        from cpp.ui.media_file import delete_file
        if delete_file(self,self.history.project.source,'The editor will close. Editable projects referencing this video will lose their source.'):
            self.storage_deleted(self.history.project.source)

    def closeEvent(self,event):
        if self.jobs.active:
            self.cancelled.set()
            self.statusBar().showMessage('Cancelling export; close again after it finishes.')
            event.ignore()
            return
        if self.dirty:
            answer=QMessageBox.question(self,'Unsaved video project','Save your editable project before closing?',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
            if answer==QMessageBox.StandardButton.Save:
                self.save_project()
                if self.dirty:
                    event.ignore()
                    return
            elif answer!=QMessageBox.StandardButton.Discard:
                event.ignore()
                return
        self.player.sequence.pause()
        self.player.media.stop()
        event.accept()
