# Day 16 — Diagnose Follow-Cam Wobble + Fix Ball-Track False Positives

## The metric-vs-reality gap (why Day-15 lied)
Day-15 declared the A-feed "solved / TrackNet not needed" on **jerk** (39→2, smoothness). But the
user WATCHED it wobble — A briefly tracks the ball, loses it, then **latches onto a false-positive
ball** (scoreboard/banner text in a frame corner) and glides smoothly to the wrong place. Jerk
measures SMOOTHNESS, not CORRECTNESS: a camera can smoothly point at the wrong thing.

## Part 0 — confirmed cause: FP-LATCHING (#1), not limiter (#2) or handoff (#3)
- **#2 ruled out:** basketball follow_cam imports the FIXED braking-distance limiter verbatim; jerk
  1.99, only 37 lag frames — no oscillation.
- **#3 ruled out:** Day-15 handoff source was coherent blocks; the safezone misses are at `detected`
  (FP) frames, not holder frames.
- **#1 confirmed, quantified** (physical FP signature = picked ball far from EVERY player box):

| seq  | FP-suspect of 'detected' | no-player FP | player-dist p90 / max | of A-feed safezone MISSES, FP-driven |
|------|-------------------------:|-------------:|----------------------:|-------------------------------------:|
| c001 | 44.3% (198/447)          | 196          | 377 / 479 px          | **69.2%**                            |
| c007 | 22.6% (76/337)           | 72           | 411 / 522 px          | **77.8%**                            |

So the c001 ball-in-safezone=0.51 was NOT edge-clamp (only 31 frames) — it was 153 frames of the
camera pulled toward FPs. See `before_c001_f275_FPlatch_scoreboard.png` (latched top-right on the
"19:49" scoreboard) and `before_c001_f1130_FPlatch_banner.png` (latched on the bottom score banner).

**Root cause (in `analyze_ball_basketball.run_kalman_bb`):** after a held-ball occlusion
(>`max_gap`=8 misses) the Kalman RESET re-initialized from the **highest-confidence detection
anywhere in the frame** — no velocity gate, no player check. It grabbed a corner FP, then tracked
that static FP within the 100px gate for a whole run (196 no-player frames ≫ 9 reset-teleports).
And because an FP is `status='detected'`, NOT `'lost'`, the Day-15 possession-handoff (fires only on
`lost`) architecturally **could not** catch it.

## Part A — fix (player-proximity prior at the ball-track level)
A basketball ball is almost always on/near a player. Added (gated behind `--require-player`):
1. **(Re)init proximity** (`reinit_prox=150px`): (re)initialization must land on a detection near a
   player box — closes the FP doorway. A real ball re-emerges held/received AT a player.
2. **In-gate proximity** (`ingate_prox=300px`, generous): rejects FPs that sit within the velocity
   gate of a drifting prediction; wide enough that shot apexes / long passes (continuous off a
   player) survive.
3. **Re-acquisition hysteresis** (`reacq=2`): require 2 consecutive in-gate hits after a gap before
   re-locking, so a one-frame FP can't yank the camera.

## Part B/C — effect (PRIMARY metrics: A-feed FP-latch rate + ball-in-safezone)

| seq  | A FP-latch before → after | A ball-in-safezone before → after | handoff frames before → after |
|------|--------------------------:|----------------------------------:|------------------------------:|
| c001 | 16.9% → **0.4%**          | 0.506 → **0.749**                 | 142 → 289                     |
| c007 | 10.2% → **0.0%**          | 0.760 → **0.879**                 | 63 → 110                      |

Safezone-miss composition flipped from 69–78% FP-driven to 12–23% FP-driven (rest = legitimate
edge-clamp/lag). Coverage lift preserved (+43.6/+46.1pp), in-frame ≈1.00, jerk still ~1.2 (smooth).
Handoff coverage ROSE because FP frames are now correctly `lost` → the handoff finally fires as
intended (follow the holder through occlusion). `after_c001_f1130_fixed_handoff.png` shows exactly
this (crop source = holder, on the play, not the banner). **Liked behavior survived:** shots still
tracked — `after_c007_f49_shot_tracked.png`.

## TrackNet re-decision: STILL NOT NEEDED — now actually evidenced
Day-15's "not needed" was premature (judged on jerk). The cheap track-level FP fix makes the A-feed
follow the real ball (FP-latch ~0%, safezone 0.75–0.88) WITHOUT TrackNet. The escalation trigger is
not met. Revisit only if a future sequence shows FP-latching that survives the proximity prior, or
systematic pass-during-occlusion loss.

## Honest correction of Day-15
The possession-handoff solved **held-ball LOSS** but not **FP-LATCHING** — a different failure mode
(detection, not loss). Day-15's "solved / TrackNet not needed" was correct about held-ball loss and
premature about the A-feed overall. The eye caught what jerk hid; the corrected PRIMARY metric
(A-feed FP-latch rate) now catches it automatically.

## Eval-metric correction (so it can't lie again)
- PRIMARY: **ball-in-safezone** (crop centered on the REAL ball) + **A-feed FP-latch rate** (fraction
  of frames the crop is centered on a no-player FP ball). Smooth-but-wrong now scores badly.
- SECONDARY: jerk/accel (smoothness only).

## Caveats (unchanged)
SportsMOT footage; ball track plausibility-validated (no per-frame ungated GT); crop/pan + proximity
thresholds camera-distance dependent (school re-tune). Proximity prior depends on player-track
quality (a missed player near the ball could drop a real detection → coasted as predicted, smooth).
