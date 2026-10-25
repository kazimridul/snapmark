"""Recording mode and file management integrated into the existing launcher."""
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QCheckBox, QDoubleSpinBox, QFileDialog, QDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QProgressDialog, QSpinBox, QVBoxLayout, QWidget)
from cpp.capture.backend import session_type, x11_capture
from cpp.jobs import Jobs
from cpp.ui.region_dialog import RegionDialog
from cpp.video.audio import sources
from cpp.video.ffmpeg import probe
from cpp.video.model import Project
from cpp.video.recording import Recorder, RecordingSettings

class SavingRecordingDialog(QProgressDialog):
    def __init__(self,parent):
        super().__init__('Recording finished. Saving video…','',0,0,parent)
        self.active=True
        self.setWindowTitle('Saving recording')
        self.setCancelButton(None)
        self.setMinimumDuration(0)
        self.setAutoClose(False)
        self.setAutoReset(False)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumSize(430,130)
        self.resize(430,130)
    def reject(self):
        if not self.active:
            super().reject()
    def closeEvent(self,event):
        event.ignore() if self.active else event.accept()
    def finish(self):
        self.active=False
        self.close()
        self.deleteLater()

class RecordingToolbar(QDialog):
    """Small persistent indicator while the main launcher is minimized."""
    def __init__(self,panel):
        super().__init__(panel)
        self.panel=panel
        self.setWindowTitle('SnapMark · Recording')
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        row=QHBoxLayout(self)
        self.label=QLabel('● Recording')
        row.addWidget(self.label)
        self.pause=QPushButton('Pause')
        self.pause.clicked.connect(lambda:panel.command('pause'))
        row.addWidget(self.pause)
        self.resume=QPushButton('Resume')
        self.resume.clicked.connect(lambda:panel.command('resume'))
        row.addWidget(self.resume)
        self.stop=QPushButton('Stop')
        self.stop.clicked.connect(panel.stop)
        row.addWidget(self.stop)
    def closeEvent(self,event):
        if self.panel.recorder and self.panel.recorder.isRunning():
            self.panel.stop()
            event.ignore()
        else:
            event.accept()

class RecordingPanel(QWidget):
    editors_changed=Signal()
    def __init__(self,parent=None):
        super().__init__(parent)
        self.jobs=Jobs(self)
        self.recorder=None
        self.windows=[]
        self.last_path=None
        self.remaining=0
        self.restore_launcher=False
        self.saving_dialog=None
        self.preferences=QSettings()
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('Screen Recording'))
        explanation=QLabel('All video and audio stay on your computer. Audio is off until you select it.\n'+('Press Print Screen to use Ubuntu’s built-in recorder with system defaults. Or configure recording here; for an area, share a monitor, then drag your recording area before capture starts.' if session_type()=='wayland' else 'X11: record the desktop or select a region in native screen pixels.'))
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.native_import = QCheckBox('Open completed Ubuntu recordings in the video editor')
        self.native_import.setChecked(True)
        self.native_import.setToolTip('While SnapMark is running, watches Videos/Screencasts and Videos for completed new recordings. Print Screen uses Ubuntu’s recording settings.')
        layout.addWidget(self.native_import)
        from cpp.video.system_recordings import SystemRecordings
        self.native_recordings = SystemRecordings(self)
        self.native_recordings.ready.connect(lambda path: self.load(path) if self.native_import.isChecked() else None)
        self.native_recordings.unavailable.connect(self.error)
        self.options=QWidget()
        form=QFormLayout(self.options)
        self.mode=QComboBox()
        self.mode.addItem('Full screen / choose monitor','full')
        self.mode.addItem('Select area', 'region')
        if session_type()=='wayland':
            self.mode.addItem('Select window','window')
        self.mode.setCurrentIndex(1)
        form.addRow('Capture',self.mode)
        self.fps=QComboBox()
        for fps in (15,24,30,60):
            self.fps.addItem(str(fps),fps)
        self.fps.setCurrentIndex(2)
        form.addRow('Frames per second',self.fps)
        self.resolution=QComboBox()
        for name,height in [('Original',0),('Up to 1080p',1080),('Up to 720p',720)]:
            self.resolution.addItem(name,height)
        # Original dimensions are reliable across portal scaling. Lower resolutions
        # are applied after capture to avoid negotiating an upscale on small streams.
        form.addRow('Resolution',self.resolution)
        self.quality=QComboBox()
        self.quality.addItems(['Low','Medium','High'])
        self.quality.setCurrentIndex(1)
        form.addRow('Quality',self.quality)
        self.audio_mode=QComboBox()
        self.audio_mode.addItems(['No audio','Microphone','System audio','Both'])
        form.addRow('Audio',self.audio_mode)
        self.mic=QComboBox()
        self.system=QComboBox()
        form.addRow('Microphone',self.mic)
        form.addRow('System monitor',self.system)
        self.volume=QDoubleSpinBox()
        self.volume.setRange(0,2)
        self.volume.setSingleStep(.1)
        self.volume.setValue(1)
        form.addRow('Capture input gain',self.volume)
        self.countdown=QSpinBox()
        self.countdown.setRange(0,30)
        form.addRow('Countdown seconds',self.countdown)
        directory=QHBoxLayout()
        self.directory=QLineEdit(self.preferences.value('video/directory',str(Path.home()/'Videos'/'SnapMark')))
        directory.addWidget(self.directory)
        choose=QPushButton('Browse…')
        choose.clicked.connect(self.choose_directory)
        directory.addWidget(choose)
        form.addRow('Save folder',directory)
        self.filename=QLineEdit()
        self.new_name()
        form.addRow('Filename',self.filename)
        layout.addWidget(self.options)
        controls=QHBoxLayout()
        self.start_button=QPushButton('Start Recording')
        self.pause_button=QPushButton('Pause')
        self.resume_button=QPushButton('Resume')
        self.stop_button=QPushButton('Stop / Cancel countdown')
        for button,fn in [(self.start_button,self.start),(self.pause_button,lambda:self.command('pause')),(self.resume_button,lambda:self.command('resume')),(self.stop_button,self.stop)]:
            button.clicked.connect(fn)
            controls.addWidget(button)
        layout.addLayout(controls)
        self.status=QLabel('Ready · MP4 / H.264 / AAC')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.elapsed=QLabel('00:00:00')
        self.elapsed.setStyleSheet('font-size: 24px;')
        layout.addWidget(self.elapsed)
        files=QHBoxLayout()
        for text,fn in [('Open video…',self.open_video),('File properties',self.file_properties),('Open project…',self.open_project),('Play / Video Editor',self.open_last),('Open folder',self.open_folder),('Delete recording…',self.delete)]:
            button=QPushButton(text)
            button.clicked.connect(fn)
            files.addWidget(button)
        layout.addLayout(files)
        layout.addStretch()
        self.timer=QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.delay_timer=QTimer(self)
        self.delay_timer.setInterval(1000)
        self.delay_timer.timeout.connect(self.countdown_tick)
        self.toolbar=RecordingToolbar(self)
        self.recording_state='Ready'
        self.state('Ready')
        self.jobs.run(sources,self.devices,lambda message:self.status.setText('Audio discovery failed: '+message))
    @property
    def busy(self):
        return self.delay_timer.isActive() or bool(self.recorder and self.recorder.isRunning()) or bool(self.jobs.active)
    def devices(self,devices):
        for source in devices:
            (self.system if source.monitor else self.mic).addItem(source.label,source.name)
    def new_name(self):
        self.filename.setText(datetime.now().strftime('snapmark_recording_%Y-%m-%d_%H%M%S.mp4'))
    def error(self,message):
        QMessageBox.warning(self,'SnapMark recording',str(message))
    def choose_directory(self):
        directory=QFileDialog.getExistingDirectory(self,'Recording output folder',self.directory.text())
        if directory:
            self.directory.setText(directory)
    def start(self):
        if self.busy:
            return
        self.remaining=self.countdown.value()
        self.options.setEnabled(False)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        if self.remaining:
            self.status.setText(f'Recording in {self.remaining}s')
            self.delay_timer.start()
        else:
            self.begin()
    def countdown_tick(self):
        self.remaining-=1
        if self.remaining<=0:
            self.delay_timer.stop()
            self.begin()
        else:
            self.status.setText(f'Recording in {self.remaining}s')
    def begin(self):
        try:
            name=self.filename.text().strip()
            if not name or Path(name).name!=name:
                raise ValueError('Enter a filename without a directory.')
            audio=[]
            mode=self.audio_mode.currentIndex()
            if mode in (1,3):
                if not self.mic.currentData():
                    raise ValueError('No microphone available. Check your audio devices or choose No audio.')
                audio.append(self.mic.currentData())
            if mode in (2,3):
                if not self.system.currentData():
                    raise ValueError('No system audio monitor available. Check PipeWire/PulseAudio or choose No audio.')
                audio.append(self.system.currentData())
            region=None
            self.hide_launcher()
            if self.mode.currentData()=='region' and session_type()=='x11':
                # Capture off the UI thread, then reuse the existing pixel-space selector.
                QTimer.singleShot(250,lambda:self.jobs.run(lambda:x11_capture('full'),lambda image:self.select_region(image,audio,name),self.failed))
                return
            self.launch(name,audio,region)
        except Exception as exc:
            self.failed(str(exc))
    def select_region(self,image,audio,name):
        dialog=RegionDialog(image,self)
        dialog.showFullScreen()
        if dialog.exec():
            r=dialog.rectangle
            self.launch(name,audio,(r.x(),r.y(),r.width(),r.height()))
        else:
            self.state('Ready')
    def hide_launcher(self):
        if self.window().isVisible():
            self.restore_launcher=True
            self.window().hide()
    def restore_main_window(self):
        if self.restore_launcher:
            self.window().showNormal()
            self.restore_launcher=False
    def select_wayland_region(self,image):
        if not self.recorder or self.recorder.cancelled.is_set():
            return
        dialog=RegionDialog(image,self)
        dialog.setWindowTitle('Select recording area — SnapMark')
        dialog.hint.setText('Drag the area to record · Escape to cancel')
        dialog.hint.adjustSize()
        dialog.showFullScreen()
        if dialog.exec():
            r=dialog.rectangle
            self.recorder.select_region((r.x(),r.y(),r.width(),r.height()))
        else:
            self.recorder.command('stop')
    def launch(self,name,audio,region):
        output=str((Path(self.directory.text()).expanduser()/name).resolve())
        settings=RecordingSettings(output,self.mode.currentData(),self.fps.currentData(),self.resolution.currentData(),self.quality.currentText(),audio,self.volume.value(),region)
        self.recorder=Recorder(settings,self)
        self.recorder.status.connect(self.state)
        self.recorder.progress.connect(self.saving_progress)
        self.recorder.region_requested.connect(self.select_wayland_region)
        self.recorder.saved.connect(self.saved)
        self.recorder.failed.connect(self.failed)
        self.recorder.finished.connect(self.worker_finished)
        self.recorder.start()
        self.preferences.setValue('video/directory',self.directory.text())
    def worker_finished(self):
        self.finish_saving()
        if self.recorder:
            self.recorder.deleteLater()
            self.recorder=None
        self.state('Ready · recording process finished')
    def command(self,command):
        if self.recorder:
            self.recorder.command(command)
    def stop(self):
        if self.delay_timer.isActive():
            self.delay_timer.stop()
            self.state('Ready')
        else:
            self.command('stop')
    def state(self,state):
        self.recording_state=state
        if state in ('Finalizing recording','Encoding MP4','finished'):
            self.restore_main_window()
            self.toolbar.hide()
            if self.saving_dialog is None:
                self.saving_dialog=SavingRecordingDialog(self.window())
            self.saving_dialog.setLabelText('Recording finished. Saving video…' if state!='Encoding MP4' else 'Recording captured. Encoding and saving MP4…')
            self.saving_dialog.show()
        elif state.startswith('Ready') or 'failed' in state:
            self.finish_saving()
        if state.startswith('Ready') or 'failed' in state:
            self.restore_main_window()
        if hasattr(self,'toolbar'):
            if state in ('recording','paused'):
                self.toolbar.show()
            elif state.startswith('Ready') or 'failed' in state:
                self.toolbar.hide()
            self.toolbar.pause.setEnabled(state=='recording')
            self.toolbar.resume.setEnabled(state=='paused')
            self.toolbar.stop.setEnabled(state in ('recording','paused'))
        self.status.setText(('● ' if state=='recording' else '')+state)
        active=bool(self.recorder and self.recorder.isRunning())
        self.start_button.setEnabled(not active)
        self.options.setEnabled(not active)
        self.pause_button.setEnabled(state=='recording')
        self.resume_button.setEnabled(state=='paused')
        self.stop_button.setEnabled(active and state not in ('Encoding MP4','Finalizing recording','finished'))
    def saving_progress(self,value):
        if self.saving_dialog:
            self.saving_dialog.setRange(0,100)
            self.saving_dialog.setValue(value)
            self.saving_dialog.setLabelText(f'Recording captured. Saving MP4… {value}%')
    def finish_saving(self):
        if self.saving_dialog:
            self.saving_dialog.finish()
            self.saving_dialog=None
    def file_properties(self):
        if not self.last_path:
            self.error('Open or record a video first.')
            return
        from cpp.ui.media_file import MediaFileDialog
        def ready(project):
            dialog=MediaFileDialog(project.source,{'Video dimensions':f'{project.width} × {project.height} px','Duration':f'{project.duration:.3f}s','Frame rate':f'{project.fps:.3f} FPS','Audio':'Yes' if project.audio else 'No'},self)
            dialog.deleted.connect(lambda _:setattr(self,'last_path',None))
            dialog.exec()
        self.jobs.run(lambda:probe(self.last_path),ready,self.error)
    def tick(self):
        if self.recorder:
            seconds=int(self.recorder.clock.seconds())
            value=f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}'
            self.elapsed.setText(value)
            self.toolbar.label.setText(f'● {self.recording_state} · {value}')
    def failed(self,message):
        self.state('Recording failed · source data preserved when available')
        self.error(message)
    def saved(self,path):
        self.finish_saving()
        self.last_path=path
        self.new_name()
        self.status.setText('Saved: '+path)
        box=QMessageBox(self)
        box.setWindowTitle('Recording saved')
        box.setText('Your recording is ready.')
        preview=box.addButton('Play / Preview',QMessageBox.ButtonRole.AcceptRole)
        editor=box.addButton('Open in Video Editor',QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() in (preview,editor):
            self.load(path,autoplay=box.clickedButton()==preview)
    def open_video(self):
        path,_=QFileDialog.getOpenFileName(self,'Open video',self.directory.text(),'Video (*.mp4 *.mkv *.webm *.mov *.avi);;All files (*)')
        if path:
            self.load(path)
    def open_project(self):
        path,_=QFileDialog.getOpenFileName(self,'Open video project',self.directory.text(),'SnapMark project (*.snapmark.json);;JSON (*.json)')
        if path:
            self.jobs.run(lambda:Project.load(path),lambda p:self.editor(p,project_path=path),self.error)
    def load(self,path,autoplay=False):
        self.last_path=path
        self.jobs.run(lambda:probe(path),lambda p:self.editor(p,autoplay),self.error)
    def editor(self,project,autoplay=False,project_path=None):
        try:
            from cpp.video.editor import VideoEditor
            window=VideoEditor(project,self.window())
            window.project_path=project_path
            self.windows.append(window)
            window.destroyed.connect(lambda:self.editor_closed(window))
            window.show()
            if autoplay:
                window.player.sequence.play()
        except ImportError:
            self.error('Install PySide6-Addons in the application environment for video playback.')
    def editor_closed(self,window):
        if window in self.windows:
            self.windows.remove(window)
        self.editors_changed.emit()
    def open_last(self):
        if self.last_path and Path(self.last_path).is_file():
            self.load(self.last_path)
        else:
            self.open_video()
    def open_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.last_path).parent if self.last_path else Path(self.directory.text()).expanduser())))
    def delete(self):
        if not self.last_path:
            return
        if QMessageBox.question(self,'Delete recording?',f'Permanently delete {self.last_path}? Projects referencing it will lose their source.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:
            return
        try:
            Path(self.last_path).unlink()
            self.last_path=None
        except OSError as exc:
            self.error(exc)
