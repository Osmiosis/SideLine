# AirLine — Day 8 PRD

**Date:** (fill in)
**Project:** AirLine (gesture-directed, scene-aware cinematography layer) on the SideLine CV pipeline
**Branch:** `airline` (continue on the same long-lived branch)
**Builds on:** Day 7's proven `flightpath` engine (`OrbitPath`, `CameraPose`, `look_at`, 3D invariants to machine precision), the Day-5 named-shot seam, the Day-6 intent backbone.

---

## Goal for the day (ONE sentence)

Complete the flight-path shot vocabulary by adding **two more primitives — push-in (with pull-out as its sign-flip) and dolly** — reusing the Day-7 `flightpath` machinery, simulator, seam, and invariant-testing pattern, each proven by **its own correct 3D invariants** (NOT orbit's).

After today the shot vocabulary is complete: **tight, wide, orbit, push-in/pull-out, dolly.** This banks the software core.

---

## Why two primitives in one day is OK here (it wasn't on Day 7)

Day 7 was ONE primitive because it introduced three new things simultaneously: the *concept* of a 3D camera pose over time, the *simulator*, and the *invariant-testing pattern*. All three now exist and are proven. Push-in and dolly are **applications of that existing machinery**, not new infrastructure — same `CameraPose`, same `look_at`, same sim, same tri-view + 3D visualization, same seam, same intent path. So the multi-unknown risk that justified one-primitive scope on Day 7 is gone. The remaining discipline is: **give each primitive its OWN honest invariants** (the Day-7 lesson — a wrong invariant passes a broken path).

---

## The two primitives (with their CORRECT, distinct invariants)

### Push-in (and pull-out)
- **Motion:** camera moves along the line between itself and the target, *toward* the target — distance to target decreases over time. Look-at stays locked on the subject. **Pull-out** = same primitive, distance increasing (a sign/direction flip — get it for free).
- **Honest invariants (NOT orbit's "constant radius"):**
  1. **Monotonic distance:** `|camera_pos − target|` strictly decreases (push-in) / increases (pull-out) over time, within tolerance — and respects configured start/end distances (does not overshoot past the target or below a min standoff).
  2. **Look-at correctness:** camera-forward points at target, `dot ≈ 1`, throughout.
  3. **Straight-line motion toward target:** the camera path is collinear with the camera→target axis (no lateral drift) — assert the position stays on the line from start toward the target.
  4. **Endpoints:** starts at the configured start distance, ends at the configured end distance (within tolerance).
  5. **Moving target:** if the target moves, push-in still reduces distance to the *current* target and keeps look-at locked.

### Dolly (tracking translation)
- **Motion:** camera translates along a straight line through space (e.g. alongside a moving subject), holding a roughly **constant offset vector** to the target, look-at locked on subject. Distinct from push-in: motion is **alongside**, not toward.
- **Honest invariants (NOT push-in's "decreasing distance"):**
  1. **Straight-line camera path:** camera positions are collinear along the configured dolly axis (within tolerance).
  2. **Constant offset (static-target case):** for a stationary target, distance to target stays ~constant while the camera translates (it's moving sideways, not closer) — note this differs from orbit (orbit is constant-distance *on a circle*; dolly is constant-distance *along a line* only for a specific geometry — define precisely which: e.g. dolly parallel to a plane at fixed perpendicular standoff). Document the exact convention so the invariant is the RIGHT one for the chosen definition.
  3. **Look-at correctness:** `dot ≈ 1` throughout.
  4. **Tracking a moving target:** if the subject moves along the dolly axis, the camera maintains its offset and keeps the subject framed (the canonical "tracking shot").
  5. **Constant speed:** equal translation per equal time (unless an ease is explicitly configured).

> The Day-7 lesson, restated: do NOT copy orbit's invariants onto these. Push-in's signature is *changing* distance; dolly's is *straight-line translation at held offset*. Asserting the wrong invariant is the bug to avoid (cf. the altitude-on-tilt catch).

---

## Modules the agent MAY touch

- Extend `AirLine/flightpath.py` with `PushInPath` (covering pull-out) and `DollyPath`, reusing `CameraPose` / `look_at`. Keep `OrbitPath` **unchanged** (its tests must stay green — regression guard).
- Extend `AirLine/sim_orbit3d.py` (or add a sibling) to visualize the new paths with the SAME two-view approach (rotating 3D + tri-view). Reuse, don't duplicate, the rendering.
- Extend the named-shot seam: `Shot.PUSH_IN`, `Shot.PULL_OUT`, `Shot.DOLLY`; matching `IntentCommand`s (`SHOT_PUSH_IN`, `SHOT_PULL_OUT`, `SHOT_DOLLY`); wire `_INTENT_TO_SHOT`. **Pre-approved additive extension points.**
- New tests in `tests/airline/` (e.g. extend `test_flightpath.py` or add `test_pushin_dolly.py`).
- `run_day8.py` to demonstrate; `PRD/`.

## DO NOT TOUCH list (hard constraint)

- Any SideLine CV script, model, config, tracker tuning; `backend/`, `Website/`, existing `tests/backend/`, `tests/frontend/`.
- `core_bridge`, `TargetTracker` contracts.
- `VirtualCamera`'s existing 2D crop/follow/drift logic — these primitives are 3D path modes alongside it; `test_camera.py` must pass unchanged.
- **`OrbitPath` itself** — Day 7's proven code; extend the module, don't modify orbit. Day-7 invariant tests must stay green.
- The two-process bridge protocol.
- **Nothing outside `AirLine/` and `tests/airline/`** (plus `PRD/`). Both venvs intact.
- Can't add cleanly without disturbing orbit / camera / a frozen contract → STOP and flag.

---

## Steps

1. **Clean start.** Branch `airline`, tree clean. Baseline main `.venv`: **133 passed + known `test_video_io.py` error unchanged.** Both venvs intact. Day 7 committed.
2. **`PushInPath`** in `flightpath.py` (toward-target, monotonic distance, pull-out via direction). Document convention.
3. **Push-in/pull-out invariant tests** — the 5 push-in invariants above, incl. moving target and pull-out.
4. **`DollyPath`** in `flightpath.py` (straight-line translation at held offset, tracking). Document the exact offset/standoff convention so the constant-distance invariant is the correct one.
5. **Dolly invariant tests** — the 5 dolly invariants above, incl. tracking a moving target.
6. **Sim:** render both new primitives with the rotating-3D + tri-view pair, off the real path code → `day8_pushin.mp4`, `day8_dolly.mp4` (or a combined panel).
7. **Seam + intents** for push-in/pull-out/dolly; tight/wide/AUTO/orbit all still dispatch correctly (regression).
8. **`run_day8.py`** — drive each new shot via the intent path; print each primitive's invariants; render the videos.
9. **Full suite** main `.venv`: 133 + Day-8 tests; `test_camera.py` AND Day-7 orbit tests green unchanged; `test_video_io.py` unchanged.

---

## Definition of Done (measurable — no "it should work")

- [ ] **Push-in proven:** numbers showing distance-to-target monotonically decreasing from start to end standoff, look-at error ~0, no lateral drift; pull-out shown as the increasing-distance case. Video `day8_pushin.mp4`.
- [ ] **Dolly proven:** numbers showing straight-line camera translation, held offset/standoff (per the documented convention), look-at ~0, and a moving-target *tracking* demo where the subject stays framed. Video `day8_dolly.mp4`.
- [ ] **Correct-invariant discipline:** push-in does NOT assert constant radius; dolly does NOT assert decreasing distance. Each primitive's invariants match its own geometry. (State this explicitly in notes — it's the Day-7 lesson applied.)
- [ ] **Regression proof:** `OrbitPath` Day-7 invariant tests green unchanged; `test_camera.py` (tight/wide/AUTO) green unchanged; orbit still dispatches via the seam.
- [ ] **Vocabulary complete:** all of tight / wide / orbit / push-in / pull-out / dolly are triggerable through the intent path. Note this as the "software shot vocabulary: complete" milestone.
- [ ] Full suite green at 133 + Day-8 tests; `test_video_io.py` unchanged; both venvs intact; `git diff` only under `AirLine/`, `tests/airline/`, `PRD/`.

---

## The localization caveat still applies (carry it forward)

Same as Day 7: these paths are **rigorous 3D**, but the **target's real depth and view-from-pose synthesis remain deferred** to a real moving camera/drone. The sims are schematic matplotlib, not rendered views. Push-in toward a real subject and a real dolly both *especially* depend on true 3D target localization later — note that push-in's standoff and dolly's offset are, for now, defined in the synthetic/defined world, not measured from real footage. Do not let the schematic sim masquerade as real imagery.

---

## Rollback note

Additive primitives in an existing module + additive seam entries; orbit and the 2D camera are guarded by their existing tests passing unchanged. If a primitive can't be added cleanly, ship the one that works and defer the other with a flag — there's no rule both must land today, only that whatever lands is proven. Days 1–7 committed; `main` untouched. matplotlib/ffmpeg only (Day-7 precedent); GIF fallback if ffmpeg missing — flag, don't add heavy deps.

---

## Explicitly NOT in scope today (deferred)

- **Spiral / radius-ramping / height-ramping** composite moves — these are *combinations* of primitives (e.g. orbit + push-in = spiral); building a **composition layer** is a later, separate idea, NOT today. Today is the three remaining *atomic* primitives only.
- **Webcam gestures** for any of these (circular/forward/lateral hand motions are their own recognition-reliability problem) — triggered via intent/mock today.
- Real 3D rendering / photoreal view synthesis; real drone flight dynamics; true 3D localization / homography-under-motion.
- Re-identification; LLM intent layer; real glove; actual drone/flight.

---

## Note to the agent (Claude Code)

Two primitives today is fine BECAUSE the infrastructure already exists — you are applying a proven pattern, not building new machinery. The one piece of real discipline: **each primitive gets its own correct invariants** (push-in = changing distance; dolly = straight-line at held offset) — do NOT copy orbit's constant-radius invariant onto them; that's exactly the false-invariant trap from Day 7. Keep `OrbitPath` and the 2D camera untouched (regression tests prove it). Reuse the sim, don't duplicate it. Be honest (as Day 7 was) that path math is rigorous 3D while target depth/view remain deferred. If only one primitive lands cleanly, ship it and flag the other — proven-and-partial beats rushed-and-whole. Close with each primitive's invariant numbers, notes.md-style, and mark the shot vocabulary complete.
