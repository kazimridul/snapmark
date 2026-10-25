"""Video invariants and real, synthetic FFmpeg exports; no desktop consent required."""
from dataclasses import replace
from pathlib import Path
import json
import shutil
import subprocess
import threading
import pytest
from cpp.editor.model import Annotation
from cpp.video.model import History, Project, TimedAnnotation
from cpp.video.recording import RecordingClock, RecordingSettings
from cpp.video.render import ExportSettings, export
from cpp.video import ffmpeg

@pytest.fixture
def project(tmp_path):
    return Project(str(tmp_path/'source.mp4'),10,320,240,30,True)

def test_annotation_timing_and_coordinates(project):
    item=TimedAnnotation(Annotation('highlighter',((10,20),(40,50))),1,4)
    assert not item.active(.99)
    assert item.active(1) and item.active(3.99)
    assert not item.active(4)
    project.annotations.append(item)
    project.validate()
    item.drawing=replace(item.drawing,points=((-1,20),))
    with pytest.raises(ValueError,match='coordinates'):
        project.validate()

def test_trim_split_history(project):
    h=History(project)
    h.edit(lambda p:p.split(3))
    assert h.project.segments==[(0,3),(3,10)]
    h.edit(lambda p:p.split(6))
    h.edit(lambda p:p.segments.pop(1))
    assert h.project.output_duration==7
    h.edit(lambda p:p.trim(1,8))
    assert h.project.segments==[(1,3),(6,8)]
    assert h.project.output_duration==4
    h.undo()
    assert h.project.output_duration==7
    h.redo()
    assert h.project.output_duration==4
    with pytest.raises(ValueError):
        h.edit(lambda p:p.segments.clear())
    assert h.project.output_duration==4

def test_crop_and_settings(project):
    project.crop=(3,5,101,99)
    project.validate()
    project.crop=(300,0,100,100)
    with pytest.raises(ValueError,match='Crop'):
        project.validate()
    for quality in ('Draft','Standard','High'):
        assert len(ExportSettings(quality).encoder())==2
    with pytest.raises(ValueError):
        ExportSettings('fake')

def test_project_round_trip(project,tmp_path):
    Path(project.source).touch()
    project.annotations=[TimedAnnotation(Annotation('text',((5,6),),text='hello\nworld'),1,3)]
    project.crop=(0,0,201,151)
    path=tmp_path/'editable.snapmark.json'
    project.save(path)
    loaded=Project.load(path)
    assert loaded.annotations[0].drawing==project.annotations[0].drawing
    assert loaded.source==project.source
    assert loaded.crop==list(project.crop)
    assert loaded.output_duration==10
    Path(project.source).unlink()
    with pytest.raises(ValueError,match='missing'):
        Project.load(path)

def test_pause_clock():
    now=[100.]
    clock=RecordingClock(lambda:now[0])
    clock.resume()
    now[0]+=3
    clock.pause()
    now[0]+=100
    assert clock.seconds()==3
    clock.resume()
    now[0]+=2
    assert clock.seconds()==5

def test_missing_ffmpeg(monkeypatch):
    monkeypatch.setattr(shutil,'which',lambda _:None)
    with pytest.raises(RuntimeError,match='missing'):
        ffmpeg.binary('ffmpeg')

def test_recording_validation(tmp_path,monkeypatch):
    monkeypatch.setattr('cpp.video.recording.session_type',lambda:'wayland')
    RecordingSettings(str(tmp_path/'a.mp4'),mode='region').validate()
    path=tmp_path/'exists.mp4'
    path.touch()
    with pytest.raises(ValueError,match='new'):
        RecordingSettings(str(path)).validate()

@pytest.fixture
def clip(tmp_path):
    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg unavailable')
    path=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=160x120:r=15:d=3','-f','lavfi','-i','sine=frequency=440:duration=3','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(path)],check=True)
    return ffmpeg.probe(path)

def frame_pixel(path,t):
    result=subprocess.run(['ffmpeg','-v','error','-ss',str(t),'-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True)
    return tuple(result.stdout[:3])

def test_real_export_timing_audio_and_trim(app,clip,tmp_path):
    clip.annotations=[TimedAnnotation(Annotation('highlight_rect',((0,0),(160,120)),color='#ffff00',opacity=1),1,2)]
    clip.crop=(0,0,159,119)
    clip.segments=[(.2,2.7)]
    output=tmp_path/'export.mp4'
    progress=[]
    assert export(clip,output,ExportSettings('Draft'),progress=progress.append)==str(output)
    info=ffmpeg.probe(output)
    assert info.audio
    assert (info.width,info.height)==(160,120)  # pad odd crop, never discard pixels
    assert abs(info.duration-2.5)<.15
    before=frame_pixel(output,.2)
    during=frame_pixel(output,1.1)
    after=frame_pixel(output,2.1)
    assert before[2]>150 and before[0]<50
    assert during[0]>180 and during[1]>180 and during[2]<70
    assert after[2]>150 and after[0]<50
    assert progress[-1]==100
    assert not list(tmp_path.glob('.snapmark-export-*'))
    with pytest.raises(FileExistsError):
        export(clip,output)
    with pytest.raises(ValueError,match='source'):
        export(clip,clip.source)

def test_split_export_and_privacy(app,clip,tmp_path):
    clip.segments=[(0,.6),(2,2.8)]
    clip.annotations=[TimedAnnotation(Annotation('pixelate',((20,20),(80,80))),0,3),TimedAnnotation(Annotation('blur',((90,20),(140,80))),0,3)]
    output=tmp_path/'split.mp4'
    export(clip,output,ExportSettings('Draft'))
    info=ffmpeg.probe(output)
    assert info.audio and abs(info.duration-1.4)<.15

def test_cancellation_cleanup(app,clip,tmp_path):
    cancel=threading.Event()
    cancel.set()
    with pytest.raises(ffmpeg.Cancelled):
        export(clip,tmp_path/'cancel.mp4',cancelled=cancel)
    assert not (tmp_path/'cancel.mp4').exists()
    assert not list(tmp_path.glob('.snapmark-export-*'))
    assert Path(clip.source).exists()

def test_ffmpeg_error():
    with pytest.raises(RuntimeError,match='FFmpeg failed'):
        ffmpeg.run(['-this_option_does_not_exist'])

def test_editor_constructs(app,clip,monkeypatch):
    # Widget wiring is tested without opening restricted desktop audio devices.
    from types import SimpleNamespace
    from unittest.mock import Mock
    from PySide6.QtWidgets import QWidget
    import cpp.video.editor as module
    media=Mock()
    media.position.return_value=0
    fake=SimpleNamespace(media=media,controls=QWidget(),open=Mock())
    def factory(owner,canvas):
        from cpp.video.sequence import SequencePlayback
        fake.sequence=SequencePlayback(media,canvas.project,owner)
        fake.pause=fake.sequence.pause
        fake.seek=lambda delta:fake.sequence.seek_by(delta/1000)
        fake.seek_timeline=fake.sequence.seek
        return fake
    monkeypatch.setattr(module,'Player',factory)
    editor=module.VideoEditor(clip)
    editor.show()
    app.processEvents()
    assert editor.canvas.project.width==160
    editor.close()
    app.processEvents()

def test_gstreamer_pause_resume_and_audio(tmp_path):
    """Actual capture pipeline with synthetic sources: no screen/audio permission."""
    import selectors
    import time
    helper=Path(__file__).parents[1]/'src/cpp/video/gst_helper.py'
    options=dict(test_source=True,session='x11',output=str(tmp_path/'capture.webm'),fps=15,height=0,quality='Low',audio=['synthetic'],volume=1)
    check=subprocess.run(['/usr/bin/python3',str(helper),json.dumps({**options,'check':True})],capture_output=True)
    if check.returncode:
        pytest.skip('System GStreamer dependencies unavailable')
    process=subprocess.Popen(['/usr/bin/python3',str(helper),json.dumps(options)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    selector=selectors.DefaultSelector()
    selector.register(process.stdout,selectors.EVENT_READ)
    def wait_for(state):
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if selector.select(.1):
                line=process.stdout.readline()
                if state in line:
                    return
                if 'error' in line:
                    pytest.fail(line)
            if process.poll() is not None:
                pytest.fail(process.stderr.read())
        pytest.fail('Capture pipeline timed out: '+state)
    def command(value):
        process.stdin.write(value+'\n')
        process.stdin.flush()
    try:
        wait_for('recording')
        time.sleep(.6)
        command('pause')
        wait_for('paused')
        time.sleep(1)
        command('resume')
        wait_for('recording')
        time.sleep(.6)
        command('stop')
        wait_for('finished')
        assert process.wait(5)==0
        captured=ffmpeg.probe(options['output'])
        assert captured.audio
        assert .9<captured.duration<1.8  # one second pause must not enter output
        output=tmp_path/'recording.mp4'
        export(captured,output,ExportSettings('Draft'))
        result=ffmpeg.probe(output)
        assert result.audio and abs(result.duration-captured.duration)<.15
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        selector.close()
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()

def test_rotation_export_and_no_upscale(app,clip,tmp_path):
    rotated=tmp_path/'rotated.mp4'
    subprocess.run(['ffmpeg','-v','error','-display_rotation:v:0','90','-i',clip.source,'-c','copy',str(rotated)],check=True)
    project=ffmpeg.probe(rotated)
    assert (project.width,project.height)==(120,160)
    output=tmp_path/'rotation-export.mp4'
    export(project,output,ExportSettings('Draft',720))
    info=ffmpeg.probe(output)
    assert (info.width,info.height)==(120,160)
    assert info.audio

def test_reordered_layers_change_exported_stacking(app,clip,tmp_path):
    clip.annotations=[
        TimedAnnotation(Annotation('highlight_rect',((0,0),(160,120)),color='#ff0000',opacity=1),0,3),
        TimedAnnotation(Annotation('highlight_rect',((0,0),(160,120)),color='#00ff00',opacity=1),0,3),
    ]
    before=tmp_path/'green-on-top.mp4'
    export(clip,before,ExportSettings('Draft'))
    assert frame_pixel(before,1)[1]>180
    clip.annotations.reverse()
    after=tmp_path/'red-on-top.mp4'
    export(clip,after,ExportSettings('Draft'))
    assert frame_pixel(after,1)[0]>180

def test_reordered_and_deleted_video_export_matches_sequence(app,tmp_path):
    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg unavailable')
    source=tmp_path/'three-colors.mp4'
    graph='color=c=red:s=160x120:r=15:d=1[r];color=c=green:s=160x120:r=15:d=1[g];color=c=blue:s=160x120:r=15:d=1[b];[r][g][b]concat=n=3:v=1:a=0'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',graph,'-f','lavfi','-i','sine=frequency=440:duration=3','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True)
    project=ffmpeg.probe(source)
    project.segments=[(2,3),(0,1)]  # blue first, green deleted, red last
    output=tmp_path/'edited.mp4'
    export(project,output,ExportSettings('Draft'))
    info=ffmpeg.probe(output)
    assert info.audio and abs(info.duration-2)<.1
    blue=frame_pixel(output,.4)
    red=frame_pixel(output,1.4)
    assert blue[2]>180 and blue[0]<50
    assert red[0]>180 and red[1]<50
