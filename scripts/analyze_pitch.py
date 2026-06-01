"""Day 10: analyze one SoccerNet GSR sequence end-to-end.

Pipeline:
  1) Read tracker output (Day-9 BoT-SORT GMC) -- per-frame (id, bbox).
  2) Read GSR Labels-GameState.json -- per-frame GT annotations with bbox_image (px) AND bbox_pitch (m).
  3) Per frame: derive homography H from GT (image_bottom_mid <-> pitch_bottom_mid).
  4) Apply H to tracker feet positions -> tracker pitch coords (m).
  5) Validate: held-out GT subset (20% per frame), apply H from 80%, measure meter error.
  6) Compute distance covered (raw + smoothed) per tracker ID.
  7) Render team + per-player heatmaps overlaid on pitch diagram.
  8) Save positions JSON + heatmap PNGs + summary JSON.

Outputs:
  outputs/deliverables/<seq>/positions.json     (per-tracker-ID meter trajectories)
  outputs/deliverables/<seq>/validation.json    (per-frame meter errors + aggregate)
  outputs/deliverables/<seq>/distances.json     (raw + smoothed totals per tracker ID)
  outputs/deliverables/<seq>/heatmap_team.png
  outputs/deliverables/<seq>/heatmap_player<ID>.png  (top-N most-tracked IDs)

Usage:
  python scripts/analyze_pitch.py SNGS-116
"""
import argparse, json, random, sys, zipfile
from collections import defaultdict
from pathlib import Path
import numpy as np
import cv2

# Standard FIFA pitch dimensions (m); GSR uses center-origin
PITCH_X_HALF = 52.5
PITCH_Y_HALF = 34.0

def load_gt(zip_path: Path, seq: str):
    """Return list of (frame, image_pt[2], pitch_pt[2]) for player+goalkeeper annotations."""
    z = zipfile.ZipFile(zip_path)
    with z.open(f"{seq}/Labels-GameState.json") as f:
        data = json.load(f)
    img_to_frame = {img["image_id"]: int(Path(img["file_name"]).stem) for img in data["images"]}
    pts = []
    for a in data["annotations"]:
        if a.get("category_id") not in (1, 2):  # players + goalkeepers
            continue
        bi = a.get("bbox_image"); bp = a.get("bbox_pitch")
        if not bi or not bp:
            continue
        frame = img_to_frame.get(a["image_id"])
        if frame is None:
            continue
        # Image bottom-middle = feet contact point
        img_x = bi["x_center"]
        img_y = bi["y"] + bi["h"]
        pt_x = bp["x_bottom_middle"]
        pt_y = bp["y_bottom_middle"]
        pts.append((frame, img_x, img_y, pt_x, pt_y))
    return pts

def load_tracker(track_path: Path):
    """Return list of (frame, id, x_feet, y_feet)."""
    out = []
    for line in track_path.read_text().splitlines():
        if not line.strip(): continue
        p = line.split(",")
        f = int(p[0]); tid = int(p[1])
        x = float(p[2]); y = float(p[3]); w = float(p[4]); h = float(p[5])
        out.append((f, tid, x + w/2, y + h))
    return out

def derive_per_frame_H(gt_pts: list, seed: int = 42):
    """Return dict {frame: (H_3x3, mean_calib_err_m)} from a per-frame 80/20 split.

    Validation: also returns held-out errors {frame: list of (test_pred_x, test_pred_y, test_true_x, test_true_y)}.
    """
    rng = random.Random(seed)
    by_frame = defaultdict(list)
    for (f, ix, iy, px, py) in gt_pts:
        by_frame[f].append((ix, iy, px, py))

    H_by_frame = {}
    holdout = {}
    for f, pts in by_frame.items():
        if len(pts) < 4:
            continue
        rng.shuffle(pts)
        n = len(pts)
        n_test = max(1, int(round(n * 0.2)))
        test = pts[:n_test]
        calib = pts[n_test:] if (n - n_test) >= 4 else pts  # if too few for calib, use all (no holdout)
        src = np.array([(p[0], p[1]) for p in calib], dtype=np.float32)
        dst = np.array([(p[2], p[3]) for p in calib], dtype=np.float32)
        H, mask = cv2.findHomography(src, dst, cv2.RANSAC, ransacReprojThreshold=2.0)
        if H is None:
            continue
        H_by_frame[f] = H
        if (n - n_test) >= 4:
            test_src = np.array([[(p[0], p[1])] for p in test], dtype=np.float32)
            test_true = np.array([(p[2], p[3]) for p in test], dtype=np.float32)
            test_pred = cv2.perspectiveTransform(test_src, H).reshape(-1, 2)
            err = np.linalg.norm(test_pred - test_true, axis=1)  # meters
            holdout[f] = list(zip(test_pred[:,0].tolist(), test_pred[:,1].tolist(),
                                  test_true[:,0].tolist(), test_true[:,1].tolist(), err.tolist()))
    return H_by_frame, holdout

def project_tracker(track: list, H_by_frame: dict):
    """Return dict {tid: list of (frame, x_m, y_m)}."""
    out = defaultdict(list)
    for (f, tid, fx, fy) in track:
        H = H_by_frame.get(f)
        if H is None:
            continue
        pt = cv2.perspectiveTransform(np.array([[[fx, fy]]], dtype=np.float32), H).ravel()
        out[tid].append((f, float(pt[0]), float(pt[1])))
    for tid in out:
        out[tid].sort(key=lambda r: r[0])
    return out

def smooth_xy(xy: np.ndarray, win: int = 5):
    """Centered moving average over (N,2)."""
    if len(xy) < 2: return xy.copy()
    k = max(1, win // 2)
    pad = np.pad(xy, ((k, k), (0, 0)), mode="edge")
    kernel = np.ones(win) / win
    sm = np.stack([np.convolve(pad[:, 0], kernel, mode="valid"),
                   np.convolve(pad[:, 1], kernel, mode="valid")], axis=1)
    return sm[:len(xy)]

def distance_total(xy: np.ndarray):
    if len(xy) < 2: return 0.0
    d = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    return float(d.sum())

def compute_distances(positions: dict, smooth_win: int = 5, fps: int = 25):
    out = {}
    for tid, traj in positions.items():
        frames = np.array([r[0] for r in traj])
        xy = np.array([(r[1], r[2]) for r in traj], dtype=np.float32)
        if len(xy) < 2:
            continue
        xy_sm = smooth_xy(xy, win=smooth_win)
        n_frames = len(xy)
        dur_s = (frames.max() - frames.min() + 1) / fps
        out[tid] = {
            "n_frames": int(n_frames),
            "dur_s": float(dur_s),
            "raw_m": distance_total(xy),
            "smoothed_m": distance_total(xy_sm),
        }
    return out

def gt_positions(gt_pts: list):
    """Return {gt_tid: [(frame, x_m, y_m), ...]} from GSR bbox_pitch directly (no homography needed).
    Used as the apples-to-apples truth reference for distance."""
    # NOTE: gt_pts lacks track_id; reconstruct from the JSON if needed. Reload here for simplicity.
    pass  # caller passes pre-loaded gt_by_tid

def gt_positions_by_tid(zip_path: Path, seq: str):
    """{gt_tid: [(frame, pt_x, pt_y), ...]} from Labels-GameState.json (players+GK only)."""
    z = zipfile.ZipFile(zip_path)
    with z.open(f"{seq}/Labels-GameState.json") as f:
        data = json.load(f)
    img_to_frame = {img["image_id"]: int(Path(img["file_name"]).stem) for img in data["images"]}
    out = defaultdict(list)
    for a in data["annotations"]:
        if a.get("category_id") not in (1, 2):
            continue
        bp = a.get("bbox_pitch")
        if not bp:
            continue
        frame = img_to_frame.get(a["image_id"])
        if frame is None:
            continue
        out[a["track_id"]].append((frame, bp["x_bottom_middle"], bp["y_bottom_middle"]))
    for tid in out:
        out[tid].sort(key=lambda r: r[0])
    return out

def render_heatmap(positions_xy: np.ndarray, out_path: Path, title: str, bins: int = 80):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10.5, 6.8), dpi=110)
    # Pitch background (FIFA approx 105 x 68 m, center origin)
    ax.set_xlim(-PITCH_X_HALF, PITCH_X_HALF)
    ax.set_ylim(-PITCH_Y_HALF, PITCH_Y_HALF)
    ax.set_aspect("equal")
    ax.set_facecolor("#2e7d32")
    # Outer rectangle
    ax.add_patch(plt.Rectangle((-PITCH_X_HALF, -PITCH_Y_HALF), 2*PITCH_X_HALF, 2*PITCH_Y_HALF, fill=False, ec="white", lw=2))
    # Halfway line + center circle
    ax.plot([0, 0], [-PITCH_Y_HALF, PITCH_Y_HALF], color="white", lw=1.5)
    ax.add_patch(plt.Circle((0, 0), 9.15, fill=False, ec="white", lw=1.5))
    # Penalty boxes (16.5 x 40.32 m)
    for sign in (-1, 1):
        ax.add_patch(plt.Rectangle((sign*PITCH_X_HALF - sign*16.5, -20.16), sign*16.5, 40.32, fill=False, ec="white", lw=1.5))
        ax.add_patch(plt.Rectangle((sign*PITCH_X_HALF - sign*5.5, -9.16), sign*5.5, 18.32, fill=False, ec="white", lw=1.5))
    # Density
    if len(positions_xy) > 0:
        h = ax.hist2d(positions_xy[:, 0], positions_xy[:, 1], bins=bins,
                      range=[[-PITCH_X_HALF, PITCH_X_HALF], [-PITCH_Y_HALF, PITCH_Y_HALF]],
                      cmap="hot", alpha=0.7)
    ax.set_title(title, color="white", fontsize=12)
    ax.set_xticks([]); ax.set_yticks([])
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, facecolor="#2e7d32", bbox_inches="tight")
    plt.close(fig)

# ---------- Static-H helper (operator-uploaded footage path) ----------
def _static_H_by_frame(homography_path, n_frames):
    import json as _json
    import numpy as _np
    H = _np.array(_json.load(open(homography_path))["H_court_from_img"], dtype=_np.float64)
    return {f: H for f in range(1, n_frames + 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", help="Seq name, e.g. SNGS-116")
    ap.add_argument("--zip", default="datasets/soccernet_gsr/test.zip")
    ap.add_argument("--tracker", default="outputs/track_results/sn_soccana_botsort_gmc")
    ap.add_argument("--out", default="outputs/deliverables")
    ap.add_argument("--smooth-win", type=int, default=5)
    ap.add_argument("--top-n-players", type=int, default=4, help="Render top-N most-tracked player heatmaps")
    ap.add_argument("--homography", default=None,
                    help="path to homography.json; use this static H instead of GT-derived per-frame H")
    args = ap.parse_args()

    out_dir = Path(args.out) / args.seq
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== {args.seq} ===")

    track = load_tracker(Path(args.tracker) / f"{args.seq}.txt")
    print(f"  tracker rows: {len(track)}")

    if args.homography:
        # Derive n_frames from max frame index in tracker MOT
        n_frames = max((row[0] for row in track), default=1)
        H_by_frame = _static_H_by_frame(args.homography, n_frames)
        n_frames_with_H = len(H_by_frame)
        print(f"  static H loaded from {args.homography}; n_frames={n_frames}")
        val_sum = {
            "n_frames_with_H": n_frames_with_H,
            "n_holdout_points": 0,
            "mean_err_m": None, "median_err_m": None,
            "p90_err_m": None, "p99_err_m": None,
        }
    else:
        gt_pts = load_gt(Path(args.zip), args.seq)
        print(f"  GT player+GK points: {len(gt_pts)}")
        H_by_frame, holdout = derive_per_frame_H(gt_pts)
        n_frames_with_H = len(H_by_frame)
        print(f"  per-frame H derived: {n_frames_with_H} frames")
        all_errs = [e for f, pts in holdout.items() for *_xy, e in pts]
        val_sum = {
            "n_frames_with_H": n_frames_with_H,
            "n_holdout_points": len(all_errs),
            "mean_err_m": float(np.mean(all_errs)) if all_errs else None,
            "median_err_m": float(np.median(all_errs)) if all_errs else None,
            "p90_err_m": float(np.percentile(all_errs, 90)) if all_errs else None,
            "p99_err_m": float(np.percentile(all_errs, 99)) if all_errs else None,
        }
        print(f"  validation: median_err={val_sum['median_err_m']:.2f}m  "
              f"mean={val_sum['mean_err_m']:.2f}m  p90={val_sum['p90_err_m']:.2f}m  p99={val_sum['p99_err_m']:.2f}m")

    positions = project_tracker(track, H_by_frame)
    print(f"  unique tracker IDs with projected positions: {len(positions)}")

    distances = compute_distances(positions, smooth_win=args.smooth_win)
    raw_total = sum(d["raw_m"] for d in distances.values())
    sm_total = sum(d["smoothed_m"] for d in distances.values())
    print(f"  TRACKER team distance: raw={raw_total:.0f}m  smoothed={sm_total:.0f}m  "
          f"(jitter inflation {100*(raw_total-sm_total)/sm_total:.0f}%)")

    # GT-derived team distance (validation-only; skipped when --homography is set)
    if not args.homography:
        gt_by_tid = gt_positions_by_tid(Path(args.zip), args.seq)
        gt_distances = compute_distances({tid: traj for tid, traj in gt_by_tid.items()},
                                         smooth_win=args.smooth_win)
        gt_raw = sum(d["raw_m"] for d in gt_distances.values())
        gt_sm = sum(d["smoothed_m"] for d in gt_distances.values())
        print(f"  GT      team distance: raw={gt_raw:.0f}m  smoothed={gt_sm:.0f}m  "
              f"({len(gt_by_tid)} GT tracks)")
        sm_err_pct = 100 * (sm_total - gt_sm) / gt_sm if gt_sm else None
        print(f"  TRACKER smoothed vs GT smoothed: +{sm_err_pct:.0f}%  "
              f"(tracker IDs={len(positions)} vs GT IDs={len(gt_by_tid)})")
    else:
        gt_raw = gt_sm = None
        sm_err_pct = None
        gt_by_tid = {}

    # Persist
    val_sum["team_distance_raw_m"] = raw_total
    val_sum["team_distance_smoothed_m"] = sm_total
    val_sum["team_distance_gt_smoothed_m"] = gt_sm
    val_sum["team_distance_gt_raw_m"] = gt_raw
    val_sum["smoothed_vs_gt_pct"] = sm_err_pct
    val_sum["n_tracker_ids"] = len(positions)
    val_sum["n_gt_ids"] = len(gt_by_tid)
    (out_dir / "validation.json").write_text(json.dumps(val_sum, indent=2))
    (out_dir / "positions.json").write_text(json.dumps(
        {str(tid): traj for tid, traj in positions.items()}, indent=2))
    (out_dir / "distances.json").write_text(json.dumps(
        {str(tid): d for tid, d in distances.items()}, indent=2))

    # Heatmaps
    team_xy = np.array([(r[1], r[2]) for traj in positions.values() for r in traj], dtype=np.float32)
    render_heatmap(team_xy, out_dir / "heatmap_team.png",
                   f"{args.seq} - team positional density (n={len(team_xy)} points, {n_frames_with_H} frames)")
    print(f"  team heatmap: {len(team_xy)} pts -> heatmap_team.png")

    # Per-player heatmaps for top-N most-tracked
    sorted_by_frames = sorted(positions.items(), key=lambda kv: -len(kv[1]))[:args.top_n_players]
    for tid, traj in sorted_by_frames:
        xy = np.array([(r[1], r[2]) for r in traj], dtype=np.float32)
        d = distances.get(tid, {})
        render_heatmap(xy, out_dir / f"heatmap_player{tid:03d}.png",
                       f"{args.seq} - player ID {tid} (n={len(xy)} pts, smoothed dist={d.get('smoothed_m',0):.0f}m)")
        print(f"  player {tid}: {len(xy)} pts -> heatmap_player{tid:03d}.png")

    print(f"  -> outputs at {out_dir}")

if __name__ == "__main__":
    main()
