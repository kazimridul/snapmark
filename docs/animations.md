# Video animations

Open a video, draw/select a layer, then click the sparkle **Animations** action.
The target selector switches between the whole video, annotation layers and
existing clip joins. Double-click a layer on the timeline to animate it. Click
**IN**, **OUT**, or a join badge on the video track for those settings directly.

Choose Entrance, Emphasis or Exit, then a preset. Only applicable controls appear.
Effect-specific properties come first, followed by duration, delay and easing.
Expand **Timing, repeat and range** for custom local start/end times, repeat
count, reverse and alternate playback. Seconds and pixel units are shown beside
numeric controls; colors use a picker. Reset restores the selected effect's
defaults. Choosing None removes that phase's effect.

The embedded preview shows the edited video. Preview plays the selected phase;
Stop pauses it. Edits are drafts until Apply. Cancel restores the prior effects
and playhead. Apply is one undoable change. Save Project retains every setting;
MP4 export uses the same animation compositor as the preview.

## Annotation presets

| Phase | Presets |
|---|---|
| Entrance | Fade In, Zoom In, Pop In, Slide In Left/Right/Top/Bottom, Wipe In, Draw On, Sweep In, Typewriter, Blur In, Rotate In |
| Emphasis | Pulse, Zoom In/Out, Shake, Bounce, Glow, Flash, Breathing, Blink, Floating, Continuous Highlight, Rotate, Wobble, Border Pulse, Blur Pulse, Color Change |
| Exit | Fade Out, Zoom Out, Shrink, Slide Out Left/Right/Top/Bottom, Wipe Out, Dissolve, Draw Erase, Blur Out, Rotate Out, Pop Out |

All phases also include None. Each preset exposes its own properties: opacity,
scale, overshoot, offset, direction, reveal speed, angle, anchor, particle size,
colors, blur, border width, frequency, distance or intensity where applicable.
Typewriter applies to text and offers Duration or Typing speed timing, character
order and cursor visibility. Draw On/Draw Erase apply to pen, highlighter, arrows,
rectangles and ellipses. Border Pulse applies to rectangles and ellipses and
preserves their fill. Blur/pixelation privacy regions remain static.

Emphasis speed/frequency is measured in cycles per second. Repeat count 0 means
continue until the emphasis range ends; entrance/exit repeats use finite counts.
Draw reveal/erase speed multiplies the selected duration. Typewriter's Typing
speed mode derives its cycle length from text length and characters per second.
The UI disables the unused timing control.

By default entrance starts with the layer, emphasis spans its visible lifetime,
and exit finishes at its end. Custom start/end values are offsets from the
layer's source start. Delay postpones the start within that range. Short layers
clip effects to their available time; a range with no visible interval does not
render an effect. Entrance and exit may overlap on short layers, in which case
their transforms/opacity combine. Annotations and their effects follow source
footage when clips are moved or deleted. Hidden portions on deleted footage do
not appear in preview or export.

## Whole video and clip joins

Whole video offers applicable entrance/exit effects in edited-sequence time.
Typewriter, Draw On/Erase and continuous emphasis are layer effects. Global
transforms act on the cropped frame when a crop is active. Slide defaults use
that frame's dimensions.

Joins offer Fade, Wipe, Blur, Zoom and Dissolve **through color**, with duration,
easing, color and optional audio fade. Wipe adds direction, Blur adds strength,
Zoom adds minimum scale and Dissolve adds particle size. Each outgoing clip moves
toward the chosen color, then the incoming clip reveals from it. These effects
do not overlap footage or shorten the video. The actual duration is clamped to
available neighboring clip lengths. Audio optionally fades down/up across the
same interval. A join remains attached to its outgoing/incoming source cut;
reordering away from that adjacency makes it inactive.

## Persistence, performance and verification

Version-2 projects store animations and transitions. Older version-1 projects
open with None effects; keep the referenced source file with your project.
Exports preserve the source and write a new MP4. Animated exports stream decoded
frames through the CPU compositor; high-resolution blur/glow/dissolve and many
layers can be slower. Frames are processed incrementally. Videos without active
animations retain the existing FFmpeg filter export path.

Automated coverage samples every annotation preset, all five joins, timing,
applicability, project migration, undo, crop transforms, contextual controls,
text positioning and border-fill behavior. Real FFmpeg tests check exported
opening/ending/join pixels, audio presence, duration and cancellation cleanup.
A live Qt Multimedia test played reordered synthetic clips with an animated
layer, opening, join and exit; it reached the correct end without player errors.
Large/long videos and all presets on real desktop hardware still need manual
performance and visual checks.
