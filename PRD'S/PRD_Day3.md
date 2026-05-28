# PRD — Day 3: Football Detection Evaluation Harness
**Project:** AI Sports Recording & Analytics System
**Goal:** Build a rigorous, trustworthy precision/recall/mAP evaluation for football ball+player detection against the SoccerNet_v3_H250 labeled test set. Re-rank soccana / uisikdag / coco on REAL metrics, settling the false-positive question with hard numbers.
**Estimated time:** 3–4 hours (more conceptually demanding than prior days; verification-heavy)
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv` and repo

---

## Why this exists (read first)

Across Day 2, every "ball %" number was RECALL-ONLY with no precision floor. This produced misleading winners twice:
- Football: uisikdag scored 68.3% but visual review showed mostly FALSE POSITIVES on white pitch markings. soccana (~12%) had near-zero FPs and is the real winner by eye.
- Basketball: boris-gans scored 22.3% but visual review showed FPs on rim/scoreboard, missing the actual ball.

This harness replaces eyeball verdicts with measured precision, recall, and mAP against a gold-standard labeled set. It validates (or overturns) the soccana-over-uisikdag call with numbers.

**Scope today: FOOTBALL ONLY.** Basketball eval is a separate later session (no clean public labeled set exists for it).

---

## The evaluation set

**SoccerNet_v3_H250** (Zenodo record 7808511):
- A subset of SoccerNet-v3: only frames where person bbox height <= 250px (i.e. WIDE-ANGLE / long-shot frames — close to our elevated camera angle).
- Already in YOLO annotation format. **2 classes: 0 = ball, 1 = person** (person = all 7 human annotation types merged).
- Splits: 14,368 train / 2,726 val / 2,692 test.
- Open access on Zenodo (no SoccerNet access gate).
- Companion code: github.com/kmouts/SoccerNet_v3_H250

**Use the TEST split only** for evaluation (never train/val — we're not training today).
**To keep runtime sane, evaluate on a fixed random sample of the test split (e.g. 500 images), seeded for reproducibility.** Full 2,692 is fine if time allows.

---

## CRITICAL — class mapping (this is where silent bugs live)

The eval set has 2 classes: ball(0), person(1). Our models have DIFFERENT schemes:
- soccana: 0=Player, 1=Ball, 2=Referee
- uisikdag: 0=ball, 1=goalkeeper, 2=player, 3=referee
- coco (yolov8m): 0=person, ..., 32=sports ball (80 classes)

**Before evaluating, map every model's output classes into the eval's 2-class space:**
- Any model class whose name contains "ball" -> eval class 0 (ball)
- Any model class whose name is player/goalkeeper/referee/person -> eval class 1 (person)
- All other COCO classes (car, etc.) -> DROP (don't count)

Map BY CLASS NAME via `model.names`, never by hardcoded index. Print the resolved mapping per model and have the developer eyeball it before the eval runs. A wrong mapping silently turns correct detections into false positives and produces another misleading number — the exact failure we're trying to kill.

---

## PART A — Acquire & sanity-check the dataset (~40 min)

1. Download SoccerNet_v3_H250 from Zenodo (record 7808511). It's large; if there's a way to pull only the test split, do that. Otherwise download and use test only.
2. Extract to `datasets/soccernet_h250/` (gitignored — add `datasets/` to .gitignore if not already).
3. Verify structure: confirm there are image files and matching YOLO `.txt` label files (each line: `class cx cy w h`, normalized).
4. Write `scripts/inspect_dataset.py` that:
   - Counts images and labels in the test split
   - Confirms every image has a label file (and flags mismatches)
   - Tallies class distribution (how many ball instances vs person instances)
   - Renders 3 sample images with their GROUND-TRUTH boxes drawn, saved to `outputs/gt_sample_*.png`
5. **Developer verifies the 3 GT sample images**: do the ground-truth boxes actually sit on the ball and players? (Confirms we're reading the labels correctly before we evaluate against them.)

**STOP. Developer confirms GT boxes look correct before proceeding.** If GT boxes are wrong, the label-parsing is wrong and every downstream metric is meaningless.

---

## PART B — Build the evaluation harness (~70 min)

Create `scripts/evaluate.py`. Requirements:

### Inputs
- A model weights path
- The dataset test split path
- A fixed sample size + random seed (default 500, seed 42)
- imgsz=1280, device=0, a confidence threshold sweep (see below)

### Core logic
For each image: run model, map predicted classes into {ball, person} per the mapping rules, then match predictions to ground-truth boxes using IoU.
- A prediction is a True Positive if it matches a GT box of the same class with IoU >= 0.5 (standard). Each GT box can be matched at most once (greedy by descending confidence).
- Unmatched predictions = False Positives. Unmatched GT boxes = False Negatives.
- Compute PER CLASS (ball separately from person — ball is the one we care about):
  - Precision = TP / (TP + FP)
  - Recall = TP / (TP + FN)
  - AP (average precision) via the precision-recall curve over confidence thresholds
- mAP@0.5 = mean of per-class AP. Also report mAP@0.5:0.95 if not too slow (standard COCO metric).

### Do NOT reinvent metric code from scratch if avoidable
Prefer a vetted implementation to reduce bug risk:
- **Option 1 (preferred):** Use Ultralytics' built-in validation. If a model + a dataset YAML (pointing at the H250 test split, 2 classes) is provided, `model.val(data=..., imgsz=1280)` computes precision/recall/mAP automatically. BUT this requires the model's class indices to match the dataset YAML's classes. Since our models have different schemes, this needs a remapping step or a per-model dataset YAML. If you can make Ultralytics val work with correct class remapping, USE IT — it's battle-tested.
- **Option 2 (fallback):** If remapping into Ultralytics val is too fiddly, hand-roll the IoU matching above, but then VALIDATE the hand-rolled metrics against a known case (see Part C).

Whichever path: the ball-class precision and recall are the headline numbers.

### Output
- A per-model table: ball precision, ball recall, ball AP, person precision, person recall, person AP, mAP@0.5, and FP count for ball specifically.
- Save raw results (per-image TP/FP/FN counts) to `outputs/eval_<model>.json` for later inspection.

---

## PART C — Sanity-check the harness BEFORE trusting it (~20 min)

A clean-looking eval that's secretly wrong is the worst outcome. Validate the harness on a known case first:

1. **Self-consistency check:** Feed the GROUND TRUTH itself in as if it were predictions (perfect detector). The harness MUST report precision=1.0, recall=1.0, mAP=1.0. If it doesn't, the matching logic is broken — fix before proceeding.
2. **Degenerate check:** Feed empty predictions. Must report recall=0, and precision undefined/0 (handle divide-by-zero gracefully).
3. **Spot check:** For one image, manually look at the model's drawn predictions vs GT and confirm the TP/FP/FN counts the harness reports match what you see by eye.

**Only after these three pass do the real model numbers mean anything.** Report sanity-check results to developer.

---

## PART D — Run the real evaluation (~30 min)

1. Run `evaluate.py` for each of: soccana, uisikdag, coco (yolov8m), all at imgsz=1280, same sample+seed.
2. Produce the final comparison table.
3. **The key question this answers:** does soccana's ball PRECISION actually beat uisikdag's, and does uisikdag's high recall come with a wrecked precision (lots of ball FPs)? Confirm or overturn the Day 2 eyeball verdict.

---

## PART E — Log & commit (~20 min)

Append to `notes.md` a Day 3 section:
```
## Day 3 — [date] — Football detection eval (SoccerNet_v3_H250 test split)

Eval set: SoccerNet_v3_H250 test, N=___ images sampled (seed 42), IoU=0.5, imgsz=1280.
Class mapping: model 'ball'->ball; player/goalkeeper/referee/person->person; others dropped.

Harness sanity checks: GT-as-pred -> P/R/mAP = 1.0 [pass/fail]; empty preds -> R=0 [pass/fail]; spot check [pass/fail].

### Results (ball class)
| Model    | Ball Precision | Ball Recall | Ball AP | Ball FPs | Person mAP | mAP@0.5 |
|----------|----------------|-------------|---------|----------|------------|---------|
| soccana  |                |             |         |          |            |         |
| uisikdag |                |             |         |          |            |         |
| coco     |                |             |         |          |            |         |

VERDICT: ____
Does this confirm the Day 2 eyeball call (soccana > uisikdag on precision)? ____
```
Plus observations. Then:
- Confirm `datasets/`, `*.pt`, videos all gitignored; `git status` clean of large files.
- `git add scripts/ notes.md` and any small YAML configs.
- `git commit -m "Day 3: football detection eval harness (precision/recall/mAP) on SoccerNet_v3_H250; re-ranked models on real metrics"`
- `git push`

---

## End-of-day report (developer -> planning chat)
1. ✅/❌ per Part
2. The 3 GT sample images looked correct? (y/n)
3. Harness sanity checks: did GT-as-prediction give P/R/mAP = 1.0? (this is the make-or-break trust check)
4. The final results table (ball precision/recall/AP per model)
5. VERDICT: did real metrics confirm or overturn the soccana-over-uisikdag eyeball call?
6. Any surprises (e.g. coco better/worse than expected, soccana recall lower than hoped)
7. Errors hit (even if fixed)
8. Time taken

---

## Do NOT today
- No basketball (separate session — no clean labeled set yet).
- No training/fine-tuning (evaluating pretrained only).
- No tracking work (that's after detection is trustworthy).
- Don't hand-roll metric code without running the Part C sanity checks — unvalidated metrics are worse than none.
- Don't hardcode class indices — map by name, print the mapping, have developer verify.
- Don't evaluate on train/val splits — TEST split only.
- Don't commit the dataset (it's large) or any weights/videos.
