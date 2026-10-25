"""Bounded media probing and cancellable processes. No shell command evaluation."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import threading
from cpp.video.model import Project

class Cancelled(RuntimeError):
    pass

def system_environment():
    """Keep bundled Qt libraries out of host FFmpeg/GStreamer processes."""
    env = os.environ.copy()
    if getattr(__import__('sys'), 'frozen', False):
        original = env.pop('LD_LIBRARY_PATH_ORIG', None)
        if original:
            env['LD_LIBRARY_PATH'] = original
        else:
            env.pop('LD_LIBRARY_PATH', None)
    return env

def binary(name):
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f'{name} is missing. Install the Ubuntu ffmpeg package.')
    return path

def probe(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('Video file does not exist.')
    result = subprocess.run([binary('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], capture_output=True, text=True, timeout=30, env=system_environment())
    if result.returncode:
        raise RuntimeError('Cannot read this video: ' + result.stderr[-1500:])
    data = json.loads(result.stdout)
    video = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
    if not video:
        raise ValueError('No video stream found.')
    w, h = video['width'], video['height']
    rotation = next((s.get('rotation', 0) for s in video.get('side_data_list', []) if 'rotation' in s), video.get('tags', {}).get('rotate', 0))
    if int(rotation) % 180:
        w, h = h, w
    num, den = video.get('avg_frame_rate', '30/1').split('/')
    fps = float(num) / float(den) if float(den) else 30
    return Project(str(path), float(video.get('duration') or data['format']['duration']), w, h, fps or 30,
                   any(s['codec_type'] == 'audio' for s in data['streams']))

def require_encoders():
    result = subprocess.run([binary('ffmpeg'), '-hide_banner', '-encoders'], capture_output=True, text=True, timeout=15, env=system_environment())
    if result.returncode or 'libx264' not in result.stdout or ' aac ' not in result.stdout:
        raise RuntimeError('FFmpeg needs the libx264 and AAC encoders for MP4 output.')

def run(arguments, cancelled=None, progress=None, duration=0):
    cancelled = cancelled or threading.Event()
    # Use a disk-backed diagnostic stream so stderr cannot fill a pipe or grow memory.
    import tempfile
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen([binary('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-progress', 'pipe:1', *map(str, arguments)], stdout=subprocess.PIPE, stderr=errors, text=True, env=system_environment())
        def stop():
            while process.poll() is None:
                if cancelled.wait(.1):
                    process.terminate()
                    try:
                        process.wait(5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    return
        watcher = threading.Thread(target=stop, daemon=True)
        watcher.start()
        try:
            for line in process.stdout:
                if progress and duration and line.startswith('out_time_us='):
                    try:
                        progress(min(99, int(int(line.split('=')[1]) / (duration*10000))))
                    except ValueError:
                        pass
            code = process.wait()
            if cancelled.is_set():
                raise Cancelled('Export cancelled. Source recording preserved.')
            if code:
                errors.seek(0, 2)
                errors.seek(max(0, errors.tell()-4000))
                raise RuntimeError('FFmpeg failed: ' + errors.read().decode(errors='replace'))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
            watcher.join(1)
