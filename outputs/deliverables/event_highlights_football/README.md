# Event Highlight Candidates — Football (Output #3)

The third DPS output: **auto-surfaced highlight candidates** for a human (Student Council /
school Instagram editor) to curate into a reel. Built from MOTION only, on SoccerNet football
clips as a proxy for the DPS dual-phone capture.

## What this is (and is not)
- **HIGH-RECALL candidate set, not a finished reel.** It over-includes on purpose: a missed
  goal is gone forever; a false positive is a 2-second skip the editor discards. A human picks
  the keepers. This is the intended workflow, not a limitation.
- **Motion-only.** Audio (whistle for fouls/stoppages, crowd-roar for goal-confirmation) is the
  documented **next lever** — it is the honest path to real fouls and goal confirmation.

## Honest event tiers (what motion can / cannot do)
| Type label | Tier | Meaning |
|------------|------|---------|
| `shot` | solid kinematic | ball accel spike + heading toward a goal region |
| `fast_transition` | solid kinematic | sustained up-pitch ball movement (counterattack) |
| `likely_goal_candidate` | **honest proxy** | shot toward goal → ball near goal then dead/restart. **NOT a goal** — no goal-line/net detection, so it also catches saves/near-misses. |
| `tackle_proxy` | **honest proxy (noisy)** | opposing players converge on ball + possession flip |
| `stoppage_review` | **honest proxy** | ball dead + players clustered. Correlates with fouls/throw-ins/injuries/subs. **NOT a foul** — motion cannot separate a foul from a fair challenge. |

NOT built (cannot be done honestly from motion): **goal detection**, **foul detection**,
**skill-move detection**.

## Files
- `index.md` / `index.json` — the curation skim list: every candidate moment with timestamp,
  type(s), confidence, and whether it covers the GSR clip-level action label.
- `contact_<seq>.jpg` — per-sequence visual skim (one row per candidate moment, 5 thumbnails
  across each, from the A-feed crop). The fastest way to eyeball the set.
- `sample_highlight.mp4` — the single top-confidence moment, 640×360 (committed demo).
- `auto_draft_reel.mp4` — top-8 moments concatenated, marked "AUTO-DRAFT, human-curate"
  (LOCAL only / gitignored — oversized video).
- Per-moment clips live at `outputs/events/<seq>/clips/*.mp4` (LOCAL / gitignored).

## How it was made
1. Reuse Day-9 player tracks, Day-10 pitch homography, Day-11 teams, Day-12 ball track — no
   re-detection/re-tracking.
2. `scripts/detect_events.py` — motion features (ball kinematics in pixel + pitch with teleport
   guards, ball-toward-goal, possession + flips, player convergence, motion-halt) → high-recall
   detectors → candidate "moments".
3. `scripts/clip_highlights.py` — cut each moment from the **Day-13 follow-cam variant A**
   (ball-faithful, the right feed for ball-centric events); package + index.

## Validation
- **Label-anchored (sparse):** SoccerNet-GSR gives one clip-level action per clip (no dense
  event stream). All **5/5** labeled actions (Corner, Offside, Shots-off-target, Clearance,
  Foul) fall inside a candidate moment. The shot detector fires on the "Shots off target" clip;
  the stoppage proxy fires on the "Foul" clip.
- **Perceptual:** the contact sheets confirm moments frame real action — shots pan to the
  goalmouth, transitions follow up-pitch breaks, stoppage/tackle moments show contested play.
  False positives are low-confidence `tackle_proxy` midfield clips (tolerable skips).

## DPS caveats
- **Every threshold is camera-scale-dependent** and must be **re-tuned at the DPS mount**
  (different camera height/angle/zoom → different pixel speeds, goal-region pixels, convergence
  radii). These values are tuned to SoccerNet broadcast-ish framing.
- SoccerNet is a **proxy** — the method transfers; the numbers do not.
- On these 30s **pre-curated** SoccerNet clips the footage is action-dense, so moments are
  frequent. On continuous DPS match footage (sparse events) the same detectors yield distinct,
  well-separated highlights.
