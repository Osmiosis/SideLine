# AirLine — Day 5 PRD

**Date:** (fill in)
**Project:** AirLine (gesture-directed, scene-aware cinematography layer) on the SideLine CV pipeline
**Branch:** `airline` (continue on the same long-lived branch)
**Builds on:** Day 1 (`core_bridge`), Day 2 (`TargetTracker`), Day 3 (`VirtualCamera`), Day 4 (`gestures.py`, `intent.py`, scripted demo, 109 tests)

---

## Goal for the day (ONE sentence)

Close the two open decisions from Day 4: (1) stand up the **isolated `.venv-gestures`** so live MediaPipe runs without touching the validated stack, and get AirLine's **first real webcam gesture recognition-rate number**; and (2) introduce a **thin named-shot-API seam** in `camera.py` so shot type is a real, dispatchable concept instead of the intent layer poking `CameraConfig` zoom values.

This is a focused **refactor + harden** day, not a feature-expansion day. No new gestures, no Tier 3.

---

## Why this is the right Day 5 (context for the agent)

Day 4 built the whole gesture pipeline but, correctly, **did not install MediaPipe** — it conflicts hard with the validated stack (mediapipe 0.10.x needs numpy <2 / protobuf <5; the env is on numpy 2.4.4 / protobuf 7.35.0, with numpy-2-built torch/ultralytics/opencv). That STOP-and-flag was the right call. So two things are still genuinely unproven or unclean:

1. **Live recognition rate is unmeasured** — the scripted demo proved the pipeline logic, but never proved a real hand in front of a real webcam is recognised reliably (esp. the confusable OPEN_PALM vs SPREAD pair). This is the one remaining real unknown in the gesture layer.
2. **Shot type is expressed by mutating public `CameraConfig` zoom fractions** — a hack that works for TIGHT/WIDE but won't survive the third shot type (push-in/orbit aren't zoom numbers; they're behaviours). Aarav approved building a proper seam **now**, while it's cheap and only two shots exist.

**Important honesty note for the agent:** the shot-API controls the *virtual camera* (crop). It is NOT the future drone's physical-camera/flight control API and must not be designed as if it were. Its justification is clean abstraction for a growing shot vocabulary, not the drone. Do not over-build it toward hypothetical physical control.

---

## Part A — Isolated gesture venv + first real recognition number

### Constraints
- The validated `.venv` (numpy 2.4.4, no mediapipe) **must remain untouched**. Verify before AND after: `numpy==2.4.4`, mediapipe absent, full suite still 109 + known `test_video_io.py` error.
- MediaPipe lives ONLY in a separate `.venv-gestures` (python 3.11) per Day-4's `requirements-gestures.txt`. The two environments never merge.

### Steps
1. Create `.venv-gestures` from `AirLine/requirements-gestures.txt`; pin exact versions actually resolved (write them back into the file). Confirm MediaPipe imports and a webcam frame yields hand landmarks in THIS venv only.
2. Confirm the main `.venv` is byte-for-byte unaffected (numpy still 2.4.4, mediapipe still absent, 109 tests + known error). **This verification is a required deliverable, not a formality** — it's the proof the quarantine held.
3. Using the live webcam path (`run_day4.py --source webcam`, already built, lazy-imports MediaPipe), run a **scripted recognition test**: perform each of the 5 gestures (POINT, FIST, OPEN_PALM, SPREAD, swipe) a fixed number of times each (e.g. 10), under normal lighting, and record confirmed-correct / attempts.
4. Specifically probe the **OPEN_PALM vs SPREAD confusion** flagged on Day 4 — report how often each is misread as the other. If they're too confusable in practice, that's a finding: note it, and propose either a clearer hand-shape definition or dropping/replacing one — flag for Aarav, don't silently merge.

### Part A definition of done (measurable)
- [ ] `.venv-gestures` exists, MediaPipe imports there, webcam → landmarks confirmed.
- [ ] **Main `.venv` proven unchanged** (numpy 2.4.4, no mediapipe, 109 tests + known error) — before and after.
- [ ] **A real number:** per-gesture recognition rate over the scripted attempts (e.g. "POINT 9/10, FIST 10/10, OPEN_PALM 7/10, SPREAD 6/10, swipe 8/10").
- [ ] **The palm-vs-spread confusion quantified**, with a recommendation if it's bad.
- [ ] Latency sanity from live use (held → fired ≈ the 6-frame/~200 ms debounce window; confirm not sluggish on real hardware).

> Reliability expectation (unchanged from Day 4): "reliable enough to demo the intent pipeline," not flawless. This webcam layer is a stand-in the glove will later replace — so a mediocre rate on a gesture is a *logged finding that may inform the glove design*, not a session-blocker. Don't burn the day chasing perfect recognition.

---

## Part B — Thin named-shot-API seam in `camera.py`

### What to build (and the discipline)
- Introduce a **named shot concept**: the camera accepts a shot intent (`TIGHT`, `WIDE`) and knows how to execute it internally, rather than callers mutating `CameraConfig` zoom fractions from outside.
- Implement **only the two shots that exist today**. The win is the *seam* (a clean dispatch point where shots are named and resolved), NOT a library of shots. Orbit/push-in/dolly are added behind this seam in a FUTURE PRD when flight-path logic exists — do not stub or build them now beyond, at most, leaving a clearly-marked extension point.
- Rewire `intent.py` so SHOT_TIGHT/SHOT_WIDE call the new shot-API instead of poking `CameraConfig`. The intent layer should now say "request shot X," not "set zoom to Y."

### The contract-change discipline (this is the careful part)
- This is the **first deliberate edit to an established contract** (`camera.py` has been consume-only since Day 3). It is Aarav-approved, but must be done surgically:
  - `camera.py`'s existing behaviour must be **provably unchanged** for the existing follow/zoom/drift logic — its current tests must stay green untouched.
  - The named-shot dispatch is an **addition**, not a rewrite of `VirtualCamera`'s motion logic.
  - New tests cover the shot-API: requesting TIGHT yields the tight framing, WIDE yields wide, default/unknown is handled, and switching shots eases (doesn't jump) consistent with Day-3 smoothing.
- If achieving this cleanly would require changing `VirtualCamera`'s *motion* behaviour (not just adding a dispatch layer), STOP and flag — that's a bigger decision than approved.

### Part B definition of done (measurable)
- [ ] `intent.py` no longer mutates `CameraConfig` zoom fractions directly; it requests named shots.
- [ ] `camera.py` exposes a named-shot entry point with TIGHT/WIDE implemented; existing motion/drift/smoothing logic unchanged.
- [ ] Existing `test_camera.py` tests **pass unchanged** (proof the refactor didn't alter proven behaviour).
- [ ] New shot-API tests pass (tight/wide/default/eased-transition).
- [ ] The scripted Day-4 demo (`--source scripted`) still produces equivalent cinematography through the new seam — i.e. the refactor is behaviour-preserving for the existing two shots. Re-render `day5_shots.mp4` to confirm by eye.

---

## DO NOT TOUCH list (hard constraint — with ONE approved exception)

- **Approved exception:** `camera.py` may receive the additive named-shot seam described in Part B (and its tests). Nothing else in it changes.
- Still untouchable: any SideLine CV script, model, config, tracker tuning; `backend/`, `Website/`, existing `tests/backend/`, `tests/frontend/`; the `core_bridge` and `TargetTracker` contracts.
- **Nothing outside `AirLine/` and `tests/airline/` may be modified.**
- The main `.venv` must not be mutated. MediaPipe stays in `.venv-gestures` only.
- Any need to go beyond the approved `camera.py` addition → STOP and flag.

---

## Full-suite / isolation proof (required)
- Re-run the full suite in the main `.venv`: must be **109 baseline + new Day-5 tests**, with `test_video_io.py` error unchanged.
- `git diff` shows changes only under `AirLine/`, `tests/airline/`, `PRD/` (camera.py is under `AirLine/`... confirm its actual path; if `camera.py` lives outside `AirLine/`, that changes the scope conversation — flag immediately, it shouldn't).
- Main `.venv` dependency snapshot unchanged.

---

## Rollback note
Part A is environment-additive (a second venv) and adds no risk to the main stack if the quarantine holds — which is itself a checked deliverable. Part B is the first contract edit, so it carries the most regression risk of any day so far; the mitigation is "existing camera tests pass unchanged" — if they don't, revert Part B and flag, the shot-API can wait. Days 1–4 intact in history; `main` untouched.

---

## Explicitly NOT in scope today (deferred — do not start)
- **Tier 3 shots (orbit / push-in / dolly)** — the seam is built today, the shots are NOT. They need flight-path primitives + a simulator first. This remains the immediate next major PRD.
- New gestures of any kind (today hardens the existing 5; it does not add to them).
- Two-hand director's-rectangle framing.
- Re-identification of a lost target.
- LLM intent layer (outer/slow loop only, later).
- Real glove hardware (webcam remains the stand-in).
- Manual flight piloting / drone / real flight / moving-camera-homography.

---

## Note to the agent (Claude Code)
Two clean, bounded jobs today: prove the gesture quarantine and get a real recognition number (Part A), and add a thin named-shot seam without disturbing proven camera behaviour (Part B). The recurring principle holds: env quarantine and contract integrity are Aarav's hard constraints — the `camera.py` addition is the single approved exception and must be surgical and test-proven. Do NOT expand the shot vocabulary, do NOT design toward the drone, do NOT touch the main venv. If Part B can't be done as a pure addition, stop and flag rather than refactoring `VirtualCamera`'s motion. Close by filling in both sets of measurements, notes.md-style — especially the live recognition rate, which is the real new knowledge this day produces.
