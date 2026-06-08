# AirLine — Working Notes

Long-lived divergent branch `airline` off SideLine `main`. AirLine *imports and
calls* the validated CV core; it never edits it. All new work lives under
`AirLine/` and `tests/airline/` only.

---

## SideLine tracker baselines (for eyeballing AirLine runs)

| sport      | model              | tracker        | typical FPS | notes                |
|------------|--------------------|----------------|-------------|----------------------|
| football   | models/football.pt | bytetrack.yaml | ~16–18      | imgsz=1280, GPU      |
| basketball | models/basketball.pt | bytetrack.yaml | ~30 @360p   | imgsz=1280, GPU      |

Validated invocation (mirrored verbatim in `AirLine/core_bridge.py`):
`model.track(source, device=0, stream=True, imgsz=1280, tracker="bytetrack.yaml", persist=True, verbose=False)`

---

## Day 1 — foundation reachable, intact, isolated  (2026-06-08)

**Goal:** stand up `AirLine/` on branch `airline` and prove it can load a clip
and run the *existing* SideLine tracker via import — no new CV, no edits to the
CV core.

### What was built
- Branch `airline` off clean `main`.
- `AirLine/__init__.py`, `core_bridge.py` (the single SideLine import seam),
  `run_day1.py` (CLI proof entry point).
- `tests/airline/test_core_bridge.py` — first AirLine test, mocked detector.

### Baseline (the "before" snapshot, on clean main)
- **68 tests pass** (`.venv` pytest).
- ⚠️ **Pre-existing failure, NOT AirLine's:** `tests/backend/test_video_io.py`
  fails collection — `ModuleNotFoundError: No module named 'scripts.video_io'`.
  Already broken on `main`. Left untouched per PRD. **Flag for Aarav.**

### Day 1 proof run — `python -m AirLine.run_day1 clips/football.mp4 --sport football`
| metric            | value | vs baseline            |
|-------------------|-------|------------------------|
| frames processed  | 540   | —                      |
| avg FPS           | 18.9  | ✅ ≈ football ~16–18    |
| unique track IDs  | 202   | plausible (fragmented IDs expected — known) |
| avg subjects/frame| 24.4  | plausible for 22 players + ball + refs |
- Visible output: `AirLine/outputs/day1_tracks.mp4` (34 MB) — boxes/IDs drawn by
  AirLine from its OWN track data (no Ultralytics `plot()` dependency), proving
  the bridge returns usable tracks.

### Isolation proof (the most important check)
- AirLine tests: **6 passed**.
- Full suite after AirLine: **74 passed** (68 baseline + 6 AirLine); `test_video_io.py`
  error **unchanged** from baseline.
- `git status` shows only `AirLine/` and `tests/airline/` as new — **no tracked
  file modified.** CV core, backend, Website, models, configs all untouched.

### Open items / flags for Aarav
1. Pre-existing `scripts.video_io` import error on `main` (decide: fix or ignore).
2. Not committed/pushed — left for Aarav per PRD.

### Deferred (per PRD, do not start)
Target selection (Day 2) · camera-move/framing (Day 3) · gestures (Day 4+) ·
LLM intent layer · hardware · moving-camera/homography-under-motion.
