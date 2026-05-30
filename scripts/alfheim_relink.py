"""Day 30 PART C: appearance-free OFFLINE gap re-linking (the big de-fragmentation lever).

Part B found the dominant break causes are OCCLUSION (35%) + edge/genuine ends; FLICKER is negligible
(0.7%) so no flicker-smoothing. The fix is OFFLINE gap re-linking on the Day-29 MOT (no re-track):
stitch a terminated track to a new track that appears shortly after, nearby, with consistent
position+VELOCITY -- pure motion, NO appearance (right for identical DPS house kits).

Offline gap re-linking with gap G is the post-hoc equivalent of `track_buffer=G`, but GLOBAL and
bidirectional (a live tracker can't look ahead) -> strictly more powerful, and free (no re-track).

OVER-LINK GUARD (the failure mode = merging two DIFFERENT players):
  * link in PITCH metres (via the fixed H), velocity-PREDICTED position, tight gate DIST_M
  * one-to-one: each ended track links to at most ONE successor and vice-versa (greedy by best score)
  * velocity-direction consistency
  * Part-A ZXY metric then checks merged tracks still map to ONE GT (purity must RISE, not just IDs fall)

Inputs: MOT (Day-29) + homography. Output: a relinked MOT + relabel stats.

Usage:
  .venv\\Scripts\\python scripts\\alfheim_relink.py --max-gap 30 --dist-m 3.0 \
     --out outputs/track_results/alfheim_fh_cam1/first_half_relinked.txt
"""
import argparse, json
from collections import defaultdict
from pathlib import Path
import numpy as np
import cv2

import sys; sys.path.insert(0, str(Path(__file__).parent))
from alfheim_trust_gate import FPS


def load_tracks(path):
    raw = defaultdict(list)              # tid -> [(frame, x, y, w, h)]  (top-left)
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(","); f = int(p[0]); tid = int(p[1])
        x, y, w, h = map(float, p[2:6])
        raw[tid].append((f, x, y, w, h))
    for t in raw:
        raw[t].sort()
    return raw


def foot_pitch(H, recs):
    pts = np.float32([[r[1] + r[3] / 2, r[2] + r[4]] for r in recs]).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, H).reshape(-1, 2)


def find(parent, a):
    while parent[a] != a:
        parent[a] = parent[parent[a]]; a = parent[a]
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mot", default="outputs/track_results/alfheim_fh_cam1/first_half.txt")
    ap.add_argument("--trust", default="outputs/alfheim/trust_gate.json")
    ap.add_argument("--stride", type=int, default=2)
    ap.add_argument("--max-gap", type=int, default=30, help="successor within this many processed frames")
    ap.add_argument("--dist-m", type=float, default=3.0, help="velocity-predicted pitch gate (m)")
    ap.add_argument("--max-speed", type=float, default=10.0, help="implied link speed cap (m/s)")
    ap.add_argument("--vel-win", type=int, default=4, help="frames to average end/start velocity")
    ap.add_argument("--out", default="outputs/track_results/alfheim_fh_cam1/first_half_relinked.txt")
    args = ap.parse_args()

    H = np.array(json.loads(Path(args.trust).read_text())["H"], np.float32)
    raw = load_tracks(args.mot)
    dt = args.stride / FPS

    # per-track endpoints in pitch metres + velocity (m/s)
    ends, starts = {}, {}
    for tid, recs in raw.items():
        pp = foot_pitch(H, recs)
        f_end = recs[-1][0]; p_end = pp[-1]
        f_start = recs[0][0]; p_start = pp[0]
        k = min(args.vel_win, len(recs) - 1)
        v_end = (pp[-1] - pp[-1 - k]) / (k * dt) if k >= 1 else np.zeros(2)
        v_start = (pp[k] - pp[0]) / (k * dt) if k >= 1 else np.zeros(2)
        ends[tid] = (f_end, p_end, v_end, len(recs))
        starts[tid] = (f_start, p_start, v_start, len(recs))

    # index starts by frame
    starts_by_frame = defaultdict(list)
    for tid, (f0, p0, v0, n) in starts.items():
        starts_by_frame[f0].append(tid)

    # candidate links: ended track A -> successor B (one-to-one, best score)
    cands = []   # (score, A, B)
    for A, (feA, pA, vA, nA) in ends.items():
        for df in range(1, args.max_gap + 1):
            fcand = feA + df
            for B in starts_by_frame.get(fcand, []):
                if B == A:
                    continue
                fB, pB, vB, nB = starts[B]
                pred = pA + vA * (df * dt)                 # velocity-predicted A position at fB
                d = float(np.hypot(*(pB - pred)))
                if d > args.dist_m:
                    continue
                implied_speed = float(np.hypot(*(pB - pA))) / max(1e-6, df * dt)
                if implied_speed > args.max_speed:
                    continue
                # velocity-direction consistency (skip if both moving and badly mis-aligned)
                if np.linalg.norm(vA) > 1.0 and np.linalg.norm(vB) > 1.0:
                    cosang = float(np.dot(vA, vB) / (np.linalg.norm(vA) * np.linalg.norm(vB)))
                    if cosang < -0.2:
                        continue
                score = d + 0.3 * df                        # prefer close + small gap
                cands.append((score, A, B))
    cands.sort()

    # greedy one-to-one assignment
    parent = {t: t for t in raw}
    used_A, used_B = set(), set()
    n_links = 0
    for score, A, B in cands:
        if A in used_A or B in used_B:
            continue
        used_A.add(A); used_B.add(B)
        parent[find(parent, B)] = find(parent, A)           # chain B into A's component
        n_links += 1

    # relabel
    comp_id = {}
    nid = 0
    out_lines = []
    new_ids = set()
    for tid, recs in raw.items():
        root = find(parent, tid)
        if root not in comp_id:
            nid += 1; comp_id[root] = nid
        cid = comp_id[root]; new_ids.add(cid)
    # write merged MOT (sorted by frame then id)
    rows = []
    for tid, recs in raw.items():
        cid = comp_id[find(parent, tid)]
        for (f, x, y, w, h) in recs:
            rows.append((f, cid, x, y, w, h))
    rows.sort()
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(f"{f},{cid},{x:.2f},{y:.2f},{w:.2f},{h:.2f},1.0,-1,-1,-1"
                             for (f, cid, x, y, w, h) in rows) + "\n")
    print(f"relink: {len(raw)} tracks -> {len(new_ids)} after {n_links} links  "
          f"(max_gap={args.max_gap} dist={args.dist_m}m)  -> {out}")
    return len(raw), len(new_ids), n_links


if __name__ == "__main__":
    main()
