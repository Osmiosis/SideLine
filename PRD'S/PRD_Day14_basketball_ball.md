# PRD — Day 14: Basketball Ball Tracking (pixel-space Kalman) — parity with football Day-12
**Project:** AI Sports Recording & Analytics System
**Goal:** Build basketball ball tracking — the Day-12 equivalent — so basketball can reach follow-cam parity with football. Pixel-space Kalman over the fine-tuned basketball ball detector, bridging detection gaps. Validate vs WASB ball-trajectory GT if accessible, else plausibility (accepted honestly). Basketball, SportsMOT/own clips.
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; fine-tuned basketball ball detector (`models/basketball_ft.pt`, ball AP 0.618 OOD from Day 5); Day-9 basketball player tracks; the pixel-space Kalman code from Day-12 (`scripts/analyze_ball.py`) to adapt

---

## Context (read first)

Football reached follow-cam (Day 13) via: ball tracking (Day 12) + player tracks (Day 9). Basketball has player tracks (Day 9, tuned) and a ball DETECTOR (Day 5, AP 0.618 OOD) but NO ball TRACKING. Follow-cam needs the ball trajectory for the "A" (ball-faithful) feed. So ball tracking is the prerequisite before basketball follow-cam — this session builds it.

**Reuse the Day-12 architecture** (pixel-space Kalman, project-on-use), with basketball-specific physics adjustments (below). Don't reinvent — adapt `analyze_ball.py`.

**Validation reality (honest):** football got free ball GT from SoccerNet-GSR (`bbox_image`) → real RMSE. Basketball has NO clean ungated ball-trajectory GT (Day-20 search: TrainingDataPro set is the rejected 72-frame commercial one; WASB is the best hope; rest are synthetic/method-refs). So validation branches:
- WASB basketball ball annotations accessible → real RMSE (full parity).
- Else → plausibility (ball in/near court, velocity sane, continuity) + visual.
Accept the rigor gap honestly: log "basketball ball = plausibility-validated" vs football's RMSE if GT unavailable. Do NOT fake precision.

**Scope: BASKETBALL, ball only.** Players done (Day 9). Follow-cam is the NEXT session once this lands.

---

## Basketball-specific physics (why this is harder than football's ball)
Football's ball mostly moves in straight lines on the ground → constant-velocity (CV) Kalman fit well. Basketball's ball:
- **Dribbles** — rapid vertical bounces. A CV model can't track the bounce cycle; treat brief dribble occlusions as short gaps the filter coasts through, don't try to model the bounce.
- **Shots** — high arcs (parabolic). Like football's aerials, these violate the ground-plane and the CV model. FLAG shot-arc/high-ball segments as lower-confidence (the basketball analogue of football's aerial flag); don't attempt parabolic modeling or 3D height (out of scope, research-level).
- **Held/occluded** — ball spends lots of time against bodies/in hands (Day-4/5 occlusion finding). More/longer gaps than football → the gap-bridging matters more, and the max-predict-gap before reset may need to be SHORTER (a held ball that reappears elsewhere shouldn't be linearly interpolated through).
Net: expect lower effective-recall lift and shorter trustworthy prediction horizons than football. That's the sport, not the method.

---

## PART 0 — Check WASB (or any) basketball ball-trajectory GT (GATES VALIDATION) (~20 min)
1. Check accessibility of WASB (Widely Applicable Strong Baseline, SBDT) basketball ball annotations — github/project page, is the basketball split downloadable without paywall/gate? Note license.
2. If WASB inaccessible, quickly check for any other ungated basketball ball-position GT (frame-level x,y). Cap at ~15 min.
3. Decide validation path: real-RMSE (if GT) vs plausibility (if not). Report which.

**STOP. Report: WASB accessible? any basketball ball GT found? → validation path (RMSE or plausibility).**

---

## PART A — Raw ball detections + gap characterization (~35 min)
1. Run `models/basketball_ft.pt` ball detections @1280 over the basketball eval clips (SportsMOT basketball seqs already on disk, and/or the Day-2 4K clip). Reuse Day-5/cache if available. Keep (frame, bbox, conf).
2. Ball position = bbox center (pixels). 
3. Gap analysis: consecutive-missing-frame run lengths. EXPECT longer/more frequent gaps than football (occlusion-heavy). Report distribution.

**STOP. Report: basketball ball detection rate? gap distribution vs football's?**

---

## PART B — Pixel-space Kalman, basketball-tuned (~55 min)
1. Adapt Day-12 Kalman: state [x,y,vx,vy], CV model, pixel space.
2. **Basketball tuning vs football:**
   - Velocity gate: re-calibrate the px/frame cap from basketball data (different court size/camera distance → different px/m; ball motion in pixels differs).
   - Max-predict-gap: likely SHORTER than football's 15 (a held/occluded ball reappearing shouldn't be coasted through a long gap into fiction). Tune from the gap distribution.
   - Process noise: may need higher (more erratic motion).
3. Predict every frame, update on detections, flag {detected|predicted|lost}.
4. Output: continuous pixel ball trajectory + flags.

**STOP. Report: Kalman running? effective-recall lift (raw → Kalman-provided → within-tolerance)? prediction horizon that stays sane?**

---

## PART C — Shot-arc / high-ball flag (~25 min)
1. Basketball analogue of football's aerial flag: flag segments where the ball is high / fast-vertical (shots, lobs) as lower-confidence — these are where a court-plane projection (if ever used for analytics) would err, and where the CV model is weakest.
2. Detection heuristic: high pixel position + vertical velocity sign change (up-then-down arc), or simply ball-y above a court-region threshold. Keep simple; flag, don't model.
3. Report fraction flagged; sanity-check it concentrates on shot moments.

---

## PART D — Validate (per Part-0 path) (~35 min)
**If WASB/GT available:** trajectory RMSE (pixels) detected vs predicted frames separately; effective recall before/after Kalman; sanity gate (GT-as-detection → RMSE ~0). Full football-parity validation.
**If plausibility only:** % trajectory within court bounds; pixel-velocity distribution (sane vs teleport); continuity; AND visual — render predicted-vs-detected ball overlay, eyeball whether predicted follows the real ball through gaps. Explicitly label this "plausibility-validated, no GT RMSE."

**STOP. Report validation per path. State the rigor level honestly.**

---

## PART E — Render, log, commit (~30 min)
1. Render sample seq with ball trajectory overlaid (detected/predicted/shot-flag color-coded).
2. notes.md `## Day 14`: WASB/GT availability + chosen validation path, detection rate + gap dist (vs football), Kalman basketball-tuning (gate, max-gap, noise) and WHY they differ from football, validation result + EXPLICIT rigor level ("plausibility-validated" if no GT — the honest football-parity caveat), effective-recall lift, shot-flag fraction, and:
   - Parity status: basketball now has ball tracking → follow-cam unblocked (next session).
   - Honest asymmetry: football ball RMSE-validated; basketball ball [RMSE/plausibility]-validated — a ground-truth-availability gap, not a method gap.
3. gitignore checks (datasets, weights, videos, NDA n/a here but SportsMOT terms); commit scripts + notes + sample:
   `git commit -m "Day 14: basketball ball tracking (pixel Kalman, basketball-tuned); [RMSE/plausibility]-validated; follow-cam parity unblocked"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. WASB/basketball ball GT accessible? → validation path
3. Ball detection rate + gap distribution vs football
4. Kalman basketball-tuning (gate, max-gap, noise) — how it differs from football & why
5. Validation: RMSE (if GT) or plausibility; effective-recall lift; STATED rigor level
6. Shot-arc flag fraction; does the rendered track follow the ball through gaps? (screenshot)
7. Parity check: is basketball ball tracking now at football's stage (modulo validation rigor)?
8. Errors hit (even if fixed)
9. Time taken

---

## Do NOT today
- Do NOT model dribble bounces or shot parabolas / 3D height — flag shots as lower-confidence, coast short gaps; advanced modeling is out of scope (research-level).
- Do NOT reuse football's velocity-gate / max-gap constants blindly — recalibrate for basketball (different court/camera/motion).
- Do NOT fake RMSE precision if no GT exists — plausibility-validate and SAY SO (honest parity caveat).
- Do NOT build follow-cam this session — that's next, once ball tracking lands.
- Do NOT do football or players.
- Do NOT trust validation until sanity gate (GT-as-detection → RMSE ~0) passes, IF GT available.
- Do NOT commit datasets/weights/videos.

---

## Appendix — Basketball ball-tracking prior work (grounding + considered alternatives)

Football's approach drew on VEO/Pixellot + autonomous-camera research. Basketball ball tracking has its own lineage — capture it for the report's considered-alternatives, and have Claude Code READ the actual methods during Part 0 (not just check the dataset) so the writeup is grounded.

**Methods to read in Part 0 (alongside the WASB dataset-accessibility check):**

1. **WASB (Widely Applicable Strong Baseline for Sports Ball Detection & Tracking).** Method = high-resolution feature extraction + position-aware training + inference with TEMPORAL CONSISTENCY across frames; validated across 5 sports incl. basketball, beats prior SBDT methods. CONFIRMS our detect-then-temporally-reason family is sound. Read its method to (a) sanity-check our Kalman is a reasonable temporal-consistency mechanism, (b) see if its dataset/basketball split is usable as GT.

2. **TrackNet — THE documented escalation path (chosen NOT to use today, by design).** Canonical small-fast-ball tracker (tennis/badminton/basketball). KEY DIFFERENCE from our pipeline: it folds temporal reasoning INTO the detector — trains on CONSECUTIVE frames (e.g. 3) and outputs a 2D Gaussian heatmap at the ball center, learning the MOTION PATTERN rather than detecting per-frame then smoothing. This can recover an occluded/blurred ball a single-frame detector misses — directly relevant to basketball's heavy occlusion.
   - **Why NOT today:** it's a new architecture to train + validate (bigger session, breaks method-parity with football's detect+Kalman). Staged discipline: reach parity + unblock follow-cam with the cheap reuse first.
   - **Escalation trigger:** if Day-14's detect+Kalman ball track is too jumpy/gappy through occlusion to feed a watchable follow-cam "A" feed (judged next session), TrackNet becomes the justified upgrade. Document this trigger explicitly in notes.

3. **Trajectory-based shooting-angle/velocity basketball systems** (the SBDT lineage) — adjacent to our shot-arc flag and future shot-event detection. Note as related work.

**Report framing:** "For basketball ball tracking I used detect-then-Kalman (reusing the football pipeline) to reach cross-sport parity, having surveyed the alternatives — WASB (temporal-consistency baseline, confirms the approach family) and TrackNet (heatmap-from-consecutive-frames, the purpose-built small-ball method). I documented TrackNet as the escalation path and defined the measured trigger (follow-cam adequacy) for adopting it." — this is graduate-level considered-alternatives reasoning.

**Part 0 addition:** while checking WASB accessibility, also have Claude Code read the WASB + TrackNet method abstracts and record a 2-3 sentence accurate summary of each in notes (so the considered-alternatives section is grounded in the papers, not this PRD's paraphrase).
