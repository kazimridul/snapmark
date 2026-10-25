"""Qt Multimedia playback controls shared by recording preview and editor."""
from PySide6.QtCore import Qt, QUrl, QSize
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from cpp.ui.icons import tool_icon
from cpp.video.sequence import SequencePlayback
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QToolButton, QSlider, QWidget

def timestamp(ms):
    seconds = max(0,int(ms)//1000)
    return f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}.{int(ms)%1000:03}'

class Player:
    def __init__(self, owner, canvas):
        self.media = QMediaPlayer(owner)
        self.audio = QAudioOutput(owner)
        self.audio.setVolume(.8)
        self.media.setAudioOutput(self.audio)
        self.sink = QVideoSink(owner)
        self.media.setVideoSink(self.sink)
        self.canvas = canvas
        self.sequence=SequencePlayback(self.media,canvas.project,owner)
        self.sequence.changed.connect(self.position)
        self.sink.videoFrameChanged.connect(self.frame)
        self.controls = QWidget()
        row = QHBoxLayout(self.controls)
        self.play_button=None
        for name,label,fn in [('back','Seek backward 5 seconds',lambda:self.seek(-5000)),('play','Play / pause · Space',self.toggle),('stop','Stop',self.sequence.stop),('forward','Seek forward 5 seconds',lambda:self.seek(5000))]:
            button=QToolButton()
            button.setIcon(tool_icon(name))
            button.setIconSize(QSize(20,20))
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.clicked.connect(fn)
            row.addWidget(button)
            if name=='play':
                self.play_button=button
        row.addStretch()
        self.time = QLabel('00:00:00 / 00:00:00')
        row.addWidget(self.time)
        speed = QComboBox()
        speed.addItems(['0.5×','1×','1.5×','2×'])
        speed.setCurrentIndex(1)
        speed.currentIndexChanged.connect(lambda i:self.media.setPlaybackRate((.5,1,1.5,2)[i]))
        row.addWidget(speed)
        volume = QSlider(Qt.Orientation.Horizontal)
        volume.setRange(0,100)
        volume.setValue(80)
        volume.setMaximumWidth(100)
        volume.setToolTip('Playback volume')
        volume.valueChanged.connect(lambda v:self.audio.setVolume(v/100))
        row.addWidget(volume)
        mute = QToolButton()
        mute.setIcon(tool_icon('volume'))
        mute.setToolTip('Mute playback')
        mute.setAccessibleName('Mute playback')
        mute.setCheckable(True)
        mute.toggled.connect(self.audio.setMuted)
        mute.toggled.connect(lambda checked:mute.setIcon(tool_icon('muted' if checked else 'volume')))
        row.addWidget(mute)
        self.media.mediaStatusChanged.connect(self.loaded)
        self.media.playbackStateChanged.connect(lambda state:self.play_button.setIcon(tool_icon('pause' if state==QMediaPlayer.PlaybackState.PlayingState else 'play')))
    def open(self,path):
        self.media.setSource(QUrl.fromLocalFile(str(path)))
    def frame(self,frame):
        source=frame.startTime()/1_000_000 if frame.startTime()>=0 else self.media.position()/1000
        if not self.sequence.accept_frame(source):
            return
        image = frame.toImage()
        if not image.isNull():
            self.canvas.position=source
            self.canvas.frame = image
            self.canvas.update()
    def loaded(self,status):
        if status==QMediaPlayer.MediaStatus.LoadedMedia:
            self.sequence.seek(self.sequence.position)

    def position(self,seconds,source):
        span=self.sequence.project.spans[self.sequence.index]
        if not span.source_start<=self.canvas.position<span.source_end:
            # A deleted/previous clip must not remain visible during an async seek.
            self.canvas.frame=QImage()
            self.canvas.update()
        self.time.setText(timestamp(round(seconds*1000))+' / '+timestamp(round(self.sequence.project.output_duration*1000)))

    def toggle(self):
        self.sequence.toggle()

    def pause(self):
        self.sequence.pause()

    def seek(self,delta):
        self.sequence.seek_by(delta/1000)

    def seek_timeline(self,seconds):
        self.sequence.seek(seconds)
