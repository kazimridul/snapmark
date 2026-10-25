"""Source-backed playback of an edited sequence without rendering a temp movie."""
from PySide6.QtCore import QObject, QTimer, Signal

class SequencePlayback(QObject):
    changed=Signal(float,float)  # edited seconds, source seconds
    def __init__(self,media,project,parent=None):
        super().__init__(parent)
        self.media=media
        self.project=project
        self.index=0
        self.position=0.
        self.source=project.segments[0][0]
        self.playing=False
        self.at_end=False
        self.pending=False
        self.pending_frame=False
        self._signature=None
        self._clip_start=0.
        self.timer=QTimer(self)
        self.timer.setInterval(10)
        self.timer.timeout.connect(lambda:self.source_position(self.media.position()))
        self.media.positionChanged.connect(self.source_position)
        self.set_project(project)

    def set_project(self,project):
        signature=tuple(tuple(segment) for segment in project.segments)
        self.project=project
        if signature==self._signature:
            return
        old_source,old_start=self.source,self._clip_start
        self._signature=signature
        for span in project.spans:
            if span.source_start<=old_source<span.source_end:
                self.seek(span.start+old_source-span.source_start)
                return
        self.seek(min(old_start,project.output_duration))

    def seek(self,seconds):
        t=max(0,min(seconds,self.project.output_duration))
        self.index,source=self.project.source_at(t)
        span=self.project.spans[self.index]
        self._clip_start=span.start
        self.at_end=t>=self.project.output_duration
        self.position=t
        # End seeks display the final kept frame, never footage after the cut.
        if self.at_end:
            source=max(span.source_start,span.source_end-1/self.project.fps)
        self.source=source
        self._seek_target=source
        self.pending=True
        self.pending_frame=True
        self.media.setPosition(round(source*1000))
        self.changed.emit(t,source)

    def seek_by(self,seconds):
        self.seek(self.position+seconds)

    def play(self):
        if self.at_end:
            self.seek(0)
        else:
            self.seek(self.position)
        self.playing=True
        self.media.play()
        self.timer.start()

    def pause(self):
        self.playing=False
        self.timer.stop()
        self.media.pause()

    def toggle(self):
        self.pause() if self.playing else self.play()

    def stop(self):
        self.pause()
        self.seek(0)

    def advance(self):
        if self.index+1>=len(self.project.segments):
            self.pause()
            self.at_end=True
            self.position=self.project.output_duration
            self.changed.emit(self.position,self.source)
            return
        following=self.project.spans[self.index+1]
        self.seek(following.start)
        if self.playing:
            # Also handles a reordered clip ending at the physical source EOF.
            self.media.play()

    def source_position(self,ms):
        source=ms/1000
        span=self.project.spans[self.index]
        if self.pending:
            if not span.source_start-.002<=source<span.source_end or abs(source-self._seek_target)>max(.15,2/self.project.fps):
                return
            self.pending=False
        if source>=span.source_end-.0001:
            if self.playing:
                self.advance()
            return
        if source<span.source_start-.002 or self.at_end:
            return
        self.source=max(span.source_start,source)
        self.position=span.start+self.source-span.source_start
        self.changed.emit(self.position,self.source)

    def accept_frame(self,source):
        """Reject buffered frames from removed footage and pre-seek clips."""
        span=self.project.spans[self.index]
        if not span.source_start-.002<=source<span.source_end:
            if self.playing and not self.pending_frame and source>=span.source_end:
                self.advance()
            return False
        if self.pending_frame:
            self.pending_frame=False
            self.pending=False
        return True
