from ultralytics import YOLO
import cv2, time
from pathlib import Path

MODEL = "models/football.pt"
INPUT = "clips/football.mp4"
OUTPUT = "outputs/football_tracked.mp4"
Path("outputs").mkdir(exist_ok=True)

model = YOLO(MODEL)
print("classes:", model.names)

cap = cv2.VideoCapture(INPUT)
fps = cap.get(cv2.CAP_PROP_FPS)
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
cap.release()

writer = cv2.VideoWriter(OUTPUT, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
unique = set()
frames = 0
t0 = time.time()
for res in model.track(source=INPUT, stream=True, device=0, imgsz=1280,
                       tracker="bytetrack.yaml", persist=True, verbose=False):
    writer.write(res.plot())
    if res.boxes.id is not None:
        for tid in res.boxes.id.cpu().numpy():
            unique.add(int(tid))
    frames += 1
    if frames % 30 == 0:
        print(f"{frames}  {frames/(time.time()-t0):.1f} FPS  uniqueIDs={len(unique)}")

writer.release()
elapsed = time.time() - t0
print(f"\nFrames={frames}  unique IDs={len(unique)}  avgFPS={frames/elapsed:.1f}")
print(f"Output: {OUTPUT}")
