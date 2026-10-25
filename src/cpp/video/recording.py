"""Asynchronous recording service; recoverable WebM intermediates are retained on failure."""
import asyncio
from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import tempfile
from PySide6.QtCore import QThread, Signal
from cpp.capture.backend import session_type
from cpp.video import ffmpeg
from cpp.video.portal import Portal

@dataclass
class RecordingSettings:
    output: str
    mode: str = 'full'
    fps: int = 30
    height: int = 0
    quality: str = 'Medium'
    audio: list[str] = field(default_factory=list)
    volume: float = 1
    region: tuple | None = None

    def validate(self):
        if self.fps not in (15, 24, 30, 60) or self.mode not in ('full', 'region', 'window'):
            raise ValueError('Unsupported recording settings.')
        if self.height not in (0, 720, 1080) or self.quality not in ('Low', 'Medium', 'High') or not 0 <= self.volume <= 2:
            raise ValueError('Unsupported recording quality or volume.')
        if session_type() == 'x11' and self.mode == 'window':
            raise ValueError('Use region recording on X11; live window capture is unavailable.')
        target = Path(self.output)
        if target.suffix.lower() != '.mp4' or target.exists():
            raise ValueError('Choose a new .mp4 recording filename.')
        target.parent.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(target.parent).free < 100*1024*1024:
            raise RuntimeError('Less than 100 MB of disk space is available.')

class RecordingClock:
    def __init__(self, now=time.monotonic):
        self.now = now
        self.elapsed = 0.
        self.started = None
    def resume(self):
        if self.started is None:
            self.started = self.now()
    def pause(self):
        if self.started is not None:
            self.elapsed += self.now()-self.started
            self.started = None
    def seconds(self):
        return self.elapsed + (self.now()-self.started if self.started is not None else 0)

class Recorder(QThread):
    progress = Signal(int)
    region_requested = Signal(object)
    status = Signal(str)
    saved = Signal(str)
    failed = Signal(str)
    helper = Path(__file__).with_name('gst_helper.py')

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.commands = queue.Queue()
        self.cancelled = threading.Event()
        self.clock = RecordingClock()
        self.region_chosen = threading.Event()

    def command(self, command):
        if command == 'stop':
            self.cancelled.set()  # Also dismiss a pending portal chooser.
        self.commands.put(command)

    def select_region(self, region):
        self.settings.region = region
        self.region_chosen.set()

    async def request_region(self, options, portal):
        """Preview the authorized stream once; recording/audio start after selection."""
        from cpp.storage import read_image
        with tempfile.TemporaryDirectory(prefix='snapmark-recording-area-') as temp:
            snapshot = Path(temp)/'monitor.png'
            preview = {**options, 'snapshot': True, 'output': str(snapshot), 'region': None, 'audio': []}
            process = await asyncio.create_subprocess_exec('/usr/bin/python3', str(self.helper), json.dumps(preview), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, pass_fds=(options['fd'],), env=ffmpeg.system_environment())
            communication = asyncio.create_task(process.communicate())
            deadline = time.monotonic()+30
            try:
                while not communication.done():
                    if self.cancelled.is_set() or portal.closed:
                        raise RuntimeError('Area selection cancelled.')
                    if time.monotonic()>deadline:
                        raise RuntimeError('No preview frame arrived from the selected monitor.')
                    await asyncio.sleep(.1)
                out,_ = await communication
                if process.returncode or not snapshot.exists():
                    raise RuntimeError('Could not preview the selected monitor: '+out.decode(errors='replace')[-1000:])
                image = read_image(snapshot)
                self.status.emit('Select recording area')
                self.region_requested.emit(image)
                deadline = time.monotonic()+180
                while not self.region_chosen.is_set():
                    if self.cancelled.is_set() or portal.closed or time.monotonic()>deadline:
                        raise RuntimeError('Area selection cancelled.')
                    await asyncio.sleep(.1)
                options['region'] = self.settings.region
                options['source_size'] = [image.width(),image.height()]
                options['fd'] = await portal.open_remote()
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
                if not communication.done():
                    communication.cancel()

    def run(self):
        try:
            asyncio.run(self.record())
        except Exception as exc:
            self.clock.pause()
            self.failed.emit(str(exc))

    async def record(self):
        self.settings.validate()
        await asyncio.to_thread(ffmpeg.require_encoders)
        session = session_type()
        if session not in ('wayland', 'x11'):
            raise RuntimeError('No supported desktop session is available.')
        options = asdict(self.settings)
        options['session'] = session
        check = await asyncio.create_subprocess_exec('/usr/bin/python3', str(self.helper), json.dumps({**options, 'check': True}), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=ffmpeg.system_environment())
        out, err = await check.communicate()
        if check.returncode:
            raise RuntimeError('Recording requires Ubuntu python3-gi, gir1.2-gstreamer-1.0, gstreamer1.0-pipewire and GStreamer base/good plugins. ' + (out+err).decode(errors='replace')[-1800:])
        portal = Portal(self.cancelled)
        process = None
        # This path is intentionally retained after failures for manual recovery.
        intermediate = Path(self.settings.output).with_name('.'+Path(self.settings.output).stem+'-'+os.urandom(4).hex()+'.webm')
        options['output'] = str(intermediate)
        options['height'] = 0  # Never upscale during PipeWire negotiation.
        try:
            self.status.emit('Waiting for screen permission')
            if session == 'wayland':
                options['fd'], options['node'] = await portal.open(self.settings.mode)
                if self.settings.mode == 'region':
                    await self.request_region(options, portal)
            if self.cancelled.is_set():
                raise RuntimeError('Recording cancelled before capture started.')
            process = await asyncio.create_subprocess_exec('/usr/bin/python3', str(self.helper), json.dumps(options), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, pass_fds=(options['fd'],) if session == 'wayland' else (), env=ffmpeg.system_environment())
            errors = []
            stopped = None
            async def messages():
                async for line in process.stdout:
                    message = json.loads(line)
                    if 'error' in message:
                        errors.append(message['error'])
                    state = message.get('state')
                    if stopped is not None and state in ('recording','paused'):
                        continue
                    if state == 'recording':
                        self.clock.resume()
                    elif state in ('paused', 'finished'):
                        self.clock.pause()
                    if state:
                        self.status.emit(state)
            reader = asyncio.create_task(messages())
            while process.returncode is None:
                if portal.closed and stopped is None:
                    self.commands.put('stop')
                try:
                    command = self.commands.get_nowait()
                    if command == 'stop':
                        stopped = time.monotonic()
                        self.clock.pause()
                        self.status.emit('Finalizing recording')
                    process.stdin.write((command+'\n').encode())
                    await process.stdin.drain()
                except queue.Empty:
                    pass
                except (BrokenPipeError, ConnectionResetError):
                    break
                if stopped and time.monotonic()-stopped > 25:
                    raise RuntimeError('Recording finalization timed out.')
                await asyncio.sleep(.1)
            await process.wait()
            await reader
            self.clock.pause()
            if process.returncode or errors:
                raise RuntimeError('; '.join(errors) or 'Screen recording process failed.')
            self.status.emit('Encoding MP4')
            from cpp.video.render import ExportSettings, export
            project = await asyncio.to_thread(ffmpeg.probe, intermediate)
            quality = {'Low': 'Draft', 'Medium': 'Standard', 'High': 'High'}[self.settings.quality]
            await asyncio.to_thread(export, project, self.settings.output, ExportSettings(quality,self.settings.height),None,self.progress.emit)
            intermediate.unlink(missing_ok=True)
            self.saved.emit(self.settings.output)
        except Exception as exc:
            recover = f' Recoverable recording, if present: {intermediate}' if intermediate.exists() else ''
            raise RuntimeError(str(exc)+recover) from exc
        finally:
            if process and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            await portal.close()
