"""Discover PulseAudio-compatible sources without enabling audio automatically."""
from dataclasses import dataclass
import json
import shutil
import subprocess
from cpp.video.ffmpeg import system_environment

@dataclass(frozen=True)
class AudioSource:
    name: str
    label: str
    monitor: bool

def sources():
    if not shutil.which('pactl'):
        return []
    result = subprocess.run(['pactl', '-f', 'json', 'list', 'sources'], capture_output=True, text=True, timeout=5, env=system_environment())
    if result.returncode:
        return []
    return [AudioSource(s['name'], s.get('description', s['name']), s.get('monitor_of_sink') not in (None, 4294967295, '4294967295') or s['name'].endswith('.monitor')) for s in json.loads(result.stdout)]
