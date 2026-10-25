"""Bounded frame streaming: one decoded frame at a time, cancellable child processes."""
from pathlib import Path
import math
import os
import subprocess
import tempfile
import threading
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QImage,QPainter
from cpp.video import ffmpeg
from cpp.video.animation_render import composite_frame

class Processes:
    def __init__(self,cancelled):
        self.cancelled=cancelled
        self.done=threading.Event()
        self.lock=threading.Lock()
        self.children=[]
    def __enter__(self):
        self.thread=threading.Thread(target=self.watch,daemon=True)
        self.thread.start();return self
    def watch(self):
        while not self.done.wait(.05):
            if self.cancelled.is_set():
                with self.lock:
                    for p in self.children:
                        if p.poll() is None:
                            try:p.terminate()
                            except ProcessLookupError:pass
                return
    def spawn(self,args,**kwargs):
        if self.cancelled.is_set(): raise ffmpeg.Cancelled('Export cancelled. Source recording preserved.')
        p=subprocess.Popen([ffmpeg.binary('ffmpeg'),'-hide_banner','-loglevel','error','-nostdin',*map(str,args)],env=ffmpeg.system_environment(),**kwargs)
        with self.lock:self.children.append(p)
        if self.cancelled.is_set(): p.terminate()
        return p
    def __exit__(self,*exc):
        self.done.set();self.thread.join(1)
        for p in self.children:
            if p.poll() is None:
                p.terminate()
                try:p.wait(3)
                except subprocess.TimeoutExpired:p.kill();p.wait()
            for stream in (p.stdin,p.stdout):
                if stream:
                    try:stream.close()
                    except OSError:pass

def read_frame(stream,size):
    parts=[];remaining=size
    while remaining:
        data=stream.read(remaining)
        if not data:return None
        parts.append(data);remaining-=len(data)
    return b''.join(parts)

def audio_filter(project):
    n=len(project.segments);filters=[]
    if n>1:filters.append('[1:a]asplit='+str(n)+''.join(f'[a{i}]' for i in range(n)))
    for i,(a,b) in enumerate(project.segments):
        chain=f'[{"a"+str(i) if n>1 else "1:a"}]atrim=start={a:.9f}:end={b:.9f},asetpts=PTS-STARTPTS'
        if i>0 and project.join_half(i) and project.transition(i).values('join')['audio_fade']:
            chain+=f',afade=t=in:st=0:d={project.join_half(i):.9f}'
        if i+1<n and project.join_half(i+1) and project.transition(i+1).values('join')['audio_fade']:
            half=project.join_half(i+1);chain+=f',afade=t=out:st={b-a-half:.9f}:d={half:.9f}'
        filters.append(chain+f'[u{i}]')
    filters.append(''.join(f'[u{i}]' for i in range(n))+f'concat=n={n}:v=0:a=1[audio]')
    return ';'.join(filters)

def output_size(project,settings):
    w,h=project.crop[2:] if project.crop else (project.width,project.height)
    if settings.max_height and h>settings.max_height:
        w=max(1,math.floor(w*settings.max_height/h+.5));h=settings.max_height
    return w+(w%2),h+(h%2)

def render_export(project,target,settings,cancelled=None,progress=None):
    cancelled=cancelled or threading.Event()
    target=Path(target)
    fps=project.fps
    width,height=output_size(project,settings)
    with tempfile.TemporaryDirectory(prefix='.snapmark-export-',dir=target.parent) as temp, tempfile.TemporaryFile() as errors, Processes(cancelled) as children:
        output=Path(temp)/'output.mp4'
        args=['-y','-f','rawvideo','-pixel_format','rgba','-video_size',f'{width}x{height}','-framerate',f'{fps:.9f}','-i','pipe:0']
        if project.audio:args+=['-i',project.source,'-filter_complex',audio_filter(project),'-map','0:v','-map','[audio]','-c:a','aac','-b:a','160k']
        preset,crf=settings.encoder()
        args+=['-c:v','libx264','-preset',preset,'-crf',crf,'-pix_fmt','yuv420p','-t',f'{project.output_duration:.9f}','-movflags','+faststart',str(output)]
        encoder=children.spawn(args,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=errors)
        total=math.ceil(project.output_duration*fps-1e-8)
        try:
            for span in project.spans:
                first=math.ceil(span.start*fps-1e-8);last=math.ceil(span.end*fps-1e-8)
                if last<=first:continue
                start=span.source_start+first/fps-span.start
                decoder=children.spawn(['-ss',f'{start:.9f}','-i',project.source,'-an','-vf',f'fps={fps:.9f},tpad=stop_mode=clone:stop_duration=1','-frames:v',str(last-first),'-f','rawvideo','-pix_fmt','rgba','pipe:1'],stdout=subprocess.PIPE,stderr=errors)
                for index in range(first,last):
                    if cancelled.is_set():raise ffmpeg.Cancelled('Export cancelled. Source recording preserved.')
                    raw=read_frame(decoder.stdout,project.width*project.height*4)
                    if raw is None:raise RuntimeError('Video decoder ended before the requested clip was complete.')
                    frame=QImage(raw,project.width,project.height,project.width*4,QImage.Format.Format_RGBA8888).copy()
                    t=index/fps;source=span.source_start+t-span.start
                    frame=composite_frame(frame,project,source,t)
                    if project.crop:frame=frame.copy(*project.crop)
                    if settings.max_height and frame.height()>settings.max_height:
                        frame=frame.scaledToHeight(settings.max_height,Qt.TransformationMode.SmoothTransformation)
                    result=QImage(width,height,QImage.Format.Format_RGBA8888);result.fill(QColor('black'))
                    painter=QPainter(result);painter.drawImage(0,0,frame);painter.end()
                    encoder.stdin.write(bytes(result.constBits()))
                    if progress:progress(min(99,round((index+1)/max(1,total)*99)))
                decoder.stdout.close()
                if decoder.wait()!=0:raise RuntimeError('Video decoding failed.')
            encoder.stdin.close()
            if encoder.wait()!=0:raise RuntimeError('Video encoding failed.')
            if cancelled.is_set():raise ffmpeg.Cancelled('Export cancelled. Source recording preserved.')
            os.link(output,target)
            if progress:progress(100)
        except Exception as exc:
            if cancelled.is_set():raise ffmpeg.Cancelled('Export cancelled. Source recording preserved.') from exc
            errors.seek(0,2);errors.seek(max(0,errors.tell()-2500))
            detail=errors.read().decode(errors='replace')
            raise RuntimeError(str(exc)+('\n'+detail if detail else '')) from exc
    return str(target)
