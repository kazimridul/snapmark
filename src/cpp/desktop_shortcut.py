"""Per-user GNOME Print Screen registration with reversible settings changes."""
import ast
import json
import os
import shlex
import shutil
import subprocess
import sys
from cpp.config import config_root

MEDIA = 'org.gnome.settings-daemon.plugins.media-keys'
CUSTOM_PATH = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/snapmark/'
CUSTOM = MEDIA + '.custom-keybinding:' + CUSTOM_PATH


def command():
    args = [sys.executable]
    if not getattr(sys, 'frozen', False):
        args += ['-m', 'cpp']
    return shlex.join(args + ['--capture', 'region'])


def gsettings(*args):
    env = os.environ.copy()
    # Frozen apps must not load bundled libraries into system executables.
    if getattr(sys, 'frozen', False):
        original = env.pop('LD_LIBRARY_PATH_ORIG', None)
        env.pop('LD_LIBRARY_PATH', None)
        if original:
            env['LD_LIBRARY_PATH'] = original
    try:
        result = subprocess.run(['gsettings', *args], env=env, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OSError('Cannot configure Print Screen: ' + str(exc)) from exc
    if result.returncode or 'failed to commit' in result.stderr.lower():
        raise OSError('Cannot configure Print Screen: ' + (result.stderr.strip() or result.stdout.strip()))
    return result.stdout.strip()


def read(schema, key):
    value = gsettings('get', schema, key)
    # GVariant annotates empty string arrays as @as [].
    return ast.literal_eval(value.removeprefix('@as '))


def write(schema, key, value):
    if gsettings('writable', schema, key) != 'true':
        raise OSError(f'The desktop has locked {schema} {key}.')
    gsettings('set', schema, key, repr(value))
    if read(schema, key) != value:
        raise OSError(f'The desktop did not save {schema} {key}.')


def set_print_screen(enabled):
    state = config_root() / 'print-screen-backup.json'
    if not enabled:
        if not state.exists():
            return
        changes = json.loads(state.read_text())
        for schema, key, before, after in reversed(changes):
            current = read(schema, key)
            if schema == MEDIA and key == 'custom-keybindings':
                if CUSTOM_PATH not in before:
                    write(schema, key, [p for p in current if p != CUSTOM_PATH])
            elif current == after:
                write(schema, key, before)
        state.unlink()
        return
    if state.exists():
        return
    desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
    if not any(name in desktop for name in ('gnome', 'ubuntu')) or not shutil.which('gsettings'):
        raise OSError('Automatic Print Screen setup requires Ubuntu GNOME. Add a custom keyboard shortcut for: ' + command())
    changes = []
    def plan(schema, key, value):
        before = read(schema, key)
        if before != value:
            changes.append([schema, key, before, value])
    paths = read(MEDIA, 'custom-keybindings')
    # Release only the unmodified Print key, preserving modified shortcuts.
    for schema in ('org.gnome.shell.keybindings', MEDIA):
        for key in gsettings('list-keys', schema).splitlines():
            if 'screenshot' in key:
                keys = read(schema, key)
                if isinstance(keys, list) and 'Print' in keys:
                    plan(schema, key, [k for k in keys if k != 'Print'])
    for path in paths:
        if path != CUSTOM_PATH:
            schema = MEDIA + '.custom-keybinding:' + path
            if read(schema, 'binding') == 'Print':
                plan(schema, 'binding', '')
    plan(CUSTOM, 'name', 'SnapMark screenshot')
    plan(CUSTOM, 'command', command())
    plan(CUSTOM, 'binding', 'Print')
    plan(MEDIA, 'custom-keybindings', list(dict.fromkeys([*paths, CUSTOM_PATH])))
    state.parent.mkdir(parents=True, exist_ok=True)
    temporary = state.with_suffix('.tmp')
    temporary.write_text(json.dumps(changes, indent=2))
    temporary.replace(state)
    applied = []
    try:
        for schema, key, before, after in changes:
            applied.append((schema, key, before))
            write(schema, key, after)
    except OSError as error:
        # A locked key must not prevent restoring the other changed bindings.
        rollback_errors = []
        for schema, key, before in reversed(applied):
            try:
                if read(schema, key) != before:
                    write(schema, key, before)
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        if rollback_errors:
            raise OSError(str(error) + ' Previous bindings could not all be restored; backup retained at ' + str(state)) from error
        state.unlink()
        raise
