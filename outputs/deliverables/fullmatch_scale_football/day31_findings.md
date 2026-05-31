# Day 31 — Full-Match Scale Test COMPLETED: events + player-highlights at 45 min (football)

Finishes the Day-29 full-match scale test. Day-29 ran the FOUNDATION (detection+tracking) + analytics
at full scale but **deferred** the two ball/identity-dependent deliverables. Day-31 gets the two missing
scale numbers on the Alfheim fixed single-cam stitched half (47.1 min, 30 fps, 1280×960; the best DPS
proxy available — fixed elevated single camera, real continuous match).

All inputs reused (no re-detection / re-tracking of players): Day-29 MOT (5,106 IDs) → Day-30 re-linked
**safe −18%** tracks (4,186 IDs) + fixed homography (1.78 m median GT error).

---

## Blocker found at session start → probe-then-branch

The PRD assumed "the ball track" existed. **It did not** — Day-29 tracked *players only* (`classes=0`),
and there was no team-assignment for Alfheim either. Both event detection and player involvement are
ball-anchored. Rather than blind-run a 1 hr ball pass that might produce an unusable track on wide
fixed-cam footage, we **probed ball recall cheaply first, then branched** (PRD addendum discipline).

---

## PART B (events) — EVIDENCE-BACKED BLOCKED (ball recall too poor)

**Ball-recall probe** (`alfheim_ball_probe.py`): soccana Ball class on a 10-min window (src frames
18000–36000, stride 4 → 4,500 processed frames), conf floor 0.15 (recall-biased).

| metric | value |
|---|---|
| raw recall (frames with ≥1 ball) | **30.0 %** (1,352 / 4,500) |
| ball confidence — median / p10 / p90 | 0.37 / 0.17 / 0.73 |
| multi-ball frames (FP/ambiguity) | 5.9 % |
| spot-check of detections | ambiguous — low-conf small blobs near midfield, indistinguishable from distant-head FPs |

**Verdict: POOR → event detection NOT run.** Event detectors (shot/transition/likely-goal) are built on
the ball's **pitch-SPEED across consecutive frames**. With the ball present in only ~30 % of frames (and
those low-confidence/ambiguous), 70 % of velocities would be interpolated/fabricated — any "event density"
number would measure the *detector's failure on wide-cam footage*, not real event density (the
metric-vs-reality trap). Reporting a fake density would be dishonest, so Part B is reported as **blocked
with measured evidence**, not a number.

**Why (root cause):** soccana was trained on SoccerNet **broadcast** footage (ball is large, tracked by a
camera operator). Alfheim is a **wide fixed elevated** camera → the ball is a few pixels on grass at
distance, often occluded/blending. Standard broadcast-tuned ball detection does not transfer.

**This is a REAL DPS finding, not a dead end.** DPS's planned **wide fixed phone capture** would hit the
**same wall**: ball-dependent event highlights (output #3) on wide fixed cameras need either a
wide-cam-tuned ball detector (small-object training) or higher-resolution capture. Known gap, now measured.

---

## PART C (player highlights) — THE TAGGING-VOLUME NUMBER (delivered fully, ball-resilient)

The priority deliverable. Output #2's design = **involvement clips** (nearest-player-to-ball) + a
**presence fallback** (every substantial track gets its longest visible stretch). The presence fallback
needs **no ball** → it carries the number even with the ball gate failed.

**Key framing — why this number is robust to the poor ball recall:** every substantial track must be
tagged once by a human (assign it to a real player) — that *is* the tagging unit. Presence gives every
substantial track ≥1 clip with no ball. Involvement only *adds* clips. So **#substantial tracks is the
MINIMUM tagging volume**, and the viable/prohibitive verdict holds regardless of ball quality.

`alfheim_player_tagging.py` on the 4,186 re-linked tracks (15 fps effective = stride-2 over 30 fps):

| metric | value |
|---|---|
| total tracks | 4,186 |
| **substantial tracks (≥1 s on screen)** | **2,224** |
| **TOTAL CLIPS TO TAG (full half)** | **2,224** (presence; 100 % — no usable ball → 0 involvement) |
| est. human tag time @ 5 s/clip | **3.1 hours** |
| est. human tag time @ 10 s/clip (realistic) | **6.2 hours** |
| est. human tag time @ 20 s/clip (careful) | **12.4 hours** |

**Tagging volume vs how-strict-you-filter** (raising the "substantial" bar doesn't rescue it):

| min track length | clips to tag | @10 s/clip |
|---|---|---|
| ≥ 1 s | 2,224 | 6.2 h |
| ≥ 2 s | 1,867 | 5.2 h |
| ≥ 3 s | 1,662 | 4.6 h |
| ≥ 5 s | 1,427 | 4.0 h |
| ≥ 10 s | 1,098 | 3.0 h |

**Verdict: PROHIBITIVE for a full match.** Even the most aggressive filter (only tracks ≥10 s) leaves
~1,100 clips ≈ 3 hours of tagging per half. And it's worse than the time: median track length is **1.3 s**
— most fragments are too short and the players too small on a wide cam to even *identify*, so per-fragment
tagging is often not just slow but **impossible in practice**.

**This corrects an over-optimistic Day-30 note.** Day-30 reasoned tagging "stays viable" because the
clipping design bounds it. On 30 s SoccerNet clips that was true (~30–40 clips/clip). **The full-match
test reveals what the 30 s proxy hid:** at match scale it's 2,224 clips. *Scale* is exactly what breaks it
— which is the whole point of running the test.

**Inclusivity survives in principle, not in practice.** Presence fallback guarantees 100 % of substantial
tracks get a clip — so coverage is technically complete. But with **~191 track-IDs per real player**
(Day-30 fragmentation), a pre-tag "player reel" is really a **track reel**; the human tagging is what
reconstitutes the ~22 real players, and *that* is the 2,224-clip / multi-hour cost. "Per-player" is
meaningful only *after* prohibitive tagging.

---

## Synthesis — all 3 deliverables now full-match-tested (honest DPS read)

| deliverable | full-match (45 min) status | DPS-deployable? |
|---|---|---|
| **Foundation** (detect+track) | Day-29: holds — RAM flat, one fixed H = 1.78 m vs ZXY | **Yes** (proven at scale) |
| **Analytics** (heatmaps/possession/team distance) | Day-29/30: team/aggregate good; per-player speed ~2× inflated (homography/single-cam, *not* identity) | **Team-level yes; per-player no** (needs denser/multi-cam homography) |
| **Events** (output #3) | Day-31: **blocked** — ball recall 30 % on wide fixed cam | **No** without a wide-cam ball detector or higher-res capture |
| **Player highlights** (output #2) | Day-31: 100 % coverage *in principle*; **2,224 clips ≈ 3–12 h tagging** per half | **Not viable** at full-match scale without fixing fragmentation (structurally blocked, Day-30) |

**What would reduce the tagging volume** (none available appearance-free today):
- Fewer track-IDs per player → fixes the count at the source, but Day-30 proved this is **structurally
  blocked** without appearance cues (identical kits) or multi-camera.
- The Day-30 re-link pre-pass already applied (−18 %, 5,106→4,186); aggressive re-link plateaus ~2,700–3,100
  and risks over-linking different players — doesn't reach a taggable count.
- Tag involvement-only (skip presence) → needs a ball we don't have, and abandons inclusivity (defeats the
  output's purpose).

**Bottom line:** the full-match scale test is now complete for all 3 outputs. The honest result is that the
*foundation* scales, *team analytics* scale, but the two flagship per-instance outputs (events, per-player
highlights) **do not** scale to a wide fixed single-cam full match — events because the ball is untrackable
at that scale, player highlights because fragmentation turns full-match tagging into hours. Both point to
the same upstream fixes (better small-object/ball detection; multi-cam or appearance for identity), not to
tuning the downstream clip/event logic.

---

### Caveats
- Alfheim is a proxy: fixed **single** elevated cam, real full match, **but not DPS** (different kit, court,
  lighting, phone optics). The wide-cam ball-recall + tagging-volume findings transfer in *kind*; exact
  numbers will shift on real DPS footage.
- Ball probe = 10-min window, one camera, night match; recall could vary by lighting/section, but 30 % at a
  permissive 0.15 floor is decisively below what event velocity needs.
- Tagging-time estimates are clip-count × seconds-per-tag; real tagging also includes the (often impossible)
  *identification* of 1–2 s distant fragments — so the estimates are optimistic lower bounds.
