# AirLine — Day 3 PRD

**Date:** (fill in)
**Project:** AirLine (gesture-directed, scene-aware cinematography layer) on the SideLine CV pipeline
**Branch:** `airline` (continue on the same long-lived branch)
**Builds on:** Day 1 (`core_bridge`), Day 2 (`TargetTracker`: `IDLE`/`LOCKED`/`LOST`, sticky-lost)

---

## Goal for the day (ONE sentence)

Render a **virtual cinematography camera** — a crop/zoom window that follows the locked target with **adaptive smoothing** (calm when the subject moves gently, responsive when they break fast) and, when the target is `LOST`, **drifts smoothly to a wide establishing shot** — producing an output video that *looks like an operated following shot*, not boxes on a wide field.

This is the visual milestone: the first time AirLine looks like the actual idea.

**Still zero new CV.** Everything today is motion math over the target box `TargetTracker` already provides. No new detection, no re-ID, no scene understanding.

---

## Why this is the right Day 3 (context for the agent)

Day 2 quantified the hard truth: the locked target's ID survives ~8s then drops (245 LOCKED / 293 LOST of 540 frames on the football clip). Day 3 turns that reality into *style* rather than breakage: a real camera operator who loses their subject eases back to a wide shot and waits — they don't freeze mid-push or jerk around. Implementing that makes the LOST majority of frames look intentional. The novelty of the whole project is "the system films like a thoughtful operator"; Day 3 is the first concrete taste of it.

---

## The two behaviours to build (the heart of the day)

### 1. Adaptive follow smoothing (Aarav's explicit design call)
Not a single smoothness setting. The virtual camera centre should:
- Move **smoothly/slowly by default** when the target is near frame centre and moving gently (cinematic, unhurried).
- Become **more responsive as the target's distance from frame centre grows**, so a sudden sprint/cut is caught quickly instead of sliding off-frame.
- Suggested implementation (agent may refine, but keep the *intent*): an exponential smoothing on the camera centre where the smoothing factor scales with target-error magnitude (small error → heavy smoothing → calm; large error → light smoothing → snappy). Optionally add a small velocity/lookahead term so fast motion is anticipated, not merely chased. Expose the key constants as named, tunable parameters (do not hardcode magic numbers inline).
- Zoom/crop size should also ease (e.g. tighter when the subject is stable and centred, slightly wider when motion is fast) — gently; avoid nauseating zoom pumping.

### 2. Drift-to-wide on target loss (Aarav's explicit design call)
- On entering `LOST` (the sticky state from Day 2), the camera **smoothly interpolates** from its current crop to a **wide establishing framing** (full-field or a sensible wide bound) over a short, eased duration. No hard cut, no freeze, no jerk.
- It **holds** the wide shot while `LOST` persists (it does NOT hunt or pan around looking — that would imply re-ID, which is deferred).
- This is the fallback that makes the 293 LOST frames look deliberate. "Hold last frame" is acceptable only as the very first instant before the drift begins; the steady-state lost behaviour is the wide shot.

---

## Modules the agent MAY touch

- New files in `AirLine/` (e.g. `camera.py` for the virtual-camera logic, `run_day3.py`).
- New tests in `tests/airline/`.
- `PRD/`.
- May read/call `core_bridge.py` and `target.py` — **do not alter their contracts.**

## DO NOT TOUCH list (hard constraint — unchanged)

- Any SideLine CV script, model, config, tracker tuning.
- `backend/`, `Website/`, existing `tests/backend/`, `tests/frontend/`.
- The `core_bridge` `model.track(...)` invocation and the `TargetTracker` state-machine contract from Day 2 (consume them; don't rewrite them).
- **Nothing outside `AirLine/` and `tests/airline/` may be modified.**
- Must edit core or change a Day 1/Day 2 contract? STOP and flag for Aarav. Don't decide it.

---

## Steps

1. **Clean start.** Branch `airline`, tree clean. Re-run suite, confirm standing baseline: **82 passed + the known `test_video_io.py` collection error unchanged.** Record as "before."

2. **Write `AirLine/camera.py` — a `VirtualCamera`.** Pure geometry/motion, no CV. Given per-frame (target box or `None`, current state from `TargetTracker`, frame size), it maintains a smoothed crop rectangle (centre + size) implementing the two behaviours above, and returns the crop to apply. Keep tunables named at the top. No I/O, no rendering inside this class — it just computes the crop (so it's unit-testable without video).

3. **Write `AirLine/run_day3.py` — the proof entry.** CLI: clip, sport, target selection (reuse Day 2's `--target-id` / `--auto-first`). Pipeline per frame: `core_bridge` tracks → `TargetTracker.update` → `VirtualCamera` → apply crop and resize to a fixed output resolution → write `AirLine/outputs/day3_follow.mp4`. Recommend also writing an optional side-by-side or picture-in-picture (wide view with the crop rectangle drawn) for debugging/eyeballing — but the primary deliverable is the *cropped following-shot* video.

4. **Tests in `tests/airline/test_camera.py`** (synthetic data, no real clip, fast/deterministic). At least:
   - Stationary centred target → crop stays put (heavy smoothing; near-zero jitter).
   - Target makes a large jump → camera moves toward it within a bounded number of frames (responsiveness kicks in), and does NOT overshoot wildly.
   - Small gentle target motion → camera lags gently (smooth, not snappy) — assert it does NOT jump immediately.
   - State goes `LOST` → crop converges toward the wide framing over the eased duration and then holds (no hunting).
   - Crop rectangle always stays within frame bounds (never crops outside the image).

5. **Re-run full suite.** Equals Step 1 baseline + new Day 3 tests; `test_video_io.py` error unchanged.

---

## Definition of Done (measurable — no "it should work")

- [ ] **The "holy cow" output:** `AirLine/outputs/day3_follow.mp4` is a cropped video that visibly *follows your locked subject like an operated shot* — smooth on gentle motion, catching up on fast motion.
- [ ] **The loss behaviour is visible and looks intentional:** at the ~8.2s mark (frame ~247) where Day 2 logged the ID drop, the output shows a **smooth drift to a wide shot**, not a freeze or jerk. Confirm by eye and note it in notes.md.
- [ ] **A number — smoothness sanity:** report a simple jitter metric for the LOCKED phase, e.g. mean per-frame movement of the crop centre (px/frame), to confirm it's smooth rather than twitchy. (A rough proxy is fine; the point is a number you can compare against future tunings.)
- [ ] **A number — responsiveness sanity:** identify one fast-motion moment and report roughly how many frames the camera takes to re-centre the subject (should be small, not sliding off-frame). Eyeball-level is acceptable.
- [ ] `tests/airline/test_camera.py` passes (stationary / big-jump / gentle-lag / lost-drift / in-bounds).
- [ ] Full suite green at baseline + Day 3 tests; `test_video_io.py` error unchanged.
- [ ] `git diff` shows changes **only** under `AirLine/`, `tests/airline/`, `PRD/`.
- [ ] FPS reported; if it dropped a lot vs Day 2, investigate (crop+resize is cheap; a big drop means something's off) — flag rather than hand-wave, Day-2 style.

---

## Rollback note

Additive files on the isolated branch; Day 1/Day 2 states intact in history, `main` untouched. No new heavy deps expected (OpenCV crop/resize already in use). New dependency? Flag first.

---

## A tuning caveat (so you're not surprised)

Adaptive smoothing has *feel* — the first parameter values will probably be slightly off (too floaty or too twitchy). That's expected and not a failure; it's a knob to turn while watching the output, exactly the "watch the video, don't just trust the metric" discipline from your SideLine work. Get it *working and bounded* first (correct behaviour, stays in-frame, drifts on loss); make it *feel great* second. Don't let perfect feel block a working Day 3.

---

## Explicitly NOT in scope today (deferred — do not start)

- Re-identification / re-acquiring a lost target (future PRD — today we drift to wide instead).
- Gesture vocabulary or real input modality (Day 4+).
- LLM intent layer (later; outer loop only, never per-frame).
- Multiple shot *types* / a cinematic intent vocabulary (orbit, push-in, etc.) — Day 3 is a single "follow + lose gracefully" behaviour; the richer vocabulary comes later.
- Drone, simulator, glove, any hardware.
- Moving-camera / homography-under-motion.

---

## Note to the agent (Claude Code)

Same principle: motion/geometry code and tests inside `AirLine/` are yours; anything touching the CV core, tracker, or the Day 1/Day 2 contracts is **Aarav's call** — surface it. Do not "fix" the target-loss problem by secretly re-acquiring a new ID to keep the shot going — the drift-to-wide is the intended, honest behaviour and re-ID is deliberately deferred. Close by filling in the measurements, notes.md-style. This is the milestone day; the bar is an output video Aarav can watch and feel the idea working.
