"""Dedicated crop workspace with handles, aspect presets and native-pixel inputs."""
from PySide6.QtCore import QRectF, QTimer
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout
from cpp.editor.canvas import Canvas
from cpp.editor.document import Document

class VideoCropDialog(QDialog):
    def __init__(self,frame,crop=None,parent=None):
        super().__init__(parent)
        self.setWindowTitle('Crop video')
        self.resize(980,720)
        self.frame=frame
        self.crop=None
        layout=QVBoxLayout(self)
        title=QLabel('Crop the video frame')
        title.setObjectName('section')
        layout.addWidget(title)
        hint=QLabel('Drag a rectangle, move it or resize its handles. The same crop applies to every kept clip. Original video pixels are used.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.canvas=Canvas(Document(frame))
        self.canvas.set_tool('crop')
        self.canvas.region=QRectF(*crop) if crop else QRectF()
        layout.addWidget(self.canvas,1)
        row=QHBoxLayout()
        row.addWidget(QLabel('Aspect ratio'))
        self.aspect=QComboBox()
        for label,value in [('Free',0),('16:9',16/9),('4:3',4/3),('Square',1)]:
            self.aspect.addItem(label,value)
        self.aspect.currentIndexChanged.connect(self.aspect_changed)
        row.addWidget(self.aspect)
        self.controls=[]
        for label,limit in [('X',frame.width()-2),('Y',frame.height()-2),('Width',frame.width()),('Height',frame.height())]:
            row.addWidget(QLabel(label))
            control=QSpinBox()
            control.setRange(0 if label in ('X','Y') else 2,limit)
            control.setKeyboardTracking(False)
            control.editingFinished.connect(self.numeric_region)
            self.controls.append(control)
            row.addWidget(control)
        reset=QPushButton('Full frame')
        reset.clicked.connect(self.reset)
        row.addWidget(reset)
        layout.addLayout(row)
        self.dimensions=QLabel()
        layout.addWidget(self.dimensions)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel)
        self.apply_button=buttons.button(QDialogButtonBox.StandardButton.Apply)
        self.apply_button.setText('Apply crop')
        self.apply_button.setObjectName('primaryAction')
        self.apply_button.clicked.connect(self.apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.canvas.selection_changed.connect(self.update_region)
        self.canvas.confirm_requested.connect(self.apply)
        self.canvas.tool_cancelled.connect(self.reject)
        self.update_region()
        QTimer.singleShot(0,self.canvas.fit)
    def aspect_changed(self):
        ratio=self.aspect.currentData()
        self.canvas.ratio=ratio
        r=self.canvas.region
        if ratio and not r.isEmpty():
            w=min(r.width(),r.height()*ratio)
            h=w/ratio
            self.canvas.region=QRectF(r.center().x()-w/2,r.center().y()-h/2,w,h)
            self.update_region()

    def update_region(self):
        r=self.canvas.region.toAlignedRect().intersected(self.frame.rect())
        for control,value in zip(self.controls,[r.x(),r.y(),r.width(),r.height()]):
            control.setValue(value)
        valid=r.width()>=2 and r.height()>=2
        self.apply_button.setEnabled(valid)
        self.dimensions.setText(f'Output crop: {r.width()} × {r.height()} px · Source: {self.frame.width()} × {self.frame.height()} px' if valid else 'Select an area of at least 2 × 2 pixels.')
        self.canvas.viewport().update()
    def numeric_region(self):
        x,y,w,h=[c.value() for c in self.controls]
        w,h=min(w,self.frame.width()-x),min(h,self.frame.height()-y)
        self.canvas.region=QRectF(x,y,w,h)
        self.update_region()
    def reset(self):
        self.aspect.setCurrentIndex(0)
        self.canvas.region=QRectF(self.frame.rect())
        self.update_region()
    def apply(self):
        r=self.canvas.region.toAlignedRect().intersected(self.frame.rect())
        if r.width()>=2 and r.height()>=2:
            self.crop=r.getRect()
            self.accept()
