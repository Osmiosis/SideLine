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
                  init_conf: float, q_pos: float, q_vel: float, r_meas: float):
    """Constant-velocity pixel Kalman with FP velocity gate + max-predict-gap reset.
    Same logic as the football tracker; Q/R exposed so basketball's erratic motion can be tuned."""
    kf = BallKalman(q_pos=q_pos, q_vel=q_vel, r_meas=r_meas)
    out = []
    for f in range(1, n_frames + 1):
        dets = cache_by_frame.get(f, [])
        rec = {"frame": f, "status": "lost", "x": None, "y": None, "vx": None, "vy": None,
               "n_dets": len(dets), "picked_conf": None}
        if not kf.initialized:
            conf = [d for d in dets if d[2] >= init_conf]
            if conf:
                b = max(conf, key=lambda d: d[2])
                kf.init((b[0], b[1]))
                rec.update(status="detected", x=b[0], y=b[1], vx=0.0, vy=0.0, picked_conf=b[2])
            out.append(rec); continue
        pred = kf.predict()
        viable = [(dx, dy, dc, float(np.hypot(dx - pred[0], dy - pred[1])))
                  for (dx, dy, dc) in dets if np.hypot(dx - pred[0], dy - pred[1]) <= vel_gate_px]
        if viable:
            viable.sort(key=lambda v: v[3])
            b = viable[0]
            kf.update((b[0], b[1]))
            rec.update(status="detected", x=float(kf.state[0]), y=float(kf.state[1]),
                       vx=float(kf.state[2]), vy=float(kf.state[3]), picked_conf=b[2])
        else:
            kf.n_missed += 1
            if kf.n_missed > max_gap:
                kf.reset()
                conf = [d for d in dets if d[2] >= init_conf]
                if conf:
                    b = max(conf, key=lambda d: d[2])
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

        records = run_kalman_bb(cache, n_frames, args.vel_gate, args.max_gap, args.init_conf,
                                args.q_pos, args.q_vel, args.r_meas)
        st = {s: sum(1 for r in records if r["status"] == s) for s in ("detected", "predicted", "lost")}
        records = flag_shots(records, H, args.y_high_frac, args.vy_fast)
        n_shot = sum(1 for r in records if r["shot_flag"])
        n_pos = st["detected"] + st["predicted"]
        print(f"  Kalman: {st} | shot/high-ball flagged: {n_shot} ({100*n_shot/max(1,n_pos):.1f}% of provided)")

        val = {"gap_analysis": ga, "tuning": {
            "vel_gate": args.vel_gate, "max_gap": args.max_gap, "q_pos": args.q_pos,
            "q_vel": args.q_vel, "r_meas": args.r_meas, "y_high_frac": args.y_high_frac,
            "vy_fast": args.vy_fast}, "statuses": st, "n_shot_flag": n_shot}
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
