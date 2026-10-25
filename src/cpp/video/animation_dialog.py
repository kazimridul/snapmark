"""Contextual animation settings. A draft can be previewed before committing."""
import copy
from dataclasses import replace
from PySide6.QtCore import Qt,Signal,QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox,QColorDialog,QComboBox,QDialog,QDialogButtonBox,QDoubleSpinBox,QFormLayout,QHBoxLayout,QLabel,QMessageBox,QPushButton,QScrollArea,QSpinBox,QSplitter,QTabWidget,QToolButton,QVBoxLayout,QWidget)
from cpp.video.animations import Animation,Animations,CATALOG,EASINGS,available,defaults,window

class AnimationProperties(QWidget):
    changed=Signal()
    def __init__(self,phase):
        super().__init__()
        self.phase=phase;self.loading=True;self.length=1;self.text='';self.context='annotation';self.drawing_kind='pen';self.frame_size=(320,240)
        layout=QVBoxLayout(self)
        self.form=QFormLayout();self.form.setSpacing(10);layout.addLayout(self.form)
        self.kind=QComboBox();self.form.addRow('Animation',self.kind)
        self.common=QWidget();self.common_form=QFormLayout(self.common);self.common_form.setContentsMargins(0,6,0,6)
        self.duration=self.number(.01,36000,.6,' s');self.delay=self.number(0,36000,0,' s')
        self.easing=QComboBox();self.easing.addItems(EASINGS)
        self.repeat=QCheckBox('Repeat animation');self.count=QSpinBox();self.count.setRange(0 if phase=='emphasis' else 1,100);self.count.setSpecialValueText('Until end' if phase=='emphasis' else '')
        self.reverse=QCheckBox('Reverse');self.alternate=QCheckBox('Alternate repeated cycles')
        self.automatic=QCheckBox('Automatic timing');self.automatic.setChecked(True)
        self.start=self.number(0,36000,0,' s');self.end=self.number(0,36000,1,' s')
        for label,widget in [('Duration',self.duration),('Delay',self.delay),('Easing',self.easing)]:self.common_form.addRow(label,widget)
        self.advanced=QWidget();self.advanced_form=QFormLayout(self.advanced);self.advanced_form.setContentsMargins(0,4,0,4)
        for label,widget in [('',self.repeat),('Repeat count',self.count),('',self.reverse),('',self.alternate),('',self.automatic),('Start (local time)',self.start),('End (local time)',self.end)]:self.advanced_form.addRow(label,widget)
        self.advanced_toggle=QToolButton();self.advanced_toggle.setText('Timing, repeat and range');self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon);self.advanced_toggle.setCheckable(True);self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_toggle.toggled.connect(self.update)
        self.parameters=QWidget();self.parameter_form=QFormLayout(self.parameters);self.parameter_form.setContentsMargins(0,6,0,6);self.form.addRow(self.parameters)
        self.form.addRow(self.common);self.form.addRow(self.advanced_toggle);self.form.addRow(self.advanced)
        self.controls={}
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.reset=QPushButton('Reset effect to defaults');self.reset.clicked.connect(self.reset_effect);layout.addWidget(self.reset);layout.addStretch()
        self.kind.currentTextChanged.connect(self.choose)
        for w in (self.duration,self.delay,self.start,self.end):w.valueChanged.connect(self.update)
        self.count.valueChanged.connect(self.update)
        self.easing.currentTextChanged.connect(self.update)
        for w in (self.repeat,self.reverse,self.alternate,self.automatic):w.toggled.connect(self.update)
        self.loading=False
    @staticmethod
    def number(lo,hi,value,suffix=''):
        w=QDoubleSpinBox();w.setDecimals(3);w.setRange(lo,hi);w.setValue(value);w.setSuffix(suffix);w.setKeyboardTracking(False);w.setSingleStep(.05 if hi<=1 else .1 if suffix==' s' or hi<=5 or suffix==' Hz' else 1);return w
    def set_context(self,spec,context,drawing_kind,length,text=''):
        self.loading=True;self.context=context;self.drawing_kind=drawing_kind;self.length=length;self.text=text
        self.kind.clear();self.kind.addItems(available(self.phase,context,drawing_kind))
        self.loading=False
        self.set_spec(spec)
    def set_spec(self,spec):
        self.loading=True
        self.kind.setCurrentText(spec.kind)
        self.duration.setValue(spec.duration);self.delay.setValue(spec.delay);self.easing.setCurrentText(spec.easing)
        self.repeat.setChecked(spec.repeat);self.count.setValue(spec.repeat_count);self.reverse.setChecked(spec.reverse);self.alternate.setChecked(spec.alternate)
        self.automatic.setChecked(spec.start is None and spec.end is None)
        self.advanced_toggle.setChecked(spec.start is not None or spec.end is not None or spec.reverse or spec.alternate or (spec.repeat and (self.phase!='emphasis' or spec.repeat_count>0)))
        self.start.setMaximum(self.length);self.end.setMaximum(self.length)
        a,b,_=window(spec,self.phase,self.length,self.text)
        self.start.setValue(spec.start if spec.start is not None else max(0,a-spec.delay));self.end.setValue(spec.end if spec.end is not None else b)
        while self.parameter_form.rowCount():self.parameter_form.removeRow(0)
        self.controls={}
        for key,prop in CATALOG[self.phase][spec.kind].items():
            value=spec.params.get(key,prop.default)
            if prop.choices:
                widget=QComboBox();widget.addItems(prop.choices);widget.setCurrentText(value);widget.currentTextChanged.connect(self.update)
            elif type(prop.default) is bool:
                widget=QCheckBox();widget.setChecked(value);widget.toggled.connect(self.update)
            elif isinstance(prop.default,str):
                widget=QPushButton(value);widget.setProperty('color',value);widget.clicked.connect(lambda checked=False,w=widget:self.pick_color(w))
            elif key in ('particle_size','bounce_count'):
                widget=QSpinBox();widget.setRange(int(prop.minimum),int(prop.maximum));widget.setValue(round(value));widget.setSuffix(prop.suffix);widget.valueChanged.connect(self.update)
            else:
                widget=self.number(prop.minimum,prop.maximum,value,prop.suffix);widget.valueChanged.connect(self.update)
            self.parameter_form.addRow(prop.label,widget);self.controls[key]=widget
        self.loading=False;self.update()
    def choose(self,name):
        if not self.loading and name:
            spec=defaults(self.phase,name)
            if self.context=='video' and name.startswith('Slide '):
                axis='x' if name.endswith(('Left','Right')) else 'y'
                spec.params[axis+'_offset']=(-1 if name.endswith(('Left','Top')) else 1)*self.frame_size[0 if axis=='x' else 1]
            self.set_spec(spec)
    def pick_color(self,button):
        color=QColorDialog.getColor(QColor(button.property('color')),self,'Animation color')
        if color.isValid():button.setProperty('color',color.name());button.setText(color.name());self.update()
    def spec(self):
        if self.kind.currentText()=='None':return Animation()
        params={}
        for key,w in self.controls.items():
            params[key]=w.currentText() if isinstance(w,QComboBox) else w.isChecked() if isinstance(w,QCheckBox) else w.property('color') if isinstance(w,QPushButton) else w.value()
        return Animation(self.kind.currentText() or 'None',self.duration.value(),self.delay.value(),self.easing.currentText(),self.repeat.isChecked(),self.count.value(),self.reverse.isChecked(),self.alternate.isChecked(),None if self.automatic.isChecked() else self.start.value(),None if self.automatic.isChecked() else self.end.value(),params)
    def update(self,*_):
        if self.loading:return
        spec=self.spec();enabled=spec.kind!='None'
        self.common.setVisible(enabled);self.parameters.setVisible(enabled);self.reset.setEnabled(enabled)
        self.common_form.setRowVisible(self.delay,self.phase!='join')
        self.advanced_toggle.setVisible(enabled and self.phase!='join')
        self.advanced.setVisible(enabled and self.phase!='join' and self.advanced_toggle.isChecked())
        self.advanced_toggle.setArrowType(Qt.ArrowType.DownArrow if self.advanced_toggle.isChecked() else Qt.ArrowType.RightArrow)
        self.advanced_form.setRowVisible(self.count,spec.repeat)
        self.advanced_form.setRowVisible(self.alternate,spec.repeat)
        self.common_form.setRowVisible(self.duration,self.phase!='emphasis')
        self.duration.setEnabled(spec.kind!='Typewriter' or spec.params.get('timing_mode')=='Duration')
        if spec.kind=='Typewriter':self.controls['typing_speed'].setEnabled(spec.params.get('timing_mode')=='Typing speed')
        self.count.setEnabled(spec.repeat);self.alternate.setEnabled(spec.repeat)
        self.start.setEnabled(not self.automatic.isChecked());self.end.setEnabled(not self.automatic.isChecked())
        if self.phase=='join':self.summary.setText('Transitions pass through the selected color, preserve clip length and fit within the neighboring clips.')
        else:
            a,b,cycle=window(spec,self.phase,self.length,self.text)
            self.summary.setText(('No visible interval at this timing. Reduce delay or adjust the range.' if b<=a else f'Animation window: {a:.3f}–{b:.3f}s · cycle {cycle:.3f}s. Times are relative to the selected item. Timing is fitted to its visible duration.') if enabled else 'No animation; the item keeps its normal appearance.')
        self.changed.emit()
    def reset_effect(self):self.choose(self.kind.currentText())

class AnimationDialog(QDialog):
    preview_requested=Signal(object,str,object,str)
    preview_stopped=Signal()
    def __init__(self,project,target=None,parent=None,phase=None):
        super().__init__(parent)
        initial_phase=phase
        self.setWindowTitle('Animations and clip transitions');self.resize(660,880)
        screen=self.screen()
        if screen:self.resize(min(660,screen.availableGeometry().width()-40),min(880,screen.availableGeometry().height()-60))
        self.draft=copy.deepcopy(project);self.loading=False
        layout=QVBoxLayout(self)
        heading=QLabel('Animate the selected item');heading.setObjectName('section');layout.addWidget(heading)
        self.target=QComboBox();self.targets=[('video',None,'Whole video · opening / ending')]
        self.targets += [('annotation',a.id,f'Layer {i+1} · {a.drawing.kind.replace("_"," ").title()}') for i,a in enumerate(project.annotations)]
        self.targets += [('join',i,f'Join {i} · Clip {i} → Clip {i+1}') for i in range(1,len(project.segments))]
        for kind,key,label in self.targets:self.target.addItem(label)
        layout.addWidget(self.target)
        self.hint=QLabel();self.hint.setWordWrap(True);layout.addWidget(self.hint)
        self.tabs=QTabWidget();self.panels={}
        for phase,label in [('entrance','Entrance'),('emphasis','Emphasis'),('exit','Exit'),('join','Join transition')]:
            panel=AnimationProperties(phase);panel.changed.connect(self.store)
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(panel)
            self.tabs.addTab(scroll,label);self.panels[phase]=panel
        from cpp.video.canvas import VideoCanvas
        self.preview_canvas=VideoCanvas()
        self.preview_canvas.setMinimumSize(320,140)
        self.preview_canvas.setEnabled(False)
        self.preview_canvas.project=self.draft
        self.preview_canvas.preview_crop=bool(self.draft.crop)
        split=QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.preview_canvas);split.addWidget(self.tabs);split.setSizes([210,480])
        layout.addWidget(split,1)
        self.preview_timer=QTimer(self);self.preview_timer.setInterval(66)
        self.preview_timer.timeout.connect(self.sync_preview);self.preview_timer.start()
        self.sync_preview()
        controls=QHBoxLayout();preview=QPushButton('▶ Preview');preview.clicked.connect(self.preview);controls.addWidget(preview)
        stop=QPushButton('Stop preview');stop.clicked.connect(self.preview_stopped.emit);controls.addWidget(stop);controls.addStretch();layout.addLayout(controls)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).setText('Apply animations');buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.target.currentIndexChanged.connect(self.reload)
        if target:
            self.target.setCurrentIndex(next((i for i,(kind,key,_) in enumerate(self.targets) if (kind,key)==target),0))
        self.reload()
        if initial_phase in self.panels:self.tabs.setCurrentIndex(list(self.panels).index(initial_phase))
    def sync_preview(self):
        parent=self.parentWidget()
        if parent and hasattr(parent,'canvas'):
            self.preview_canvas.frame=parent.canvas.frame
            self.preview_canvas.position=parent.canvas.position
            self.preview_canvas.timeline_position=parent.canvas.timeline_position
            self.preview_canvas.update()

    def current(self):return self.targets[self.target.currentIndex()][:2]
    def reload(self,*_):
        self.loading=True;context,key=self.current()
        item=next((a for a in self.draft.annotations if a.id==key),None) if context=='annotation' else None
        bundle=item.animations if item else self.draft.video_animations
        length=item.end-item.start if item else self.draft.output_duration
        for i,phase in enumerate(self.panels):
            visible=phase=='join' if context=='join' else phase!='join' and (context=='annotation' or phase!='emphasis')
            self.tabs.setTabVisible(i,visible)
            if visible:
                spec=self.draft.transition(key) if phase=='join' else getattr(bundle,phase)
                self.panels[phase].frame_size=tuple(self.draft.crop[2:]) if self.draft.crop else (self.draft.width,self.draft.height)
                self.panels[phase].set_context(spec,context,item.drawing.kind if item else 'pen',length,item.drawing.text if item else '')
        if context=='join':
            half=self.draft.join_half(key)
            self.hint.setText(f'Applies at {self.draft.spans[key].start:.3f}s in the edited sequence. No overlap or change to video length. Effective duration: {half*2:.3f}s.')
        elif item and item.drawing.kind in ('blur','pixelate'):
            self.hint.setText('Privacy masks stay fixed for their full assigned range. Animation is available for visual annotation layers.')
        else:self.hint.setText('Entrance, emphasis and exit use the same rendering in preview and exported video. Select a preset to show its relevant properties.')
        if not self.tabs.isTabVisible(self.tabs.currentIndex()):self.tabs.setCurrentIndex(next(i for i in range(self.tabs.count()) if self.tabs.isTabVisible(i)))
        self.loading=False
    def store(self):
        if self.loading:return
        context,key=self.current()
        if context=='join':
            name=self.draft.join_key(self.draft.segments[key-1],self.draft.segments[key])
            spec=self.panels['join'].spec()
            if spec.kind=='None':self.draft.transitions.pop(name,None)
            else:self.draft.transitions[name]=spec
            self.hint.setText(f'Join at {self.draft.spans[key].start:.3f}s · effective duration {self.draft.join_half(key)*2:.3f}s. Clip length is preserved.')
        else:
            bundle=self.draft.video_animations if context=='video' else next(a for a in self.draft.annotations if a.id==key).animations
            for phase in ('entrance','emphasis','exit'):
                if context=='annotation' or phase!='emphasis':setattr(bundle,phase,self.panels[phase].spec())
    def preview(self):
        self.store()
        try:self.draft.validate()
        except ValueError as exc:QMessageBox.warning(self,'Animation settings',str(exc));return
        context,key=self.current();self.preview_requested.emit(self.draft,context,key,list(self.panels)[self.tabs.currentIndex()])
    def apply(self):
        self.store()
        try:self.draft.validate()
        except ValueError as exc:QMessageBox.warning(self,'Animation settings',str(exc));return
        self.accept()
    def done(self,result):
        self.preview_timer.stop();self.preview_stopped.emit();super().done(result)
