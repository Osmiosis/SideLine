# Coach Package — Football (first stakeholder-facing deliverable)

Sample clip: **SNGS-118** (SoccerNet, "shots off target", 30 s). The cleanest fit to ground
truth in Day-10 (median position error 0.14 m; team distance +8% vs GT).

This is the first assembled coach artifact — glance-and-share, NOT a dashboard.

## Contents
- `coach_analysis.pdf` — the one-glance coach analytics one-pager (open this).
- `coach_analysis_preview.png` — PNG render of the PDF for quick viewing.
- `tactical_sample.mp4` — 10 s wide tactical "analyst-view" clip: team-coloured player
  boxes + feet markers, highlighted ball (yellow; "pred" when predicted), possession lower-third.
  (Downscaled to 960×540 for repo size; the full-res 30 s clip is generated locally and gitignored.)
- `tactical_contact_sheet.png` — 6 stills from the tactical view.
- `fig_*.png` — the individual PDF panels.
- `metrics.json` — all numbers + plausibility sanity checks.

## Metric tiers (kept visibly distinct in the PDF — honesty)
- **VALIDATED** (trust-gated vs ground truth in prior sessions): team-split positional
  heatmaps, team distance covered, possession % (possession is plausibility-validated, marked so).
- **DERIVED ANALYTICS** (geometric summaries of the validated pitch positions — inherit that
  trust but are NOT separately GT-checked): formation map, territory / field tilt, team shape /
  compactness, intensity zones.
- **Coming soon** (not faked): pass networks, per-player stat lines.

Intensity speed bands are the standard football GPS zones; the high-speed-running threshold
(≥5.5 m/s) follows Bradley et al. (2009), *J Sports Sci* 27(2):159–168.

## Honest caveats
- SoccerNet footage (the homography that makes pitch metrics possible relies on GSR's provided
  calibration). DPS MIS deployment on the school's own footage is pending (needs manual pitch
  calibration there).
- Derived metrics inherit the validated-position trust but are not separately ground-truth checked.
- Per-player stat lines are deferred until ReID lifts AssA above ~0.5 (current ID-switch noise
  makes single-player totals untrustworthy; team-level aggregates are robust).

Regenerate: `python scripts/coach_deliverable.py SNGS-118`
