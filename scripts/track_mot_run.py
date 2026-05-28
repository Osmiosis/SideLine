"""Run ByteTrack over a SportsMOT-style sequence directory; write MOT-format output.

Two modes:
  --from-detector <model.pt>   # use a YOLO detector for per-frame boxes
  --from-gt                    # read GT boxes (positions only — strip identity IDs)

Sequence layout (MOT17 / SportsMOT):
  <seq>/
    img1/000001.jpg, 000002.jpg, ...
    gt/gt.txt    (frame,id,x,y,w,h,conf,cls,vis)
    seqinfo.ini

Output: one line per detection per frame
  frame,id,x,y,w,h,conf,-1,-1,-1

Usage:
  python scripts/track_mot_run.py <seq_dir> --from-detector yolov8m.pt \
    --out outputs/track_results/<tracker_tag>/<seq>.txt --class-name person
  python scripts/track_mot_run.py <seq_dir> --from-gt \
    --out outputs/track_results/<tracker_tag>/<seq>.txt
"""
import argparse
import configparser
from pathlib import Path
from collections import defaultdict
import numpy as np
import cv2
import torch
import yaml
from types import SimpleNamespace

def parse_seqinfo(seq_dir: Path):
    ini = seq_dir / "seqinfo.ini"
    if not ini.exists():
        raise FileNotFoundError(f"seqinfo.ini not found in {seq_dir}")
    cp = configparser.ConfigParser()
    cp.read(ini)
    s = cp["Sequence"]
    return {
        "name": s.get("name"),
        "imDir": s.get("imDir", "img1"),
        "seqLength": int(s.get("seqLength")),
        "imWidth": int(s.get("imWidth")),
        "imHeight": int(s.get("imHeight")),
        "imExt": s.get("imExt", ".jpg"),
        "frameRate": int(s.get("frameRate", 25)),
    }

def load_gt_by_frame(gt_path: Path):
    """Return {frame: [(x, y, w, h, cls, vis), ...]} stripped of identity ids."""
    by_frame = defaultdict(list)
    for line in gt_path.read_text().splitlines():
        p = line.strip().split(",")
        if len(p) < 6: continue
        f = int(p[0])
        x, y, w, h = map(float, p[2:6])
        conf = float(p[6]) if len(p) > 6 else 1.0
        cls = int(float(p[7])) if len(p) > 7 else 1
        vis = float(p[8]) if len(p) > 8 else 1.0
        # MOT17 convention: conf=1 means "to be considered". Skip ones explicitly marked 0.
        if conf == 0: continue
        by_frame[f].append((x, y, w, h, cls, vis))
    return by_frame

def make_bytetracker():
    """Build Ultralytics' BYTETracker with default bytetrack.yaml settings."""
    from ultralytics.trackers.byte_tracker import BYTETracker
    # Read the shipped default bytetrack.yaml from the package
    import ultralytics
    yml = Path(ultralytics.__file__).parent / "cfg" / "trackers" / "bytetrack.yaml"
    cfg_dict = yaml.safe_load(yml.read_text())
    # BYTETracker expects an args-like namespace with these fields
    # frame_rate is read off args.frame_rate by current Ultralytics BYTETracker
    cfg_dict.setdefault("frame_rate", 30)
    args = SimpleNamespace(**cfg_dict)
    return BYTETracker(args)

def boxes_to_track_input(xyxy: np.ndarray, conf: np.ndarray, cls: np.ndarray, orig_shape):
    """Build a real Ultralytics Boxes object so BYTETracker can index/slice it."""
    from ultralytics.engine.results import Boxes
    n = len(xyxy)
    if n == 0:
        data = torch.zeros(0, 6)
    else:
        data = torch.from_numpy(np.concatenate([xyxy, conf[:, None], cls[:, None]], axis=1)).float()
    return Boxes(data, orig_shape)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq_dir", help="Path to one SportsMOT/MOT17 sequence directory")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-gt", action="store_true", help="Feed ground-truth boxes (stripped of IDs) into tracker")
    src.add_argument("--from-detector", metavar="MODEL_PT", help="Path to YOLO .pt for detection")
    ap.add_argument("--class-name", default="person", help="When --from-detector: keep predictions whose class name contains this")
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--out", required=True, help="Output .txt path (MOT format)")
    args = ap.parse_args()

    seq_dir = Path(args.seq_dir)
    info = parse_seqinfo(seq_dir)
    img_dir = seq_dir / info["imDir"]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"seq: {info['name']}  frames: {info['seqLength']}  res: {info['imWidth']}x{info['imHeight']}  fps: {info['frameRate']}")

    tracker = make_bytetracker()

    # Pre-load GT if needed
    gt_by_frame = None
    if args.from_gt:
        gt_path = seq_dir / "gt" / "gt.txt"
        gt_by_frame = load_gt_by_frame(gt_path)
        print(f"loaded GT for {len(gt_by_frame)} frames")

    # Pre-load detector if needed
    model = None
    keep_classes = None
    if args.from_detector:
        from ultralytics import YOLO
        model = YOLO(args.from_detector)
        keep_classes = {i for i, n in model.names.items() if args.class_name.lower() in n.lower()}
        print(f"model: {args.from_detector}  classes_kept: {[(i, model.names[i]) for i in keep_classes]}")

    out_lines = []
    for f in range(1, info["seqLength"] + 1):
        img_path = img_dir / f"{f:06d}{info['imExt']}"
        # ---- Build per-frame detections ----
        if args.from_gt:
            entries = gt_by_frame.get(f, [])
            xyxy = np.array([(x, y, x + w, y + h) for (x, y, w, h, *_) in entries], dtype=np.float32).reshape(-1, 4)
            confs = np.full(len(entries), 1.0, dtype=np.float32)
            clses = np.zeros(len(entries), dtype=np.float32)
        else:
            frame = cv2.imread(str(img_path))
            if frame is None:
                print(f"  skip unreadable frame {f}"); continue
            res = model(frame, device=0, imgsz=args.imgsz, conf=args.conf, verbose=False)[0]
            mcls = res.boxes.cls.cpu().numpy().astype(int)
            mconf = res.boxes.conf.cpu().numpy()
            mxyxy = res.boxes.xyxy.cpu().numpy()
            keep = np.array([c in keep_classes for c in mcls], dtype=bool)
            xyxy = mxyxy[keep].astype(np.float32)
            confs = mconf[keep].astype(np.float32)
            clses = np.zeros(int(keep.sum()), dtype=np.float32)

        # ---- Run tracker ----
        det_obj = boxes_to_track_input(xyxy, confs, clses, (info["imHeight"], info["imWidth"]))
        online = tracker.update(det_obj)

        # online is np.ndarray of shape (N, 7): xyxy + track_id + conf + cls + idx
        if online is None or len(online) == 0:
            continue
        for row in online:
            x1, y1, x2, y2 = row[:4]
            tid = int(row[4])
            cf = float(row[5])
            w = float(x2 - x1); h = float(y2 - y1)
            out_lines.append(f"{f},{tid},{x1:.2f},{y1:.2f},{w:.2f},{h:.2f},{cf:.4f},-1,-1,-1")

        if f % 50 == 0:
            print(f"  frame {f}/{info['seqLength']}  tracks={len(online)}")

    out_path.write_text("\n".join(out_lines) + ("\n" if out_lines else ""))
    print(f"wrote {len(out_lines)} rows -> {out_path}")

if __name__ == "__main__":
    main()
