# PRD — Day 21: Basketball Court Homography (auto + manual fallback) + Basketball Analytics PDF
**Project:** AI Sports Recording & Analytics System
**Goal:** Build a basketball court homography (pixel→court-meters) robust to messy/missing school-court lines — auto-detect with a MANUAL one-time point-marking fallback (matches fixed-camera deployment) — then assemble the first basketball coach analytics PDF on top. Plausibility-validated (no court-meter GT exists). Basketball, SportsMOT.
**Estimated time:** 4–5 hours (homography + analytics PDF in one session; full session)
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; basketball player tracks (Day-9), basketball ball track (Day-19 cleaned), Day-20 `coach_deliverable.py` to adapt for the PDF; SportsMOT basketball clips

---

## Context (read first)

Football has a coach analytics deliverable (Day-20). Basketball can't match it because basketball ball/player tracking is all PIXEL-space — there's no court homography (football's Day-10 homography is what made heatmaps/distance/territory real in meters). This session builds the basketball court homography to unlock basketball analytics parity.

**Two things make basketball homography DIFFERENT from football's Day-10:**
1. **No GT reference.** Football's GSR shipped `bbox_pitch` (real pitch meters) → validated to 0.2m. Basketball has NO court-meter GT (SportsMOT = pixel boxes only; Day-18 confirmed basketball ball/coord GT is a dead-end hunt). So homography is PLAUSIBILITY-validated, not GT-validated — same honesty level as the Day-19 basketball ball track. Label it so.
2. **Deployment-court uncertainty (user-flagged, important).** The user does NOT know their school court's state — it may have faded/missing/multi-sport-overlaid/non-regulation/outdoor markings. So the method must be ROBUST to messy lines, NOT assume clean regulation markings. Design = AUTO-detect court landmarks, with a MANUAL one-time point-marking FALLBACK. The fixed deployment camera (no zoom/cuts) means manual marking is done ONCE and holds — the robust real-world path.

**Scope honesty — basketball analytics will be ONE COMPONENT BEHIND football's:** football's PDF had team-split heatmaps + possession because Day-11 built football team assignment. BASKETBALL HAS NO TEAM ASSIGNMENT YET. So this basketball PDF is TEAM-AGNOSTIC: all-players heatmap, total distance, court territory, intensity zones, average positions. Team-split heatmaps + possession are DEFERRED to a future basketball-team-assignment session. State this clearly (parity of METHOD, not yet of completeness).

---

## PART A — Build the court homography: auto-detect + manual fallback (~80 min)
1. **Define the court model:** standard FIBA 28×15 m (note NBA 28.65×15.24 alt); encode the known real-world coordinates of court landmarks (corners, center line, center circle, the two free-throw lanes/keys, three-point arcs). This is the target coordinate system.
2. **AUTO path (try first):** detect court lines/landmarks in a frame (line detection / court-template fitting) and match to the model → homography (cv2.findHomography). If the detected landmarks are sufficient and the fit is good (low reprojection error), use it.
3. **MANUAL fallback (always available):** a tool that shows one frame and lets the user CLICK ≥4 known court points (whatever the court actually has — corners are the most robust, present on nearly any court) → map to their known real coords → homography. This is the deployment-realistic path (works on faded/messy/multi-sport courts; fixed camera = mark once).
   - Design the manual tool to need only points the user can actually SEE — degrade gracefully to just the 4 court corners + known court dimensions if that's all that's identifiable.
4. On SportsMOT: since broadcast cameras MOVE, either pick a stable-camera segment for a single homography, or mark per-segment. Note that the real fixed-camera deployment is EASIER than this (mark once, holds all match).

**STOP. Report: auto-detect work on the test clip? manual fallback functional? homography produced? reprojection error of the marked points?**

---

## PART B — Validate by PLAUSIBILITY (no GT — the honest trust level) (~40 min)
No court-meter GT, so validate against known geometry + physics:
1. **Court reconstruction:** apply homography to known court features (e.g. the center circle, the key rectangle) — do they reconstruct to their KNOWN real dimensions (center circle 3.6m radius, key 5.8×4.9m, etc.)? Report the error on features NOT used to fit the homography (held-out landmarks = the closest thing to a trust gate here).
2. **In-bounds check:** apply to player tracks — do players stay within/near the 28×15m court bounds? Players flying off to 50m = bad homography.
3. **Speed sanity:** player speeds in basketball-plausible range (sprints ~6-8 m/s, not 30).
4. Label the result explicitly: "plausibility-validated, no court-coordinate GT (cf. football's 0.2m GT-validation) — same honesty level as the Day-19 basketball ball track."

**STOP. Report: held-out court-feature reconstruction error? players in-bounds? speeds sane? plausibility verdict?**

---

## PART C — Basketball analytics (team-agnostic) (~60 min)
Apply the homography to existing basketball player+ball tracks (reuse Day-9/Day-19; do NOT re-run detection/tracking). Compute, in court-meters:
1. **All-players positional heatmap** (team-agnostic — no team assignment yet) on a to-scale court diagram.
2. **Total distance covered** (team-agnostic; smoothed, with the >10 m/s ID-switch teleport guard from Day-20).
3. **Court territory:** % of play (player+ball position points) per court zone (e.g. by court thirds or by half).
4. **Intensity zones:** velocity bucketed into basketball-appropriate speed bands (cite a basketball-specific source if available; else note the football-band caveat and adjust — basketball sprints are shorter/faster bursts).
5. **Average positions:** per-well-tracked-ID mean court position (the ≥150-frame cutoff trick from Day-20 to avoid ID-fragment phantoms).
Plausibility-check each (territory sums to 100%, intensity bands sum to distance, positions on-court).

**STOP. Report: basketball analytics computed + plausibility-checked? heatmap look like real basketball court usage?**

---

## PART D — Basketball coach PDF + tactical video (~50 min)
1. Adapt Day-20 `coach_deliverable.py` for basketball: the team-agnostic analytics into a coach PDF, same VALIDATED-vs-DERIVED honesty structure — BUT note the validated band is thinner here (homography is plausibility-validated, not GT-validated), so be honest about the trust level.
2. **DEFERRED section (honest):** team-split heatmaps, possession (need basketball team assignment — a future session), passes, per-player stat lines (per the football deferrals). State why.
3. Tactical video: wide view with basketball player tracking + ball drawn on (no team colors yet — team-agnostic), clean coach overlay.
4. Package → `outputs/deliverables/coach_package_basketball/`.

**STOP. Report: basketball PDF + video generated? coach-readable? honesty labels correct (plausibility-level)?**

---

## PART E — Log + commit (~30 min)
notes.md `## Day 21`: the deployment-court-uncertainty reframe (auto + manual fallback, why manual fits fixed-camera deployment), homography method + plausibility validation (held-out reconstruction error), the team-agnostic basketball analytics, the PDF/video, and:
- Honest status: basketball analytics now at parity of METHOD with football, but ONE COMPONENT BEHIND (no team assignment → no team-split/possession yet).
- The deployment note: this homography approach (esp. manual marking) is designed to transfer to the school's actual court whatever its line state; real validation pending own footage.
- What's next: basketball team assignment (unlocks team-split/possession parity); football+basketball highlights (A/C feeds).
gitignore checks; commit scripts + notes + basketball package:
`git commit -m "Day 21: basketball court homography (auto + manual fallback, plausibility-validated) + team-agnostic basketball analytics PDF/video"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Auto-detect work? manual fallback functional? reprojection error?
3. Plausibility validation: held-out court-feature reconstruction error? players in-bounds? speeds sane?
4. Basketball analytics computed + plausible? heatmap look like real court usage?
5. Basketball PDF + video coach-readable? honesty labels at the right (plausibility) trust level?
6. Is the team-agnostic limitation clearly stated (team-split/possession deferred)?
7. Errors hit (even if fixed)
8. Time taken

---

## Do NOT today
- Do NOT assume clean regulation court markings — build robust to messy/missing lines (auto + manual fallback); the school court is an unknown worst-case.
- Do NOT present the homography as GT-validated — it's PLAUSIBILITY-validated (no court-meter GT, cf. football's 0.2m). Label honestly.
- Do NOT fake team-split heatmaps or possession for basketball — no team assignment yet; defer with the honest reason.
- Do NOT invent intensity bands without basis — cite basketball-appropriate thresholds or caveat the football-band reuse.
- Do NOT re-run detection/tracking — reuse Day-9 player + Day-19 ball tracks.
- Do NOT forget the >10 m/s ID-switch teleport guard (Day-20) in distance/intensity.
- Do NOT do football or highlights this session.
- Do NOT commit oversized video or license-encumbered data.
