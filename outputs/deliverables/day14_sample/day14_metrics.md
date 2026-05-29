# Day 14 — Basketball Ball Tracking (pixel-space Kalman, basketball-tuned)

Football reached follow-cam (Day 13) on ball tracking (Day 12) + player tracks (Day 9).
Basketball had players + a ball *detector* (Day 5, OOD AP 0.618) but no ball *tracking*.
This builds it — the **same pixel-space constant-velocity Kalman as football (Day 12)**,
basketball-tuned — so basketball follow-cam is unblocked next. SportsMOT basketball, 5 seqs
(`v_00HRwkvvjtQ_c001/c003/c005/c007/c008`, 1280×720 @25fps).

## Detection + gaps (vs football)
| seq | det-rate | gaps mean/p90/max | detected consec-jump p90/p99 (px) | shot-flag % |
|---|---:|---|---:|---:|
| c001 | 0.72 | 2.9 / 7 / 20 | 684 / 1077 | 20.2 |
| c003 | 0.71 | 2.9 / 6 / 18 | 522 / 1069 | 8.3 |
| c005 | 0.70 | 2.2 / 4 / 14 | 372 / 803 | 16.4 |
| c007 | 0.69 | 3.4 / 8 / 19 | 553 / 1148 | 21.6 |
| c008 | 0.75 | 2.4 / 5 / 18 | 570 / 982 | 2.9 |

Raw det-rate is *higher* than football's 51% (strong Day-5 detector), but **consec-jumps are
huge (p90 ~370–680px on a 1280-wide frame) = heavy false positives**. Gaps are short (p90 ≤ 8).

## Coverage lift (effective recall — NO within-tol, no GT)
Gate-accepted raw **0.45** → Kalman-provided **0.90 (+44.8 pp)**; in-frame 0.98–0.99; longest
predict streak = 8 (= max-gap → no runaway coasting). The gate-accepted "real detection" rate
(~0.45) ≈ football's 0.52 raw; the +44pp is real but a larger share is short-gap extrapolation.

## Basketball tuning (and why it differs from football)
| param | football | basketball | why |
|---|---|---|---|
| velocity gate | 150 px/fr | **100** | smaller frame (1280 vs 1920), recalibrated |
| max-predict-gap | 15 | **8** | occlusion-heavy; short gaps; don't coast a held ball into fiction |
| court-region prior | — | **drop y < 0.10·H** | reject static banner/scoreboard false positives |

## The basketball-specific failure we fixed: banner false-positives
The broadcast banner/scoreboard text ("BASKETBALL", logos) is detected as the ball with
**confidence as high as the real ball** (top-band conf 0.38 vs court 0.39) — so a conf floor
can't remove it — and it's **static**, so the velocity gate can't either. First run, the Kalman
locked onto it: **33% of frames in the top 12%** of the image. Fix = a **court-region prior**
(drop detections above the court, y < 0.10·H): removed ~16% of c001's detections (the banner
FPs), near-no-op elsewhere; top-band locking + the bogus shot-flag collapsed. Football never hits
this — its pitch fills the frame; basketball's scoreboard sits above the court.

## Validation rigor: PLAUSIBILITY-ONLY (stated honestly)
No ungated per-frame basketball ball GT exists for these clips (SportsMOT annotates players only;
WASB's basketball GT is MIT-licensed + public **but** its source frames are 404 upstream and are
for *different* videos; DeepSportradar is gated/3D-oracle; UniqueData is loose screenshots). So we
do **not** fake RMSE. Evidence is coverage lift + in-frame % + sane pixel-velocity + continuity +
**visual** (sample overlays: on-court coherent trails through gaps — see PNGs). 

**Honest asymmetry vs football:** football ball = **RMSE-validated** (SoccerNet-GSR `bbox_image`);
basketball ball = **plausibility-validated** — a ground-truth-availability gap, not a method gap.

## Considered alternatives (surveyed, grounded)
- **WASB** (BMVC 2023, MIT) — HRNet high-res ball-heatmap + position-aware training + temporal-
  consistency linking; validated on 5 sports incl. basketball. Confirms our detect-then-Kalman
  (temporal-reasoning) family is sound.
- **TrackNet** (arXiv 1907.03698) — CNN+DeconvNet on N consecutive frames → Gaussian heatmap at
  the ball center; folds temporal reasoning *into* the detector, recovering occluded/blurred
  balls. THE escalation path. **Trigger:** adopt it if Day-14's detect+Kalman track proves too
  jumpy/gappy to feed a watchable follow-cam "A" feed (judged next session).

## Shot/high-ball flag (coarse, honest)
`|vy| > 15 px/frame` (fast-vertical / shot-lob) OR `y < 0.15·H` (upper-court), 3–22% per seq.
Caveat: with one broadcast camera and no court projection, image-y conflates "far court" with
"airborne" — so this is a coarse "lower-confidence" marker, not precise shot detection. Flag, don't
model (c007 sample shows it correctly lighting up a shot arc rising to the rim).

## Parity
**Basketball now has ball tracking → follow-cam unblocked (next session).** Output
`outputs/ball_track_bb/<seq>/trajectory.json` is the basketball analogue of Day-12's football track.

Sample frames (overlay: green=detected, blue=predicted/gap-fill, yellow=shot/high-ball):
`c001` (fixed banner→smooth on-court pass curve), `c007` (shot arc to the rim), `c008` (clean on-court).
