# Verification

## Automated

Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`.

Tests cover crop normalization/clipping, translucent highlighter pixels, all vector tools, multiline text, privacy pixels, annotation movement/properties, undo/redo and clean states, PNG export/clipboard fidelity, JPEG/WebP decoding, invalid files/write failures, settings recovery, history semantics, zoom-independent coordinates, crop handles, immediate privacy edits and Escape cancellation of unfinished drags, main-thread callbacks, delayed capture/cancellation, and capture workflow recovery.

Capture tests use a fake D-Bus connection and fake X11 grabber. Portal tests cover version-specific target options, a Response arriving before the Screenshot method reply, permission failure, cancellation, URI validation, and connection cleanup. They cannot establish real compositor compatibility.

## Manual release matrix — unverified until checked on hardware

Record Ubuntu version, desktop version, portal version, Qt version, session type, monitor layout and scale for each run. Repeat on GNOME Wayland and X11, Ubuntu 24.04 LTS and a current Ubuntu release.

- [ ] Launch main window and open a real PNG/JPEG/WebP.
- [ ] Capture full desktop; ensure SnapMark windows are absent.
- [ ] Capture a region at every screen edge; verify exported dimensions/pixels.
- [ ] Capture a window if supported; ensure it is the intended window, including when another editor was previously active.
- [ ] Confirm unsupported window capture is disabled or accurately labeled Select Window.
- [ ] Cancel system permission UI; deny permission; check main window/control recovery.
- [ ] Cancel 3/5/10-second countdown; check no capture occurs.
- [ ] Single monitor at 100%, 125%, 150%, and 200% scaling.
- [ ] Multiple monitors, negative monitor origins, mixed resolutions and scales; verify actual full-desktop coverage and selection precision.
- [ ] Test all tools while zoomed and panned; move text/arrow; edit selected properties.
- [ ] Crop using corners and side handles, move the crop, test each ratio, Apply/Cancel and undo/redo.
- [ ] Drag over a private area with Blur/Pixelate; confirm the effect is applied on release and matches export. Undo must restore it; Escape must cancel an unfinished drag.
- [ ] Select a preset/custom pen color, size, and opacity; switch tools and confirm the pen remembers them.
- [ ] Capture a region with a real system-selector click; confirm the editor comes forward, its capture badge is visible, and previously open SnapMark windows do not compete for focus. Repeat after a delayed capture and with another app focused.
- [ ] Copy edited image into another image editor and a document application; test before/after exiting SnapMark with the desktop clipboard manager.
- [ ] Save PNG/JPEG/WebP, overwrite a file, cancel overwrite, reopen and compare; verify lack of free space/write permissions produces a recoverable error.
- [ ] Close unsaved editor/main window and exercise Save/Discard/Cancel.
- [ ] Restart with settings changed; simulate corrupt settings JSON; remove/move a recent file; remove history without deleting its file.
- [ ] Test light/dark/system theme, keyboard focus/contrast, tray with and without an indicator extension, and opt-in login startup.
- [ ] Assign a GNOME custom global shortcut, verify conflict handling and the absolute executable path.
- [ ] Install the built wheel in a clean environment and repeat capture, clipboard, and launcher tests.

Headless UI checks and package import tests are not substitutes for these checks. No live desktop capture, real clipboard cross-application paste, tray behavior, or hardware scaling support is certified by automated tests alone.
