"""Run BoT-SORT over CACHED detections + frames (for GMC).

Like track_from_cache.py but uses BOTSORT and passes the frame to enable
sparseOptFlow Global Motion Compensation. ReID is disabled (with_reid=False)
to avoid pulling a separate ReID model — this isolates the GMC contribution.

Usage:
  python scripts/track_botsort_from_cache.py \
      --cache outputs/det_cache/sn_soccana \
      --source datasets/soccernet_tracking \
      --out outputs/track_results/sn_soccana_botsort_gmc \
      --param match_thresh=0.9 --param new_track_thresh=0.7
"""
import argparse, configparser
from pathlib import Path
from collections import defaultdict
from types import SimpleNamespace
import numpy as np
import cv2
import torch
import yaml

import sys
sys.path.insert(0, str(Path(__file__).parent))
from track_from_cache import parse_seqinfo, load_cache, boxes_to_track_input  # noqa: E402

def make_botsort(overrides: dict, frame_rate: int):
    from ultralytics.trackers.bot_sort import BOTSORT
    import ultralytics
    yml = Path(ultralytics.__file__).parent / "cfg" / "trackers" / "botsort.yaml"
    cfg = yaml.safe_load(yml.read_text())
    cfg["frame_rate"] = frame_rate
    if overrides:
        cfg.update(overrides)
    cfg.setdefault("with_reid", False)  # frames-only GMC test
    return BOTSORT(SimpleNamespace(**cfg)), cfg

def track_seq(cache_path: Path, seq_dir: Path, out_path: Path, overrides: dict):
    info = parse_seqinfo(seq_dir)
    img_dir = seq_dir / "img1"
    by_frame = load_cache(cache_path)
    tracker, _ = make_botsort(overrides, info["frameRate"])
    out_lines = []
    for f in range(1, info["seqLength"] + 1):
        img_path = img_dir / f"{f:06d}.jpg"
        img = cv2.imread(str(img_path))  # required for GMC
        if img is None:
            continue
        det_obj = boxes_to_track_input(by_frame.get(f, []), (info["imHeight"], info["imWidth"]))
        online = tracker.update(det_obj, img=img)
        if online is None or len(online) == 0:
            continue
        for row in online:
            x1, y1, x2, y2 = row[:4]
            tid = int(row[4]); cf = float(row[5])
            w = float(x2 - x1); h = float(y2 - y1)
            out_lines.append(f"{f},{tid},{x1:.2f},{y1:.2f},{w:.2f},{h:.2f},{cf:.4f},-1,-1,-1")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out_lines) + ("\n" if out_lines else ""))
    return len(out_lines)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--param", action="append", default=[])
    args = ap.parse_args()

    overrides = {}
    for p in args.param:
        k, v = p.split("=", 1)
        try:    v = int(v)
        except ValueError:
            try: v = float(v)
            except ValueError:
                if v.lower() in ("true", "false"): v = v.lower() == "true"
        overrides[k] = v
    print(f"overrides: {overrides}")

    source = Path(args.source); cache = Path(args.cache); out = Path(args.out)
    seqs = sorted(d for d in source.iterdir() if d.is_dir() and (d / "seqinfo.ini").exists())
    for seq_dir in seqs:
        n = track_seq(cache / f"{seq_dir.name}.txt", seq_dir, out / f"{seq_dir.name}.txt", overrides)
        print(f"  {seq_dir.name}: {n} rows")

if __name__ == "__main__":
    main()
