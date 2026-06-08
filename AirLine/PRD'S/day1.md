# AirLine — Day 1 PRD

**Project:** AirLine (gesture-directed, scene-aware cinematography layer) built on the SideLine CV pipeline
**Branch:** `AirLine` (long-lived divergent branch off SideLine `main`)

---

## Goal for the day (ONE sentence)

Stand up the `airline/` module on a new branch and prove it can load a clip and run the **existing** SideLine tracker on it via import, producing tracks — **without adding any new CV and without editing one line of the validated CV core.**

That's it. No target selection, no camera moves, no gestures. Today is *plumbing and proof that the foundation is reachable, intact, and isolated.*

---

## Why this is the right Day 1 (context for the agent)

The SideLine pipeline is a multi-month, precision-audited system (detection model bake-offs decided on precision-over-recall, ByteTrack tracking, homography calibration, follow-cam, team assignment). AirLine's novelty is a layer *on top* of this, not a rewrite of it. Day 1 exists to guarantee that the existing system stays a stable, importable foundation and that all new work is physically isolated in `airline/`.

---

## Modules the agent MAY touch

- Anything inside a new top-level `airline/` directory (to be created).
- A new test directory `tests/airline/`.
- `PRD/` (this file already lives here).

## DO NOT TOUCH list (hard constraint)

- **Any existing CV script** (detection, tracking, homography, team-assign, ball, follow-cam, event detection, involvement scoring).
- **The existing `backend/`, `Website/`, and existing `tests/backend/` + `tests/frontend/`.**
- **Any model file, config, or `bytetrack.yaml` tuning.**
- In short: **nothing outside `airline/` and `tests/airline/` may be modified.** AirLine *imports* and *calls* existing code; it never edits it.
- If the agent believes it MUST edit core code to proceed, it STOPS and flags it in writing for Aarav to decide. It does not edit core code on its own judgment.

---

## Steps

1. **Branch.** From a clean `main` (all existing tests green), create and check out branch `airline`. Confirm working tree is clean before starting.

2. **Baseline the core.** Run the existing test suite (the ~62 tests or more) and record the result. This is the "before" snapshot. If anything is already failing on `main`, note it — we do not want to blame AirLine for pre-existing failures.

3. **Create the module skeleton:**
   ```
   airline/
     __init__.py
     core_bridge.py     # the ONLY place that imports SideLine CV code
     run_day1.py        # entry point for today's proof
   tests/airline/
     test_core_bridge.py
   ```

4. **Write `core_bridge.py`.** This is the single, deliberate seam between AirLine and SideLine. It exposes thin wrapper functions that call the *existing* tracker on a clip and return tracks in a plain, AirLine-owned data structure (e.g. a list of per-frame detections with track IDs, boxes, class). Rationale: one isolated import surface means if SideLine's internals move later, only this file changes. The bridge does NOT reimplement tracking — it calls the existing script/module.

5. **Write `run_day1.py`.** Takes a clip path as a CLI arg. Loads it, calls `core_bridge` to get tracks, and (a) prints a summary (frames processed, avg FPS, unique track IDs, avg subjects/frame) and (b) writes an annotated output video to `airline/outputs/day1_tracks.mp4`. Reuse the existing footage you already have (e.g. the football or basketball clips from the notes).

6. **Write `tests/airline/test_core_bridge.py`.** At minimum: a test that the bridge returns a non-empty, correctly-shaped track structure on a short fixture clip (or a mocked detector if a real clip is too slow for CI). Mirror the discipline already used in `tests/backend/`. This is the first AirLine test; the pattern starts here.

7. **Re-run the full existing test suite.** It must be **identically green** to the Step 2 baseline. This is the proof that AirLine touched nothing it shouldn't have.

---

## Definition of Done (must be measurable — no "it should work")

- [ ] Branch `airline` exists; working tree clean; `main` untouched.
- [ ] `airline/` module runs end to end on a real clip you already have.
- [ ] **A number:** `run_day1.py` prints frames processed, avg FPS, and unique track ID count — and you eyeball them against your notes.md baselines (e.g. football ~16–18 FPS, basketball ~30 FPS at 360p) to confirm the tracker is behaving as it always did.
- [ ] **A visible output:** `airline/outputs/day1_tracks.mp4` shows the existing tracker's boxes/IDs on your footage — proof the foundation is reachable from AirLine.
- [ ] `tests/airline/test_core_bridge.py` passes.
- [ ] The existing ~62-test suite is **green and unchanged** from the Day-1 baseline (the isolation proof).
- [ ] `git diff main..airline --stat` shows changes **only** under `airline/` and `tests/airline/` (and `PRD/`). Nothing else. This is the single most important check.

---

## Rollback note

If the day goes sideways, AirLine is an isolated branch + isolated directory — `git checkout main` returns you to the untouched, validated pipeline instantly. Nothing today can harm SideLine. That's the whole point of the structure.

---

## Explicitly NOT in scope today (deferred, do not start)

- Target selection by ID (Day 2)
- Camera-move / framing output (Day 3)
- Gesture vocabulary, keypress stand-in (Day 4+)
- LLM intent layer (much later — outer loop only, never per-frame)
- Drone, simulator, glove, hardware of any kind (later phases)
- Any moving-camera / homography-under-motion work (a known hard problem; flagged for a future PRD, not now)

---

## Note to the agent (Claude Code)

You are operating under the "copilot does grunt-work, the human owns the decisions" principle. Scaffolding, wiring, and test-writing inside `AirLine/` is yours. Any decision that touches the validated CV core, model choices, or tracker tuning is **Aarav's call** — surface it, don't make it. End the session with the measurements above filled in, the way notes.md records results.
Do not commit or push, leave that to Aarav.
