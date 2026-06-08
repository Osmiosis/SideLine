# AirLine — Day 2 PRD

**Date:** (fill in)
**Project:** AirLine (gesture-directed, scene-aware cinematography layer) on the SideLine CV pipeline
**Branch:** `airline` (continue on the same long-lived branch from Day 1)
**Builds on:** Day 1 (`core_bridge.py`, `run_day1.py`, passing isolation proof)

---

## Goal for the day (ONE sentence)

Given the tracks AirLine already produces, let a **stand-in input select one subject by track ID**, and have the system **lock onto and follow that subject** through the clip — ignoring all others — while **handling the target's ID disappearing gracefully** (the known fragmentation case), with no crash and a clear visible state.

No camera moves yet. No gestures yet. No new CV. Today is *target state management*: who is the system paying attention to, and what happens when it loses them.

---

## Why this is the right Day 2 (context for the agent)

Day 1 proved AirLine can read SideLine's tracks. Day 2 is the first behaviour SideLine never had: a notion of **"the current target."** Everything downstream (camera framing on Day 3, gestures on Day 4+, the whole novelty) depends on a reliable answer to "which subject are we filming right now." This is pure logic over existing track data — still zero new perception.

**Critical known issue (from notes.md):** track IDs fragment — ~202 unique IDs appeared for ~24 real subjects, because ByteTrack drops and reacquires players, assigning a new ID on reacquisition. Therefore "lock onto ID 7" is inherently fragile: ID 7 may simply vanish partway through as the same player becomes ID 143. **Day 2 does NOT solve re-identification.** Day 2 must instead *detect* that the locked target's ID has disappeared and enter a clear, non-crashing "target lost" state. Re-ID is explicitly deferred.

---

## Modules the agent MAY touch

- New files inside `AirLine/` (e.g. `target.py`, `run_day2.py`).
- New tests in `tests/airline/`.
- `PRD/` (this file).
- May *read from and call* `core_bridge.py` (do not rewrite its seam contract).

## DO NOT TOUCH list (hard constraint — unchanged from Day 1)

- Any existing SideLine CV script, model, config, or tracker tuning.
- `backend/`, `Website/`, existing `tests/backend/`, `tests/frontend/`.
- The validated `model.track(...)` invocation inside `core_bridge.py` — Day 2 consumes its output, it does not alter how tracking is done.
- **Nothing outside `AirLine/` and `tests/airline/` may be modified.**
- If the agent believes it must edit core code or change the `core_bridge` contract, it STOPS and flags it for Aarav. It does not decide this itself.

---

## Steps

1. **Confirm clean start.** On branch `airline`, working tree clean. Re-run the full suite and confirm the **Day 1 baseline: 74 passed, plus the known pre-existing `test_video_io.py` collection error unchanged.** Record this as today's "before."

2. **Write `AirLine/target.py` — a `TargetTracker` (state manager, not a CV model).** Responsibilities:
   - Hold the currently selected target track ID (or `None`).
   - `select(track_id)` — lock onto a subject.
   - `update(frame_tracks)` — given one frame's tracks, find the locked ID. Return a small status object: one of `LOCKED` (target present this frame, with its box), `LOST` (target ID not present this frame), or `IDLE` (nothing selected).
   - Track how many consecutive frames the target has been missing. After a configurable threshold (e.g. N frames), transition from a transient miss to a confirmed `LOST` state. (Rationale: a 1-frame gap is normal jitter; a sustained gap is real loss. Don't overreact to single-frame drops.)
   - **No re-acquisition logic.** When lost, it stays lost and says so. Re-ID is a future PRD.

3. **Write `AirLine/run_day2.py` — the proof entry point.** CLI: clip path, sport, and a way to specify the target (e.g. `--target-id 7`, or `--auto-first` to lock the first stable ID seen). It:
   - Runs tracks via `core_bridge` (exactly as Day 1).
   - Feeds each frame to `TargetTracker`.
   - Renders output where the **locked target is visually distinct** (e.g. highlighted box / different colour) and **all other subjects are de-emphasised** (dimmed or thin outline). On-screen text shows current state (`LOCKED id=7` / `TARGET LOST` / `IDLE`).
   - Writes `AirLine/outputs/day2_target.mp4`.

4. **Stand-in input for selection (NOT gestures — that's Day 4+).** Keep it dead simple and deterministic: a CLI arg, or an interactive keypress to cycle the locked ID among currently visible IDs. The point today is the *lock-and-follow behaviour*, not the input modality. Do not build a gesture or fancy UI; it would be wasted work replaced later.

5. **Write tests in `tests/airline/test_target.py`.** Cover at least:
   - Selecting an ID present in synthetic frames → `LOCKED` with correct box.
   - Target ID absent for > threshold frames → `LOST`.
   - Single-frame gap under threshold → stays `LOCKED` (no overreaction).
   - No selection → `IDLE`.
   - Use synthetic/mocked frame-track data (fast, deterministic) — do not require a real clip in the unit tests.

6. **Re-run full suite.** Must equal the Step 1 baseline plus the new Day 2 tests, with the pre-existing `test_video_io.py` error **still unchanged**.

---

## Definition of Done (measurable — no "it should work")

- [ ] **A visible output:** `AirLine/outputs/day2_target.mp4` clearly shows ONE highlighted subject being followed while others are de-emphasised, with a live on-screen state label.
- [ ] **The fragmentation case is demonstrated, not hidden:** find (or note the timestamp of) a moment in your real football clip where the locked target's ID drops, and confirm the video shows a clean `TARGET LOST` state there rather than a crash, a frozen box, or silently following the wrong subject. Write the timestamp in notes.md.
- [ ] **A number:** report how many frames the target was `LOCKED` vs `LOST` vs total over the clip (e.g. "LOCKED 410 / LOST 130 / 540"). This quantifies the fragmentation reality you're up against — useful data for the future re-ID decision.
- [ ] `tests/airline/test_target.py` passes, covering locked / lost / sub-threshold-gap / idle.
- [ ] Full suite green at **Day 1 baseline + Day 2 tests**; pre-existing `test_video_io.py` error unchanged.
- [ ] `git diff` shows changes **only** under `AirLine/`, `tests/airline/`, `PRD/`. Nothing else.
- [ ] FPS unchanged from Day 1 within noise (target state logic is cheap; if FPS dropped meaningfully, something is wrong — flag it).

---

## Rollback note

Day 2 is additive files on the same isolated branch. If it goes wrong, the Day 1 state is intact in git history and `main` remains untouched. No new dependencies expected; if the agent wants to add one, it flags it first.

---

## Decision waiting on Aarav (carried from Day 1 — resolve today)

The pre-existing `scripts.video_io` collection error on `main`. **Choose one and write it in notes.md:**
(a) fix it on `main` in a separate commit (keeps the baseline clean), or
(b) formally accept "74 passed + 1 known collection error" as the standing baseline so it's never mistaken for AirLine breakage.
Either is fine — but make it a conscious decision, not a floating crack.

---

## Explicitly NOT in scope today (deferred — do not start)

- Camera-move / framing / cropping toward the target (that's **Day 3** — the "holy cow" day).
- Re-identification / re-acquiring a lost target under a new ID (deep problem; future PRD).
- Gesture vocabulary or any real input modality (Day 4+).
- LLM intent layer (later; outer loop only, never per-frame).
- Drone, simulator, glove, any hardware.
- Moving-camera / homography-under-motion.

---

## Note to the agent (Claude Code)

Same principle as Day 1: scaffolding, state logic, and tests inside `AirLine/` are yours. Any choice that touches the validated CV core, the tracker, or the `core_bridge` contract is **Aarav's decision** — surface it, don't make it. The fragmentation behaviour is the heart of today: do not paper over a lost target to make the demo look smoother — an honest `TARGET LOST` is the correct, valuable result. Close the session by filling in the measurements above, notes.md-style.
