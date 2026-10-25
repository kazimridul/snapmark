"""Shared deterministic QImage compositor for playback and animated exports."""
from dataclasses import replace
from functools import lru_cache
import math
import random
from PIL import Image,ImageChops,ImageFilter
from PySide6.QtCore import QPointF,QRectF,Qt
from PySide6.QtGui import QColor,QFont,QFontMetricsF,QImage,QLinearGradient,QPainter,QTransform
from cpp.editor.model import paint_annotation
from cpp.video.animations import ease,progress


def pil(image):
    image=image.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombytes('RGBA',(image.width(),image.height()),bytes(image.constBits()),'raw','RGBA',image.bytesPerLine())

def qt(image):
    raw=image.tobytes()
    return QImage(raw,image.width,image.height,image.width*4,QImage.Format.Format_RGBA8888).copy()

def mix_color(a,b,p):
    a,b=QColor(a),QColor(b)
    return QColor(*(round(x+(y-x)*p) for x,y in zip(a.getRgb(),b.getRgb()))).name(QColor.NameFormat.HexArgb)

def state_for(animations,t,length,text=''):
    state=dict(opacity=1.,scale=1.,angle=0.,dx=0.,dy=0.,anchor='Center',reveal=1.,direction='Left',feather=0.,path_start=0.,path_end=1.,text=1.,cursor=False,blur=0.,glow=0.,glow_color='#ffffff',color=None,color_mix=1.,width=None,border_only=False,dissolve=False,particle_size=8)
    for phase in ('entrance','emphasis','exit'):
        spec=getattr(animations,phase)
        sample=progress(spec,phase,t,length,text)
        if sample is None: continue
        p,cycle_time=sample
        if p<0:
            state['opacity']=0
            continue
        v=spec.values(phase)
        name=spec.kind
        wave=(1-math.cos(2*math.pi*p))/2
        if name=='Fade In': state['opacity']*=v['opacity_start']+(1-v['opacity_start'])*p
        elif name=='Fade Out': state['opacity']*=1+(v['opacity_end']-1)*p
        elif name in ('Zoom In','Zoom Out'): state['scale']*=v['start_scale']+(v['end_scale']-v['start_scale'])*p
        elif name=='Pop In':
            c=v['overshoot']; back=1+(c+1)*(p-1)**3+c*(p-1)**2
            state['scale']*=v['start_scale']+(1-v['start_scale'])*back
        elif name=='Pop Out':
            c=v['overshoot']; back=(c+1)*p**3-c*p**2
            state['scale']*=1+(v['end_scale']-1)*back
        elif name=='Shrink': state.update(scale=state['scale']*(1+(v['min_scale']-1)*p),anchor=v['anchor'])
        elif name.startswith('Slide '):
            amount=1-p if phase=='entrance' else p
            state['dx']+=v.get('x_offset',0)*amount
            state['dy']+=v.get('y_offset',0)*amount
        elif name in ('Wipe In','Wipe Out','Sweep In'):
            state.update(reveal=min(state['reveal'],p if phase=='entrance' else 1-p),direction=v['direction'],feather=v.get('sweep_width',0)/100)
        elif name in ('Draw On','Draw Erase'):
            reverse=v['direction']=='Reverse'
            if name=='Draw On': state['path_start'],state['path_end']=(1-p,1) if reverse else (0,p)
            else: state['path_start'],state['path_end']=(0,1-p) if reverse else (p,1)
        elif name=='Typewriter':
            state['text']=p
            state['text_reverse']=v['character_order']=='Reverse'
            state['cursor']=v['cursor'] and state['text']<1 and int(t*2)%2==0
        elif name in ('Blur In','Blur Out'):
            state['blur']+=v['blur']*((1-p) if phase=='entrance' else p)
            state['opacity']*=p if phase=='entrance' else 1-p
        elif name in ('Rotate In','Rotate Out'):
            state['angle']+=v['start_angle']+(v['end_angle']-v['start_angle'])*p
            state['opacity']*=p if phase=='entrance' else 1-p
        elif name=='Dissolve': state.update(reveal=1-p,dissolve=True,particle_size=v['particle_size'],direction=v['direction'])
        elif name=='Pulse': state['scale']*=v['min_scale']+(v['max_scale']-v['min_scale'])*wave
        elif name=='Zoom In/Out': state['scale']*=v['min_scale']+(v['max_scale']-v['min_scale'])*(1-abs(2*p-1))
        elif name=='Shake':
            if v['direction'] in ('Horizontal','Both'): state['dx']+=v['intensity']*math.sin(p*math.pi*6)
            if v['direction'] in ('Vertical','Both'): state['dy']+=v['intensity']*math.sin(p*math.pi*10)
        elif name=='Bounce': state['dy']-=v['height']*abs(math.sin(math.pi*p*v['bounce_count']))
        elif name=='Glow': state.update(glow=v['min_intensity']+(v['max_intensity']-v['min_intensity'])*wave,glow_color=v['glow_color'])
        elif name=='Flash': state.update(color=v['flash_color'],color_mix=v['intensity'] if p<.5 else 0)
        elif name=='Breathing': state['opacity']*=v['min_opacity']+(v['max_opacity']-v['min_opacity'])*wave
        elif name=='Blink': state['opacity']*=1 if p<.5 else v['min_opacity']
        elif name=='Floating':
            amount=v['distance']*math.sin(2*math.pi*p)
            if v['direction'] in ('Horizontal','Diagonal'): state['dx']+=amount
            if v['direction'] in ('Vertical','Diagonal'): state['dy']+=amount
        elif name=='Rotate': state['angle']+=v['angle']*p*(1 if v['direction']=='Clockwise' else -1)
        elif name=='Wobble': state['angle']+=v['angle']*v['intensity']*math.sin(2*math.pi*p)
        elif name=='Border Pulse': state.update(border_only=True,color=v['border_color'],width=v['min_width']+(v['max_width']-v['min_width'])*wave)
        elif name=='Blur Pulse': state['blur']+=v['min_blur']+(v['max_blur']-v['min_blur'])*wave
        elif name=='Color Change': state['color']=mix_color(v['start_color'],v['end_color'],p)
        elif name=='Continuous Highlight': state.update(color=v['highlight_color'],glow=v['intensity']*(.25+.75*wave),glow_color=v['highlight_color'])
    return state

def partial_path(drawing,start,end):
    if start<=0 and end>=1: return drawing
    points=list(drawing.points)
    a,b=points[0],points[-1]
    x0,x1=sorted((a[0],b[0]));y0,y1=sorted((a[1],b[1]))
    if drawing.kind=='rectangle': points=[(x0,y0),(x1,y0),(x1,y1),(x0,y1),(x0,y0)]
    elif drawing.kind=='ellipse': points=[((x0+x1)/2+(x1-x0)/2*math.cos(i*2*math.pi/96),(y0+y1)/2+(y1-y0)/2*math.sin(i*2*math.pi/96)) for i in range(97)]
    lengths=[math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(points,points[1:])]
    total=sum(lengths)
    if not total:
        return drawing if end>start else None
    low,high=start*total,end*total
    output=[];cursor=0
    for a,b,length in zip(points,points[1:],lengths):
        left,right=max(low,cursor),min(high,cursor+length)
        if length and right>left:
            for distance in (left,right):
                t=(distance-cursor)/length
                point=(a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t)
                if not output or output[-1]!=point: output.append(point)
        cursor+=length
    return replace(drawing,kind='arrow' if drawing.kind=='arrow' and end>=1 else 'pen',points=tuple(output),fill=False) if output else None

@lru_cache(maxsize=32)
def noise_grid(w,h,seed,direction):
    rng=random.Random(seed)
    data=Image.frombytes('L',(w,h),bytes(rng.randrange(256) for _ in range(w*h)))
    if direction!='Random':
        gradient=Image.linear_gradient('L').resize((w,h))
        if direction in ('Left','Right'): gradient=Image.linear_gradient('L').rotate(90,expand=True).resize((w,h))
        if direction in ('Right','Bottom'): gradient=ImageChops.invert(gradient)
        data=ImageChops.add(data.point(lambda x:int(x*.4)),gradient.point(lambda x:int(x*.6)))
    return data

def mask_layer(image,fraction,direction,feather=0,dissolve=False,particle_size=8,seed=1):
    if fraction>=1: return image
    if fraction<=0:
        empty=QImage(image.size(),QImage.Format.Format_ARGB32_Premultiplied);empty.fill(Qt.GlobalColor.transparent);return empty
    if dissolve:
        area=pil(image)
        block=max(1,int(particle_size));w=math.ceil(area.width/block);h=math.ceil(area.height/block)
        mask=noise_grid(w,h,seed,direction).point(lambda x:255 if x<fraction*256 else 0).resize(area.size,Image.Resampling.NEAREST)
        area.putalpha(ImageChops.multiply(area.getchannel('A'),mask))
        return qt(area)
    output=QImage(image.size(),QImage.Format.Format_ARGB32_Premultiplied)
    output.fill(Qt.GlobalColor.transparent)
    p=QPainter(output)
    w,h=image.width(),image.height()
    if not feather:
        r=QRectF(0,0,w*fraction,h) if direction=='Left' else QRectF(w*(1-fraction),0,w*fraction,h) if direction=='Right' else QRectF(0,0,w,h*fraction) if direction=='Top' else QRectF(0,h*(1-fraction),w,h*fraction)
        p.setClipRect(r);p.drawImage(0,0,image)
    else:
        p.drawImage(0,0,image)
        edge=fraction*(1+feather);a=edge-feather;b=edge
        first,last=(QPointF(a*w,0),QPointF(b*w,0)) if direction=='Left' else (QPointF((1-a)*w,0),QPointF((1-b)*w,0)) if direction=='Right' else (QPointF(0,a*h),QPointF(0,b*h)) if direction=='Top' else (QPointF(0,(1-a)*h),QPointF(0,(1-b)*h))
        gradient=QLinearGradient(first,last)
        gradient.setColorAt(0,QColor(255,255,255,255));gradient.setColorAt(1,QColor(255,255,255,0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        p.fillRect(output.rect(),gradient)
    p.end();return output


def effects(image,state,seed=1):
    image=mask_layer(image,state['reveal'],state['direction'],state['feather'],state['dissolve'],state['particle_size'],seed)
    if state['blur']>.01:
        premult=image.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
        area=Image.frombytes('RGBA',(premult.width(),premult.height()),bytes(premult.constBits()),'raw','RGBA',premult.bytesPerLine()).filter(ImageFilter.GaussianBlur(state['blur']))
        raw=area.tobytes();image=QImage(raw,area.width,area.height,area.width*4,QImage.Format.Format_RGBA8888_Premultiplied).copy()
    if state['glow']>.001:
        original=pil(image);alpha=original.getchannel('A')
        color=QColor(state['glow_color'])
        glow=Image.new('RGBA',original.size,color.getRgb())
        glow.putalpha(alpha.point(lambda x:int(x*state['glow'])))
        glow=glow.filter(ImageFilter.GaussianBlur(12))
        glow.alpha_composite(original);image=qt(glow)
    return image

@lru_cache(maxsize=64)
def raster(drawing,padding=48):
    bounds=drawing.bounds().adjusted(-padding,-padding,padding,padding).toAlignedRect()
    image=QImage(max(1,bounds.width()),max(1,bounds.height()),QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p=QPainter(image);p.translate(-bounds.x(),-bounds.y());paint_annotation(p,drawing);p.end()
    return image,bounds

def anchor(rect,name):
    return rect.topLeft() if name=='Top left' else rect.topRight() if name=='Top right' else rect.bottomLeft() if name=='Bottom left' else rect.bottomRight() if name=='Bottom right' else rect.center()

def paint_animated(painter,item,seconds):
    a=item.drawing
    state=state_for(item.animations,seconds-item.start,item.end-item.start,a.text)
    if state['opacity']<=0 or state['scale']<=0: return
    if state['color'] is not None: a=replace(a,color=mix_color(a.color,state['color'],state['color_mix']))
    if state['width'] is not None: a=replace(a,width=state['width'])
    if state['border_only']:a=replace(a,fill=False)
    a=partial_path(a,state['path_start'],state['path_end'])
    if a is None: return
    # Rasterize in a fixed full-object rectangle so text/path reveal does not drift.
    padding=max(48,math.ceil((state['width'] or 0)*1.5),math.ceil(max((spec.params.get('blur',spec.params.get('max_blur',0)) for spec in (item.animations.entrance,item.animations.emphasis,item.animations.exit)),default=0)*3))
    bounds=item.drawing.bounds().adjusted(-padding,-padding,padding,padding).toAlignedRect()
    typed=a.kind=='text' and (state['text']<1 or state['cursor'])
    if a==item.drawing and not typed: image,_=raster(a,padding)
    else:
        image=QImage(bounds.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(Qt.GlobalColor.transparent)
        p=QPainter(image);p.translate(-bounds.x(),-bounds.y())
        if state['border_only'] and item.drawing.fill:
            p.save();p.setOpacity(item.drawing.opacity);p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(item.drawing.color))
            r=QRectF(QPointF(*a.points[0]),QPointF(*a.points[-1])).normalized()
            p.drawEllipse(r) if a.kind=='ellipse' else p.drawRect(r)
            p.restore()
        paint_typed(p,a,state) if typed else paint_annotation(p,a)
        p.end()
    image=effects(image,state,int(item.id[:8],16) if all(c in '0123456789abcdef' for c in item.id[:8]) else 1)
    painter.save();painter.setOpacity(max(0,min(1,state['opacity'])))
    painter.setTransform(animation_transform(item.drawing,state),True)
    painter.drawImage(bounds.topLeft(),image);painter.restore()


def animation_transform(drawing,state):
    center=anchor(drawing.bounds(),state['anchor'])
    matrix=QTransform();matrix.translate(center.x()+state['dx'],center.y()+state['dy']);matrix.rotate(state['angle']);matrix.scale(state['scale'],state['scale']);matrix.translate(-center.x(),-center.y())
    return matrix


def paint_typed(painter,a,state):
    font=QFont('Sans Serif');font.setPixelSize(a.font_size);font.setBold(a.bold)
    metrics=QFontMetricsF(font)
    count=int(len(a.text)*state['text']);reverse=state.get('text_reverse',False)
    low,high=(len(a.text)-count,len(a.text)) if reverse else (0,count)
    painter.save();painter.setOpacity(a.opacity);painter.setFont(font);painter.setPen(QColor(a.color))
    if a.background:painter.fillRect(a.bounds(),QColor('white'))
    x,y=a.points[0];offset=0
    for row,line in enumerate(a.text.split('\n')):
        start,end=max(0,low-offset),min(len(line),high-offset)
        if end>start:painter.drawText(QPointF(x+4+metrics.horizontalAdvance(line[:start]),y+2+row*metrics.height()+metrics.ascent()),line[start:end])
        cursor=low if reverse else high
        if state['cursor'] and offset<=cursor<=offset+len(line):
            px=x+4+metrics.horizontalAdvance(line[:cursor-offset]);top=y+2+row*metrics.height()
            painter.drawLine(QPointF(px,top),QPointF(px,top+metrics.height()))
        offset+=len(line)+1
    painter.restore()


def frame_transform(frame_rect,state):
    a=anchor(frame_rect,state['anchor'])
    matrix=QTransform();matrix.translate(a.x()+state['dx'],a.y()+state['dy']);matrix.rotate(state['angle']);matrix.scale(max(0,state['scale']),max(0,state['scale']));matrix.translate(-a.x(),-a.y())
    return matrix


def transform_frame(frame,state,color='#000000'):
    image=effects(frame,state)
    result=QImage(frame.size(),QImage.Format.Format_ARGB32_Premultiplied);result.fill(QColor(color))
    p=QPainter(result);p.setOpacity(max(0,min(1,state['opacity'])))
    p.setTransform(frame_transform(QRectF(frame.rect()),state));p.drawImage(0,0,image);p.end();return result


def video_states(project,seconds):
    states=[]
    if project.video_animations.enabled:states.append((state_for(project.video_animations,seconds,project.output_duration),'#000000'))
    for span in project.spans[1:]:
        half=project.join_half(span.index)
        if not half or abs(seconds-span.start)>=half:continue
        spec=project.transition(span.index);v=spec.values('join');q=ease(abs(seconds-span.start)/half,spec.easing)
        state=state_for(project.video_animations.__class__(),0,1);state['opacity']=q
        if spec.kind=='Wipe through color':state.update(reveal=q,direction=v['direction'],opacity=1)
        elif spec.kind=='Blur through color':state['blur']=(1-q)*v['blur']
        elif spec.kind=='Zoom through color':state['scale']=v['min_scale']+(1-v['min_scale'])*q
        elif spec.kind=='Dissolve through color':state.update(reveal=q,dissolve=True,particle_size=v['particle_size'],direction='Random',opacity=1)
        states.append((state,v['color']))
    return states


def video_matrix(project,seconds):
    x,y,w,h=project.crop if project.crop else (0,0,project.width,project.height)
    matrix=QTransform();matrix.translate(-x,-y);visible=True
    for state,_ in video_states(project,seconds):
        matrix=matrix*frame_transform(QRectF(0,0,w,h),state)
        visible=visible and state['opacity']>0 and state['reveal']>0
    shift=QTransform();shift.translate(x,y)
    return matrix*shift,visible


def decorate_video(frame,project,seconds):
    states=video_states(project,seconds)
    if not states:return frame
    if project.crop:
        x,y,w,h=project.crop;patch=frame.copy(x,y,w,h)
        for state,color in states:patch=transform_frame(patch,state,color)
        result=QImage(frame);p=QPainter(result);p.drawImage(x,y,patch);p.end();return result
    for state,color in states:frame=transform_frame(frame,state,color)
    return frame


def composite_frame(frame,project,source,seconds):
    result=frame.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    from cpp.editor.document import State
    from cpp.editor.effects import privacy_state
    for item in project.annotations:
        if not item.active(source): continue
        if item.drawing.kind in ('blur','pixelate'):
            a,b=item.drawing.points[0],item.drawing.points[-1]
            r=QRectF(QPointF(*a),QPointF(*b)).normalized()
            if r.width()>=2 and r.height()>=2: result=privacy_state(State(result),r,item.drawing.kind,item.strength).base
        else:
            p=QPainter(result);paint_animated(p,item,source);p.end()
    return decorate_video(result,project,seconds)
