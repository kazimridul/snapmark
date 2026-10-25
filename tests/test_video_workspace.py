"""Workspace interaction, native completion notifications and region capture."""
import asyncio
from pathlib import Path
import json
import os
import subprocess
import time
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget
from cpp.editor.model import Annotation
from cpp.video.model import Project, TimedAnnotation

@pytest.fixture
def editor(app,monkeypatch,tmp_path):
    import cpp.video.editor as module
    media=Mock()
    media.position.return_value=0
    player=SimpleNamespace(media=media,controls=QWidget(),open=Mock())
    def factory(owner,canvas):
        from cpp.video.sequence import SequencePlayback
        player.sequence=SequencePlayback(media,canvas.project,owner)
        player.pause=player.sequence.pause
        player.seek=lambda delta:player.sequence.seek_by(delta/1000)
        player.seek_timeline=player.sequence.seek
        return player
    monkeypatch.setattr(module,'Player',factory)
    window=module.VideoEditor(Project(str(tmp_path/'source.mp4'),10,320,240))
    window.show()
    app.processEvents()
    yield window
    window.dirty=False
    window.close()
    app.processEvents()

def test_icon_tools_context_and_resizable_docks(editor,app):
    assert editor.property_scroll.isHidden()
    assert all(not b.icon().isNull() for b in editor.tool_buttons.values())
    editor.tool_buttons['text'].click()
    app.processEvents()
    assert editor.canvas.tool=='text'
    assert not editor.property_scroll.isHidden()
    assert not editor.property_rows['font'].isHidden()
    assert editor.property_rows['width'].isHidden()
    text_cursor=editor.canvas.cursor().pixmap().cacheKey()
    editor.tool_buttons['pen'].click()
    assert editor.canvas.tool=='pen'
    assert editor.canvas.cursor().pixmap().cacheKey()!=text_cursor
    assert not editor.property_rows['width'].isHidden()
    assert editor.property_rows['font'].isHidden()
    assert editor.tools_dock.maximumWidth()>500
    assert editor.timeline_dock.maximumHeight()>500
    assert set(editor.header_actions)=={'save','undo','redo','fullscreen'}

def test_layers_move_resize_reorder_undo(editor,app):
    editor.tool_buttons['rectangle'].click()
    editor.add_annotation(Annotation('rectangle',((10,10),(80,60))))
    editor.tool_buttons['arrow'].click()
    editor.add_annotation(Annotation('arrow',((90,20),(140,80))))
    a,b=editor.history.project.annotations
    editor.change_timing(a.id,2,5)
    assert editor.history.project.annotations[0].start==2
    assert editor.start.value()==2
    editor.reorder_layers(0,1)
    assert [i.id for i in editor.history.project.annotations]==[b.id,a.id]
    editor.undo()
    assert [i.id for i in editor.history.project.annotations]==[a.id,b.id]
    editor.undo()
    assert editor.history.project.annotations[0].start==0
    assert editor.changes.count()==3

def test_timeline_drag_changes_model(editor,app):
    editor.add_annotation(Annotation('pen',((10,10),(80,60))))
    timeline=editor.timeline
    app.processEvents()
    initial=editor.history.project.annotations[0]
    y=timeline.HEADER+timeline.ROW+timeline.ROW//2
    start=QPoint(round(timeline.x(1)),y)
    end=QPoint(round(timeline.x(4)),y)
    QTest.mousePress(timeline,Qt.MouseButton.LeftButton,pos=start)
    QTest.mouseMove(timeline,end)
    QTest.mouseRelease(timeline,Qt.MouseButton.LeftButton,pos=end)
    item=editor.history.project.annotations[0]
    assert abs(item.start-3)<.05 and abs(item.end-6)<.05
    editor.undo()
    assert editor.history.project.annotations[0].start==0

def test_native_recorder_only_imports_closed_new_files(app,tmp_path):
    from cpp.video.system_recordings import SystemRecordings
    folder=tmp_path/'Videos'
    target=folder/'Screencasts'
    target.mkdir(parents=True)
    (target/'existing.webm').write_bytes(b'old')
    watcher=SystemRecordings(directory=folder)
    received=[]
    watcher.ready.connect(received.append)
    path=target/'new.webm'
    stream=path.open('wb')
    stream.write(b'ongoing')
    stream.flush()
    app.processEvents()
    assert received==[]
    stream.close()
    QTest.qWait(20)
    app.processEvents()
    assert received==[str(path)]
    with (target/'existing.webm').open('ab') as output:
        output.write(b'edit')
    QTest.qWait(20)
    assert received==[str(path)]
    watcher.deleteLater()
    app.processEvents()

def test_legacy_settings_preserve_system_shortcut(tmp_path,app):
    from cpp.config import Settings
    path=tmp_path/'settings.json'
    path.write_text(json.dumps({'print_screen':True}))
    assert not Settings.load(path).print_screen
    Settings(print_screen=True).save(path)
    assert Settings.load(path).print_screen  # new explicit override is respected
    assert not Settings().print_screen

@pytest.fixture
def helper():
    path=Path(__file__).parents[1]/'src/cpp/video/gst_helper.py'
    check=subprocess.run(['/usr/bin/python3',str(path),json.dumps({'check':True,'session':'x11'})],capture_output=True)
    if check.returncode:
        pytest.skip('GStreamer unavailable')
    return path

def test_snapshot_and_region_pipeline(helper,tmp_path):
    import selectors
    from cpp.video.ffmpeg import probe
    snapshot=tmp_path/'preview.png'
    options=dict(session='x11',test_source=True,snapshot=True,output=str(snapshot),fps=15,height=0,quality='Low',audio=[],volume=1)
    result=subprocess.run(['/usr/bin/python3',str(helper),json.dumps(options)],capture_output=True,timeout=10)
    assert result.returncode==0,result.stdout+result.stderr
    assert QImage(str(snapshot)).size().width()==320
    assert b'"state": "recording"' not in result.stdout
    output=tmp_path/'region.webm'
    options.update(snapshot=False,session='wayland',fd=0,node=0,region=[20,30,100,80],source_size=[320,240],output=str(output))
    process=subprocess.Popen(['/usr/bin/python3',str(helper),json.dumps(options)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    selector=selectors.DefaultSelector()
    selector.register(process.stdout,selectors.EVENT_READ)
    try:
        assert selector.select(10),'No pipeline status'
        line=process.stdout.readline()
        assert 'recording' in line,line
        time.sleep(.4)
        process.stdin.write('stop\n')
        process.stdin.flush()
        out,err=process.communicate(timeout=10)
        assert process.returncode==0,out+err
        info=probe(output)
        assert (info.width,info.height)==(100,80)
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
            process.wait()

def test_wayland_region_handoff(app,helper,tmp_path):
    from cpp.video.recording import Recorder, RecordingSettings
    recorder=Recorder(RecordingSettings(str(tmp_path/'result.mp4'),mode='region'))
    fd=os.open('/dev/null',os.O_RDONLY)
    options=dict(session='wayland',test_source=True,fd=fd,node=0,output=str(tmp_path/'unused'),fps=15,height=0,quality='Low',audio=[],volume=1)
    portal=SimpleNamespace(closed=False,open_remote=Mock())
    async def remote():
        return fd
    portal.open_remote=remote
    recorder.region_requested.connect(lambda image:recorder.select_region((10,20,120,80)))
    try:
        asyncio.run(recorder.request_region(options,portal))
        assert options['region']==(10,20,120,80)
        assert options['source_size']==[320,240]
        assert recorder.clock.seconds()==0
    finally:
        os.close(fd)

def test_wayland_region_cancel_never_starts_recording(app,helper,tmp_path,monkeypatch):
    from cpp.video.recording import Recorder, RecordingSettings
    import tempfile
    monkeypatch.setattr(tempfile,'tempdir',str(tmp_path))
    recorder=Recorder(RecordingSettings(str(tmp_path/'result.mp4'),mode='region'))
    fd=os.open('/dev/null',os.O_RDONLY)
    options=dict(session='wayland',test_source=True,fd=fd,node=0,fps=15,height=0,quality='Low',audio=[],volume=1)
    portal=SimpleNamespace(closed=False,open_remote=Mock())
    recorder.region_requested.connect(lambda _:recorder.command('stop'))
    try:
        with pytest.raises(RuntimeError,match='cancelled'):
            asyncio.run(recorder.request_region(options,portal))
        assert recorder.clock.seconds()==0
        assert not (tmp_path/'result.mp4').exists()
        assert not list(tmp_path.glob('snapmark-recording-area-*'))
        portal.open_remote.assert_not_called()
    finally:
        os.close(fd)

def test_split_clip_drag_and_ripple_delete(editor,app):
    editor.player.sequence.seek(3)
    editor.split()
    editor.player.sequence.seek(6)
    editor.split()
    assert editor.history.project.segments==[(0,3),(3,6),(6,10)]
    timeline=editor.timeline
    app.processEvents()
    y=timeline.HEADER+timeline.ROW//2
    QTest.mousePress(timeline,Qt.MouseButton.LeftButton,pos=QPoint(round(timeline.x(8)),y))
    QTest.mouseMove(timeline,QPoint(round(timeline.x(.3)),y))
    QTest.mouseRelease(timeline,Qt.MouseButton.LeftButton,pos=QPoint(round(timeline.x(.3)),y))
    assert editor.history.project.segments==[(6,10),(0,3),(3,6)]
    assert editor.segments.currentIndex()==0
    editor.segments.setCurrentIndex(1)
    editor.remove_segment()
    assert editor.history.project.segments==[(6,10),(3,6)]
    assert editor.history.project.output_duration==7
    assert [span.start for span in editor.history.project.spans]==[0,4]
    assert editor.trim_end.value()==7
    editor.undo()
    assert editor.history.project.output_duration==10
    editor.undo()
    assert editor.history.project.segments==[(0,3),(3,6),(6,10)]

def test_zoom_and_horizontal_scroll_seek_in_edited_time(editor,app):
    from PySide6.QtCore import QPointF, QCoreApplication
    from PySide6.QtGui import QWheelEvent
    viewport=editor.timeline_scroll.viewport()
    center=viewport.rect().center()
    event=QWheelEvent(QPointF(center),QPointF(viewport.mapToGlobal(center)),QPoint(),QPoint(0,480),Qt.MouseButton.NoButton,Qt.KeyboardModifier.ControlModifier,Qt.ScrollPhase.NoScrollPhase,False)
    QCoreApplication.sendEvent(viewport,event)
    app.processEvents()
    assert editor.timeline_zoom==2
    scrollbar=editor.timeline_scroll.horizontalScrollBar()
    assert scrollbar.maximum()>0
    scrollbar.setValue(scrollbar.maximum())
    app.processEvents()
    x=scrollbar.value()+viewport.width()//2
    expected=editor.timeline.seconds(x)
    QTest.mouseClick(editor.timeline,Qt.MouseButton.LeftButton,pos=QPoint(x,10))
    assert abs(editor.player.sequence.position-expected)<.01
    editor.fit_timeline()
    app.processEvents()
    assert scrollbar.maximum()==0 and scrollbar.value()==0

def test_move_tool_drag_survives_selection_and_updates_geometry(editor,app):
    editor.add_annotation(Annotation('rectangle',((40,40),(120,100))))
    editor.activate_select()
    editor.canvas.frame=QImage(320,240,QImage.Format.Format_RGB32)
    editor.canvas.frame.fill(QColor('white'))
    app.processEvents()
    canvas=editor.canvas
    def point(x,y):
        return QPoint(round(canvas.target.x()+x/320*canvas.target.width()),round(canvas.target.y()+y/240*canvas.target.height()))
    QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=point(70,65))
    assert canvas.points  # selecting the object must not reset the gesture
    QTest.mouseMove(canvas,point(100,85))
    assert canvas.move_preview is not None
    QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=point(100,85))
    drawing=editor.history.project.annotations[0].drawing
    assert abs(drawing.points[0][0]-70)<1
    assert abs(drawing.points[0][1]-60)<1
    assert abs(editor.geometry_controls[0].value()-70)<1

def test_geometry_fields_apply_without_extra_button(editor):
    editor.add_annotation(Annotation('rectangle',((40,40),(120,100))))
    for control,value in zip(editor.geometry_controls,[80,70,110,90]):
        control.setValue(value)
    editor.geometry_controls[-1].editingFinished.emit()
    assert editor.history.project.annotations[0].drawing.points==((80,70),(190,160))
    count=len(editor.history.past)
    editor.resize_annotation()
    assert len(editor.history.past)==count  # same values do not create changes

def test_unchanged_and_undone_video_does_not_prompt(editor,monkeypatch):
    from cpp.video.editor import QMessageBox
    def unexpected(*args):
        pytest.fail('Unchanged recording must not ask to save')
    monkeypatch.setattr(QMessageBox,'question',unexpected)
    editor.undo()
    assert not editor.dirty
    editor.add_annotation(Annotation('arrow',((20,20),(90,90))))
    assert editor.dirty
    editor.undo()
    assert not editor.dirty
    assert editor.close()

def test_dedicated_crop_dialog_numeric_reset_apply(app):
    from cpp.video.crop_dialog import VideoCropDialog
    image=QImage(320,240,QImage.Format.Format_RGB32)
    dialog=VideoCropDialog(image)
    assert not dialog.apply_button.isEnabled()
    for control,value in zip(dialog.controls,[20,30,200,150]):
        control.setValue(value)
    dialog.numeric_region()
    assert dialog.apply_button.isEnabled()
    assert '200 × 150' in dialog.dimensions.text()
    dialog.apply()
    assert dialog.crop==(20,30,200,150)
    dialog.reset()
    dialog.apply()
    assert dialog.crop==(0,0,320,240)
    dialog.deleteLater()

def test_recording_saving_loader_stays_until_finished(app,monkeypatch):
    from cpp.video.panel import RecordingPanel
    monkeypatch.setattr('cpp.video.panel.sources',lambda:[])
    panel=RecordingPanel()
    panel.state('Finalizing recording')
    assert panel.saving_dialog and panel.saving_dialog.isVisible()
    assert panel.saving_dialog.minimum()==panel.saving_dialog.maximum()==0
    panel.state('Encoding MP4')
    panel.saving_progress(45)
    assert panel.saving_dialog.value()==45
    assert 'Saving MP4' in panel.saving_dialog.labelText()
    panel.saving_dialog.reject()
    assert panel.saving_dialog.isVisible()
    panel.state('Ready')
    assert panel.saving_dialog is None
    deadline=time.monotonic()+3
    while panel.jobs.active and time.monotonic()<deadline:
        app.processEvents()
        QTest.qWait(5)
    panel.deleteLater()
    app.processEvents()

def test_export_completion_only_shows_message(editor,monkeypatch,tmp_path):
    from cpp.video.editor import QFileDialog,QMessageBox
    messages=[]
    path=str(tmp_path/'edited.mp4')
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(path,''))
    monkeypatch.setattr(QMessageBox,'information',lambda parent,title,text:messages.append(text))
    def run(work,ready,failed):
        editor.progress.setValue(100)
        ready(path)
    monkeypatch.setattr(editor.jobs,'run',run)
    assert editor.export_progress_row.isHidden()
    editor.export()
    assert messages==['Export complete']
    assert editor.export_progress_row.isHidden()
    assert editor.export_button.isEnabled()

def test_video_source_delete_closes_without_another_save_prompt(editor,app,monkeypatch):
    from cpp.video.editor import QMessageBox
    from unittest.mock import Mock
    path=Path(editor.history.project.source)
    path.write_bytes(b'video')
    editor.add_annotation(Annotation('pen',((20,20),(80,60))))
    assert editor.dirty
    with monkeypatch.context() as patch:
        close=Mock()
        patch.setattr(editor,'close',close)
        patch.setattr(QMessageBox,'question',lambda *a:QMessageBox.StandardButton.Yes)
        editor.delete_from_storage()
        app.processEvents()
        assert not path.exists() and not editor.dirty
        close.assert_called_once()

def test_text_geometry_and_flat_stroke_resize(editor):
    editor.add_annotation(Annotation('text',((10,10),),text='Hello',font_size=24))
    editor.geometry_controls[0].setValue(40)
    editor.geometry_controls[1].setValue(50)
    editor.geometry_controls[3].setValue(editor.geometry_controls[3].value()*2)
    editor.resize_annotation()
    drawing=editor.history.project.annotations[0].drawing
    assert drawing.points==((40,50),) and 47<=drawing.font_size<=49
    editor.add_annotation(Annotation('pen',((20,40),(100,40))))
    editor.geometry_controls[3].setValue(50)
    editor.resize_annotation()
    assert editor.history.project.annotations[1].drawing.points==((20,40),(100,90))

def test_geometry_focus_without_edit_does_not_change_fractional_points(editor):
    import copy
    editor.add_annotation(Annotation('rectangle',((40.123,40.876),(120.543,100.324))))
    before=copy.deepcopy(editor.history.project)
    editor.clean_project=copy.deepcopy(before)
    editor.dirty=False
    count=len(editor.history.past)
    editor.geometry_controls[0].editingFinished.emit()
    assert editor.history.project==before
    assert len(editor.history.past)==count and not editor.dirty
