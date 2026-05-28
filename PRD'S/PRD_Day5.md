# PRD — Day 5: Fine-Tune a Basketball Ball Detector
**Project:** AI Sports Recording & Analytics System
**Goal:** Fine-tune a YOLO ball detector on YOLOBball and test whether it beats the current basketball baseline (COCO yolov8m @1280, ball AP 0.285). Evaluate honestly with BOTH in-distribution and out-of-distribution tests to avoid the in-distribution illusion.
**Estimated time:** 3–5 hours (real training; may need a second session for tuning)
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo, `scripts/evaluate.py`, YOLOBball dataset already downloaded

---

## Context (read first)

Day 4 proved NO off-the-shelf basketball detector in our pool beats generic COCO (yolov8m @1280 = ball AP 0.285). Purpose-trained models flopped: boris-gans caught 1/1,113 balls; 446f6e6e79 AP 0.091. Football's soccana sits at ball AP 0.474 (measured out-of-distribution on SoccerNet H250). Basketball is materially behind, and the path to parity is to TRAIN our own detector — no one else has done it well for us.

This session: fine-tune on YOLOBball (11,310 train images, ball-only, already downloaded), measure against COCO baseline.

**Scope discipline:** ONE solid training run + honest eval this session. NOT an open-ended hyperparameter marathon. If the first run underperforms, that's diagnostic — we plan tuning deliberately, we don't thrash.

**Players are out of scope for this model.** YOLOBball is ball-only. Player detection is already solved (COCO/soccana do players well). Final system = dedicated ball detector (this) + separate player detector, run together. Train ball-only here.

---

## THE central trap: the in-distribution illusion

Training on YOLOBball-train and testing on YOLOBball-test will give a number that looks great (possibly 0.7+ AP) because train/test share the same source distribution. **That number does NOT mean the detector is good at basketball in general, or at DPS MIS footage.** It means it learned YOLOBball.

Football's 0.474 was measured OUT-of-distribution (soccana wasn't trained on SoccerNet H250). Comparing an in-distribution basketball number to an out-of-distribution football number is apples-to-oranges and would falsely flatter basketball.

**Therefore we report TWO numbers:**
1. **In-distribution (ID):** train YOLOBball-train, eval YOLOBball-test. Answers "did training work at all?"
2. **Out-of-distribution (OOD):** eval the SAME trained model on a DIFFERENT basketball dataset it never saw. Answers "does it generalize?" THIS is the number comparable to football's 0.474.

The ID-minus-OOD gap measures overfitting to the training distribution — itself a key finding for predicting DPS MIS deployment performance.

---

## PART A — Prep training data + acquire OOD test set (~40 min)

1. **Confirm YOLOBball structure.** It's at `datasets/yolobball/` (1.6GB, train 11,310 / valid 1,077 / test 539, 1 class `Basketball`). Confirm `data.yaml` points at the right train/valid/test paths. Confirm labels are YOLO txt.
2. **Acquire a small OOD basketball test set** — a DIFFERENT source than YOLOBball, used ONLY for testing (never training). Search Roboflow/HF/Kaggle for any basketball ball-detection set distinct from YOLOBball. Requirements: has a ball class, real footage, ~100-500 images is plenty for a test. Convert to YOLO format if needed. Save to `datasets/basketball_ood/`.
   - If a clean OOD set can't be found in ~20 min, FALLBACK: hold out a chunk of YOLOBball BY SOURCE if it has multiple source videos (a weak OOD proxy — note the limitation). Or use the user's own Day 2 4K clip with a small hand-labeled or eyeballed sample. Ask the developer.
3. Sanity-check the OOD set's GT boxes (render 3-5 samples). Confirm ball boxes sit on the ball.

**STOP. Report: YOLOBball confirmed? OOD set acquired + source + GT looks correct?**

---

## PART B — Baseline the starting point on BOTH test sets (~20 min)

Before training, establish the COCO baseline on BOTH the ID and OOD test sets using the existing harness, so we have a clean before/after:
- yolov8m COCO @1280 on YOLOBball-test (should reproduce ~0.285 ball AP from Day 4)
- yolov8m COCO @1280 on the OOD set (new number)

Record both. These are what the fine-tuned model must beat.

---

## PART C — Fine-tune (~60-90 min including training time)

1. **Starting weights:** fine-tune from `yolov8m.pt` (COCO-pretrained). Rationale: COCO pretraining already gives decent general object features and was our baseline winner; we adapt it to basketball. (yolov8s is an option if training is too slow, but start with m to match the baseline.)
2. **Training config** (`scripts/train_basketball.py` or a yolo CLI call):
   - data = YOLOBball data.yaml
   - imgsz = 1280 (match our eval resolution — critical, small ball)
   - epochs = start with 50, but ENABLE EARLY STOPPING (patience=10) so it stops when val plateaus
   - batch = auto or as large as the 4060's VRAM allows at 1280 (likely small, 4-8; if OOM, reduce batch or imgsz to 960 and note it)
   - device = 0
   - Save runs to `runs/train/bball_ft/` (gitignored)
   - Set a fixed seed for reproducibility
3. **Watch for OOM at imgsz=1280.** The 4060 laptop has limited VRAM. If it OOMs: reduce batch first, then imgsz to 960 if needed. Note whatever was used.
4. **Watch the training curves** (Ultralytics auto-logs): box loss, cls loss, and val mAP per epoch. If val mAP is still climbing at the epoch cap, note that more epochs might help. If it plateaued early, early stopping handled it.
5. Best weights save to `runs/train/bball_ft/weights/best.pt`. Copy to `models/basketball_ft.pt`.

**STOP. Report: training completed? Final val mAP from training? Any OOM/config changes? Training curve behavior (still climbing vs plateaued)?**

---

## PART D — Honest evaluation (~30 min)

Run the existing `scripts/evaluate.py` (same harness, same protocol: IoU 0.5, imgsz 1280, class-by-name) on the fine-tuned `models/basketball_ft.pt`:
1. **ID test:** on YOLOBball-test. (Note: this overlaps training distribution — expect inflated.)
2. **OOD test:** on the `basketball_ood` set. THIS is the headline, comparable to football's 0.474.

Run the harness sanity checks (GT-as-pred=1.0) on the OOD set first if not already done.

Produce a comparison:
| Model            | YOLOBball-test (ID) ball AP | OOD ball AP | OOD ball R@0.25 |
|------------------|------------------------------|-------------|------------------|
| COCO yolov8m     | 0.285 (Day 4)                | [Part B]    |                  |
| fine-tuned       | [Part D]                     | [Part D]    |                  |

**The verdict questions:**
- Did fine-tuning beat COCO on the OOD set? (the honest measure)
- How big is the ID-vs-OOD gap? (overfitting indicator)
- Where does OOD ball AP land vs football's 0.474? (parity check)

---

## PART E — Log, document considered-alternatives, commit (~30 min)

Append to `notes.md` a Day 5 section:
```
## Day 5 — [date] — Basketball ball detector fine-tuning

### Setup
- Base weights: yolov8m.pt (COCO). Train data: YOLOBball train (11,310 imgs, ball-only).
- Config: imgsz=___, epochs=___ (early stop patience 10), batch=___, seed=___. [note any OOM-driven changes]
- OOD test set: ___ (source, why it's a valid OOD set, n images).

### Baselines (COCO yolov8m @1280, before fine-tuning)
- YOLOBball-test ball AP: ___ (reproduces Day 4 0.285?)
- OOD ball AP: ___

### Fine-tuned results
| Model       | ID (YOLOBball) ball AP | OOD ball AP | OOD R@0.25 |
|-------------|------------------------|-------------|------------|
| COCO yolov8m| 0.285                  |             |            |
| fine-tuned  |                        |             |            |

- Training final val mAP: ___. Curve: [plateaued / still climbing].
- ID-vs-OOD gap: ___ (overfitting indicator).

### VERDICT
- Did fine-tuning beat COCO OOD? ___
- Parity vs football soccana (OOD ball AP 0.474)? ___
- [honest read]

### Considered alternatives (for report — architectures NOT chosen, and why)
- **BallSeg (semantic segmentation):** detects partial/occluded ball via pixel mask. Rejected for now: needs mask-labeled data; YOLOBball has only boxes. Strong future direction.
- **PIFBall (Part-Intensity-Field / keypoint):** treats ball as a center keypoint, robust to motion blur. Rejected: needs keypoint labels + reframes the whole box-based pipeline/harness. Future work.
- **Temporal LSTM tracker:** infers hidden-ball position from t-1/t+1 trajectory. Not needed as a separate model — the tractable equivalent (Kalman filter on ball trajectory) is already planned for the tracking phase. Will revisit LSTM only if Kalman proves insufficient.
- **Chosen approach:** fine-tuned single-frame YOLO detector + (later) Kalman temporal smoothing — best achievable per-frame detection from available box-labeled data, plus gap-filling at tracking time. Covers most of the occlusion/blur benefit the exotic methods promise, buildable in the timeline.

### Next steps
- [if won OOD] fine-tuned model becomes models/basketball.pt for downstream.
- [if lost/marginal] diagnose: more epochs? higher res? augmentation? or accept and document.
- Players: dedicated player detector (COCO/soccana-style) to be combined with this ball detector at integration.
```
Then: confirm `runs/`, `datasets/`, `*.pt`, videos all gitignored; `git status` clean; commit scripts + notes:
`git commit -m "Day 5: fine-tuned basketball ball detector on YOLOBball; ID+OOD eval; considered-alternatives documented"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. OOD set used + why it's a valid out-of-distribution test
3. Training: completed? final val mAP? any OOM/config changes? curve plateaued or climbing?
4. Harness sanity check on OOD labels: GT-as-pred = 1.0?
5. The results table (ID + OOD ball AP, fine-tuned vs COCO)
6. VERDICT: beat COCO OOD? ID-vs-OOD gap? parity vs football 0.474?
7. Errors hit (even if fixed)
8. Time taken

---

## Do NOT today
- Don't report ONLY the in-distribution (YOLOBball-test) number — it's flattering and misleading alone. The OOD number is the headline.
- Don't open-ended hyperparameter-thrash — ONE solid run this session; plan tuning deliberately if needed.
- Don't train on the OOD set — it's test-only, forever. Training on it destroys its purpose.
- Don't try BallSeg/PIFBall/LSTM today — documented as considered alternatives, not built.
- Don't add players to this model — ball-only; players come from a separate detector at integration.
- Don't trust the OOD number until GT-as-pred=1.0 passes on the OOD labels.
- Don't commit datasets, runs/, weights, or videos.
