# "Try Sideline" — simulated end-to-end walkthrough (design)

**Date:** 2026-07-06
**Status:** approved pending spec review
**Purpose:** Give reviewers a hands-on "gist of reality" of the full Sideline flow —
court setup → find players → choose output → processing → results — entirely in the
browser, so it is **$0, always-on (24/7), and needs no GPU or local PC**. It is a
throwaway demo for the review; it does not touch real jobs or the pipeline.

## Why

Reviewers need to experience the product 24/7 without depending on the operator's
local "studio." The real processing is GPU-bound and local by design, so this
walkthrough *simulates* the operator/user experience using real assets and the real
calibration math, ending in real analytics. It complements (does not replace) the
pre-processed Tottenham demo job in the demo account's "My matches."

## Scope

- **In:** a self-contained multi-step wizard page, reachable without login, that
  fakes the pipeline and shows real sample results.
- **Out:** no backend, no GPU, no real job creation, no writes to Supabase/Drive.
  Nothing here changes the customer or operator apps.

## Entry point

A public **"See how it works"** link on the sign-in page (`index.html`), above or
beside the sign-in card. Opens `demo.html`. No auth required.

## The five steps (single page, client-side state machine)

1. **Court setup** — show `site/demo/football_frame.png` (from
   `outputs/frames/football_midframe.png`). Prompt: click the 4 pitch corners in
   order (far-left, far-right, near-right, near-left). After the 4th click, compute
   the homography **client-side using the same corner→metre mapping as
   `backend/landmarks.py`** and draw the full pitch model (touchlines, halfway line,
   centre circle, both penalty boxes) warped onto the frame so the lines visibly
   "snap" onto the real pitch. A **Reset** re-arms it.
2. **Find players** — show `site/demo/football_tracked_frame.png` (from
   `outputs/frames/football_tracked_midframe.png`, which already has tracking boxes
   burned in). Caption: "We found the players automatically." A small panel lets the
   reviewer type a name on 1–2 players (the tagging gist). Purely cosmetic.
3. **Choose output** — three checkboxes: Coach analytics / Event highlights / Player
   highlights (labels mirror the real product). All checked by default; selection is
   cosmetic (does not change results shown).
4. **Processing** — a fake loading screen that steps through the **real stage labels**
   from `backend/pipeline.py` `_STAGE_LABELS` ("Tracking players", "Assigning teams",
   "Rendering highlights", …) with a progress bar, ~10s total, then auto-advances.
5. **Results** — the **real Tottenham vs Watford analytics** when available:
   embedded heatmap PNGs pulled into `site/demo/results/` after that job reaches
   `ready`, plus an **"Open the full results"** button to the job's Drive
   `results_url` (Drive's viewer plays the mp4 clips that the browser cannot).
   **Fallback:** if Tottenham results are not yet bundled, show representative
   heatmaps from `outputs/deliverables/SNGS-118/` so the demo always works. Caption:
   "Sample output — matches you submit are processed for you."

## Components / files

- `site/demo.html` — the wizard (markup + step orchestration, one `<script type=module>`).
- `site/js/calibration.js` — pure homography helpers: `worldPoints(labels)`,
  `computeHomography(srcPts, dstPts)` (4-point DLT), `project(H, pt)`. **Unit-tested.**
- `site/js/pitchmodel.js` — football pitch line segments in metre coordinates, for
  drawing the warped overlay. (Data + a `segments()` accessor.)
- `site/demo/*.png` — bundled frames + result heatmaps (copied from `outputs/`).
- `site/tests/calibration.test.mjs` — tests for the homography math (identity,
  known-square mapping, projection round-trip).
- Link added to `site/index.html`.

## Data flow

All client-side. Clicks → `computeHomography` → `project` each pitch segment endpoint
→ draw on canvas. No network calls except loading bundled images. Step state is a
simple in-memory index; no persistence.

## Error handling

- Fewer than 4 corner clicks → "Click all 4 corners" and stay on step 1.
- Degenerate/collinear clicks → homography solve returns null → friendly "Those points
  don't form a pitch — reset and try again," no crash.
- Missing bundled result images → fallback heatmaps (above).

## Testing

- Unit: `computeHomography` recovers a known homography for a unit square; `project`
  round-trips corners to their metre targets within tolerance; collinear points → null.
- Manual/browser: run all 5 steps on the preview deploy; confirm no console errors,
  pitch lines align, loading advances, results render.

## Dependencies / sequencing

- Steps 1–4 and the fallback results can be built and shipped immediately.
- Step 5's *real* Tottenham results require that job to reach `ready` (operator
  finishes calibration + render); then its heatmaps are copied into
  `site/demo/results/` and the Drive link wired in.

## Non-goals / risks

- Not a real pipeline; explicitly labelled "demo/sample" so reviewers aren't misled.
- mp4 clips are not embedded (mp4v is not browser-playable) — videos are reached via
  the Drive link only.
