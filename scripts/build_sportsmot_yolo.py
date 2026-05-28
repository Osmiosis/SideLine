"""Build a YOLO-format detection dataset from extracted SportsMOT basketball-train seqs.

Splits 15 seqs into train/val by SEQUENCE (no frame leakage). Defaults pick 2 val seqs
spanning different games to broaden the val distribution.

Output layout:
  datasets/sportsmot_player_train/
    images/train/<seq>_<frame>.jpg
    images/val/<seq>_<frame>.jpg
    labels/train/<seq>_<frame>.txt
    labels/val/<seq>_<frame>.txt
    data.yaml
"""
import argparse, configparser, shutil
from pathlib import Path

VAL_SEQS = ["v_-6Os86HzwCs_c009", "v_4LXTUim5anY_c012"]

def parse_seqinfo(p):
    cp = configparser.ConfigParser(); cp.read(p)
    s = cp["Sequence"]
    return int(s["imWidth"]), int(s["imHeight"]), int(s["seqLength"]), s.get("imExt", ".jpg"), s.get("imDir", "img1")

def gt_by_frame(gt_path):
    bf = {}
    for line in gt_path.read_text().splitlines():
        p = line.strip().split(",")
        if len(p) < 6: continue
        f = int(p[0]); x, y, w, h = map(float, p[2:6])
        conf = float(p[6]) if len(p) > 6 else 1.0
        if conf == 0: continue
        bf.setdefault(f, []).append((x, y, w, h))
    return bf

def convert_seq(seq_dir, out_root, split, stride):
    W, H, N, ext, im_dir = parse_seqinfo(seq_dir / "seqinfo.ini")
    bf = gt_by_frame(seq_dir / "gt" / "gt.txt")
    img_out = out_root / "images" / split
    lbl_out = out_root / "labels" / split
    img_out.mkdir(parents=True, exist_ok=True)
    lbl_out.mkdir(parents=True, exist_ok=True)
    n_img, n_box = 0, 0
    for f in range(1, N + 1):
        if (f - 1) % stride != 0: continue
        boxes = bf.get(f, [])
        if not boxes: continue
        src_img = seq_dir / im_dir / f"{f:06d}{ext}"
        if not src_img.exists(): continue
        stem = f"{seq_dir.name}_{f:06d}"
        shutil.copy2(src_img, img_out / f"{stem}{ext}")
        lines = []
        for (x, y, w, h) in boxes:
            cx, cy = (x + w/2) / W, (y + h/2) / H
            nw, nh = w / W, h / H
            if nw <= 0 or nh <= 0: continue
            lines.append(f"0 {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
        (lbl_out / f"{stem}.txt").write_text("\n".join(lines) + "\n")
        n_img += 1; n_box += len(lines)
    return n_img, n_box

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="Dir of extracted SportsMOT basketball-train seqs")
    ap.add_argument("--out", default="datasets/sportsmot_player_train")
    ap.add_argument("--stride", type=int, default=5)
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    seqs = sorted(d for d in src.iterdir() if d.is_dir() and (d / "seqinfo.ini").exists())
    print(f"found {len(seqs)} seqs")

    train_seqs = [s for s in seqs if s.name not in VAL_SEQS]
    val_seqs   = [s for s in seqs if s.name in VAL_SEQS]
    print(f"train seqs: {len(train_seqs)}, val seqs: {len(val_seqs)} -> {[s.name for s in val_seqs]}")

    totals = {"train": [0, 0], "val": [0, 0]}
    for seq in train_seqs:
        ni, nb = convert_seq(seq, out, "train", args.stride)
        totals["train"][0] += ni; totals["train"][1] += nb
        print(f"  train {seq.name}: {ni} imgs, {nb} boxes")
    for seq in val_seqs:
        ni, nb = convert_seq(seq, out, "val", args.stride)
        totals["val"][0] += ni; totals["val"][1] += nb
        print(f"  val   {seq.name}: {ni} imgs, {nb} boxes")

    yaml_path = out / "data.yaml"
    yaml_path.write_text(
        f"path: {out.resolve().as_posix()}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"nc: 1\nnames:\n  0: player\n"
    )
    print(f"\nTOTALS train: {totals['train']}  val: {totals['val']}")
    print(f"wrote {yaml_path}")

if __name__ == "__main__":
    main()
