# Coach Package — Basketball (team-aware, plausibility-level)

> **Calibration: MANUAL (human-marked) — trusted.** A human marked the court points with
> `scripts/mark_court.py`; the tool auto-pruned 8 stray clicks (3 free-throw misclicks + 4 left-half
> landmarks not visible in this right-half frame + 1), leaving 8 well-spread points. Held-out
> landmark reconstruction = **0.20 m mean / 0.30 m leave-one-out** — sub-metre, on par with
> football's 0.2 m. See `overlay.png` (yellow court sits on the real lines). The earlier *automatic*
> registration was discarded — its overlay was visually wrong despite passing the in-bounds metric;
> manual marking is the required path (and the real deployment workflow: fixed camera, mark once).


Sample: **v_00HRwkvvjtQ_c007** (SportsMOT, NCAA tournament broadcast), stable-camera window
**f493–591 (~4 s)**. Built on the Day-21 court homography + the Day-22 **team assignment** —
basketball is now at **full analytics parity of METHOD with football** (team-split heatmaps +
possession added). Team A = Kentucky blue jerseys, Team B = Wichita white.

## Trust level — read this
- The court homography is **PLAUSIBILITY-validated, NOT ground-truth-validated**. Basketball has no
  court-metre GT (SportsMOT = pixel boxes only; Day-18 confirmed that's a dead-end hunt). Compare
  football's Day-10 homography, GT-validated to 0.2 m. Same honesty level as the Day-19 basketball
  ball track. The PDF's "validated" band is deliberately thin and labelled plausibility-level.
- **Team assignment (Day-23, frozen embeddings)**: a frozen ImageNet **ResNet18** torso embedding
  (512-d, PCA-50) clustered into 2 teams (the deployment-transferable method — nothing fit to NCAA),
  per-tracklet majority vote + court-position filter. This **replaced** Day-22's mean-colour
  clustering, which had a structural white-attractor failure. **Hand-label validated on the SAME 717
  crops: 94.6% team accuracy** (random floor 50%; football Day-11 was 88-92% GT). Before/after:

  | metric | Day-22 colour | Day-23 embedding |
  |---|---|---|
  | overall | 79.6% | **94.6%** |
  | Team A (white) | 98.3% | 93.7% |
  | Team B (blue) | 65.2% | **95.3%** |
  | ref/bench exclusion | 16% | **48%** |

  The white-attractor is dissolved: blue 65→95%, refs 16→48%. Team A = white (Wichita), B = blue
  (Kentucky). See `validation_emb.json` (full numbers) vs `validation_bb.json` (the colour baseline).
- **~4 s method demo**: SportsMOT broadcast pans constantly, so a single homography only holds for a
  short stable window. A fixed deployment camera (mark once, holds the match) removes this limit —
  the broadcast is the *harder* stress test.

## Contents
- `coach_analysis_basketball.pdf` / `_preview.png` — the coach one-pager (now with team-split
  heatmaps + possession).
- `tactical_sample_basketball.mp4` — ~4 s wide tactical view: **team-coloured** player boxes (A blue
  / B red) + feet markers + IDs, highlighted ball (yellow; "pred" when predicted). 960×540.
- `tactical_contact_sheet.png` — 6 stills from the tactical view.
- `fig_team_heatmaps.png` — team-split positional density (the Day-22 panel).
- `overlay.png` — the court model projected back onto the calibration frame (the alignment eye-test).
- `court_diagram.png` — players projected to court-metres (calibration sanity: 100% in-bounds).
- `fig_*.png` — PDF panels (heatmap, average positions, territory, intensity, team heatmaps).
- `sample_torsos.png` — the 2 team clusters' torso swatches (spot-check: blue vs white).
- `track_teams_emb.json` / `validation_emb.json` — the CURRENT (Day-23 embedding) per-track team
  roles + validation (94.6% team accuracy, before/after table, torso vs full-body).
- `track_teams_bb.json` / `validation_bb.json` / `cluster_summary_bb.json` — the Day-22 colour
  baseline, kept for the before/after comparison.
- `homography.json` / `validation.json` — H + calibration method + plausibility metrics.
- `metrics_basketball.json` — all numbers (incl. possession) + plausibility sanity checks.

## Team assignment (Day-23 embeddings; Day-22 colour is the baseline)
Frozen ImageNet ResNet18 torso embeddings (512-d → PCA-50) clustered k=2, per-tracklet majority vote,
court-position filter (Day-21 homography) + embedding-distance outlier for refs. Blind clustering
(never sees the labels), Hungarian permutation-aligned at validation. Torso beat full-body overall
(94.6% vs 89.7%; full-body had better ref-exclusion 64% but worse Team A 80%). The frozen encoder has
nothing fit to NCAA → transfers to DPS kits unchanged (the DPS-right property; same pattern that fixed
Day-19 ball-vs-head). NOT a ReID model (ReID maximises inter-individual distinctness — wrong for
team-grouping; it's the later per-player-highlights tool).

**Possession caveat:** = nearest on-court player to the ball, by team (Day-12 method). It shifted hard
from Day-22 (white A 81→3%, blue B 19→97%) — because Day-22 mis-labeled the blue defenders crowding
the ball as white (the attractor), and the fix re-labels them blue. This is the fix showing its
effect, but it also exposes that nearest-player conflates the ball-handler with nearby defenders, so
the possession split is plausibility-level, not a true on-ball-possession metric.

## How the court was calibrated (Day-21 method)
- **Manual marking (USED here — `scripts/mark_court.py`):** a human clicks known court points on one
  frame; the app draws the projected court back LIVE so you re-mark until the yellow lines sit on the
  real lines, then auto-prunes stray clicks (court-space recon error > 2 m) and saves. Here: 8 clean
  points, 0.20 m mean / 0.30 m leave-one-out reconstruction. Corners are the most robust landmarks
  (present on nearly any court — faded/multi-sport/outdoor). Fixed deployment camera ⇒ mark once.
- **Auto-detect (`--auto`, retired):** blackhat+Hough finds court-line candidates but **can't
  reliably LABEL** which line is which on broadcast (logos/text/crowd/occlusion) → defers to manual.
- **Auto-register (`--register`, retired):** camera-pose chamfer matching. Discarded — its overlay
  was **visually wrong** while still passing the players-in-bounds metric (an in-bounds score is
  satisfiable by a misaligned pose). Kept in code only to document the dead-end.

## Intensity speed bands
Basketball lacks football's single standardised GPS band set. Adapted from basketball time-motion
analysis (McInnes et al. 1995, *J Sports Sci*; Stojanović et al. 2018, *Sports Med*) — high-speed
efforts are short bursts on a small court, so thresholds are lower than football's. Bands (m/s):
stand/walk <1.4, jog 1.4–3, run 3–4.5, high-intensity 4.5–6, sprint >6. Per-step >9 m/s (above
basketball peak ~8.5) is treated as an ID-switch teleport artefact (Day-20 guard, basketball-tuned).

## What's next
- Lift blue-team accuracy / ref exclusion: per-match colour calibration + ReID (Day-9 arm) for
  shadowed/similar kits; extend the court-position filter beyond the c007 window.
- Highlights (A-feed events, C-feed player reels) — both sports now fully analytics-equipped.
- Real **deployment calibration + per-match colour calibration** on DPS's own court/kits.

Regenerate: `python scripts/bball_team_assign.py` then
`python scripts/coach_deliverable_basketball.py v_00HRwkvvjtQ_c007 --win 493 591`
