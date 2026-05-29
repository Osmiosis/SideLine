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
- **Team assignment (Day-22)**: torso-colour a/b-chroma clustering (court-position aided), per-
  tracklet majority vote. Unlocks **team-split heatmaps + possession** (now in the PDF; were deferred
  in Day-21). **Accuracy validation is PENDING** — a human labels a crop set with
  `scripts/label_crops.py`, then `scripts/bball_team_assign.py --validate-only` produces the
  hand-label team-accuracy number. The PDF currently says "validation pending" until that runs.
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
- `track_teams_bb.json` / `cluster_summary_bb.json` — per-track team roles + cluster colours.
- `homography.json` / `validation.json` — H + calibration method + plausibility metrics.
- `metrics_basketball.json` — all numbers (incl. possession) + plausibility sanity checks.

## Team assignment (Day-22)
Torso-colour clustering (a/b chroma, the deployment-robust choice — NOT a luminance shortcut, which
would overfit this broadcast and break on DPS kits), per-tracklet majority vote, with a **court-
position filter** (Day-21 homography excludes off-court bench/refs) and a colour-distance outlier for
refs. Blind clustering (never sees the labels). 2 clean clusters: cluster 0 = Kentucky blue, cluster
1 = Wichita white (`sample_torsos.png`). Possession = nearest on-court player to the ball, by team
(Day-12 football method). **Hand-label validation pending** (see above); random 2-team floor = 50%,
football Day-11 was GT-validated at 88–92%.

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
- **Validate team assignment**: label crops (`scripts/label_crops.py`) → `bball_team_assign.py
  --validate-only` → regenerate this PDF with the real team-accuracy number.
- Highlights (A-feed events, C-feed player reels) — both sports now fully analytics-equipped.
- Real **deployment calibration + per-match colour calibration** on DPS's own court/kits.

Regenerate (after labelling): `python scripts/bball_team_assign.py` then
`python scripts/coach_deliverable_basketball.py v_00HRwkvvjtQ_c007 --win 493 591`
