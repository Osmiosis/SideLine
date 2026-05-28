"""Build per-frame detection cache for one (detector, dataset) pair.

For each sequence in <source>:
  - Run YOLO detector @imgsz on every frame
  - Filter to predictions whose class name contains --class-name (case-insensitive)
  - Write per-frame detections to <out>/<seq>.txt

Cache format (one detection per line, frames are 1-indexed):
  frame,x,y,w,h,conf

Designed for re-use: tracker association sweeps read this cache and never re-run the detector.
Seq-by-seq with GPU-cache flush between seqs to dodge sustained-inference TDR on the 4060.
"""
import argparse, gc, time
from pathlib import Path
import numpy as np
import cv2
import torch

def parse_seqinfo(seq_dir: Path):
    import configparser
    cp = configparser.ConfigParser()
    cp.read(seq_dir / "seqinfo.ini")
    s = cp["Sequence"]
    return {
        "name": s.get("name"),
        "imDir": s.get("imDir", "img1"),
        "seqLength": int(s.get("seqLength")),
        "imExt": s.get("imExt", ".jpg"),
    }

def run_seq(model, seq_dir: Path, out_path: Path, class_keep: set, imgsz: int, conf: float):
    info = parse_seqinfo(seq_dir)
    img_dir = seq_dir / info["imDir"]
    rows = []
    t0 = time.time()
    for f in range(1, info["seqLength"] + 1):
        img_path = img_dir / f"{f:06d}{info['imExt']}"
        frame = cv2.imread(str(img_path))
        if frame is None:
            continue
        res = model(frame, device=0, imgsz=imgsz, conf=conf, verbose=False)[0]
        cls = res.boxes.cls.cpu().numpy().astype(int)
        cf = res.boxes.conf.cpu().numpy()
        xy = res.boxes.xyxy.cpu().numpy()
        keep = np.array([c in class_keep for c in cls], dtype=bool)
        for x1, y1, x2, y2, c in zip(xy[keep, 0], xy[keep, 1], xy[keep, 2], xy[keep, 3], cf[keep]):
            rows.append(f"{f},{x1:.2f},{y1:.2f},{x2-x1:.2f},{y2-y1:.2f},{c:.4f}")
        if f % 100 == 0:
            print(f"  {info['name']}  frame {f}/{info['seqLength']}  dets={int(keep.sum())}  ({time.time()-t0:.1f}s)")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(rows) + ("\n" if rows else ""))
    print(f"  wrote {len(rows)} dets in {time.time()-t0:.1f}s -> {out_path}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--detector", required=True, help="Path to YOLO .pt")
    ap.add_argument("--source", required=True, help="Dataset root containing seq dirs")
    ap.add_argument("--out", required=True, help="Cache output dir (per-seq .txt files)")
    ap.add_argument("--class-name", default="player")
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--only", nargs="+", help="Process only these seqs (for retry)")
    args = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(args.detector)
    class_keep = {i for i, n in model.names.items() if args.class_name.lower() in n.lower()}
    print(f"detector: {args.detector}  classes_kept: {[(i, model.names[i]) for i in class_keep]}")

    source = Path(args.source); out = Path(args.out)
    seqs = sorted(d for d in source.iterdir() if d.is_dir() and (d / "seqinfo.ini").exists())
    if args.only:
        seqs = [s for s in seqs if s.name in args.only]
    print(f"sequences: {[s.name for s in seqs]}")

    for seq_dir in seqs:
        out_path = out / f"{seq_dir.name}.txt"
        if out_path.exists() and out_path.stat().st_size > 0 and not args.only:
            print(f"[skip] {seq_dir.name} already cached ({out_path.stat().st_size} bytes)")
            continue
        print(f"\n[{seq_dir.name}]")
        run_seq(model, seq_dir, out_path, class_keep, args.imgsz, args.conf)
        torch.cuda.empty_cache(); gc.collect()

if __name__ == "__main__":
    main()
