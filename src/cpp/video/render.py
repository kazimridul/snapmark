"""Use the same vector painter for preview and exported overlays."""
from dataclasses import dataclass
from pathlib import Path
import os
import tempfile
from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import Qt
from cpp.editor.model import paint_annotation
from cpp.video import ffmpeg

@dataclass(frozen=True)
class ExportSettings:
    quality: str = 'Standard'
    max_height: int = 0
    def __post_init__(self):
        if self.quality not in ('Draft', 'Standard', 'High') or self.max_height not in (0,720,1080):
            raise ValueError('Unsupported export settings.')
    def encoder(self):
        return {'Draft': ('ultrafast', '28'), 'Standard': ('veryfast', '23'), 'High': ('medium', '18')}[self.quality]

def annotation_image(width, height, drawing):
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    paint_annotation(painter, drawing)
    painter.end()
    return image

def export(project, destination, settings=ExportSettings(), cancelled=None, progress=None):
    project.validate()
    ffmpeg.require_encoders()
    target = Path(destination).resolve()
    if target == Path(project.source).resolve():
        raise ValueError('Export to a separate file to preserve the source recording.')
    if target.suffix.lower() != '.mp4':
        raise ValueError('Choose an .mp4 output file.')
    if target.exists():
        raise FileExistsError('Choose a new export filename; this file already exists.')
    if project.has_animations:
        from cpp.video.animated_export import render_export
        return render_export(project,target,settings,cancelled,progress)
    with tempfile.TemporaryDirectory(prefix='.snapmark-export-', dir=target.parent) as temp:
        temp = Path(temp)
        args = ['-y', '-i', project.source]
        filters, current = ['[0:v]setpts=PTS-STARTPTS,format=rgba[normalized]'], 'normalized'
        overlay_index = 1
        for i, item in enumerate(project.annotations):
            a = item.drawing
            enabled = f"gte(t,{item.start:.6f})*lt(t,{item.end:.6f})"
            output = f'e{i}'
            if a.kind in ('blur', 'pixelate'):
                xs, ys = zip(*a.points)
                x, y = int(min(xs)), int(min(ys))
                w, h = max(2, int(max(xs))-x), max(2, int(max(ys))-y)
                w, h = min(w, project.width-x), min(h, project.height-y)
                if w < 2 or h < 2:
                    raise ValueError('Privacy rectangle must be at least 2 × 2 pixels.')
                filters.append(f'[{current}]split=2[b{i}][p{i}]')
                effect = f'gblur=sigma={item.strength}' if a.kind == 'blur' else f'scale={max(1,w//item.strength)}:{max(1,h//item.strength)},scale={w}:{h}:flags=neighbor'
                filters.append(f'[p{i}]crop={w}:{h}:{x}:{y}:exact=1,{effect}[q{i}]')
                filters.append(f"[b{i}][q{i}]overlay={x}:{y}:enable='{enabled}'[{output}]")
            else:
                png = temp / f'overlay-{i}.png'
                if not annotation_image(project.width, project.height, a).save(str(png)):
                    raise OSError('Cannot write temporary annotation overlay.')
                args += ['-i', str(png)]
                filters.append(f"[{current}][{overlay_index}:v]overlay=0:0:enable='{enabled}':eof_action=repeat[{output}]")
                overlay_index += 1
            current = output
        if project.crop:
            x, y, w, h = project.crop
            filters.append(f'[{current}]crop={w}:{h}:{x}:{y}:exact=1[cropped]')
            current = 'cropped'
        if settings.max_height:
            filters.append(f"[{current}]scale=-2:'min(ih,{settings.max_height})'[scaled]")
            current = 'scaled'
        filters.append(f'[{current}]pad=ceil(iw/2)*2:ceil(ih/2)*2,setsar=1[base]')
        count = len(project.segments)
        if count > 1:
            filters.append('[base]split=' + str(count) + ''.join(f'[s{i}]' for i in range(count)))
            if project.audio:
                filters.append('[0:a]asplit=' + str(count) + ''.join(f'[a{i}]' for i in range(count)))
        for i, (start, end) in enumerate(project.segments):
            filters.append(f'[{"s"+str(i) if count>1 else "base"}]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS[v{i}]')
            if project.audio:
                filters.append(f'[{"a"+str(i) if count>1 else "0:a"}]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[u{i}]')
        inputs = ''.join(f'[v{i}]' + (f'[u{i}]' if project.audio else '') for i in range(count))
        filters.append(inputs + f'concat=n={count}:v=1:a={int(project.audio)}[video]' + ('[audio]' if project.audio else ''))
        preset, crf = settings.encoder()
        args += ['-filter_complex_threads', '1', '-filter_complex', ';'.join(filters), '-map', '[video]']
        if project.audio:
            args += ['-map', '[audio]', '-c:a', 'aac', '-b:a', '160k']
        result = temp / 'output.mp4'
        args += ['-c:v', 'libx264', '-preset', preset, '-crf', crf, '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(result)]
        ffmpeg.run(args, cancelled, progress, project.output_duration)
        # Atomic, no-clobber publish, including when another process created the target.
        os.link(result, target)
        if progress:
            progress(100)
    return str(target)
