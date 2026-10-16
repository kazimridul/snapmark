# Development

Use Python 3.12+ and a virtual environment. Install with `python -m pip install -e '.[dev]'`; launch `python -m cpp`; run `QT_QPA_PLATFORM=offscreen python -m pytest -q`. No real desktop capture runs in the test suite.

The displayed application name is **SnapMark**, its distribution is `snapmark-screenshot`, and its launcher is `snapmark`. The Python import package remains `cpp` and the former `cpp-screenshot` command is retained as a compatibility alias. Existing settings/history are read from the old configuration location when needed.

## Implemented milestones

1. Foundation: pyproject, native Qt main/editor windows, image decoding, compositing, PNG/JPEG/WebP save, and image clipboard. Verified by offscreen window launch, image round-trip, and clipboard tests.
2. Capture: asynchronous X11 and Wayland backends, target negotiation, delayed capture, cancellation/error handling, and frozen-image region selection. Verified with mocked capture and D-Bus response tests. Live session testing is listed separately.
3. Editing: crop handles/aspect constraints, highlighter/freehand and rectangular highlight, pen, arrows, filled/outlined shapes, multiline text, annotation movement/property edits, command undo/redo. Verified with pixel assertions and Qt input simulation.
4. Privacy/usability: true pixel effects applied on drag release with undo, zoom/pan, dirty-state prompts, consistent export renderer, atomic writes. Verified through document and UI tests.
5. Integration: configurable app shortcuts, recent files/thumbnails, validated settings, optional tray/login startup, SVG icon and launcher installer. Verified offscreen and with a staged launcher installation. Desktop-specific activation still needs manual verification.
6. Release preparation: tests, documentation, wheel/source packaging, installation checks. Actual AppImage and hardware compatibility remain release gates, not completed claims.

## Making changes

Keep image processing in the model/effects/storage layers. Reuse `paint_annotation` instead of drawing a different approximation in the UI. Use Jobs for blocking work; completion callbacks run on the GUI thread. Do not access QWidget/QPixmap from worker threads. QImage/QPainter image rendering and Pillow processing can run there. Never log annotation text or image bytes.

Add tests for changes that affect compositing, capture semantics, pixel coordinates, persistence, or file integrity. For capture tests, mock the backend or D-Bus bus instead of opening permission dialogs. Test both a signal received before the Screenshot method returns and a later response; the portal subscription must be installed before requesting capture.

## Troubleshooting

- `ModuleNotFoundError`: use the project's `.venv/bin/python` and reinstall the editable package.
- Qt xcb plugin error: install missing Ubuntu runtime libraries listed in README, or use a working Wayland session. `QT_DEBUG_PLUGINS=1` can identify a missing library.
- Portal unavailable: run in the logged-in desktop session with its D-Bus environment. Check your xdg-desktop-portal/GNOME backend; sandboxed development sessions may block the bus even though the application runs normally on the host.
- Missing tray icon: tray support is optional. Use the main window; start-minimized falls back to showing it.
- Clipboard persistence: keep SnapMark open until the image has been pasted. Some desktop clipboard managers cannot preserve large image data after the owner exits.
