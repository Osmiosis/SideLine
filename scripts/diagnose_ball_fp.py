"""Day 16 Part 0: DIAGNOSE the follow-cam wobble. NO fixes here -- evidence only.

Reconciles the Day-15 "notes say solved / eyes say wobbling" gap. Hypothesis (PRD): the A-feed
wobble is FALSE-POSITIVE LATCHING in the Day-14 ball track, not the held-ball loss the handoff
solved. The handoff only fires on status=='lost'; an FP is status=='detected', so the ball-faithful
A-feed confidently follows the FP and swings across the frame.

This script produces, WITHOUT changing any tracker:
  1. Quantitative FP-suspect breakdown of the Day-14 `trajectory.json` 'detected' frames, using two
     physical FP signatures that need no GT:
       - NO-PLAYER: the picked ball is far from EVERY player box (a basketball ball is almost always
         on/near a player -- held, dribbled, passed, or just-shot). Far-from-all-players => FP.
       - RESET-TELEPORT: a 'detected' frame that follows a max-gap reset and lands implausibly far
         from the last confident position (the ungated reset re-init is the suspected FP doorway).
  2. A decomposition of the A-feed ball-in-safezone misses into {edge-clamp, FP-suspect, fast-lag}
     -- to confirm the 0.51 is FP-latching, not just edge-clamp.
  3. A DEBUG-OVERLAY video (full frame) for the human eye: every raw detection (+conf), the picked
     Kalman ball (color by status), the nearest-player link, an FP-SUSPECT flag, the A-feed crop
     window + its target source {ball|pred|holder|centroid}. Watch the wobbles against this.

Inputs (read-only):
  outputs/ball_track_bb/<seq>/trajectory.json            (Day 14 track)
  outputs/det_cache/bb_ball/<seq>.txt                    (raw detections: frame,x,y,w,h,conf top-left)
  outputs/track_results/bb_ftdet_botsort_gmc/<seq>.txt   (Day 9 player tracks, MOT)
  outputs/follow_cam_bb/<seq>/follow_cam.json            (Day 15 A-feed paths + per-frame source)
  datasets/sportsmot_basketball/<seq>/img1/*.jpg

Usage:
  python scripts/diagnose_ball_fp.py v_00HRwkvvjtQ_c001            # metrics + overlay video
  python scripts/diagnose_ball_fp.py v_00HRwkvvjtQ_c001 --no-video # metrics only (fast)
"""
import argparse, json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent))

SEQS_DEFAULT = ["v_00HRwkvvjtQ_c001", "v_00HRwkvvjtQ_c007"]


def load_traj(p): return json.loads(Path(p).read_text())


def load_dets(path):
    """raw detection cache -> {frame: [(cx, cy, conf), ...]} (x,y top-left -> center)."""
    by = defaultdict(list)
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        q = line.split(",")
        f = int(float(q[0])); x = float(q[1]); y = float(q[2]); w = float(q[3]); h = float(q[4])
        c = float(q[5]) if len(q) > 5 else 1.0
        by[f].append((x + w / 2, y + h / 2, c))
    return by


def load_players_boxes(path):
    """MOT -> {frame: [(x0,y0,x1,y1,cx,cy), ...]} player boxes + centers (pixel)."""
    by = defaultdict(list)
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        q = line.split(",")
        f = int(q[0]); x = float(q[2]); y = float(q[3]); w = float(q[4]); h = float(q[5])
        by[f].append((x, y, x + w, y + h, x + w / 2, y + h / 2))
    return by


def pt_to_box_dist(px, py, box):
    """Euclidean distance from a point to a rectangle (0 if inside)."""
    x0, y0, x1, y1 = box[:4]
    dx = max(x0 - px, 0, px - x1)
    dy = max(y0 - py, 0, py - y1)
    return float(np.hypot(dx, dy))


def nearest_player_dist(px, py, boxes):
    if not boxes:
        return np.inf
    return min(pt_to_box_dist(px, py, b) for b in boxes)


def diagnose(seq, args):
    base = Path(args.ball_dir) / seq
    recs = load_traj(base / "trajectory.json")
    dets = load_dets(Path(args.cache_dir) / f"{seq}.txt")
    players = load_players_boxes(Path(args.track_dir) / f"{seq}.txt")
    n = len(recs)

    # --- per-frame diagnostics ---
    prox = np.full(n, np.nan)          # nearest-player-box distance of the picked ball
    teleport = np.full(n, np.nan)      # jump from previous provided position
    post_reset = np.zeros(n, bool)     # detected frame immediately after a >max_gap loss/predict run
    fp_noplayer = np.zeros(n, bool)
    fp_teleport = np.zeros(n, bool)

    prev_pos = None; prev_provided_frame = None; miss_run = 0
    for i, r in enumerate(recs):
        f = r["frame"]; s = r["status"]
        if s == "detected":
            px, py = r["x"], r["y"]
            prox[i] = nearest_player_dist(px, py, players.get(f, []))
            if prev_pos is not None:
                tp = float(np.hypot(px - prev_pos[0], py - prev_pos[1]))
                # normalize by the gap so a 1-frame jump and a 9-frame coast compare fairly
                gap = max(1, f - prev_provided_frame)
                teleport[i] = tp / gap
            if miss_run > args.max_gap:
                post_reset[i] = True
            # FP signatures
            if prox[i] > args.prox_px:
                fp_noplayer[i] = True
            if post_reset[i] and prev_pos is not None and teleport[i] > args.vel_gate:
                fp_teleport[i] = True
            prev_pos = (px, py); prev_provided_frame = f; miss_run = 0
        elif s == "predicted":
            prev_pos = (r["x"], r["y"]); prev_provided_frame = f; miss_run += 1
        else:  # lost
            miss_run += 1

    det_idx = [i for i in range(n) if recs[i]["status"] == "detected"]
    n_det = len(det_idx)
    fp_any = fp_noplayer | fp_teleport
    n_fp = int(fp_any[det_idx].sum())

    # --- A-feed safezone-miss decomposition (uses Day-15 follow_cam.json A path) ---
    fc_path = Path(args.fc_dir) / seq / "follow_cam.json"
    safezone = None
    if fc_path.exists():
        fc = json.loads(fc_path.read_text())
        cw, ch, W, H = fc["crop_w"], fc["crop_h"], fc["frame_w"], fc["frame_h"]
        A = {d["frame"]: (d["cx"], d["cy"]) for d in fc["variants"]["A"]}
        hw, hh = cw / 2 * args.safe_frac, ch / 2 * args.safe_frac
        hwf, hhf = cw / 2.0, ch / 2.0
        miss_clamp = miss_fp = miss_lag = inside = 0
        for i in det_idx:
            r = recs[i]; f = r["frame"]
            if f not in A:
                continue
            cx, cy = A[f]
            in_sz = abs(r["x"] - cx) <= hw and abs(r["y"] - cy) <= hh
            if in_sz:
                inside += 1; continue
            clamped = (cx <= hwf + 0.5 or cx >= W - hwf - 0.5 or
                       cy <= hhf + 0.5 or cy >= H - hhf - 0.5)
            if fp_any[i]:
                miss_fp += 1
            elif clamped:
                miss_clamp += 1
            else:
                miss_lag += 1
        tot = inside + miss_clamp + miss_fp + miss_lag
        safezone = dict(inside=inside, miss_fp=miss_fp, miss_clamp=miss_clamp, miss_lag=miss_lag,
                        total=tot, safezone_rate=inside / tot if tot else None)

    # --- report ---
    finite_prox = prox[det_idx][np.isfinite(prox[det_idx])]
    print(f"\n=== {seq} ===  frames={n}  detected={n_det}")
    st = {s: sum(1 for r in recs if r["status"] == s) for s in ("detected", "predicted", "lost")}
    print(f"  status: {st}")
    print(f"  picked-ball -> nearest-PLAYER-box dist (detected frames): "
          f"p50={np.percentile(finite_prox,50):.0f} p90={np.percentile(finite_prox,90):.0f} "
          f"max={finite_prox.max():.0f}  (>{args.prox_px:.0f}px = no-player FP)")
    print(f"  FP-SUSPECT detected frames: no-player={int(fp_noplayer[det_idx].sum())} "
          f"reset-teleport={int(fp_teleport[det_idx].sum())} "
          f"-> ANY={n_fp}/{n_det} ({100*n_fp/max(1,n_det):.1f}% of detected)")
    n_reset = int(post_reset.sum())
    print(f"  post-reset re-inits (ungated): {n_reset}  "
          f"(of which FP-teleport: {int(fp_teleport[det_idx].sum())})")
    if safezone:
        print(f"  A-feed safezone (det frames): inside={safezone['safezone_rate']:.3f} | "
              f"misses -> FP={safezone['miss_fp']} clamp={safezone['miss_clamp']} lag={safezone['miss_lag']}")
        print(f"    => of the safezone MISSES, FP-driven = "
              f"{100*safezone['miss_fp']/max(1,(safezone['miss_fp']+safezone['miss_clamp']+safezone['miss_lag'])):.1f}%")

    diag = dict(seq=seq, n_frames=n, n_detected=n_det, statuses=st,
                fp_noplayer=int(fp_noplayer[det_idx].sum()),
                fp_reset_teleport=int(fp_teleport[det_idx].sum()),
                fp_any=n_fp, fp_rate=n_fp / max(1, n_det),
                n_post_reset=n_reset,
                prox_p50=float(np.percentile(finite_prox, 50)),
                prox_p90=float(np.percentile(finite_prox, 90)),
                prox_max=float(finite_prox.max()), safezone=safezone,
                params=dict(prox_px=args.prox_px, vel_gate=args.vel_gate, max_gap=args.max_gap))

    # --- debug-overlay video (the human eye) ---
    if not args.no_video:
        render_overlay(seq, recs, dets, players, prox, fp_noplayer, fp_teleport, post_reset,
                       fc_path, args)
    return diag


def render_overlay(seq, recs, dets, players, prox, fp_noplayer, fp_teleport, post_reset, fc_path, args):
    frames_dir = Path(args.source) / seq / "img1"
    img0 = cv2.imread(str(frames_dir / "000001.jpg"))
    H, W = img0.shape[:2]
    A = src = None
    if fc_path.exists():
        fc = json.loads(fc_path.read_text())
        cw, ch = fc["crop_w"], fc["crop_h"]
        A = {d["frame"]: (d["cx"], d["cy"]) for d in fc["variants"]["A"]}
        src = {d["frame"]: d["src"] for d in fc["a_feed_source"]}
    out = Path(args.fc_dir) / seq / "debug_overlay_A.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    vw = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (W, H))
    SRCCOL = {"ball": (40, 240, 40), "pred": (40, 200, 240), "holder": (40, 120, 255),
              "centroid": (200, 80, 200)}
    for i, r in enumerate(recs):
        f = r["frame"]
        img = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
        if img is None:
            continue
        # all raw detections (gray) + conf
        for (dx, dy, dc) in dets.get(f, []):
            cv2.circle(img, (int(dx), int(dy)), 6, (180, 180, 180), 1)
            cv2.putText(img, f"{dc:.2f}", (int(dx) + 6, int(dy)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.4, (180, 180, 180), 1)
        # picked Kalman ball, color by status; FP-suspect -> red ring + label
        if r["status"] in ("detected", "predicted") and r["x"] is not None:
            bx, by = int(r["x"]), int(r["y"])
            col = (40, 220, 40) if r["status"] == "detected" else (240, 120, 40)
            cv2.circle(img, (bx, by), 13, col, 2)
            if r["status"] == "detected":
                # nearest-player link
                pj = players.get(f, [])
                if pj:
                    nb = min(pj, key=lambda b: pt_to_box_dist(r["x"], r["y"], b))
                    cv2.line(img, (bx, by), (int(nb[4]), int(nb[5])), (90, 90, 90), 1)
                if fp_noplayer[i] or fp_teleport[i]:
                    cv2.circle(img, (bx, by), 20, (0, 0, 255), 3)
                    tag = "FP:no-player" if fp_noplayer[i] else "FP:reset-teleport"
                    cv2.putText(img, tag, (bx + 14, by + 6), cv2.FONT_HERSHEY_SIMPLEX,
                                0.6, (0, 0, 255), 2)
                if post_reset[i]:
                    cv2.putText(img, "RESET", (bx + 14, by + 28), cv2.FONT_HERSHEY_SIMPLEX,
                                0.5, (0, 140, 255), 2)
        # A-feed crop window + target source
        if A and f in A:
            cx, cy = A[f]; s = src.get(f, "?")
            x0 = int(cx - cw / 2); y0 = int(cy - ch / 2)
            sc = SRCCOL.get(s, (255, 255, 255))
            cv2.rectangle(img, (x0, y0), (x0 + cw, y0 + ch), sc, 2)
            cv2.putText(img, f"A target: {s}", (x0 + 8, y0 + 24), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, sc, 2)
        cv2.putText(img, f"{seq} f{f} {r['status']}  dets={r.get('n_dets',len(dets.get(f,[])))}",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(img, "gray=raw det  green=detected  blue=predicted  RED=FP-suspect",
                    (10, H - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        vw.write(img)
    vw.release()
    print(f"  wrote debug overlay -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="?", default=None)
    ap.add_argument("--ball-dir", default="outputs/ball_track_bb")
    ap.add_argument("--cache-dir", default="outputs/det_cache/bb_ball")
    ap.add_argument("--track-dir", default="outputs/track_results/bb_ftdet_botsort_gmc")
    ap.add_argument("--fc-dir", default="outputs/follow_cam_bb")
    ap.add_argument("--source", default="datasets/sportsmot_basketball")
    ap.add_argument("--prox-px", type=float, default=150.0,
                    help="picked ball farther than this from EVERY player box = no-player FP")
    ap.add_argument("--vel-gate", type=float, default=100.0, help="Day-14 gate (for reset-teleport flag)")
    ap.add_argument("--max-gap", type=int, default=8, help="Day-14 max-predict-gap (reset boundary)")
    ap.add_argument("--safe-frac", type=float, default=0.7)
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--no-video", action="store_true")
    args = ap.parse_args()

    seqs = [args.seq] if args.seq else SEQS_DEFAULT
    allout = {}
    for seq in seqs:
        allout[seq] = diagnose(seq, args)
    outp = Path(args.fc_dir) / "_diagnose_fp.json"
    outp.write_text(json.dumps(allout, indent=2))
    print(f"\nwrote {outp}")


if __name__ == "__main__":
    main()
