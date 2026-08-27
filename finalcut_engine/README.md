# FinalCut Engine

A professional-grade, Final Cut Pro–style video editing **engine** — not an
application. It is the computational foundation a modern macOS/Apple Silicon
NLE would be built on: a magnetic timeline, a professional media pipeline
(ProRes/proxy workflow, multicam, non-destructive audio/colour/effects/motion),
optional AI assistance, and a node-based GPU-ready render/export pipeline.

```
IMPORT MEDIA -> MEDIA ANALYSIS -> LIBRARY -> EVENT -> PROJECT
    -> MAGNETIC TIMELINE -> EDITING -> AUDIO -> COLOUR -> EFFECTS -> MOTION
    -> AI ASSISTANCE -> RENDER -> EXPORT
```

## Quick start

```bash
pip install -r finalcut_engine/requirements.txt
python -m finalcut_engine.examples.demo_film   # runs the full pipeline end-to-end
pytest finalcut_engine/tests/                  # 59 tests covering every subsystem
```

The demo and test suite use deterministic **synthetic media** (procedurally
generated frames/audio) rather than real video files, so the whole engine —
import through export — is exercisable without shipping sample footage or an
FFmpeg install.

## Architecture

Every subsystem lives in its own package and can be used independently —
`timeline` has no import-time dependency on `colour`, `colour` has none on
`ai`, and so on. `core.engine.FinalCutEngine` and `api.engine_api.EngineAPI`
are the only places that wire everything together, and only because a UI
needs one object to hold onto; nothing about the timeline, colour, or audio
math requires the engine facade to exist.

```
core/          Timebase (CMTime-style rational time), event bus, undo/redo
               command engine, Project, and the FinalCutEngine facade.
media/         Metadata, import (ffprobe + a synthetic prober for tests),
               technical analysis, thumbnails, waveform extraction.
library/       Library -> Event -> Project hierarchy, keywords, ratings,
               favourites, smart collections.
timeline/      The magnetic timeline: Storyline, Clip/Gap/Transition,
               ConnectedClip, CompoundClip. See "The magnetic timeline" below.
multicam/      Camera angles, timecode/waveform sync, angle switching.
audio/         SOURCE -> GAIN -> EQ -> COMPRESSOR -> EFFECTS -> LIMITER ->
               MASTER audio graph; EQ/compressor/limiter/noise-reduction DSP.
colour/        SOURCE -> BALANCE -> EXPOSURE -> COLOUR -> LUT -> LOOK ->
               OUTPUT non-destructive colour pipeline; 3D LUTs; smart
               colour matching.
effects/       Stackable, keyframeable, maskable effects (blur, sharpen,
               vignette, noise, distortion, stabilisation) + blend modes.
motion/        Keyframes/easing, 2D transforms (affine warp), titles,
               generators, and the glue tying keyframes to transforms.
ai/            Optional, non-destructive suggestions: scene detection,
               object/face detection, speech-to-text, highlight detection,
               auto-edit, colour matching, semantic search.
render/        The per-clip render graph (SOURCE -> TRANSFORM -> CROP ->
               COLOUR -> EFFECT -> COMPOSITE -> TEXT -> OUTPUT), an LRU
               render cache, proxy/ProRes-ladder policy, a priority
               background job queue, and a CPU/GPU compute-backend seam.
export/        ProRes/H.264/HEVC profiles, named presets (Master, ProRes,
               H.264, HEVC, Web, Social, Archive, Audio-only), and an
               exporter with its own timeline-independent export graph.
optimisation/  Scheduling policy, a unified-memory-aware cache budget, a
               CPU/GPU work router, and a performance monitor with automatic
               bottleneck diagnosis.
persistence/   SQLite project database (transactions, integrity checks),
               project save/load, versioning, autosave/crash recovery.
api/           EngineAPI: the one high-level surface a UI needs, wrapping
               every mutating operation in a reversible Command.
examples/      demo_film.py: an end-to-end walkthrough of every subsystem.
tests/         59 tests covering timeline math, magnetic relationships,
               trimming/ripple/roll edits, multicam sync, the audio and
               colour DSP, render-graph cache correctness, export, undo/redo,
               and persistence/crash-recovery.
```

### The magnetic timeline

The core design decision: **no timeline item stores its own position.** A
`Storyline` is an ordered list of items (`Clip`, `Gap`, `Transition`,
`CompoundClip`); an item's position is always the sum of the durations of
everything before it. `ConnectedClip`s attach to a primary-storyline item by
id plus an offset from that item's start, not by an absolute time.

The payoff: every ripple-style edit (`ripple_trim`, `delete_clip(ripple=True)`,
`move_clip`) only has to touch the one item being edited. Everything
downstream — later clips, and anything connected to them — is automatically
in the right place the next time its position is asked for, with zero extra
bookkeeping. `timeline/magnetic_timeline.py`'s and `timeline/storyline.py`'s
docstrings walk through the trim/ripple/transition math in detail.

### Native Apple Silicon integration points

This is a Python prototype; it does not pretend to provide hardware
acceleration it doesn't have. Every place a native implementation would plug
in is an explicit, documented seam rather than a hidden assumption:

- `render/gpu.py` — `ComputeBackend` protocol; `MetalBackend.run()` raises
  clearly rather than silently running on the CPU and calling itself
  accelerated.
- `media/importer.py` — `MediaProbe` protocol; swap in an `AVAsset`-backed
  prober for real files.
- `render/proxy.py` — the ProRes ladder and proxy-switching *policy*; pixel
  transcoding is a VideoToolbox/AVFoundation concern.
- `ai/object_detection.py`, `ai/face_detection.py`, `ai/speech_to_text.py` —
  each ships a genuinely functional, dependency-free reference
  implementation (colour-threshold blob detection, energy-gated voice
  activity detection) plus a named extension point for a real model.
- `motion/titles.py` — `GlyphRenderer` protocol; the default renderer draws
  correct-by-construction placeholders (7-segment digits, word-shaped
  blocks) rather than a hand-rolled, unverifiable pixel font.

## Non-destructive by construction

Original media is never modified. Clips reference source media by id plus an
in/out range; effects, colour grades, and transforms are configuration
objects attached to a clip, re-evaluated by the render graph on demand.
AI analyzers return `ai.Suggestion` objects — accept/reject — and never
mutate the project themselves.
