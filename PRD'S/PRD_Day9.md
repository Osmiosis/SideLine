# PRD — Day 9: Shared Tracker-Tuning Sweep (both sports, cached detections)
**Project:** AI Sports Recording & Analytics System
**Goal:** Close the association gap that Day 6-8 localized in BOTH sports. Cache detections once, then cheaply sweep ByteTrack association parameters over the cached boxes, measuring HOTA/IDF1/AssA per config against the existing baselines. Only escalate to BoT-SORT appearance-ReID if the ByteTrack sweep plateaus below target.
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo, TrackEval harness, detectors (soccana football, basketball_player), datasets (SoccerNet GSR subset, SportsMOT football+basketball subsets)

---

## Context (read first)

Tracking is now baselined for both sports and BOTH are association-bound (not detection-bound):
- **Football (SoccerNet):** real HOTA 54.99, AssA 43.47; ceiling HOTA 76.50, AssA 68.24. **AssA gap 24.7 — the biggest single lever in the project.**
- **Football (SportsMOT):** real HOTA 53.83, AssA 42.16; ceiling AssA 51.71.
- **Basketball (SportsMOT, post-Day-7 detector):** real HOTA 48.50, AssA 31.55; ceiling AssA 65.39. AssA gap ~34.
All measured with default `bytetrack.yaml`. The detectors are good; the TRACKER's default association is the bottleneck.

This session attacks association. Detection is NOT touched — we reuse the existing detectors. To keep it light on the 4060 (which threw OOM on Day 5/7 and a VIDEO_TDR on Day 8 under sustained 1280 inference), we CACHE detections once and sweep the tracker over cached boxes — association tuning is CPU-only math, no GPU, no TDR risk, dozens of configs cheaply.

**Approach (staged):** ByteTrack param sweep FIRST (cheap, motion-only). Escalate to BoT-SORT appearance-ReID ONLY if ByteTrack tuning plateaus below target. Rationale: cached-detection sweeping makes ByteTrack tuning nearly free; BoT-SORT reintroduces GPU load (appearance-feature extraction) so it's the second arm, not the first.

---

## PART A — Build the detection cache (~40 min)
The key enabler: run each detector over each dataset subset ONCE, save all detections to disk in a tracker-agnostic format. Then the sweep never re-runs the detector.

1. For each (detector, dataset-subset) pair, run detection @1280 over every frame, save per-frame detections (frame, x, y, w, h, conf, class) to `outputs/det_cache/<dataset>_<detector>/<seq>.txt` (or .npz). Pairs:
   - soccana × SoccerNet-GSR subset (5 seqs)
   - soccana × SportsMOT-football subset (5 seqs)
   - basketball_player × SportsMOT-basketball subset (5 seqs)
2. **Run this ONCE, carefully** — this is the only GPU-heavy step. To dodge the Day-8 VIDEO_TDR on long seqs: process seq-by-seq, free GPU memory between seqs, and if a seq crashes, it can be re-run individually without redoing the others. (Consider lowering to imgsz=960 if 1280 TDRs again — but note that detection-resolution change in the log, since it slightly changes the cached detections.)
3. Verify cache: detection counts per seq should match the Day-6/7/8 baseline detection counts (sanity that the cache reproduces what we measured before).

**STOP. Report: caches built for all 3 pairs? counts match prior baselines?**

---

## PART B — Build the cached-detection tracker runner (~30 min)
1. Adapt the Day-6 tracker runner to read detections FROM CACHE instead of running the detector. Feed cached boxes frame-by-frame into ByteTrack with a CONFIGURABLE parameter set.
2. **Validate the cache path reproduces the baseline:** run the cached runner with DEFAULT bytetrack.yaml params and confirm it reproduces the Day-8 / Day-7 real-baseline HOTA (e.g. SoccerNet soccana should give HOTA ~54.99 again). If it doesn't match, the cache or the cached-runner is wrong — FIX before sweeping. (This is the trust gate for this session: the cached pipeline must reproduce the known baseline number.)

**STOP. Report: does cached-default reproduce the Day-8 baselines (HOTA ~55 football, ~48.5 basketball)?**

---

## PART C — ByteTrack parameter sweep (~60 min)
Sweep the association-relevant params over cached detections (CPU, fast, no GPU). Parameters and rationale:
- **track_buffer** (default 30 frames): how long a lost track survives before deletion. Sports players get occluded/leave frame and return — a longer buffer should cut ID re-spawning (the 343-vs-117 ID inflation). Try {30, 60, 90, 120}.
- **match_thresh** (default 0.8): IoU threshold for associating detections to tracks. Try {0.7, 0.8, 0.9}.
- **new_track_thresh** (default 0.6): confidence to spawn a new track. Higher = fewer spurious new IDs. Try {0.6, 0.7, 0.8}.
- **track_high_thresh / track_low_thresh**: the two-stage association thresholds. Optionally sweep coarsely.

1. Run a grid (or sensible subset — don't combinatorially explode; start with one-param-at-a-time from defaults, then combine the best). Each config: cached dets → ByteTrack(config) → TrackEval → record HOTA/DetA/AssA/MOTA/IDF1/IDsw.
2. Do this PER DATASET (SoccerNet football, SportsMOT football, SportsMOT basketball) — a config that helps one may differ across sports/footage. Note per-sport best.
3. Produce a results table: config → metrics, sorted by HOTA (and separately by AssA, since AssA is the target).

**Key question:** how much of each sport's AssA gap does ByteTrack tuning close? (Football SoccerNet target: 43→toward 68. Basketball: 32→toward 65.)

**STOP. Report the sweep results table + best config per dataset + how much AssA gap closed.**

---

## PART D — Decide on BoT-SORT (only if needed) (~40 min, conditional)
Look at Part C results:
- **If ByteTrack tuning closed most of the AssA gap** (e.g. football AssA into the 60s): great, BoT-SORT may be unnecessary this session. Document and stop.
- **If a meaningful gap remains** (AssA plateaus well below ceiling): run a BoT-SORT arm. BoT-SORT adds appearance ReID (GPU step — re-detection not needed, but appearance features are extracted from cached frames). Run BoT-SORT (its sensible defaults + best motion params from Part C) on each dataset, measure, compare to best ByteTrack.
- Note: BoT-SORT reintroduces GPU work; process seq-by-seq to avoid TDR.

Report: did BoT-SORT beat tuned ByteTrack, and by how much, per sport? Is the appearance-ReID cost worth the gain?

---

## PART E — Log, interpret, commit (~30 min)
Append `## Day 9` to notes.md: cache build, cached-default reproduces-baseline gate, the sweep table (per dataset), best configs, AssA gap closed per sport, BoT-SORT decision + result (if run), and:
- Updated real HOTA per sport vs the Day-6/7/8 baselines and the ceilings.
- Which single parameter mattered most (the report-worthy finding).
- Remaining gap to ceiling and whether it's worth chasing further or "good enough" to start building deliverables.
- Recommended production tracker config per sport (the thing the real pipeline will use).
Then: confirm det_cache/track_results/datasets/weights/videos gitignored, no SoccerNet leakage; commit scripts + notes:
`git commit -m "Day 9: shared tracker-tuning sweep over cached detections; ByteTrack params [+ BoT-SORT]; AssA gap closed both sports"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Caches built + counts match prior baselines?
3. Cached-default reproduces Day-8 baselines (the trust gate)?
4. Sweep table: best config + metrics per dataset
5. AssA gap closed per sport (football 43→? toward 68; basketball 32→? toward 65)
6. Single most impactful parameter?
7. BoT-SORT run? if so, did it beat tuned ByteTrack, worth the cost?
8. Recommended production tracker config per sport
9. Errors hit (even if fixed) + time taken

---

## Do NOT today
- Do NOT re-train or change detectors — association only; reuse existing detectors via cache.
- Do NOT re-run detection per sweep config — that's the whole point of the cache (and dodges the 4060 TDR).
- Do NOT hand-roll metrics — reuse TrackEval.
- Do NOT trust sweep numbers until cached-default reproduces the known Day-8 baseline (the session's trust gate).
- Do NOT combinatorially explode the grid — one-param-at-a-time from defaults, then combine winners.
- Do NOT do the ball (Kalman, separate session).
- Do NOT commit caches, track_results, datasets (incl SoccerNet/NDA), weights, or videos.
