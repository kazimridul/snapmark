"""Edited-time mapping and playback: cuts/reordering must affect every transport."""
from pathlib import Path
import pytest
from PySide6.QtCore import QObject, Signal
from cpp.editor.model import Annotation
from cpp.video.model import Project, TimedAnnotation
from cpp.video.sequence import SequencePlayback

class Media(QObject):
    positionChanged=Signal(int)
    def __init__(self):
        super().__init__()
        self.ms=0
        self.running=False
        self.seeks=[]
    def position(self):
        return self.ms
    def setPosition(self,ms):
        self.ms=ms
        self.seeks.append(ms)
        self.positionChanged.emit(ms)
    def play(self):
        self.running=True
    def pause(self):
        self.running=False
    def tick(self,ms):
        self.ms=ms
        self.positionChanged.emit(ms)

@pytest.fixture
def project(tmp_path):
    return Project(str(tmp_path/'source.mp4'),10,320,240,segments=[(0,2),(4,6),(8,10)])

@pytest.fixture
def playback(project,app):
    media=Media()
    player=SequencePlayback(media,project)
    yield player,media
    player.pause()

def test_reorder_mapping_trim_split_and_save(project,tmp_path):
    project.move_segment(2,0)
    assert project.segments==[(8,10),(0,2),(4,6)]
    project.validate()
    assert project.output_duration==6
    assert project.source_at(0)==(0,8)
    assert project.source_at(2)==(1,0)
    assert project.source_at(4.5)==(2,4.5)
    assert project.timeline_at(1)==3
    Path(project.source).touch()
    path=tmp_path/'order.snapmark.json'
    project.save(path)
    loaded=Project.load(path)
    assert loaded.segments==[[8,10],[0,2],[4,6]]
    loaded.split_timeline(1)
    assert loaded.segments[:2]==[(8,9),(9,10)]
    project.trim_timeline(.5,4.5)
    assert project.segments==[(8.5,10),(0,2),(4,4.5)]
    assert project.output_duration==4

def test_overlap_rejected_in_any_order(project):
    project.segments=[(8,10),(0,3),(2,4)]
    with pytest.raises(ValueError,match='overlap'):
        project.validate()

def test_annotations_follow_reordered_and_cut_source(project):
    item=TimedAnnotation(Annotation('arrow',((10,10),(20,20))),1,9)
    project.move_segment(2,0)
    assert project.annotation_spans(item)==[(0,0,1),(1,3,4),(2,4,6)]

def test_playback_skips_cuts_and_follows_reordered_clips(playback,project):
    sequence,media=playback
    project.move_segment(2,0)
    sequence.set_project(project)
    sequence.seek(0)
    sequence.play()
    assert media.position()==8000
    media.tick(8500)
    assert sequence.position==.5
    assert sequence.accept_frame(8.5)
    media.tick(10000)
    assert sequence.index==1 and media.position()==0 and media.running
    assert not sequence.accept_frame(9.9)  # old buffered frame after backward seek
    assert sequence.accept_frame(0)
    media.tick(1000)
    assert sequence.position==3
    media.tick(2000)
    assert sequence.index==2 and media.position()==4000
    assert not sequence.accept_frame(3)  # removed section never reaches canvas
    assert sequence.accept_frame(4)
    media.tick(6000)
    assert not sequence.playing and not media.running
    assert sequence.position==6
    sequence.play()
    assert media.position()==8000  # replay starts at the first edited clip

def test_delete_current_clip_updates_paused_preview_immediately(playback,project):
    sequence,media=playback
    sequence.seek(3)
    assert media.position()==5000
    project.segments.pop(1)
    sequence.set_project(project)
    assert sequence.position==2 and media.position()==8000
    assert not sequence.accept_frame(5)
    assert sequence.accept_frame(8)
    assert sequence.project.output_duration==4

def test_delete_earlier_clip_preserves_current_content_and_moves_playhead(playback,project):
    sequence,media=playback
    sequence.seek(4.5)
    project.segments.pop(0)
    sequence.set_project(project)
    assert sequence.source==8.5
    assert sequence.position==2.5
    assert media.position()==8500

def test_seek_step_end_and_stale_seek_results(playback):
    sequence,media=playback
    sequence.seek(1.9)
    sequence.seek_by(.2)
    assert media.position()==4100
    sequence.seek(5.5)
    assert media.position()==9500
    # A late source-position notification must not undo a user seek.
    sequence.pending=True
    media.tick(8500)
    assert sequence.position==5.5
    sequence.seek(sequence.project.output_duration)
    assert sequence.position==6
    assert 9900<media.position()<10000
    sequence.stop()
    assert sequence.position==0 and media.position()==0

def test_player_clears_deleted_frame_while_waiting_for_seek(app,project):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QLabel
    from cpp.video.player import Player
    project.segments=[(8,10)]
    canvas=SimpleNamespace(position=5,frame=QImage(4,4,QImage.Format.Format_RGB32),update=Mock())
    player=SimpleNamespace(canvas=canvas,sequence=SimpleNamespace(project=project,index=0),time=QLabel())
    Player.position(player,0,8)
    assert canvas.frame.isNull()
    assert player.time.text().endswith('00:00:02.000')
