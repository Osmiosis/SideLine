"""Day 29 PART B/C: full-match SCALE FINDINGS + speed-band trust gate (Alfheim first half).

The point of the scale-stress-test: what BREAKS / what HOLDS at 47-min full-match length.
Reads the full MOT (track_alfheim.py) + the ZXY-calibrated homography (trust_gate.json) and reports:

  ID ACCUMULATION (the headline scale metric):
    - total unique track ids over the half (vs ~22 real players on pitch)
    - new ids introduced per minute (the accumulation curve)
    - track-lifetime distribution (median seconds a track survives = fragmentation)
  DENSITY:
    - mean detections/frame
  SPEED-BAND TRUST GATE (the analytics intensity bands vs ZXY GT speed classes):
    - per track, map foot-points -> pitch via the fixed H, smooth, per-frame speed; bucket into the
      standard football GPS bands; compare the IN-VIEW band distribution to ZXY's own speed bands.
      (single-camera + ID-fragmentation caveats apply -> distribution-level, not per-player.)

Usage:
  .venv\\Scripts\\python scripts\\alfheim_scale_findings.py --stride 2
"""
import argparse, json, csv
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
import numpy as np
import cv2

import sys; sys.path.insert(0, str(Path(__file__).parent))
from alfheim_trust_gate import T0, FPS, load_zxy

SPEED_BANDS = [("walk", 0, 2), ("jog", 2, 4), ("run", 4, 5.5), ("high", 5.5, 7), ("sprint", 7, 99)]
PLAYER_TELEPORT_MPS = 10.0   # Day-20 guard: >10 m/s player step = ID-switch teleport, dropped


def band_of(v):
    for name, lo, hi in SPEED_BANDS:
        if lo <= v < hi:
            return name
    return "sprint"


def load_mot_full(path):
    by_track = defaultdict(list)   # tid -> [(frame, footx, footy)]
    per_frame_count = defaultdict(int)
    first_seen = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(","); f = int(p[0]); tid = int(p[1])
        x, y, w, h = map(float, p[2:6])
        by_track[tid].append((f, x + w / 2.0, y + h))
        per_frame_count[f] += 1
        if tid not in first_seen:
            first_seen[tid] = f
    return by_track, per_frame_count, first_seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mot", default="outputs/track_results/alfheim_fh_cam1/first_half.txt")
    ap.add_argument("--trust", default="outputs/alfheim/trust_gate.json")
    ap.add_argument("--zxy", default="datasets/alfheim/2013-11-03/zxy/2013-11-03_tromso_stromsgodset_first.csv")
    ap.add_argument("--stride", type=int, default=2)
    ap.add_argument("--out", default="outputs/alfheim/scale_findings.json")
    args = ap.parse_args()

    by_track, per_frame_count, first_seen = load_mot_full(args.mot)
    frames_sorted = sorted(per_frame_count)
    n_proc_frames = len(frames_sorted)
    dt = args.stride / FPS                       # seconds between consecutive PROCESSED frames
    half_min = n_proc_frames * dt / 60.0

    # --- ID accumulation ---
    total_ids = len(by_track)
    # new ids per minute bucket
    per_min_new = defaultdict(int)
    for tid, f in first_seen.items():
        minute = int((f - 1) * dt / 60.0)
        per_min_new[minute] += 1
    accum_curve = [per_min_new[m] for m in range(int(half_min) + 1)]
    # track lifetimes (seconds)
    lifetimes = []
    for tid, recs in by_track.items():
        fr = [r[0] for r in recs]
        lifetimes.append((max(fr) - min(fr) + 1) * dt)
    lifetimes.sort()
    substantial = [l for l in lifetimes if l >= 1.0]

    # --- speed bands (in-view, via fixed H) ---
    band_secs = defaultdict(float)
    H = None
    trust = json.loads(Path(args.trust).read_text()) if Path(args.trust).exists() else {}
    if trust.get("H"):
        H = np.array(trust["H"], np.float32)
    SMOOTH_SEC = 0.5                                   # window for velocity (Day-20: smoothed, not frame-to-frame)
    win = max(1, int(round(SMOOTH_SEC / dt)))          # frames spanning ~0.5 s
    if H is not None:
        for tid, recs in by_track.items():
            recs = sorted(recs)
            life = (recs[-1][0] - recs[0][0] + 1) * dt
            if life < 2.0 or len(recs) < win + 1:       # substantial tracks only (cut fragment noise)
                continue
            pts = np.float32([[r[1], r[2]] for r in recs]).reshape(-1, 1, 2)
            pitch = cv2.perspectiveTransform(pts, H).reshape(-1, 2)
            for k in range(win, len(recs)):
                df = recs[k][0] - recs[k - win][0]
                if df <= 0:
                    continue
                gap = df * dt
                step = float(np.hypot(*(pitch[k] - pitch[k - win])))
                v = step / gap                          # speed over the ~0.5 s window
                if v > PLAYER_TELEPORT_MPS:             # ID-switch teleport guard (Day-20)
                    continue
                band_secs[band_of(v)] += gap
    tot_band = sum(band_secs.values()) or 1.0
    my_band_pct = {n: round(100 * band_secs[n] / tot_band, 1) for n, _, _ in SPEED_BANDS}

    # --- ZXY speed-band distribution (home team, whole pitch) for comparison ---
    samples, _ = load_zxy(args.zxy)
    zxy_band_secs = defaultdict(float)
    # zxy ~16Hz; weight each sample by its nominal dt
    by_tag_speeds = defaultdict(list)
    for (t, tag, x, y, spd) in samples:
        by_tag_speeds[tag].append(spd)
    for tag, sp in by_tag_speeds.items():
        for v in sp:
            zxy_band_secs[band_of(v)] += 1.0
    ztot = sum(zxy_band_secs.values()) or 1.0
    zxy_band_pct = {n: round(100 * zxy_band_secs[n] / ztot, 1) for n, _, _ in SPEED_BANDS}

    report = {
        "half_minutes": round(half_min, 1), "processed_frames": n_proc_frames, "stride": args.stride,
        "ID_ACCUMULATION": {
            "total_unique_track_ids": total_ids,
            "real_players_on_pitch": "~22 (2 teams) + refs",
            "fragmentation_ratio": round(total_ids / 22.0, 1),
            "new_ids_per_minute": accum_curve,
            "track_lifetime_sec": {
                "median": round(float(np.median(lifetimes)), 1),
                "p90": round(float(np.percentile(lifetimes, 90)), 1),
                "max": round(max(lifetimes), 1),
                "n_substantial_ge1s": len(substantial),
            },
        },
        "DENSITY": {"mean_detections_per_frame": round(np.mean(list(per_frame_count.values())), 1)},
        "SPEED_BAND_TRUST_GATE": {
            "my_inview_pct": my_band_pct, "zxy_gt_pct": zxy_band_pct,
            "note": "single-camera in-view + ID-fragmentation -> distribution-level comparison, not per-player",
        },
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"\n  -> {args.out}")


if __name__ == "__main__":
    main()
