"""Day 22 Part A: basketball player-crop generator + DEAD-SIMPLE hand-labeling app.

Builds the VALIDATION set for basketball team assignment (SportsMOT has no team GT). Mirrors the
Day-19 ball/head sorter that worked well: enlarged crop + the WIDER FRAME with the player's box
highlighted (so you can tell which team) + one key per class. Autosaves every keypress, resumable.

Two steps:
  1) `--build`  -> sample player crops across the 5 clips (diverse: a few frames per track),
                   save crops + a manifest (crop -> seq, frame, tid, bbox).
  2) (default)  -> label them: press a / b / r / o per crop. Saves crop_idx -> label.

Classes (press the key):
  a = Team A        b = Team B        r = Referee (striped / official)
  o = Bench-or-other (sideline / tracksuit / coach / fan)
  s = skip (unsure)   u = undo last   q / ESC = save + quit

Pick which jersey is "Team A" vs "Team B" however you like and stay consistent -- the validator
tries both A/B->cluster mappings and takes the better (cluster IDs are arbitrary). Aim for a few
hundred labels, with a good number of refs/bench so the exclusion accuracy is measurable.

Outputs:
  outputs/team_assign_bb/crops.npz        imgs + manifest (seq,frame,tid,x,y,w,h)
  outputs/team_assign_bb/hand_labels.json { "<crop_idx>": "A"|"B"|"ref"|"bench" }

Run it yourself (interactive window):
  .venv\\Scripts\\python scripts\\label_crops.py --build      # once, to make crops
  .venv\\Scripts\\python scripts\\label_crops.py              # label them
"""
import argparse, json, sys
from collections import defaultdict, Counter
from pathlib import Path
import numpy as np
import cv2
# GUI uses Tkinter (stdlib) + PIL, NOT cv2.imshow -- the installed OpenCV is the headless build
# (no highgui), so cv2 windows raise "function not implemented". Tkinter needs no extra install.

SEQS = ["v_00HRwkvvjtQ_c001", "v_00HRwkvvjtQ_c003", "v_00HRwkvvjtQ_c005",
        "v_00HRwkvvjtQ_c007", "v_00HRwkvvjtQ_c008"]
CROP_W, CROP_H = 110, 200
CLASSES = {"a": "A", "b": "B", "r": "ref", "o": "bench"}


def load_rows(track_path):
    by_tid = defaultdict(list)
    for line in Path(track_path).read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(",")
        by_tid[int(p[1])].append((int(p[0]), float(p[2]), float(p[3]), float(p[4]), float(p[5])))
    return by_tid


def build(args):
    """Sample up to per_track crops per (seq,tid), spread across the clip; cap total. Diverse set."""
    rng = np.random.RandomState(0)
    imgs, manifest = [], []
    for seq in SEQS:
        by_tid = load_rows(Path(args.track) / f"{seq}.txt")
        fd = Path(args.frames_root) / seq / "img1"
        for tid, rows in by_tid.items():
            rows = sorted(rows)
            if len(rows) < args.min_track:
                continue
            pick = rows[:: max(1, len(rows) // args.per_track)][:args.per_track]
            for (f, x, y, w, h) in pick:
                img = cv2.imread(str(fd / f"{f:06d}.jpg"))
                if img is None:
                    continue
                H, W = img.shape[:2]
                x1, y1 = max(0, int(x)), max(0, int(y))
                x2, y2 = min(W, int(x + w)), min(H, int(y + h))
                if x2 - x1 < 8 or y2 - y1 < 16:
                    continue
                crop = cv2.resize(img[y1:y2, x1:x2], (CROP_W, CROP_H), interpolation=cv2.INTER_AREA)
                imgs.append(crop)
                manifest.append({"seq": seq, "frame": f, "tid": tid,
                                 "bbox": [round(x, 1), round(y, 1), round(w, 1), round(h, 1)]})
    imgs = np.array(imgs)
    # shuffle for diverse labeling order
    order = rng.permutation(len(imgs))
    imgs = imgs[order]; manifest = [manifest[i] for i in order]
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    np.savez(out / "crops.npz", imgs=imgs, manifest=json.dumps(manifest))
    print(f"built {len(imgs)} crops across {len(SEQS)} clips -> {out/'crops.npz'}")
    print("now run (no --build) to label them.")


def context_view(crop, manifest_i, frames_root):
    """crop (left) + wider frame with the player's box drawn (right)."""
    fd = Path(frames_root) / manifest_i["seq"] / "img1" / f"{manifest_i['frame']:06d}.jpg"
    frame = cv2.imread(str(fd))
    left = cv2.resize(crop, (CROP_W * 2, CROP_H * 2), interpolation=cv2.INTER_NEAREST)
    if frame is None:
        ctx = np.zeros((CROP_H * 2, 480, 3), np.uint8)
    else:
        x, y, w, h = manifest_i["bbox"]
        cv2.rectangle(frame, (int(x), int(y)), (int(x + w), int(y + h)), (0, 0, 255), 3)
        ctx = cv2.resize(frame, (480, int(480 * frame.shape[0] / frame.shape[1])))
    Hc = max(left.shape[0], ctx.shape[0])
    pad = lambda im: cv2.copyMakeBorder(im, 0, Hc - im.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=0)
    return np.hstack([pad(left), pad(ctx)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--track", default="outputs/track_results/bball_ftdet_bytetrack")
    ap.add_argument("--frames-root", default="datasets/sportsmot_basketball")
    ap.add_argument("--out", default="outputs/team_assign_bb")
    ap.add_argument("--per-track", type=int, default=4)
    ap.add_argument("--min-track", type=int, default=20)
    args = ap.parse_args()
    if args.build:
        build(args); return

    import tkinter as tk
    from PIL import Image, ImageTk

    d = np.load(Path(args.out) / "crops.npz", allow_pickle=True)
    imgs = d["imgs"]; manifest = json.loads(str(d["manifest"]))
    n = len(imgs)
    lab_path = Path(args.out) / "hand_labels.json"
    labels = json.loads(lab_path.read_text()) if lab_path.exists() else {}
    print(f"{n} crops | already labeled: {len(labels)} | a=TeamA b=TeamB r=ref o=bench s=skip u=undo q=quit")

    def save():
        lab_path.write_text(json.dumps(labels))

    def counts():
        c = Counter(labels.values())
        return f"A={c['A']} B={c['B']} ref={c['ref']} bench={c['bench']}  labeled={len(labels)}/{n}"

    state = {"i": 0, "history": []}

    root = tk.Tk()
    root.title("label crops")
    status = tk.Label(root, font=("Consolas", 13), fg="#0a0", anchor="w", justify="left")
    status.pack(fill="x", padx=6, pady=4)
    legend = tk.Label(root, font=("Consolas", 11),
                      text="a=Team A   b=Team B   r=referee   o=bench/other   s=skip   u=undo   q=save+quit")
    legend.pack(fill="x", padx=6)
    panel = tk.Label(root)
    panel.pack(padx=6, pady=6)

    def show():
        i = state["i"]
        while i < n and str(i) in labels:
            i += 1
        state["i"] = i
        if i >= n:
            status.config(text=f"ALL DONE  {counts()}  -- press q to quit")
            panel.config(image="")
            return
        view = context_view(imgs[i], manifest[i], args.frames_root)        # BGR
        im = Image.fromarray(cv2.cvtColor(view, cv2.COLOR_BGR2RGB))
        photo = ImageTk.PhotoImage(im)
        panel.config(image=photo); panel.image = photo                     # keep ref
        status.config(text=f"#{i}/{n}  [{manifest[i]['seq'][-4:]}]   {counts()}")

    def do_label(cls):
        i = state["i"]
        if i >= n:
            return
        labels[str(i)] = cls; state["history"].append(i); save()
        state["i"] = i + 1; show()

    def do_skip():
        state["i"] += 1; show()

    def do_undo():
        if state["history"]:
            last = state["history"].pop(); labels.pop(str(last), None); save()
            state["i"] = last; show()

    def do_quit():
        save(); root.destroy()

    def on_key(e):
        k = (e.char or "").lower()
        if k in CLASSES:
            do_label(CLASSES[k])
        elif k == "s":
            do_skip()
        elif k == "u":
            do_undo()
        elif k == "q" or e.keysym == "Escape":
            do_quit()

    root.bind("<Key>", on_key)
    root.protocol("WM_DELETE_WINDOW", do_quit)
    show()
    root.mainloop()
    save()
    print(f"\nsaved {len(labels)} labels -> {lab_path}  ({counts()})")
    print("Re-run to continue, or tell Claude to validate once you have a few hundred.")


if __name__ == "__main__":
    main()
