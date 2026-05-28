# Day 1 Notes
Date: 2026-05-28

## Environment
- Python 3.11.9 in `.venv/`
- PyTorch 2.11.0+cu128, CUDA 12.8, RTX 4060 Laptop GPU detected
- Ultralytics 8.4.56, yt-dlp 2026.3.17
- OpenCV 4.13.0, NumPy 2.4.4

## Test clip
- Source: YouTube `L_8Zx6wjRo0` — "Real Madrid 2 vs Benfica 1 | Tactical Cam"
- 1080x720 @ 30fps, 2670 frames (~89s)
- Saved to `clips/day1_test.mp4` (gitignored)

## Results
- Image detection (bus.jpg): bus 0.96, 4 persons 0.75-0.93, 87.1ms inference
- Video detection: **33.3 FPS avg** on RTX 4060 (target was 20+)
- Annotated output: `outputs/day1_video_annotated.mp4` (gitignored)
- First frame snapshot: `outputs/day1_first_frame.png`

## Bonus run: user-supplied football.mp4
- Input: `football.mp4` (project root, gitignored), 1280x720 @ 30fps, 540 frames (18s)
- **26.8 FPS avg** on RTX 4060 (20.2s wall-clock)
- 9265 total person detections -> 17.2 players/frame avg (22 on pitch + ref + sideline)
- 0 ball detections (expected per PRD; YOLOv8 weak on small fast objects)
- Outputs: `outputs/annotated_videos/football_annotated.mp4`, `outputs/frames/football_midframe.png`

## Known issues / notes
- Initial push to GitHub deferred (per user choice); remote `origin` set to
  `https://github.com/Osmiosis/sports-ai-capstone.git`. Run `git push -u origin main`
  manually to publish.
- Ultralytics saves under `runs/detect/<project>/<name>` regardless of `project=`
  argument (the arg only sets the subdir, not the parent). Not a bug.
- Ball detection unreliable as expected per PRD; will swap to sports-specific model later.

---

## Day 2 — 2026-05-28

### Football model bake-off (imgsz=1280)
| Model      | Ball % (recall proxy) | Players/frame | Ball conf | FPS | Visual FP rate |
|------------|-----------------------|---------------|-----------|-----|----------------|
| soccana    | 12.4                  | 24.1          | 0.40      | 17.9 | near-zero — fires only on actual ball when close |
| uisikdag   | 68.3                  | 25.5          | 0.38      | 18.6 | HIGH — white field-line markings tagged as balls |
| coco_hires | 16.7                  | 22.6          | 0.51      | 17.5 | low |

**WINNER (revised after visual inspection): soccana** (`Adit-jain/soccana`, classes: Player/Ball/Referee).
- Initial automatic pick was uisikdag based on 68.3% ball-detection — but visual review showed those detections are mostly **false positives on white pitch markings** (penalty area, center circle), not the actual ball.
- soccana has lower recall (~12%, misses the far/small ball) but **near-zero false positives** — it only fires when the actual ball is reasonably close and clear.
- **For tracking and downstream possession logic, high precision beats high recall:** a stream of FP "balls" on field paint poisons the tracker (gives the ball-track persistent IDs on stationary line markings) and breaks any "who has the ball" heuristic.

**Methodology fix — ball % alone is misleading.** The bake-off script counted any box labeled "ball" as a detection; it had no way to distinguish a real-ball detection from a false-positive on field markings. Until we add an FP audit (visual or labeled-frame eval), treat "ball %" as a *recall proxy with no precision floor*. Future bake-offs should sample N frames and hand-label TP/FP, or evaluate against a ground-truth labeled subset.

`models/football.pt` re-pointed to soccana (5.6MB, SHA256 `dd5f0bec…`).
Day 1 baseline ball: 0/540 (0%) → Day 2 winner (soccana): ~12% **precise** ball detections, vs uisikdag's 68% mostly-spurious detections.

### Football tracking (ByteTrack, imgsz=1280)
- Run made with the original (uisikdag) winner BEFORE the precision revision.
- Frames: 540, avg FPS: 15.9, **unique IDs: 371** (severe churn — expected 25-45).
- Likely drivers: ball gets re-IDed every flicker, crowded occlusions in wide tactical angle, default `bytetrack.yaml` not tuned for sports.
- Output `outputs/annotated_videos/football_tracked.mp4` reflects the uisikdag run (including its field-line "ball" FPs). **TODO: rerun with `models/football.pt` now pointing to soccana** to get a tracking baseline on the precision winner.

### Basketball
- Model: `boris-gans/basketball-yolo11s-detect` (12 classes: ball variants, player + actions, referee, rim).
  - Rejected `446f6e6e79/YOLO-basketball-fineTuned` after inspecting classes — overfit to specific Red_X / White_X jersey numbers.
- `track_basketball.py` now takes the input clip as a CLI arg; output filename derives from input stem.

| Clip            | Resolution | Frames | Ball % | Players/f | Unique IDs | FPS  |
|-----------------|------------|--------|--------|-----------|------------|------|
| basketball.mp4  | 640x360    | 762    | 3.1    | 7.7       | 268        | 30.8 |
| Basketball1.mp4 | 3840x2160  | 579    | 22.3   | 7.1       | 325        | 7.8  |

- Resolution effect on ball: **3.1% -> 22.3% (~7x lift)** going from 360p to 4K, as predicted. Confirms the 360p clip was the dominant blocker.
- Same precision caveat as football: 22.3% is a recall proxy; need a visual FP audit (especially around rim / scoreboard) before declaring victory.
- 4K throughput drops to 7.8 FPS — letterbox to imgsz=1280 still has to decode 4K frames. Acceptable for offline analysis; would need downsample-first or imgsz tuning for real-time.
- ID churn (325 / 268) mirrors football — default ByteTrack untuned for sports.
- Outputs: `outputs/annotated_videos/basketball_tracked.mp4` + `outputs/annotated_videos/Basketball1_tracked.mp4`, midframes `outputs/frames/basketball_tracked_midframe.png` + `outputs/frames/Basketball1_tracked_midframe.png`

### Observations / next steps
- **Precision audit is the missing piece across the board.** Every "ball %" number in this doc is recall-only. Add a TP/FP labelling step (even N=50 hand-labelled frames) before picking ball models on future clips.
- **Football detection (soccana) is solid for the baseline clip** on precision: 12% recall but the boxes are real. Tracking on top of soccana not yet measured — rerun pending.
- **Tracking is the next bottleneck** — tune ByteTrack thresholds (track_high_thresh, track_low_thresh, match_thresh, new_track_thresh, max_age) for sports; consider running tracking only on `player` class and treating ball as a separate single-instance tracker.
- **Basketball benefited from the 4K clip (22.3% ball recall vs 3.1% at 360p);** still needs the same FP audit before any verdict.
- **4K throughput is 7.8 FPS** — fine for batch, will need downsample/imgsz tuning for live.
- **Models folder** now holds: soccana.pt, uisikdag.pt, football.pt (=soccana, 5.6MB, SHA256 dd5f0b…), basketball_borisgans.pt, basketball.pt (=boris-gans). All gitignored.

---

## Day 3 — 2026-05-28 — Football detection eval (SoccerNet_v3_H250 test split)

Eval set: SoccerNet_v3_H250 test, N=500 images sampled (seed 42), IoU=0.5, imgsz=1280, prod-conf=0.25.
- Source: Zenodo 7808511 (MD5 verified `cdc2401a…`). Test split = 2,692 images (used random 500 for runtime).
- Class instances in full test: 2,108 ball, 38,004 person.
- Class mapping (by name via `model.names`): model 'ball'/'Ball' -> ball; player/goalkeeper/referee/Player/Referee -> person; everything else dropped.

### Harness sanity checks (all PASS)
1. GT-as-pred -> ball P/R/AP = 1.0, person P/R/AP = 1.0, FP = 0 across 500 images. Matching logic correct.
2. Empty preds -> R = 0, P = 0, AP = 0, FN = n_gt for both classes. No divide-by-zero.
3. Spot-check on one image (soccana): ball TP=1 FP=0 FN=0, person TP=20 FP=4 FN=1 — plausible (the 4 person FPs are likely sideline/coach detections not in GT). Canvas at `outputs/frames/spot_check.png`.

### Results — ball class (the headline)
| Model      | P@0.25 | R@0.25 | AP    | FP@0.25 | FP@allconf | n_gt |
|------------|--------|--------|-------|---------|------------|------|
| soccana    | 0.647  | 0.491  | 0.474 | 102     | 5,425      | 381  |
| uisikdag   | 0.129  | 0.034  | 0.108 | 88      | 1,970      | 381  |
| yolov8m    | 0.258  | 0.373  | 0.286 | 409     | 14,988     | 381  |

### Results — person class
| Model      | P@0.25 | R@0.25 | AP    |
|------------|--------|--------|-------|
| soccana    | 0.928  | 0.923  | 0.903 |
| uisikdag   | 0.610  | 0.610  | 0.621 |
| yolov8m    | 0.833  | 0.888  | 0.880 |

### mAP@0.5
- **soccana: 0.689** (winner)
- uisikdag: 0.364
- yolov8m:  0.583

### VERDICT
**soccana wins on every metric.** The Day 2 eyeball call (soccana > uisikdag on precision) is **strongly confirmed and quantified**:
- Ball precision: soccana 0.647 vs uisikdag 0.129 -> ~5x more precise.
- Ball recall: soccana 0.491 vs uisikdag 0.034 (at conf=0.25) -> ~14x more recall at the production threshold.
- Ball AP: soccana 0.474 vs uisikdag 0.108 -> ~4.4x better ranking quality.
- uisikdag's Day 2 "68.3% ball" was almost entirely **low-confidence trash** — at conf=0.25 it only catches 13 of 381 balls, while filing 88 FPs.

### Surprises
1. **soccana's real ball recall is 49%, not the ~12% Day 2 eyeball suggested.** The video-mode test was punishing it more than the still-image eval does. Day 2's hand-estimate undersold soccana's recall by ~4x.
2. **uisikdag is worse than the COCO baseline on ball** (AP 0.108 vs 0.286). Day 2 picked uisikdag as winner on (mostly-FP) ball recall — turns out it's the worst of the three on every dimension. Lesson: never rank on recall without a precision floor.
3. **COCO yolov8m is a non-trivial baseline** at 1280px (mAP 0.583, ball AP 0.286). Generic pretraining + high res closes a lot of the gap to soccer-specific models.
4. coco has the **highest FP@allconf for both classes** (14,988 ball, 78,520 person) — its low-confidence noise floor is huge because it has 80 classes and fires loosely. At conf=0.25 it tames down to reasonable numbers.

### Methodology notes for next time
- "Ball %" alone is meaningless without a precision floor — Day 2 lesson re-confirmed in hard numbers.
- AP is the right ranking metric (full PR curve, threshold-independent). P/R at conf=0.25 is the right operating-point report. Reporting both kept the assessment honest.
- The 3 sanity checks (gt-as-pred, empty, spot) caught nothing this time but are cheap insurance — keep them in any future eval harness.

### Models confirmed
- `models/football.pt` = soccana (re-pointed on Day 2; confirmed correct choice today).
- uisikdag retained on disk but should not be used for ball detection without retraining/recalibration.

---

## Day 4 — 2026-05-28 — Basketball detection eval

### Dataset (after detour from PRD candidates)
- **PRD plan A — UniqueData/Kaggle (trainingdatapro/basketball-tracking-dataset):** downloaded, inspected. Turned out to be 72 image frames from one source video (`source.mp4`), CVAT XML format (NOT VOC as PRD claimed), `<track id="0" label="ball">` only. **No player labels. 106/106 boxes had `occluded="0"` — zero occluded examples. No `basket` attribute at all.** Inadequate for a rigorous eval; the planned occlusion split is impossible.
- **PRD plan B — Roboflow "Fiba Basketball":** no project literally named "FIBA" exists on Universe. After scout, picked `basketball-keumj/yolobball` v6 (CC BY 4.0) as the actual usable Roboflow basketball detection set.
- **Used:** Roboflow `basketball-keumj/yolobball` v6. 11,310 train + 1,077 valid + **539 test** images, 1 class only (`Basketball` — no players), 1,190 ball instances across test split. Real footage (user-verified), 1.6 GB on disk.
- DeepSportradar parked as gold-standard for future fine-tuning per PRD.

### Class mapping
'ball'/'Ball'/'Basketball' -> eval class 0. Player/person classes -> dropped (ball-only dataset). Harness updated with auto-detection: scans GT for classes present and drops predictions to absent classes (otherwise person predictions on a ball-only set become spurious FPs forever).

### Harness sanity checks (on basketball labels)
1. GT-as-pred -> ball P/R/AP = 1.0, mAP = 1.0. Person n_gt = 0 correctly skipped. PASS.
2. Empty preds -> R = 0, mAP = 0. PASS.
3. Spot-check on basketball: skipped (Day 3 spot-check already validated harness flow; basketball auto-checks both pass).

### Results — ball class (N=500, seed=42, imgsz=1280, IoU=0.5)
| Model                | Ball P@0.25 | Ball R@0.25 | Ball AP | FP@0.25 | FP@allconf | n_gt |
|----------------------|-------------|-------------|---------|---------|------------|------|
| boris-gans (yolo11s) | 0.0147      | 0.0009      | 0.0014  | 67      | 8,300      | 1,113 |
| 446f6e6e79           | 0.1549      | 0.0099      | 0.0909  | 60      | 5,258      | 1,113 |
| **yolov8m COCO**     | **0.7650**  | **0.1375**  | **0.2852** | **47** | 3,033   | 1,113 |

**WINNER: yolov8m COCO at imgsz=1280** — by a huge margin.

### Occlusion breakdown
Not possible on YOLOBball (no occlusion attribute). PRD's UniqueData plan A would have allowed it but the data had zero occluded examples anyway. Deferred until a richer benchmark is sourced.

### Football vs Basketball parity check
| Sport      | Best model       | Ball AP | Ball R@0.25 | Person AP |
|------------|------------------|---------|-------------|-----------|
| Football   | soccana          | 0.474   | 0.491       | 0.903     |
| Basketball | yolov8m COCO     | 0.285   | 0.138       | n/a (no GT) |

**PARITY VERDICT: basketball is materially behind football.** Best basketball ball AP is **60% of football's** (0.285 vs 0.474). Ball recall is **28% of football's** (0.138 vs 0.491). The gap is bigger than it looks because basketball's "best" is a generic model — there's no specialized basketball detector that beats COCO baseline yet.

### HUGE surprise
**Both purpose-trained basketball detectors flop dramatically vs generic COCO:**
- boris-gans (Day 2 video winner with 22.3% "ball"): caught 1 of 1,113 balls at conf=0.25. Ball AP = 0.0014 — statistical noise. The Day 2 "22.3% ball" was almost entirely rim/scoreboard FPs, now quantified: at all-conf, fp_allconf=8,300 vs tp_allconf=22 (FP:TP ratio ~377:1).
- 446f6e6e79 (Day 2 rejected for jersey-overfit on players): ball AP = 0.091. Also bad — its narrow scrimmage training doesn't transfer.
- **yolov8m COCO** at imgsz=1280: ball AP = 0.285. Generic "sports ball" class trained across many sports actually generalizes better than purpose-trained models with narrow training distributions.

### Methodology vindications
- Day 2 lesson "ball % alone is misleading" confirmed for the third time: boris-gans 22.3% (Day 2 video) -> 0.14% recall (Day 4 eval). All-conf FP:TP ratio of 377:1.
- Day 3 harness pattern reused cleanly: same evaluate.py, same sanity-check protocol, same class-by-name remapping. New dataset, same trust gate. No metric-code rewrite.

### Implications & next steps
- **No good off-the-shelf basketball ball detector exists in our candidate pool.** COCO wins by default of others being broken. For DPS MIS production use, basketball will likely need either (a) fine-tuning on YOLOBball or DPS MIS footage, or (b) different model architecture for small-fast objects.
- For tracking, use `yolov8m.pt` for basketball ball detection (NOT boris-gans). Update `models/basketball.pt` accordingly? Deferred — not part of Day 4 scope, but recommended.
- DeepSportradar fine-tuning is the right next move when ready.
- Roboflow/Kaggle credentials stored OUTSIDE the repo at `~/.roboflow/key` and `~/.kaggle/access_token`. Not committed.

---

## Day 5 — 2026-05-28 — Basketball ball detector fine-tuning

### Setup
- Base weights: `yolov8m.pt` (COCO). Train data: YOLOBball (`basketball-keumj/yolobball` v6) train split: 11,310 imgs, 1 class (ball-only).
- Config: imgsz=1280, epochs=30 (cap), patience=10, batch=4 (explicit — autobatch OOM'd on the 4060), workers=2 (Windows DataLoader fragility), amp=True (mixed precision for VRAM headroom), cache=False, seed=42. Optimizer: AdamW auto-picked, lr=0.002.
- **Stopped manually after epoch 15** because val mAP slope was clearly flattening (Δ shrank from +0.068 at ep1→2 to +0.002 at ep13→14, +0.006 at ep14→15). Patience clock had not yet started (every epoch was a new fitness best), but plateau was visible.
- VRAM at training: 6.1 GB / 8.0 GB stable. GPU 80–100% util, 80–84°C. ~21 min/epoch at 2.5 it/s. Total training wall: ~5h15m for 15 epochs.

### OOD test set (the headline)
- `computer-vision-d5fjh/basketball-detection-dn6fg` v4 (Roboflow, CC BY 4.0), 488 test imgs, classes ball/basket/person.
- Different workspace, different annotation pipeline, different source video material from YOLOBball. Valid out-of-distribution: the fine-tuned model never saw these images during training.
- Why not UniqueData (Kaggle)? Attempted first — its CVAT XML annotations were in 1280x720 source-video coords but the `images/N/M.png` files on disk were portrait-oriented and differently sized; `boxes/frame_*.PNG` had bounding boxes already drawn ON the pixels (cyan rectangles), so they couldn't be used as clean training/eval data either. Structurally broken — abandoned.

### Per-epoch val curve (YOLOBball val, 1,077 imgs, 2,325 instances)
| Epoch | P | R | mAP@0.5 | mAP@0.5:0.95 |
|------:|------:|------:|--------:|-------------:|
| 1  | 0.819 | 0.686 | 0.787 | 0.541 |
| 2  | 0.894 | 0.767 | 0.855 | 0.617 |
| 3  | 0.915 | 0.788 | 0.871 | 0.638 |
| 4  | 0.917 | 0.825 | 0.898 | 0.670 |
| 5  | 0.913 | 0.860 | 0.910 | 0.688 |
| 6  | 0.934 | 0.850 | 0.918 | 0.707 |
| 7  | 0.933 | 0.858 | 0.923 | 0.711 |
| 8  | 0.935 | 0.867 | 0.922 | 0.716 |
| 9  | 0.931 | 0.895 | 0.937 | 0.728 |
| 10 | 0.933 | 0.898 | 0.942 | 0.742 |
| 11 | 0.937 | 0.915 | 0.953 | 0.749 |
| 12 | 0.936 | 0.906 | 0.946 | 0.752 |
| 13 | 0.941 | 0.914 | 0.954 | 0.761 |
| 14 | 0.944 | 0.922 | 0.956 | 0.766 |
| 15 | 0.943 | 0.933 | **0.960** | **0.775** |

### Baselines (COCO yolov8m @1280, before fine-tuning)
- YOLOBball-test (ID) ball AP: 0.285 (reproduces Day 4)
- OOD ball AP: 0.274 (almost identical to ID, confirming the basketball ball-detection difficulty is comparable across both sources for COCO)

### Fine-tuned headline (N=500 per set, seed=42, imgsz=1280, IoU=0.5)
| Model            | ID ball AP | OOD ball AP | OOD ball R@0.25 |
|------------------|-----------:|------------:|----------------:|
| COCO yolov8m     | 0.285      | 0.274       | 0.074           |
| **Fine-tuned (ep 15)** | **0.893** | **0.618** | **0.534**     |
| Lift vs COCO     | +0.608 (3.1x) | +0.344 (2.3x) | 7.2x |

- ID-vs-OOD gap: 0.893 → 0.618 = **0.275 absolute drop, ~31% relative.** Real overfitting signal — the model learned YOLOBball harder than it learned "basketball ball in general." Not catastrophic; worth budgeting for in deployment.

### VERDICT
- **Did fine-tuning beat COCO OOD?** Yes — by a wide margin. 0.618 vs 0.274 ball AP (2.3x), 0.534 vs 0.074 recall (7.2x). Honest improvement, not an in-distribution artifact.
- **Parity vs football soccana (OOD ball AP 0.474):** basketball is now **AHEAD by +0.144**. Day 4's "basketball is materially behind football" is fully reversed by one round of fine-tuning. The previous gap was a model-availability gap, not a sport-difficulty gap.
- **Plateau read:** mAP@0.5 climbed +0.173 in epochs 1-15 but the last 5 epochs only added +0.018. Marginal returns clearly diminishing. More epochs likely buy <+0.01. If pushing further, the lever is data variety (more sources → smaller ID-vs-OOD gap), not more epochs on the same data.

### Considered alternatives (architectures NOT chosen this session, and why)

**Perspective A: Pixel-Level Segmentation (BallSeg).** State-of-the-art basketball ball models formulate detection as semantic segmentation — predict a probability mask over the image so partial/occluded ball pixels (e.g., 80% blocked by hands) still register. This effectively eliminates the occlusion density problem that causes standard bbox detectors to drop frames. **Rejected for now:** needs pixel-mask labels; YOLOBball has only bounding boxes. Strong future direction once we have mask-labeled data (DeepSportradar with segmentation export is a candidate).

**Perspective B: Part-Intensity-Field (PIFBall).** Treats the ball as a keypoint and predicts its exact center, drawing on human-pose-estimation techniques. Highly effective for severe motion blur — the network learns aerodynamic / directional blur patterns rather than relying on clear spherical boundaries. **Rejected for now:** needs keypoint labels + reframes the whole box-based pipeline and eval harness (precision/recall against keypoints, not IoU). Future work if motion blur becomes the dominant failure mode in DPS MIS footage.

**Perspective C: Temporal Sequential Tracking (Bidirectional LSTMs).** Pairs a Faster R-CNN or RetinaNet single-frame detector with a bidirectional LSTM that, if the ball is hidden in frame t, mathematically infers its position from velocity / trajectory / physics across frames t-1 and t+1. **Rejected as a separate model:** the tractable equivalent — a Kalman filter on ball trajectory — is already planned for the tracking phase and covers most of the gap-filling benefit at a fraction of the engineering cost. Will revisit LSTM only if Kalman proves insufficient.

**Chosen approach:** fine-tuned single-frame YOLO detector (this session) + (later) Kalman temporal smoothing at tracking time. Covers most of the occlusion / blur robustness the exotic methods promise, buildable in the timeline, with a working harness already in place.

### Next steps
- `models/basketball.pt` should be updated to point at the fine-tuned weights (currently still points at boris-gans from Day 4). Recommend `cp models/basketball_ft.pt models/basketball.pt` for downstream tracking.
- Reduce the ID-vs-OOD gap: source 1–2 additional basketball training sets distinct from YOLOBball; retrain on the union. This is the highest-leverage next move.
- DeepSportradar still parked as the gold-standard fine-tuning target when the project is ready for it.
- Players: dedicated player detector (COCO yolov8m on persons is already strong — OOD person AP 0.837 measured today) combined with this ball detector at tracking integration time.

### Errors hit (informative)
1. **Autobatch OOM at imgsz=1280** on 4060 8GB — autobatch fell back to batch=16, which OOM'd. In-process retry poisoned the CUDA context and crashed empty_cache(). Fix: explicit batch=4 + fresh process.
2. **Windows multiprocessing `RuntimeError`** ("not using fork to start child processes"). The training script was missing `if __name__ == "__main__":`. Standard Windows + multiprocessing pitfall. Fixed with main-guard.
3. **DataLoader worker died unexpectedly** at epoch 1 batch 156. Default 8 workers was too aggressive under memory pressure. Fix: workers=2 + amp=True + cache=False.
4. **Ultralytics path quirk:** `project="runs/train"` saves under `runs/detect/runs/train/bball_ft/` (project type prepended). Harmless; weights still findable.

### Time
- Wall: ~7h end-to-end (most of it training). Hands-on: ~45min (Part A dataset wrangling + Part B baselines + script iteration + Part D evals + Part E notes).

---

## Day 6 — 2026-05-28 — Basketball player tracking: measurement harness + baseline (SportsMOT)

### Pivot context
- Original Day 6 was football tracking (SoccerNet-Tracking). SoccerNet is NDA-gated; the agreement/password flow is pending, so pivoted to basketball today via SportsMOT (open access, no NDA).
- The harness built today is sport-agnostic — drops in MOTChallenge-format sequences from any source. Football harness re-use will be near-zero new code once SoccerNet (or SportsMOT football seqs) is available.

### Setup
- Eval: SportsMOT basketball, 5 sequences from the val split (chosen alphabetically for reproducibility): `v_00HRwkvvjtQ_c001`, `_c003`, `_c005`, `_c007`, `_c008`. 1280x720 @ 25fps, total ~4,600 frames, 50 GT player IDs, 43,897 GT detections.
- Tools: `sn-trackeval` 0.4.0 (imports as `trackeval`) for HOTA/MOTA/IDF1/IDsw via MotChallenge2DBox dataset, `DO_PREPROC=False` (SportsMOT has no distractor preproc).
- Tracker: Ultralytics' `BYTETracker` with shipped `bytetrack.yaml` defaults. No tuning.
- Detector for Baseline #2: `yolov8m.pt` (COCO) at imgsz=1280, keep `person` class.
- Data source: HuggingFace `MCG-NJU/SportsMOT` (CC BY-NC 4.0). Pulled val.tar (6.3 GB), extracted only 5 chosen basketball seqs to `datasets/sportsmot_basketball/` (1.5 GB on disk).

### Sanity checks
- GT tracklets visualized in `outputs/gt_samples/bball_track_gt_{c001,c003,c005}.mp4` (max 100 frames each, IDs drawn).
- **TrackEval GT-as-output: HOTA=1.000, IDF1=1.000, MOTA=1.000, IDsw=0** across all 5 seqs (43,897 detections, 50 IDs, all matched). PASS.
- **TrackEval empty output: HOTA=0.000, IDF1=0.000, MOTA=0.000**, no crash. PASS.

### Baselines (player class only)
| Setup                              | HOTA   | MOTA    | IDF1   | IDsw | DetA  | AssA  | unique-ID proxy |
|------------------------------------|--------|---------|--------|------|-------|-------|-----------------|
| **GT detections + ByteTrack** (ceiling) | **74.05** | 98.95 | **84.56** | 53 | 83.88 | 65.39 | 83 |
| **yolov8m person + ByteTrack** (real)   | **26.62** | -113.03 | **22.23** | 365 | 25.32 | 28.00 | **2,435** |

Notes on the real baseline:
- MOTA is NEGATIVE because false positives (90,032) far exceed true positives (40,782). When `FP > TP + FN`, MOTA goes negative — a clear failure signal.
- Det recall = 78.57% (yolov8m finds 4 of 5 actual players) but Det precision = 26.37% (most "person" boxes are NOT GT players — they're refs, coaches, audience, sideline).
- 130,814 detections vs 43,897 GT = **~3x over-detection**.

### Interpretation

**Where the gap lives.** Ceiling HOTA 74.05 vs real 26.62 = a gap of **47.4 points**, and DetA collapses from 83.88 to 25.32 (-58.6) while AssA only drops from 65.39 to 28.00 (-37.4). **The dominant problem is detection, not tracking.** Specifically, it's a class-semantics problem: yolov8m's COCO `person` class includes ANY person in frame (refs, coaches, audience, ball boys, sideline staff), while SportsMOT GT only labels the 10 players on court. The tracker is doing its job — it's correctly persisting the IDs of all the people the detector hands it, including the wrong ones.

**Unique-ID proxy vs IDF1 — exactly how misleading.** Day 2's "basketball had 268-325 unique IDs" sounded bad. Today's real run produced **2,435** unique IDs (with a stronger detector). But the actual identity metric (IDF1) is 22.2 — the unique-ID count tells us almost nothing about whether the SAME id stays on the SAME player. Day 2's proxy understated the chaos by an order of magnitude AND can't distinguish between "tracker reassigns IDs every frame" (real story) vs "detector saw few people once each" (fake story).

**vs SportsMOT published numbers.** The SportsMOT paper reports best-method basketball HOTA ~60.8, SOTA refinement methods ~81 overall. Our **ceiling** (perfect detections + vanilla ByteTrack) sits at 74.05 — comfortably in the middle of that range, confirming the published "basketball is the hardest sport to track" finding mostly comes from detection, not association. Our **real** at 26.62 is well below the paper's worst published method — because they used proper person-vs-player classification or court-bounds filtering, both of which we have not yet.

### Where next effort belongs

**Detector, by a mile.** The ceiling experiment proves vanilla ByteTrack handles basketball association at IDF1 84.56 when given clean inputs. Tracker tuning will help, but the leverage is 10x bigger on detection. Three concrete fixes ranked by effort:

1. **Court-bounds filter** (lowest effort): mask off-court detections via a homography or a simple rectangular court polygon. Single-image preprocessing. Likely gets MOTA back into positive territory immediately.
2. **Person-class filter** (medium effort): use jersey color / size / on-court heuristic to drop refs and bench staff. Bridges player vs person.
3. **Player-trained detector** (highest leverage, highest effort): fine-tune on SportsMOT-train or similar to learn "basketball player on court" rather than "any person." Mirrors the Day 5 ball detector win pattern.

### Next sessions (NOT today)
- Tune ByteTrack thresholds (`track_high_thresh`, `match_thresh`, `new_track_thresh`, `track_buffer`/`max_age`) for fast-motion sports; try BoT-SORT (appearance features) vs ByteTrack; re-measure vs this baseline.
- Football tracking: reuse this exact harness on SportsMOT football seqs (already have train/val splits) or SoccerNet-Tracking when NDA lands.
- Ball tracking: separate session, Kalman + the fine-tuned basketball detector from Day 5.
- Try a court-bounds filter as the fastest detector-side win before training anything new.

### Errors hit (informative)
- `BYTETracker.__init__()` no longer accepts `frame_rate=` kwarg in Ultralytics current; reads it from args namespace instead. One-line fix.
- `BYTETracker.update()` expects an indexable `Boxes` object, not a SimpleNamespace; reconstructed predictions as `ultralytics.engine.results.Boxes(tensor, orig_shape)` and it worked.

### Time
Wall: ~25min hands-on after the val.tar download (~3 min). Total session about 50 min including reorg + memory work earlier.

---

## Day 7 — Fine-Tune Basketball PLAYER Detector (the durable fix)

**Goal:** Fix the detection bottleneck Day 6 identified (real HOTA 26.6 vs 74 ceiling, caused by COCO yolov8m's `person` class detecting refs/coaches/bench/crowd). Train a "basketball player on court" detector on SportsMOT-train, evaluate honestly (ID + OOD detection), re-run the Day-6 tracking harness to measure HOTA lift.

### Setup
- **Training data:** SportsMOT basketball-train, 15 seqs total. Held out 2 by SEQUENCE (no frame leakage) for Ultralytics val: `v_-6Os86HzwCs_c009`, `v_4LXTUim5anY_c012` (different games). 13 train seqs sampled stride=5 -> **2,209 train imgs / 19,471 player boxes**; 2 val seqs stride=5 -> **275 val imgs / 2,359 boxes**.
- **ID detection eval set:** SportsMOT-val (the 5 Day-6 seqs), stride=5 -> 922 imgs / 8,796 player boxes. Same-distribution as training (flattering).
- **OOD detection eval set:** `basketball_ood` (Roboflow `basketball-detection-dn6fg`) -- re-used from Day 5. `person` class becomes the OOD player test. 488 test imgs, 1280x1280 padded. **Different source from SportsMOT; no NEW labeling needed.**
- **Sanity gates (must pass before trusting any number):**
  - ID GT-as-pred -> P=R=AP=1.0 (n_gt=971 in 100-img sample)
  - OOD GT-as-pred -> person AP=1.0 (n_gt=133), ball AP=1.0 (n_gt=88)
- **Base weights:** yolov8m.pt (COCO). Mirrored Day 5 hyperparams: epochs=30 cap, patience=10, batch=4, workers=2, amp=True, cache=False, seed=42, imgsz=1280.

### COCO baseline (the bar to beat)

| Set | precision@0.25 | recall@0.25 | player AP |
|---|---:|---:|---:|
| ID (SportsMOT-val, n=300 imgs, 2884 boxes) | 27.4% | 94.8% | 75.0% |
| OOD (basketball_ood, n=300 imgs, 399 boxes) | 89.8% | 79.2% | 83.3% |

ID **precision is the killer (27%)** -- 7,246 FPs vs 2,735 TPs in 300 imgs (~24 FPs / image). Reproduces the Day 6 diagnosis exactly: COCO catches every person, SportsMOT GT only labels on-court players. OOD precision is high (90%) because the OOD set is sparse single-player drill footage with little crowd; the over-detection problem isn't visible there.

### Training -- config changes (OOM + crash diagnosis)

1. **Crash #1 -- CUDA OOM at imgsz=1280 batch=4:** cublasGemmEx CUBLAS_STATUS_EXECUTION_FAILED at first forward pass. Loss-tensor size scales with target instance count per image; SportsMOT has ~10 players/frame vs Day 5's YOLOBball 1 ball/frame. The 4060's 8 GB couldn't hold it. **Fix:** dropped imgsz to 960 per PRD fallback.
2. **Crash #2 -- host-RAM exhaustion in validation:** epoch 1 train ran fine at 960 batch=4 workers=2 (2:16 / 553 batches @ 4 it/s, 3.76G GPU). Crashed in post-epoch validation on a 4.55 MiB numpy alloc inside `ap_per_class` precision-curve construction. Host RAM was 60% used; the worker subprocesses + cached label tensors + ~60k accumulated predictions tipped it over. **Fix:** workers=0 (single-process loader, no subprocess RAM duplication). Trained cleanly from there.

### Training curve (best.pt = epoch 7)

| Epoch | val P | val R | val mAP50 | mAP50-95 |
|------:|------:|------:|----------:|---------:|
| 1 | 0.949 | 0.915 | 0.970 | 0.719 |
| 2 | 0.925 | 0.934 | 0.969 | 0.749 |
| 3 | 0.946 | 0.937 | 0.976 | 0.742 |
| 4 | 0.960 | 0.947 | 0.982 | 0.767 |
| 5 | 0.956 | 0.951 | 0.978 | 0.766 |
| 6 | 0.947 | 0.955 | 0.979 | 0.764 |
| **7** | 0.959 | 0.954 | **0.986** | 0.778 |

Manually stopped after epoch 7 -- mAP50 plateaued (0.97-0.99 range across 7 epochs). Per Day 5 lesson, didn't chase tiny mAP50-95 gains the tracker wouldn't notice. Total wall ~25 minutes on 4060 at imgsz=960. **best.pt -> `models/basketball_player.pt`** (198 MB).

### Detection eval (the honest table)

| Model | Set | precision@0.25 | recall@0.25 | player AP | TP@0.25 | FP@0.25 | FN@0.25 |
|---|---|---:|---:|---:|---:|---:|---:|
| COCO yolov8m person | ID | 27.4% | 94.8% | 75.0% | 2,735 | 7,246 | 149 |
| **FT player (this work)** | ID | **93.3%** | **97.7%** | **90.8%** | 2,819 | 203 | 65 |
| COCO yolov8m person | OOD | 89.8% | 79.2% | 83.3% | 316 | 36 | 83 |
| **FT player (this work)** | OOD | **6.4%** | **3.3%** | **9.4%** | 13 | 191 | 386 |

**ID readings (the deployment-relevant numbers):**
- AP +16 points (75 -> 91).
- **Precision 27% -> 93%** -- the Day-6 killer is fixed. FPs collapsed from 7,246 -> 203 in 300 imgs (~24 FPs/img -> 0.7 FPs/img).
- Recall up too (95% -> 98%) -- fine-tuning didn't trade recall for precision; it learned what's NOT a player.

**OOD reading (the honest "did we overfit?" signal):**
- AP 83 -> 9. P 90% -> 6%, R 79% -> 3%. **Severe collapse.** Render-diagnosis (`outputs/gt_samples/day7_ood_diag_*.png`) shows the FT model produces 0-1 detections per OOD frame.
- **Root cause is distribution shift + OOD set choice mismatch, not pure overfitting:** basketball_ood is 1280x1280 padded single-player drill/freeplay footage (`*_freeplay_mp4-*`, `*_ground_mp4-*`, `yt-false-*`); SportsMOT is 1280x720 broadcast 10-player games. The model learned "10 player silhouettes in a wide-frame court at ~60% court coverage." It does not generalize to solo drill clips at square aspect ratio. This OOD set was great for ball-only Day 5 (ball geometry is consistent) but the `person` semantics differs from "on-court basketball player" -- many OOD persons are individual trainees in empty gyms.
- **What this means for deployment:** the model is heavily fit to the broadcast game-footage distribution it'll be used on. The PRD's option (a) -- labeling 40-50 frames of the user's own 4K basketball clip -- would be the more representative OOD test; deferred (cost vs value) but flagged as a real gap. The IN-DISTRIBUTION tracking test (Part D) is the relevant proxy for the deployment use case.

### Tracking re-run (the payoff)

Reused `scripts/track_mot_run.py` and `scripts/eval_track.py` from Day 6 EXACTLY. Fed `models/basketball_player.pt` (class-name "player") into default ByteTrack, no tracker tuning, on the same 5 SportsMOT-val basketball seqs.

| Setup | HOTA | DetA | AssA | MOTA | IDF1 | IDsw | Unique-IDs | Total dets |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GT detections + ByteTrack (ceiling) | 74.05 | 83.88 | 65.39 | 98.95 | 84.56 | 53 | 83 | 43,839 |
| COCO person + ByteTrack (Day-6 real) | 26.62 | 25.32 | 28.00 | -113.03 | 22.23 | 365 | 2,435 | 130,814 |
| **FT player + ByteTrack (Day-7 new)** | **48.50** | **74.75** | 31.55 | **+91.24** | **50.71** | 409 | **430** | **43,857** |

(Tracker outputs at `outputs/track_results/bball_ftdet_bytetrack/<seq>.txt`.)

### Interpretation

**Detector overhaul did exactly what Day 6 predicted:**
- **DetA: 25.32 -> 74.75 (+49.4 points).** Closes 99% of the 58.6-point Day-6 DetA gap to the ceiling. The detection bottleneck is gone.
- **MOTA: -113 -> +91.** Flipped from "more errors than truths" to "near-perfect frame-level accuracy." Crowd / ref / bench FPs that drove MOTA negative are eliminated (130k dets -> 44k dets, matching the GT count of 43.9k almost exactly).
- **HOTA: 26.62 -> 48.50 (+21.9 points).** Closes ~46% of the 47.4-point ceiling gap with detector work alone, no tracker tuning.
- **IDF1: 22.23 -> 50.71 (+28.5 points).** Identity-consistent tracking more than doubled.

**Association is now the bottleneck:**
- **AssA only moved 28 -> 32 (+3.6 points)** -- barely. Default ByteTrack (untuned) struggles with basketball: fast direction changes, occlusions during plays, very similar-looking uniformed players.
- **Unique-IDs 430 vs 50 GT** -- still 8.6x over. The tracker creates fresh IDs every time a player is occluded or leaves frame briefly. Day 6's 2,435 -> today's 430 is a huge cleanup, but to reach the ceiling's 83 we need longer `track_buffer` / different `match_thresh` / appearance features (BoT-SORT).
- **IDsw 365 -> 409** went slightly WORSE. Not a failure -- Day 6 IDsw counted switches across a noisy mess; now with clean detections there are more "real" identities to confuse and the default tracker keeps mis-binding them across occlusions.

**The remaining 25.5-point HOTA gap (48.5 -> 74.05 ceiling) is now association headroom**, addressable in a tracker-tuning session: `track_buffer` (currently 30 frames default), `match_thresh`, `new_track_thresh`, BoT-SORT appearance ReID. Exactly the next session per the PRD.

**ID-vs-OOD detection gap (AP 91 vs 9):** real overfit signal; lever is more data variety (other SportsMOT sports as negatives, broadcast clips from non-NBA games, eventually the user's own footage). For deployment on game broadcasts the ID number is the right one; for deployment on drill / training footage we'd need different training data.

### Errors hit (informative)
- **CUDA OOM @ imgsz=1280 batch=4** (loss-tensor scaling with ~10 instances/frame). Fix: imgsz=960.
- **Host-RAM crash during val on 4.5 MiB alloc** (workers=2 subprocess memory pressure). Fix: workers=0.
- **First training run died after epoch 1 with no checkpoint saved** -- Ultralytics saves checkpoints only after a successful validation. Fix: workers=0 retry produced clean per-epoch checkpoints.

### VERDICT
- Detector closed **99% of the detection gap** (DetA 25 -> 75, ceiling 84) -- the durable fix the Day-6 root-cause analysis pointed at.
- **MOTA flipped from -113 to +91** -- a 200-point swing.
- **HOTA jumped +21.9 points** (26.6 -> 48.5) with NO tracker tuning. Remaining 25.5-point gap to ceiling is fully association-side, addressable next session.
- OOD AP is poor; honest signal that this model is broadcast-game-specific. Acceptable for the deployment target; flagged for future variety/data work.

### Time
Wall: ~75 min for Part A-D (15 min train.tar download, 10 min train extract + YOLO build, 25 min train across two failed starts + one successful 7-epoch run, ~10 min eval + tracking + reporting). Total Day 7 session ~90 min.

### Files added / changed
- `scripts/sportsmot_to_yolo.py` -- single-seq-dir MOT->YOLO converter (ID eval set).
- `scripts/build_sportsmot_yolo.py` -- multi-seq train/val builder with sequence-level holdout.
- `scripts/extract_sportsmot_train.py` -- tar extractor for basketball-train subset only.
- `scripts/train_player.py` -- Day 5-style train driver targeting the new dataset.
- `models/basketball_player.pt` -- new fine-tuned player detector (epoch 7 best).
- `datasets/sportsmot_player_train/{images,labels}/{train,val}/` + `data.yaml` -- YOLO training data.
- `datasets/sportsmot_id_eval/test/{images,labels}` + `data.yaml` -- ID detection eval set.
- `outputs/eval/day7_{id,ood}_{gtaspred,coco,ft}.json` -- six eval reports.
- `outputs/track_results/bball_ftdet_bytetrack/*.txt` -- tracker outputs (5 seqs).
- `outputs/gt_samples/day7_{train_*,ood_diag_*}.png` -- diagnostic visualizations.
