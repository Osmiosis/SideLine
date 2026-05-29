"""Day 19 Part A.5: FAST interactive hand-sorter for ball-vs-not-ball candidate crops.

Replaces the contaminated geometric pseudo-labels (Day-19: balls+heads leaked both ways) with CLEAN
hand labels -- the PRD's intended flow. Shows each auto-cropped candidate enlarged; you press ONE key
to bin it. Autosaves after every keypress (resumable -- rerun to continue), so you can stop whenever
you have enough (a few hundred clean labels is plenty for the binary classifier).

Crops are presented in a SEEDED SHUFFLE across all 5 clips, so the first few hundred you label are a
diverse mix (not all from one sequence) -- good for an honest train/test split later.

Keys:
  b = BALL            n = NOT-ball (head / junk / body)      s = skip (don't label, move on)
  u = undo last       q or ESC = save + quit

Output: outputs/ball_head/hand_labels.json  { "<crop_index>": "ball" | "not" }

Run it yourself (interactive window):
  .venv\Scripts\python scripts\sort_crops.py
"""
import argparse, json
from pathlib import Path
import numpy as np
import cv2


def make_canvas(crop, idx, k_ball, k_not, k_skip, total, hint):
    """Enlarged crop + an info strip with progress and key legend."""
    view = cv2.resize(crop, (360, 360), interpolation=cv2.INTER_NEAREST)
    panel = np.zeros((360, 360, 3), np.uint8)
    lines = [
        f"crop #{idx}", f"pseudo: {hint}", "",
        f"labeled: ball={k_ball} not={k_not}", f"skipped={k_skip}  / {total} total", "",
        "[b] BALL", "[n] NOT-ball", "[s] skip", "[u] undo", "[q] save+quit",
    ]
    for i, t in enumerate(lines):
        col = (40, 240, 40) if t.startswith("[b]") else (60, 160, 255) if t.startswith("[n]") else (230, 230, 230)
        cv2.putText(panel, t, (12, 34 + i * 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 1, cv2.LINE_AA)
    return np.hstack([view, panel])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crops", default="outputs/ball_head/crops.npz")
    ap.add_argument("--out", default="outputs/ball_head/hand_labels.json")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    d = np.load(args.crops, allow_pickle=True)
    imgs, cls = d["imgs"], d["cls"]
    n = len(imgs)
    order = np.random.RandomState(args.seed).permutation(n)

    out = Path(args.out)
    labels = json.loads(out.read_text()) if out.exists() else {}
    print(f"{n} crops | already labeled: {len(labels)} | resuming...")

    def save():
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(labels))

    history = []  # for undo
    win = "sort crops: b=ball  n=not  s=skip  u=undo  q=quit"
    cv2.namedWindow(win)
    i = 0
    while i < n:
        idx = int(order[i])
        if str(idx) in labels:
            i += 1; continue
        kb = sum(1 for v in labels.values() if v == "ball")
        kn = sum(1 for v in labels.values() if v == "not")
        canvas = make_canvas(imgs[idx], idx, kb, kn, len(history) - kb - kn if False else 0, n, str(cls[idx]))
        cv2.imshow(win, canvas)
        key = cv2.waitKey(0) & 0xFF
        if key in (ord("q"), 27):
            break
        elif key == ord("b"):
            labels[str(idx)] = "ball"; history.append(idx); save(); i += 1
        elif key == ord("n"):
            labels[str(idx)] = "not"; history.append(idx); save(); i += 1
        elif key == ord("s"):
            i += 1
        elif key == ord("u") and history:
            last = history.pop(); labels.pop(str(last), None); save()
            # step back to the undone crop
            while i > 0 and int(order[i]) != last:
                i -= 1
        # else: ignore other keys, re-show same crop
    cv2.destroyAllWindows()
    save()
    kb = sum(1 for v in labels.values() if v == "ball")
    kn = sum(1 for v in labels.values() if v == "not")
    print(f"\nsaved {len(labels)} labels -> {args.out}  (ball={kb}  not-ball={kn})")
    print("Re-run to continue, or tell Claude to train once you have a few hundred of each.")


if __name__ == "__main__":
    main()
