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

---

## Day 4 — gesture engine + intent wiring (directing by intent)  (2026-06-08)

**Goal:** replace the `--target-id` stand-in with a reusable **gesture engine**
(debounce/confirmation) emitting typed **intent commands**, wired onto the proven
`TargetTracker` + `VirtualCamera`. Tier 1 (subject) + Tier 2 (shot) gestures.

### ⚠️ DEPENDENCY FLAG — MediaPipe NOT installed (Step-2 gate honoured)
MediaPipe is a hard conflict with the validated CV stack — **did not install it**:
| dep | main .venv | mediapipe 0.10.x needs |
|-----|-----------|------------------------|
| numpy | **2.4.4** | **<2** |
| protobuf | **7.35.0** | **>=4.25,<5** |
| (also torch 2.11+cu128, opencv 4.10 — all numpy-2 built) |
Installing would force-downgrade numpy 2→1 and protobuf 7→4 → very likely breaks
ultralytics/torch/opencv. **This is a STOP-and-flag, not a force-install.** Env
left untouched (verified post-build: numpy still 2.4.4, mediapipe still absent).
- Recorded pinned set in `AirLine/requirements-gestures.txt` for an **isolated**
  `.venv-gestures` (python 3.11) that runs ONLY the capture process.
- **Aarav's call:** approve the isolated-venv capture path, or keep the scripted
  driver. Engine/wiring/tests/demo all run with zero mediapipe either way.

### What was built (all import-safe without mediapipe)
- `AirLine/gestures.py` — the engine. `HandClassifier` (pure geometry on 21
  landmarks → POINT/FIST/OPEN_PALM/SPREAD/NONE), `GestureDebouncer` (hold N
  frames → fire once on transition — the Day-2-style anti-flicker), `GestureEngine`
  (classify + horizontal-swipe + debounce), `MediaPipeHandSource` (**lazy** import,
  live path only).
- `AirLine/intent.py` — `IntentCommand` enum, `gesture_to_intent` (the separation
  seam), `IntentApplier` (SELECT nearest-to-ref-x / SWITCH cycle / RELEASE →
  TargetTracker; SHOT_TIGHT/WIDE → camera zoom **via public CameraConfig**, so
  `camera.py` is never edited and no contract changes).
- `AirLine/run_day4.py` — `--source scripted` (default; feeds a raw-label timeline
  through the REAL engine, no webcam/mediapipe) and `--source webcam` (lazy live
  path). Overlays raw gesture / confirmed intent / target / shot / state.
- Tests: `tests/airline/test_gestures.py` (12) + `test_intent.py` (8).

### Before-snapshot
- 89 passed + known `test_video_io.py` error unchanged. ✅

### Day 4 proof — `run_day4 clips/football.mp4 --source scripted`
`AirLine/outputs/day4_gestured.mp4` (22 MB). 7 intents fired exactly on the
scripted holds, driving the cinematography on the football clip:
| frame | intent | gesture |
|------:|--------|---------|
| 35  | select      | POINT (held 6f) |
| 95  | shot_tight  | FIST |
| 150 | switch_next | swipe → |
| 215 | shot_wide   | SPREAD |
| 300 | switch_next | swipe → |
| 365 | shot_tight  | FIST |
| 455 | release     | OPEN_PALM |
- **Debounce demonstrated (the reliability proof):** a deliberate **1-frame FIST
  flicker at f70 did NOT fire** (`flicker fired? False`). On-screen overlay shows
  raw vs confirmed so the gating is legible.
- **Latency number:** confirm window = 6 frames ≈ **200 ms @ 30 fps** (held→fired).
- avg FPS 16.3 (tracker-bound, consistent with Days 1/3).

### Numbers — honesty notes
- **Recognition-rate number is NOT yet measurable.** It needs live MediaPipe + a
  real hand, which is gated on the dependency decision above. Classification
  *logic* is proven by unit tests (crafted landmarks → correct labels incl. the
  confusable OPEN_PALM vs SPREAD pair, separated by finger-span ratio). Real-world
  rate (and the palm-vs-spread confusion check) pends the isolated-venv capture.
- **What the scripted demo proves vs not:** proves the full
  gesture→debounce→intent→target/camera pipeline + on-screen legibility + flicker
  rejection. Does NOT prove webcam recognition robustness (that's the gated part).

### Isolation proof
- AirLine tests: **41 passed** (6+8+7+12+8). Full suite: **109 passed**;
  `test_video_io.py` error unchanged.
- Env unmutated (numpy 2.4.4, no mediapipe). Changes only under `AirLine/` +
  `tests/airline/`. No contract edits to core_bridge/target/camera.

### Open items / flags for Aarav
1. **MediaPipe install decision** (isolated `.venv-gestures` vs keep scripted) —
   your call; `requirements-gestures.txt` ready.
2. Live recognition-rate + palm-vs-spread confusion number pends (1).
3. One judgment call: SHOT_TIGHT/WIDE drive the camera by mutating the public
   `CameraConfig` zoom fractions (not a contract change, camera.py untouched). If
   you'd rather have a dedicated camera shot-API, that's a contract addition →
   flagging rather than deciding it.
4. `scripts.video_io` error still accepted as baseline (Day-2 decision b).
5. Day 4 files not committed/pushed — left for you.

---

## Day 5 — gesture quarantine + named-shot seam (refactor/harden)  (2026-06-08)

Two bounded jobs: (A) stand up the isolated gesture venv + prove the quarantine,
(B) add a thin named-shot API to `camera.py` (the one approved contract edit).

### Part A — isolated `.venv-gestures` + quarantine proof
- Created **`C:\airline-gestures-venv`** (python 3.11.9) — built OUTSIDE the repo
  on purpose: `.gitignore` covers `.venv/` but not `.venv-gestures/`, and editing
  root `.gitignore` is out of scope, so keeping it off-repo keeps `git status`
  clean. (Path is the only deviation from the PRD's `.venv-gestures` name; flagged.)
- **Resolved pins (written back into `requirements-gestures.txt`):**
  mediapipe 0.10.21, **numpy 1.26.4**, **protobuf 4.25.9**, opencv 4.10/4.11.
  → These are exactly the downgrades (numpy 2.4.4→1.26.4, protobuf 7.35→4.25.9)
  that would have broken the main stack. **The Day-4 STOP was correct.**
- **Live mediapipe proven in the isolated venv:** webcam opens (1920×1080 frames),
  `MediaPipeHandSource` instantiates and processes a frame with no error.
  Landmarks returned `None` only because **no hand was in view** — I have no hands.
- **QUARANTINE HELD (required deliverable):** main `.venv` byte-identical before
  AND after — `numpy 2.4.4`, mediapipe absent, full suite green. The two envs
  never merged.

#### ARCHITECTURE FINDING — webcam recognition must be ultralytics-free
`run_day4 --source webcam` is a dead end by design: it imports `core_bridge` →
**ultralytics** (the tracker) AND needs **mediapipe** — two stacks that can't share
a venv (the whole quarantine). A COMBINED live demo (gestures driving the football
crop) therefore needs a future **two-process bridge** (capture proc emits intents →
render proc applies them). But the recognition NUMBER doesn't need the tracker at
all, so it got its own tool:
- **`AirLine/gesture_eval.py`** — imports ONLY `AirLine.gestures` (mediapipe lazy),
  zero ultralytics. Verified to import + run in the gestures venv. Interactive:
  performs each gesture ×N, tallies rate + palm/spread confusion + latency, with a
  live preview window. Pure `summarize()` is unit-tested in the main venv.

#### RECOGNITION NUMBER — FINAL (Aarav at the webcam, 2026-06-08, 10 reps each)
First run exposed two bugs (spread 0/10, swipe 0/10); after fixes, second run:
| gesture | first run | **after fixes** |
|---------|-----------|-----------------|
| point     | 10/10 | **10/10 (100%)** ✅ |
| fist      | 9/10* | **10/10 (100%)** ✅ |
| open_palm | 10/10 | **10/10 (100%)** ✅ |
| spread    | 0/10  | **10/10 (100%)** ✅ (fixed, no calibration even needed) |
| swipe     | 0/10  | **6/10 (60%)** — the 4 misses were `none` (too little travel) |
- *the fist "miss" was a deliberate POINT. palm-vs-spread confusion now **0/0**.
- mean held→fired latency **432 ms** (debounce 6 frames; ≈ the window — not sluggish). ✅
- **Verdict:** 4/5 gestures rock-solid, swipe ~60% (motion-threshold sensitive —
  tune `--swipe-dx` lower for more sensitivity). Per the PRD's "reliable enough to
  demo, not flawless" bar, this **passes**. Part A number = DONE.

#### Three bugs found and fixed (root causes)
1. **SPREAD 0/10** — spread metric normalized fingertip span by *palm length*
   (`wrist→middle-MCP`), never crossing threshold. **Fixed:** `spread_ratio =
   (index-tip..pinky-tip)/(index-MCP..pinky-MCP knuckle span)` — measures fan-out,
   scale/rotation invariant. Threshold 1.2→1.4. (`--calibrate` mode added but the
   default already gave 10/10.)
2. **SWIPE 0/10** — wrist-motion tracking was gated on a clean static pose; a fast
   swipe blurs → `none` → buffer cleared each frame. **Fixed:** track the wrist
   whenever ANY hand is present, pose-independent. Eval is swipe-aware + `--swipe-dx`.
3. **Preview froze after attempt 1** — blocking `input()` starved the GUI loop.
   **Fixed:** gesture_eval is fully preview-driven (SPACE/s/q), frames pump live,
   overlay shows raw label + spread_ratio.

#### Reality check — this webcam layer is a STAND-IN; sensors replace it later
Per the project arc, hand tracking will ultimately be done by **wearable sensors /
a glove**, not a webcam + MediaPipe. So the webcam recognition rate is not a
long-term quality gate — it only had to be "reliable enough to demo the intent
pipeline," which it now is. The durable value is the layering: the glove later
swaps in as a new landmark/label SOURCE behind the SAME `GestureEngine → intent`
seam, and everything downstream (debounce, intents, target, camera, shots) is
reused unchanged. Swipe's 60% and any future gesture flakiness are therefore
**logged findings that may inform the glove design, not blockers** to fix here.

### Part B — named-shot API seam in `camera.py` (first approved contract edit)
Done as a pure ADDITION — motion/follow/drift logic untouched:
- Added `Shot` enum (`AUTO` / `TIGHT` / `WIDE`; marked as the extension point for
  future push-in/orbit — NOT built), `CameraConfig.shot_tight_frac` (0.38) /
  `shot_wide_frac` (0.95), `VirtualCamera.request_shot()` + `.shot`, and a
  `_zoom_target_h()` dispatch. **AUTO branch is byte-identical to Day-3 zoom**, so
  existing `test_camera.py` passes UNCHANGED (proof: a test asserts default-AUTO vs
  explicit-AUTO produce identical crops).
- `intent.py` rewired: SHOT_TIGHT/WIDE now call `camera.request_shot(...)` (says
  "request shot X"); RELEASE resets to AUTO. **No more poking CameraConfig zoom.**
  `IntentApplier(tracker, camera)` (was `tracker, cfg`).
- Shot changes EASE in (same `zoom_alpha`), don't jump — test-asserted.
- Re-rendered `AirLine/outputs/day5_shots.mp4` via `--source scripted` through the
  new seam: identical 7 intents fire (select→tight→switch→wide→switch→tight→
  release), flicker @f70 still rejected → **behaviour-preserving refactor**.

### Isolation proof
- New Day-5 tests: 5 (shot-API: default-AUTO, tight, wide, eased-transition,
  AUTO-unchanged). Existing camera tests pass unchanged.
- AirLine tests: **46 passed**. Full suite: **114 passed**; `test_video_io.py`
  error unchanged. Changes only under `AirLine/` + `tests/airline/`.

### Open items / flags for Aarav
1. **Live recognition number: DONE** — point/fist/open_palm/spread 10/10, swipe
   6/10, palm-vs-spread confusion 0, latency 432 ms (via `AirLine/gesture_eval.py`,
   after fixing the spread metric + swipe motion-tracking). Webcam is a stand-in;
   sensors/glove replace it later behind the same engine→intent seam, so swipe's
   60% is a logged finding, not a blocker. (`run_day4 --source webcam` retired —
   can't mix ultralytics+mediapipe; a combined live demo needs a 2-process bridge.)
2. `.venv-gestures` lives at `C:\airline-gestures-venv` (off-repo) not in the repo
   tree — deviation from the PRD name to keep git clean; relocate if you prefer.
3. Named-shot seam is in; Tier-3 shots (orbit/push-in) are the marked extension
   point, NOT built (need flight-path logic first).
4. `scripts.video_io` error still accepted as baseline (Day-2 decision b).
5. Day 5 files not committed/pushed — left for you.

### Deferred (per PRD, do not start)
**Tier 3 shots (orbit/push-in/dolly) — seam built today, shots NOT** (need
flight-path primitives + simulator first; immediate next major PRD) · new gestures ·
two-hand director's-rectangle · re-identification · LLM intent layer (outer/slow
loop only) · real glove hardware (webcam is its stand-in) · manual flight piloting /
drone / real flight / moving-camera-homography.

---

## Day 6 — two-process live bridge + latency (plumbing day)  (2026-06-08)

**Goal:** split capture (gestures venv) from render (main venv) across a socket so a
hand live-directs the football cinematography; headline = an honest latency breakdown.

### What was built (all reuse Day 1–5 contracts unchanged across the split)
- `AirLine/bridge_protocol.py` — **pure stdlib**, importable by BOTH venvs.
  Newline-delimited JSON `IntentMessage` (intent, ts, seq, payload). `decode()`
  never raises; `is_known()` filters; `KNOWN_INTENTS` unit-tested in sync with
  `IntentCommand`.
- `AirLine/intent_types.py` — **small additive refactor (flagged):** extracted
  `IntentCommand` + `gesture_to_intent` out of `intent.py` into a stdlib-safe module
  (depends only on `gestures`), so the capture process can emit intents WITHOUT
  importing `intent.py` (which reaches `core_bridge → ultralytics`). `intent.py`
  re-exports them → every existing import still works, IntentApplier unchanged.
- `AirLine/bridge_capture.py` — capture process. Real webcam mode (gestures venv:
  `GestureEngine`+`MediaPipeHandSource`, emits on confirmed transitions, stamps a
  live `confirm_ms`) + `--mock` (scripted intents, no mediapipe, runs in main venv).
- `AirLine/bridge_render.py` — render process (main venv). Socket SERVER; **warms
  the YOLO model BEFORE accepting** so model-load never contaminates the latency
  measurement; plays the clip via `core_bridge`, applies received intents via the
  EXISTING `IntentApplier`, overlays live state, writes `day6_live.mp4`, reports
  the breakdown.
- `AirLine/SETUP.md` — documents the two-env setup + rebuild + run commands
  (closes the Day-5 undocumented-env loose end).
- Tests: `tests/airline/test_bridge_protocol.py` (6): round-trip, str/bytes,
  in-sync-with-enum, unknown-filtered, **malformed→None-never-raises** (9 bad
  inputs), and decoded-intent→IntentApplier path.

### THE NUMBER — latency breakdown (REAL: Aarav's hand, webcam capture, 15 intents)
| stage | mean | worst | how measured |
|-------|------|-------|--------------|
| gesture→confirmed | **261 ms** | **318 ms** | **live** — capture stamps raw-pose-start → confirmed |
| **transport+apply** | **35 ms** | **58 ms** | **live** — send-ts → applied in render |
| **~total hand→screen** | **297 ms** | **376 ms** | sum |
- 15 intents (select/tight/wide/release — static gestures; no swipe this run), all
  applied correctly; the football crop reacted live to the hand.
- Clock: both processes share one machine + one wall clock (`time.time()`), so
  transport latency has **no cross-process offset** — stated honestly.
- (Earlier mock run measured transport in isolation at 34 ms mean — matches the live
  35 ms, confirming the mock was a faithful transport proxy.)

### VERDICT — transport is NOT the bottleneck; the debounce is. Feel is GOOD.
The socket bridge adds ~35 ms mean — negligible. Total live latency **~297 ms mean
/ 376 ms worst** is dominated by the **261 ms gesture-confirmation debounce**, exactly
as the PRD hypothesized. ~300 ms hand→screen is **responsive enough to feel direct** —
the live feel is acceptable, not laggy. (Note: live confirm came in at 261 ms, snappier
than the 432 ms Day-5 estimate — the live capture times raw-pose-start→confirm cleanly;
Day-5's higher figure included model warm-up and looser holds.) The two-process backbone
is proven cheap, viable, and de-risked for the future glove/CV-brain split.
- **Levers (logged, NOT implemented today):** shorter debounce window = faster but
  less reliable (swipe was already fragile at 60% — Day 5); lighter serialization
  (already trivial JSON); decouple render FPS from intent rate (already async).
  The only lever that meaningfully moves the number is the debounce, and that's a
  reliability trade — a dedicated tuning decision, not a blind change.

### Measurement provenance (all REAL now)
Both stages measured live: transport+apply from the real socket+clock; gesture→confirmed
from Aarav's webcam (capture stamps raw-pose-start→confirmed). The earlier mock run only
existed to measure transport before a hand was available — its 34 ms matched the live
35 ms, so it was a faithful proxy. **No placeholder numbers remain.**

### Graceful-exit fix
The live run ended with a `ConnectionAbortedError` (WinError 10053): render closes the
socket when the clip ends, capture tried to send one more intent. Harmless (all numbers
captured) but ugly → **fixed**: `bridge_capture.run_real` now catches `ConnectionError`
on send and exits cleanly ("render disconnected — stopping").

### Isolation proof
- New Day-6 tests: 6. Full suite **121 passed**; `test_video_io.py` error unchanged.
- **Both venvs intact**: main numpy 2.4.4 / no mediapipe; gestures mediapipe 0.10.21
  / numpy 1.26.4. **Capture stack imports in the gestures venv with zero ultralytics**
  — the seam holds across the process boundary.
- Changes only under `AirLine/` + `tests/airline/` (+ `AirLine/SETUP.md`). No Day 1–5
  contract modified (intent_types extraction is additive + re-exported).

### Open items / flags for Aarav
1. **Real hand→screen latency: DONE** — 297 ms mean / 376 ms worst (261 ms confirm +
   35 ms transport), 15 live intents, crop reacted live. Feel is good. ✅
2. `intent_types.py` extraction is the one structural change — additive, re-exported,
   all 121 tests green. Flagging since it touched `intent.py`'s imports.
3. Day 6 files not committed/pushed — left for you.

### Day-6 deferred (unchanged)
Tier 3 shots (next major PRD: flight-path + simulator) · LLM intent layer attaches
HERE later as a slow outer intent consumer/producer · glove replaces capture process
behind this same protocol · drone/flight/moving-camera-homography.

---

## Day 7 — first 3D flight-path primitive: ORBIT  (2026-06-08)

**Goal:** first time AirLine computes a **camera pose in 3D space over time** (not a 2D
crop). ONE primitive — orbit — as a genuine 3D trajectory in a **tiltable plane** (level
= special case), proven by 3D invariants, two schematic views, behind the Day-5 seam.

### What was built
- `AirLine/flightpath.py` — `OrbitPath` + `CameraPose` + `look_at`. Pure 3D kinematics,
  documented convention (X right, Y depth, **Z up**). Circle of fixed radius in a plane
  (center, radius, plane_normal), constant angular speed, camera always looking at center;
  center can be supplied per-step (**moving target**). Deterministic, no I/O.
- `AirLine/sim_orbit3d.py` — BOTH views off the real path: rotating mpl-3D plot +
  tri-view orthographic (top XY / side XZ / front YZ). ffmpeg available → mp4 (Pillow GIF
  fallback wired but unused).
- Seam (additive, pre-approved): `Shot.ORBIT`, `IntentCommand.SHOT_ORBIT`,
  `_INTENT_TO_SHOT[SHOT_ORBIT]=ORBIT`, `KNOWN_INTENTS += shot_orbit`. No gesture maps to
  orbit (per PRD — circular-hand-motion is its own reliability problem). The 2D camera
  treats ORBIT as a crop pass-through (no view synthesis); tight/wide/AUTO **unchanged**.
- `AirLine/run_day7.py` — drives orbit via the intent path, prints invariants, renders
  both videos. Tests: `tests/airline/test_flightpath.py` (10) + 2 seam/regression tests.

### NUMBERS — 3D invariants hold to machine precision (the real proof)
| orbit | 3D radius (mean / dev) | look-at err max | out-of-plane max | altitude dev | period closure |
|-------|------------------------|-----------------|------------------|--------------|----------------|
| level (n=+Z)   | 4.0000 / 4.4e-16 | 0.0e0 deg | 0.0e0 | **0.0000** (level) | 9.8e-16 |
| tilted 35° (static) | 5.0000 / 1.8e-15 | 1.5e-6 deg | 2.7e-15 | **5.74** (tilted) | 1.2e-15 |
| tilted 35° + moving target | 5.0000 / 1.8e-15 | 1.5e-6 deg | 2.7e-15 | 5.74 | n/a (center moves) |
- Constant-radius, look-at, in-plane, period-closure, constant-angular-speed, moving-target,
  and level-altitude-constant all verified (10 invariant tests).
- **Tilt genuinely demonstrated:** altitude varies 5.74 m on the tilted orbit, exactly 0 on
  the level one — altitude-constant asserted ONLY for the level case (NOT a false invariant
  for tilted).
- Seam: `SELECT→lock id, SHOT_ORBIT→camera.shot=orbit` (OK); `test_camera.py` **12 passed
  unchanged** (tight/wide/AUTO regression proof).

### Two visible proofs
- `AirLine/outputs/day7_orbit_3d.mp4` (rotating 3D) and `day7_orbit_triview.mp4`
  (top/side/front) — camera on a constant-radius circle in a tilted plane, always looking
  at a *moving* target. The tri-view is the lie-catcher: drift/ellipse/off-look-at would
  show in an orthographic panel even if the 3D plot looked fine.

### ⚠️ LOCALIZATION CAVEAT (do NOT gloss — path is 3D, depth & view are NOT)
- The orbit **path is rigorous 3D** (invariants above, machine-precision).
- BUT a real subject's **3D depth is approximated**: the fixed football cam gives a 2D image
  position only; a real orbit center would come from a documented 2D→ground-plane assumption
  (subject on flat ground). For proving the *path math* this is fine — here run_day7 defines
  the world exactly (synthetic target), so no approximation is even invoked yet.
- **No view synthesis exists:** there is NO real imagery of the subject from the orbiting
  camera's poses (the clip is one fixed viewpoint). The sim shows where the camera *would be*
  and roughly frame — **schematic matplotlib, not a rendered view.**
- Genuinely deferred to a real moving camera / multi-view capture (the actual drone):
  **true 3D target localization** and **view-from-pose synthesis**. Path = rigorous 3D;
  target depth & view = approximated/deferred.

### Isolation proof
- New Day-7 tests: 12. Full suite **133 passed**; `test_video_io.py` unchanged.
- `test_camera.py` unchanged (12 pass) — 2D motion logic untouched; orbit is an additive
  3D mode. Main venv numpy 2.4.4 / no mediapipe; both venvs intact. Changes only under
  `AirLine/` + `tests/airline/`.

### Open items / flags for Aarav
1. Orbit path proven in 3D; **target depth (2D→ground) and view-from-pose are the deferred
   real-drone pieces** (caveat above) — stated, not glossed.
2. Day 7 files not committed/pushed — left for you.

### Day-7 deferred (per PRD)
Push-in & dolly (next primitives — reuse this `flightpath` machinery) · spiral/radius-ramp/
height-ramp orbits (different primitives; today = circle in a tiltable plane) · webcam
gesture for orbit (own reliability problem) · real 3D rendering / photoreal view synthesis ·
real drone flight dynamics · true 3D localization / homography-under-motion · re-ID · LLM
intent layer · glove · actual drone/flight.
