"""Extract a small SoccerNet SN-GSR-2025 subset and convert to MOT format.

Pulls N sequences from test.zip, materializes:
  <out>/<seq>/img1/000001.jpg ...
  <out>/<seq>/gt/gt.txt          (MOT: frame,id,x,y,w,h,1,1,1.0 — players + goalkeepers only)
  <out>/<seq>/seqinfo.ini

Output dir is gitignored (datasets/* in .gitignore). NDA-safe by default.
"""
import argparse, json, zipfile
from pathlib import Path

# GSR category IDs we keep as "player" for tracking eval
KEEP_CATS = {1, 2}  # 1=player, 2=goalkeeper (drop referee/ball/other for player-tracking)

def write_seqinfo(seq_dir: Path, info: dict, images: list):
    h = images[0]["height"]; w = images[0]["width"]
    ini = (
        f"[Sequence]\n"
        f"name={info['name']}\n"
        f"imDir=img1\n"
        f"frameRate={info['frame_rate']}\n"
        f"seqLength={info['seq_length']}\n"
        f"imWidth={w}\n"
        f"imHeight={h}\n"
        f"imExt={info['im_ext']}\n"
    )
    (seq_dir / "seqinfo.ini").write_text(ini)

def convert_gt(annotations: list, images: list) -> str:
    # image_id -> 1-indexed frame number, derived from file_name (e.g. "000123.jpg" -> 123)
    img_frame = {}
    for img in images:
        img_frame[img["image_id"]] = int(Path(img["file_name"]).stem)
    # Build contiguous tracker IDs (TrackEval prefers small ints)
    seen_tids = {}
    next_tid = 1
    rows = []
    for a in annotations:
        if a.get("category_id") not in KEEP_CATS:
            continue
        if a.get("supercategory") != "object":
            continue
        bb = a.get("bbox_image")
        if not bb:
            continue
        frame = img_frame.get(a["image_id"])
        if frame is None:
            continue
        orig_tid = a["track_id"]
        if orig_tid not in seen_tids:
            seen_tids[orig_tid] = next_tid
            next_tid += 1
        tid = seen_tids[orig_tid]
        x = float(bb["x"]); y = float(bb["y"])
        w = float(bb["w"]); h = float(bb["h"])
        # MOT GT: frame,id,x,y,w,h,conf,cls,vis
        # conf=1 (consider), cls=1 (pedestrian), vis=1.0
        rows.append(f"{frame},{tid},{x:.2f},{y:.2f},{w:.2f},{h:.2f},1,1,1.0")
    rows.sort(key=lambda s: (int(s.split(',')[0]), int(s.split(',')[1])))
    return "\n".join(rows) + "\n"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default="datasets/soccernet_gsr/test.zip")
    ap.add_argument("--out", default="datasets/soccernet_tracking")
    ap.add_argument("--seqs", nargs="+",
                    default=["SNGS-116", "SNGS-117", "SNGS-118", "SNGS-119", "SNGS-120"])
    args = ap.parse_args()

    out_root = Path(args.out); out_root.mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(args.zip)
    all_names = z.namelist()

    for seq in args.seqs:
        members = [n for n in all_names if n.startswith(seq + "/")]
        print(f"\n[{seq}]  {len(members)} members")
        seq_dir = out_root / seq
        (seq_dir / "img1").mkdir(parents=True, exist_ok=True)
        (seq_dir / "gt").mkdir(parents=True, exist_ok=True)

        # 1) Extract images + labels (zipfile.extract preserves nested paths)
        n_imgs = 0
        for m in members:
            if m.endswith("/"):
                continue
            target = out_root / m
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(m) as src, open(target, "wb") as dst:
                dst.write(src.read())
            if m.endswith(".jpg"):
                n_imgs += 1
        print(f"  extracted {n_imgs} jpgs")

        # 2) Convert Labels-GameState.json -> MOT gt.txt + seqinfo.ini
        labels_path = seq_dir / "Labels-GameState.json"
        data = json.loads(labels_path.read_text())
        gt_text = convert_gt(data["annotations"], data["images"])
        (seq_dir / "gt" / "gt.txt").write_text(gt_text)
        write_seqinfo(seq_dir, data["info"], data["images"])

        n_rows = gt_text.count("\n")
        ids = {int(r.split(',')[1]) for r in gt_text.strip().splitlines()}
        print(f"  gt.txt: {n_rows} rows, {len(ids)} unique IDs")
        print(f"  seqinfo.ini: {data['info']['seq_length']} frames @ {data['info']['frame_rate']} fps")

if __name__ == "__main__":
    main()
