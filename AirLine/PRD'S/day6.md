# AirLine — Day 6 PRD

**Date:** (fill in)
**Project:** AirLine (gesture-directed, scene-aware cinematography layer) on the SideLine CV pipeline
**Branch:** `airline` (continue on the same long-lived branch)
**Builds on:** Day 1–5. Key Day-5 finding this day acts on: the gesture stack (mediapipe, numpy<2) and the render/tracker stack (ultralytics, numpy 2) **cannot share a venv** — so a combined live demo requires two processes passing intent commands.

---

## Goal for the day (ONE sentence)

Build the **two-process live bridge**: a **capture process** (in `.venv-gestures`) reads the webcam, runs the gesture engine, and emits **typed intent commands**; a **render process** (in the main `.venv`) receives those intents and applies them to the football clip through the already-proven `TargetTracker` + `VirtualCamera` + shot-API — so your hand **live-directs** the cinematography in real time. The **headline deliverable is a measured end-to-end latency number.**

This is a **plumbing-and-latency day** (like Day 1 was a plumbing day). No new gestures, no new shots, no Tier 3.

---

## Why this is the right Day 6 (context for the agent)

Day 5 surfaced — but did not build — the two-process architecture. It currently exists only as a finding. Two reasons to build it now:
1. **De-risk the foundation before stacking on it.** Everything later (Tier 3 paths, eventually a glove + drone) assumes intents can flow cleanly and quickly between a capture device and a render/brain. That assumption is untested. Prove it real now, isolated, measurable — before flight-path logic or hardware is tangled in.
2. **This IS the final system's backbone, not a throwaway.** On the real product the glove and the CV brain are separate devices passing intent over a link. The two-process bridge is that backbone with both processes on one machine. Building it now is building the real thing early.

The real new challenge today is **latency**: capture → classify → debounce → serialize → transport → receive → apply → render. Each stage adds delay on top of the ~432 ms debounce window measured Day 5. Measuring and reporting this honestly is the point of the day.

---

## Architecture (hold this separation)

- **Capture process** (runs in `.venv-gestures`; mediapipe, NO ultralytics):
  webcam → `GestureEngine` → confirmed `IntentCommand` → **emit over the transport** as a small serialized message (intent type + minimal payload, e.g. a reference x for SELECT, timestamp for latency). Emits ONLY on confirmed-intent transitions (not every frame), exactly as Day 4's debounce already gates.
- **Render process** (runs in main `.venv`; ultralytics, NO mediapipe):
  reads the football clip via `core_bridge` (unchanged) → on each received intent, applies it via the EXISTING `IntentApplier` (`tracker`, `camera`) → renders the resulting cinematography live to a window and/or `day6_live.mp4`.
- **Transport between them:** keep it simple and local. A localhost socket or a local message queue is fine; pick the lowest-overhead option that's easy to reason about. The intent message must carry a **send-timestamp** so the render side can compute transport+apply latency. Do NOT pull in a heavy broker/dependency — flag if you think one is needed.
- **The separation seam is unchanged:** capture emits intents; render consumes intents. Neither imports the other's stack. This is the same `gesture → intent → execution` seam from Day 4, now split across a process boundary. The glove later replaces the capture process; render is untouched.

---

## Modules the agent MAY touch

- New files in `AirLine/` (e.g. `bridge_capture.py`, `bridge_render.py`, a small shared `bridge_protocol.py` for the message format).
- New tests in `tests/airline/`.
- `PRD/`, and `SETUP.md`/README for the env-documentation item below.
- May read/call existing AirLine modules — **do not alter their contracts** (`core_bridge`, `TargetTracker`, `VirtualCamera`, `GestureEngine`, `IntentApplier`, `intent`). The whole point is they're reused unchanged across the split.

## DO NOT TOUCH list (hard constraint)

- Any SideLine CV script, model, config, tracker tuning; `backend/`, `Website/`, existing `tests/backend/`, `tests/frontend/`.
- All Day 1–5 AirLine contracts — consumed, not modified. (If the message format needs `intent.py` to expose a serialization helper, that's a small additive change — flag it, don't restructure.)
- **Nothing outside `AirLine/` and `tests/airline/`** (plus the doc file noted below) **may be modified.**
- Main `.venv` must stay numpy 2.4.4 / no mediapipe; `.venv-gestures` stays the mediapipe env. Neither changes.

---

## Steps

1. **Clean start.** Branch `airline`, tree clean. Confirm standing baseline in main `.venv`: **114 passed + known `test_video_io.py` error unchanged.** Confirm both venvs intact.

2. **Define the message protocol** (`bridge_protocol.py`): a tiny, explicit serialized intent message (intent type, optional payload, send-timestamp). Keep it dependency-light (JSON over socket is perfectly fine). This file must be importable by BOTH venvs (so it must NOT import mediapipe or ultralytics — pure stdlib).

3. **Capture process** (`bridge_capture.py`, runs in `.venv-gestures`): reuse `GestureEngine` + `MediaPipeHandSource`; on confirmed intent, stamp and send. Print what it sends for legibility.

4. **Render process** (`bridge_render.py`, runs in main `.venv`): play the football clip through `core_bridge` + `IntentApplier`; on each received intent, apply it and overlay (received intent, current target, shot, state) live; compute and display **per-intent transport+apply latency** from the send-timestamp. Write `AirLine/outputs/day6_live.mp4`.

5. **Latency instrumentation (the headline):** measure and report, separately:
   - **gesture→confirmed** (the Day-5 debounce contribution, ~432 ms),
   - **transport+apply** (send-timestamp → applied in render),
   - **total hand-motion → on-screen response**, at least roughly.
   Report mean and rough worst-case. State the clock approach honestly (if the two processes share the system clock locally, say so; if there's any clock-offset caveat, note it).

6. **Tests** (`tests/airline/`, main `.venv`, no webcam, no live socket needed):
   - `bridge_protocol` round-trips: serialize → deserialize yields the same intent + payload + timestamp.
   - Malformed/garbage message is rejected gracefully (no crash) — a transport must not be able to take the render process down.
   - The render-side intent handling (given a decoded intent) drives `IntentApplier` correctly — reuse/extend existing intent tests; this is mostly already covered, just confirm it works via the decoded path.
   - (The live socket + webcam end-to-end is validated by hand, not unit-tested — note that explicitly.)

7. **Re-run full suite** in main `.venv`: 114 baseline + new Day-6 tests; `test_video_io.py` unchanged.

8. **Document the envs** (the Day-5 loose end): add a short `SETUP.md` (or README section) stating that AirLine needs TWO environments — the main `.venv` (numpy 2, ultralytics) and `.venv-gestures` / `C:\airline-gestures-venv` (mediapipe, numpy<2) — and how to rebuild each from their requirements files. This kills the undocumented-dependency risk flagged Day 5.

---

## Definition of Done (measurable — no "it should work")

- [ ] **The live demo works:** with capture running in `.venv-gestures` and render in main `.venv`, your hand gestures **live-drive** the football-clip cinematography (select/switch/tight/wide/release), captured in `AirLine/outputs/day6_live.mp4` and/or witnessed live. This is the upgraded "holy cow" — real-time, not a re-render.
- [ ] **THE NUMBER — end-to-end latency:** report gesture→confirmed, transport+apply, and rough total hand→screen latency (mean + worst-case). This is the day's primary knowledge output.
- [ ] **A verdict on that number:** is the live feel acceptable, or is latency a problem? If it's bad, that's a logged finding with a hypothesis (where the time goes) — a useful result, not a failure. (See "if latency is bad" below.)
- [ ] `bridge_protocol` round-trip + malformed-message-safety tests pass.
- [ ] Full suite green at 114 + Day-6 tests; `test_video_io.py` error unchanged.
- [ ] **Both venvs proven intact**; neither stack contaminated.
- [ ] `git diff` shows changes only under `AirLine/`, `tests/airline/`, `PRD/`, and the new `SETUP.md`/README.
- [ ] `SETUP.md`/README documents the two-environment setup (Day-5 loose end closed).

---

## If latency is bad (so a bad result is still a good day)

If total hand→screen latency feels laggy, DO NOT start optimizing blindly. Instead:
- Report the **breakdown** so we know which stage dominates (likely the debounce window, but prove it).
- Note the obvious levers without implementing them yet: shorter debounce (trades reliability for speed — recall swipe was already fragile), lighter serialization, decoupling render FPS from intent rate.
- Leave it as a logged finding for a dedicated tuning decision. A measured, understood latency problem is a SUCCESSFUL Day 6 — the whole reason to build this now was to find such problems early and cheaply.

---

## Rollback note

Additive files + two already-existing venvs; no contract edits expected. The transport is the only genuinely new moving part, and it's local and disposable. If the bridge misbehaves, the Day-5 state (scripted demo, all 114 tests) is intact and `main` is untouched. New heavy dependency for transport? Flag first — stdlib sockets/queues should suffice.

---

## Explicitly NOT in scope today (deferred — do not start)

- **Tier 3 shots (orbit/push-in/dolly)** — still gated on flight-path primitives + simulator; the next major PRD AFTER the bridge is proven.
- New gestures; swipe-reliability tuning (logged Day-5 finding; not today).
- Two-hand director's-rectangle framing.
- Re-identification of a lost target.
- LLM intent layer (this bridge is, notably, where it would later attach — as a slow outer consumer/producer of intents — but NOT today).
- Real glove hardware (it will later replace the capture process behind this same protocol).
- Drone / real flight / moving-camera-homography.

---

## Note to the agent (Claude Code)

This is plumbing and measurement, not features. Reuse every Day 1–5 module unchanged across the process split — if you find yourself wanting to modify a contract to make the bridge work, STOP and flag; the architecture's whole value is that the seam already supports this. Keep the transport dependency-light (stdlib if at all possible). The headline output is an honest latency breakdown — a measured latency *problem* is a successful day, so report numbers straight, no smoothing-over. Close `SETUP.md` (the Day-5 env-doc loose end) while you're here. Fill in measurements notes.md-style; the latency breakdown is the real new knowledge.
