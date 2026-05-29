"""Day 14: BASKETBALL ball tracking — pixel-space Kalman, basketball-tuned (Day-12 parity).

Reuses the Day-12 architecture (pixel-space constant-velocity Kalman, project-on-use) from
`analyze_ball.py` (we import BallKalman + the cache loader), with basketball-specific tuning
and validation because basketball ball motion + data differ from football:

  - Dribbles  : rapid vertical bounces — a CV model can't track the bounce; we coast brief
                dribble occlusions as short gaps (do NOT model the bounce).
  - Shots/lobs: high parabolic arcs — like football aerials these break the CV model; we FLAG
                high/fast-vertical segments as lower-confidence (do NOT model the parabola).
  - Held/occluded: the ball spends long stretches against bodies/in hands -> more/longer gaps
                than football -> the max-predict-gap before reset is SHORTER (a held ball that
                reappears elsewhere must not be linearly coasted through a long gap into fiction).

Validation reality (honest): basketball has no clean ungated ball-trajectory GT on disk, so the
default path is PLAUSIBILITY (in-frame %, sane pixel velocity, continuity) + VISUAL overlay.
If a frame-level ball GT file is passed via --gt (x,y per frame), we additionally run the full
football-parity RMSE + sanity gate. We never fake RMSE precision when no GT exists.

Cache format (Day-9 builder): frame,x,y,w,h,conf  (x,y = top-left; 1-indexed frames).

Outputs (outputs/ball_track_bb/<seq>/):
  trajectory.json   per-frame {frame,status,x,y,vx,vy,n_dets,picked_conf,shot_flag}
  validation.json   gap stats + plausibility (+ RMSE if --gt) + tuning used
  sample_frame.png  trail overlay (green=detected, blue=predicted, yellow=shot/high-ball)
  track_overlay.mp4 full overlay video (optional, --render-video; gitignored)

Usage:
  python scripts/analyze_ball_basketball.py v_00HRwkvvjtQ_c001 --max-gap 8 --vel-gate 100
  python scripts/analyze_ball_basketball.py            # all default seqs, metrics + sample frame
"""
import argparse, json, sys, configparser
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent))
from analyze_ball import BallKalman, load_cache  # reuse Day-12 Kalman + cache loader

SEQS_DEFAULT = ["v_00HRwkvvjtQ_c001", "v_00HRwkvvjtQ_c003", "v_00HRwkvvjtQ_c005",
                "v_00HRwkvvjtQ_c007", "v_00HRwkvvjtQ_c008"]


# ---------- Day-16: player-proximity prior (FP rejection) ----------
def load_player_boxes(path: Path):
    """MOT player tracks -> {frame: [(x0,y0,x1,y1), ...]} pixel boxes. A basketball ball is
    almost always on/near a player (held, dribbled, passed, just-shot); detections far from
    EVERY player box are crowd/banner/scoreboard FPs. (Day-16 diagnosis: these FPs, latched via
    the ungated reset re-init, drove the A-feed wobble — 44% of c001 'detected' frames.)"""
    from collections import defaultdict
    by = defaultdict(list)
    if not Path(path).exists():
        return {}
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        q = line.split(",")
        f = int(q[0]); x = float(q[2]); y = float(q[3]); w = float(q[4]); h = float(q[5])
        by[f].append((x, y, x + w, y + h))
    return dict(by)


def _pt_box_dist(px, py, box):
    """Point-to-rectangle distance (0 if inside the box)."""
    dx = max(box[0] - px, 0.0, px - box[2])
    dy = max(box[1] - py, 0.0, py - box[3])
    return (dx * dx + dy * dy) ** 0.5


def _near_player(x, y, boxes, prox_px):
    """True if (x,y) within prox_px of any player box. No boxes this frame -> don't block (True)."""
    if not boxes:
        return True
    return any(_pt_box_dist(x, y, b) <= prox_px for b in boxes)


def _in_head_zone(x, y, boxes, frac_h, frac_w):
    """Day-17: True if (x,y) sits in the HEAD region of any player box -- the top frac_h of the box
    height, within the central frac_w of its width. A head is the most player-PROXIMATE round,
    ball-sized object on court, so the Day-16 proximity prior cannot reject it; this geometric zone
    can. (Day-17 diagnosis: heads are NOT size-separable from the ball -- median area ratio ~1.0 --
    so the size gate is dead; head-zone geometry is the working lever.)"""
    for b in boxes:
        x0, y0, x1, y1 = b[0], b[1], b[2], b[3]
        w = x1 - x0; h = y1 - y0; cxb = (x0 + x1) / 2
        if (y0 <= y <= y0 + frac_h * h) and (abs(x - cxb) <= frac_w * w / 2):
            return True
    return False


# ---------- seq info ----------
def seq_info(source: Path, seq: str):
    cp = configparser.ConfigParser()
    cp.read(source / seq / "seqinfo.ini")
    s = cp["Sequence"]
    return (int(s["seqLength"]), int(s["imWidth"]), int(s["imHeight"]),
            s.get("imDir", "img1"), s.get("imExt", ".jpg"))


# ---------- Part A: gap characterization ----------
def gap_analysis(cache_by_frame: dict, n_frames: int):
    """Detection rate + consecutive-missing run-length distribution + detected-jump distribution
    (the basketball analogue of football's GT consec-jump, but on detections since we have no GT —
    informs the velocity gate)."""
    detected = set(cache_by_frame.keys())
    det_rate = len(detected) / n_frames

    gaps, cur = [], 0
    for f in range(1, n_frames + 1):
        if f in detected:
            if cur > 0:
                gaps.append(cur); cur = 0
        else:
            cur += 1
    if cur > 0:
        gaps.append(cur)
    gaps = np.array(gaps) if gaps else np.array([0])

    # detected-to-detected consecutive-frame pixel jumps (use highest-conf det per frame)
    def best(f):
        ds = cache_by_frame.get(f, [])
        return max(ds, key=lambda d: d[2])[:2] if ds else None
    jumps = []
    for f in range(1, n_frames):
        a, b = best(f), best(f + 1)
        if a and b:
            jumps.append(float(np.hypot(a[0] - b[0], a[1] - b[1])))
    jumps = np.array(jumps) if jumps else np.array([0.0])

    return {
        "det_rate": det_rate, "n_detected": len(detected), "n_frames": n_frames,
        "n_gaps": int((gaps > 0).sum()),
        "gap_mean": float(gaps.mean()), "gap_p50": float(np.percentile(gaps, 50)),
        "gap_p90": float(np.percentile(gaps, 90)), "gap_p99": float(np.percentile(gaps, 99)),
        "gap_max": int(gaps.max()),
        "det_jump_p50": float(np.percentile(jumps, 50)), "det_jump_p90": float(np.percentile(jumps, 90)),
        "det_jump_p99": float(np.percentile(jumps, 99)), "det_jump_max": float(jumps.max()),
    }


# ---------- Part B: basketball-tuned Kalman (mirrors analyze_ball.run_kalman, Q tunable) ----------
def run_kalman_bb(cache_by_frame: dict, n_frames: int, vel_gate_px: float, max_gap: int,
                  init_conf: float, q_pos: float, q_vel: float, r_meas: float,
                  players_by_frame: dict = None, reinit_prox_px: float = None,
                  ingate_prox_px: float = None, reacq_frames: int = 1,
                  reject_head: bool = False, motion_consistency: bool = False,
                  head_frac_h: float = 0.18, head_frac_w: float = 0.6, motion_speed: float = 8.0):
    """Constant-velocity pixel Kalman with FP velocity gate + max-predict-gap reset.
    Same logic as the football tracker; Q/R exposed so basketball's erratic motion can be tuned.

    Day-16 FP-rejection (active only when players_by_frame + a prox threshold are given):
      - reinit_prox_px : (RE)INITIALIZATION must land on a detection within this distance of a
        player box. Closes the FP doorway -- the ungated reset re-init was grabbing the highest-conf
        detection ANYWHERE (banner/scoreboard/crowd in frame corners) after a held-ball occlusion.
        A real ball re-emerges held/received AT a player, so proximity at re-init is correct and
        does not touch in-flight shot tracking (which re-acquires via the continuity gate below).
      - ingate_prox_px : in-gate acceptance also requires player-proximity (generous threshold) to
        stop an FP that sits within vel_gate of a drifting prediction. Set wide enough that shot
        apexes / long passes (a continuous trajectory off a player) survive.
      - reacq_frames : re-acquisition hysteresis. After a reset/loss, require this many CONSECUTIVE
        in-gate detections before committing to 'detected' (intermediate frames stay 'predicted'),
        so a single one-frame FP cannot yank the camera before the track is re-confirmed."""
    use_prox = players_by_frame is not None and reinit_prox_px is not None
    use_head = players_by_frame is not None and (reject_head or motion_consistency)

    def head_block(x, y, f, speed):
        """True if a detection at (x,y) should be rejected as a head FP this frame.
        reject_head: any head-zone detection. motion_consistency: head-zone ONLY when the ball is
        slow (a fast ball flying/arcing through head height -- pass/shot -- is allowed through)."""
        if not use_head:
            return False
        boxes = players_by_frame.get(f, [])
        if not _in_head_zone(x, y, boxes, head_frac_h, head_frac_w):
            return False
        if reject_head:
            return True
        return speed < motion_speed  # motion_consistency: only block slow (head-locked) picks

    def pick_init(dets, f):
        cand = [d for d in dets if d[2] >= init_conf]
        if use_prox:
            boxes = players_by_frame.get(f, [])
            cand = [d for d in cand if _near_player(d[0], d[1], boxes, reinit_prox_px)]
        if use_head:  # at (re)init there is no velocity yet -> treat as slow (block head-zone)
            cand = [d for d in cand if not head_block(d[0], d[1], f, 0.0)]
        return max(cand, key=lambda d: d[2]) if cand else None

    kf = BallKalman(q_pos=q_pos, q_vel=q_vel, r_meas=r_meas)
    out = []
    pending = 0  # consecutive in-gate detections seen during re-acquisition (hysteresis)
    for f in range(1, n_frames + 1):
        dets = cache_by_frame.get(f, [])
        rec = {"frame": f, "status": "lost", "x": None, "y": None, "vx": None, "vy": None,
               "n_dets": len(dets), "picked_conf": None}
        if not kf.initialized:
            b = pick_init(dets, f)
            if b:
                kf.init((b[0], b[1]))
                rec.update(status="detected", x=b[0], y=b[1], vx=0.0, vy=0.0, picked_conf=b[2])
            out.append(rec); continue
        pred = kf.predict()
        viable = [(dx, dy, dc, float(np.hypot(dx - pred[0], dy - pred[1])))
                  for (dx, dy, dc) in dets if np.hypot(dx - pred[0], dy - pred[1]) <= vel_gate_px]
        if use_prox and ingate_prox_px is not None:
            boxes = players_by_frame.get(f, [])
            viable = [v for v in viable if _near_player(v[0], v[1], boxes, ingate_prox_px)]
        if use_head:
            speed = float(np.hypot(kf.state[2], kf.state[3]))  # current ball speed (px/frame)
            viable = [v for v in viable if not head_block(v[0], v[1], f, speed)]
        if viable:
            viable.sort(key=lambda v: v[3])
            b = viable[0]
            # re-acquisition hysteresis: after a gap, require reacq_frames consecutive hits
            # (part of the Day-16 FP-fix package -> gated behind use_prox so the un-fixed path
            #  is byte-for-byte Day-14)
            if use_prox and kf.n_missed > 0 and reacq_frames > 1:
                pending += 1
                if pending < reacq_frames:
                    rec.update(status="predicted", x=float(pred[0]), y=float(pred[1]),
                               vx=float(kf.state[2]), vy=float(kf.state[3]))
                    kf.n_missed += 1
                    out.append(rec); continue
            pending = 0
            kf.update((b[0], b[1]))
            rec.update(status="detected", x=float(kf.state[0]), y=float(kf.state[1]),
                       vx=float(kf.state[2]), vy=float(kf.state[3]), picked_conf=b[2])
        else:
            pending = 0
            kf.n_missed += 1
            if kf.n_missed > max_gap:
                kf.reset()
                b = pick_init(dets, f)
                if b:
                    kf.init((b[0], b[1]))
                    rec.update(status="detected", x=b[0], y=b[1], vx=0.0, vy=0.0, picked_conf=b[2])
            else:
                rec.update(status="predicted", x=float(pred[0]), y=float(pred[1]),
                           vx=float(kf.state[2]), vy=float(kf.state[3]))
        out.append(rec)
    return out


# ---------- Part C: shot-arc / high-ball flag (pixel-based; flag, don't model) ----------
def flag_shots(records: list, H: int, y_high_frac: float, vy_fast: float):
    """Basketball analogue of football's aerial flag. Flag a frame lower-confidence if the ball
    is HIGH in the frame (small y -> top y_high_frac band, ~ near/above the rim) OR moving fast
    vertically (|vy| > vy_fast -> a shot/lob in flight). We flag, we do not model the parabola."""
    y_thresh = y_high_frac * H
    for r in records:
        r["shot_flag"] = False
        if r["x"] is None:
            continue
        high = r["y"] < y_thresh
        fast_vert = r["vy"] is not None and abs(r["vy"]) > vy_fast
        r["shot_flag"] = bool(high or fast_vert)
    return records


# ---------- Part D: validation ----------
def validate_plausibility(records: list, n_frames: int, W: int, H: int, vel_gate_px: float):
    """No-GT honest validation: coverage lift, in-frame %, pixel-velocity sanity, continuity."""
    pos = [r for r in records if r["status"] in ("detected", "predicted")]
    det = [r for r in records if r["status"] == "detected"]
    # coverage lift (no GT -> raw detected vs Kalman-provided; NO within-tol, that needs GT)
    raw_rate = len(det) / n_frames
    provided_rate = len(pos) / n_frames

    # in-frame fraction of Kalman-provided positions (predicted frames can drift out of frame)
    in_frame = sum(1 for r in pos if 0 <= r["x"] <= W and 0 <= r["y"] <= H)
    in_frame_rate = in_frame / len(pos) if pos else None

    # pixel-velocity sanity over the provided trajectory (consecutive provided frames)
    speeds = []
    prev = None
    for r in records:
        if r["status"] in ("detected", "predicted"):
            if prev is not None and prev["frame"] == r["frame"] - 1:
                speeds.append(float(np.hypot(r["x"] - prev["x"], r["y"] - prev["y"])))
            prev = r
        else:
            prev = None
    speeds = np.array(speeds) if speeds else np.array([0.0])

    # continuity: longest predict streak
    longest_pred, cur = 0, 0
    for r in records:
        if r["status"] == "predicted":
            cur += 1; longest_pred = max(longest_pred, cur)
        else:
            cur = 0

    return {
        "raw_detection_rate": raw_rate, "kalman_provided_rate": provided_rate,
        "coverage_lift_pp": (provided_rate - raw_rate),
        "in_frame_rate": in_frame_rate,
        "speed_p50": float(np.percentile(speeds, 50)), "speed_p90": float(np.percentile(speeds, 90)),
        "speed_p99": float(np.percentile(speeds, 99)), "speed_max": float(speeds.max()),
        "teleport_frac_over_gate": float((speeds > vel_gate_px).mean()),
        "longest_predict_streak": longest_pred,
    }


def load_ball_gt_xy(path: Path):
    """Optional GT loader: tolerant of CSV/JSON {frame:[x,y]} or 'frame,x,y' lines. Returns {frame:(x,y)}."""
    if not path or not path.exists():
        return None
    txt = path.read_text().strip()
    try:
        data = json.loads(txt)
        return {int(k): (float(v[0]), float(v[1])) for k, v in data.items()}
    except Exception:
        out = {}
        for line in txt.splitlines():
            p = line.replace(",", " ").split()
            if len(p) >= 3:
                try:
                    out[int(float(p[0]))] = (float(p[1]), float(p[2]))
                except ValueError:
                    continue
        return out or None


def validate_rmse(records: list, gt: dict, tol_px: float = 50.0):
    """Football-parity RMSE when GT x,y per frame is available."""
    by = {"detected": [], "predicted": []}
    within = 0
    gt_frames = set(gt)
    provided = {r["frame"] for r in records if r["status"] in ("detected", "predicted")}
    for r in records:
        if r["status"] not in ("detected", "predicted") or r["frame"] not in gt:
            continue
        gx, gy = gt[r["frame"]]
        by[r["status"]].append((r["x"] - gx) ** 2 + (r["y"] - gy) ** 2)
        if np.hypot(r["x"] - gx, r["y"] - gy) <= tol_px:
            within += 1
    rmse = {k: (float(np.sqrt(np.mean(v))) if v else None) for k, v in by.items()}
    return {
        "rmse_detected_px": rmse["detected"], "rmse_predicted_px": rmse["predicted"],
        "n_detected_eval": len(by["detected"]), "n_predicted_eval": len(by["predicted"]),
        "gt_frame_count": len(gt_frames),
        "effective_within_tol_rate": within / len(gt_frames) if gt_frames else None,
        "kalman_provided_rate_vs_gt": len(provided & gt_frames) / len(gt_frames) if gt_frames else None,
        "tol_px": tol_px,
    }


# ---------- Part E: render ----------
COLOR = {"detected": (40, 220, 40), "predicted": (240, 120, 40)}  # green / blue(BGR)


def _pick_frame(records):
    """Pick a mid-clip detected frame that has predicted (gap-fill) frames in its trailing
    window — so the sample visibly shows the tracker coasting through a gap."""
    n = len(records); start = int(n * 0.3)
    for r in records:
        if r["frame"] >= start and r["status"] == "detected":
            win = [x for x in records if r["frame"] - 60 <= x["frame"] < r["frame"]]
            if any(x["status"] == "predicted" for x in win):
                return r["frame"]
    cand = [r["frame"] for r in records if r["status"] == "detected"]
    return cand[len(cand) // 2] if cand else n // 2


def render_sample(seq, records, frames_dir, out_path, frame_idx=None, n_trail=60):
    if frame_idx is None:
        frame_idx = _pick_frame(records)
    img = cv2.imread(str(frames_dir / f"{frame_idx:06d}.jpg"))
    if img is None:
        return None
    trail = [r for r in records if frame_idx - n_trail <= r["frame"] <= frame_idx
             and r["status"] in ("detected", "predicted")]
    for r in trail:
        c = (0, 200, 255) if r["shot_flag"] else COLOR[r["status"]]
        cv2.circle(img, (int(r["x"]), int(r["y"])), 4, c, -1)
    cur = next((r for r in records if r["frame"] == frame_idx), None)
    if cur and cur["status"] in ("detected", "predicted"):
        c = (0, 200, 255) if cur["shot_flag"] else COLOR[cur["status"]]
        cv2.circle(img, (int(cur["x"]), int(cur["y"])), 14, c, 2)
        cv2.putText(img, f"f{frame_idx} {cur['status']}", (int(cur["x"]) + 12, int(cur["y"]) - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 2)
    cv2.putText(img, "detected (green)  predicted (blue)  shot/high-ball (yellow)",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
    cv2.imwrite(str(out_path), img)
    return frame_idx


def render_video(seq, records, frames_dir, out_path, W, H, fps=25, n_trail=25):
    vw = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
    for i, r in enumerate(records):
        img = cv2.imread(str(frames_dir / f"{r['frame']:06d}.jpg"))
        if img is None:
            continue
        trail = [x for x in records[max(0, i - n_trail):i + 1]
                 if x["status"] in ("detected", "predicted")]
        for t in trail:
            c = (0, 200, 255) if t["shot_flag"] else COLOR[t["status"]]
            cv2.circle(img, (int(t["x"]), int(t["y"])), 3, c, -1)
        if r["status"] in ("detected", "predicted"):
            c = (0, 200, 255) if r["shot_flag"] else COLOR[r["status"]]
            cv2.circle(img, (int(r["x"]), int(r["y"])), 12, c, 2)
        cv2.putText(img, f"{seq} f{r['frame']} {r['status']}", (10, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        vw.write(img)
    vw.release()


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="?", default=None)
    ap.add_argument("--cache-dir", default="outputs/det_cache/bb_ball")
    ap.add_argument("--source", default="datasets/sportsmot_basketball")
    ap.add_argument("--out", default="outputs/ball_track_bb")
    ap.add_argument("--gt", default=None, help="optional ball GT x,y per frame (JSON {frame:[x,y]} or 'frame,x,y')")
    # basketball-tuned Kalman (recalibrated vs football's vel_gate=150 / max_gap=15)
    ap.add_argument("--vel-gate", type=float, default=100.0, help="FP velocity gate px/frame (basketball court/cam)")
    ap.add_argument("--max-gap", type=int, default=8, help="max consecutive predict-only frames (SHORTER than football: occlusion-heavy)")
    ap.add_argument("--init-conf", type=float, default=0.35)
    ap.add_argument("--q-pos", type=float, default=4.0)
    ap.add_argument("--q-vel", type=float, default=16.0, help="velocity process noise (raise for erratic motion)")
    ap.add_argument("--r-meas", type=float, default=9.0)
    # court-region prior: drop ball detections in the top banner/scoreboard strip. These are
    # high-CONFIDENCE static FPs (banner text / logos read as 'Basketball') that the velocity
    # gate can't reject (they don't move), so the Kalman would lock onto them.
    ap.add_argument("--court-top-frac", type=float, default=0.10, help="drop ball dets with y_center < this*H (above the court)")
    # Day-16 player-proximity FP rejection (the wobble fix). Off unless --require-player.
    ap.add_argument("--require-player", action="store_true",
                    help="gate ball (re)init + in-gate acceptance on nearness to a player box (kills banner/crowd/scoreboard FPs)")
    ap.add_argument("--track-dir", default="outputs/track_results/bb_ftdet_botsort_gmc",
                    help="player tracks (MOT) for the proximity prior")
    ap.add_argument("--reinit-prox", type=float, default=150.0,
                    help="(re)init detection must be within this px of a player box (ball re-emerges AT a player)")
    ap.add_argument("--ingate-prox", type=float, default=300.0,
                    help="in-gate detection must be within this px of a player box (generous; shots/long passes survive)")
    ap.add_argument("--reacq-frames", type=int, default=2,
                    help="re-acquisition hysteresis: consecutive in-gate hits required after a gap before re-locking")
    # Day-17 head-FP fixes (separately gated for A/B isolation; need --require-player for boxes)
    ap.add_argument("--reject-head", action="store_true",
                    help="FIX#1: reject ball detections in a player's head zone (top frac of box)")
    ap.add_argument("--motion-consistency", action="store_true",
                    help="FIX#3: reject head-zone detections ONLY when the ball is slow (fast pass/shot through head height survives)")
    ap.add_argument("--head-frac-h", type=float, default=0.18, help="head zone = top this frac of player box height")
    ap.add_argument("--head-frac-w", type=float, default=0.6, help="head zone = central this frac of player box width")
    ap.add_argument("--motion-speed", type=float, default=8.0, help="px/frame: below this the ball is 'slow' (head-lock) for motion-consistency")
    # Day-19 appearance filter (ball-vs-head crop classifier as a pre-Kalman veto)
    ap.add_argument("--appearance-filter", default=None,
                    help="path to outputs/ball_head/filter.pt -- veto non-ball (head/junk) detections by appearance before the Kalman")
    ap.add_argument("--appear-thr", type=float, default=None, help="override the saved classifier threshold")
    # shot flag (pixel-only: lean on fast-vertical motion -- image-y conflates far-court w/ airborne)
    ap.add_argument("--y-high-frac", type=float, default=0.15, help="ball-y above this frac of H = upper-court/high")
    ap.add_argument("--vy-fast", type=float, default=15.0, help="|vy| above this px/frame = fast-vertical (shot/lob)")
    ap.add_argument("--tol-px", type=float, default=50.0)
    ap.add_argument("--render-video", action="store_true")
    args = ap.parse_args()

    seqs = [args.seq] if args.seq else SEQS_DEFAULT
    gt = load_ball_gt_xy(Path(args.gt)) if args.gt else None
    summary = {}
    for seq in seqs:
        print(f"\n=== {seq} ===")
        out_seq = Path(args.out) / seq
        out_seq.mkdir(parents=True, exist_ok=True)
        n_frames, W, H, im_dir, im_ext = seq_info(Path(args.source), seq)
        frames_dir = Path(args.source) / seq / im_dir
        if args.appearance_filter:
            # Day-19: appearance ball-vs-head veto BEFORE the Kalman. Operate on full (cx,cy,w,h,conf)
            # detections (need box size to crop), then hand the survivors to the pipeline as centers.
            from diagnose_ball_fp import load_dets_full
            from ball_appearance_filter import filter_detections
            full = load_dets_full(Path(args.cache_dir) / f"{seq}.txt")
            full, afst = filter_detections(full, frames_dir, args.appearance_filter, args.appear_thr)
            cache = {f: [(cx, cy, c) for (cx, cy, w, h, c) in dets] for f, dets in full.items()}
            print(f"  appearance filter ({Path(args.appearance_filter).name} thr={afst['thr']:.2f}): "
                  f"kept {afst['n_out']}/{afst['n_in']} dets (dropped {afst['n_dropped']} non-ball/head)")
        else:
            cache = load_cache(Path(args.cache_dir) / f"{seq}.txt")

        # court-region prior: drop detections above the court (banner/scoreboard static FPs)
        court_top = args.court_top_frac * H
        n_before = sum(len(v) for v in cache.values())
        cache = {f: [d for d in ds if d[1] >= court_top] for f, ds in cache.items()}
        cache = {f: ds for f, ds in cache.items() if ds}
        n_removed = n_before - sum(len(v) for v in cache.values())
        print(f"  court-region filter (y>= {court_top:.0f}px): dropped {n_removed}/{n_before} dets "
              f"({100*n_removed/max(1,n_before):.1f}%)")

        ga = gap_analysis(cache, n_frames)
        print(f"  frames={n_frames} {W}x{H} | det_rate={ga['det_rate']:.3f} "
              f"({ga['n_detected']}/{n_frames}) | gaps: n={ga['n_gaps']} "
              f"mean={ga['gap_mean']:.1f} p90={ga['gap_p90']:.0f} max={ga['gap_max']}")
        print(f"  detected consec-jump px: p50={ga['det_jump_p50']:.0f} p90={ga['det_jump_p90']:.0f} "
              f"p99={ga['det_jump_p99']:.0f} max={ga['det_jump_max']:.0f}  (informs --vel-gate)")

        players_bf = None
        if args.require_player or args.reject_head or args.motion_consistency:
            players_bf = load_player_boxes(Path(args.track_dir) / f"{seq}.txt")
            npf = sum(len(v) for v in players_bf.values())
            head = (" | HEAD-FIX: reject-head" if args.reject_head else
                    " | HEAD-FIX: motion-consistency" if args.motion_consistency else "")
            print(f"  player priors ON: {len(players_bf)} frames w/ boxes ({npf} boxes) | "
                  f"reinit<= {args.reinit_prox:.0f}px ingate<= {args.ingate_prox:.0f}px reacq={args.reacq_frames}{head}")
        records = run_kalman_bb(cache, n_frames, args.vel_gate, args.max_gap, args.init_conf,
                                args.q_pos, args.q_vel, args.r_meas,
                                players_by_frame=players_bf,
                                reinit_prox_px=args.reinit_prox if args.require_player else None,
                                ingate_prox_px=args.ingate_prox if args.require_player else None,
                                reacq_frames=args.reacq_frames,
                                reject_head=args.reject_head, motion_consistency=args.motion_consistency,
                                head_frac_h=args.head_frac_h, head_frac_w=args.head_frac_w,
                                motion_speed=args.motion_speed)
        st = {s: sum(1 for r in records if r["status"] == s) for s in ("detected", "predicted", "lost")}
        records = flag_shots(records, H, args.y_high_frac, args.vy_fast)
        n_shot = sum(1 for r in records if r["shot_flag"])
        n_pos = st["detected"] + st["predicted"]
        print(f"  Kalman: {st} | shot/high-ball flagged: {n_shot} ({100*n_shot/max(1,n_pos):.1f}% of provided)")

        val = {"gap_analysis": ga, "tuning": {
            "vel_gate": args.vel_gate, "max_gap": args.max_gap, "q_pos": args.q_pos,
            "q_vel": args.q_vel, "r_meas": args.r_meas, "y_high_frac": args.y_high_frac,
            "vy_fast": args.vy_fast, "require_player": args.require_player,
            "reinit_prox": args.reinit_prox if args.require_player else None,
            "ingate_prox": args.ingate_prox if args.require_player else None,
            "reacq_frames": args.reacq_frames if args.require_player else None},
            "statuses": st, "n_shot_flag": n_shot}
        plaus = validate_plausibility(records, n_frames, W, H, args.vel_gate)
        val["plausibility"] = plaus
        print(f"  coverage: raw={plaus['raw_detection_rate']:.3f} -> Kalman={plaus['kalman_provided_rate']:.3f} "
              f"(+{plaus['coverage_lift_pp']*100:.1f}pp) | in-frame={plaus['in_frame_rate']:.3f} | "
              f"speed p90={plaus['speed_p90']:.0f} p99={plaus['speed_p99']:.0f} | longest-pred={plaus['longest_predict_streak']}")
        if gt:
            val["rmse"] = validate_rmse(records, gt, args.tol_px)
            val["validation_rigor"] = "RMSE (GT available)"
            print(f"  RMSE detected={val['rmse']['rmse_detected_px']} predicted={val['rmse']['rmse_predicted_px']} "
                  f"eff-within-{args.tol_px:.0f}px={val['rmse']['effective_within_tol_rate']}")
        else:
            val["validation_rigor"] = "plausibility-only (no GT RMSE)"

        frames_dir = Path(args.source) / seq / im_dir
        chosen = render_sample(seq, records, frames_dir, out_seq / "sample_frame.png")
        print(f"  sample frame @ {chosen}")
        if args.render_video:
            render_video(seq, records, frames_dir, out_seq / "track_overlay.mp4", W, H)
            print(f"  rendered track_overlay.mp4")

        (out_seq / "trajectory.json").write_text(json.dumps(records, indent=2))
        (out_seq / "validation.json").write_text(json.dumps(val, indent=2))
        summary[seq] = val

    if len(summary) > 1:
        print(f"\n=== combined ({len(summary)} seqs) ===")
        rr = [v["plausibility"]["raw_detection_rate"] for v in summary.values()]
        kr = [v["plausibility"]["kalman_provided_rate"] for v in summary.values()]
        print(f"  raw det rate: mean={np.mean(rr):.3f} [{min(rr):.3f},{max(rr):.3f}]")
        print(f"  Kalman-provided: mean={np.mean(kr):.3f} [{min(kr):.3f},{max(kr):.3f}]  "
              f"(+{(np.mean(kr)-np.mean(rr))*100:.1f}pp lift)")
        sf = [v["n_shot_flag"] for v in summary.values()]
        print(f"  shot-flag frames: mean={np.mean(sf):.0f}")


if __name__ == "__main__":
    main()
