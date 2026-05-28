# PRD — Day 2 (Revised): Model Bake-Off → Tracking → Basketball
**Project:** AI Sports Recording & Analytics System
**Date:** Day 2
**Estimated time:** 3.5–4.5 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv` and repo from Day 1

---

## Context (read first)

Day 1 baseline on `clips/football.mp4` (720p, 540 frames): players ~17/frame, **ball 0/540** with COCO YOLOv8m at default resolution.

Day 2 goal:
1. **Bake-off**: run 2–3 football detection models on the same clip, measure ball-detection rate, pick the winner by data.
2. **Tracking**: add ByteTrack to the winning model so players get persistent IDs.
3. **Basketball**: apply the pipeline to a basketball clip, honestly assess the gap.

Football must reach a fully-verified state BEFORE basketball.

---

## Constraints & rules

- All work inside the existing activated `.venv`. Never system Python.
- **Run all models LOCALLY on the GPU.** Download weights once; no hosted inference APIs in the loop.
- **No Roboflow needed.** Use Hugging Face / GitHub direct downloads. If a model is only on Roboflow, skip it.
- Reuse Day 1 clips. Don't download new footage unless missing.
- **CRITICAL — class indices differ per model.** Each model numbers classes differently. ALWAYS print `model.names` after loading and map the ball class BY NAME ("ball"), never by hardcoded index.
- **Run detection at imgsz=1280, not default 640.** The ball is small; higher inference resolution dramatically improves small-object detection. Apply to ALL models for a fair comparison.
- If a step fails, STOP and report the exact error (model load failures, CUDA OOM at 1280, class-name mismatches).
- New scripts in `scripts/`. Weights in `models/` (gitignored as `*.pt`).
- Report after each Part before continuing.

---

## PART A — Model Bake-Off (~90 min)

### Goal
Fairly compare candidate models on `clips/football.mp4` and pick the best by measured ball-detection rate (player quality / FPS as tiebreakers).

### Candidate models (download weights to `models/`)

**Candidate 1 — soccana (YOLOv11, claims scale-invariance — most promising for elevated angle):**
- Hugging Face repo: `Adit-jain/soccana`
- Classes per card: 0=Player, 1=Ball, 2=Referee
- Download the weights `.pt` from the repo Files tab via `huggingface_hub.hf_hub_download`. Save as `models/soccana.pt`. No HF account needed for public models.

**Candidate 2 — uisikdag YOLOv8 (4 classes):**
- Hugging Face repo: `uisikdag/yolo-v8-football-players-detection`
- Classes: ['ball','goalkeeper','player','referee']
- Download the raw `.pt` from Files tab. Save as `models/uisikdag.pt`.
- The card mentions `ultralyticsplus` with pinned OLD versions — DO NOT install those. Load the raw `.pt` with the CURRENT `ultralytics` YOLO class.

**Candidate 3 — COCO YOLOv8m at high-res (control):**
- Already have `yolov8m.pt`. Classes include 0=person, 32=sports ball.
- Tests whether resolution alone (imgsz=1280) fixes the Day 1 ball problem.

If a download for C1 or C2 stalls > ~15 min, skip it and note it. Two candidates is acceptable.

### Bake-off script
Create `scripts/bakeoff.py`:
- Load each model, print `model.names`, find ball/player classes BY NAME.
- Run inference at `imgsz=1280, device=0`.
- Record per model: frames_with_ball, ball_%, avg players/frame, avg ball confidence, avg FPS.
- Save one annotated sample video per model (`outputs/bakeoff_<tag>.mp4`).
- Print a final comparison table.

```python
from ultralytics import YOLO
import cv2, time
from pathlib import Path

INPUT = "clips/football.mp4"
Path("outputs").mkdir(exist_ok=True)
IMGSZ = 1280

candidates = {
    "soccana":    "models/soccana.pt",
    "uisikdag":   "models/uisikdag.pt",
    "coco_hires": "yolov8m.pt",
}

def ball_idx(names):   return {i for i,n in names.items() if "ball" in n.lower()}
def player_idx(names): return {i for i,n in names.items() if any(k in n.lower() for k in ["player","person","goalkeeper"])}

summary = {}
for tag, path in candidates.items():
    if not Path(path).exists():
        print(f"SKIP {tag}: weights not found at {path}"); continue
    model = YOLO(path)
    print(f"\n=== {tag} === classes: {model.names}")
    b_idx, p_idx = ball_idx(model.names), player_idx(model.names)
    if not b_idx: print(f"  WARNING: no 'ball' class in {tag}")

    cap = cv2.VideoCapture(INPUT)
    fps_in = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(f"outputs/bakeoff_{tag}.mp4", cv2.VideoWriter_fourcc(*"mp4v"), fps_in, (w,h))
    frames=frames_with_ball=ball_dets=player_sum=0; ball_conf_sum=0.0; t0=time.time()
    while True:
        ret, frame = cap.read()
        if not ret: break
        res = model(frame, device=0, imgsz=IMGSZ, verbose=False)[0]
        cls = res.boxes.cls.cpu().numpy().astype(int)
        conf = res.boxes.conf.cpu().numpy()
        has_ball=False
        for c,cf in zip(cls,conf):
            if c in b_idx: has_ball=True; ball_dets+=1; ball_conf_sum+=float(cf)
            if c in p_idx: player_sum+=1
        if has_ball: frames_with_ball+=1
        writer.write(res.plot()); frames+=1
    writer.release(); cap.release(); dt=time.time()-t0
    summary[tag]={"ball_%":round(100*frames_with_ball/frames,1) if frames else 0,
                  "players/f":round(player_sum/frames,1) if frames else 0,
                  "ballConf":round(ball_conf_sum/ball_dets,2) if ball_dets else 0,
                  "fps":round(frames/dt,1) if dt else 0}
    print(f"  {tag}: {summary[tag]}")

print("\n=========== BAKE-OFF SUMMARY ===========")
print(f"{'model':<12}{'ball%':>8}{'players/f':>11}{'ballConf':>10}{'FPS':>7}")
for tag,s in summary.items():
    print(f"{tag:<12}{s['ball_%']:>8}{s['players/f']:>11}{s['ballConf']:>10}{s['fps']:>7}")
```

### Verification & decision
- Each available model → a sample video + a summary row.
- Developer watches each `outputs/bakeoff_<tag>.mp4` and combines numbers with what they see.
- Decision rule: highest ball-% that ALSO keeps players solid and runs ≥5 FPS at 1280. Highest ball% usually wins unless its video looks visibly bad (jittery false ball boxes).
- Copy the winning weights to `models/football.pt` so downstream scripts are model-agnostic.

**STOP after Part A. Report the full summary table + winner + why.**

---

## PART B — Tracking on the winning model (~50 min)

Create `scripts/track_football.py`:
```python
from ultralytics import YOLO
import cv2, time
from pathlib import Path

MODEL="models/football.pt"; INPUT="clips/football.mp4"; OUTPUT="outputs/football_tracked.mp4"
Path("outputs").mkdir(exist_ok=True)
model=YOLO(MODEL); print("classes:", model.names)
cap=cv2.VideoCapture(INPUT); fps=cap.get(cv2.CAP_PROP_FPS)
w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
writer=cv2.VideoWriter(OUTPUT, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w,h))
unique=set(); frames=0; t0=time.time()
for res in model.track(source=INPUT, stream=True, device=0, imgsz=1280,
                       tracker="bytetrack.yaml", persist=True, verbose=False):
    writer.write(res.plot())
    if res.boxes.id is not None:
        for tid in res.boxes.id.cpu().numpy(): unique.add(int(tid))
    frames+=1
    if frames%30==0: print(f"{frames}  {frames/(time.time()-t0):.1f} FPS  uniqueIDs={len(unique)}")
writer.release()
print(f"\nFrames={frames}  unique IDs={len(unique)}  avgFPS={frames/(time.time()-t0):.1f}\nOutput: {OUTPUT}")
```

### Interpretation
- ~25 people on pitch. Unique IDs near 25–45 ⇒ stable-ish. 100+ ⇒ heavy ID-switching (note it).

### Verification
- Output shows boxes WITH IDs. Developer follows one player: does the ID persist? Do IDs swap on crossings? Report count + read.

**STOP after Part B. Report before continuing.**

---

## PART C — Basketball (~40 min)

1. Find Day 1 basketball clip in `clips/`. If missing, ask developer for a URL (short, WIDE-ANGLE, raw gameplay — not a broadcast montage).
2. Find a basketball detection model with local weights (HF/GitHub; search "basketball player ball detection yolov8/yolov11"). ~15 min cap. If nothing solid, FALL BACK to COCO YOLOv8m at imgsz=1280 and note the fallback.
3. Create `scripts/track_basketball.py` (same as football tracking; basketball model + clip; output `outputs/basketball_tracked.mp4`).
4. Run; collect ball-%, unique IDs, FPS.

### Verification
- Output plays. Report model used, ball %, unique IDs, FPS, honest read.
- A poor basketball result is a FINDING, not a failure — document it.

---

## PART D — Compare, log, commit (~30 min)

Append to `notes.md`:
```
## Day 2 — [date]

### Football model bake-off (imgsz=1280)
| Model      | Ball % | Players/frame | Ball conf | FPS |
|------------|--------|---------------|-----------|-----|
| soccana    |        |               |           |     |
| uisikdag   |        |               |           |     |
| coco_hires |        |               |           |     |
WINNER: ____  (reason: ____)
Day 1 baseline ball: 0/540 (0%). Day 2 winner: ___%.

### Tracking (winner + ByteTrack)
- Total unique IDs: ___ (expected ~25-45)
- ID stability read: ___

### Basketball
- Model: ___   Ball %: ___   Unique IDs: ___
- Honest assessment: ___

### Observations / next steps
- ...
```
Then:
- `git status` → confirm NO `.pt` and NO video files staged.
- `git add scripts/ notes.md`
- `git commit -m "Day 2: model bake-off (ball detection solved), ByteTrack tracking, basketball baseline"`
- `git push`

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. **Full bake-off table + winner + why**
3. Day1→Day2 ball detection: 0% → ?%
4. Football unique-ID count + ID-stability read
5. Basketball: model, ball %, honest read
6. FPS figures
7. Screenshots: best football tracked frame + basketball tracked frame
8. Errors hit (even if fixed)
9. Time taken

---

## Do NOT today
- No fine-tuning from scratch (selecting pretrained, not training).
- No team assignment / heatmaps / analytics (Day 3+).
- No stitching / multi-camera.
- Don't hardcode ball class index — map by name (differs per model).
- Don't install pinned-old `ultralyticsplus`/`ultralytics==8.0.25` — use current ultralytics, load raw `.pt`.
- Don't commit weights or videos.
- Don't exceed ~15 min hunting any single model's weights — skip and note.
