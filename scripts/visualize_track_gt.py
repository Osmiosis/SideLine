"""Render a MOT-format sequence's GT tracklets onto frames -> short mp4.

Each track gets a deterministic color so a developer can eyeball whether IDs
stay glued to the same player across frames.

Usage:
  python scripts/visualize_track_gt.py <seq_dir> --out outputs/gt_samples/<seq>_gt.mp4 [--max-frames 150]
"""
import argparse, configparser
from pathlib import Path
from collections import defaultdict
import cv2
import numpy as np

def color_for_id(tid: int):
    rng = np.random.RandomState(tid * 9973 + 7)
    return tuple(int(c) for c in rng.randint(40, 256, size=3))

def parse_seqinfo(seq_dir: Path):
    cp = configparser.ConfigParser()
    cp.read(seq_dir / "seqinfo.ini")
    s = cp["Sequence"]
    return s.get("name"), s.get("imDir", "img1"), int(s.get("seqLength")), int(s.get("imWidth")), int(s.get("imHeight")), s.get("imExt", ".jpg"), int(s.get("frameRate", 25))

def load_gt(seq_dir: Path):
    by_frame = defaultdict(list)
    for line in (seq_dir / "gt" / "gt.txt").read_text().splitlines():
        p = line.strip().split(",")
        if len(p) < 6: continue
        f, tid = int(p[0]), int(p[1])
        x, y, w, h = map(float, p[2:6])
        conf = float(p[6]) if len(p) > 6 else 1.0
        if conf == 0: continue
        by_frame[f].append((tid, x, y, w, h))
    return by_frame

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq_dir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-frames", type=int, default=150)
    args = ap.parse_args()

    seq_dir = Path(args.seq_dir)
    name, imDir, seqLen, W, H, ext, fps = parse_seqinfo(seq_dir)
    img_dir = seq_dir / imDir
    by_frame = load_gt(seq_dir)
    n_frames = min(seqLen, args.max_frames)
    print(f"{name}: {n_frames} frames @ {fps}fps -> {args.out}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(args.out, cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
    for f in range(1, n_frames + 1):
        img = cv2.imread(str(img_dir / f"{f:06d}{ext}"))
        if img is None: continue
        for tid, x, y, w, h in by_frame.get(f, []):
            c = color_for_id(tid)
            cv2.rectangle(img, (int(x), int(y)), (int(x + w), int(y + h)), c, 2)
            cv2.putText(img, f"id={tid}", (int(x), max(0, int(y) - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 2)
        cv2.putText(img, f"frame {f}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
        cv2.putText(img, f"frame {f}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        writer.write(img)
    writer.release()
    print(f"wrote {args.out}")

if __name__ == "__main__":
    main()
