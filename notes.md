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
| Model      | Ball % | Players/frame | Ball conf | FPS |
|------------|--------|---------------|-----------|-----|
| soccana    | 12.4   | 24.1          | 0.40      | 17.9 |
| uisikdag   | 68.3   | 25.5          | 0.38      | 18.6 |
| coco_hires | 16.7   | 22.6          | 0.51      | 17.5 |

**WINNER: uisikdag** (`uisikdag/yolo-v8-football-players-detection`, classes: ball/goalkeeper/player/referee).
Reason: 68.3% ball detection — 5x the next best, with the best player count and FPS. Day 1 baseline 0/540 (0%) -> Day 2 winner 68.3%. Resolution alone (coco_hires) only nudged ball from 0% to 16.7%, so the win is the sports-trained model, not just imgsz.
Copied to `models/football.pt` for downstream scripts.

### Football tracking (uisikdag + ByteTrack, imgsz=1280)
- Frames: 540, avg FPS: 15.9
- **Unique IDs: 371** (expected 25-45; >100 = heavy churn per PRD)
- ID stability read: severe churn. Likely drivers: ball gets re-IDed every flicker, crowded occlusions in wide tactical angle, default `bytetrack.yaml` not tuned for sports. Detection is solid; tracking continuity needs work.
- Output: `outputs/football_tracked.mp4`, midframe `outputs/football_tracked_midframe.png`

### Basketball
- Clip: `clips/basketball.mp4`, 640x360 @ 30fps, 762 frames (25.4s) — user-supplied
- Model: `boris-gans/basketball-yolo11s-detect` (12 classes: ball variants, player + actions, referee, rim)
  - Rejected `446f6e6e79/YOLO-basketball-fineTuned` after inspecting classes — overfit to specific Red_X / White_X jersey numbers.
- Ball %: **3.1**   Players/frame: 7.7   Unique IDs: 268   FPS: 30.8
- Honest assessment: 360p clip is the dominant blocker — ball is a few pixels wide at this resolution, no model can recover that. Player count ~7.7 (expected ~10) is reasonable for partial view. ID churn mirrors football — default ByteTrack is too generic.
- Output: `outputs/basketball_tracked.mp4`, midframe `outputs/basketball_tracked_midframe.png`

### Observations / next steps
- **Football detection is "solved" for the baseline clip** at 68% ball, 25 players/frame.
- **Tracking is the next bottleneck** — tune ByteTrack thresholds (track_high_thresh, track_low_thresh, match_thresh, new_track_thresh, max_age) for sports; consider running tracking only on `player` class and treating ball separately.
- **Basketball needs a higher-res clip** before any real assessment is possible.
- **Models folder** now holds: soccana.pt, uisikdag.pt, football.pt (=uisikdag), basketball_borisgans.pt, basketball.pt (=boris-gans). All gitignored.
