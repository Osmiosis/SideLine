# Coach Package — Basketball (team-agnostic, plausibility-level)

> ⚠ **PROVISIONAL — calibration not yet trusted.** The court homography in this package came from
> the **automatic** camera-pose registration, whose projected-court overlay turned out **visually
> VERY WRONG** (it passed the players-in-bounds metric while being misaligned — see `overlay.png`,
> kept here as evidence of *why* auto is unreliable). So **every court-metre number below is NOT
> trustworthy yet.** Calibration is now a **manual, human-marked** step:
>
> 1. `python scripts/mark_court.py v_00HRwkvvjtQ_c007 --frame 540` — click the court points, watch the
>    yellow overlay snap onto the real lines, save.
> 2. `python scripts/coach_deliverable_basketball.py v_00HRwkvvjtQ_c007 --win 493 591` — regenerate
>    the PDF/video/metrics from the trusted manual homography.
>
> The method, pipeline, and honesty structure are correct; only the calibration source needs the
> human-in-the-loop step (which is also the real deployment workflow: fixed camera, mark once).


Sample: **v_00HRwkvvjtQ_c007** (SportsMOT, NCAA tournament broadcast), stable-camera window
**f493–591 (~4 s)**. This is the first basketball coach deliverable — built on a new court
homography (Day-21), at **parity of METHOD with football but ONE COMPONENT BEHIND** (no basketball
team assignment yet → team-agnostic).

## Trust level — read this
- The court homography is **PLAUSIBILITY-validated, NOT ground-truth-validated**. Basketball has no
  court-metre GT (SportsMOT = pixel boxes only; Day-18 confirmed that's a dead-end hunt). Compare
  football's Day-10 homography, GT-validated to 0.2 m. Same honesty level as the Day-19 basketball
  ball track. The PDF's "validated" band is deliberately thin and labelled plausibility-level.
- **Team-agnostic**: no basketball team assignment exists yet (football got it in Day-11). So:
  all-players heatmap, total distance, court territory, intensity, average positions — but **no
  team-split heatmaps and no possession** (deferred to a future team-assignment session).
- **~4 s method demo**: SportsMOT broadcast pans constantly, so a single homography only holds for a
  short stable window. A fixed deployment camera (mark once, holds the match) removes this limit —
  the broadcast is the *harder* stress test.

## Contents
- `coach_analysis_basketball.pdf` / `_preview.png` — the coach one-pager.
- `tactical_sample_basketball.mp4` — ~4 s wide tactical view: team-agnostic player boxes + feet
  markers + IDs, highlighted ball (yellow; "pred" when predicted). 960×540 for repo size.
- `tactical_contact_sheet.png` — 6 stills from the tactical view.
- `overlay.png` — the court model projected back onto the calibration frame (the alignment eye-test).
- `court_diagram.png` — players projected to court-metres (calibration sanity: 100% in-bounds).
- `fig_*.png` — PDF panels (heatmap, average positions, territory, intensity).
- `homography.json` / `validation.json` — H + calibration method + plausibility metrics.
- `metrics_basketball.json` — all numbers + plausibility sanity checks.

## How the court was calibrated (Day-21 method)
- **Auto-detect** (tried first): blackhat+Hough finds court-line candidates + a blue centre-logo
  blob, but **cannot reliably LABEL** which line is which on broadcast footage (logos, painted
  text, crowd, players occluding the lane) — so it defers to manual. (Expected; the reason the
  manual fallback exists.)
- **Auto-register** (used here): camera-pose chamfer matching — optimise a real camera (focal +
  look-at extrinsics) projecting the 3D court plane to align projected court lines with detected
  court edges, with a *players-stay-in-bounds* prior that rules out the degenerate low-cost-but-
  wrong fits a free homography falls into. Result: 100% players in-bounds, ~12 px line-alignment
  residual.
- **Manual fallback** (deployment path, `basketball_court.py --mark`): click ≥4 known court points
  on one frame (corners are most robust — present on nearly any court, even faded/multi-sport).
  Fixed camera ⇒ mark once. This is the real, easier deployment route.

## Intensity speed bands
Basketball lacks football's single standardised GPS band set. Adapted from basketball time-motion
analysis (McInnes et al. 1995, *J Sports Sci*; Stojanović et al. 2018, *Sports Med*) — high-speed
efforts are short bursts on a small court, so thresholds are lower than football's. Bands (m/s):
stand/walk <1.4, jog 1.4–3, run 3–4.5, high-intensity 4.5–6, sprint >6. Per-step >9 m/s (above
basketball peak ~8.5) is treated as an ID-switch teleport artefact (Day-20 guard, basketball-tuned).

## What's next
- Basketball **team assignment** → unlocks team-split heatmaps + possession (football parity).
- Football + basketball highlights (A/C follow-cam feeds).
- Real **deployment calibration** on the school's own court footage (manual marking, fixed camera).

Regenerate: `python scripts/basketball_court.py v_00HRwkvvjtQ_c007 --frame 540 --register` then
`python scripts/coach_deliverable_basketball.py v_00HRwkvvjtQ_c007 --win 493 591`
