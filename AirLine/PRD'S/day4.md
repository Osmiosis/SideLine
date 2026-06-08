# AirLine — Day 4 PRD

**Date:** (fill in)
**Project:** AirLine (gesture-directed, scene-aware cinematography layer) on the SideLine CV pipeline
**Branch:** `airline` (continue on the same long-lived branch)
**Builds on:** Day 1 (`core_bridge`), Day 2 (`TargetTracker`), Day 3 (`VirtualCamera`)

---

## Goal for the day (ONE sentence)

Replace the keyboard/`--target-id` stand-in with **real cinematic-intent hand gestures via webcam (MediaPipe)** — built on a reusable **gesture engine with a debounce/confirmation layer** — wiring **Tier 1 (subject control)** and **Tier 2 (shot type)** gestures onto the already-proven `TargetTracker` and `VirtualCamera`.

This is the first time the *novel* part of the project — directing by intent — becomes tangible.

---

## Why this is the right Day 4 (context for the agent)

Days 1–3 built and proved the executor: lock a subject, follow it with adaptive smoothing, drift to wide on loss. The input was always a stand-in (`--target-id`, keypress). Day 4 swaps the stand-in for gestures. Crucially, these are **cinematic-INTENT gestures** ("film this subject," "go wide"), NOT flight-piloting gestures. Piloting is a separate, hardware-era, physical-controller concern and is explicitly out of scope (and must never live on a webcam channel for safety reasons). The webcam/MediaPipe layer is itself a **stand-in for the future wearable glove** — so build it solid but do not gold-plate it; the glove will later replace the input source while reusing everything downstream.

**Architectural principle to preserve:** input modality (gesture engine) must be cleanly separable from intent (what the gesture means) from execution (target + camera). A gesture produces an *intent command*; the existing pipeline executes it. This separation is what lets the glove later replace the webcam without touching target/camera code.

---

## The gesture set for today (Tier 1 + Tier 2 only)

**Tier 1 — subject control (drives `TargetTracker`):**
- **Point / select** → lock the subject nearest the pointing direction. *v1 simplification:* nearest to a screen reference point (e.g. frame centre or the fingertip's x-position mapped to the field) — do NOT attempt true 3D pointing-ray projection today; that's over-scoping. Replaces `--target-id`.
- **Swipe left / right** → cycle locked target to the next/previous tracked ID.
- **Open palm (held)** → release target → `IDLE` / wide (the natural "stop following").

**Tier 2 — shot type (drives `VirtualCamera`):**
- **Fist** → tight follow (sets a tighter zoom target on the locked subject).
- **Spread hand / five fingers** → wide establishing shot (intentionally triggers the drift-to-wide behaviour that already exists).

> Note the open-palm (release) and spread-hand (wide) are deliberately distinct-but-similar — see the reliability requirement below; the debounce/confirmation layer and a clear hand-shape definition must keep them from colliding. If they prove too confusable in practice, flag it for Aarav rather than silently merging them.

---

## The gesture ENGINE (build this FIRST — it's the reusable foundation)

`AirLine/gestures.py` — turns webcam frames into *confirmed intent commands*:
- Uses MediaPipe Hands for landmarks (new dependency — see flag below).
- Classifies the current hand pose into one of the gesture labels (or `none`).
- **Debounce/confirmation layer (the heart of the day):** a raw gesture must be held consistently for **N consecutive frames** (configurable, suggest ~5–8) before it *fires* as a confirmed command. This is the direct analog of Day 2's sub-threshold-gap logic — it prevents the camera from spasming on every MediaPipe flicker. A confirmed gesture should also not re-fire continuously while held (fire on confirmed transition, not every frame).
- Emits a small, typed **intent command** object (e.g. `SELECT`, `SWITCH_NEXT`, `RELEASE`, `SHOT_TIGHT`, `SHOT_WIDE`) — NOT raw landmarks. Downstream code consumes intents, never MediaPipe internals. This is the separation seam.
- Pure-ish and testable: the classification + debounce logic must be unit-testable by feeding synthetic landmark/label sequences (no webcam required in tests).

---

## Modules the agent MAY touch

- New files in `AirLine/` (e.g. `gestures.py`, `intent.py`, `run_day4.py`).
- New tests in `tests/airline/`.
- `PRD/`.
- May read/call `core_bridge.py`, `target.py`, `camera.py` — **do not alter their contracts.** If a contract genuinely needs to change to accept intent commands, STOP and flag for Aarav.

## DO NOT TOUCH list (hard constraint — unchanged)

- Any SideLine CV script, model, config, tracker tuning.
- `backend/`, `Website/`, existing `tests/backend/`, `tests/frontend/`.
- The `core_bridge` invocation and the Day 2/Day 3 contracts (consume; don't rewrite).
- **Nothing outside `AirLine/` and `tests/airline/` may be modified.**

---

## Steps

1. **Clean start.** Branch `airline`, tree clean. Re-run suite, confirm standing baseline: **89 passed + the known `test_video_io.py` collection error unchanged.** Record as "before."

2. **Dependency flag — STOP and confirm before installing.** MediaPipe is a new dependency. Before adding it: (a) note it explicitly for Aarav, (b) pin a version, (c) confirm it coexists with the existing CV stack (Ultralytics/torch/opencv) without version conflicts. If there's a conflict risk, flag it and propose options (e.g. isolated import, alternative hand-tracking lib) rather than force-installing. Do not silently mutate the environment.

3. **Build the gesture engine** (`gestures.py`) with the debounce/confirmation layer, emitting typed intent commands. Unit-testable via synthetic label sequences.

4. **Build the intent → pipeline wiring** (`intent.py` or inside `run_day4.py`): map each confirmed intent onto the existing `TargetTracker` / `VirtualCamera` API. SELECT/SWITCH/RELEASE → target state; SHOT_TIGHT/SHOT_WIDE → camera zoom intent. This layer is thin glue — the heavy lifting already exists.

5. **Build `run_day4.py`** — two input sources, one pipeline:
   - **webcam** for gestures (your hand), AND
   - **a clip** for the footage being "filmed" (reuse `clips/football.mp4`; id 107 was the good long-lived subject).
   - Per frame: read webcam → gesture engine → confirmed intent → apply to target/camera → render the *resulting cinematography* on the football clip → write `AirLine/outputs/day4_gestured.mp4`. Also overlay the current confirmed gesture/intent as on-screen text so the demo is legible.
   - (If running webcam + clip in lockstep is awkward, an acceptable v1 is: record the gesture intent stream live, then apply it to the clip — but live-and-simultaneous is the better demo if feasible. Agent's call on implementation; flag if it simplifies.)

6. **Tests** (`tests/airline/test_gestures.py`, synthetic, no webcam): debounce holds a gesture N frames before firing; sub-N flicker does NOT fire; confirmed gesture fires once on transition, not every frame; each gesture label maps to the correct intent command; ambiguous/`none` produces no command.

7. **Re-run full suite.** Baseline + new Day 4 tests; `test_video_io.py` error unchanged.

---

## Definition of Done (measurable — no "it should work")

- [ ] **Visible output:** `AirLine/outputs/day4_gestured.mp4` shows your hand gestures driving the cinematography on the football clip — select a subject by gesture, switch, go tight, go wide, release — with on-screen labels of the confirmed intent.
- [ ] **The debounce works, demonstrated:** show (or note) that a brief accidental hand flicker does NOT trigger a command, while a deliberately-held gesture does. This is the reliability proof.
- [ ] **A number — gesture reliability:** over a short scripted sequence (e.g. perform each of the 5 gestures 5 times), report a rough recognition rate (confirmed-correct / attempts) and note any gesture pair that confuses (esp. open-palm vs spread-hand). This is the honest reliability picture, Day-2-style.
- [ ] **A number — latency:** rough frames/ms from gesture-held to command-fired (should be ~the debounce window; confirm it's not sluggishly long).
- [ ] `tests/airline/test_gestures.py` passes (debounce / flicker-rejection / fire-once / label-mapping).
- [ ] Full suite green at baseline + Day 4 tests; `test_video_io.py` error unchanged.
- [ ] `git diff` shows changes **only** under `AirLine/`, `tests/airline/`, `PRD/`.
- [ ] MediaPipe dependency recorded (version pinned) and confirmed not to break the existing CV stack / existing tests.

---

## Rollback note

Additive files on the isolated branch; Days 1–3 intact in history, `main` untouched. The one real risk today is the **MediaPipe dependency** perturbing the environment — hence the explicit Step 2 flag. If install causes any existing-test breakage, that is a STOP-and-flag event, not something to paper over.

---

## Reliability caveat (so you're not surprised)

Webcam gesture recognition is inherently flickery — lighting, hand angle, and similar-looking poses cause misfires. The debounce layer mitigates but won't eliminate this. Expectation for today: gestures work *reliably enough to demo the intent pipeline*, not flawlessly. Getting select/tight/wide solid is success; if swipe or open-palm-vs-spread proves flaky, log it and we refine (or drop a gesture) rather than burning the session chasing perfect recognition on a layer the glove will eventually replace anyway.

---

## Explicitly NOT in scope today (deferred — do not start)

- **Tier 3 camera moves (orbit / push-in / dolly)** — BLOCKED until flight-path logic exists; these gestures would command nothing today. **This is the immediate NEXT PRD** (flight-path primitives + a simulator to test them, *then* the gestures that command them).
- **Two-hand director's-rectangle framing** — harder detection; later polish.
- Manual flight piloting — separate hardware-era concern, physical controller, never the webcam channel.
- Re-identification of a lost target (future PRD).
- LLM intent layer (later; outer/slow loop only, never per-frame).
- Real glove hardware (the webcam is today's stand-in for it).
- Drone, real flight, moving-camera/homography-under-motion.

---

## Note to the agent (Claude Code)

Same principle: the gesture engine, intent wiring, and tests inside `AirLine/` are yours; anything touching the CV core, tracker, camera, or the Day 1–3 contracts is **Aarav's call** — surface it. Two specific stop-and-flag triggers today: (1) the MediaPipe dependency install if it risks the existing stack, (2) any temptation to change a downstream contract to fit gestures. Build the gesture *engine* (with debounce) first as the reusable foundation; the Tier 1/Tier 2 gestures are thin wiring onto already-proven behaviour. Close by filling in the measurements, notes.md-style.
