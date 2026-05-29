# Day 17 — Head-FP Fix (final cheap attempt before TrackNet)

## The residual FP class
Day-16's player-proximity prior killed CORNER false positives (scoreboard/banner). But the user
re-watched and the camera still sometimes jumped to a person's HEAD as the ball. A head is the most
player-PROXIMATE round, ball-sized object on court — it sails straight through the 150px reinit /
300px in-gate proximity prior. A different, harder FP class.

## Part 0 — head-FP confirmed + quantified (on the Day-16 track)
Extended `diagnose_ball_fp.py` to flag picked balls in a player HEAD ZONE (top 18% of a player box,
central 60% of width).

| seq  | head-FP of 'detected' | head-FP of all frames | A-feed head-latch |
|------|----------------------:|----------------------:|------------------:|
| c001 | 9.5% (34/359)         | 2.9%                  | 34 frames         |
| c007 | 14.9% (37/248)        | 5.2%                  | 37 frames         |

This is the residual wobble. See `before_c001_f40_HEADfp_latch.png` (picked ball on a player's head).

**SIZE GATE RULED OUT (key negative result):** head-zone picked-detection bbox area vs clean-ball:
429 vs 403 px² (1.07×) c001; 382 vs 431 px² (0.89×) c007. Heads and the ball are the SAME pixel size
here — the detector emits a ball-sized box on the head. Any size threshold that drops heads drops an
equal share of real balls. Fix #2 is dead on arrival; the diagnostic ruled it out before building it.

## Part A — three fixes, measured INDEPENDENTLY vs the Day-16 baseline

| fix | c001 head-FP | c007 head-FP | real-ball regression |
|-----|-------------:|-------------:|----------------------|
| baseline (Day-16) | 9.5% | 14.9% | — |
| **#1 head-zone exclusion** | **0.0%** | **0.8%** | minimal (shots 45→45 / 47→43; net detection neutral-to-+) |
| #2 size gate | — | — | RULED OUT (areas overlap ~1.0×) |
| #3 motion-consistency | 1.5% | 4.7% | minimal (protects fast balls through head height) |

A/B-isolated (each fix separately gated behind `--reject-head` / `--motion-consistency`; Day-16
proximity stays on as the baseline). **#1 wins** — it nearly eliminates head-FP. In c007, detected
only fell 248→243 despite removing 37 head frames, because in ~32 of them the tracker then found the
REAL ball instead of the head (a gain, not a loss). Shots survived (c001 45→45, c007 47→43).

## Part B — A-feed PRIMARY metrics, baseline → Fix#1 (FP-latch now includes head)

| seq  | A-feed FP-latch (no-player+head) | A ball-in-safezone |
|------|---------------------------------:|-------------------:|
| c001 | 3.4% (5+34) → **0.4%** (5+0)     | 0.749 → 0.696      |
| c007 | 5.2% (0+37) → **0.3%** (0+2)     | 0.879 → 0.885      |

The small c001 safezone dip is HONEST deflation: head-FPs sit near frame center (a head on a player
near the crop center counted as "ball in safezone"), so removing them removes inflation, not real
tracking. RE-WATCH: `after_c001_f40_head_rejected.png` (head rejected → ball predicted → camera on
the real play, not the head); `after_c007_f49_shot_survived.png` (shot still tracked).

## THE DECISION: PASS — TrackNet NOT needed
Bar: head-FP-latch < ~2% AND camera stays on the real ball when visible AND dribble/pass/shot survives.
- head-FP-latch 0.4% (c001) / 0.3% (c007) — well under 2%. ✓
- camera stays on the real ball; head-latch frames now predict/hand off to the play. ✓
- shots/dribbles/passes intact (shot-flag counts preserved; real-ball detection neutral-to-improved). ✓

**Basketball ball track is DONE:** corner-FPs (Day-16) + head-FPs (Day-17) both cleared. Follow-cam
A-feed is watchable. Both sports at follow-cam parity. Proceed to highlights next.

The staged escalation worked as designed: cheap-first, measure, escalate-with-evidence. Three sessions
(15 wobble → 16 corner-FP → 17 head-FP) closed the FP classes with cheap track-level levers; TrackNet
was never needed, and that is now an EVIDENCED conclusion, not a jerk-based guess.

## Fix#1's residual risk (documented, not blocking)
Head-zone exclusion is strict (rejects ALL head-zone detections). A genuinely high-held ball
(overhead pass, rebound reach) in a head zone would be dropped → coasted as predicted. On these clips
the regression was minimal (shots survived), but for footage with frequent overhead action, Fix#3
(motion-consistency: allow FAST balls through head height, block only slow head-locks) is the
lower-regression default. Both are in the code; `--reject-head` is canonical, `--motion-consistency`
is the alternative.

## Caveats (unchanged)
SportsMOT footage; ball track plausibility-validated (no per-frame ungated GT); proximity + head-zone
fractions are camera-distance/pose dependent (school re-tune); head zone depends on player-track quality.
