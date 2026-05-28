"""Convert SportsMOT sequence directories to YOLO detection format.

Drops tracklet IDs (we're training a DETECTOR, not a tracker). All boxes -> class 0 (player).

Input layout (per seq):
  <seq>/img1/000001.jpg, ...
  <seq>/gt/gt.txt   (frame,id,x,y,w,h,conf,cls,vis)
  <seq>/seqinfo.ini

Output (YOLO):
  out_root/images/<seq>_<frame>.jpg
  out_root/labels/<seq>_<frame>.txt    one line per box: "0 cx cy w h" normalized

Optional --stride N: keep every Nth frame (default 1).

Usage:
  python scripts/sportsmot_to_yolo.py datasets/sportsmot_basketball_train \
    --out datasets/sportsmot_player_yolo/train --stride 5
"""
import argparse, configparser, shutil
from pathlib import Path

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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src_root", help="Directory containing SportsMOT seq subdirs")
    ap.add_argument("--out", required=True)
    ap.add_argument("--stride", type=int, default=1, help="Keep every Nth frame")
    ap.add_argument("--copy", action="store_true", help="Copy images instead of symlinking")
    args = ap.parse_args()

    src = Path(args.src_root)
    out = Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)

    seqs = sorted(d for d in src.iterdir() if d.is_dir() and (d / "seqinfo.ini").exists())
    print(f"found {len(seqs)} seqs under {src}")

    total_imgs, total_boxes = 0, 0
    for seq in seqs:
        W, H, N, ext, im_dir = parse_seqinfo(seq / "seqinfo.ini")
        bf = gt_by_frame(seq / "gt" / "gt.txt")
        kept = 0
        for f in range(1, N + 1):
            if (f - 1) % args.stride != 0: continue
            boxes = bf.get(f, [])
            if not boxes: continue  # no labels => skip frame
            src_img = seq / im_dir / f"{f:06d}{ext}"
            if not src_img.exists():
                print(f"  missing {src_img}"); continue
            stem = f"{seq.name}_{f:06d}"
            dst_img = out / "images" / f"{stem}{ext}"
            dst_lbl = out / "labels" / f"{stem}.txt"
            if args.copy:
                shutil.copy2(src_img, dst_img)
            else:
                # On Windows, fallback to copy if symlink not permitted
                try:
                    if dst_img.exists(): dst_img.unlink()
                    dst_img.symlink_to(src_img.resolve())
                except (OSError, NotImplementedError):
                    shutil.copy2(src_img, dst_img)
            lines = []
            for (x, y, w, h) in boxes:
                cx, cy = (x + w / 2) / W, (y + h / 2) / H
                nw, nh = w / W, h / H
                if nw <= 0 or nh <= 0: continue
                lines.append(f"0 {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
            dst_lbl.write_text("\n".join(lines) + "\n")
            kept += 1
            total_boxes += len(lines)
        print(f"  {seq.name}: {kept} frames kept ({N} total)")
        total_imgs += kept

    print(f"\nTotal: {total_imgs} images, {total_boxes} player boxes -> {out}")

if __name__ == "__main__":
    main()
