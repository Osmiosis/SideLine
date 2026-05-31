"""Day 30 PART A: a REAL identity-stability metric vs ZXY ground truth (not raw ID count).

Day-29 found 5,106 tracked IDs for ~22 players (232x fragmentation). But raw ID count is a proxy
inflated by the away team + refs + ghost detections. The REAL question is identity STABILITY:
how consistently does ONE tracked ID follow ONE real player? ZXY GT (home team, ~11 players,
pitch positions @ ~16 Hz) lets us measure it.

Method (reuses the Day-29 ZXY-refined homography + 30 fps time-sync -- do NOT re-break it):
  per processed frame -> map tracked foot-points to pitch (fixed H) -> Hungarian-match to the
  in-view ZXY home players (gate GATE_M metres) -> accumulate, per GT player, the timeline of which
  tracked-ID covered them. From that:
    * IDs-per-GT-player  = distinct tracked IDs matched to a GT player = the REAL fragmentation
    * identity purity    = fraction of a GT's matched frames held by its DOMINANT tracked ID (AssA-like)
    * ID switches        = transitions between different tracked IDs along a GT timeline
    * IDF1               = standard identity-F1 over the GT<->track cooccurrence (Hungarian/IDTP)

Caveat: ZXY = home team only -> this is HOME-team identity stability. Still a real GT metric.

Inputs:
  --mot   outputs/track_results/alfheim_fh_cam1/first_half.txt   (or any re-linked MOT, Part C)
  --trust outputs/alfheim/trust_gate.json                        (fixed homography H)
  --zxy   datasets/.../2013-11-03_tromso_stromsgodset_first.csv

Output:
  outputs/alfheim/identity_metric[_<tag>].json

Usage:
  .venv\\Scripts\\python scripts\\alfheim_identity_metric.py --stride 2
  .venv\\Scripts\\python scripts\\alfheim_identity_metric.py --mot <relinked.txt> --tag relinked
"""
import argparse, json
from collections import defaultdict, Counter
from datetime import timedelta
from pathlib import Path
import numpy as np
import cv2
from scipy.optimize import linear_sum_assignment

import sys; sys.path.insert(0, str(Path(__file__).parent))
from alfheim_trust_gate import T0, FPS, load_zxy, zxy_at, mot_frame_walltime

GATE_M = 3.0          # pitch-distance gate for tracked<->GT match (homography err ~1.78 m)
IMG_W, IMG_H = 1280, 960


def load_mot(path):
    by_frame = defaultdict(list)   # frame -> [(tid, footx, footy)]
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(","); f = int(p[0]); tid = int(p[1])
        x, y, w, h = map(float, p[2:6])
        by_frame[f].append((tid, x + w / 2.0, y + h))
    return by_frame


def apply_H(H, pts):
    if not len(pts):
        return np.empty((0, 2))
    a = np.asarray(pts, np.float32).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(a, H).reshape(-1, 2)


def compute(mot_path, H, samples, times, stride):
    by_frame = load_mot(mot_path)
    Hinv = np.linalg.inv(H)
    frames = sorted(by_frame)

    gt_timeline = defaultdict(list)     # gt_tag -> [(frame, tid)]
    gt_inview_frames = Counter()        # gt_tag -> # frames in-view (mappable, should be tracked)
    cooc = defaultdict(Counter)         # gt_tag -> Counter(tid -> matched frames)
    track_matched_total = Counter()     # tid -> matched frames (to any GT)

    for f in frames:
        dets = by_frame[f]
        tids = [d[0] for d in dets]
        tp = apply_H(H, [(d[1], d[2]) for d in dets])    # tracked pitch pts
        when = mot_frame_walltime(f, stride)
        zp = zxy_at(samples, times, when)                 # {tag:(x,y,spd)}
        if not zp:
            continue
        # in-view GT (back-project pitch -> image, inside bounds)
        gt_tags, gt_xy = [], []
        for tag, (gx, gy, spd) in zp.items():
            px = cv2.perspectiveTransform(np.float32([[[gx, gy]]]), Hinv).reshape(2)
            if 0 <= px[0] < IMG_W and 0 <= px[1] < IMG_H:
                gt_tags.append(tag); gt_xy.append((gx, gy)); gt_inview_frames[tag] += 1
        if not gt_tags or not len(tp):
            continue
        G = np.array(gt_xy, np.float32)
        # cost matrix tracked x gt (pitch distance)
        D = np.hypot(tp[:, None, 0] - G[None, :, 0], tp[:, None, 1] - G[None, :, 1])
        ri, ci = linear_sum_assignment(D)
        for r, c in zip(ri, ci):
            if D[r, c] <= GATE_M:
                tag = gt_tags[c]; tid = tids[r]
                gt_timeline[tag].append((f, tid))
                cooc[tag][tid] += 1
                track_matched_total[tid] += 1

    # --- metrics ---
    per_gt = {}
    idsw_total = 0
    purity_list = []
    for tag, tl in gt_timeline.items():
        tl.sort()
        ids = [t for _, t in tl]
        distinct = len(set(ids))
        switches = sum(1 for i in range(1, len(ids)) if ids[i] != ids[i - 1])
        idsw_total += switches
        dom = Counter(ids).most_common(1)[0][1] if ids else 0
        purity = dom / len(ids) if ids else 0.0
        purity_list.append(purity)
        per_gt[tag] = {"matched_frames": len(ids), "inview_frames": gt_inview_frames[tag],
                       "distinct_track_ids": distinct, "id_switches": switches,
                       "dominant_purity": round(purity, 3)}

    # IDF1 via Hungarian on cooccurrence (maximize IDTP)
    gt_keys = list(cooc.keys())
    tid_keys = sorted({t for c in cooc.values() for t in c})
    idtp = 0
    if gt_keys and tid_keys:
        M = np.zeros((len(gt_keys), len(tid_keys)))
        for i, g in enumerate(gt_keys):
            for j, t in enumerate(tid_keys):
                M[i, j] = cooc[g].get(t, 0)
        ri, ci = linear_sum_assignment(-M)
        idtp = int(M[ri, ci].sum())
    total_gt = sum(gt_inview_frames.values())                  # in-view GT detections (denominator)
    total_track_matched = sum(track_matched_total.values())
    idfn = total_gt - idtp
    idfp = total_track_matched - idtp
    idf1 = (2 * idtp) / max(1, (2 * idtp + idfp + idfn))

    # over-merge: a tracked ID matched to >=2 DIFFERENT GT players = it fused two real players.
    # (the Day-30 guard: re-linking/anchoring must not join different players.) Build tid -> GT cooc.
    tid_to_gt = defaultdict(Counter)
    for tag, c in cooc.items():
        for tid, n in c.items():
            tid_to_gt[tid][tag] += n
    over_merge_any = 0      # track touches >=2 GT (incl 1-frame leaks)
    over_merge_strict = 0   # track's 2nd GT has >=3 matched frames (genuine spanning, not noise)
    for tid, gc in tid_to_gt.items():
        if len(gc) >= 2:
            over_merge_any += 1
            if sorted(gc.values(), reverse=True)[1] >= 3:
                over_merge_strict += 1

    frags = [v["distinct_track_ids"] for v in per_gt.values()]
    tot_matched = sum(v["matched_frames"] for v in per_gt.values())
    tot_inview = sum(v["inview_frames"] for v in per_gt.values())
    report = {
        "mot": str(mot_path), "stride": stride, "gate_m": GATE_M,
        "coverage_caveat": (
            "single CENTRE camera: the homography back-projects far/occluded GT into frame bounds, "
            "so 'in-view' over-counts what the camera usably resolves (~7 detections/frame vs ~12 'in-view' GT) "
            "-> IDF1 (has FN denominator) is DEPRESSED and is a RELATIVE before/after number, not absolute. "
            "IDs-per-GT-player + identity_purity + id_switches are measured on confident matches and ARE the "
            "primary metric; corroborated GT-free by Day-29 median track-life 1.3 s."),
        "match_coverage_pct": round(100 * tot_matched / max(1, tot_inview), 1),
        "n_gt_players_tracked": len(per_gt),
        "IDs_per_GT_player": {
            "mean": round(float(np.mean(frags)), 1) if frags else 0,
            "median": int(np.median(frags)) if frags else 0,
            "max": int(max(frags)) if frags else 0,
            "total_distinct_over_home": int(sum(frags)),
        },
        "identity_purity_mean": round(float(np.mean(purity_list)), 3) if purity_list else 0,
        "id_switches_vs_GT_total": idsw_total,
        "over_merge_tracks_2plus_GT": over_merge_any,
        "over_merge_tracks_strict": over_merge_strict,
        "IDF1": round(idf1, 3),
        "IDTP": idtp, "IDFP": idfp, "IDFN": idfn,
        "raw_unique_track_ids_in_mot": len({t for fr in by_frame.values() for t in [d[0] for d in fr]}),
        "per_gt": per_gt,
    }
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mot", default="outputs/track_results/alfheim_fh_cam1/first_half.txt")
    ap.add_argument("--trust", default="outputs/alfheim/trust_gate.json")
    ap.add_argument("--zxy", default="datasets/alfheim/2013-11-03/zxy/2013-11-03_tromso_stromsgodset_first.csv")
    ap.add_argument("--stride", type=int, default=2)
    ap.add_argument("--tag", default=None, help="output suffix (e.g. baseline, relinked)")
    args = ap.parse_args()

    H = np.array(json.loads(Path(args.trust).read_text())["H"], np.float32)
    samples, times = load_zxy(args.zxy)
    rep = compute(args.mot, H, samples, times, args.stride)

    suffix = f"_{args.tag}" if args.tag else ""
    out = Path("outputs/alfheim", f"identity_metric{suffix}.json")
    out.write_text(json.dumps(rep, indent=2))
    print(json.dumps({k: rep[k] for k in (
        "n_gt_players_tracked", "IDs_per_GT_player", "identity_purity_mean",
        "id_switches_vs_GT_total", "over_merge_tracks_2plus_GT", "over_merge_tracks_strict",
        "IDF1", "raw_unique_track_ids_in_mot")}, indent=2))
    print(f"  -> {out}")


if __name__ == "__main__":
    main()
