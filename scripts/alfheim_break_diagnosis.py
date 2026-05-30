"""Day 30 PART B: diagnose WHY tracks break (before fixing -- the fix depends on the cause).

Day-29 = 5,106 IDs, median track life 1.3 s. A track "breaks" when it terminates and (usually) a
new track id spawns for the same player. We classify each track END by cause so the Part-C fix is
matched to the dominant cause (buffer/re-link for occlusion+flicker, association for fast-motion):

  EDGE        track ends near an image border -> player left the camera view (NOT re-linkable here)
  OCCLUSION   at the end frame another detection overlaps/abuts the ending track (players crossed)
  FLICKER     a successor track starts within 1-3 frames very close by -> detector dropped a frame
  FAST_MOTION successor starts a bit later, displaced along the track's velocity (gate too tight)
  GENUINE_END no successor appears nearby soon -> track really ended (long occlusion / left play)

A track END is "RE-LINKABLE" if a plausible successor exists (OCCLUSION/FLICKER/FAST_MOTION): same
player, motion-rejoinable WITHOUT appearance. That fraction is the headroom for Part-C re-linking.

Cross-check (occlusion truth): at break moments, were two ZXY home players actually close?

Inputs: MOT (Day-29) + homography (for pitch-space distances) + ZXY.
Output: outputs/alfheim/break_diagnosis.json

Usage: .venv\\Scripts\\python scripts\\alfheim_break_diagnosis.py --stride 2
"""
import argparse, json
from collections import defaultdict, Counter
from pathlib import Path
import numpy as np
import cv2

import sys; sys.path.insert(0, str(Path(__file__).parent))
from alfheim_trust_gate import load_zxy, zxy_at, mot_frame_walltime

IMG_W, IMG_H = 1280, 960
EDGE_PX = 45
OCC_PX = 55           # another detection center within this of the ending box center = overlap
MAX_GAP_FR = 30       # search successor within this many PROCESSED frames (~2 s at stride2/30fps)
FLICKER_GAP = 3       # successor within <=3 frames = detector flicker
LINK_PX = 90          # successor start within this pixel dist (after velocity prediction) = same player
MIN_LIFE = 2          # ignore 1-frame blips as "ends" (still counted in fragmentation elsewhere)


def load_tracks(path):
    by_track = defaultdict(list)         # tid -> [(frame, cx, cy, w, h)]
    by_frame = defaultdict(list)         # frame -> [(tid, cx, cy, w, h)]
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(","); f = int(p[0]); tid = int(p[1])
        x, y, w, h = map(float, p[2:6])
        cx, cy = x + w / 2, y + h / 2
        by_track[tid].append((f, cx, cy, w, h)); by_frame[f].append((tid, cx, cy, w, h))
    for t in by_track:
        by_track[t].sort()
    return by_track, by_frame


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mot", default="outputs/track_results/alfheim_fh_cam1/first_half.txt")
    ap.add_argument("--trust", default="outputs/alfheim/trust_gate.json")
    ap.add_argument("--zxy", default="datasets/alfheim/2013-11-03/zxy/2013-11-03_tromso_stromsgodset_first.csv")
    ap.add_argument("--stride", type=int, default=2)
    ap.add_argument("--out", default="outputs/alfheim/break_diagnosis.json")
    args = ap.parse_args()

    by_track, by_frame = load_tracks(args.mot)
    H = np.array(json.loads(Path(args.trust).read_text())["H"], np.float32)
    samples, times = load_zxy(args.zxy)

    # index track starts by frame for successor search
    starts = defaultdict(list)            # frame -> [(tid, cx, cy)]
    for tid, recs in by_track.items():
        f0, cx, cy, w, h = recs[0]
        starts[f0].append((tid, cx, cy))
    start_frames = sorted(starts)

    causes = Counter()
    occ_zxy_confirm = [0, 0]              # [confirmed two GT close, checked]
    relinkable = 0
    n_ends = 0
    for tid, recs in by_track.items():
        if len(recs) < MIN_LIFE:
            causes["BLIP_1frame"] += 1
            continue
        n_ends += 1
        fe, cx, cy, w, h = recs[-1]
        # velocity from last 2 samples
        if len(recs) >= 2:
            vx, vy = cx - recs[-2][1], cy - recs[-2][2]
        else:
            vx = vy = 0.0
        # EDGE?
        if cx < EDGE_PX or cx > IMG_W - EDGE_PX or cy < EDGE_PX or cy > IMG_H - EDGE_PX or (cy + h / 2) > IMG_H - EDGE_PX:
            causes["EDGE"] += 1
            continue
        # OCCLUSION at end frame? another detection overlapping
        occluder = False
        for (otid, ox, oy, ow, oh) in by_frame.get(fe, []):
            if otid == tid:
                continue
            if np.hypot(ox - cx, oy - cy) < OCC_PX:
                occluder = True; break
        # successor search
        succ = None
        for df in range(1, MAX_GAP_FR + 1):
            fcand = fe + df
            if fcand not in starts:
                continue
            px, py = cx + vx * df, cy + vy * df       # velocity-predicted position
            for (stid, sx, sy) in starts[fcand]:
                d = np.hypot(sx - px, sy - py)
                if d < LINK_PX:
                    succ = (df, d); break
            if succ:
                break
        if succ is None:
            causes["GENUINE_END"] += 1
            continue
        relinkable += 1
        df, d = succ
        if occluder:
            causes["OCCLUSION"] += 1
            # ZXY cross-check: were two home players close at break?
            zp = zxy_at(samples, times, mot_frame_walltime(fe, args.stride))
            if len(zp) >= 2:
                P = np.array([(x, y) for (x, y, s) in zp.values()])
                dmin = min(np.hypot(P[i, 0] - P[j, 0], P[i, 1] - P[j, 1])
                           for i in range(len(P)) for j in range(i + 1, len(P)))
                occ_zxy_confirm[1] += 1
                if dmin < 3.0:
                    occ_zxy_confirm[0] += 1
        elif df <= FLICKER_GAP:
            causes["FLICKER"] += 1
        else:
            causes["FAST_MOTION"] += 1

    total = sum(causes.values())
    pct = {k: round(100 * v / max(1, total), 1) for k, v in causes.most_common()}
    report = {
        "mot": args.mot, "total_tracks": len(by_track), "classified_ends": total,
        "cause_counts": dict(causes.most_common()),
        "cause_pct": pct,
        "relinkable_ends": relinkable,
        "relinkable_pct_of_nonblip": round(100 * relinkable / max(1, n_ends), 1),
        "occlusion_zxy_confirmed": {"two_GT_within_3m": occ_zxy_confirm[0],
                                    "occlusion_ends_checked": occ_zxy_confirm[1]},
        "params": {"EDGE_PX": EDGE_PX, "OCC_PX": OCC_PX, "MAX_GAP_FR": MAX_GAP_FR,
                   "FLICKER_GAP": FLICKER_GAP, "LINK_PX": LINK_PX},
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in (
        "total_tracks", "cause_pct", "relinkable_pct_of_nonblip", "occlusion_zxy_confirmed")}, indent=2))
    print(f"  -> {args.out}")


if __name__ == "__main__":
    main()
