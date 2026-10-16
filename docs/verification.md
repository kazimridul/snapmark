# Verification record — 16 October 2026

## Version 0.1.3 Ubuntu installer — 2026-10-16

- Built `dist/snapmark_0.1.3_amd64.deb` on Ubuntu 25.10, Python 3.13, glibc 2.42. Bundles Python/Qt and runtime dependencies; older Ubuntu versions are not supported by this binary.
- **67 tests pass**, including Wayland v2 window chooser availability, window action/editor handoff, and login startup for the bundled executable.
- Extracted the .deb into a temporary directory. Its executable reports `SnapMark 0.1.3` and the GUI remained running in the offscreen Qt platform for a four-second smoke test without PYTHONPATH or an active virtual environment.
- Apt installation simulation resolved dependencies on the build host. No system install was performed. Package metadata inspected and SHA-256 verified.
- Actual installed desktop launch, interactive capture permissions, real window selection, and cross-application clipboard remain manual checks. This local package has not been published or signed.


## Version 0.1.2 update

- **59 tests pass**, including immediate blur/pixelation on mouse release, pixel restoration through Undo, Escape cancellation of unfinished drags, pen color/size/opacity memory, and editor activation/transient-parent behavior in the offscreen Qt platform, and cancellation of older editor activation timers before capture.
- Inspected the new swatches, compact sliders, crop controls, and blur controls in light/dark themes and at the minimum editor width.
- Real Wayland test with a blank test image confirmed that the editor is a transient top-level of the main window. The compositor **did not activate** this automatically launched editor. No real screenshot/user click was involved, so the actual native capture-to-editor focus handoff remains a manual check. The app requests activation, avoids focus requests from restored windows, and provides a persistent capture badge and taskbar attention request.
- Activation uses Qt's supported `requestActivate()` API; it does not bypass the compositor, install a GNOME extension, or leave windows permanently on top. See https://doc.qt.io/qt-6/qwindow.html#requestActivate and https://wayland.app/protocols/xdg-activation-v1.

## Version 0.1.1 update

- **53 tests pass** after the SnapMark rename, with regression tests for the Wayland v2 native selection going straight to the editor, one-drag fallback capture, backend ownership of region selection, icon sizing/alignment/tooltips, and settings/history compatibility.
- Renamed the visible application, launcher, desktop identity, suggested filenames, and distribution. Kept `cpp` imports and `cpp-screenshot` command compatibility.
- Inspected rendered light/dark editors and the main window. The left palette uses 24px vector icons in aligned 44px buttons with descriptive hover text and accessible names.
- Rebuilt `snapmark-screenshot` 0.1.1 and validated a staged SnapMark desktop launcher install/uninstall.
- Native screenshot interaction after this change still needs a user desktop check; automated regression tests mock the system selector's returned image.

## Original 0.1.0 foundation checks


Environment: Ubuntu 25.10, Python 3.13.7, PySide6 6.12.0, Pillow 12.3.0.

- Automated suite: **42 passed** (`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`). Includes core pixel checks, UI mouse interactions, full editor Save/Copy flow, unsaved-close behavior, and mocked capture backends.
- Python compilation: `src` and `tools` compile successfully.
- Layout review: rendered and inspected the main window, editor with real vector annotations, light/dark themes, and settings dialog using Qt offscreen rendering.
- Real Wayland launch: cpp opened on the host desktop and closed cleanly after querying capabilities. Host screenshot portal reports **version 2**: Full Screen and Region enabled; direct Window capture disabled. No screenshot was taken during this probe.
- Integration fix verified on host: portal property retrieval uses a direct `org.freedesktop.DBus.Properties.GetAll` request, avoiding dbus-next XML introspection errors caused by an unrelated GNOME property named `power-saver-enabled`.
- Desktop files validate with `desktop-file-validate`. A user launcher/icon install and uninstall were tested under a temporary staging prefix; no launcher or login entry was installed into the user's real configuration by these tests.
- Source and wheel distributions build successfully. The wheel can be installed under a separate temporary target and its console entry point reports `cpp 0.1.0`. Source distribution includes tools, documentation, launcher template, run script, and test fixtures.

Not verified: actual screenshot permission/capture end to end, real cross-application clipboard paste, X11 hardware, multi-monitor/mixed-scale displays, login startup, tray extension behavior, Ubuntu 24.04, AppImage, or .deb. Follow [the manual checklist](testing.md) before calling this a production release.
