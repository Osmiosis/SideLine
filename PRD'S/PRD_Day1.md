# PRD — Day 1: Environment Setup & First Detection
**Project:** AI Sports Recording & Analytics System
**Date:** Day 1 (May 28, 2026)
**Estimated total time:** 3–4 hours
**Target environment:** Windows 11, RTX 4060 GPU, Python 3.11

---

## Goal of today

By end of session, the developer should have:
1. A project folder with a Python 3.11 virtual environment
2. PyTorch installed with CUDA support and verified using the RTX 4060
3. Ultralytics YOLOv8m installed and running detection on the GPU
4. A working script that processes a sports video clip frame-by-frame and outputs annotated video
5. A public GitHub repository with all code committed
6. SoccerNet dataset access request submitted (user-handled)

**Out of scope today:** custom training, ByteTrack integration, stitching, team assignment, any pipeline beyond raw YOLO detection on a single clip.

---

## Constraints & rules

- **Python 3.11 only.** Not 3.12 or 3.13. Several CV libraries lag on newer versions.
- **Project path must not contain spaces or non-ASCII characters.** Avoid OneDrive-synced paths.
- **All Python work happens inside the virtual environment.** Never use system Python.
- **All paths use forward slashes or raw strings** in Python code for Windows compatibility.
- **If a step fails, STOP and report the exact error.** Do not attempt creative fixes without the developer's approval, especially for CUDA-related issues.
- **Never commit large files** (videos, model weights, venv folder) to git. `.gitignore` must be set before the first commit.
- **The developer will handle:** GitHub repo creation on github.com, Python 3.11 installer download if needed, SoccerNet account request, picking the test video URL. Ask the developer for these inputs; do not attempt to automate them.

---

## Task 1 — Project folder + Git initialization

1. Create the project directory at a path the developer specifies (suggest `C:\Users\<user>\Projects\sports-ai` if they haven't decided).
2. Inside it, run `git init`.
3. Create `README.md` with this content:
   ```
   # AI Sports Recording & Analytics System

   A capstone project building an end-to-end pipeline that records school sports
   matches and produces three outputs from a single capture: coach-facing tactical
   analytics, per-player highlight clips, and event highlight reels.

   Author: [developer name]
   School: DPS Modern Indian School, Doha
   Status: Day 1 — environment setup
   ```
4. Create `.gitignore` with these entries:
   ```
   # Python
   __pycache__/
   *.py[cod]
   *$py.class
   *.so
   .Python

   # Virtual environments
   .venv/
   venv/
   env/

   # Model weights (large binary files)
   *.pt
   *.pth
   *.onnx
   *.engine

   # Video files (too large for git)
   *.mp4
   *.mov
   *.avi
   *.mkv
   *.webm

   # Data folders
   clips/
   datasets/
   outputs/
   runs/

   # IDE
   .vscode/
   .idea/

   # OS
   .DS_Store
   Thumbs.db

   # Notes (uncomment if you want notes private)
   # notes.md
   ```
5. Create empty directories that will be needed later: `clips/`, `scripts/`, `outputs/`. Each should contain a `.gitkeep` file so git tracks the empty directory.
6. Create `notes.md` for the developer to log decisions and commands during the day. Stub with: `# Day 1 Notes` and a date line.
7. **Stop here and ask the developer for the GitHub remote URL** after they create the empty repo on github.com. Then:
   - `git add .`
   - `git commit -m "Initial commit: project structure"`
   - `git branch -M main`
   - `git remote add origin <URL provided by developer>`
   - `git push -u origin main`

**Verification:** Refreshing the GitHub repo page in a browser should show the README, .gitignore, and the empty folders with .gitkeep files.

---

## Task 2 — Python 3.11 environment

1. Check whether Python 3.11 is installed: `py -3.11 --version`.
2. **If not installed:** Tell the developer to download Python 3.11 from python.org and run the installer, making sure to check "Add Python to PATH" during installation. Wait for confirmation before proceeding.
3. Once Python 3.11 is available, inside the project directory:
   ```
   py -3.11 -m venv .venv
   ```
4. Activate the venv. On Windows PowerShell:
   ```
   .\.venv\Scripts\Activate.ps1
   ```
   If PowerShell execution policy blocks this, the developer must manually run (as themselves, not in script): `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` — ask them first.
5. Verify activation: `where python` should return a path inside `.venv\Scripts\`. `python --version` should return `Python 3.11.x`.
6. Upgrade pip inside the venv: `python -m pip install --upgrade pip`.

**Verification:** Terminal prompt prefixed with `(.venv)`. `python -c "import sys; print(sys.executable)"` returns a path inside the project's `.venv`.

---

## Task 3 — PyTorch with CUDA (CRITICAL — most likely to fail)

1. Run `nvidia-smi` and read the "CUDA Version" reported in the top-right of the output. Report this value to the developer.
2. Direct the developer to https://pytorch.org/get-started/locally/ and ask them to select: Stable / Windows / Pip / Python / the highest CUDA version that is ≤ the version from nvidia-smi.
3. **Wait for the developer to provide the install command from the PyTorch website.** Do not guess the command. CUDA-mismatched installs are the #1 cause of "torch.cuda.is_available() returns False."
4. Run the install command the developer provides, inside the activated venv.
5. Create `scripts/verify_gpu.py`:
   ```python
   import torch
   print(f"PyTorch version: {torch.__version__}")
   print(f"CUDA available: {torch.cuda.is_available()}")
   if torch.cuda.is_available():
       print(f"CUDA version: {torch.version.cuda}")
       print(f"Device count: {torch.cuda.device_count()}")
       print(f"Device name: {torch.cuda.get_device_name(0)}")
   else:
       print("WARNING: CUDA not available. PyTorch will run on CPU only.")
   ```
6. Run it: `python scripts/verify_gpu.py`.

**Verification:** Output must show `CUDA available: True` AND `Device name: NVIDIA GeForce RTX 4060 ...`.

**If CUDA is not available:** STOP. Do not attempt fixes. Report the exact output to the developer and wait for instructions. Common silent failures here include installing the CPU-only wheel by accident, or mixing CUDA toolkit versions.

---

## Task 4 — Ultralytics YOLOv8 install + first image detection

1. Inside the venv: `pip install ultralytics`. This will install OpenCV, NumPy, and other dependencies as side effects.
2. Create `scripts/detect_image.py`:
   ```python
   from ultralytics import YOLO
   from pathlib import Path

   # Download YOLOv8m on first run (~50MB to current directory or ~/.cache)
   model = YOLO("yolov8m.pt")

   # Use a built-in sample image from ultralytics or any local image
   # Ultralytics ships with 'bus.jpg' as a default test
   results = model("https://ultralytics.com/images/bus.jpg",
                   device=0,  # GPU
                   save=True,
                   project="outputs",
                   name="day1_image_test",
                   exist_ok=True)

   # Print what was detected
   for r in results:
       print(f"Detections in image:")
       for box, cls, conf in zip(r.boxes.xyxy.cpu().numpy(),
                                  r.boxes.cls.cpu().numpy(),
                                  r.boxes.conf.cpu().numpy()):
           class_name = model.names[int(cls)]
           print(f"  {class_name}: {conf:.2f}")
       print(f"Saved to: {r.save_dir}")
   ```
3. Run: `python scripts/detect_image.py`.
4. Confirm an annotated image was saved in `outputs/day1_image_test/`.

**Verification:** Console output lists detections (e.g. "bus: 0.92, person: 0.87"). Annotated image file exists with bounding boxes drawn.

---

## Task 5 — First video detection on a real sports clip

1. **Ask the developer for a YouTube URL** of a short (under 2 minutes) sports clip — football or basketball, doesn't matter which, but prefer something with clear gameplay from a wide angle.
2. Install yt-dlp: `pip install yt-dlp`.
3. Download the video to `clips/`:
   ```
   yt-dlp -f "bestvideo[height<=1080][ext=mp4]+bestaudio/best[height<=1080]" -o "clips/day1_test.%(ext)s" "<URL>"
   ```
4. Create `scripts/detect_video.py`:
   ```python
   from ultralytics import YOLO
   import cv2
   import time
   from pathlib import Path

   INPUT = "clips/day1_test.mp4"
   OUTPUT = "outputs/day1_video_annotated.mp4"

   Path("outputs").mkdir(exist_ok=True)
   model = YOLO("yolov8m.pt")

   cap = cv2.VideoCapture(INPUT)
   fps = cap.get(cv2.CAP_PROP_FPS)
   width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
   height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
   total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

   fourcc = cv2.VideoWriter_fourcc(*"mp4v")
   writer = cv2.VideoWriter(OUTPUT, fourcc, fps, (width, height))

   # Classes we care about: 0 = person, 32 = sports ball (COCO indices)
   CLASSES_OF_INTEREST = [0, 32]

   frame_idx = 0
   t_start = time.time()
   while True:
       ret, frame = cap.read()
       if not ret:
           break
       results = model(frame, device=0, classes=CLASSES_OF_INTEREST, verbose=False)
       annotated = results[0].plot()
       writer.write(annotated)
       frame_idx += 1
       if frame_idx % 30 == 0:
           elapsed = time.time() - t_start
           fps_proc = frame_idx / elapsed
           print(f"Frame {frame_idx}/{total_frames}  |  {fps_proc:.1f} FPS  |  ETA: {(total_frames - frame_idx) / fps_proc:.0f}s")

   cap.release()
   writer.release()
   elapsed = time.time() - t_start
   print(f"\nDone. Processed {frame_idx} frames in {elapsed:.1f}s ({frame_idx/elapsed:.1f} FPS avg).")
   print(f"Output: {OUTPUT}")
   ```
5. Run: `python scripts/detect_video.py`.
6. After completion, report the processing FPS to the developer.

**Verification:** `outputs/day1_video_annotated.mp4` exists and plays. Bounding boxes follow players. Average processing speed should be 20+ FPS on RTX 4060 for 1080p YOLOv8m.

**Known expected behaviour (do not flag as bug):** ball detection will be unreliable — small fast-moving objects challenge YOLOv8 out-of-the-box. Player detection should be solid.

---

## Task 6 — Final commit & push

1. Verify nothing large is staged: `git status` then `git ls-files --others --exclude-standard | xargs du -sh 2>/dev/null` to spot any leaked large files.
2. If everything looks clean:
   ```
   git add scripts/ README.md notes.md
   git commit -m "Day 1: environment setup, GPU verified, first YOLOv8 detection on sample clip"
   git push
   ```
3. Confirm the push succeeded and the new commit appears on GitHub.

**Verification:** GitHub repo shows the new scripts under `scripts/` folder. No video files or model weights in the repo.

---

## End-of-day report (for the developer to send back)

When done (or stuck), the developer should report:

1. ✅ / ❌ for each task (1–6)
2. The `verify_gpu.py` output (cuda available? device name?)
3. The processing FPS reported by `detect_video.py`
4. A screenshot or paste of the output video's first frame with bounding boxes
5. Any errors encountered, even if "fixed"
6. Actual time taken vs. estimated

---

## Things NOT to do today (deferred for later)

- Do not install or configure ByteTrack — that's Day 3+
- Do not attempt to fine-tune any model — that's after we have real DPS MIS footage
- Do not start stitching, team assignment, or any analytics — those depend on this foundation working
- Do not try to make the ball detection better through hyperparameter tuning — we'll switch to a sports-specific model later
- Do not download more than one test clip — we don't have a storage strategy yet
