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

## Known issues / notes
- Initial push to GitHub deferred (per user choice); remote `origin` set to
  `https://github.com/Osmiosis/sports-ai-capstone.git`. Run `git push -u origin main`
  manually to publish.
- Ultralytics saves under `runs/detect/<project>/<name>` regardless of `project=`
  argument (the arg only sets the subdir, not the parent). Not a bug.
- Ball detection unreliable as expected per PRD; will swap to sports-specific model later.
