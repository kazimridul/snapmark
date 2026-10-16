# Packaging and installation

## Python distribution (implemented)

```bash
.venv/bin/python -m build
python3 -m venv /tmp/cpp-clean
/tmp/cpp-clean/bin/python -m pip install dist/snapmark_screenshot-0.1.2-py3-none-any.whl
/tmp/cpp-clean/bin/snapmark --version
```

The wheel contains the application and SVG icon. pip installs its declared Python dependencies; system Qt display libraries and the desktop portal are runtime host requirements, not bundled services. The wheel is platform-neutral Python but its Qt dependencies are platform-specific.

## Desktop launcher (implemented)

Run `.venv/bin/python tools/install_desktop.py`. It writes only `io.github.snapmark.SnapMark.desktop` and the matching SVG icon under your XDG data directory. It embeds the current interpreter path so the launcher works even if the virtual environment's bin directory is not in PATH. Use `--prefix /tmp/cpp-launcher-check` for a staged installation. Undo with `--uninstall` using the same prefix. The checked-in generic desktop file is suitable for a package whose `snapmark` executable is on PATH.

## AppImage build plan (not yet built or validated)

1. On a clean Ubuntu 24.04 build VM, install a supported Python/Qt stack and build a one-directory application with PyInstaller. Collect SnapMark's SVG and only required Qt plugins (platforms, Wayland/XCB, imageformats, iconengines). Preserve PySide/Qt licensing notices and allow compliance with LGPL requirements.
2. Put the runnable application under `AppDir/usr/`, provide `AppRun`, install the desktop file and icon, and use `appimagetool` to create the image. Do not bundle or start a desktop portal daemon; communicate with the host session service.
3. Test the actual AppImage on clean Ubuntu 24.04 and newer, with Wayland/X11, no development venv, no host screenshot utilities, tray available/unavailable, and image clipboard consumers.
4. Inspect bundled libraries, architecture/glibc compatibility, and dependency license notices before distributing. Confirm no unwanted QtWebEngine/QtPdf modules are included.

This repository does not claim to provide a verified AppImage or .deb. A .deb can later install the wheel into a private application environment, the generic launcher, and the icon, with explicit system-library dependencies. Optional packaging is not needed to run the working source or installable wheel.

## Uninstall

Disable Launch at login in Settings, remove the desktop launcher using the installer, and run `python -m pip uninstall snapmark-screenshot` with the installing environment. Removing the project virtual environment then removes its remaining dependencies. Screenshots and XDG settings/history are intentionally preserved; remove those manually only if you want to discard them.
