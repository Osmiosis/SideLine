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

def ball_idx(names):   return {i for i, n in names.items() if "ball" in n.lower()}
def player_idx(names): return {i for i, n in names.items() if any(k in n.lower() for k in ["player", "person", "goalkeeper"])}

summary = {}
for tag, path in candidates.items():
    if not Path(path).exists():
        print(f"SKIP {tag}: weights not found at {path}")
        continue
    model = YOLO(path)
    print(f"\n=== {tag} === classes: {model.names}")
    b_idx, p_idx = ball_idx(model.names), player_idx(model.names)
    if not b_idx: print(f"  WARNING: no 'ball' class in {tag}")

    cap = cv2.VideoCapture(INPUT)
    fps_in = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(f"outputs/bakeoff_{tag}.mp4", cv2.VideoWriter_fourcc(*"mp4v"), fps_in, (w, h))
    frames = frames_with_ball = ball_dets = player_sum = 0
    ball_conf_sum = 0.0
    t0 = time.time()
    while True:
        ret, frame = cap.read()
        if not ret: break
        res = model(frame, device=0, imgsz=IMGSZ, verbose=False)[0]
        cls = res.boxes.cls.cpu().numpy().astype(int)
        conf = res.boxes.conf.cpu().numpy()
        has_ball = False
        for c, cf in zip(cls, conf):
            if c in b_idx:
                has_ball = True
                ball_dets += 1
                ball_conf_sum += float(cf)
            if c in p_idx:
                player_sum += 1
        if has_ball: frames_with_ball += 1
        writer.write(res.plot())
        frames += 1
    writer.release(); cap.release()
    dt = time.time() - t0
    summary[tag] = {
        "ball_%":   round(100 * frames_with_ball / frames, 1) if frames else 0,
        "players/f": round(player_sum / frames, 1) if frames else 0,
        "ballConf": round(ball_conf_sum / ball_dets, 2) if ball_dets else 0,
        "fps":      round(frames / dt, 1) if dt else 0,
    }
    print(f"  {tag}: {summary[tag]}")

print("\n=========== BAKE-OFF SUMMARY ===========")
print(f"{'model':<12}{'ball%':>8}{'players/f':>11}{'ballConf':>10}{'FPS':>7}")
for tag, s in summary.items():
    print(f"{tag:<12}{s['ball_%']:>8}{s['players/f']:>11}{s['ballConf']:>10}{s['fps']:>7}")
