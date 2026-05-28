# PRD — Day 7: Fine-Tune a Basketball PLAYER Detector (the durable fix)
**Project:** AI Sports Recording & Analytics System
**Goal:** Fine-tune a detector to recognize "basketball player on court" (not generic COCO "person"), to fix the detection bottleneck that tanked Day 6 tracking (real HOTA 26.6 vs 74 ceiling, caused by COCO detecting refs/coaches/crowd). Evaluate with full Day-5 rigor (in-distribution + out-of-distribution detection metrics), then RE-RUN the Day-6 tracking harness to measure the HOTA lift.
**Estimated time:** 4–5 hours (real training; may span sessions — same as Day 5)
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo, SportsMOT data, TrackEval harness from Day 6

---

## Context (read first)

Day 6 diagnosed basketball tracking: ceiling (GT detections + ByteTrack) = HOTA 74.05 / IDF1 84.56, but real (yolov8m COCO person + ByteTrack) = HOTA 26.62 / IDF1 22.23. The collapse is DETECTION, not association: DetA fell 58.6 pts, precision was 26% (90k false positives — refs, coaches, audience, sideline), 3x over-detection. COCO "person" detects everyone; SportsMOT GT labels only the ~10 on-court players.

Fix: fine-tune a detector that natively detects only on-court basketball players. This is the Day-5 ball-detector pattern applied to players. We skipped the cheap court-bounds-filter validation deliberately — the diagnosis is strong enough (clean DetA collapse + precision signal) to commit directly to the durable fix.

**Scope: PLAYERS only.** Ball detector (Day 5) stays separate; combined pipeline is later.

---

## THE two traps (both about fooling ourselves)

**Trap 1 — in-distribution illusion (same as Day 5).** Training on SportsMOT-train and evaluating on SportsMOT-val = same distribution. Both the detection metrics AND the tracking HOTA you measure on SportsMOT-val are IN-DISTRIBUTION numbers. They'll look great and partly aren't real-world predictive. MUST also report an OUT-OF-DISTRIBUTION detection number on non-SportsMOT basketball footage.

**Trap 2 — two-layer eval.** This detector feeds a tracker, so "improvement" must be shown at BOTH layers:
- Detection layer: precision/recall/AP of the new player detector vs COCO baseline (ID + OOD).
- Tracking layer: re-run the Day-6 TrackEval harness with the new detector; HOTA/IDF1/MOTA vs the Day-6 real baseline (26.62 / 22.23 / -113). This is ID-only (no tracklet-labeled OOD footage available — note this limitation).

---

## Datasets
- **SportsMOT-train** (basketball sequences): training data. Player bounding boxes, on-court players only. Already have val; pull the basketball TRAIN sequences. Note count.
- **SportsMOT-val** (the 5 basketball seqs from Day 6): in-distribution detection + tracking eval. Already on disk.
- **OOD detection test:** a NON-SportsMOT basketball source the detector never trained on. Options, in order: (a) the user's own Day 2 4K basketball clip (closest to real deployment — needs a small hand/eyeball-labeled player sample, ~40-50 frames), (b) a different public basketball player-detection set. Decide in Part A.

---

## PART A — Prep training data + OOD test + baseline (~50 min)
1. Confirm/pull SportsMOT basketball TRAIN sequences. Build a YOLO-format training set: convert SportsMOT MOT-format GT boxes (player class) → YOLO txt (1 class: player). Build the data.yaml.
   - SportsMOT GT is per-frame boxes with tracklet IDs; for DETECTION training we drop the IDs and keep boxes as class "player". (Tracklet IDs aren't needed to train a detector.)
2. Acquire/define the OOD player test set (see options above). Sanity-check its GT boxes (render samples). If using the user's own clip, label ~40-50 frames' players.
3. **Baseline the starting point** on both ID (SportsMOT-val) and OOD: run COCO yolov8m person @1280 through the detection eval harness (Day 3 evaluate.py). Record player AP for ID and OOD. (ID should reproduce the Day-6 precision/recall story.)

**STOP. Report: train set built (n images)? OOD set ready + source? COCO baseline player AP (ID + OOD)?**

---

## PART B — Fine-tune the player detector (~90 min incl training)
1. Base weights: yolov8m.pt (COCO). Fine-tune on SportsMOT-train player class.
2. Config (mirror Day 5 — it worked): imgsz=1280, epochs=30 cap, patience=10, batch=4 (autobatch OOM'd the 4060 at 1280 on Day 5 — set batch=4 explicitly), workers=2, amp=True, cache=False, seed=42. Main-guard the script (`if __name__=="__main__":`) — Day 5 Windows multiprocessing crash.
3. Watch for OOM; if it happens, reduce batch then imgsz to 960, note it.
4. Watch val curves. MANUALLY STOP when mAP@0.5 plateaus (Day 5 lesson: the strict mAP@0.5:0.95 keeps creeping on box-tightness long after mAP@0.5 — the detection-quality metric we care about — flattens; don't waste hours chasing box-tightness the tracker doesn't need).
5. best.pt → copy to models/basketball_player.pt.

**STOP. Report: trained? final val mAP@0.5? OOM/config changes? curve plateaued or climbing?**

---

## PART C — Detection eval, honest (ID + OOD) (~30 min)
Run the Day-3 detection harness (evaluate.py) on models/basketball_player.pt, player class, imgsz=1280, IoU 0.5:
1. ID: SportsMOT-val. (overlaps training distribution — flattering)
2. OOD: the non-SportsMOT set. THE honest detection number.
Sanity-check (GT-as-pred=1.0) on the OOD labels first.

Comparison:
| Model              | ID player AP | OOD player AP | OOD precision | OOD recall |
|--------------------|--------------|---------------|---------------|------------|
| COCO yolov8m person| [Part A]     | [Part A]      |               |            |
| fine-tuned player  |              |               |               |            |

Key reads: did fine-tuning raise PRECISION (the Day-6 killer was 26% precision from crowd/ref FPs)? ID-vs-OOD gap?

**STOP. Report detection comparison.**

---

## PART D — Re-run the tracking harness: the payoff (~40 min)
Reuse the Day-6 TrackEval harness EXACTLY. Feed the new player detector into ByteTrack (default config — NO tracker tuning yet, isolate the detector's effect), on the same 5 SportsMOT-val basketball seqs.

Comparison vs Day-6 baselines:
| Setup                                   | HOTA  | MOTA   | IDF1  | IDsw | DetA | AssA |
|-----------------------------------------|-------|--------|-------|------|------|------|
| GT detections + ByteTrack (ceiling)     | 74.05 | 98.95  | 84.56 | 53   | 83.88| 65.39|
| COCO person + ByteTrack (Day-6 real)    | 26.62 | -113.03| 22.23 | 365  | 25.32| 28.00|
| fine-tuned player + ByteTrack (NEW)     |       |        |       |      |      |      |

Key reads:
- Did HOTA jump from 26.62 toward the 74 ceiling? By how much?
- Did MOTA go positive (crowd/ref FPs removed)?
- How much of the 47-pt ceiling gap did better detection close — and how much remains (that residual is what tracker tuning + association improvements would target next)?

---

## PART E — Log, interpret, commit (~30 min)
Append `## Day 7` to notes.md: setup, OOD source, COCO baseline, detection ID+OOD table, training curve/plateau note, the tracking comparison table, and interpretation:
- Detection precision before/after (the 26% killer → ?).
- HOTA lift 26.62 → ? ; MOTA negative → ? ; remaining gap to 74 ceiling.
- ID-vs-OOD detection gap (overfit signal; lever = more data variety / own footage).
- What's left for the tracker-tuning session (the residual ceiling gap = association headroom).
Then: confirm datasets/runs/weights/videos gitignored; commit scripts + notes:
`git commit -m "Day 7: fine-tuned basketball player detector (SportsMOT); ID+OOD detection eval; tracking HOTA lift vs Day-6 baseline"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. OOD set used + confirmation it's genuinely different-source from SportsMOT
3. Training: completed? final val mAP@0.5? OOM/config changes? curve plateaued?
4. Sanity gate: GT-as-pred=1.0 on OOD labels?
5. Detection table: ID + OOD player AP/precision/recall, fine-tuned vs COCO
6. Tracking table: HOTA/MOTA/IDF1 fine-tuned vs Day-6 real (26.62) and ceiling (74.05)
7. VERDICT: how much of the detection gap closed? did MOTA go positive? residual ceiling gap?
8. Errors hit (even if fixed)
9. Time taken

---

## Do NOT today
- Do NOT report only the in-distribution (SportsMOT-val) number — flattering. OOD detection number is the honest headline.
- Do NOT tune the tracker yet — feed the new detector into DEFAULT ByteTrack so we isolate the detector's effect on HOTA. Tracker tuning is the NEXT session.
- Do NOT open-ended hyperparameter-thrash — one solid run; manual stop at plateau.
- Do NOT train on the OOD set — test-only forever.
- Do NOT wire in the ball detector — players only this session.
- Do NOT trust the OOD number until GT-as-pred=1.0 passes on OOD labels.
- Do NOT commit datasets, runs/, weights, or videos.
