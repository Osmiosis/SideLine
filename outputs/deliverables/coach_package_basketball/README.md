# Coach Package — Basketball (team-agnostic, plausibility-level)

> **Calibration: MANUAL (human-marked) — trusted.** A human marked the court points with
> `scripts/mark_court.py`; the tool auto-pruned 8 stray clicks (3 free-throw misclicks + 4 left-half
> landmarks not visible in this right-half frame + 1), leaving 8 well-spread points. Held-out
> landmark reconstruction = **0.20 m mean / 0.30 m leave-one-out** — sub-metre, on par with
> football's 0.2 m. See `overlay.png` (yellow court sits on the real lines). The earlier *automatic*
> registration was discarded — its overlay was visually wrong despite passing the in-bounds metric;
> manual marking is the required path (and the real deployment workflow: fixed camera, mark once).


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
- Basketball **team assignment** → unlocks team-split heatmaps + possession (football parity).
- Football + basketball highlights (A/C follow-cam feeds).
- Real **deployment calibration** on the school's own court footage (manual marking, fixed camera).

Regenerate: `python scripts/basketball_court.py v_00HRwkvvjtQ_c007 --frame 540 --register` then
`python scripts/coach_deliverable_basketball.py v_00HRwkvvjtQ_c007 --win 493 591`
