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
