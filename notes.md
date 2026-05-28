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
- Outputs: `outputs/football_annotated.mp4`, `outputs/football_midframe.png`

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
- Output `outputs/football_tracked.mp4` reflects the uisikdag run (including its field-line "ball" FPs). **TODO: rerun with `models/football.pt` now pointing to soccana** to get a tracking baseline on the precision winner.

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
- Outputs: `outputs/basketball_tracked.mp4` + `outputs/Basketball1_tracked.mp4`, midframes `outputs/basketball_tracked_midframe.png` + `outputs/Basketball1_tracked_midframe.png`

### Observations / next steps
- **Precision audit is the missing piece across the board.** Every "ball %" number in this doc is recall-only. Add a TP/FP labelling step (even N=50 hand-labelled frames) before picking ball models on future clips.
- **Football detection (soccana) is solid for the baseline clip** on precision: 12% recall but the boxes are real. Tracking on top of soccana not yet measured — rerun pending.
- **Tracking is the next bottleneck** — tune ByteTrack thresholds (track_high_thresh, track_low_thresh, match_thresh, new_track_thresh, max_age) for sports; consider running tracking only on `player` class and treating ball as a separate single-instance tracker.
- **Basketball benefited from the 4K clip (22.3% ball recall vs 3.1% at 360p);** still needs the same FP audit before any verdict.
- **4K throughput is 7.8 FPS** — fine for batch, will need downsample/imgsz tuning for live.
- **Models folder** now holds: soccana.pt, uisikdag.pt, football.pt (=soccana, 5.6MB, SHA256 dd5f0b…), basketball_borisgans.pt, basketball.pt (=boris-gans). All gitignored.
