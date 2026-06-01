"""Day 12: ball tracking via Kalman filter in PIXEL space.

Architecture (the deliverable-driven judgment call):
  - Smooth the ball trajectory where the noise + main consumer live: PIXELS.
  - Project to pitch only on-demand (per-frame H from Day 10) where an analytic needs meters.
  - Bonus: sidesteps the airborne-ball problem entirely -- a high ball has a valid PIXEL
    position; only PITCH projection breaks for aerials (flagged, not "solved").

Pipeline per seq:
  1. Load cached ball detections (soccana, --class-name=ball)
  2. Run constant-velocity Kalman in pixel (x_center, y_center).
     - FP velocity gate: reject detection if distance to predicted state > VEL_GATE_PX
     - Predict-only through gaps up to MAX_GAP_FRAMES
     - Re-init from next confident detection if exceeded
  3. Project trajectory to pitch using Day-10 per-frame H derived from GT correspondences;
     flag frames where projected pitch speed > AERIAL_PITCH_SPEED_THRESH m/s as aerial-suspect.
  4. Validate vs GSR ball GT (category_id=4, bbox_image.x_center, y_center):
     - GT-as-detection sanity gate: feed GT through Kalman -> RMSE ~0 expected
     - Real run: effective-recall lift (raw det rate -> Kalman post-gate frame coverage)
     - Predicted-frame pixel RMSE: only frames where Kalman PREDICTED (no real det) vs GT
     - Detected-frame pixel RMSE: sanity check (should be small but non-zero)
  5. Sample render: overlay color-coded trajectory on a sample frame
     (green=detected, blue=Kalman-predicted, red=lost/no-track).

Outputs:
  outputs/ball_track/<seq>/trajectory.json
  outputs/ball_track/<seq>/validation.json
  outputs/ball_track/<seq>/sample_frame.png

Usage:
  python scripts/analyze_ball.py [SNGS-118] [--vel-gate 80] [--max-gap 15]
"""
import argparse, json, sys, zipfile
from collections import defaultdict
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent))
from analyze_pitch import load_gt, derive_per_frame_H, PITCH_X_HALF, PITCH_Y_HALF

SEQS_DEFAULT = ["SNGS-116", "SNGS-117", "SNGS-118", "SNGS-119", "SNGS-120"]

# ---------- Kalman in pixel space ----------
class BallKalman:
    """Constant-velocity Kalman in 2D pixel space. State = [x, y, vx, vy].

    F = [[1,0,1,0],[0,1,0,1],[0,0,1,0],[0,0,0,1]]   (Δt = 1 frame)
    H = [[1,0,0,0],[0,1,0,0]]                       (observe x, y)
    """
    def __init__(self, q_pos=4.0, q_vel=16.0, r_meas=9.0):
        self.F = np.array([[1,0,1,0],[0,1,0,1],[0,0,1,0],[0,0,0,1]], dtype=np.float32)
        self.H = np.array([[1,0,0,0],[0,1,0,0]], dtype=np.float32)
        # Process noise: position drift slower than velocity drift
        self.Q = np.diag([q_pos, q_pos, q_vel, q_vel]).astype(np.float32)
        # Measurement noise (per-pixel)
        self.R = np.diag([r_meas, r_meas]).astype(np.float32)
        self.state = None       # (4,)
        self.P = None           # (4,4)
        self.initialized = False
        self.n_missed = 0

    def init(self, z):
        """Initialize from first detection z=(x,y)."""
        self.state = np.array([z[0], z[1], 0.0, 0.0], dtype=np.float32)
        # Start with high pos uncertainty + very high vel uncertainty
        self.P = np.diag([16.0, 16.0, 100.0, 100.0]).astype(np.float32)
        self.initialized = True
        self.n_missed = 0

    def predict(self):
        """Step state forward one frame; return predicted (x, y)."""
        if not self.initialized:
            return None
        self.state = self.F @ self.state
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.state[:2].copy()

    def update(self, z):
        """Standard Kalman update with measurement z = (x, y)."""
        y = np.array([z[0], z[1]], dtype=np.float32) - self.H @ self.state
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.state = self.state + K @ y
        self.P = (np.eye(4, dtype=np.float32) - K @ self.H) @ self.P
        self.n_missed = 0

    def reset(self):
        self.state = None
        self.P = None
        self.initialized = False
        self.n_missed = 0

# ---------- Detection cache loader ----------
def load_cache(cache_path: Path):
    """Return {frame: list of (x_center, y_center, conf)}."""
    by_frame = defaultdict(list)
    if not cache_path.exists():
        return by_frame
    for line in cache_path.read_text().splitlines():
        if not line.strip(): continue
        p = line.split(",")
        f = int(p[0])
        x = float(p[1]); y = float(p[2]); w = float(p[3]); h = float(p[4])
        c = float(p[5])
        by_frame[f].append((x + w/2, y + h/2, c))
    return by_frame

# ---------- Tracker driver ----------
def run_kalman(cache_by_frame: dict, n_frames: int,
               vel_gate_px: float, max_gap: int,
               init_conf: float = 0.35):
    """Return per-frame record: list of dicts with keys:
       frame, status ('detected'|'predicted'|'lost'), x, y, vx, vy, n_dets, picked_conf.
    """
    kf = BallKalman()
    out = []
    for f in range(1, n_frames + 1):
        dets = cache_by_frame.get(f, [])
        record = {"frame": f, "status": "lost", "x": None, "y": None,
                  "vx": None, "vy": None, "n_dets": len(dets), "picked_conf": None}
        if not kf.initialized:
            # Need to init from a confident detection
            confident = [d for d in dets if d[2] >= init_conf]
            if confident:
                # Highest confidence
                best = max(confident, key=lambda d: d[2])
                kf.init((best[0], best[1]))
                record.update({"status": "detected", "x": best[0], "y": best[1],
                               "vx": 0.0, "vy": 0.0, "picked_conf": best[2]})
            out.append(record); continue
        # Predict
        pred = kf.predict()
        # Apply FP velocity gate against candidate detections
        viable = []
        for (dx, dy, dc) in dets:
            d_pred = float(np.hypot(dx - pred[0], dy - pred[1]))
            if d_pred <= vel_gate_px:
                viable.append((dx, dy, dc, d_pred))
        if viable:
            # Pick the closest to predicted position (not highest confidence -- the gate already filtered)
            viable.sort(key=lambda v: v[3])
            best = viable[0]
            kf.update((best[0], best[1]))
            record.update({"status": "detected", "x": float(kf.state[0]), "y": float(kf.state[1]),
                           "vx": float(kf.state[2]), "vy": float(kf.state[3]),
                           "picked_conf": best[2]})
        else:
            # No usable detection -- predict only
            kf.n_missed += 1
            if kf.n_missed > max_gap:
                kf.reset()
                # Try to re-init from a confident det immediately (rare in same frame, but safe)
                confident = [d for d in dets if d[2] >= init_conf]
                if confident:
                    best = max(confident, key=lambda d: d[2])
                    kf.init((best[0], best[1]))
                    record.update({"status": "detected", "x": best[0], "y": best[1],
                                   "vx": 0.0, "vy": 0.0, "picked_conf": best[2]})
                else:
                    record["status"] = "lost"
            else:
                record.update({"status": "predicted", "x": float(pred[0]), "y": float(pred[1]),
                               "vx": float(kf.state[2]), "vy": float(kf.state[3])})
        out.append(record)
    return out

# ---------- Pitch projection + aerial flag ----------
def project_trajectory(records: list, H_by_frame: dict,
                       aerial_pitch_speed_thresh: float = 25.0, fps: int = 25):
    """Add pitch_x_m, pitch_y_m, aerial_suspect to each record.
    aerial_suspect = True if projected meter-speed > thresh (default 25 m/s) -- typical max
    ground ball ~30 m/s, so >25 implies aerial or noisy projection."""
    prev_pitch = None
    for rec in records:
        rec["pitch_x_m"] = None; rec["pitch_y_m"] = None; rec["aerial_suspect"] = False
        if rec["x"] is None: continue
        H = H_by_frame.get(rec["frame"])
        if H is None: continue
        pt = cv2.perspectiveTransform(
            np.array([[[rec["x"], rec["y"]]]], dtype=np.float32), H).ravel()
        rec["pitch_x_m"] = float(pt[0]); rec["pitch_y_m"] = float(pt[1])
        if prev_pitch is not None:
            dx = pt[0] - prev_pitch[0]; dy = pt[1] - prev_pitch[1]
            pitch_speed = float(np.hypot(dx, dy)) * fps  # m / s
            if pitch_speed > aerial_pitch_speed_thresh:
                rec["aerial_suspect"] = True
        prev_pitch = pt
    return records

# ---------- GSR ball GT ----------
def load_ball_gt(zip_path: Path, seq: str):
    """Return {frame: (x_center, y_center, x_pitch, y_pitch)} for category_id=4."""
    z = zipfile.ZipFile(zip_path)
    with z.open(f"{seq}/Labels-GameState.json") as f:
        data = json.load(f)
    img_to_frame = {img["image_id"]: int(Path(img["file_name"]).stem) for img in data["images"]}
    out = {}
    for a in data["annotations"]:
        if a.get("category_id") != 4: continue
        bi = a.get("bbox_image"); bp = a.get("bbox_pitch")
        if not bi: continue
        f = img_to_frame.get(a["image_id"])
        if f is None: continue
        out[f] = (
            bi["x_center"], bi["y_center"],
            bp["x_bottom_middle"] if bp else None,
            bp["y_bottom_middle"] if bp else None,
        )
    return out

# ---------- Sanity gate: GT as detection ----------
def sanity_gate_gt_as_detection(gt: dict, n_frames: int, vel_gate_px: float, max_gap: int):
    """Feed GT centers AS the detection stream and verify Kalman RMSE -> ~0."""
    cache = {f: [(v[0], v[1], 1.0)] for f, v in gt.items()}
    records = run_kalman(cache, n_frames, vel_gate_px=vel_gate_px, max_gap=max_gap)
    errs = []
    for rec in records:
        if rec["status"] in ("detected", "predicted") and rec["frame"] in gt:
            gx, gy, *_ = gt[rec["frame"]]
            errs.append((rec["x"] - gx)**2 + (rec["y"] - gy)**2)
    rmse = float(np.sqrt(np.mean(errs))) if errs else None
    return rmse, len(errs)

# ---------- Validation against GSR ball GT ----------
def validate(records: list, gt: dict, n_frames: int, tol_px: float = 50.0):
    """RMSE per-status; effective recall (frames where Kalman provided pos AND within tol of GT)."""
    by_status = {"detected": [], "predicted": []}
    for rec in records:
        if rec["status"] not in ("detected", "predicted"): continue
        if rec["frame"] not in gt: continue
        gx, gy, *_ = gt[rec["frame"]]
        sq = (rec["x"] - gx)**2 + (rec["y"] - gy)**2
        by_status[rec["status"]].append(sq)

    rmse = {k: float(np.sqrt(np.mean(v))) if v else None for k, v in by_status.items()}
    n_per = {k: len(v) for k, v in by_status.items()}

    # Coverage: of the GT-ball frames, how many did Kalman output a position?
    gt_frames = set(gt.keys())
    kalman_frames = {r["frame"] for r in records if r["status"] in ("detected", "predicted")}
    raw_det_frames = {r["frame"] for r in records if r["status"] == "detected"}

    # Effective coverage: provided AND within tol
    within = set()
    for rec in records:
        if rec["status"] not in ("detected", "predicted"): continue
        if rec["frame"] not in gt: continue
        gx, gy, *_ = gt[rec["frame"]]
        d = np.hypot(rec["x"] - gx, rec["y"] - gy)
        if d <= tol_px:
            within.add(rec["frame"])

    return {
        "rmse_detected_px": rmse["detected"], "n_detected_eval": n_per["detected"],
        "rmse_predicted_px": rmse["predicted"], "n_predicted_eval": n_per["predicted"],
        "gt_frame_count": len(gt_frames),
        "kalman_provided_frames": len(kalman_frames & gt_frames),
        "raw_detected_frames": len(raw_det_frames & gt_frames),
        "effective_coverage_within_tol_px": len(within & gt_frames),
        "raw_detection_rate": len(raw_det_frames & gt_frames) / len(gt_frames),
        "kalman_provided_rate": len(kalman_frames & gt_frames) / len(gt_frames),
        "effective_within_tol_rate": len(within & gt_frames) / len(gt_frames),
        "tol_px": tol_px,
    }

# ---------- Sample render ----------
def render_sample(seq: str, records: list, gt: dict, frames_dir: Path, out_path: Path,
                  frame_idx: int = None, n_trail: int = 60):
    """Pick a frame; draw the trail of the last N frames color-coded by status, GT in white."""
    if frame_idx is None:
        # Pick the densest non-aerial detected frame
        candidates = [r["frame"] for r in records if r["status"] == "detected" and not r["aerial_suspect"]]
        frame_idx = candidates[len(candidates)//2] if candidates else (len(records)//2 + 1)
    img = cv2.imread(str(frames_dir / f"{frame_idx:06d}.jpg"))
    if img is None: return None
    color_by_status = {
        "detected": (40, 220, 40),   # green
        "predicted": (240, 120, 40), # blue (BGR)
    }
    # Draw trail of last N frames (or N before frame_idx)
    trail = [r for r in records if frame_idx - n_trail <= r["frame"] <= frame_idx
             and r["status"] in ("detected", "predicted")]
    for i, r in enumerate(trail):
        c = color_by_status[r["status"]]
        if r.get("aerial_suspect"):
            c = (0, 200, 255)  # yellow override for aerial
        cv2.circle(img, (int(r["x"]), int(r["y"])), 4, c, -1)
    # Mark current ball with bigger circle
    cur = next((r for r in records if r["frame"] == frame_idx), None)
    if cur and cur["status"] in ("detected", "predicted"):
        c = color_by_status[cur["status"]]
        cv2.circle(img, (int(cur["x"]), int(cur["y"])), 14, c, 2)
        cv2.putText(img, f"f{frame_idx} {cur['status']}", (int(cur["x"]) + 12, int(cur["y"]) - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 2)
    # GT ball for reference (small white cross)
    if frame_idx in gt:
        gx, gy, *_ = gt[frame_idx]
        cv2.drawMarker(img, (int(gx), int(gy)), (255, 255, 255), cv2.MARKER_CROSS, 18, 2)
    # Legend
    cv2.putText(img, "GT (white +)  detected (green)  predicted (blue)  aerial (yellow)",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
    cv2.imwrite(str(out_path), img)
    return frame_idx

# ---------- Static-H helper (operator-uploaded footage path) ----------
def _static_H_by_frame(homography_path, n_frames):
    import json as _json
    import numpy as _np
    H = _np.array(_json.load(open(homography_path))["H_court_from_img"], dtype=_np.float64)
    return {f: H for f in range(1, n_frames + 1)}


# ---------- Main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="?", default=None, help="Single seq (omit -> run all 5)")
    ap.add_argument("--cache-dir", default="outputs/det_cache/sn_ball")
    ap.add_argument("--zip", default="datasets/soccernet_gsr/test.zip")
    ap.add_argument("--source", default="datasets/soccernet_tracking")
    ap.add_argument("--out", default="outputs/ball_track")
    ap.add_argument("--vel-gate", type=float, default=80.0, help="FP velocity gate (px/frame)")
    ap.add_argument("--max-gap", type=int, default=15, help="Max consecutive predict-only frames")
    ap.add_argument("--init-conf", type=float, default=0.35, help="Min conf to (re)initialize")
    ap.add_argument("--aerial-thresh", type=float, default=25.0, help="Pitch m/s above this = aerial-suspect")
    ap.add_argument("--tol-px", type=float, default=50.0, help="Effective-coverage tolerance px vs GT")
    ap.add_argument("--homography", default=None,
                    help="path to homography.json; use this static H instead of GT-derived per-frame H")
    args = ap.parse_args()

    seqs = [args.seq] if args.seq else SEQS_DEFAULT

    summary = {}
    for seq in seqs:
        print(f"\n=== {seq} ===")
        out_seq = Path(args.out) / seq
        out_seq.mkdir(parents=True, exist_ok=True)

        # Load detection cache + count frames
        cache = load_cache(Path(args.cache_dir) / f"{seq}.txt")
        import configparser
        cp = configparser.ConfigParser()
        cp.read(Path(args.source) / seq / "seqinfo.ini")
        n_frames = int(cp["Sequence"]["seqLength"])
        det_frames = len(cache)
        print(f"  raw cache: {det_frames}/{n_frames} frames have a ball det ({100*det_frames/n_frames:.1f}%)")

        # Load GT (skipped when --homography is set; no GT available for uploaded footage)
        if not args.homography:
            gt = load_ball_gt(Path(args.zip), seq)
            print(f"  GT ball frames: {len(gt)}/{n_frames}")
            rmse_gt, n_eval = sanity_gate_gt_as_detection(gt, n_frames, args.vel_gate, args.max_gap)
            print(f"  sanity gate (GT-as-det): RMSE={rmse_gt:.2f}px over {n_eval} evals")
        else:
            gt = {}
            rmse_gt, n_eval = None, 0

        # Kalman tracker on real detections
        records = run_kalman(cache, n_frames, vel_gate_px=args.vel_gate,
                             max_gap=args.max_gap, init_conf=args.init_conf)
        statuses = {"detected": 0, "predicted": 0, "lost": 0}
        for r in records: statuses[r["status"]] += 1
        print(f"  Kalman output: detected={statuses['detected']}, predicted={statuses['predicted']}, lost={statuses['lost']}")

        # Project to pitch
        if args.homography:
            H_by_frame = _static_H_by_frame(args.homography, n_frames)
        else:
            gt_pts = load_gt(Path(args.zip), seq)
            H_by_frame, _ = derive_per_frame_H(gt_pts)
        records = project_trajectory(records, H_by_frame,
                                     aerial_pitch_speed_thresh=args.aerial_thresh)
        n_aerial = sum(1 for r in records if r["aerial_suspect"])
        n_projected = sum(1 for r in records if r["pitch_x_m"] is not None)
        print(f"  projected to pitch: {n_projected}; aerial-suspect: {n_aerial} ({100*n_aerial/max(1,n_projected):.1f}%)")

        # Validate — GT-only; skip when running on operator footage (no GT).
        if args.homography:
            val = {}
        else:
            val = validate(records, gt, n_frames, tol_px=args.tol_px)
            print(f"  raw-det rate (frames vs GT): {val['raw_detection_rate']:.3f}")
            print(f"  Kalman-provided rate: {val['kalman_provided_rate']:.3f}")
            print(f"  Effective within {args.tol_px:.0f}px: {val['effective_within_tol_rate']:.3f}")
            print(f"  RMSE detected={val['rmse_detected_px']:.2f}px (n={val['n_detected_eval']})  "
                  f"predicted={val['rmse_predicted_px']:.2f}px (n={val['n_predicted_eval']})"
                  if val['rmse_predicted_px'] is not None
                  else f"  RMSE detected={val['rmse_detected_px']:.2f}px (n={val['n_detected_eval']})  no predicted-frame evals")

        # Render
        frames_dir = Path(args.source) / seq / "img1"
        chosen = render_sample(seq, records, gt, frames_dir, out_seq / "sample_frame.png")
        print(f"  rendered sample at frame {chosen}")

        # Persist
        (out_seq / "trajectory.json").write_text(json.dumps(records, indent=2))
        val["statuses"] = statuses
        val["sanity_gate_rmse_gt_as_det"] = rmse_gt
        val["n_aerial_suspect"] = n_aerial
        val["n_projected"] = n_projected
        (out_seq / "validation.json").write_text(json.dumps(val, indent=2))
        summary[seq] = val

    # Combined summary
    if len(summary) > 1:
        print(f"\n=== combined across {len(summary)} seqs ===")
        for k in ("raw_detection_rate", "kalman_provided_rate", "effective_within_tol_rate"):
            vals = [v[k] for v in summary.values() if v[k] is not None]
            print(f"  {k}: mean={np.mean(vals):.3f}  range=[{min(vals):.3f}, {max(vals):.3f}]")
        rmse_p = [v["rmse_predicted_px"] for v in summary.values() if v["rmse_predicted_px"] is not None]
        rmse_d = [v["rmse_detected_px"] for v in summary.values() if v["rmse_detected_px"] is not None]
        if rmse_p: print(f"  rmse_predicted_px: mean={np.mean(rmse_p):.2f}  (n_seqs={len(rmse_p)})")
        if rmse_d: print(f"  rmse_detected_px: mean={np.mean(rmse_d):.2f}")

if __name__ == "__main__":
    main()
