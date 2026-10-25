"""Every exposed preset is rendered, persisted and checked in exported pixels."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import threading
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QImage
from cpp.editor.model import Annotation
from cpp.video.animations import Animation,Animations,CATALOG,available,defaults,progress,window
from cpp.video.animation_render import composite_frame,state_for
from cpp.video.model import Project,TimedAnnotation,History
from cpp.video.render import export,ExportSettings
from cpp.video import ffmpeg

@pytest.fixture
def project(tmp_path):
    return Project(str(tmp_path/'source.mp4'),3,160,120,15)

@pytest.fixture
def frame(app):
    image=QImage(160,120,QImage.Format.Format_RGBA8888);image.fill(QColor('#123456'));return image

PRESETS=[(phase,name) for phase in ('entrance','emphasis','exit') for name in CATALOG[phase] if name!='None']
@pytest.mark.parametrize('phase,name',PRESETS)
def test_every_annotation_preset_changes_rendered_pixels(app,project,frame,phase,name):
    kind='text' if name=='Typewriter' else 'rectangle' if name=='Border Pulse' else 'arrow'
    a=TimedAnnotation(Annotation(kind,((40,35),(110,75)) if kind!='text' else ((35,35),),color='#f03020',width=5,text='Hello world',font_size=24),0,3,id='abcdef012345')
    spec=defaults(phase,name)
    if phase!='emphasis':spec.duration=1
    setattr(a.animations,phase,spec)
    project.annotations=[a]
    project.validate()
    samples=[2+t if phase=='exit' else t for t in (0,.2,.4,.6,.8,.99)]
    hashes=[]
    for t in samples:
        result=composite_frame(frame,project,t,t)
        assert not result.isNull()
        hashes.append(hashlib.sha256(bytes(result.constBits())).hexdigest())
    assert len(set(hashes))>1,name

@pytest.mark.parametrize('name',[n for n in CATALOG['join'] if n!='None'])
def test_all_join_transitions_cover_the_cut_and_preserve_duration(app,project,frame,name):
    project.segments=[(0,1),(2,3)]
    project.transitions[project.join_key(*project.segments)]=defaults('join',name)
    project.validate()
    at_cut=composite_frame(frame,project,2,1)
    assert at_cut.pixelColor(80,60).red()<5 and at_cut.pixelColor(80,60).blue()<5
    assert project.output_duration==2
    assert project.join_audio_gain(1)==0
    assert project.join_audio_gain(.5)==1

def test_contextual_availability_and_invalid_properties():
    assert 'Typewriter' in available('entrance','annotation','text')
    assert 'Typewriter' not in available('entrance','annotation','arrow')
    assert available('exit','annotation','blur')==['None']
    assert available('emphasis','video')==['None']
    with pytest.raises(ValueError):Animation('Fade In',params={'opacity_start':2}).validate('entrance')
    with pytest.raises(ValueError):Animation('Fade In',delay=float('nan')).validate('entrance')
    with pytest.raises(ValueError):Animation('Shake',params={'speed':0}).validate('emphasis')
    with pytest.raises(ValueError):Animation('Fade In',params={'unknown':1}).validate('entrance')

def test_timing_delay_reverse_alternate_and_speed():
    spec=Animation('Fade In',duration=.5,delay=.2,easing='Linear')
    assert progress(spec,'entrance',.1,3)[0]==-1
    assert progress(spec,'entrance',.45,3)[0]==pytest.approx(.5)
    spec.reverse=True
    assert progress(spec,'entrance',.3,3)[0]==pytest.approx(.8)
    spec=Animation('Pulse',repeat=True,repeat_count=2,alternate=True,easing='Linear',params={'speed':1})
    assert progress(spec,'emphasis',.2,3)[0]==pytest.approx(.2)
    assert progress(spec,'emphasis',1.2,3)[0]==pytest.approx(.8)
    assert progress(spec,'emphasis',2.2,3) is None
    slow=Animation('Pulse',repeat=True,repeat_count=0,easing='Linear',params={'speed':.1})
    assert progress(slow,'emphasis',1,3)[0]==pytest.approx(.1)
    out=Animation('Fade Out',duration=1,delay=.3)
    assert window(out,'exit',3)[0]==pytest.approx(2.3)
    typing=Animation('Typewriter',duration=2,params={'timing_mode':'Typing speed','typing_speed':5})
    assert window(typing,'entrance',10,'Hello')[2]==1

def test_project_v2_animation_roundtrip_and_v1_migration(project,tmp_path):
    Path(project.source).touch()
    project.annotations=[TimedAnnotation(Annotation('text',((20,20),),text='Hello'),0,3)]
    project.annotations[0].animations.entrance=Animation('Typewriter',duration=1)
    project.video_animations.exit=Animation('Fade Out')
    project.segments=[(0,1),(2,3)]
    project.transitions[project.join_key(*project.segments)]=Animation('Fade through color')
    path=tmp_path/'animated.snapmark.json';project.save(path)
    assert json.loads(path.read_text())['version']==2
    loaded=Project.load(path)
    assert loaded.annotations[0].animations==project.annotations[0].animations
    assert loaded.video_animations==project.video_animations
    assert loaded.transitions==project.transitions
    data=json.loads(path.read_text());data['version']=1;data.pop('video_animations');data.pop('transitions')
    for a in data['annotations']:a.pop('animations')
    path.write_text(json.dumps(data));legacy=Project.load(path)
    assert not legacy.has_animations
    history=History(legacy)
    history.edit(lambda p:setattr(p.video_animations,'entrance',Animation('Zoom In')))
    assert history.project.has_animations
    history.undo();assert not history.project.has_animations


def test_dialog_properties_filter_and_reset(app,project):
    from cpp.video.animation_dialog import AnimationDialog
    project.annotations=[TimedAnnotation(Annotation('text',((20,20),),text='Hello'),0,3)]
    dialog=AnimationDialog(project,('annotation',project.annotations[0].id))
    panel=dialog.panels['entrance'];panel.kind.setCurrentText('Typewriter')
    assert set(panel.controls)=={'timing_mode','character_order','typing_speed','cursor'}
    assert panel.duration.isEnabled() and not panel.controls['typing_speed'].isEnabled()
    panel.controls['timing_mode'].setCurrentText('Typing speed')
    assert not panel.duration.isEnabled() and panel.controls['typing_speed'].isEnabled()
    panel.controls['typing_speed'].setValue(3)
    panel.reset_effect()
    assert panel.controls['typing_speed'].value()==20
    assert not project.annotations[0].animations.enabled  # edits remain a draft
    dialog.apply()
    assert dialog.draft.annotations[0].animations.entrance.kind=='Typewriter'
    dialog.deleteLater()

@pytest.fixture
def clip(tmp_path):
    if not shutil.which('ffmpeg'):pytest.skip('FFmpeg unavailable')
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=160x120:r=15:d=3','-f','lavfi','-i','sine=frequency=440:duration=3','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True)
    return ffmpeg.probe(source)

def pixel(path,time,x=80,y=60):
    result=subprocess.run(['ffmpeg','-v','error','-ss',str(time),'-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True)
    index=(y*160+x)*3;return tuple(result.stdout[index:index+3])

def test_real_animated_export_entrance_exit_join_audio(app,clip,tmp_path):
    clip.segments=[(0,1),(2,3)]
    clip.video_animations.entrance=Animation('Fade In',duration=.5,easing='Linear')
    clip.video_animations.exit=Animation('Fade Out',duration=.5,easing='Linear')
    clip.transitions[clip.join_key(*clip.segments)]=Animation('Fade through color',duration=.4,easing='Linear')
    path=tmp_path/'animated.mp4';values=[]
    export(clip,path,ExportSettings('Draft'),progress=values.append)
    info=ffmpeg.probe(path)
    assert info.audio and abs(info.duration-2)<.1
    assert pixel(path,0)[2]<20
    assert pixel(path,.6)[2]>180
    assert pixel(path,1)[2]<25
    assert pixel(path,1.3)[2]>180
    assert pixel(path,1.93)[2]<80
    assert values[-1]==100 and not list(tmp_path.glob('.snapmark-export-*'))

def test_real_animated_annotation_export_and_cancel(app,clip,tmp_path):
    item=TimedAnnotation(Annotation('highlight_rect',((0,0),(160,120)),color='#ffff00',opacity=1),0,3)
    item.animations.entrance=Animation('Fade In',duration=1,easing='Linear')
    clip.annotations=[item]
    output=tmp_path/'annotation.mp4';export(clip,output,ExportSettings('Draft'))
    first=pixel(output,0);middle=pixel(output,.5);last=pixel(output,1.3)
    assert first[2]>180 and first[0]<30
    assert 60<middle[0]<200 and 60<middle[2]<200
    assert last[0]>180 and last[1]>180 and last[2]<30
    cancelled=threading.Event();cancelled.set()
    with pytest.raises(ffmpeg.Cancelled):export(clip,tmp_path/'cancelled.mp4',cancelled=cancelled)
    assert not (tmp_path/'cancelled.mp4').exists() and Path(clip.source).exists()
    assert not list(tmp_path.glob('.snapmark-export-*'))

def test_noop_dialog_apply_stays_clean_for_join_and_video(app,project):
    from cpp.video.animation_dialog import AnimationDialog
    project.segments=[(0,1),(2,3)]
    for target in [('video',None),('join',1)]:
        dialog=AnimationDialog(project,target)
        dialog.apply()
        assert dialog.draft==project
        dialog.deleteLater()

def test_video_slide_defaults_use_cropped_output_dimensions(app,project):
    from cpp.video.animation_dialog import AnimationDialog
    project.crop=(10,10,100,80)
    dialog=AnimationDialog(project)
    dialog.panels['entrance'].kind.setCurrentText('Slide In Left')
    assert dialog.panels['entrance'].spec().params['x_offset']==-100
    dialog.deleteLater()

def test_crop_global_transform_anchors_to_cropped_frame(app,project,frame):
    from cpp.video.animation_render import video_matrix
    from PySide6.QtCore import QPointF
    project.crop=(40,30,80,60)
    project.video_animations.entrance=Animation('Zoom In',duration=1,easing='Linear')
    matrix,shown=video_matrix(project,.5)
    assert shown and matrix.map(QPointF(80,60))==QPointF(80,60)
    result=composite_frame(frame,project,.5,.5).copy(*project.crop)
    assert result.pixelColor(0,0).blue()==0
    assert result.pixelColor(40,30).blue()>50

def test_mid_export_cancellation_cleans_children_and_temp(app,clip,tmp_path):
    clip.video_animations.entrance=Animation('Fade In',duration=1)
    cancelled=threading.Event()
    def stop(value):
        if value>=5:cancelled.set()
    with pytest.raises(ffmpeg.Cancelled):export(clip,tmp_path/'interrupted.mp4',cancelled=cancelled,progress=stop)
    assert not (tmp_path/'interrupted.mp4').exists()
    assert not list(tmp_path.glob('.snapmark-export-*'))
    assert Path(clip.source).exists()

def test_dialog_shows_active_stored_phase_not_hidden_join_tab(app,project):
    from cpp.video.animation_dialog import AnimationDialog
    item=TimedAnnotation(Annotation('text',((20,20),),text='Hello'),0,3)
    item.animations.entrance=Animation('Typewriter',duration=2)
    project.annotations=[item]
    dialog=AnimationDialog(project,('annotation',item.id))
    assert dialog.tabs.currentIndex()==0
    assert dialog.panels['entrance'].kind.currentText()=='Typewriter'
    assert dialog.panels['entrance'].duration.value()==2
    dialog.reject();dialog.deleteLater()
    dialog=AnimationDialog(project,phase='exit')
    assert dialog.tabs.currentIndex()==2
    dialog.reject();dialog.deleteLater()

def test_border_pulse_does_not_recolor_shape_fill(app,project,frame):
    item=TimedAnnotation(Annotation('rectangle',((30,30),(130,90)),color='#ff0000',fill=True),0,3)
    item.animations.emphasis=defaults('emphasis','Border Pulse');project.annotations=[item]
    result=composite_frame(frame,project,.5,.5)
    center=result.pixelColor(80,60)
    assert center.red()>240 and center.green()<20

def test_reverse_typewriter_keeps_character_positions(app,project,frame):
    item=TimedAnnotation(Annotation('text',((20,20),),text='MMMMI',font_size=24,color='#ff0000'),0,3)
    item.animations.entrance=Animation('Typewriter',duration=1,easing='Linear',params={'character_order':'Reverse','cursor':False})
    project.annotations=[item]
    result=composite_frame(frame,project,.2,.2)
    xs=[x for y in range(20,65) for x in range(160) if result.pixelColor(x,y).red()>150 and result.pixelColor(x,y).green()<100]
    assert xs and min(xs)>80

def test_shortening_clips_keeps_animation_project_editable(project):
    project.segments=[(0,.1),(2,3)]
    project.video_animations.entrance=Animation('Fade In',delay=.5)
    history=History(project)
    history.edit(lambda p:p.segments.pop(1))
    assert history.project.output_duration==.1
    history.project.validate()

def test_join_identity_follows_the_actual_source_cut(project):
    project.segments=[(0,1),(2,3)]
    key=project.join_key(*project.segments)
    project.transitions[key]=Animation('Fade through color')
    project.split(.5)
    assert project.transition(2).kind=='Fade through color'
    assert project.transition(1).kind=='None'
    project.move_segment(2,0)
    assert not project.has_animations
