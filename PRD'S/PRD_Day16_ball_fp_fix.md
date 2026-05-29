# PRD — Day 16: Diagnose the Follow-Cam Wobble + Fix Ball-Track False Positives
**Project:** AI Sports Recording & Analytics System
**Goal:** Reconcile the Day-15 "notes say solved / eyes say wobbling" gap by diagnosing the A-feed wobble on-screen FIRST, then fix the confirmed cause (suspected: false-positive ball detections the velocity gate missed) at the ball-track level — the cheap, targeted fix before any TrackNet escalation. Basketball, SportsMOT.
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; Day-14 ball track (`outputs/ball_track_bb/`), Day-15 follow-cam (`scripts/follow_cam_basketball.py`, `analyze_ball_basketball.py`/`analyze_ball.py`), Day-9 player tracks

---

## Context (read first — important)

Day-15 notes declared the A-feed handoff "solved" and "TrackNet NOT needed," citing jerk reduction (39→2) and 95% held-ball holder-coverage. BUT the user WATCHED the rendered A and B feeds and saw them WOBBLING around — A follows the ball briefly, loses it, then LATCHES ONTO A FALSE-POSITIVE ball and swings across the frame. C looked fine.

The metric that exposed it (under-weighted in Day-15): **A-feed ball-in-safezone = 0.51 (c001)** — the camera is on the ball only ~half the time. Jerk measures SMOOTHNESS, not CORRECTNESS: a camera can smoothly glide to the WRONG place (low jerk, high confidence, still wrong). This is the recurring project trap — a metric moving the right way while the real thing is wrong. The user's eyes caught it; trust the eyes.

**Key insight on why the handoff didn't fix this:** the possession-handoff only fires on a TRULY-LOST ball. A false-positive ball is a DETECTION, not a loss — so the system thinks it has the ball and confidently follows the FP. The handoff architecturally cannot catch FP-latching. So the dominant visible failure (FP wobble) is a DIFFERENT failure mode than the held-ball dropout the handoff solved.

**This session: DIAGNOSE first (confirm the cause on-screen), then FIX the confirmed cause.** Do not assume — three different wobble causes are possible (below) and they need different fixes.

---

## The three possible wobble causes (must distinguish before fixing)
1. **FP latching** — ball-track jumps to a head/banner/round-object FP the velocity gate didn't reject → fix at ball-track FP rejection. (User's hypothesis, evidence-backed.)
2. **Limiter oscillation** — the crop-motion controller itself oscillates. Football Day-13 had EXACTLY this bug (accel>decel sawtooth) and fixed it via braking-distance cap. Confirm the basketball follow-cam actually inherited the FIXED limiter, not a regressed one.
3. **Handoff thrashing** — target rapidly flips between ball and last-holder → fix with handoff hysteresis.
The fix differs per cause. Part 0 identifies WHICH (likely #1, possibly compounded).

---

## PART 0 — Diagnose on-screen, reconcile the metric-vs-reality gap (~50 min)
1. Re-render the A-feed for c001 (held-ball-heavy) + c007 with a DEBUG OVERLAY showing, per frame: the raw ball detection(s) + conf, the Kalman state {detected|predicted|lost}, the chosen crop target source {ball|pred|holder|centroid}, AND an FP-SUSPECT flag on any ball detection that (a) is far from the predicted position, (b) has no nearby player, or (c) sits in a head/banner-prone region.
2. WATCH it. At each wobble, record what the overlay shows: is the camera chasing an FP detection (#1)? Is the target stable but the crop oscillating anyway (#2)? Is the target flipping ball↔holder (#3)?
3. Tie it to the metric: show WHERE in the sequence ball-in-safezone fails — confirm the 0.51 is FP-latching frames, not edge-clamp frames.

**STOP. Report: which wobble cause(s) confirmed on-screen? Is it FP-latching as hypothesized, or also limiter/handoff? Quantify: what fraction of wobble frames are FP-driven?**

---

## PART A — Fix the confirmed cause (~70 min)
**If FP-latching (expected):** tighten ball-track FP rejection — apply as many as needed, measure each:
- **Tighter velocity/teleport gate:** reject a re-detection that implies the ball jumped implausibly from the last confident position (the Day-14 gate exists but is clearly too loose — the FPs prove it). Re-calibrate from the FP jumps seen in Part 0.
- **Player-proximity prior:** a basketball ball is almost always near a player (held, dribbled, passed between players, or shot from a player). Reject/down-weight ball detections with NO player nearby — kills banner/crowd/scoreboard FPs. (Court-region prior from Day-14 was a coarse version; player-proximity is sharper.)
- **Trajectory-consistency / confidence-over-time:** require a detection to be consistent with recent motion before the crop commits to it; a one-frame jump to a head shouldn't yank the camera. (A short confirmation window before re-locking.)
- **Re-acquisition hysteresis:** after a loss, don't instantly snap to the first re-detection; require a couple of consistent frames. This stops the swing-to-FP-then-back.

**If limiter oscillation (#2):** confirm/port the FIXED braking-distance limiter from football Day-13.
**If handoff thrashing (#3):** add hysteresis so the target doesn't flip ball↔holder every frame.

Re-run the ball track + A-feed after each fix; keep what reduces FP-latching without breaking the genuine tracking the user LIKED (dribbles/passes/shots tracked well — don't regress that).

**STOP. Report: which fixes applied, and the effect on FP-latching frames + ball-in-safezone?**

---

## PART B — Re-render and RE-WATCH (the real eval) (~40 min)
1. Re-render A (fixed) + the debug overlay for both seqs.
2. WATCH. The bar is PERCEPTUAL: is the wobble gone? Does A now follow the ball on dribbles/passes/shots (the good behavior) WITHOUT swinging to FPs (the bad behavior)?
3. Confirm the good stuff didn't regress: the dribble/pass/shot tracking the user was impressed by must still work.

**STOP. Report: is the A-feed watchable now? wobble gone? did the liked behavior survive?**

---

## PART C — Fix the eval metric so it can't lie again (~25 min)
The Day-15 eval got fooled because jerk (smoothness) was treated as the headline. Fix it:
1. Make **ball-in-safezone (or "crop centered on the REAL ball")** the PRIMARY A-feed metric — smooth-but-wrong must score badly.
2. Keep jerk as a SECONDARY smoothness check only.
3. Add an **FP-latching rate** metric: fraction of frames the crop target is a rejected/suspect detection. This is the number that should have caught Day-15.
Report all three for A-feed, before-vs-after the fix.

---

## PART D — Log, the honest TrackNet re-decision, commit (~30 min)
1. notes.md `## Day 16`: the metric-vs-reality reconciliation (what jerk hid, what safezone showed), the confirmed wobble cause(s), the FP fixes applied + effect, the re-watch verdict, the corrected eval metrics, and:
   - **Honest correction of Day-15:** the handoff solved held-ball loss but NOT FP-latching (different failure); Day-15's "solved/TrackNet-not-needed" was premature for the A-feed.
   - **TrackNet re-decision:** if the cheap FP fix makes A watchable → TrackNet still not needed (now actually evidenced). If FP-latching persists despite track-level fixes → TrackNet justified (temporal-consistency detection may suppress FPs), with the specific failing cases documented as its spec.
   - Honest caveats unchanged (SportsMOT footage, plausibility-validated ball, school re-tune).
2. gitignore checks; commit:
   `git commit -m "Day 16: diagnose follow-cam wobble (FP-latching, not held-ball); ball-track FP-rejection fixes; corrected A-feed eval metric"`; No need to push just commit.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Confirmed wobble cause(s) on-screen — FP-latching as hypothesized, or also limiter/handoff?
3. What fraction of wobble was FP-driven?
4. Which FP-rejection fixes applied + effect (FP-latching rate, ball-in-safezone before/after)
5. RE-WATCH verdict: is A watchable now? wobble gone? did dribble/pass/shot tracking survive?
6. Corrected eval: ball-in-safezone + FP-latching rate (the metrics that should've caught Day-15)
7. TrackNet re-decision: needed or not — now with real evidence?
8. Errors hit (even if fixed)
9. Time taken

---

## Do NOT today
- Do NOT skip Part 0 / assume the cause — confirm the wobble is FP-latching on-screen before fixing (could be compounded by limiter/handoff; different fixes).
- Do NOT trust jerk/smoothness as success — a smooth camera pointed at the wrong place is a FAILURE. Ball-in-safezone + FP-latching rate are the truth metrics.
- Do NOT regress the GOOD behavior (dribble/pass/shot tracking the user liked) while killing FPs — check both.
- Do NOT jump to TrackNet — the cheap track-level FP fix is tested first; TrackNet only if it persists, with evidence.
- Do NOT re-declare "solved" on metrics alone — the re-WATCH is the verdict.
- Do NOT do football, C-feed (it's fine), or build highlights yet.
- Do NOT commit datasets/weights/videos.
