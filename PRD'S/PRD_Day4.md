# PRD — Day 4: Basketball Detection Evaluation
**Project:** AI Sports Recording & Analytics System
**Goal:** Bring basketball detection to the same measured rigor as football. Acquire and sanity-check a ball-inclusive labeled basketball eval set, then bake off basketball detection models against it using the EXISTING Day 3 harness. Produce real precision/recall/mAP for the ball — and, if possible, broken down by occlusion.
**Estimated time:** 3–4 hours (data wrangling makes this longer than a pure-eval day)
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo, and `scripts/evaluate.py` from Day 3

---

## Context (read first)

Day 3 built a trustworthy football eval harness (`scripts/evaluate.py`) with verified precision/recall/mAP and passing sanity checks (GT-as-prediction → 1.0). soccana won football decisively (ball AP 0.474, mAP 0.689).

Basketball is currently BROKEN: boris-gans scored 22.3% "ball" but visual review showed it was firing on rim/scoreboard and missing the actual ball. No basketball model has been honestly measured yet, and no labeled basketball eval set existed — until now.

Day 4 fixes that: get a ball-labeled basketball eval set, sanity-check it, and measure basketball models for real. The DPS MIS court uses a MIX of ball types, so a generic-ball benchmark is more representative than a single-ball-type one.

**The Day 3 harness is reusable** — it evaluates any YOLO-format labeled set. Reuse it; don't rewrite metric logic.

---

## Datasets — acquire BOTH, sanity-check, then commit

### Primary candidate — UniqueData "Basketball Object Tracking" (Kaggle)
- Explicit BALL bounding boxes, PASCAL VOC format (annotations.xml).
- Has per-instance attributes: `occluded` (ball >30% blocked by player) and `basket` (ball obscured by net/rim).
- These attributes enable the standout analysis: mAP on CLEAN vs OCCLUDED frames.
- FRICTION: VOC XML → YOLO txt conversion needed (~15-line script: parse each XML, convert box to normalized cx,cy,w,h, write .txt per image).
- RISK: contains screenshots from video games AND broadcasts. Must check the real-vs-synthetic mix — a model that aces game renders may not transfer to real outdoor footage.

### Secondary candidate — Roboflow "Fiba Basketball"
- Already YOLOv8/v11 `.txt` format with `data.yaml` — plugs into the harness directly.
- Targets the official Molten 12-panel FIBA ball specifically.
- RISK: single-ball-type. Since DPS MIS uses mixed balls, this benchmark may be optimistic/unrepresentative. Treat as secondary / cross-check, not primary.

### Parked for the future — DeepSportradar Ball 3D Localization
- Gold-standard, real professional-arena footage, camera calibration included.
- NOT YOLO format (.pickle extraction via gabriel-vanzandycke/deepsport repo), and framed for 3D localization not 2D detection.
- Too high-friction for today. NOTE IT in notes.md as "the gold-standard benchmark to graduate to when fine-tuning." Do not attempt today.

---

## PART A — Acquire & convert datasets (~50 min)

1. **Fiba (Roboflow):** download in YOLOv8 format to `datasets/basketball_fiba/`. Already has data.yaml + txt labels. (Roboflow download may need a free account/key for the download step only — that's fine, it's a one-time download, not in the inference loop. If it blocks, ask developer.)
2. **UniqueData (Kaggle):** download via Kaggle CLI (`kaggle datasets download ...`) to `datasets/basketball_uniquedata/`. Kaggle CLI needs the developer's kaggle.json API token in place — if not configured, PAUSE and ask the developer to set it up (they download kaggle.json from their Kaggle account settings).
3. Write `scripts/voc_to_yolo.py` to convert UniqueData's PASCAL VOC XMLs → YOLO txt:
   - Parse each annotations.xml (object name, bndbox xmin/ymin/xmax/ymax, image width/height).
   - Convert to normalized (class cx cy w h). Map ball → class 0, player/person → class 1 (match the football harness's 2-class scheme: ball=0, person=1). NOTE: football harness used ball=0, person=1 per SoccerNet H250 — keep the SAME convention for consistency.
   - ALSO parse and preserve the `occluded` and `basket` attributes into a sidecar file (e.g. per-image JSON) so we can later split eval by occlusion.
   - Add `datasets/` to .gitignore if not already.

**STOP. Report what downloaded successfully and any auth friction.**

---

## PART B — Sanity-check BOTH datasets before trusting either (~30 min)

Reuse/extend `scripts/inspect_dataset.py` from Day 3:
1. For each dataset: count images, count labels, confirm image↔label pairing, tally ball vs person instance counts.
2. Render 5 ground-truth sample images per dataset with GT boxes drawn → `outputs/bball_gt_<dataset>_*.png`.
3. **For UniqueData specifically:** render samples that are flagged real vs flagged game/synthetic (if distinguishable), so the developer can judge the real-vs-videogame mix.

**Developer verifies (judgment call):**
- Do the GT ball boxes actually sit on the ball in both datasets?
- For UniqueData: how much is video-game footage vs real? Is it real enough to trust as a proxy for outdoor school basketball?
- DECISION POINT: pick the primary eval set based on what the samples show. Default expectation: UniqueData primary (for occlusion analysis) IF real-enough; Fiba as cross-check. If UniqueData is mostly game renders, flip to Fiba primary and note the limitation.

**STOP. Developer confirms which dataset(s) to use as primary before evaluating.**

---

## PART C — Reuse the harness: sanity-check on basketball data (~20 min)

Before trusting basketball numbers, re-run the Day 3 harness self-checks on the chosen basketball set:
1. GT-as-prediction → precision/recall/mAP = 1.0 (confirms harness reads the new labels correctly).
2. Empty predictions → recall 0, no crash.
3. Spot-check one image: model predictions vs GT, counts match by eye.

If GT-as-prediction ≠ 1.0 on basketball data, the label conversion (Part A) is likely wrong — fix before proceeding.

**STOP. Report sanity-check results.**

---

## PART D — Basketball model bake-off (~50 min)

Candidate models to evaluate (download weights to `models/`, all run at imgsz=1280, class-mapped BY NAME):
1. **boris-gans/basketball-yolo11s-detect** — the Day 2 model (12 classes incl ball variants). Now measure it HONESTLY — expect the eval to confirm it's weak/FP-prone.
2. **A generic basketball model from Roboflow/HF** — search "basketball ball player yolov8/yolo11 detection". Pick 1–2 with a real `ball` class (map by name).
3. **COCO yolov8m at 1280** — control baseline (has "sports ball" + "person").

Run `scripts/evaluate.py` (Day 3 harness) on each, against the chosen primary basketball eval set. Same protocol: IoU 0.5, fixed sample+seed, class mapping by name, report ball precision/recall/AP + person metrics + mAP@0.5 + ball FP count.

**IF UniqueData is the primary set:** also run the eval split by occlusion — ball mAP on `occluded=false` frames vs `occluded=true`/`basket=true` frames. This is the headline diagnostic: quantify how much occlusion degrades ball detection.

---

## PART E — Log, compare to football, commit (~30 min)

Append to `notes.md` a Day 4 section:
```
## Day 4 — [date] — Basketball detection eval

Eval set(s): [chosen primary + why]. Real-vs-videogame assessment: ___.
Class mapping: 'ball'->0, player/person->1 (same as football harness).
Harness sanity checks on basketball labels: GT-as-pred = 1.0 [pass/fail], empty=0 [pass/fail], spot [pass/fail].

### Results — ball class
| Model        | Ball P | Ball R | Ball AP | Ball FP | Person mAP | mAP@0.5 |
|--------------|--------|--------|---------|---------|------------|---------|
| boris-gans   |        |        |         |         |            |         |
| [other]      |        |        |         |         |            |         |
| coco yolov8m |        |        |         |         |            |         |
WINNER: ___

### Occlusion breakdown (if UniqueData)
| Condition       | Ball mAP |
|-----------------|----------|
| clean           |          |
| occluded/basket |          |

### Football vs Basketball parity check
| Sport      | Best model | Ball AP | Ball R | Person mAP |
|------------|-----------|---------|--------|------------|
| Football   | soccana   | 0.474   | 0.491  | 0.903      |
| Basketball | [winner]  |         |        |            |

VERDICT: is basketball at football-parity, or still behind? By how much?

### Notes
- DeepSportradar parked as gold-standard benchmark for future fine-tuning.
- [observations]
```
Then: confirm `datasets/`, `*.pt`, videos gitignored; `git status` clean of large files; commit scripts + notes:
`git commit -m "Day 4: basketball detection eval (harness reused), ball-labeled benchmark, occlusion breakdown, football-parity check"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Which dataset(s) downloaded; any auth friction (Kaggle/Roboflow)
3. GT sample images correct for the chosen set? Real-vs-videogame read on UniqueData?
4. Harness sanity check on basketball labels: GT-as-pred = 1.0? (trust gate)
5. Bake-off results table (ball P/R/AP per model) + winner
6. Occlusion breakdown numbers (if done)
7. PARITY VERDICT: basketball best vs football's soccana (0.474 ball AP, 0.491 recall) — close or far?
8. Errors hit (even if fixed)
9. Time taken

---

## Do NOT today
- Don't attempt DeepSportradar (too high-friction; parked for fine-tuning later).
- Don't trust any basketball number until the harness sanity check (GT-as-pred=1.0) passes on basketball labels.
- Don't commit to a dataset before sanity-checking GT boxes — the video-game-footage risk is real.
- Don't rewrite the metric logic — reuse scripts/evaluate.py from Day 3.
- Don't hardcode class indices — map by name (boris-gans has 12 classes, very different scheme).
- Don't train/fine-tune today — evaluating pretrained only (fine-tuning is a future session, against DeepSportradar).
- Don't commit datasets (large) or weights/videos.
