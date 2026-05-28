# PRD — Day 10: First Deliverable — Player Heatmaps + Distance Covered (Football)
**Project:** AI Sports Recording & Analytics System
**Goal:** Build the FIRST stakeholder-facing deliverable on top of the tuned tracking foundation: per-player and team positional HEATMAPS, and DISTANCE COVERED in real meters (via homography). Validate distance against SoccerNet GSR's official pitch coordinates. Football, SoccerNet.
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; tuned football tracker config from Day 9; SoccerNet GSR subset with tracking + `bbox_pitch` already on disk

---

## Context (read first)

The detect+track foundation is complete and tuned (Day 1-9). Production football tracker: BoT-SORT + GMC (sparseOptFlow) + match_thresh=0.9, HOTA ~59.8 on SoccerNet. This session turns tracking into a DELIVERABLE: heatmaps + distance covered — the first thing a coach would actually look at.

**This is a NEW KIND of work.** Days 1-9 measured against ground truth with a trust gate (score 1.0). Heatmaps/distance have NO direct ground truth — the new failure mode is producing authoritative-looking numbers that are quietly wrong (bad homography, ID-switch corruption, jitter inflation). The discipline shifts from "gate against GT" to "validate against physical plausibility AND a known reference."

**The key asset:** SoccerNet GSR annotations include `bbox_pitch` — real pitch coordinates in METERS via the dataset's official homography. This gives us a REFERENCE to validate our own distance computation against. Use it — it's the trust gate for this session.

---

## Sport & data
- **Football, SoccerNet GSR subset** (the 5 seqs from Day 8, SNGS-116..120). Football chosen because: pitch line markings make homography tractable, and GSR's `bbox_pitch` gives a validation reference.
- Use the Day-9 production tracker config to generate player tracks (or reuse Day-9 cached tracker outputs if available).

---

## PART A — Generate clean player tracks (~30 min)
1. Using the Day-9 production football config (BoT-SORT + GMC + match_thresh=0.9), produce per-player tracks (frame, id, bbox) for the 5 SoccerNet seqs. Reuse Day-9 cached detections + tracker outputs if already on disk — don't re-run detection.
2. For each track, derive a single ground-point per player per frame: the BOTTOM-CENTER of the bbox (feet position) — NOT the box center. Distance/position is about where the player stands on the pitch, i.e. their feet. (Box center drifts with player height/pose; feet are the pitch contact point.)
3. Output: per-seq, per-player pixel trajectories (list of (frame, x_feet, y_feet)).

**STOP. Report: tracks generated for 5 seqs? feet-point extraction sane (spot-check a few)?**

---

## PART B — Homography: pixel → pitch meters (~70 min, the hard part)
1. **Establish the pixel→pitch mapping.** Options, in order of preference:
   - **(a) Use GSR's provided homography/camera params if present.** SoccerNet GSR ships camera calibration for many sequences. If the per-seq calibration (or the homography implied by matching `bbox_image` ↔ `bbox_pitch` pairs) is available, DERIVE the homography from those image↔pitch point correspondences directly. This is the most accurate path and leverages the dataset.
   - **(b) Manual point correspondence.** If no calibration, pick ≥4 recognizable pitch landmarks per seq (penalty box corners, center circle intersections, halfway line ends) with known real-world pitch coordinates (standard pitch = 105×68 m; SoccerNet provides the template), mark their pixel locations, compute the homography matrix (cv2.findHomography / getPerspectiveTransform).
2. Apply the homography to each player's feet-pixel trajectory → trajectory in pitch meters.
3. **VALIDATION (the trust gate for this session):** independently, compute player positions from GSR's `bbox_pitch` (official meters). Compare YOUR homography-derived positions to GSR's for the same players/frames. They should agree within a small tolerance (e.g. <2-3 m positional error, and aggregate distances within ~5-10%). If they diverge wildly, the homography is wrong — FIX before trusting any distance number.

**STOP. Report: homography source (a or b)? Validation vs GSR bbox_pitch — positional error and distance agreement? Pass/fail?**

---

## PART C — Distance covered (with smoothing) (~40 min)
1. For each player, the naive distance = sum of frame-to-frame displacement of the feet-position in meters. BUT raw frame-to-frame summation INFLATES distance because detection jitter adds spurious motion to even a standing player.
2. **Smooth the trajectory before summing:** apply a simple trajectory smoother (moving average, Savitzky-Golay, or a light Kalman smoother) to the meter-space positions. Then sum displacement. Report BOTH raw and smoothed totals so the inflation is visible/quantified.
3. **Sanity-check against physical plausibility:** a footballer covers roughly 9-12 km in a 90-min match ≈ ~100-130 m per 30s clip of active play (less if standing). Your per-player 30s distances should be in a believable range — flag any player "covering" implausible distances (a sign of ID switches stitching two players' paths, or jitter).
4. **Caveat per-player numbers with ID-switch risk:** where AssA ~0.50, some per-player totals are corrupted by ID switches. The aggregate/team distance is more robust than individual totals. State this.

**STOP. Report: raw vs smoothed distances? plausibility check? which players look ID-switch-corrupted?**

---

## PART D — Heatmaps (~40 min)
1. **Team/aggregate positional heatmap:** accumulate all players' feet-positions (in pitch meters) over a sequence into a 2D density map, overlaid on a pitch diagram. This is ROBUST to ID switches (it's positional density, identity-agnostic) — the safest, most visual deliverable.
2. **Per-player heatmap:** density map for individual tracked players. Note these inherit ID-switch error — a player's heatmap may include another's positions where IDs swapped.
3. Render heatmaps as clean visuals overlaid on a to-scale pitch (use the pitch-meter coordinates from the homography, so the heatmap is geometrically correct, not pixel-distorted).
4. Output: `outputs/deliverables/heatmap_team_<seq>.png`, `outputs/deliverables/heatmap_player<ID>_<seq>.png`.

**STOP. Report: heatmaps rendered? do they look plausible (play concentrated where you'd expect)?**

---

## PART E — Package, log, commit (~30 min)
1. Produce a small sample "coach-facing" output: one sequence's team heatmap + a per-player distance table (smoothed, with the ID-switch caveat noted). This is the prototype of the eventual coach deliverable.
2. Append `## Day 10` to notes.md: homography source + validation result vs GSR bbox_pitch (the trust gate), raw-vs-smoothed distance, plausibility check, heatmap outputs, and:
   - What's trustworthy (team heatmap, validated distance) vs what's caveated (per-player totals under ID switches).
   - The honest limitation: this is on SoccerNet footage; real DPS MIS deployment needs the school's pitch dimensions for the homography + own footage validation.
   - What the next deliverable needs (team assignment for possession; ball tracking for follow-cam).
3. Confirm deliverables/, datasets (incl SoccerNet/NDA), caches, weights, videos gitignored; commit scripts + notes + the SAMPLE deliverable images (the heatmap PNGs are derived visuals, not raw NDA data — safe to commit IF they don't embed identifiable raw frames; if unsure, gitignore them too):
   `git commit -m "Day 10: first deliverable — player heatmaps + homography-based distance covered (football); validated vs GSR pitch coords"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Homography source (GSR calibration or manual points)?
3. **Distance validation vs GSR bbox_pitch: positional error + distance agreement — did it pass?** (the session trust gate)
4. Raw vs smoothed distance — how much did jitter inflate?
5. Per-player plausibility — any ID-switch-corrupted totals spotted?
6. Heatmaps — do they look right? (screenshot)
7. What's trustworthy vs caveated in this deliverable
8. Errors hit (even if fixed)
9. Time taken

---

## Do NOT today
- Do NOT report distance without the GSR bbox_pitch validation — an unvalidated homography gives authoritative-looking wrong numbers (the new failure mode).
- Do NOT sum raw frame-to-frame distance without smoothing — it inflates via jitter; report both so the effect is visible.
- Do NOT present per-player totals without the ID-switch caveat — aggregate is robust, per-player is fragile at AssA ~0.50.
- Do NOT use bbox CENTER for position — use feet (bottom-center); position is about pitch contact point.
- Do NOT re-run detection/tracking from scratch — reuse Day-9 tracks/caches.
- Do NOT commit SoccerNet raw data (NDA); be cautious even with rendered frames if identifiable.
- Do NOT start team assignment or ball tracking — those are the NEXT deliverables' prerequisites, separate sessions.
