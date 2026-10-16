# Architecture

- `main.py` creates QApplication, loads validated settings, applies the theme, and dispatches CLI requests.
- `capture/backend.py` exposes immutable capabilities and a common capture function. Wayland uses the XDG Screenshot portal through dbus-next; X11 uses Pillow/XCB and python-xlib for reliable window geometry. The session never silently changes backends. Portal version/target negotiation determines the window action label and availability.
- `editor/model.py` defines immutable typed vector annotations and the shared QPainter renderer. The canvas and export call the same drawing code, including translucent marker strokes and multiline text.
- `editor/document.py` contains State and command-based undo/redo. Vector edits share the base QImage through Qt's implicit sharing. Crops flatten and change actual pixel dimensions. Privacy effects flatten existing annotations and change the composited pixels, so exported files cannot accidentally expose an unmodified original layer.
- `editor/canvas.py` maps viewport events into image-pixel scene coordinates. It draws guides and temporary selections separately from export, handles panning/zooming and eight crop/region handles, and commits vectors only on release. The separate fallback capture selector accepts immediately on release. Wayland v2/v3 native region results bypass that selector so the user selects only once.
- `editor/effects.py` applies Pillow effects to selected pixel rectangles and returns a new state. Privacy effects commit on drag release as one undoable operation. Escape cancels an unfinished drag; Undo restores the original image and annotations after a committed effect. Only crop keeps an explicit Crop image/Cancel confirmation.
- `jobs.py` owns Qt workers and routes completion through main-thread QObject slots. Capture, decoding, thumbnails, compositing for export, saving, crop, and privacy processing happen in workers. GUI objects and clipboard ownership remain on the main thread. Window closing is blocked while an owned job is active, preventing destruction of running QThreads.
- `storage.py` validates input decoding, creates bounded thumbnails through callers, and writes images/history atomically with QSaveFile. PNG export and image clipboard data use the fully composited state; UI controls are never part of it.
- `ui/tool_options.py` provides color swatches and compact size/opacity/strength sliders. Per-tool style choices are retained within each editor. New editors are transient top-level windows of the capture window, with a bounded activation retry and no always-on-top flag. Restored windows are shown without requesting focus.
- `config.py` handles versioned JSON, per-field validation, and user-controlled login startup.
- `ui/` contains the main capture screen, editor, contextual settings, tray, region dialog, and theme. History removal affects metadata only. There is no network client or telemetry subsystem.

## Limits and deliberate choices

100 retained undo commands bound command count, not total memory. Destructive pixel edits retain their before/after images; vector edits retain only immutable annotations and shared pixels. A future release can add a byte-budgeted pixel tile cache for repeated edits of huge images.

Export is flattened, with ordinary image interoperability favored over a proprietary editable project format. No global shortcut daemon, automatic host configuration, cloud upload, or privileged process is installed. Native Qt dialogs handle file selection and overwrite confirmation.

Screenshot portal reference: https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Screenshot.html
