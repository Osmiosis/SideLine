# Day 15 — Basketball Follow-Cam (A/B/C + possession-handoff)

Virtual camera: digital 640×360 (16:9, zoom 2.0) crop steered out of the 1280×720 SportsMOT
basketball frame. Three DISTINCT feeds, basketball-tuned, at parity with football Day-13.

- **A** — ball-faithful **+ possession-handoff** → gameplay / event highlights (THE new piece)
- **B** — ball+player confidence-weighted blend → comparison
- **C** — player-stabilized, heavily smoothed → player highlights / celebrations

Inputs: Day-14 ball track (`outputs/ball_track_bb/`), Day-9 player tracks
(`bb_ftdet_botsort_gmc`). Eval is PERCEPTUAL (basketball has no per-frame ungated ball GT;
Day-14 was plausibility-validated) — proxy metrics below are SUPPORTING evidence only.

## Proxy metrics (RAW = naive ball-center, the thing we must NOT ship)

### v_00HRwkvvjtQ_c001  (held-ball-heavy: 147 lost frames, longest 29-frame occlusion run)
| metric             |   RAW |     A |     B |     C |
|--------------------|------:|------:|------:|------:|
| jerk (px)          | 39.36 |  1.99 |  1.11 |  0.81 |
| accel (px)         | 20.71 |  2.47 |  1.74 |  0.52 |
| ball-in-safezone   | 0.698 | 0.506 | 0.396 | 0.132 |
| action-in-frame    | 0.362 | 0.377 | 0.573 | 0.790 |
| edge-clamp frac    | 0.706 | 0.599 | 0.197 | 0.092 |

### v_00HRwkvvjtQ_c007  (shot-heavy: 138 shot-flag frames, cleaner ball track)
| metric             |   RAW |     A |     B |     C |
|--------------------|------:|------:|------:|------:|
| jerk (px)          | 35.52 |  1.68 |  0.84 |  0.93 |
| accel (px)         | 19.02 |  2.16 |  1.50 |  0.57 |
| ball-in-safezone   | 0.884 | 0.760 | 0.703 | 0.252 |
| action-in-frame    | 0.383 | 0.434 | 0.651 | 0.835 |
| edge-clamp frac    | 0.388 | 0.331 | 0.038 | 0.044 |

Reading: A/B/C cut jerk ~20–35× vs RAW (no whip-pans). Ordering is by design — A keeps the
ball centered (high ball-safezone), C keeps the players in frame (high action-in-frame), B
sits between. A's higher edge-clamp is inherent: the basketball reaches frame edges (rim
shots, full-court) and the crop honestly pins there — it is not a tracking fault (clamp is
LOWEST at tighter zoom, where the crop has more centering freedom).

## Possession-handoff — A-feed target source breakdown (THE hypothesis)

| seq  | ball | pred | **holder (handoff)** | centroid | held/lost covered by holder |
|------|-----:|-----:|---------------------:|---------:|-----------------------------|
| c001 |  447 |  568 | **142**              | 5        | 142 / 147 lost (96.6%)      |
| c007 |  337 |  303 | **63**               | 4        | 63 / 67 lost (94.0%)        |

When the ball is confidently detected → follow ball. Short Kalman-predicted gaps (≤8 frames)
→ trust the predicted ball. When the ball is truly lost (hands occlude a held ball) → follow
the **last-holder player** (nearest player to the last confident ball — a held ball IS at that
player). Only a long no-holder gap → team centroid. The handoff segments are coherent
multi-frame blocks (see `*_handoff.png`), not single-frame flicker — the camera stays locked
on the ball-holder through each occlusion.

## THE TrackNet decision: NOT NEEDED

The cheap possession-handoff covers ~95% of held/lost frames by following the player who has
the ball; the crude team-centroid fallback fires on only 5 (c001) / 4 (c007) frames. Visually
(contact sheets + A/B/C frames) the A-feed stays on the action through held-ball dropouts — no
swing-to-nowhere. **The held-ball dropout the user saw is solved without TrackNet.**

Residual failure modes (bounded; monitor, do not yet justify TrackNet):
1. **Pass/shot released DURING a true detection gap** → camera lags on the passer until the
   ball is re-detected at the receiver. Mitigated: Day-14 Kalman `pred` already covers
   in-flight momentum for short gaps; only fully-lost (held-ball) frames hand to the holder,
   where the holder is the correct target by definition.
2. **Simultaneous loss of ball AND holder track** → falls to team centroid (5/4 frames) —
   coarse but brief.
3. **Holder ID switch mid-occlusion** (tracker swaps the held player's ID) — tracker-quality
   dependent; would drop to centroid if the bound track ends.

Revisit TrackNet only if a future sequence shows *systematic* pass-during-occlusion loss.

## Parity

Basketball now has A (gameplay/event highlights) + C (player highlights/celebrations) feeds —
same deliverable mapping as football Day-13. **Both sports at follow-cam parity.**

## Caveats
- SportsMOT broadcast footage; upstream ball track is plausibility-validated (Day-14), not
  RMSE-validated (no per-frame ungated GT for these clips).
- Crop ratio / pan limits are camera-distance dependent — re-tune by eye for school footage.
