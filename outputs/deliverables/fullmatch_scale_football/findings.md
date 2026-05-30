# Full-Match Scale-Stress-Test — Alfheim fixed single-camera (football, output foundation)

**Source:** Alfheim 2013-11-03 Tromsø IL – Strømsgodset, **single camera 1** (the *center* fixed
camera — chosen because a fixed elevated single camera ≈ the DPS phone rig; NOT the 5-cam stitched
panorama). First half. SportsMOT/SoccerNet were 30-second proxies; **this is the first full-match
(47-min) test on fixed-camera footage** — the closest proxy yet to DPS deployment.

**The point was to find what BREAKS at full-match length.** It did. Below: what broke, what held,
and the first real ground-truth validation of the analytics geometry (Alfheim ships ZXY sensor GT).

---

## Acquisition + stitch (Part 0/A)
- **Continuity gate (verified BEFORE stitching):** 942 clips, indices 56→997, **zero missing numbers**,
  inter-clip gaps all 2.97–3.01 s (median 3.001) — the 3-second raw-H.264 segments tile the whole
  half with **no gaps**. CONTIGUOUS → GO. (A gappy event-clustered source would have made a "match"
  that teleports across cuts — useless. It isn't.)
- **Stitch finding:** raw-H.264 **stream-copy concat corrupts at clip seams** (widespread decoder
  macroblock errors) — the byte-joined elementary streams aren't a cleanly continuous bitstream.
  **Fix = re-encode** during concat (decode-each-clip-clean, GPU nvenc): produced a clean 47.1-min
  / 30 fps / 84,780-frame `first_half.mp4` with only ONE single-frame seam blip. *Honest note: the
  seam glitches are STITCH artifacts, not pipeline failures.*

## Foundation at scale (Part B) — what BROKE
Day-9 tracker (soccana.pt + BoT-SORT + GMC) on the full half, `imgsz=1280`, processed at `vid_stride=2`
(15 fps sampling, 42,390 frames):

| metric | value | reading |
|--------|-------|---------|
| **unique track IDs over the half** | **5,106** | vs ~22 real players → **232× fragmentation** |
| new IDs / match-minute | ~108, **no plateau** | IDs accumulate linearly all half — the core scale break |
| median track lifetime | **1.3 s** | tracks shatter constantly (p90 29.5 s, max 243.7 s) |
| substantial tracks (≥1 s) | 2,774 | even these vastly exceed 22 |
| detections / frame | 15.3 | center camera sees ~15 of 22 players |
| runtime (RTX 4060) | **63.9 min** for one half @ 11 fps | every-frame full-res ≈ 2.9 hr/half projected |
| **peak RAM** | **1.47 GB, flat** | **no memory exhaustion** (Day-26 lesson handled by streaming) |

**What broke:** identity. Over 47 min, ID-switch/fragmentation accumulates without bound (5,106 IDs,
median 1.3 s lifetime). On 30-second clips this is invisible; at full-match scale it dominates — and it
is exactly why **per-player** season stats need a human tag-per-clip identity layer (Day-27/28), not
raw track IDs. **What held:** memory (flat 1.47 GB) and throughput (feasible but ~1 hr/half on a 4060 →
real operator-app compute signal: an overnight/offline batch, not live).

## Analytics TRUST GATE vs ZXY ground truth (Part C) — the bonus
Alfheim ships ZXY sensor GT (home-team pitch positions + speed @ ~16 Hz). **First real GT validation of
the analytics geometry** (prior sessions were plausibility-only).

- **One FIXED homography holds the whole 47-min half.** Seeded from 4 center-circle landmarks, then
  ZXY-refined (ICP/RANSAC). Held-out frames spread across the FULL half give **median 1.78 m** player-
  position error (mean 1.71, p90 2.61) — the *same* as a 3-min window, proving a single fixed H is
  stable for the entire half. **This is the fixed-camera DPS advantage, demonstrated on real full-length
  footage** (broadcast proxies needed per-segment homography). ~10 of 11 home players are in-view.
- **Intensity speed-bands: directionally right, magnitude inflated.** My in-view distribution
  (walk 44 / jog 33 / run 12 / high 6 / sprint 5 %) vs ZXY GT (walk 57 / jog 33 / run 8 / high 2 /
  sprint 0.5 %): same walk-dominated monotonic shape, but **high-intensity inflated ~2×**. Causes
  (honest): single-camera in-view bias (camera captures active central play), 1.78 m homography noise,
  and ID-fragmentation. **Full-match intensity/distance is NOT yet GT-trustworthy** without ID stability
  + denser homography — a concrete, measured next-step, not a guess.

## Caveats
- Alfheim is STILL a proxy (Norwegian pro match) — but the **best proxy yet**: fixed single camera, full
  match, sensor GT. DPS kit/court/lighting pending real DPS footage.
- ZXY = **home team only** (~10 outfield players); away team has no GT.
- Single CENTER camera → in-view geometry validation, not full-pitch per-player distance.
- Tracked at stride 2 (15 fps); full-rate would add ID churn, not remove it.

## Files (figures in this folder)
- `id_accumulation.png` — cumulative IDs vs match minute (no plateau).
- `speed_bands_vs_zxy.png` — intensity bands, mine vs ZXY GT.
- `trust_overlay.png` — ZXY GT players back-projected via the fixed homography onto a real frame.
- `trust_gate.json`, `scale_findings.json`, `tracking_stats.json` — the numbers.

**Deferred to a split session (PRD-anticipated):** events + player-highlights at full-match scale (the
downstream deliverable scripts are SoccerNet-seq-coupled → need decoupling). This session delivered the
foundation + the analytics trust gate.
