# PRD — Day 22: Basketball Team Assignment (torso-color, court-position aided, hand-label validated)
**Project:** AI Sports Recording & Analytics System — for DPS Modern Indian School, Doha
**Goal:** Assign basketball players to teams (Team A / Team B / referee-or-bench excluded) via torso-color clustering, using the new homography's court positions to exclude off-court people, aggregated per-tracklet, VALIDATED against a hand-labeled set (Claude Code builds an easy labeling app). Closes the last basketball parity gap → unlocks basketball team-split heatmaps + possession. Basketball, SportsMOT (proxy for DPS deployment).
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; basketball player tracks (Day-9), Day-21 court homography, Day-11 football `team_assign.py` to adapt

---

## PROJECT GOAL CONTEXT (re-anchored — read first)
This is a DEPLOYABLE system for DPS MIS Doha: fixed dual-phone wide capture of DPS football + basketball → one shared CV pipeline → three outputs (coach analytics, per-player highlights, event reels) for coaches/players/Student Council. SoccerNet/SportsMOT are PROXIES to build+validate the method; the real target is DPS's own courts/teams/kits.

**This is WHY the method must be torso-color clustering, NOT a luminance shortcut.** The NBA/NCAA home-light/away-dark convention is a broadcast artifact — DPS house/school teams won't reliably follow it (similar PE kits, bibs, house colors). Torso-color clustering transfers to whatever DPS actually wears; luminance would overfit the proxy and break at deployment. (Same deployment-first reasoning as the Day-21 court-markings robustness and the Day-19 court-color-leak concern.)

---

## Context
Day-21 gave basketball a court homography → team-AGNOSTIC analytics. The last gap to football parity is TEAM ASSIGNMENT (football got it Day-11: torso a/b-chroma clustering, GK/ref handled, 88-92% GSR-validated). This session is the basketball equivalent.

**Basketball differences from football Day-11:**
- **No GT** (SportsMOT has no team labels) → validate against a HAND-LABELED set (real accuracy number, user's choice).
- **No goalkeeper** (simpler than football); refs (striped/grey) + bench/sideline are the non-two-team people.
- **Court-position lever (NEW):** the Day-21 homography means off-court people (bench, refs near sideline) can be excluded by position — a tool football Day-11 didn't have.
- **More skin exposure** (arms/legs) → torso-region sampling matters even more (sample jersey, not limbs).

**Scope: BASKETBALL team assignment.** Then regenerate the Day-21 PDF WITH team-split heatmaps + possession (the deferred panels).

---

## PART A — Hand-label set: easy labeling app (~40 min, user-driven)
Claude Code builds a DEAD-SIMPLE labeling app (like the Day-19 ball/head sorter that worked well):
1. Auto-crop player detections (from Day-9 tracks) across a few basketball clips → present each crop with CLEAR instructions ("click: Team A / Team B / Referee / Bench-or-other").
2. The app shows the crop + ideally the wider frame context (so the user can tell which team) + a button per class. Saves crop→label. Pre-seed nothing; user labels a few hundred crops (~enough for a validation set + optional small train).
3. Explicit instructions in-app: what counts as Team A vs B (pick by jersey, the user will see which is which), referee = striped/official, bench = sideline/tracksuit.

**STOP. Report: labeling app works? how many crops labeled per class? labeling time? was it easy enough?**

---

## PART B — Court-position player filter (~30 min)
1. Using the Day-21 homography, project each detection's court position. Players are ON the court; bench/refs/sideline are OFF or at the boundary.
2. Filter: keep detections within the court bounds (+ small margin) as team-assignment candidates; flag off-court as non-players (bench/ref-likely). Note how many excluded.
3. This reduces the ref/bench contamination BEFORE clustering — the homography assist football Day-11 lacked.

**STOP. Report: court-position filter working? fraction excluded as off-court? does it look right (bench/sideline removed)?**

---

## PART C — Torso-color team clustering (~60 min)
Adapt Day-11's approach (the proven football method), basketball-tuned:
1. **Torso region only** (upper-central bbox; AVOID arms/legs — more skin in basketball). Sample color.
2. **Color space:** a/b chroma (lighting-robust, as Day-11 found) — or test Lab full vs a/b. NOT a luminance shortcut (deployment reasoning above).
3. **Cluster on-court players into 2 teams.** Refs (striped/grey, low chroma) fall out as outliers (like football's refs) — combine with the court-position filter for cleanup.
4. **Per-tracklet majority vote** (not per-frame) — stable, leverages tracking. Split-vote tracks flag ID switches.
5. Assign: Team A / Team B / referee(-or-excluded).

**STOP. Report: 2 team clusters emerge cleanly? refs/bench separated (color + court-position)? per-track assignments produced?**

---

## PART D — Validate against the hand-labeled set (~40 min)
1. Match assignments to the hand-labeled crops. **Team accuracy with label-permutation** (cluster IDs arbitrary vs your A/B labels — try both mappings, take the better; the Hungarian-alignment lesson from football Day-11).
2. Report: outfield-equivalent team accuracy (the main number), ref/bench exclusion accuracy. Compare to football's 88-92% (with the caveat: football was GT-validated, this is hand-label-validated — your labels ARE the reference, so note label-noise possibility).
3. Sanity floor: random 2-team = 50%; useful system well above (target 85%+ on distinct kits, as football).

**STOP. Report: team accuracy (post-alignment)? ref/bench accuracy? above 85%?**

---

## PART E — Regenerate basketball PDF WITH teams + log + commit (~40 min)
1. Now that teams exist, regenerate the Day-21 basketball coach deliverable WITH the previously-deferred panels: **team-split heatmaps** (per-team) and **possession** (nearest-player-to-ball by team, the Day-12 football method). Move these from "coming soon" into the PDF.
2. Update the tactical video with TEAM COLORS (no longer team-agnostic single-green).
3. notes.md `## Day 22`: the DPS-deployment reasoning for torso-color (not luminance), the labeling app, court-position filter, clustering method, hand-label validation accuracy, the now-team-aware PDF/video, and:
   - Basketball now at FULL analytics parity with football (team-split + possession added).
   - Honest level: hand-label-validated (your labels are the reference), team-split/possession inherit tracking ID-switch noise → still plausibility-level downstream, like football's possession.
   - Deployment note: torso-color clustering chosen to transfer to DPS kits; per-match color calibration likely needed (as football Day-11 found constants aren't universal); similar-kit DPS teams are the deployment risk (embeddings/Day-9-ReID would help).
   - What's next: highlights (A-feed events, C-feed player) — both sports now fully analytics-equipped.
gitignore checks; commit scripts + notes + updated basketball package:
`git commit -m "Day 22: basketball team assignment (torso-color + court-position, hand-label validated); team-split heatmaps + possession; full analytics parity"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Labeling app easy? crops/class labeled? time?
3. Court-position filter: fraction excluded as off-court, looks right?
4. 2 team clusters clean? refs/bench separated?
5. Team accuracy vs hand-labels (post-alignment) — above 85%?
6. Regenerated PDF with team-split heatmaps + possession? tactical video team-colored?
7. Basketball now at full analytics parity with football?
8. Errors + time

---

## Do NOT today
- Do NOT use a luminance shortcut — torso-color clustering (transfers to DPS kits; luminance overfits the broadcast proxy and breaks at deployment).
- Do NOT sample the whole bbox or limbs for color — torso region only (basketball = lots of skin).
- Do NOT cluster into k=2 blindly without ref/bench handling — use color outlier + court-position filter.
- Do NOT assign per-frame — per-tracklet majority vote.
- Do NOT use the hand-labels to MAKE the assignment — assign blind, validate after (using them to assign inflates accuracy; the Day-11 lesson).
- Do NOT forget label-permutation (Hungarian) in validation — or correct assignment can look like 50%.
- Do NOT re-run detection/tracking — reuse Day-9 + Day-21 homography.
- Do NOT claim GT-validation — it's hand-label-validated (your labels are the reference; note label-noise).
- Do NOT commit oversized video or license-encumbered crops.