# PRD — Day 17: Head-FP Fix (final cheap attempt before TrackNet) — Basketball Ball Track
**Project:** AI Sports Recording & Analytics System
**Goal:** Kill the residual head-as-basketball false positives in the basketball ball track — the FP class the Day-16 proximity prior CAN'T catch (a head is the most player-proximate object). Diagnose head-latching first, then test three targeted fixes (head-zone exclusion, size gate, motion-consistency) independently. THIS IS THE FINAL CHEAP ATTEMPT: if it fails the bar, TrackNet is the evidenced next step. Basketball, SportsMOT.
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; Day-16 ball track + FP diagnostic (`scripts/diagnose_ball_fp.py`, `analyze_ball_basketball.py`), Day-9 player tracks, `follow_cam_basketball.py`

---

## Context (read first)

Day-16 fixed the CORNER false positives (scoreboard/banner) with a player-proximity prior: A-feed FP-latch 16.9%→0.4% (c001), 10.2%→0.0% (c007), safezone 0.51→0.75 / 0.76→0.88. BUT the user re-watched and the camera STILL sometimes switches to a person's HEAD as the ball — even when the real ball is visible.

**Why proximity can't catch this:** a head is ON a player — the MOST player-proximate object on court. It sails through the 150px reinit / 300px in-gate proximity prior. It's round, ball-sized, ball-ish in some lighting, attached to a person. So head-FPs are a DIFFERENT, HARDER class than the corner FPs Day-16 solved.

**Why this is the FINAL cheap attempt:** this is the 3rd session on basketball ball FPs (15 wobble, 16 corner-FP, 17 head-FP). Head-FPs have obvious cheap levers NOT yet tried (below). But an open-ended patch loop is a trap. So: defined bar + escalation trigger. If the cheap head-fixes don't clear it, TrackNet (temporal-consistency detection that learns ball-vs-head motion) is the EVIDENCED next step, with this session's failure cases as its spec.

**The escalation bar (decide PASS/FAIL against this):**
- PASS (TrackNet NOT needed): head-FP-latch rate < ~2% AND re-watch shows the camera stays on the real ball when it's visible AND the liked dribble/pass/shot tracking survives.
- FAIL (TrackNet justified): head-latching persists above bar despite all three fixes, OR fixing it breaks real-ball tracking (the fixes are too blunt) → TrackNet, with documented failure cases.

**Scope: BASKETBALL ball track + A-feed re-watch.** No football, no highlights, C-feed is fine.

---

## PART 0 — Diagnose head-latching specifically (~45 min)
Extend the Day-16 diagnostic (`diagnose_ball_fp.py`) to flag HEAD-region detections:
1. For each 'detected' ball frame, check if the picked ball sits in the HEAD ZONE of a nearby player box — top ~15-20% of a player bbox, horizontally centered. Flag as head-FP-suspect.
2. Quantify: what % of 'detected' frames are head-FP-suspect? What % of A-feed safezone misses are head-driven (vs the edge-clamp/lag that's legitimately left after Day-16)?
3. Render the debug overlay with head-zone boxes drawn + head-FP flags. WATCH: confirm the residual wobble is head-latching (camera jumps to a head while the real ball is elsewhere/visible).
4. Also measure SIZE: are head-FP detections larger (px area) than real-ball detections at similar court depth? (Tests whether the size gate will work.)

**STOP. Report: head-FP rate confirmed + quantified? Is it the residual wobble? Are heads size-separable from the ball?**

---

## PART A — Three head-FP fixes, measured INDEPENDENTLY (~80 min)
Apply each as a separately-gated flag (A/B isolation discipline from Day-16 — one variable at a time), measure each's effect on head-FP-latch + safezone + (critically) whether real-ball tracking regresses:

1. **Head-zone exclusion:** reject/down-weight ball detections landing in the top ~15-20% of a player box (the head region). Tune the zone height. RISK: a ball held UP high (overhead pass, rebound reach) could be in a head zone — so make it a down-weight or require corroboration, not a hard kill, and watch for losing high-held balls.

2. **Size gate:** reject ball detections whose pixel area is inconsistent with the expected ball size at that court location (heads are typically bigger). Calibrate expected ball-size from confident real-ball detections. RISK: perspective changes ball size across the court — calibrate per-region or with generous tolerance.

3. **Motion-consistency (the poor-man's TrackNet):** reject detections whose recent motion matches a PLAYER's gait (bobbing, human-speed, tracks a player) rather than ball physics (flies/bounces/arcs, decouples from any single player). This is cheap temporal discrimination — the key idea TrackNet would learn, hand-crafted. RISK: a slow dribble near a walking player could look player-like — tune carefully.

Measure each fix ALONE vs the Day-16 baseline, then the best combination. Keep what reduces head-FP WITHOUT regressing dribble/pass/shot tracking.

**STOP. Report: each fix's effect (head-FP-latch + safezone + any real-ball regression)? best combination?**

---

## PART B — Re-render + RE-WATCH against the bar (~40 min)
1. Re-render A-feed (best combination) + head-flag debug overlay, both seqs.
2. WATCH against the PASS/FAIL bar: head-FP-latch < ~2%? camera stays on the real ball when visible? dribble/pass/shot tracking survived?
3. Be honest: if it's better but not clean, or if killing heads cost real-ball tracking, that's closer to FAIL → TrackNet.

**STOP. Report: PASS or FAIL against the bar? The honest re-watch verdict.**

---

## PART C — The decision + log + commit (~35 min)
1. notes.md `## Day 17`: head-FP diagnosis + rate, the three fixes measured independently, best combination, the re-watch verdict, and THE DECISION:
   - **PASS** → basketball ball track done (corner-FPs Day-16 + head-FPs Day-17 both cleared); follow-cam A-feed watchable; both sports at parity; proceed to highlights.
   - **FAIL** → TrackNet is the evidenced next step; document EXACTLY which head-FP cases survived the cheap fixes (the spec for TrackNet), and note the data-sourcing cost flagged earlier (consecutive-frame ball GT scarce → hand-label or bootstrap).
   - Honest framing: this was the final cheap attempt; the staged escalation (cheap-first, measure, escalate-with-evidence) is the project's discipline, and either outcome is a clean, defensible result.
2. Keep the corrected eval metrics (safezone + FP-latch PRIMARY, jerk secondary) from Day-16.
3. gitignore checks; commit:
   `git commit -m "Day 17: head-FP fix attempt (head-zone/size/motion-consistency); [PASS basketball ball done / FAIL TrackNet justified]"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Head-FP rate confirmed in Part 0? is it the residual wobble?
3. Each fix's independent effect (head-FP-latch, safezone, real-ball regression)
4. Best combination + its numbers
5. RE-WATCH verdict vs the bar: PASS or FAIL?
6. If PASS: is the A-feed finally watchable, dribble/pass/shot intact?
7. If FAIL: which head cases survived (TrackNet spec)? confirm willingness to take on the data-labeling cost
8. Errors hit (even if fixed)
9. Time taken

---

## Do NOT today
- Do NOT skip Part 0 — confirm + quantify head-latching before fixing (it must be the actual residual, not lag/edge-clamp).
- Do NOT apply the three fixes together blindly — isolate each (one-variable discipline; Day-16's isolation bug is the cautionary tale).
- Do NOT kill head-FPs at the cost of real-ball tracking — a fix that breaks dribble/pass/shot tracking is a FAIL, not a win. Check both every time.
- Do NOT trust jerk/smoothness — safezone + head-FP-latch are the truth metrics; the re-WATCH is the verdict.
- Do NOT patch beyond this session — if the bar isn't met, escalate to TrackNet (don't start a Day-18 of more cheap patches).
- Do NOT do football / highlights / C-feed.
- Do NOT commit datasets/weights/videos.
