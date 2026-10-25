"""Typed animation catalog, applicability and deterministic time sampling."""
from dataclasses import dataclass,field
import math
from PySide6.QtGui import QColor

@dataclass(frozen=True)
class Property:
    label:str
    default:object
    minimum:float=0
    maximum:float=100
    choices:tuple=()
    suffix:str=''

def number(label,default,lo=0,hi=100,suffix=''):
    return Property(label,default,lo,hi,suffix=suffix)
def choice(label,default,values):
    return Property(label,default,choices=tuple(values))
def color(label,default):
    return Property(label,default)

DIRECTIONS=('Left','Right','Top','Bottom')
EASINGS=('Linear','Ease In','Ease Out','Ease In Out')
CATALOG={p:{'None':{}} for p in ('entrance','emphasis','exit','join')}
def add(phase,name,**properties):
    CATALOG[phase][name]=properties
add('entrance','Fade In',opacity_start=number('Starting opacity',0,0,1))
add('entrance','Zoom In',start_scale=number('Start scale',0,0,5),end_scale=number('End scale',1,.01,5))
add('entrance','Pop In',start_scale=number('Start scale',0,0,5),overshoot=number('Overshoot intensity',1.7,0,5))
for direction,axis,offset in [('Left','x',-180),('Right','x',180),('Top','y',-180),('Bottom','y',180)]:
    add('entrance','Slide In '+direction,**{axis+'_offset':number('Start '+axis.upper()+' offset',offset,-16384,16384,' px')})
add('entrance','Wipe In',direction=choice('Direction','Left',DIRECTIONS))
add('entrance','Draw On',direction=choice('Drawing direction','Forward',('Forward','Reverse')),reveal_speed=number('Stroke reveal speed',1,.1,10,'×'))
add('entrance','Sweep In',direction=choice('Direction','Left',DIRECTIONS),sweep_width=number('Sweep width',25,1,100,' %'))
add('entrance','Typewriter',timing_mode=choice('Timing mode','Duration',('Duration','Typing speed')),character_order=choice('Character order','Forward',('Forward','Reverse')),typing_speed=number('Typing speed',20,1,200,' chars/s'),cursor=Property('Show typing cursor',True))
add('entrance','Blur In',blur=number('Starting blur',20,0,100,' px'))
add('entrance','Rotate In',start_angle=number('Start angle',-90,-720,720,'°'),end_angle=number('End angle',0,-720,720,'°'))
add('exit','Fade Out',opacity_end=number('Ending opacity',0,0,1))
add('exit','Zoom Out',start_scale=number('Start scale',1,0,5),end_scale=number('End scale',0,0,5))
add('exit','Shrink',min_scale=number('Minimum scale',0,0,1),anchor=choice('Anchor','Center',('Center','Top left','Top right','Bottom left','Bottom right')))
for direction,axis,offset in [('Left','x',-180),('Right','x',180),('Top','y',-180),('Bottom','y',180)]:
    add('exit','Slide Out '+direction,**{axis+'_offset':number('End '+axis.upper()+' offset',offset,-16384,16384,' px')})
add('exit','Wipe Out',direction=choice('Direction','Left',DIRECTIONS))
add('exit','Dissolve',particle_size=number('Particle size',8,1,128,' px'),direction=choice('Dissolve direction','Random',('Random',*DIRECTIONS)))
add('exit','Draw Erase',direction=choice('Erasing direction','Forward',('Forward','Reverse')),reveal_speed=number('Erase speed',1,.1,10,'×'))
add('exit','Blur Out',blur=number('Ending blur',20,0,100,' px'))
add('exit','Rotate Out',start_angle=number('Start angle',0,-720,720,'°'),end_angle=number('End angle',90,-720,720,'°'))
add('exit','Pop Out',end_scale=number('End scale',0,0,5),overshoot=number('Overshoot intensity',1.7,0,5))
for name in ('Pulse','Zoom In/Out'):
    add('emphasis',name,speed=number('Speed',1,.05,20,' Hz'),min_scale=number('Minimum scale',1,.01,5),max_scale=number('Maximum scale',1.15,.01,5))
add('emphasis','Shake',intensity=number('Intensity',8,0,200,' px'),speed=number('Speed',2,.05,20,' Hz'),direction=choice('Direction','Both',('Horizontal','Vertical','Both')))
add('emphasis','Bounce',height=number('Height',20,0,500,' px'),speed=number('Speed',1,.05,20,' Hz'),bounce_count=number('Bounce count',3,1,20))
add('emphasis','Glow',glow_color=color('Glow color','#ffe14a'),min_intensity=number('Minimum intensity',.1,0,1),max_intensity=number('Maximum intensity',1,0,1),speed=number('Speed',1,.05,20,' Hz'))
add('emphasis','Flash',flash_color=color('Flash color','#ffffff'),frequency=number('Flash frequency',2,.05,20,' Hz'),intensity=number('Intensity',1,0,1))
add('emphasis','Breathing',min_opacity=number('Minimum opacity',.3,0,1),max_opacity=number('Maximum opacity',1,0,1),speed=number('Speed',.5,.05,20,' Hz'))
add('emphasis','Blink',frequency=number('Blink frequency',2,.05,20,' Hz'),min_opacity=number('Minimum opacity',0,0,1))
add('emphasis','Floating',distance=number('Movement distance',15,0,500,' px'),direction=choice('Direction','Vertical',('Horizontal','Vertical','Diagonal')),speed=number('Speed',.5,.05,20,' Hz'))
add('emphasis','Continuous Highlight',highlight_color=color('Highlight color','#ffe14a'),intensity=number('Intensity',.8,0,1),speed=number('Pulse speed',1,.05,20,' Hz'))
add('emphasis','Rotate',angle=number('Rotation angle',360,0,1440,'°'),direction=choice('Direction','Clockwise',('Clockwise','Counterclockwise')),speed=number('Speed',.5,.05,20,' Hz'))
add('emphasis','Wobble',angle=number('Rotation angle',12,0,180,'°'),speed=number('Speed',1,.05,20,' Hz'),intensity=number('Intensity',1,0,1))
add('emphasis','Border Pulse',border_color=color('Border color','#ffe14a'),min_width=number('Minimum width',2,.1,100,' px'),max_width=number('Maximum width',10,.1,100,' px'),speed=number('Speed',1,.05,20,' Hz'))
add('emphasis','Blur Pulse',min_blur=number('Minimum blur',0,0,100,' px'),max_blur=number('Maximum blur',12,0,100,' px'),speed=number('Speed',1,.05,20,' Hz'))
add('emphasis','Color Change',start_color=color('Start color','#e95420'),end_color=color('End color','#ffe14a'),speed=number('Transition speed',.5,.05,20,' Hz'))
for name in ('Fade through color','Wipe through color','Blur through color','Zoom through color','Dissolve through color'):
    props={'color':color('Join color','#000000'),'audio_fade':Property('Fade audio at the join',True)}
    if name=='Wipe through color': props['direction']=choice('Direction','Left',DIRECTIONS)
    if name=='Blur through color': props['blur']=number('Blur strength',20,0,100,' px')
    if name=='Zoom through color': props['min_scale']=number('Minimum scale',.6,.01,1)
    if name=='Dissolve through color': props['particle_size']=number('Particle size',12,1,128,' px')
    add('join',name,**props)

@dataclass
class Animation:
    kind:str='None'
    duration:float=.6
    delay:float=0
    easing:str='Ease Out'
    repeat:bool=False
    repeat_count:int=1
    reverse:bool=False
    alternate:bool=False
    start:float|None=None
    end:float|None=None
    params:dict=field(default_factory=dict)

    def values(self,phase):
        return {k:self.params.get(k,p.default) for k,p in CATALOG[phase][self.kind].items()}

    def validate(self,phase,context='annotation',drawing_kind='pen'):
        if any(type(v) is not bool for v in (self.repeat,self.reverse,self.alternate)) or not isinstance(self.params,dict):
            raise ValueError('Invalid animation flags/properties.')
        if self.kind not in available(phase,context,drawing_kind):
            raise ValueError(f'{self.kind} is not applicable to this {context}.')
        for value in (self.duration,self.delay):
            if not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=36000:
                raise ValueError('Invalid animation duration/delay.')
        if phase!='emphasis' and self.repeat and self.repeat_count==0:raise ValueError('Entrance and exit repeats need a finite count.')
        if self.duration<.01 or self.easing not in EASINGS or type(self.repeat_count) is not int or not 0<=self.repeat_count<=100:
            raise ValueError('Invalid animation timing or repeat count.')
        for value in (self.start,self.end):
            if value is not None and (not isinstance(value,(int,float)) or not math.isfinite(value) or value<0):
                raise ValueError('Invalid animation time range.')
        if self.start is not None and self.end is not None and self.start>=self.end:
            raise ValueError('Animation start must precede its end.')
        definitions=CATALOG[phase][self.kind]
        if set(self.params)-set(definitions): raise ValueError('Unknown animation property.')
        for key,value in self.values(phase).items():
            prop=definitions[key]
            if prop.choices:
                valid=value in prop.choices
            elif type(prop.default) is bool:
                valid=type(value) is bool
            elif isinstance(prop.default,str):
                valid=isinstance(value,str) and QColor(value).isValid()
            else:
                valid=isinstance(value,(int,float)) and math.isfinite(value) and prop.minimum<=value<=prop.maximum
            if not valid: raise ValueError('Invalid animation property: '+prop.label)
        values=self.values(phase)
        for lo,hi in (('min_scale','max_scale'),('min_intensity','max_intensity'),('min_opacity','max_opacity'),('min_width','max_width'),('min_blur','max_blur')):
            if lo in values and hi in values and values[lo]>values[hi]: raise ValueError('Minimum must not exceed maximum.')

@dataclass
class Animations:
    entrance:Animation=field(default_factory=Animation)
    emphasis:Animation=field(default_factory=Animation)
    exit:Animation=field(default_factory=Animation)
    @property
    def enabled(self):
        return any(getattr(self,p).kind!='None' for p in ('entrance','emphasis','exit'))
    def validate(self,context='annotation',drawing_kind='pen',length=None):
        for phase in ('entrance','emphasis','exit'):
            spec=getattr(self,phase)
            spec.validate(phase,context,drawing_kind)
    @classmethod
    def load(cls,data):
        return cls(**{phase:Animation(**value) for phase,value in data.items()})


def available(phase,context='annotation',drawing_kind='pen'):
    names=list(CATALOG[phase])
    if context=='join': return list(CATALOG['join']) if phase=='join' else ['None']
    if context=='video':
        return [n for n in names if n not in ('Draw On','Draw Erase','Typewriter')] if phase!='emphasis' else ['None']
    if drawing_kind in ('blur','pixelate'): return ['None']
    if drawing_kind!='text': names=[n for n in names if n!='Typewriter']
    if drawing_kind not in ('pen','highlighter','arrow','rectangle','ellipse'): names=[n for n in names if n not in ('Draw On','Draw Erase')]
    if drawing_kind not in ('rectangle','ellipse'): names=[n for n in names if n!='Border Pulse']
    return names

def defaults(phase,kind):
    return Animation(kind=kind,repeat=phase=='emphasis',repeat_count=0 if phase=='emphasis' else 1,easing='Linear' if kind=='Typewriter' else 'Ease In Out' if phase=='emphasis' else 'Ease Out')

def ease(p,name):
    p=max(0,min(1,p))
    return p**3 if name=='Ease In' else 1-(1-p)**3 if name=='Ease Out' else (4*p**3 if p<.5 else 1-(-2*p+2)**3/2) if name=='Ease In Out' else p

def cycle_duration(spec,phase,text=''):
    v=spec.values(phase)
    if phase=='emphasis': return 1/v.get('speed',v.get('frequency',1))
    if spec.kind=='Typewriter' and v['timing_mode']=='Typing speed': return max(.01,len(text)/v['typing_speed'])
    return spec.duration/v.get('reveal_speed',1)

def window(spec,phase,length,text=''):
    cycle=cycle_duration(spec,phase,text)
    count=spec.repeat_count if spec.repeat and spec.repeat_count else 1
    a=spec.start if spec.start is not None else max(0,length-cycle*count) if phase=='exit' else 0
    b=spec.end if spec.end is not None else length if phase in ('exit','emphasis') else min(length,a+spec.delay+cycle*count)
    return min(length,a+spec.delay),min(length,b),cycle

def progress(spec,phase,t,length,text=''):
    if spec.kind=='None': return None
    a,b,cycle=window(spec,phase,length,text)
    if b<=a: return None
    if t<a: return (-1,0) if phase=='entrance' else None
    if t>=b:
        if phase=='emphasis': return None
        p=1
        if spec.repeat and spec.alternate and max(1,spec.repeat_count)%2==0: p=0
        return (1-p if spec.reverse else p,cycle)
    elapsed=t-a
    cycle=cycle if phase=='emphasis' else min(cycle,b-a)
    if phase=='emphasis' and not spec.repeat and elapsed>=cycle: return None
    if phase=='emphasis' and spec.repeat and spec.repeat_count and elapsed>=cycle*spec.repeat_count: return None
    index=int(elapsed/cycle) if spec.repeat else 0
    p=(elapsed%cycle)/cycle if spec.repeat else min(1,elapsed/cycle)
    if spec.alternate and index%2: p=1-p
    if spec.reverse: p=1-p
    return ease(p,spec.easing),p*cycle_duration(spec,phase,text)
