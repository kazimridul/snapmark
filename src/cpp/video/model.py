"""Versioned, frame-coordinate editing state independent of playback and capture."""
from dataclasses import asdict, dataclass, field
from pathlib import Path
import copy
import json
import math
import os
import tempfile
import uuid
from cpp.editor.model import Annotation
from cpp.video.animations import Animation, Animations

KINDS = {'pen', 'highlighter', 'highlight_rect', 'arrow', 'rectangle', 'ellipse', 'text', 'blur', 'pixelate'}

@dataclass
class TimedAnnotation:
    drawing: Annotation
    start: float
    end: float
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    strength: int = 20
    animations: Animations = field(default_factory=Animations)

    def active(self, seconds):
        return self.start <= seconds < self.end

@dataclass(frozen=True)
class ClipSpan:
    index: int
    start: float
    end: float
    source_start: float
    source_end: float

@dataclass
class Project:
    source: str
    duration: float
    width: int
    height: int
    fps: float = 30
    audio: bool = False
    segments: list = field(default_factory=list)
    crop: tuple | None = None
    annotations: list[TimedAnnotation] = field(default_factory=list)
    video_animations: Animations = field(default_factory=Animations)
    transitions: dict[str,Animation] = field(default_factory=dict)

    def __post_init__(self):
        if not self.segments:
            self.segments = [(0., self.duration)]
        self.validate()

    @property
    def output_duration(self):
        return sum(b-a for a, b in self.segments)

    @staticmethod
    def join_key(left,right):
        return f'{left[1]:.12g}>{right[0]:.12g}'

    def transition(self,index):
        return self.transitions.get(self.join_key(self.segments[index-1],self.segments[index]),Animation()) if index>0 else Animation()

    def join_half(self,index):
        spec=self.transition(index)
        return min(spec.duration/2,(self.segments[index-1][1]-self.segments[index-1][0])/2,(self.segments[index][1]-self.segments[index][0])/2) if spec.kind!='None' else 0

    @property
    def has_animations(self):
        return self.video_animations.enabled or any(a.animations.enabled for a in self.annotations) or any(self.transition(i).kind!='None' for i in range(1,len(self.segments)))

    def join_audio_gain(self,seconds):
        gain=1.
        for span in self.spans[1:]:
            spec=self.transition(span.index)
            half=self.join_half(span.index)
            if half and spec.values('join')['audio_fade'] and abs(seconds-span.start)<half:
                gain=min(gain,abs(seconds-span.start)/half)
        return gain

    def validate(self):
        self.video_animations.validate('video')
        for key,spec in self.transitions.items():
            if not isinstance(key,str) or len(key)>100: raise ValueError('Invalid transition key.')
            try:
                ends=[float(value) for value in key.split('>')]
                if len(ends)!=2 or any(not math.isfinite(v) or v<0 or v>self.duration+.001 for v in ends):raise ValueError()
            except (ValueError,TypeError):raise ValueError('Invalid transition cut positions.')
            spec.validate('join','join')
        if not math.isfinite(self.duration) or self.duration <= 0 or not 0 < self.fps <= 240:
            raise ValueError('Invalid video duration or frame rate.')
        if not 0 < self.width <= 16384 or not 0 < self.height <= 16384:
            raise ValueError('Invalid video dimensions.')
        if not self.segments:
            raise ValueError('Keep at least one video segment.')
        for a, b in self.segments:
            if not (math.isfinite(a) and math.isfinite(b) and 0 <= a < b <= self.duration + .001):
                raise ValueError('Segments must be inside the source video.')
        ordered=sorted(self.segments)
        if any(left[1]>right[0]+1e-7 for left,right in zip(ordered,ordered[1:])):
            raise ValueError('Source segments must not overlap.')
        self.video_animations.validate('video',length=self.output_duration)
        if self.crop:
            x, y, w, h = self.crop
            if any(type(v) is not int for v in self.crop) or x < 0 or y < 0 or w < 2 or h < 2 or x+w > self.width or y+h > self.height:
                raise ValueError('Crop must fit inside the original video frame.')
        ids = set()
        for item in self.annotations:
            a = item.drawing
            item.animations.validate('annotation',a.kind,item.end-item.start)
            if item.id in ids or not item.id or a.kind not in KINDS:
                raise ValueError('Invalid or duplicate annotation.')
            ids.add(item.id)
            if not 0 <= item.start < item.end <= self.duration + .001:
                raise ValueError('Annotation time range is outside the source.')
            if not a.points or len(a.points) > 100000 or any(not (math.isfinite(x) and math.isfinite(y) and 0 <= x <= self.width and 0 <= y <= self.height) for x, y in a.points):
                raise ValueError('Annotation coordinates must use source-frame pixels.')
            if not 0 <= a.opacity <= 1 or not 0 < a.width <= 500 or not 1 <= a.font_size <= 1000 or not 2 <= item.strength <= 100:
                raise ValueError('Invalid annotation style.')

    @property
    def spans(self):
        cursor=0.
        spans=[]
        for i,(a,b) in enumerate(self.segments):
            spans.append(ClipSpan(i,cursor,cursor+b-a,a,b))
            cursor+=b-a
        return spans

    def source_at(self, seconds):
        """Map a ripple-closed edited timeline position to source media time."""
        if not math.isfinite(seconds):
            raise ValueError('Invalid timeline position.')
        t=max(0,min(seconds,self.output_duration))
        spans=self.spans
        for span in spans:
            if t<span.end-1e-9:
                return span.index,span.source_start+t-span.start
        return spans[-1].index,spans[-1].source_end

    def timeline_at(self, source, index=None):
        for span in self.spans:
            if (index is None or index==span.index) and span.source_start<=source<=span.source_end:
                return span.start+source-span.source_start
        raise ValueError('This source position was removed from the sequence.')

    def annotation_spans(self, item):
        """Annotations stay attached to their source footage through cuts/moves."""
        result=[]
        for span in self.spans:
            a,b=max(item.start,span.source_start),min(item.end,span.source_end)
            if a<b:
                result.append((span.index,span.start+a-span.source_start,span.start+b-span.source_start))
        return result

    def move_segment(self, source, destination):
        if not 0<=source<len(self.segments) or not 0<=destination<len(self.segments):
            raise ValueError('Invalid clip position.')
        self.segments.insert(destination,self.segments.pop(source))

    def split_timeline(self, seconds):
        _,source=self.source_at(seconds)
        self.split(source)

    def trim_timeline(self, start, end):
        kept=[]
        for span in self.spans:
            a,b=max(start,span.start),min(end,span.end)
            if a<b:
                kept.append((span.source_start+a-span.start,span.source_start+b-span.start))
        if not kept:
            raise ValueError('The trim range must include a kept segment.')
        self.segments=kept
        self.validate()

    def split(self, seconds):
        for i, (a, b) in enumerate(self.segments):
            if a + 1/self.fps <= seconds <= b - 1/self.fps:
                self.segments[i:i+1] = [(a, seconds), (seconds, b)]
                return
        raise ValueError('Place the playhead inside a kept segment, at least one frame from its edges.')

    def trim(self, start, end):
        segments = [(max(a, start), min(b, end)) for a, b in self.segments if max(a, start) < min(b, end)]
        if not segments:
            raise ValueError('The trim range must include a kept segment.')
        self.segments = segments
        self.validate()

    def save(self, path):
        self.validate()
        target = Path(path).resolve()
        if target == Path(self.source).resolve():
            raise ValueError('A project cannot overwrite its source video.')
        if target.suffix.lower() != '.json':
            raise ValueError('Save editable projects with a .json extension.')
        data = {'version': 2, **asdict(self)}
        data['source'] = os.path.relpath(Path(self.source).resolve(), target.parent)
        fd, name = tempfile.mkstemp(prefix='.snapmark-project-', dir=target.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(data, stream, indent=2, allow_nan=False)
            os.replace(name, target)
        finally:
            Path(name).unlink(missing_ok=True)

    @classmethod
    def load(cls, path):
        path = Path(path).resolve()
        if path.stat().st_size > 20_000_000:
            raise ValueError('Project file is too large.')
        data = json.loads(path.read_text())
        if data.pop('version', None) not in (1,2):
            raise ValueError('Unsupported SnapMark video project version.')
        source = Path(data['source'])
        source = source if source.is_absolute() else path.parent / source
        if not source.is_file():
            raise ValueError('Source video is missing: ' + str(source))
        data['source'] = str(source.resolve())
        annotations = []
        for item in data.pop('annotations', []):
            item['animations']=Animations.load(item.pop('animations',{}))
            drawing = item.pop('drawing')
            drawing['points'] = tuple(tuple(p) for p in drawing['points'])
            annotations.append(TimedAnnotation(Annotation(**drawing), **item))
        if not data.get('segments'):
            raise ValueError('Project has no video segments.')
        data['video_animations']=Animations.load(data.pop('video_animations',{}))
        data['transitions']={k:Animation(**v) for k,v in data.pop('transitions',{}).items()}
        return cls(**data, annotations=annotations)

class History:
    """Bounded snapshots; source media is never copied into undo history."""
    def __init__(self, project):
        self.project = project
        self.past, self.future = [], []

    def edit(self, function):
        before = copy.deepcopy(self.project)
        try:
            function(self.project)
            self.project.validate()
        except Exception:
            self.project = before
            raise
        if self.project == before:
            return False
        self.past.append(before)
        self.past = self.past[-100:]
        self.future.clear()
        return True

    def undo(self):
        if self.past:
            self.future.append(copy.deepcopy(self.project))
            self.project = self.past.pop()

    def redo(self):
        if self.future:
            self.past.append(copy.deepcopy(self.project))
            self.project = self.future.pop()
