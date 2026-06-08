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

---

## Day 2 — the current target (lock-and-follow)  (2026-06-08)

**Goal:** a stand-in input selects ONE subject by track ID; system locks on and
follows it, ignoring all others, and handles the ID disappearing gracefully
(honest `TARGET LOST`, no crash). Pure state logic over Day-1 tracks — zero new CV.

### What was built
- `AirLine/target.py` — `TargetTracker` state machine: `IDLE` / `LOCKED` / `LOST`.
  Sub-threshold gap (default 5 frames) stays `LOCKED` (no overreaction); a
  sustained gap confirms `LOST` and is **sticky** — never silently re-acquires
  (re-ID is a future PRD).
- `AirLine/run_day2.py` — proof entry. Stand-in selection: `--target-id N` or
  `--auto-first` (locks first ID stable ≥3 frames). Renders locked target as a
  thick green box + centre dot, everyone else as thin grey outline, live state
  label top-left.
- `tests/airline/test_target.py` — 8 tests: locked/lost/sub-threshold-gap/idle +
  sticky-lost, reselect, clear, invalid-threshold.

### Before-snapshot (clean start, branch `airline`)
- 74 passed + known `test_video_io.py` collection error unchanged. ✅

### Day 2 proof run — `python -m AirLine.run_day2 clips/football.mp4 --auto-first`
| metric            | value | note |
|-------------------|-------|------|
| locked target id  | 1     | auto-first (stable ≥3 frames) |
| frames            | 540   | — |
| **LOCKED / LOST** | **245 / 293** (IDLE 2) | the fragmentation reality, quantified |
| **first LOST**    | **frame 247 ≈ 8.2 s** @ 30 fps | ID 1 drops here; video shows clean `TARGET LOST`, stays lost (sticky) |
| avg FPS           | 25.7  | ✅ not dropped vs Day 1 — see note below |
- Visible output: `AirLine/outputs/day2_target.mp4` (27 MB) — one highlighted
  subject followed, others de-emphasised, live state label.
- **Fragmentation demonstrated, not hidden:** at ~8.2 s the locked ID vanishes and
  the overlay honestly reads `TARGET LOST` — it does NOT freeze the box or follow
  the wrong subject. 293/540 LOST frames is exactly the re-ID problem to solve later.
- **FPS note:** 25.7 vs Day-1 18.9 — went *up*, not down. The tracker call is
  byte-identical; the difference is overlay cost (Day 1 did a per-detection HSV
  colour conversion + label on ~24 boxes/frame; Day 2 draws thin rects + one
  target). Target-state logic itself is negligible, as expected. No concern.

### Isolation proof
- AirLine tests: **14 passed** (6 Day 1 + 8 Day 2).
- Full suite: **82 passed** (74 baseline + 8 Day 2); `test_video_io.py` error
  **unchanged**.
- `git diff main..airline --stat` + working tree: changes only under `AirLine/`
  and `tests/airline/`. No tracked file outside scope modified. (Day 1 was
  committed by Aarav; Day 2 files left uncommitted per PRD.)

### DECISION — pre-existing `scripts.video_io` error  → option (b) ADOPTED
Standing baseline is **"74 passed + 1 known `test_video_io.py` collection error"**
(now 82 + that 1 known error after Day 2). Reason: option (a) fixing it lives on
`main`/`backend`, **outside** AirLine's hard DO-NOT-TOUCH boundary — not mine to
make. Recorded here so it's a conscious accepted baseline, not a floating crack.
**Aarav:** if you'd rather do (a) (fix `scripts/__init__.py` / import on `main` in
a separate commit), that's still open — it just has to happen outside this branch's
AirLine scope.

### Open items / flags for Aarav
1. `scripts.video_io` error → accepted as baseline (b); (a) still your call.
2. Day 2 files not committed/pushed — left for you per PRD.

---

## Day 3 — virtual cinematography camera (the milestone)  (2026-06-08)

**Goal:** a crop/zoom window that follows the locked target with adaptive
smoothing (calm when gentle, responsive when fast) and, on `LOST`, drifts
smoothly to a wide establishing shot — output that looks like an operated
following shot. Still zero new CV — motion math over the Day-2 target box.

### What was built
- `AirLine/camera.py` — `VirtualCamera` (pure geometry, no I/O, unit-testable).
  - **Adaptive follow:** exponential smoothing on the crop centre whose factor
    scales with target-error (small error → `alpha_min` 0.05 calm; large error →
    `alpha_max` 0.45 snappy), plus a velocity lookahead. Zoom eases tight when
    stable, wider when fast (slow `zoom_alpha` to avoid pumping). All constants
    named in `CameraConfig`.
  - **Drift-to-wide on LOST:** eases from the crop-at-loss to full establishing
    over `drift_frames` (30, smoothstep), then holds. No hunting/panning.
- `AirLine/run_day3.py` — proof pipeline (tracks → target → camera → crop+resize
  → `day3_follow.mp4`), optional `--debug-pip` wide+rect overlay. `--target-id`
  selection is **deferred to first sighting** so a mid-clip subject locks
  correctly (stand-in input only; no contract touched).
- `tests/airline/test_camera.py` — 7 tests: in-bounds-always, stationary-stays,
  gentle-lag, big-jump-responsive-&-bounded (+subject-never-leaves-crop),
  lost-drift-then-hold, idle-wide, aspect-preserved.

### Before-snapshot
- 82 passed + known `test_video_io.py` error unchanged. ✅

### Day 3 proof — `run_day3 clips/football.mp4 --target-id 107 --debug-pip`
(id 107 = longest-lived active subject, 345-frame life; picked over auto-first's
id 1 which is near-stationary.)
| metric | value | note |
|--------|-------|------|
| locked id | 107 | locks on first sighting |
| frames | 540 | LOCKED **350** / LOST **161** |
| **first LOST** | **frame 379 ≈ 12.6 s** | camera drifts to wide here |
| **jitter (LOCKED)** | **2.05 px/frame** mean crop-centre move | smooth, not twitchy |
| fastest target jump | 9 px @ frame 310 | see responsiveness note |
| avg FPS | 16.3 | tracker-bound; crop+resize cheap |
- **Holy-cow output:** `AirLine/outputs/day3_follow.mp4` (22 MB) — a cropped video
  that follows the subject like an operated shot, then eases to a wide shot on loss.
- **Loss behaviour visible & intentional:** at ~12.6 s (frame 379) the locked ID
  drops; the output **drifts smoothly to wide** over ~1 s and holds — no freeze,
  no jerk, no wrong-subject chase. (auto-first / id-1 run drifts at ~8.2 s.)

### Numbers — honesty notes (read before tuning)
- **Smoothness:** 2.05 px/frame mean crop-centre movement while LOCKED → smooth.
  Baseline to compare against future tuning.
- **Responsiveness:** THIS footage cannot exercise it. It's a wide fixed-cam shot;
  the most active long-lived subject peaks at ~9 px/frame and the median is
  ~2–3 px/frame — nobody "breaks fast" in pixel space. Responsiveness is therefore
  validated by the **unit test** (`test_big_jump_is_responsive_and_bounded`:
  camera re-centres a large jump within ≤30 frames without sliding the subject out
  of frame), not by this clip. To feel it on real video, needs footage with faster
  pixel motion (tighter camera / closer action) — flagged for a future clip, not a
  code problem.
- **FPS:** 16.3, essentially tracker-bound (≈ Day-1 18.9). Day-2's 25.7 was the
  outlier — its overlay was ultra-light. Crop+resize+PiP add modest cost. No concern.

### Tuning status (per PRD caveat: working+bounded first, feel later)
Working and bounded ✅ (in-frame always, smooth, drifts on loss). `feel` is a knob:
current values read calm/cinematic on id 107; revisit `alpha_*` / `zoom_*` against
faster footage when available.

### Isolation proof
- AirLine tests: **21 passed** (6 Day 1 + 8 Day 2 + 7 Day 3).
- Full suite: **89 passed**; `test_video_io.py` error **unchanged**.
- Changes only under `AirLine/` + `tests/airline/`. No tracked file outside scope
  modified. Day 3 files left uncommitted per PRD.

### Open items / flags for Aarav
1. `scripts.video_io` error → still accepted as baseline (Day-2 decision b).
2. Responsiveness needs faster-motion footage to show on a real clip (above).
3. Day 3 files not committed/pushed — left for you per PRD.

### Deferred (per PRD, do not start)
Re-identification of a lost target under a new ID (future PRD — today drifts to
wide instead) · gestures / real input modality (Day 4+) · LLM intent layer ·
multiple shot *types* / cinematic vocabulary (orbit, push-in…) · hardware ·
moving-camera/homography-under-motion.
