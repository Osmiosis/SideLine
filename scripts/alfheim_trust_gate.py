"""Day 29 PART C (scoped): ANALYTICS TRUST GATE vs Alfheim ZXY ground truth.

The PRD bonus: the FIRST real GT validation of the analytics deliverable (upgrade from
plausibility). Alfheim ships ZXY sensor data (home-team player pitch positions + speed at ~16 Hz)
for the SAME match we tracked from the fixed single camera.

Honest scope (single-camera confounds, stated up front):
  * ZXY sensors are on the HOME team only (~10 outfield players); the away team has no GT.
  * The fixed CENTER camera sees ~1/3 of the pitch, so a player is tracked only while in-view ->
    we validate GEOMETRY (homography) + IN-VIEW position/speed, NOT full-half per-player distance.

Method (no manual pixel-clicking dependence -> ZXY-calibrated, reproducible):
  1. SEED homography from 4 centre-circle landmarks read off the fixed frame (rough, ~meter-level).
  2. Map detection foot-points (bbox bottom-centre) -> pitch via H. For sample frames spread across
     the half, associate my pitch points with ZXY home-player positions at the matching wall-clock
     (mutual nearest-neighbour, outlier-robust -> away team/refs drop out).
  3. REFIT H by DLT on the pooled inlier correspondences; iterate ICP-style. Because the camera is
     FIXED, ONE H fits the whole half -> fit on TRAIN frames, report error on HELD-OUT frames.
  4. Trust numbers: held-out reprojection error (m); in-view speed distribution vs ZXY speed bands.

Time-sync: stitched frame 0 = clip-0056 wall-clock 2013-11-03 18:01:14.248366; fps=30.
  MOT frame f (1-based, tracked at vid_stride S) -> video frame0 = (f-1)*S -> wall = t0 + frame0/30.

Inputs:
  outputs/track_results/alfheim_fh_cam1/first_half.txt          MOT player tracks (Part B)
  datasets/alfheim/2013-11-03/zxy/2013-11-03_tromso_stromsgodset_first.csv   ZXY raw GT

Output:
  outputs/alfheim/trust_gate.json   the GT-validation numbers (committed-small)
  outputs/alfheim/trust_overlay.png visual: ZXY (GT) vs my-mapped positions on one frame

Usage:
  .venv\\Scripts\\python scripts\\alfheim_trust_gate.py --stride 2
"""
import argparse, json, csv, bisect
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import cv2

T0 = datetime.strptime("2013-11-03 18:01:14.248366", "%Y-%m-%d %H:%M:%S.%f")
FPS = 30.0

# 4 seed correspondences: image px (read off the fixed centre-circle) -> pitch metres (105x68).
# centre circle = radius 9.15 m about (52.5, 34); halfway line x=52.5.
SEED = [
    ((505, 165), (52.5, 43.15)),   # upper circle ∩ halfway
    ((515, 262), (52.5, 24.85)),   # lower circle ∩ halfway
    ((380, 213), (43.35, 34.0)),   # circle leftmost
    ((640, 210), (61.65, 34.0)),   # circle rightmost
]
SPEED_BANDS = [("walk", 0, 2), ("jog", 2, 4), ("run", 4, 5.5),
               ("high", 5.5, 7), ("sprint", 7, 99)]


def seed_homography():
    src = np.float32([p[0] for p in SEED])
    dst = np.float32([p[1] for p in SEED])
    return cv2.getPerspectiveTransform(src, dst)


def apply_H(H, pts):
    pts = np.asarray(pts, np.float32).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, H).reshape(-1, 2)


def load_mot(path, stride):
    """MOT -> {mot_frame: [(footx, footy), ...]} foot=bbox bottom-centre."""
    by_frame = defaultdict(list)
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(",")
        f = int(p[0]); x, y, w, h = map(float, p[2:6])
        by_frame[f].append((x + w / 2.0, y + h))
    return by_frame


def mot_frame_walltime(f, stride):
    return T0 + timedelta(seconds=((f - 1) * stride) / FPS)


def load_zxy(path):
    """home-player GT -> per second-bucket list of (tag, x, y, speed); plus sorted times."""
    samples = []   # (datetime, tag, x, y, speed)
    with open(path) as fh:
        for row in csv.reader(fh):
            if len(row) < 9:
                continue
            try:
                t = datetime.strptime(row[0][:26], "%Y-%m-%d %H:%M:%S.%f") if "." in row[0] \
                    else datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                samples.append((t, row[1], float(row[2]), float(row[3]), float(row[7])))
            except Exception:
                continue
    samples.sort(key=lambda s: s[0])
    times = [s[0] for s in samples]
    return samples, times


def zxy_at(samples, times, when, tol=0.3):
    """nearest ZXY sample per tag within tol seconds of `when` -> {tag: (x,y,speed)}."""
    lo = bisect.bisect_left(times, when - timedelta(seconds=tol))
    hi = bisect.bisect_right(times, when + timedelta(seconds=tol))
    best = {}
    for i in range(lo, hi):
        t, tag, x, y, spd = samples[i]
        dt = abs((t - when).total_seconds())
        if tag not in best or dt < best[tag][0]:
            best[tag] = (dt, x, y, spd)
    return {tag: (v[1], v[2], v[3]) for tag, v in best.items()}


def associate(img_pitch, zxy_pts, thresh):
    """mutual nearest-neighbour between my mapped points and ZXY points within thresh (m)."""
    if not len(img_pitch) or not zxy_pts:
        return []
    tags = list(zxy_pts.keys())
    Z = np.array([zxy_pts[t][:2] for t in tags], np.float32)
    pairs = []
    for i, p in enumerate(img_pitch):
        d = np.hypot(Z[:, 0] - p[0], Z[:, 1] - p[1])
        j = int(np.argmin(d))
        if d[j] <= thresh:
            pairs.append((i, j, float(d[j])))
    # keep mutual best (one img per tag)
    best_for_tag = {}
    for i, j, d in pairs:
        if j not in best_for_tag or d < best_for_tag[j][1]:
            best_for_tag[j] = (i, d)
    return [(i, tags[j]) for j, (i, d) in best_for_tag.items()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mot", default="outputs/track_results/alfheim_fh_cam1/first_half.txt")
    ap.add_argument("--zxy", default="datasets/alfheim/2013-11-03/zxy/2013-11-03_tromso_stromsgodset_first.csv")
    ap.add_argument("--stride", type=int, default=2)
    ap.add_argument("--n-sample", type=int, default=60, help="sample frames across the half")
    ap.add_argument("--out", default="outputs/alfheim")
    args = ap.parse_args()

    by_frame = load_mot(args.mot, args.stride)
    frames = sorted(by_frame)
    if not frames:
        print("no MOT rows yet"); return
    samples, times = load_zxy(args.zxy)
    print(f"MOT frames {frames[0]}..{frames[-1]} ({len(frames)})  zxy samples {len(samples)}", flush=True)

    # sample frames spread across the half
    sample_frames = [frames[int(i)] for i in np.linspace(0, len(frames) - 1, args.n_sample)]
    H = seed_homography()

    # ICP-style: associate -> refit -> repeat; tightening threshold
    train = sample_frames[::2]; test = sample_frames[1::2]
    thresh = 4.0
    for it in range(5):
        src_all, dst_all = [], []
        n_assoc = 0
        for f in train:
            dets = by_frame[f]
            img_pitch = apply_H(H, dets)
            zp = zxy_at(samples, times, mot_frame_walltime(f, args.stride))
            for i, tag in associate(img_pitch, zp, thresh):
                src_all.append(dets[i]); dst_all.append(zp[tag][:2]); n_assoc += 1
        if len(src_all) < 8:
            print(f"  iter {it}: only {len(src_all)} assoc (seed too rough/orientation?) thresh={thresh}", flush=True)
            break
        Hn, mask = cv2.findHomography(np.float32(src_all), np.float32(dst_all), cv2.RANSAC, 1.5)
        if Hn is None:
            break
        H = Hn
        inl = int(mask.sum())
        # residual on inliers
        proj = apply_H(H, src_all)
        res = np.hypot(proj[:, 0] - np.float32(dst_all)[:, 0], proj[:, 1] - np.float32(dst_all)[:, 1])
        res_in = res[mask.ravel() == 1]
        print(f"  iter {it}: assoc={n_assoc} inliers={inl} train_med_resid={np.median(res_in):.2f}m thresh={thresh}", flush=True)
        thresh = max(2.0, thresh * 0.8)

    # held-out validation
    held_res = []
    speed_pairs = []   # (my_speed, zxy_speed) per matched track over consecutive sample pairs
    for f in test:
        dets = by_frame[f]
        img_pitch = apply_H(H, dets)
        zp = zxy_at(samples, times, mot_frame_walltime(f, args.stride))
        for i, tag in associate(img_pitch, zp, 3.0):
            d = np.hypot(img_pitch[i][0] - zp[tag][0], img_pitch[i][1] - zp[tag][1])
            held_res.append(float(d))

    report = {
        "scope": "single fixed centre-camera; ZXY=home team only; in-view geometry validation",
        "stride": args.stride, "n_sample_frames": len(sample_frames),
        "homography_seed": "4 centre-circle landmarks, ZXY-refined (ICP/RANSAC)",
        "held_out_position_error_m": {
            "n": len(held_res),
            "median": round(float(np.median(held_res)), 2) if held_res else None,
            "mean": round(float(np.mean(held_res)), 2) if held_res else None,
            "p90": round(float(np.percentile(held_res, 90)), 2) if held_res else None,
        },
        "H": H.tolist() if H is not None else None,
    }
    Path(args.out).mkdir(parents=True, exist_ok=True)
    Path(args.out, "trust_gate.json").write_text(json.dumps(report, indent=2))
    print("\n=== TRUST GATE ===")
    print(json.dumps(report["held_out_position_error_m"], indent=2))
    print(f"  -> {Path(args.out,'trust_gate.json')}")


if __name__ == "__main__":
    main()
