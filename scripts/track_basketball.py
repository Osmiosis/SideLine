from ultralytics import YOLO
import cv2, time, sys
from pathlib import Path

MODEL = "models/basketball.pt"
INPUT = sys.argv[1] if len(sys.argv) > 1 else "clips/basketball.mp4"
OUTPUT = f"outputs/annotated_videos/{Path(INPUT).stem}_tracked.mp4"
Path("outputs/annotated_videos").mkdir(parents=True, exist_ok=True)
print(f"INPUT={INPUT}  OUTPUT={OUTPUT}")

model = YOLO(MODEL)
print("classes:", model.names)

ball_idx = {i for i, n in model.names.items() if "ball" in n.lower() and "basket" not in n.lower()}
player_idx = {i for i, n in model.names.items() if n.lower().startswith("player")}
print("ball indices:", ball_idx, "player indices:", player_idx)

cap = cv2.VideoCapture(INPUT)
fps = cap.get(cv2.CAP_PROP_FPS)
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
cap.release()

writer = cv2.VideoWriter(OUTPUT, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
unique = set()
frames = frames_with_ball = ball_dets = player_sum = 0
t0 = time.time()
for res in model.track(source=INPUT, stream=True, device=0, imgsz=1280,
                       tracker="bytetrack.yaml", persist=True, verbose=False):
    cls = res.boxes.cls.cpu().numpy().astype(int)
    has_ball = False
    for c in cls:
        if c in ball_idx:
            has_ball = True
            ball_dets += 1
        if c in player_idx:
            player_sum += 1
    if has_ball: frames_with_ball += 1
    if res.boxes.id is not None:
        for tid in res.boxes.id.cpu().numpy():
            unique.add(int(tid))
    writer.write(res.plot())
    frames += 1
    if frames % 30 == 0:
        print(f"{frames}  {frames/(time.time()-t0):.1f} FPS  uniqueIDs={len(unique)}")

writer.release()
elapsed = time.time() - t0
print(f"\nFrames={frames}  unique IDs={len(unique)}  avgFPS={frames/elapsed:.1f}")
print(f"Ball %: {100*frames_with_ball/frames:.1f}   Players/f avg: {player_sum/frames:.1f}")
print(f"Output: {OUTPUT}")
