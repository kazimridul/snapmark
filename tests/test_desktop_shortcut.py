import copy
import pytest
from cpp import desktop_shortcut as shortcuts


@pytest.fixture
def desktop(monkeypatch, tmp_path):
    shell = 'org.gnome.shell.keybindings'
    other = shortcuts.MEDIA + '.custom-keybinding:/custom/other/'
    values = {
        (shell, 'show-screenshot-ui'): ['Print', '<Shift>Print'],
        (shell, 'screenshot-window'): ['<Alt>Print'],
        (shortcuts.MEDIA, 'custom-keybindings'): ['/custom/other/'],
        (other, 'binding'): 'Print',
        (shortcuts.CUSTOM, 'name'): '',
        (shortcuts.CUSTOM, 'command'): '',
        (shortcuts.CUSTOM, 'binding'): '',
    }
    monkeypatch.setenv('XDG_CURRENT_DESKTOP', 'ubuntu:GNOME')
    monkeypatch.setattr(shortcuts, 'config_root', lambda: tmp_path)
    monkeypatch.setattr(shortcuts.shutil, 'which', lambda _: '/usr/bin/gsettings')
    monkeypatch.setattr(shortcuts, 'read', lambda schema, key: copy.deepcopy(values[(schema, key)]))
    monkeypatch.setattr(shortcuts, 'write', lambda schema, key, value: values.__setitem__((schema, key), value))
    monkeypatch.setattr(shortcuts, 'gsettings', lambda *args: '\n'.join(k for s, k in values if s == args[1]))
    return values


def test_print_screen_installs_and_restores_previous_bindings(desktop, tmp_path):
    original = copy.deepcopy(desktop)
    shortcuts.set_print_screen(True)
    assert desktop[('org.gnome.shell.keybindings', 'show-screenshot-ui')] == ['<Shift>Print']
    assert desktop[(shortcuts.CUSTOM, 'binding')] == 'Print'
    assert desktop[(shortcuts.CUSTOM, 'command')].endswith('--capture region')
    after = copy.deepcopy(desktop)
    shortcuts.set_print_screen(True)
    assert desktop == after
    shortcuts.set_print_screen(False)
    assert desktop == original
    assert not (tmp_path / 'print-screen-backup.json').exists()


def test_restore_preserves_new_user_shortcuts(desktop):
    shortcuts.set_print_screen(True)
    desktop[(shortcuts.MEDIA, 'custom-keybindings')].append('/custom/new/')
    desktop[('org.gnome.shell.keybindings', 'show-screenshot-ui')] = ['<Super>Print']
    shortcuts.set_print_screen(False)
    assert '/custom/new/' in desktop[(shortcuts.MEDIA, 'custom-keybindings')]
    assert shortcuts.CUSTOM_PATH not in desktop[(shortcuts.MEDIA, 'custom-keybindings')]
    assert desktop[('org.gnome.shell.keybindings', 'show-screenshot-ui')] == ['<Super>Print']


def test_registration_rolls_back_partial_failure(desktop, monkeypatch, tmp_path):
    original = copy.deepcopy(desktop)
    def write(schema, key, value):
        if key == 'command' and value:
            raise OSError('locked')
        desktop[(schema, key)] = value
    monkeypatch.setattr(shortcuts, 'write', write)
    with pytest.raises(OSError, match='locked'):
        shortcuts.set_print_screen(True)
    assert desktop == original
    assert not (tmp_path / 'print-screen-backup.json').exists()


def test_unsupported_desktop_changes_nothing(desktop, monkeypatch):
    original = copy.deepcopy(desktop)
    monkeypatch.setenv('XDG_CURRENT_DESKTOP', 'KDE')
    with pytest.raises(OSError, match='GNOME'):
        shortcuts.set_print_screen(True)
    assert desktop == original


def test_frozen_shortcut_command_uses_executable(monkeypatch):
    monkeypatch.setattr(shortcuts.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(shortcuts.sys, 'executable', '/opt/snapmark/snapmark')
    assert shortcuts.command() == '/opt/snapmark/snapmark --capture region'
