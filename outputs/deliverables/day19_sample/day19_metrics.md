# Day 19 — Lightweight Ball-vs-Head Appearance FP Rejection (broke the TrackNet tunnel-vision)

## The reframe
Four sessions (15 wobble, 16 corner-FP, 17 head-FP) assumed the fix was either spatial-geometry
(failed: Day-17 proved heads aren't size/geometry-separable, area ~1.0×) or full temporal-learning
(TrackNet — Day-18 found it data-gated). The skipped MIDDLE ground is APPEARANCE: a head and a ball
look different even at identical size/shape, and learning that needs SINGLE labeled crops — no
consecutive-frame data. This sidesteps the entire TrackNet data wall.

## Part A/A.5 — labeling
Cropped every ball-candidate detection from `det_cache/bb_ball` over 5 clips (3,348 crops). First
attempt at geometric pseudo-labels was CONTAMINATED — the user eyeballed the contact sheets and caught
balls+heads mixed in BOTH classes (geometry is exactly the signal that can't separate them; it leaks).
So the user HAND-SORTED via an interactive keypress tool (`sort_crops.py`): **3,329 clean labels —
1,045 ball / 2,284 not-ball** (heads + junk + body). `hand_ball.png` / `hand_notball.png` show the
clean classes — the appearance separation (orange round-on-wood vs skin/hair-on-jersey) is obvious.

## Part B/C — two methods (frozen ImageNet ResNet18 embedding; 75/25 random split of hand labels)
| method | ball-recall | ball FALSE-REJECT (must-not-break) | head-reject | junk-reject |
|--------|------------:|-----------------------------------:|------------:|------------:|
| **M1 classifier** (logistic on embedding) @thr0.50 | 87.5% | 12.5% | **98.5%** | 100% |
| M1 @thr0.32 (tuned ball-FR≤5%) | 93.8% | 6.2% | 79.6% | 99.2% |
| M2 embedding-distance (bootstrap anchor, ~no labels) | 45.5% | **54.5%** ✗ | 87.6% | 100% |

**M1 wins decisively** — M2's bootstrapped ball-anchor + single cosine threshold rejects over half the
real balls (a single mean-embedding anchor doesn't capture ball-appearance variety). M1 shows the
classic precision/recall tension: kill heads (thr0.50, 98.5% head-reject) costs 12.5% ball false-reject;
keep balls (thr0.32) leaks ~20% of heads.

## Part D — integration + RE-WATCH (the verdict)
Winner integrated as a pre-Kalman veto (`ball_appearance_filter.py`): detector proposes → ResNet18+
logistic classifies each crop → non-ball (head/junk) dropped → survivors feed the existing Kalman.
Canonical config: `--require-player --reject-head --appearance-filter filter.npz --appear-thr 0.5`
(proximity kills banners + init gating; geometric reject-head kills in-zone heads; **appearance kills
the out-of-zone heads the geometry missed** — the Day-17 residual).

A-feed effect (c001 / c007), Day-17 → Day-19:
| metric | c001 | c007 |
|--------|------|------|
| ball-in-safezone | 0.70 → **0.95** | 0.89 → **0.98** |
| A-feed FP-latch | (heads leaked) → **0.0%** | → 0.1% |
| detection coverage | 0.68 → 0.51 | 0.76 → 0.60 |

In the track, dropped balls become 1-frame Kalman predictions (recoverable) and the possession-handoff
covers longer gaps — so the lower coverage shifts the risk from "wobble to heads" to "coast on the
play," which the **RE-WATCH confirmed is fine**: the user watched the rendered A-feed and reported the
camera oscillated only ONCE, mildly — heads no longer grab it, shots/dribbles/passes still tracked
(`after_c001_f40_head_rejected.png`: the old head-latch frame now predicts onto the play;
`after_c007_f49_shot_survives.png`: shot still detected/framed).

## THE DECISION: WORKS — basketball ball track FINALLY done; TrackNet NOT needed
The lightweight appearance classifier (single hand-labeled crops, frozen pretrained backbone, a logistic
head, ~minutes to train on a 4060) solved the head-FP that four prior sessions couldn't — WITHOUT the
gated consecutive-frame data TrackNet needs. Both sports now at follow-cam parity → highlights/deliverables
next. TrackNet remains the documented fallback but is no longer needed.

## Caveats
SportsMOT footage; plausibility-validated track. Coverage is lower (more predicted frames) — acceptable
on the re-watch but a tighter (school) camera may want a higher threshold to recover detections. The
classifier is trained on these 5 clips' appearance — re-label/re-train for very different courts/lighting.
Labels are hand-sorted (clean) but the held-out split is random (mild near-duplicate optimism); the
re-watch is the real verdict, not the held-out numbers.
