"""Run ByteTrack over CACHED detections (built by build_det_cache.py).

Reads <cache>/<seq>.txt (frame,x,y,w,h,conf) per seq, feeds boxes into BYTETracker
with optional parameter overrides, writes MOT-format tracker output.

Designed to be subprocess-free: helpers are imported by sweep_tracker.py.

Single-config CLI usage (e.g., for the trust gate that the cache reproduces baseline):
  python scripts/track_from_cache.py \
      --cache outputs/det_cache/sn_soccana \
      --source datasets/soccernet_tracking \
      --out outputs/track_results/sn_soccana_cached_default
"""
import argparse, configparser
from pathlib import Path
from collections import defaultdict
from types import SimpleNamespace
import numpy as np
import torch
import yaml

def parse_seqinfo(seq_dir: Path):
    cp = configparser.ConfigParser()
    cp.read(seq_dir / "seqinfo.ini")
    s = cp["Sequence"]
    return {
        "name": s.get("name"),
        "seqLength": int(s.get("seqLength")),
        "imWidth": int(s.get("imWidth")),
        "imHeight": int(s.get("imHeight")),
        "frameRate": int(s.get("frameRate", 25)),
    }

def load_cache(cache_path: Path):
    """Return {frame: list of (x, y, w, h, conf)}."""
    by_frame = defaultdict(list)
    if not cache_path.exists():
        return by_frame
    for line in cache_path.read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(",")
        f = int(p[0])
        x, y, w, h, c = map(float, p[1:6])
        by_frame[f].append((x, y, w, h, c))
    return by_frame

def make_bytetracker(overrides: dict, frame_rate: int):
    """Build Ultralytics BYTETracker with optional param overrides applied to bytetrack.yaml."""
    from ultralytics.trackers.byte_tracker import BYTETracker
    import ultralytics
    yml = Path(ultralytics.__file__).parent / "cfg" / "trackers" / "bytetrack.yaml"
    cfg = yaml.safe_load(yml.read_text())
    cfg["frame_rate"] = frame_rate
    if overrides:
        cfg.update(overrides)
    return BYTETracker(SimpleNamespace(**cfg)), cfg

def boxes_to_track_input(dets: list, orig_shape):
    """dets: list of (x,y,w,h,conf). Returns ultralytics Boxes obj."""
    from ultralytics.engine.results import Boxes
    if not dets:
        return Boxes(torch.zeros(0, 6), orig_shape)
    arr = np.array(dets, dtype=np.float32)
    xyxy = arr[:, :4].copy()
    xyxy[:, 2] = arr[:, 0] + arr[:, 2]  # x2 = x + w
    xyxy[:, 3] = arr[:, 1] + arr[:, 3]  # y2 = y + h
    cf = arr[:, 4:5]
    cls = np.zeros((len(arr), 1), dtype=np.float32)
    data = torch.from_numpy(np.concatenate([xyxy, cf, cls], axis=1))
    return Boxes(data, orig_shape)

def track_seq(cache_path: Path, seq_dir: Path, out_path: Path, overrides: dict):
    info = parse_seqinfo(seq_dir)
    by_frame = load_cache(cache_path)
    tracker, _ = make_bytetracker(overrides, info["frameRate"])
    out_lines = []
    for f in range(1, info["seqLength"] + 1):
        det_obj = boxes_to_track_input(by_frame.get(f, []), (info["imHeight"], info["imWidth"]))
        online = tracker.update(det_obj)
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
    ap.add_argument("--cache", required=True, help="Detection cache dir (per-seq .txt)")
    ap.add_argument("--source", required=True, help="Dataset dir for seqinfo.ini")
    ap.add_argument("--out", required=True, help="Tracker output dir")
    ap.add_argument("--param", action="append", default=[],
                    help='Override bytetrack.yaml: e.g. --param track_buffer=60 --param match_thresh=0.7')
    args = ap.parse_args()

    overrides = {}
    for p in args.param:
        k, v = p.split("=", 1)
        try:    v = int(v)
        except ValueError:
            try: v = float(v)
            except ValueError: pass
        overrides[k] = v
    print(f"overrides: {overrides}")

    source = Path(args.source); cache = Path(args.cache); out = Path(args.out)
    seqs = sorted(d for d in source.iterdir() if d.is_dir() and (d / "seqinfo.ini").exists())
    for seq_dir in seqs:
        cache_path = cache / f"{seq_dir.name}.txt"
        out_path = out / f"{seq_dir.name}.txt"
        n = track_seq(cache_path, seq_dir, out_path, overrides)
        print(f"  {seq_dir.name}: {n} rows -> {out_path}")

if __name__ == "__main__":
    main()
