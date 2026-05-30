# Track De-Fragmentation — appearance-free, ZXY-validated (football, Alfheim full half)

**Problem (from Day-29):** the full-match scale-test exposed **5,106 track IDs for ~22 players**
(median track life 1.3 s) — identity is the real DPS blocker. **Goal:** cut fragmentation with
**APPEARANCE-FREE** methods only (motion/position re-linking — right for identical DPS house kits;
appearance ReID is useless on them, Day-26), and **measure the lift against ZXY ground truth**.

**Honest headline:** appearance-free re-linking cuts the raw ID count **18–27 % safely**, but does
**NOT** meaningfully improve ground-truth identity stability or analytics magnitude on this footage.
The fragmentation is structural (occlusion + unstable detection), beyond what motion-only can repair.
This **refines** the going-in hypothesis ("plausibly 5,106 → a few hundred"): not achievable
appearance-free here — which **sharpens the DPS case for the human tag-per-clip layer.**

## Part A — a REAL identity metric vs ZXY (not raw ID count)
Reused the Day-29 ZXY-refined fixed homography + 30 fps time-sync. Per frame, Hungarian-match tracked
foot-points (→ pitch) to in-view ZXY home players, accumulate per-GT the timeline of covering IDs:

| metric | baseline |
|--------|----------|
| **IDs per GT home player** | **median 191** (mean 171, max 275) — the *real* per-player fragmentation |
| identity purity (dominant ID's share of a GT's matched frames) | **0.116** |
| ID-switches vs GT | 2,600 |
| IDF1 (coverage-limited → relative) | 0.008 |
| raw unique IDs | 5,106 |

*Coverage caveat:* the single CENTRE camera + ~1.78 m homography means the GT-match denominator is
limited (≈14 % of "in-view" GT frames get a confident match) → IDF1 is a **relative** before/after
number, not absolute. The fragmentation (191 IDs/player) is **corroborated GT-free** by Day-29's median
track-life of 1.3 s.

## Part B — WHY tracks break (diagnose before fixing)
| cause | % | re-linkable? |
|-------|---|--------------|
| **OCCLUSION** (players cross) | **35.2** | yes (motion) |
| EDGE (left camera view) | 25.9 | only on re-entry |
| GENUINE_END | 20.1 | no |
| BLIP (1-frame) | 16.4 | — |
| FAST_MOTION | 1.9 | yes |
| FLICKER (detector drops a frame) | **0.7** | yes — but negligible |

~45 % of non-blip ends are motion-rejoinable, **dominated by occlusion**. FLICKER is negligible →
**detection-flicker smoothing was correctly skipped** (it would buy ~nothing). The fix = offline gap
re-linking targeting occlusion + buffer.

## Part C — appearance-free offline gap re-linking (measured)
Offline gap re-linking with gap *G* is the post-hoc equivalent of `track_buffer=G`, but global +
bidirectional → strictly more powerful, and **free (no ~1 hr re-track)**. Velocity-predicted in pitch
metres, tight gate, **one-to-one**, velocity-direction guarded (the over-link guards):

| config | raw IDs | substantial ≥2 s | IDs/GT median | purity | 2-GT spanning (over-link) |
|--------|---------|------------------|---------------|--------|---------------------------|
| baseline | 5,106 | 2,270 | 191 | 0.116 | 194 / 1036 (19 % noise floor) |
| moderate (gap 30 / 3 m) | **4,186** (−18 %) | 2,118 | 183 | 0.116 | 202 (≈ unchanged) |
| aggressive (gap 60 / 4 m) | 3,729 (−27 %) | 2,058 | 181 | 0.116 | 205 |

- **Raw IDs drop 18–27 %, SAFELY** — the 2-GT-spanning (over-link) count barely moves above the 19 %
  single-camera noise floor → re-linking is **not merging different players** (the guards work).
- **But GT identity stability is FLAT** — IDs/GT 191→183, purity 0.116→0.116, IDF1 0.008→0.008, and the
  **substantial-track count barely drops** (2,270→2,118). Re-linking merges mostly short/spurious tracks
  (away players, refs, blips), not the substantial tracks a human would tag.
- **Why the ceiling:** the home players' fragmentation is occlusion-driven *mid-stream identity hopping*
  (coverage hops between already-running tracks during crowding), plus an unstable detector (≈15 of 22
  players detected/frame in night footage). End→start motion re-linking cannot repair mid-stream hops,
  and appearance can't help on identical kits. Generous gates plateau ~2,700–3,100 IDs and start risking
  over-link — nowhere near "a few hundred clean tracks."

## Part D — did reduced fragmentation help the analytics?
**No.** Re-running the Day-29 intensity speed-bands on the re-linked tracks: **unchanged** (walk
43.6→43.8 %, sprint 4.6→4.5 % vs ZXY's walk 56.5 / sprint 0.5 %). The ~2× high-intensity inflation is
from **homography noise + single-camera in-view bias**, not ID-fragmentation (the band computation
already used substantial tracks + a teleport guard). Identity de-frag is not the lever for analytics
magnitude — a denser homography is.

## DPS read (the deployable conclusion)
- **Auto de-fragmentation is NOT a substitute for the human tag-per-clip identity layer** — appearance-free
  motion re-linking can't deliver clean per-player tracks on real fixed-camera footage. This is a
  *measured* confirmation of the Day-26/27/28 decision, not an assumption.
- **The tagging burden is bounded by the clipping design, not by the 2,270 tracks:** Day-27/28 tag
  *clips* (involvement + presence), so a human names a bounded set of highlight clips, never all tracks.
- **Team / aggregate analytics** (heatmaps, possession, team distance — no per-player identity needed)
  remain usable; **per-player season stats are not deliverable from auto-tracking** at this footage quality.
- The safe re-link (moderate, −18 %) is worth keeping as a cheap pre-pass (fewer spurious IDs), but it is
  not the identity solution.

## Caveats
ZXY = home team only (~11 players) → home-team identity metric. Single centre camera → coverage-limited
GT match (IDF1 relative). Alfheim is still a proxy (best yet). Over-link monitored against GT, but the
19 % baseline 2-GT noise floor limits how finely over-link can be certified.

## Files
`defrag_summary.json` (sweep + metrics), `break_causes.png`, `defrag_vs_identity.png`.
Scripts: `alfheim_identity_metric.py`, `alfheim_break_diagnosis.py`, `alfheim_relink.py`.
