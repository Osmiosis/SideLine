# Basketball Event Highlight Candidates — RANKED (Output #3 parity)

The basketball half of the third DPS output: **auto-surfaced, interest-RANKED highlight
candidates** for a human (Student Council editor) to curate. Built from MOTION only, on a
SportsMOT basketball clip (`v_00HRwkvvjtQ_c007`) as a proxy for the DPS dual-phone capture.

## What this is (and is not)
- **HIGH-RECALL + RANKED.** Basketball is shot-dense, so a flat high-recall list would drown the
  editor. The set is **sorted best-first** (made-baskets/blocks at top, routine attempts at bottom)
  so the editor skims top-down, catches everything, isn't flooded.
- **The USER is the perceptual arbiter.** This package surfaces clips + contact sheets + a ranked
  index for a human to watch and verdict. It does not self-declare quality.
- **Motion-only.** Audio (whistle → fouls/stoppages, crowd-roar → made-basket confirmation) is the
  documented next lever — same as football.

## Honest event tiers
| Type | Tier | Meaning |
|------|------|---------|
| `shot_attempt` | kinematic | ball launches toward a hoop zone (launch-anchored = the release) |
| `fast_break` | kinematic | sustained fast full-court ball + players streaming one way |
| `likely_made_basket` | **proxy** | ball reaches the rim zone + play reverses (possession flip / ball back out). **NOT a confirmed score** — no net/height detection, plausibility-level ball track. Catches makes *and* close misses. |
| `block_proxy` | **proxy** | shot reaches the rim then sharply reverses away without a make |
| `steal_proxy` | **proxy** | open-court (midcourt) possession flip |

NOT built (cannot be done honestly from motion): **made-basket certainty**, **fouls** (referee
judgment → audio lever), **travels/violations**.

## Files
- `index.md` / `index.json` — the **ranked** curation list (rank, interest, type, confidence, timestamp).
- `contact_<seq>.jpg` — per-seq visual skim, rows in **rank order**, 5 thumbnails across each moment.
- `sample_highlight.mp4` — the **#1 ranked** moment, 640×360 (committed demo).
- `auto_draft_reel.mp4` — top-N ranked moments concatenated, marked "AUTO-DRAFT, human-curate"
  (LOCAL / gitignored — oversized).
- Per-moment clips: `outputs/events_bb/<seq>/clips/*.mp4` (LOCAL / gitignored).

## How it was made (reuse of Day-24, basketball-tuned)
1. Reuse Day-9 players, Day-19 ball (head-FP-cleaned), Day-21 court homography, Day-23 teams — no
   re-detection/tracking.
2. `scripts/detect_events_basketball.py` — motion features (ball court-kinematics with the
   **lost-ball = DEAD** discipline; ball-relative-to-hoop; possession + open-court flips; player
   streaming) → high-recall detectors → **interest ranking**.
3. `scripts/clip_highlights_basketball.py` — cut each moment with a **strict ball-tracking crop**
   (`--crop ball`, default): the camera follows the Kalman ball every detected/predicted frame and
   interpolates across lost gaps between real sightings, so it traverses to where the ball reappears
   (e.g. up to the rim during a shot) instead of holding on the shooter. The Day-15/16 follow-cam
   variant A is a *possession-handoff* feed (falls back to the last holder when the ball is lost),
   which kept the camera on the shooter during shots — `--crop follow_A` still selects it for compare.

## Validation
- **Sparse labels:** SportsMOT is tracking-only — no event/action labels → no label-anchored recall.
- **Internal anchor:** ball reaches **0.3 m** from the right hoop (rim) → a real shot/make is present.
- **USER perceptual** (the primary judge): watch the ranked clips — are the top-ranked ones genuinely
  exciting? Are made-baskets correctly surfaced at the top? Is the ranking usable? Tolerable FPs?

## DPS caveats
- **Hoop calibration is a setup dependency** football didn't have: the hoop zone comes from the
  **manual court-marking** (Day-21). Only `c007` is calibrated here; other clips would need marking.
- **Single-frame homography + a moving broadcast camera.** The c007 court homography was marked on
  ONE frame (540). This SportsMOT clip's camera pans/zooms, so projecting the ball to court coords is
  only accurate near frame 540 and drifts elsewhere — which makes the hoop-relative labels
  (`likely_made_basket`, `block_proxy`) **weak proxies, not reliable made-calls** (hence the "likely"
  / proxy naming, never a confirmed score). At a DPS **fixed** mount one calibration holds for the
  whole match, so this specific weakness is a proxy-footage artifact, not a method limitation — but
  it does mean ranking-by-made-basket should be treated as approximate on this clip. The pixel-space
  signals (ball motion, possession flips) and the strict-ball clip crop are unaffected by camera motion.
- **Plausibility-level ball track** + occlusion-heavy basketball → noisier events than football; the
  lost-ball discipline + ranking keep the top of the list clean.
- All thresholds (rim radius, approach distance, possession/convergence radii, speeds) are
  camera-scale + court-marking dependent → **re-tune at the DPS mount**. SportsMOT is a proxy:
  the method transfers, the numbers do not. Human-in-the-loop curation is the intended workflow.
