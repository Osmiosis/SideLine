"""Day 32: Formation-INVARIANT dead-ball identity anchor (PROBE).

One appearance-free lever against full-match identity drift, untried before (Day-30 settled that
local motion re-linking + appearance can't fix the fragmentation). IDEA: at settled/dead-ball
moments the ~22 players hold a spread formation; register the CURRENT settled position-set to the
PREVIOUS dead-ball's set (point-set registration, NO assumed tactical template -> transfers to DPS
school games), and use the recovered correspondence to RE-PIN identity across the gap (merge the
fragments that map to the same registered player).

Honest scope (PRD): anchors are SPARSE (kickoff, post-goal, settled restarts) -> this BOUNDS drift
by periodic reset, it CANNOT prevent the fragmentation accumulating BETWEEN anchors. Realistic best
case = MODEST lift. Measure-first; the ZXY scorer (alfheim_identity_metric.py) is the verdict.

PART A: detect settled anchor frames from motion (low median player speed + spread + in-view count,
        sustained). PART B: trimmed rigid ICP between consecutive anchor sets (rotation+translation,
        geometry only) -> union-find merge of corresponded track IDs -> relabeled MOT.

Inputs: re-linked MOT (Day-30 safe -18%) + fixed H (trust_gate) + ZXY (for genuineness/over-merge check).
Output: outputs/track_results/alfheim_fh_cam1/first_half_formation_anchor.txt
        outputs/alfheim/formation_anchor_report.json

Usage:
  .venv\\Scripts\\python scripts\\alfheim_formation_anchor.py --detect-only   # tune Part A
  .venv\\Scripts\\python scripts\\alfheim_formation_anchor.py                  # full run
"""
import argparse, json
from collections import defaultdict
from pathlib import Path
import numpy as np
import cv2

import sys; sys.path.insert(0, str(Path(__file__).parent))
from alfheim_trust_gate import FPS, load_zxy, zxy_at, mot_frame_walltime
from alfheim_identity_metric import apply_H

IMG_W, IMG_H = 1280, 960


def load_mot_full(path):
    """-> rows[tid] = [(f,x,y,w,h)], and by_frame[f] = [(tid, footx, footy)]"""
    rows = defaultdict(list)
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(","); f = int(p[0]); tid = int(p[1])
        x, y, w, h = map(float, p[2:6])
        rows[tid].append((f, x, y, w, h))
    for t in rows:
        rows[t].sort()
    by_frame = defaultdict(list)
    for tid, rs in rows.items():
        for (f, x, y, w, h) in rs:
            by_frame[f].append((tid, x + w / 2.0, y + h))
    return rows, by_frame


def frame_signals(by_frame, H, stride):
    """per frame: (median player speed m/s, spread m, count, {tid:(px,py)}). speed from same-tid
    displacement to previous frame; dt = stride/FPS s (15 fps effective)."""
    frames = sorted(by_frame)
    dt = stride / FPS
    pitch_at = {}      # f -> {tid:(px,py)}
    for f in frames:
        dets = by_frame[f]
        pp = apply_H(H, [(d[1], d[2]) for d in dets])
        pitch_at[f] = {dets[i][0]: (float(pp[i][0]), float(pp[i][1])) for i in range(len(dets))}
    sig = {}
    prev = None
    for f in frames:
        cur = pitch_at[f]
        speeds = []
        if prev is not None and (f - prev) <= 2:        # consecutive-ish
            pc = pitch_at[prev]
            for tid, (x, y) in cur.items():
                if tid in pc:
                    d = np.hypot(x - pc[tid][0], y - pc[tid][1]) / (dt * (f - prev))
                    speeds.append(d)
        pts = np.array(list(cur.values()), float)
        spread = 0.0
        if len(pts) >= 3:
            c = pts.mean(0)
            spread = float(np.mean(np.hypot(pts[:, 0] - c[0], pts[:, 1] - c[1])))
        sig[f] = (float(np.median(speeds)) if speeds else np.nan, spread, len(cur), cur)
        prev = f
    return frames, sig, pitch_at


PITCH_CX, PITCH_CY = 52.5, 34.0   # centre spot (105x68 pitch)


def detect_kickoffs(frames, sig, speed_thr, min_players, min_len, merge_gap,
                    centre_r=10.0, max_in_centre=2):
    """User-suggested genuine-dead-ball filter: a KICKOFF has the centre circle ~empty + players
    split across the halfway line + very low motion. No ball needed -- inferred from player geometry.
    Far more specific than generic low-motion (which over-fires on this walk-heavy match)."""
    cand = []
    for f in frames:
        spd, spread, n, cur = sig[f]
        if np.isnan(spd) or spd > speed_thr or n < min_players:
            continue
        pts = np.array(list(cur.values()), float)
        in_centre = int(np.sum(np.hypot(pts[:, 0] - PITCH_CX, pts[:, 1] - PITCH_CY) <= centre_r))
        left = int(np.sum(pts[:, 0] < PITCH_CX)); right = int(np.sum(pts[:, 0] >= PITCH_CX))
        # centre near-empty AND both halves populated (teams in own halves)
        if in_centre <= max_in_centre and left >= 2 and right >= 2:
            cand.append(f)
    anchors = []
    if not cand:
        return anchors
    run = [cand[0]]
    for f in cand[1:]:
        if f - run[-1] <= merge_gap:
            run.append(f)
        else:
            if len(run) >= min_len:
                anchors.append(min(run, key=lambda x: sig[x][0]))
            run = [f]
    if len(run) >= min_len:
        anchors.append(min(run, key=lambda x: sig[x][0]))
    return anchors


def detect_anchors(frames, sig, speed_thr, spread_thr, min_players, min_len, merge_gap):
    """sustained low-motion + spread + enough in-view -> anchor = min-motion frame of each run."""
    cand = []
    for f in frames:
        spd, spread, n, _ = sig[f]
        if not np.isnan(spd) and spd <= speed_thr and spread >= spread_thr and n >= min_players:
            cand.append(f)
    # group consecutive candidates (within merge_gap processed frames) into runs
    anchors = []
    if not cand:
        return anchors
    run = [cand[0]]
    for f in cand[1:]:
        if f - run[-1] <= merge_gap:
            run.append(f)
        else:
            if len(run) >= min_len:
                anchors.append(min(run, key=lambda x: sig[x][0]))
            run = [f]
    if len(run) >= min_len:
        anchors.append(min(run, key=lambda x: sig[x][0]))
    return anchors


def trimmed_icp(P, Q, gate=6.0, iters=12):
    """rigid (rotation+translation, NO scale) trimmed ICP aligning P onto Q.
    P,Q: (n,2),(m,2). Returns correspondence list [(i,j)] (mutual NN within gate post-align)."""
    if len(P) < 2 or len(Q) < 2:
        return []
    A = P.copy()
    R = np.eye(2); t = np.zeros(2)
    for _ in range(iters):
        # nearest Q for each A within gate
        D = np.hypot(A[:, None, 0] - Q[None, :, 0], A[:, None, 1] - Q[None, :, 1])
        j = D.argmin(1); dmin = D[np.arange(len(A)), j]
        keep = dmin <= gate
        if keep.sum() < 2:
            break
        src = P[keep]; dst = Q[j[keep]]
        # Procrustes rigid fit src->dst (no scale)
        cs = src.mean(0); cd = dst.mean(0)
        Hm = (src - cs).T @ (dst - cd)
        U, _, Vt = np.linalg.svd(Hm)
        Rr = Vt.T @ U.T
        if np.linalg.det(Rr) < 0:
            Vt[-1] *= -1; Rr = Vt.T @ U.T
        tr = cd - Rr @ cs
        R, t = Rr, tr
        A = (P @ R.T) + t
    # final mutual NN within gate
    D = np.hypot(A[:, None, 0] - Q[None, :, 0], A[:, None, 1] - Q[None, :, 1])
    pairs = []
    for i in range(len(A)):
        j = int(D[i].argmin())
        if D[i, j] <= gate and int(D[:, j].argmin()) == i:   # mutual
            pairs.append((i, j))
    return pairs


def find(par, a):
    while par[a] != a:
        par[a] = par[par[a]]; a = par[a]
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mot", default="outputs/track_results/alfheim_fh_cam1/first_half_relink_mod.txt")
    ap.add_argument("--trust", default="outputs/alfheim/trust_gate.json")
    ap.add_argument("--zxy", default="datasets/alfheim/2013-11-03/zxy/2013-11-03_tromso_stromsgodset_first.csv")
    ap.add_argument("--stride", type=int, default=2)
    ap.add_argument("--speed-thr", type=float, default=1.2, help="median player speed floor for 'settled' (m/s)")
    ap.add_argument("--spread-thr", type=float, default=12.0, help="min spatial spread (m) -> formation-like")
    ap.add_argument("--min-players", type=int, default=6, help="min in-view tracks at an anchor")
    ap.add_argument("--min-len", type=int, default=4, help="min sustained candidate frames (~0.27s)")
    ap.add_argument("--merge-gap", type=int, default=15, help="group candidates within this gap into one run")
    ap.add_argument("--icp-gate", type=float, default=6.0, help="post-align correspondence gate (m)")
    ap.add_argument("--mode", choices=["settled", "kickoff"], default="settled",
                    help="settled=low-motion+spread; kickoff=centre-circle-empty+half-split (genuine dead-balls)")
    ap.add_argument("--detect-only", action="store_true")
    ap.add_argument("--out-mot", default="outputs/track_results/alfheim_fh_cam1/first_half_formation_anchor.txt")
    ap.add_argument("--out-report", default="outputs/alfheim/formation_anchor_report.json")
    args = ap.parse_args()

    H = np.array(json.loads(Path(args.trust).read_text())["H"], np.float32)
    rows, by_frame = load_mot_full(args.mot)
    frames, sig, pitch_at = frame_signals(by_frame, H, args.stride)

    spds = np.array([sig[f][0] for f in frames if not np.isnan(sig[f][0])])
    spreads = np.array([sig[f][1] for f in frames])
    counts = np.array([sig[f][2] for f in frames])
    print(f"[A] frames={len(frames)}  median-speed dist: p10={np.percentile(spds,10):.2f} "
          f"p50={np.percentile(spds,50):.2f} p90={np.percentile(spds,90):.2f} m/s")
    print(f"[A] spread dist: p10={np.percentile(spreads,10):.1f} p50={np.percentile(spreads,50):.1f} "
          f"p90={np.percentile(spreads,90):.1f} m  | in-view count p50={int(np.percentile(counts,50))}")

    if args.mode == "kickoff":
        anchors = detect_kickoffs(frames, sig, args.speed_thr, args.min_players,
                                  args.min_len, args.merge_gap)
    else:
        anchors = detect_anchors(frames, sig, args.speed_thr, args.spread_thr,
                                 args.min_players, args.min_len, args.merge_gap)
    print(f"[A] mode={args.mode}  anchors detected = {len(anchors)}")
    samples, times = load_zxy(args.zxy)
    anchor_info = []
    for a in anchors:
        spd, spread, n, _ = sig[a]
        when = mot_frame_walltime(a, args.stride)
        # ZXY home-team spread at this time (genuineness cross-check: real formation -> high GT spread)
        zp = zxy_at(samples, times, when)
        gxy = np.array([(v[0], v[1]) for v in zp.values()], float) if zp else np.empty((0, 2))
        gt_spread = float(np.mean(np.hypot(gxy[:, 0] - gxy[:, 0].mean(), gxy[:, 1] - gxy[:, 1].mean()))) \
            if len(gxy) >= 3 else None
        mins = (a - 1) * args.stride / FPS / 60.0
        anchor_info.append({"frame": a, "t_min": round(mins, 2), "median_speed_mps": round(spd, 2),
                            "track_spread_m": round(spread, 1), "in_view": n,
                            "zxy_home_spread_m": round(gt_spread, 1) if gt_spread else None,
                            "zxy_players": len(zp)})
    for ai in anchor_info:
        print(f"    f{ai['frame']} @{ai['t_min']:.1f}min  spd={ai['median_speed_mps']} "
              f"spread={ai['track_spread_m']}m n={ai['in_view']}  "
              f"ZXY-spread={ai['zxy_home_spread_m']}m ({ai['zxy_players']} GT)")

    if args.detect_only:
        Path(args.out_report).write_text(json.dumps(
            {"n_anchors": len(anchors), "anchors": anchor_info, "params": vars(args)}, indent=2))
        print(f"[A] detect-only -> {args.out_report}")
        return

    # ---- PART B: register consecutive anchor sets + union-find merge ----
    par = {t: t for t in rows}
    n_links = 0
    merge_pairs = []     # (tidA, tidB, anchorA_frame, anchorB_frame)
    for k in range(len(anchors) - 1):
        fa, fb = anchors[k], anchors[k + 1]
        ca, cb = sig[fa][3], sig[fb][3]
        tidsA = list(ca.keys()); tidsB = list(cb.keys())
        P = np.array([ca[t] for t in tidsA], float)
        Q = np.array([cb[t] for t in tidsB], float)
        pairs = trimmed_icp(P, Q, gate=args.icp_gate)
        for (i, j) in pairs:
            a, b = tidsA[i], tidsB[j]
            if find(par, a) != find(par, b):
                par[find(par, b)] = find(par, a); n_links += 1
            merge_pairs.append((a, b, fa, fb))

    # over-merge DIRECT check vs ZXY: at each merge, do both endpoints match the SAME GT player?
    from alfheim_identity_metric import GATE_M
    Hinv = np.linalg.inv(H)

    def gt_at_frame(f):
        when = mot_frame_walltime(f, args.stride)
        zp = zxy_at(samples, times, when)
        tags, xy = [], []
        for tag, (gx, gy, spd) in zp.items():
            px = cv2.perspectiveTransform(np.float32([[[gx, gy]]]), Hinv).reshape(2)
            if 0 <= px[0] < IMG_W and 0 <= px[1] < IMG_H:
                tags.append(tag); xy.append((gx, gy))
        return tags, (np.array(xy, float) if xy else np.empty((0, 2)))

    def match_gt(tid, f, cur):
        if tid not in cur:
            return None
        tags, G = gt_at_frame(f)
        if not len(G):
            return None
        p = np.array(cur[tid]); d = np.hypot(G[:, 0] - p[0], G[:, 1] - p[1])
        j = int(d.argmin())
        return tags[j] if d[j] <= GATE_M else None

    same_gt = diff_gt = undet = 0
    for (a, b, fa, fb) in merge_pairs:
        ga = match_gt(a, fa, sig[fa][3]); gb = match_gt(b, fb, sig[fb][3])
        if ga is None or gb is None:
            undet += 1
        elif ga == gb:
            same_gt += 1
        else:
            diff_gt += 1

    # relabel + write MOT
    comp = {}; nid = 0; out_rows = []
    for tid, rs in rows.items():
        r = find(par, tid)
        if r not in comp:
            nid += 1; comp[r] = nid
        for (f, x, y, w, h) in rs:
            out_rows.append((f, comp[r], x, y, w, h))
    out_rows.sort()
    Path(args.out_mot).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_mot).write_text("\n".join(
        f"{f},{cid},{x:.2f},{y:.2f},{w:.2f},{h:.2f},1.0,-1,-1,-1" for (f, cid, x, y, w, h) in out_rows) + "\n")

    report = {
        "mot_in": args.mot, "mot_out": args.out_mot,
        "n_anchors": len(anchors), "anchors": anchor_info,
        "n_merge_pairs": len(merge_pairs), "n_links_applied": n_links,
        "ids_before": len(rows), "ids_after": nid,
        "over_merge_direct_check": {
            "merges_same_GT": same_gt, "merges_DIFFERENT_GT": diff_gt,
            "merges_undetermined": undet,
            "note": "endpoints both GT-matched: same=good (re-pinned one player), DIFFERENT=over-merge"},
        "params": {k: getattr(args, k) for k in
                   ("speed_thr", "spread_thr", "min_players", "min_len", "merge_gap", "icp_gate")},
    }
    Path(args.out_report).write_text(json.dumps(report, indent=2))
    print(f"\n[B] anchors={len(anchors)}  merge_pairs={len(merge_pairs)}  links={n_links}  "
          f"IDs {len(rows)} -> {nid}")
    print(f"[B] over-merge direct check: same-GT={same_gt}  DIFFERENT-GT={diff_gt}  undet={undet}")
    print(f"[B] -> {args.out_mot}\n[B] -> {args.out_report}")


if __name__ == "__main__":
    main()
