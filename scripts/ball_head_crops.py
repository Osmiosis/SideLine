"""Day 19 Part A: build a ball-vs-not-ball CANDIDATE-CROP dataset for appearance-based FP rejection.

The basketball ball track latches onto HEADS. Day-17 proved heads aren't size/geometry-separable
from the ball (area ~1.0x); Day-18 found TrackNet (motion-learning) is data-gated. The skipped
middle ground is APPEARANCE: a head and a ball look different even at identical size/shape, and
learning that needs SINGLE labeled crops -- no consecutive-frame data (sidesteps the TrackNet wall).

Labeling: the PRD's intended flow is a human bulk-sorting auto-cropped candidates into ball/not-ball.
Running autonomously, we instead PSEUDO-LABEL from the existing geometric signals (Day-9 player boxes
+ Day-17 head-zone) and VALIDATE the labels by eye on contact sheets. Honest caveat: pseudo-labels are
heuristic, not hand-verified -- so the held-out metrics are supporting evidence; the RE-WATCH (Part D)
is the verdict (Day-15/17 lesson). The appearance classifier still adds value: it learns APPEARANCE and
can generalize BEYOND the geometric head-zone (catching the head-latches the zone missed in Day-17).

Pseudo-label rule (per raw detection in det_cache/bb_ball):
  BALL (positive)  : conf >= conf_ball AND near a player box (<= prox_near) AND NOT in a head zone.
  HEAD (negative)  : center in a player HEAD zone (top head_frac_h of box, central head_frac_w).
  JUNK (negative)  : far from EVERY player box (> prox_far) -> banner/crowd/scoreboard.
  (ambiguous: near-player, non-head, low-conf -> SKIPPED to keep labels clean.)

Train/test split is BY SEQUENCE (test = one held-out clip) to avoid near-duplicate leakage between
adjacent frames' crops.

Outputs (outputs/ball_head/, gitignored):
  crops.npz        imgs(N,48,48,3 uint8), y(N: 1=ball,0=not), cls(N: ball/head/junk), seq, frame, cx, cy, conf
  sheet_ball.png / sheet_head.png / sheet_junk.png   contact sheets for eye-validation of the labels

Usage:
  python scripts/ball_head_crops.py            # all 5 seqs
"""
import argparse, sys
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent))
from diagnose_ball_fp import load_dets_full, load_players_boxes, in_head_zone, nearest_player_dist

SEQS = ["v_00HRwkvvjtQ_c001", "v_00HRwkvvjtQ_c003", "v_00HRwkvvjtQ_c005",
        "v_00HRwkvvjtQ_c007", "v_00HRwkvvjtQ_c008"]


def crop_square(img, cx, cy, w, h, ctx=1.3, out=48):
    """Tight square crop around a detection (side = ctx * max(w,h)), resized to out x out."""
    side = max(w, h) * ctx
    x0 = int(round(cx - side / 2)); y0 = int(round(cy - side / 2))
    x1 = int(round(cx + side / 2)); y1 = int(round(cy + side / 2))
    H, W = img.shape[:2]
    x0c, y0c = max(0, x0), max(0, y0); x1c, y1c = min(W, x1), min(H, y1)
    if x1c - x0c < 4 or y1c - y0c < 4:
        return None
    patch = img[y0c:y1c, x0c:x1c]
    return cv2.resize(patch, (out, out), interpolation=cv2.INTER_LINEAR)


def build(args):
    imgs, ys, clss, seqs, frames, cxs, cys, confs = [], [], [], [], [], [], [], []
    for seq in SEQS:
        dets = load_dets_full(Path(args.cache_dir) / f"{seq}.txt")   # {frame:[(cx,cy,w,h,conf)]}
        players = load_players_boxes(Path(args.track_dir) / f"{seq}.txt")
        fdir = Path(args.source) / seq / "img1"
        n_ball = n_head = n_junk = 0
        # cache loaded frames to avoid re-reading (group dets by frame)
        for f in sorted(dets.keys()):
            img = cv2.imread(str(fdir / f"{f:06d}.jpg"))
            if img is None:
                continue
            boxes = players.get(f, [])
            for (cx, cy, w, h, conf) in dets[f]:
                head = any(in_head_zone(cx, cy, b, args.head_frac_h, args.head_frac_w) for b in boxes)
                npd = nearest_player_dist(cx, cy, boxes)
                if head:
                    cls = "head"; y = 0
                elif npd > args.prox_far:
                    cls = "junk"; y = 0
                elif conf >= args.conf_ball and npd <= args.prox_near:
                    cls = "ball"; y = 1
                else:
                    continue  # ambiguous -> skip
                patch = crop_square(img, cx, cy, w, h, args.ctx, args.out_px)
                if patch is None:
                    continue
                imgs.append(patch); ys.append(y); clss.append(cls); seqs.append(seq)
                frames.append(f); cxs.append(cx); cys.append(cy); confs.append(conf)
                n_ball += cls == "ball"; n_head += cls == "head"; n_junk += cls == "junk"
        print(f"  {seq}: ball={n_ball} head={n_head} junk={n_junk}")
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    imgs = np.stack(imgs).astype(np.uint8)
    np.savez_compressed(out / "crops.npz", imgs=imgs, y=np.array(ys, np.int64),
                        cls=np.array(clss), seq=np.array(seqs), frame=np.array(frames, np.int64),
                        cx=np.array(cxs, np.float32), cy=np.array(cys, np.float32),
                        conf=np.array(confs, np.float32))
    print(f"\nTOTAL crops={len(ys)}  ball={ys.count(1)}  not-ball={ys.count(0)} "
          f"(head={clss.count('head')} junk={clss.count('junk')})")
    # contact sheets for eye-validation
    for name in ("ball", "head", "junk"):
        idx = [i for i, c in enumerate(clss) if c == name]
        if idx:
            sheet(imgs[idx], out / f"sheet_{name}.png", title=name)
    print(f"wrote {out}/crops.npz + sheet_ball/head/junk.png")


def sheet(crops, path, cols=20, tile=48, title=""):
    rng = np.random.RandomState(0)
    sel = crops if len(crops) <= cols * 12 else crops[rng.choice(len(crops), cols * 12, replace=False)]
    rows = int(np.ceil(len(sel) / cols))
    grid = np.zeros((rows * tile, cols * tile, 3), np.uint8)
    for k, c in enumerate(sel):
        r, cc = divmod(k, cols)
        grid[r * tile:(r + 1) * tile, cc * tile:(cc + 1) * tile] = cv2.resize(c, (tile, tile))
    grid = cv2.copyMakeBorder(grid, 24, 0, 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
    cv2.putText(grid, f"{title} (n={len(crops)})", (8, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    cv2.imwrite(str(path), grid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default="outputs/det_cache/bb_ball")
    ap.add_argument("--track-dir", default="outputs/track_results/bb_ftdet_botsort_gmc")
    ap.add_argument("--source", default="datasets/sportsmot_basketball")
    ap.add_argument("--out", default="outputs/ball_head", help="output directory")
    ap.add_argument("--out-px", type=int, default=48, help="crop pixel size")
    ap.add_argument("--conf-ball", type=float, default=0.5, help="min conf for a BALL positive")
    ap.add_argument("--prox-near", type=float, default=120.0, help="ball must be within this px of a player box")
    ap.add_argument("--prox-far", type=float, default=200.0, help="farther than this from all players = junk")
    ap.add_argument("--head-frac-h", type=float, default=0.18)
    ap.add_argument("--head-frac-w", type=float, default=0.6)
    ap.add_argument("--ctx", type=float, default=1.3, help="crop side = ctx*max(w,h)")
    args = ap.parse_args()
    build(args)


if __name__ == "__main__":
    main()
