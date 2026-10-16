# SnapMark — Ubuntu screenshots & quick annotation

A native Python/Qt application for taking screenshots, highlighting details, drawing arrows, cropping, and saving or copying edited images. All image processing is local. No accounts, uploads, telemetry, or root privileges are required to run it.

## Run

Target: Ubuntu 24.04 or newer, Python 3.12+, GNOME on Wayland or X11. Automated testing currently uses Ubuntu 25.10 / Python 3.13. Real desktop capture and multi-monitor compatibility must be verified using [the manual checklist](docs/testing.md); this is version 0.1.2, not a certified production release.

```bash
cd /path/to/snapmark
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
./run.sh
```

Or use `.venv/bin/snapmark`. Open an image with `./run.sh /path/to/image.png`. Start a capture with `./run.sh --capture full`, `--capture region`, or `--capture window`. `--minimized` starts in the tray if the desktop provides one; otherwise the main window remains available.

Python virtual environment support and Qt's system libraries must be present. Ubuntu packages commonly needed are `python3-venv`, `libegl1`, `libgl1`, `libxkbcommon0`, `libxcb-cursor0`, and `libxcb-xinerama0`. Wayland needs a running session bus and a working `xdg-desktop-portal` with its desktop backend (normally `xdg-desktop-portal-gnome` on Ubuntu). Installing OS dependencies may require administrator access; running SnapMark does not.

## Everyday use

1. Choose Full Screen, Select Region, or the available window capture action. Optional 3, 5, and 10 second countdowns keep the UI responsive.
2. Use the editor's icon-only left palette; hover over an icon for its name and purpose. Choose a color swatch (or Custom), adjust the size/opacity sliders, and draw with the pen, translucent highlighter, rectangular highlight, arrow, rectangle, ellipse, or text. Each tool remembers its color and stroke settings while the editor stays open.
3. Crop by dragging an area, resizing its eight handles, and moving the selection. Choose Freeform, 1:1, 4:3, or 16:9 before drawing. Choose Crop image or press Enter; Escape cancels.
4. Blur/pixelate: set the strength, then drag over an area. Releasing the mouse applies the effect immediately. Use Undo to restore it; Escape cancels an unfinished drag. There is no extra Apply Selection step.
5. Select an annotation to move it or change its properties. Delete removes it. Select text and choose Edit text to revise it. Ctrl+Z / Ctrl+Y undo and redo committed operations, including crop and privacy edits.
6. Save or Copy. Save As offers PNG, JPEG, and WebP. PNG is recommended for sharp text. The copied image includes committed annotations and pixel edits. Keep SnapMark open until you paste, since Linux clipboard persistence depends on the desktop.

Mouse wheel zooms. Space + drag or middle-button drag pans. Ctrl++ / Ctrl+- zoom, Ctrl+0 fits the image, Ctrl+1 shows 100%. All editing coordinates use the original image's pixels, independent of zoom.

Annotation objects remain editable in the current session. Exported files are ordinary flattened images, so annotations remain visible when reopened but are no longer separate movable objects. Crop and privacy edits also flatten existing vectors at their boundary; undo restores the prior objects. Undo retains up to 100 operations. Large crop/privacy changes can consume substantial memory because their previous image pixels must remain available for undo. Images over 100 megapixels are refused.

Blur and pixelation are configurable visual obfuscation, not guaranteed irreversible anonymization. For highly sensitive information, cover it with an opaque filled rectangle, export, and inspect the result. Undo history exists only in memory and is not embedded in exported images.

## Desktop capture behavior

| Session | Full screen | Region | Window |
|---|---|---|---|
| X11 | Pillow/XCB captures the full X display at native pixel resolution | Drag once on a fullscreen frozen image; releasing the mouse opens the editor | Uses the window manager's `_NET_ACTIVE_WINDOW`, if supported; client area without decorations |
| Wayland portal v1 | Desktop portal screenshot workflow | Drag once on the returned screenshot | Disabled; use Region |
| Wayland portal v2 | Desktop portal screenshot workflow | Select once in the system screenshot UI; the result opens directly in the editor | Select Window opens the system chooser; choose Window there, then click the desired window |
| Wayland portal v3 | Advertised Screen target | Advertised Area target, otherwise local selection of returned screen image | Active Window if advertised, otherwise Select Window if advertised |
| No usable display/portal | Disabled with an explanation | Disabled | Disabled; existing images can still be edited |

The portal may ask for permission or show its own UI. It controls monitor coverage, scaling, and selection behavior; SnapMark does not read the Wayland framebuffer. Cancellations do not become fake screenshots, and failures never silently fall back to X11. X11 captures the full display rather than pretending to support monitor-specific native coordinate mappings. Multi-monitor/mixed-scale results need real hardware verification. Capture windows are hidden before requesting the screenshot. On return, restored windows do not request focus; the new editor requests activation and stays above the SnapMark main window. A green Screenshot captured badge remains until the first edit. Wayland compositors can still decline foreground activation when no valid user-input token exists.

Capture shortcuts (default Ctrl+Shift+F/R/W) and capture-menu Ctrl+Shift+S work in the main window. Editor defaults include Ctrl+S, Ctrl+Shift+S (Save As), Ctrl+C, Ctrl+Z, and Ctrl+Y. Customize these in Settings. For a **system-wide shortcut**, use Ubuntu Settings → Keyboard → Custom Shortcuts and point it at an absolute executable command, for example `/path/to/snapmark/.venv/bin/snapmark --capture region`. Ubuntu handles conflicts and permissions. SnapMark does not install a global keyboard hook or silently change desktop bindings. Each CLI invocation creates an application process; no single-instance service is installed in this release.

## Settings, recent files, and tray

Settings include output folder/format, annotation defaults, privacy strength, capture delay, automatic editor opening, theme, tray, login startup, and application shortcuts. They are validated and stored under Qt's XDG app configuration location, normally `~/.config/SnapMark/SnapMark/`. Existing settings/history from `~/.config/cpp-screenshot/cpp/` are read automatically when no new SnapMark data exists. Invalid JSON falls back to defaults. History stores at most 30 paths locally. Removing a history entry preserves the image file.

Turning off automatic editing saves captures to the configured screenshots folder and adds them to Recent. A failed quick-save opens the captured image in the editor so it can be recovered. Tray support depends on the desktop; GNOME may require its AppIndicator extension. Hide to tray is explicit. Closing the main window or choosing Quit exits after handling unsaved editors; closing never secretly leaves a tray process behind. Login startup is opt-in and uses the current Python installation, which must remain at the same path.

## Test and package

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/python -m build
.venv/bin/python tools/install_desktop.py
```

The desktop installer creates the launcher and SVG icon in your XDG user data directory. It records the current virtual environment path, so rerun it if you move the project. See [the verification record](docs/verification.md), [packaging](packaging/README.md), [architecture](docs/architecture.md), [development](docs/development.md), and [manual verification](docs/testing.md).

Uninstall the launcher with `.venv/bin/python tools/install_desktop.py --uninstall`, disable Launch at login in Settings, then uninstall the Python package with `.venv/bin/python -m pip uninstall snapmark-screenshot`. Your saved images and local settings/history are preserved.
