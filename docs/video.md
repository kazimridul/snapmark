# Screen recording and video editing (0.2.3)

SnapMark retains the existing screenshot capture services, image document/canvas,
settings, and worker architecture. `MainWindow` now hosts Screenshot and Screen
Recording tabs. The screenshot editor and its export behavior are unchanged.

## Run

Install the system runtime dependencies with your normal Ubuntu package manager:

```bash
sudo apt install ffmpeg python3-gi gir1.2-gstreamer-1.0 \
  gstreamer1.0-pipewire gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good pulseaudio-utils
.venv/bin/python -m pip install -e '.[dev]'
./run.sh
```

Open an existing video directly with `./run.sh /path/to/video.webm`, or choose
SnapMark for a video file in the file manager. `.snapmark.json` project paths
can also be passed to the launcher.

Root is needed only for installing OS packages. The app runs as your user. The
new Debian package declares these dependencies and bundles Qt Multimedia.

Print Screen keeps Ubuntu’s native capture/recording chooser and system defaults.
While SnapMark is running, its optional native import watcher opens completed new
recordings from Videos/Screencasts or Videos. It waits for the writer to close the
file (or atomically rename it), rather than opening an unfinished recording.
Recordings already in those folders at startup are left alone.

Choose **Screen Recording**, set a new MP4 filename, frame rate, quality, optional
countdown and audio, then Start. Wayland opens the system screen-sharing chooser.
Select one monitor or window and approve. Select area is the default: share a
monitor, then drag the recording area on its frozen preview. Capture and audio
start only after that selection; the encoder crops the stream to those pixels.
The launcher hides during selection/recording and returns when finished. Audio defaults to **No audio**. Select
an actual microphone and/or sink monitor for audio; absent devices produce an
error rather than a silent substitution. Input gain applies to selected sources.
Pause and Resume exclude paused time from the pipeline clock. Stop finalizes the
WebM intermediate and encodes H.264/AAC MP4 before offering preview or editing.
The visible timer excludes pauses and stops when recording stops. A separate
Saving recording dialog appears immediately during finalization, then shows MP4
encoding progress. It closes only when saving finishes or an error is reported.

Lower-resolution options set a maximum output height and preserve aspect ratio;
small recordings are never upscaled. Default output keeps the source size, with
black padding on an odd right/bottom edge when H.264 requires even dimensions.
Keep the recording controls outside the area you share if you do not want them
visible in the recording. Recordings remain local; nothing is uploaded.

## Playback and edits

Open Video loads existing MP4, WebM, MKV, MOV and other formats supported by the
installed Qt FFmpeg backend. Play/Pause, Stop, seek buttons, scrubbing, volume,
mute and 0.5/1/1.5/2× speed are available. Full screen expands the workspace.
Space toggles playback; Left/Right seek five seconds; Home/End seek to the edges;
Escape exits full screen. These keys defer to text and numeric input controls.
Frame stepping seeks by the source's average frame period; exact frame stepping
on variable-frame-rate media is not guaranteed.

The editor uses icon actions above the preview, a left icon tool rail with
contextual properties, and an Outline on the right containing only layers and
change history. Tools change the cursor glyph. The left, right and bottom panels
are resizable, movable Qt docks.

The timeline ruler, playback duration and transport controls use **edited sequence
time**, starting at zero. Split at the playhead, then drag a video clip left or
right to insert it at a new position. An insertion line shows the drop location.
Click a clip to select it; the trash action removes that selected clip and closes
the gap immediately. At least one clip must remain. The preview skips deleted
footage automatically, including while paused or scrubbing. There is no separate
"play kept segments" switch. The saved source file is preserved.

Trim handles and numeric trim values operate on this assembled sequence, including
after reordering. Undo/redo restores cuts, deletions and clip order. The player
streams from the source and seeks between the kept clips; it does not first
render a temporary movie. Old buffered frames outside the current clip are
rejected. Export encodes the same ordered clips with their audio, using accurate
cuts rather than keyframe-only stream copying.

Use the zoom icons or **Ctrl+mouse wheel** to zoom around the cursor. A horizontal
scrollbar appears below the timeline; **Shift+wheel** and horizontal trackpad
scrolling also pan it. **Fit** returns to the complete edited sequence. Ruler
intervals adapt to the zoom level, and playback follows the playhead when zoomed.
Panels can still be resized to show more timeline rows.

Choose a drawing tool and pause to draw on the frame. Set source Start and End times
before drawing; the default duration is three seconds from the current playhead.
Highlighter and Highlight rectangle default to translucent yellow. Pen, arrow,
rectangle, ellipse and multiline text use the existing screenshot annotation
renderer. Color, width, opacity, fill, font size and text background are adjustable.

Select an annotation in the right Outline to show its timing/style/text and
geometry controls on the left. Select/move pauses playback; drag an object on
the preview to move it with a live outline. Numeric X/Y/Width/Height controls
apply on Enter or focus loss; the Move / resize button also applies them. Text
size changes proportionally, and flat strokes can be given a nonzero extent. Delete annotation removes it. Each annotation has its own timeline row, projected onto the kept clips.
Annotations stay attached to source footage when clips move, and portions on
deleted footage disappear from the edited sequence. Drag its bar to move the time range,
drag its edges to resize duration, or drag the layer name vertically to reorder
overlays. Changes apply to preview, export, project persistence and undo/redo. Undo/Redo covers model edits, including timing, crop, trim,
splits, annotation edits and removal (100 snapshots).

Crop opens a dedicated workspace showing the current frame, an adjustable
selection with eight handles, aspect-ratio presets, X/Y/Width/Height fields and
Apply crop / Cancel / Full frame controls. It uses original video pixels. The
preview shows the applied crop across the entire edited sequence; Adjust crop
reopens the workspace and Clear crop restores the full frame.
Privacy regions are static rectangles for the chosen interval, not trackers.
Blur/pixelation are visible in playback and burned into export; weak blur is not
reliable anonymization. Inspect the final exported file for sensitive content.
Privacy preview uses Pillow Gaussian blur; export uses FFmpeg Gaussian blur, so
the exact appearance can differ slightly.

Export As writes a separate, new MP4 with H.264 video and AAC audio, when present.
Draft, Standard and High choose encoding speed/quality. Export rejects existing
filenames, even after a file-dialog overwrite confirmation; use a new filename.
The original video is never modified. Encoding runs in a worker with progress
and cancellation. The progress row is shown only while exporting. Success hides it and displays
just “Export complete”. Temporary export directories are cleaned on success/
failure/cancellation. Atomic no-clobber publication avoids overwriting a concurrent file.
A failed recording preserves its WebM intermediate and reports its location.

Save Project stores version-1 JSON referencing the source with relative paths,
kept segments, crop and timed annotations. Open Project restores editing state.
Keep the source alongside the project when moving files. Missing source files,
invalid ranges and unsupported project versions produce errors. Projects do not
embed media. Opening or previewing an already saved recording does not prompt
on close. No-op operations do not dirty a project; undoing to its last saved
state removes the warning. Closing prompts only for actual unsaved edits. Quit waits for
recording finalization and export cancellation before allowing closure.

## Modules and reuse

| Module | Responsibility |
|---|---|
| `video/recording.py` | recording settings, worker lifecycle, monotonic timer |
| `video/portal.py` | ScreenCast requests, response cancellation, PipeWire FD/session cleanup |
| `video/gst_helper.py` | isolated system-GI capture pipeline, pause/resume, WebM muxing |
| `video/audio.py` | actual PulseAudio/PipeWire-compatible source discovery |
| `video/system_recordings.py` | completed native recording import via close-write notifications |
| `video/player.py` | Qt Multimedia decoder, frame gating, audio and playback controls |
| `video/sequence.py` | edited/source time mapping in playback, cut skipping and transport |
| `video/canvas.py` | frame-coordinate drawing, timed overlays and privacy preview |
| `video/timeline.py` | playhead, source ranges, trim handles and annotation bars |
| `video/model.py` | validated editing/project model and bounded undo/redo |
| `video/render.py` | shared vector overlays, FFmpeg filter graph, export settings |
| `video/ffmpeg.py` | encoder checks, probing, progress, process cancellation |
| `video/editor.py`, `video/panel.py` | editing workspace and recording navigation |

The image annotation dataclass/painter and region selector are reused. Image
capture and editing modules were not replaced. Large recordings are streamed to
disk and decoded frame by frame; full media never enters project/undo history.

## Platform limits and verification

Wayland uses the ScreenCast portal, not the screenshot portal or direct
framebuffer access. It requests a single monitor or window; actual availability
is controlled by the desktop backend. Portal-selected **monitor** means that
monitor, not the union of every monitor. Wayland region recording authorizes one monitor, snapshots it for selection,
then opens a fresh PipeWire connection in the same authorized session and crops
the live stream before encoding. The preview and recording use native stream
pixel coordinates, independent of the selector’s display scaling. X11 supports full
root-display and frozen-image region selection; live X11 window recording is not
offered. Mixed-DPI/multiple-monitor mapping needs real hardware verification.
No direct framebuffer fallback bypasses denied Wayland permissions.

GStreamer VP8/Opus is used for the capture intermediate because those encoders
are available in Ubuntu's good/base plugins. MP4 finalization is a second encode
and can take time after Stop. Video encoding, privacy preview and large numbers
of full-frame annotation overlays can be CPU/memory intensive. No object tracking,
manual motion keyframes, multitrack composition or separate audio editing is
implemented. Playback codec availability depends on the installed Qt backend.

Automated checks performed on the development host:

- All pre-existing screenshot tests passed.
- Real synthetic FFmpeg tests verify timed highlight pixels, audio preservation,
  crop padding, trim/split duration, privacy filters, cancellation and cleanup.
- A real GStreamer pipeline with synthetic video/audio verifies pause/resume,
  excludes the pause from output duration and produces an audio-bearing MP4.
- Real Qt Multimedia playback outside the sandbox decoded a 320×240 VP8 clip and
  reached its 2.133-second end position. UI wiring is mocked in offscreen CI.
- A live Wayland permission request was attempted, but no source was selected
  before the 45-second test timeout. **Real screen recording remains unverified.**
- X11 recording, actual microphone/system audio synchronization, mixed-DPI,
  multi-monitor and long-recording behavior have not been manually verified.

## Phase delivery record

1. Recording: `recording`, `portal`, `gst_helper`, `audio`, `panel` implement the
   capture flow. Synthetic pause/audio pipeline verified; live desktop check
   incomplete because the chooser received no selection.
2. Playback: `player` and `canvas` implement preview and keyboard controls; actual
   synthetic-clip playback passed outside the restricted sandbox.
3. Essential editing: `model`, `timeline`, `editor` implement trim/split/crop and
   undo/redo. Model tests and actual exported duration/crop checks passed.
4. Annotations: `canvas`, `editor`, `model` reuse the existing image painter;
   timed highlight pixels and privacy export filters tested with real FFmpeg.
5. Export/projects: `render`, `ffmpeg`, `model` implement asynchronous safe export
   and versioned project persistence; round-trip and cancellation checks passed.
6. Integration: launcher tabs, dependencies, packaging, version and docs updated.
   Package construction/inspection is separate from installation verification;
   manual desktop and installation checks below remain required before release.

Run tests with:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/python tools/build_deb.py
```

## Manual release checklist (not yet completed)

- [ ] Ubuntu Wayland: approve monitor sharing, record and inspect the MP4.
- [ ] Ubuntu Wayland: approve window sharing, including permission denial/cancel.
- [ ] Ubuntu X11: full desktop and region; verify selection matches native pixels.
- [ ] Microphone, system monitor, both and no audio; missing/disconnected devices.
- [ ] Synchronization after several pauses/resumes and in final export.
- [ ] Original/720p/1080p output, all frame rates, no upscaling, odd dimensions.
- [ ] Countdown cancellation, stop while paused, close while recording/finalizing.
- [ ] Player controls, seeking, speeds, mute, keyboard/text entry and full screen.
- [ ] Every annotation tool, move/resize, timing edges, undo/redo and text editing.
- [ ] Static blur/pixelation during correct intervals in exported MP4.
- [ ] Trim/split/remove, crop, preview selection and play kept segments only.
- [ ] Export progress/cancel, disk-full and damaged/unsupported video errors.
- [ ] Reopen project after moving project/source together; missing source error.
- [ ] External-player playback of exported MP4 and audio.
- [ ] Long recording, multiple monitors, mixed-DPI and rotated source metadata.
- [ ] Install .deb on its target Ubuntu version and run without a virtualenv.
- [ ] Screenshot capture/editor/save/clipboard regression checks on desktop.

### 0.2.1 build verification

The final local `dist/snapmark_0.2.1_amd64.deb` was built and extracted, its SHA-256
check passed, and the extracted binary returned `SnapMark 0.2.1`. Its bundle
contains `gst_helper.py`, Qt Multimedia and the FFmpeg media plugin. `apt-get -s
install` resolved its dependencies successfully without installing anything.
The application has **not** been installed system-wide as part of this work.
The existing tests and expanded workspace/recording regression suite pass. Tests
include native close-write import, dock/tool behavior, draggable layer ranges,
layer reorder with undo, Wayland area handoff, snapshot completion and actual
GStreamer selected-region output. Rotated video probe/
export and no-upscaling were also checked automatically. A real Qt playback
check of a 90-degree rotated synthetic clip returned a 240×320 display frame from
a 320×240 encoded source, matching the editor's rotated coordinate space.

For the local installer:

```bash
sudo apt install ./dist/snapmark_0.2.2_amd64.deb
snapmark
```


### 0.2.1 workspace fixes

Print Screen was restored on the development desktop and the saved SnapMark
override was disabled. The in-app live Wayland area check was attempted; no
monitor was selected before its 55-second timeout. Live monitor sharing and
area selection therefore remain manually unverified. The automated suite tests
real synthetic snapshot/region pipelines, area cancellation without starting the
recording clock, layer timing movement, stacking order in actual MP4 exports,
native close-write completion and the redesigned dock/tool/outline wiring.

The final 0.2.1 suite passed **97 tests**. Its rebuilt Debian installer passed
SHA-256 verification, extraction, an extracted `--version` check, a short
headless GUI startup smoke check and an apt dependency-resolution simulation.
The actual 0.2.1 system package was not installed by this coding session.


### 0.2.2 clip editing fixes

Video clips now have an explicit sequence order independent of their source
timestamps. Dragging split clips changes that order; deletion ripple-closes the
sequence, updates the duration and changes preview immediately. Saved projects
retain this order. Existing version-1 project JSON remains readable. Annotation
properties continue to refer to source footage, while their timeline bars follow
the edited sequence.

Regression coverage includes clip drag/reorder, deletion while paused, buffered
frame rejection, gap-free edited/source time mapping, undo/redo, reordered project
persistence, source annotations across cuts, wheel zoom, horizontally scrolled
seeking, trim/split after reordering and real MP4 color/order/audio checks. A real
Qt Multimedia check played a blue clip followed by red after deleting the green
clip, and stopped at the correct two-second edited duration.


The 0.2.2 regression suite passed **108 tests**. The rebuilt installer passed
SHA-256 verification, extraction, the bundled sequence-module check and an apt
upgrade simulation. Its extracted executable reports `SnapMark 0.2.2`. The
installer was not installed system-wide by this session.


### 0.2.3 capture, feedback and file controls

The desktop log showed GNOME denying an access dialog because the app had lost
focus. Wayland screenshot requests now keep the requesting window visible and
request the interactive, user-authorized flow. On a version-2 portal, choose
Screen in that system chooser for full-screen capture. The public options are
documented in the [Screenshot portal API](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Screenshot.html).
A live test window was opened, but no capture request was made before its timeout;
the real permission approval flow still needs a desktop retest.

Screenshots are automatically saved before the image editor opens, regardless
of whether automatic editing is enabled. If disk saving fails, the image opens
for recovery and retains an unsaved warning. Saved, unchanged screenshots and
recordings close without that warning. File properties in both editors show
location, size, type, modification time and image/video details, with Open folder
and confirmed Delete from storage. Deleting a source video closes its editor;
projects referencing it will need that source to be restored.

The recording loader remains visible through finalization and MP4 encoding.
Export progress is transient and success shows “Export complete”. Crop has a
dedicated selection dialog. Selection no longer cancels the move gesture, and
geometry edits apply directly without accumulating unchanged history entries.

The 0.2.3 suite passed **122 tests**, including saved-capture clean closing,
Wayland requester visibility, move gestures and live geometry, fractional no-op
properties, text/flat-stroke resizing, save-loader lifetime, export completion
feedback, crop controls, file metadata and confirmed storage deletion. The final
Debian package passed checksum, extraction, bundled-dialog and apt-upgrade
simulation checks; its executable reports `SnapMark 0.2.3`. It was not installed
system-wide by this session.
