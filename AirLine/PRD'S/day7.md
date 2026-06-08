# AirLine — Day 7 PRD (3D revision)

**Date:** (fill in)
**Project:** AirLine (gesture-directed, scene-aware cinematography layer) on the SideLine CV pipeline
**Branch:** `airline` (continue on the same long-lived branch)
**Builds on:** Day 1–6. Especially Day 5's **named-shot seam** (`Shot` enum + `request_shot()`, orbit marked as the extension point) and Day 6's proven two-process intent backbone.
**Supersedes:** the earlier 2D-scoped Day 7 draft. Per Aarav's call, the flight-path math is **full 3D** from the start (a 2D-only path would be thrown away the moment a real drone, which moves in 3D, is involved).

---

## Goal for the day (ONE sentence)

Introduce the first **flight-path primitive** — **orbit**, computed as a genuine **3D camera trajectory** generalized to a **tiltable orbital plane** (a level orbit is the special case) — proven by **3D geometric invariants**, visualized by **both** a rotating matplotlib-3D plot and unflattering **tri-view orthographic projections**, and slotted behind the existing named-shot seam.

This is the first day AirLine computes a **camera pose in 3D space over time**, not a 2D crop. Scope is **ONE primitive (orbit)**, done rigorously in 3D.

---

## Why 3D, why one primitive, why tiltable

- **Why 3D:** a camera orbiting a subject lives in 3D (position x,y,z, altitude, look-down angle). Computing this in true 3D is only slightly more vector math than 2D and is *correct* rather than a throwaway — it carries directly to the real drone. (Aarav's rigor call; endorsed.)
- **Why one primitive:** this day introduces three new things at once — the concept of camera-pose-in-space, the path kinematics, and a simulator to show them. Adding push-in + dolly on top would be a multi-unknown pile-up. Orbit proves the machinery; push-in/dolly reuse it next, fast.
- **Why tiltable from the start:** building the *general* case (a circle in an arbitrarily-oriented plane) forces the math to be correct for the level case too (level = plane normal points straight up). A real cinematic drone does tilted/descending orbits, so the general primitive future-proofs. The cost is careful vector math, not scope blowup — see the scope guard.

### Scope guard (hold this line)
"Orbit" = **a circle of fixed radius in a plane defined by a center, radius, and plane-normal (tilt)**, traced at constant angular speed, camera always looking at the target. It is **NOT**:
- a freeform 3D path,
- a spiral / radius-changing path,
- a height-ramping-per-revolution path.
Those are different primitives for other days. An orbit is a circle — just one allowed to live in a tilted plane. Keeping to "circle in a tiltable plane" is what preserves clean, provable invariants.

---

## The 3D orbit math (the concrete primitive)

- Inputs: **target position** (3D; see the localization caveat below), **radius**, **angular speed**, and an **orbital-plane normal** (the tilt; straight-up = level orbit).
- Output per time step: a **camera pose** = 3D position on the circle + a **look-at** direction toward the target. Document the coordinate convention and the plane parameterization explicitly at the top of the module.
- Pure deterministic kinematics — no rendering, no I/O — fully unit-testable.

### The honest invariants for a TILTED orbit (test these, not false ones)
Because the orbit can be tilted, **altitude is NOT constant** and must NOT be asserted. The invariants that are actually fundamental:
1. **Constant 3D radius:** `|camera_pos − target|` is constant within tolerance (the core invariant; true in any plane).
2. **Look-at correctness:** the camera-forward vector points at the target — `dot(normalize(forward), normalize(target − camera_pos)) ≈ 1`.
3. **In-plane:** the camera position lies in the defined orbital plane — `dot(camera_pos − center, plane_normal) ≈ 0`.
4. **Period closure:** after 360°, pose returns to the start within tolerance.
5. **Constant angular speed:** equal angle advanced per equal time.
6. **Moving-target tracking:** if the target moves, the orbit center follows it, so the subject stays centred (look-at invariant holds against a moving target).
7. **Level is the special case:** with plane_normal = up, altitude *is* constant — assert it only in that case as a sanity check on the generalization.

---

## The simulator / visualization (BOTH, by design)

Two views, because they catch different failures:
- **`AirLine/sim_orbit3d.py` — rotating matplotlib 3D plot** (`mpl_toolkits.mplot3d`): target point, the camera's 3D orbit path, periodic look-at lines, camera marker moving along the path. For intuition ("that's a camera circling the subject"). Export a rotating animation to `AirLine/outputs/day7_orbit_3d.mp4`.
- **Tri-view orthographic projections — top (XY), side (XZ), front (YZ)** of the same path: for *catching lies*. A subtly wrong path (drift, ellipse, off look-at) looks obviously wrong in at least one orthographic view even when the 3D plot looks fine. Export `AirLine/outputs/day7_orbit_triview.mp4` (or a stacked panel).

Both drive off the SAME `flightpath` code (validate the real path, not a parallel mock). Use matplotlib (already available) — **do NOT build or pull in a 3D game engine / real renderer.** These are schematic verification views, not photoreal imagery.

---

## Integration with existing seams

- **Add `ORBIT` to the `Shot` enum** (Day-5 extension point) and a **`SHOT_ORBIT` `IntentCommand`**. `request_shot(ORBIT)` engages the 3D orbit path.
- **Trigger today via mock/scripted intent or keypress** (reuse Day-6 `--mock`). **Do NOT add a new webcam gesture** for orbit today — recognizing circular-hand-motion is its own reliability problem (cf. swipe at 60%) and would confound "is the bug in the path or the gesture?". Path first; orbit-gesture later.
- tight/wide/AUTO behaviour must remain **provably unchanged** (regression guard).

---

## Modules the agent MAY touch

- New files in `AirLine/` (`flightpath.py` for 3D orbit kinematics, `sim_orbit3d.py` for both visualizations, `run_day7.py`).
- Additive extension of the Day-5 named-shot seam (`Shot` enum + dispatch) and a new intent type — **pre-approved additive extension points**; existing tight/wide/AUTO must stay unchanged.
- New tests in `tests/airline/`.
- `PRD/`.

## DO NOT TOUCH list (hard constraint)

- Any SideLine CV script, model, config, tracker tuning; `backend/`, `Website/`, existing `tests/backend/`, `tests/frontend/`.
- `core_bridge`, `TargetTracker` contracts — consumed, not modified.
- `VirtualCamera`'s existing **crop/follow/drift 2D motion logic** — orbit is a NEW 3D path mode alongside it, not a rewrite. Existing `test_camera.py` must pass unchanged.
- The two-process bridge protocol (reuse as-is if triggering orbit over it).
- **Nothing outside `AirLine/` and `tests/airline/`** (plus `PRD/`) **may be modified.** Both venvs intact.
- If orbit cannot integrate without changing frozen motion logic or a contract → STOP and flag.

---

## Steps

1. **Clean start.** Branch `airline`, tree clean. Baseline main `.venv`: **121 passed + known `test_video_io.py` error unchanged.** Both venvs intact.
2. **`flightpath.py`** — 3D orbit kinematics, tiltable plane, documented convention. Pure math.
3. **3D invariant tests** (`tests/airline/test_flightpath.py`) — all 7 invariants above, incl. tilted AND level cases, plus moving target.
4. **`sim_orbit3d.py`** — both the rotating 3D plot and the tri-view projections, off the real path code.
5. **Seam integration** — `ORBIT` shot + `SHOT_ORBIT` intent; tight/wide/AUTO untouched; trigger via mock/keypress.
6. **`run_day7.py`** — scripted/mock intent: select target → request ORBIT → both visualizations render; export the two videos.
7. **Full suite** main `.venv`: 121 + Day-7 tests; existing `test_camera.py` unchanged; `test_video_io.py` unchanged.

---

## Definition of Done (measurable — no "it should work")

- [ ] **Two visible proofs:** `day7_orbit_3d.mp4` (rotating 3D) and `day7_orbit_triview.mp4` (top/side/front) both show a camera on a constant-radius circle in a (possibly tilted) plane, always looking at the target — including around a *moving* target.
- [ ] **Numbers — 3D path invariants hold:** report measured (a) 3D radius mean ± deviation (near-constant), (b) max look-at error angle (~0°), (c) max out-of-plane distance (~0), (d) period-closure error. These prove the math; the videos are secondary.
- [ ] **Tilt actually demonstrated:** show at least one genuinely tilted orbit (non-vertical plane normal) AND the level special case, with altitude-constant asserted ONLY for the level case.
- [ ] **Seam regression proof:** tight/wide/AUTO on the football clip unchanged from Day 6; existing `test_camera.py` green unchanged.
- [ ] Orbit triggerable through the intent path (mock/scripted) — slots into existing architecture, no new gesture.
- [ ] Full suite green at 121 + Day-7; `test_video_io.py` unchanged; both venvs intact; `git diff` only under `AirLine/`, `tests/airline/`, `PRD/`.

---

## The localization caveat (state it honestly in the notes — do NOT gloss)

The orbit *path* is rigorously 3D. But the **target's 3D position is an approximation**: the fixed football camera gives a 2D image position with no true depth, so the orbit center is derived via a documented 2D→ground-plane assumption (target on a flat ground plane). For verifying the *path math* this is fine (we define the world). What remains genuinely deferred:
- **True 3D target localization** (real depth for the subject), and
- **View synthesis** — there is NO real imagery of the subject from the orbiting camera's poses (the clip is one fixed viewpoint). The sim shows where the camera *would be* and *roughly frame*, not a synthesized real view.
Both await a real moving camera / multi-view capture (i.e. the actual drone). The notes must say plainly: **path = rigorous 3D; target depth & view-from-pose = approximated/deferred.** Do not present the 2D→ground mapping or the schematic view as exact.

---

## Rollback note

Orbit + sim are additive new modules; the seam extension is the only touch to existing code, guarded by "existing camera tests pass unchanged." If orbit can't be added cleanly, revert and flag — orbit can wait. Days 1–6 committed and intact; `main` untouched. Visualization deps: matplotlib only (already present); writing mp4 from matplotlib may need ffmpeg — if unavailable, fall back to a GIF or PNG-sequence and flag, don't add heavy deps.

---

## Explicitly NOT in scope today (deferred — do not start)

- **Push-in and dolly** — next primitives, reuse today's `flightpath` machinery once orbit is proven.
- **Spiral / radius-changing / height-ramping orbits** — different primitives; today's orbit is a circle in a tiltable plane (the scope guard).
- A **webcam gesture for orbit** — its own reliability problem; today triggers via intent/mock.
- **Real 3D rendering / photoreal view synthesis** — sim is schematic matplotlib, not a renderer.
- **Real drone flight dynamics** (inertia/wind/motor limits) — not modelled, not half-modelled.
- **True 3D target localization / homography-under-motion** — deferred; orbit uses the documented 2D→ground approximation.
- Re-identification; LLM intent layer; real glove; actual drone/flight.

---

## Note to the agent (Claude Code)

Conceptual step up: 3D paths over time, not crops. Discipline: **narrow scope (orbit only), prove by 3D invariants, two schematic views, honest about what's approximated.** Build the general tiltable-plane orbit (level = special case) so the math is correct in general. Test by geometric invariants — and do NOT assert constant altitude for tilted orbits (that's a false invariant; the in-plane + constant-radius checks are the right ones). Extend the Day-5 seam additively; tight/wide/AUTO stay provably unchanged. Be explicit in the notes that the path is rigorous 3D while target depth and view-from-pose remain approximated/deferred — do not let the schematic sim masquerade as real imagery. Close with the invariant measurements, notes.md-style.
