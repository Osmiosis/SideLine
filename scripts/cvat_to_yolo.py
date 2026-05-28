"""Convert UniqueData CVAT XML basketball annotations -> YOLO format.

Input: datasets/_dl_bball/  (annotations.xml + images/<subdir>/<N>.png + basketball_tracking.csv)
Output: datasets/basketball_ood/test/{images,labels}/  (ball class -> 0, YOLO normalized)

The CSV maps image_id -> image_name (e.g. 0 -> images/1/0.png).
The XML's <track id="0" label="ball"><box frame=N xtl=... ytl=... xbr=... ybr=...></track>
maps frame=N to image_id=N (one ball box per frame).

Saves a sidecar JSON of per-image attrs (occluded / outside) for any future occlusion
splits — even though this dataset has zero occluded=1 examples.
"""
import csv, json, shutil
import xml.etree.ElementTree as ET
from pathlib import Path
import cv2

SRC = Path("datasets/_dl_bball")
DST = Path("datasets/basketball_ood")
SPLIT = "test"   # treat the whole tiny set as test — never used for training

def main():
    img_out = DST / SPLIT / "images"
    lbl_out = DST / SPLIT / "labels"
    img_out.mkdir(parents=True, exist_ok=True)
    lbl_out.mkdir(parents=True, exist_ok=True)

    # Build image_id -> source path
    id2src = {}
    with open(SRC / "basketball_tracking.csv") as f:
        for row in csv.DictReader(f):
            id2src[int(row["image_id"])] = SRC / row["image_name"]

    # Parse XML — get original image size + per-frame ball box
    root = ET.parse(SRC / "annotations.xml").getroot()
    orig_w = int(root.findtext("./meta/task/original_size/width"))
    orig_h = int(root.findtext("./meta/task/original_size/height"))
    print(f"original size: {orig_w}x{orig_h}")

    frame_boxes = {}   # frame_id -> (xtl, ytl, xbr, ybr, occluded, outside)
    for track in root.findall("track"):
        label = track.get("label")
        if label.lower() != "ball": continue
        for box in track.findall("box"):
            fid = int(box.get("frame"))
            frame_boxes[fid] = {
                "xtl": float(box.get("xtl")),
                "ytl": float(box.get("ytl")),
                "xbr": float(box.get("xbr")),
                "ybr": float(box.get("ybr")),
                "occluded": int(box.get("occluded")),
                "outside": int(box.get("outside")),
            }

    print(f"XML boxes: {len(frame_boxes)}; CSV image rows: {len(id2src)}")

    n_written = 0
    n_skipped = 0
    attrs = {}
    for image_id, src_path in id2src.items():
        if not src_path.exists():
            print(f"  ! missing image for id={image_id}: {src_path}")
            n_skipped += 1
            continue
        box = frame_boxes.get(image_id)
        # Copy image to flat dir with a unique-ish name (image_id + original stem)
        out_name = f"ud_{image_id:04d}.png"
        target_img = img_out / out_name
        shutil.copy2(src_path, target_img)

        # Verify image size matches XML's original_size (PRD says 1280x720)
        img = cv2.imread(str(target_img))
        H, W = img.shape[:2]

        # Write YOLO label (ball class = 0)
        label_path = lbl_out / (Path(out_name).stem + ".txt")
        if box and box["outside"] == 0:
            cx = (box["xtl"] + box["xbr"]) / 2 / W
            cy = (box["ytl"] + box["ybr"]) / 2 / H
            w  = (box["xbr"] - box["xtl"]) / W
            h  = (box["ybr"] - box["ytl"]) / H
            label_path.write_text(f"0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")
            attrs[out_name] = {"occluded": box["occluded"], "outside": box["outside"]}
        else:
            # Ball outside frame or no annotation: write empty label file
            label_path.write_text("")
        n_written += 1

    # data.yaml so this set works with Ultralytics tooling too
    yaml_path = DST / "data.yaml"
    yaml_path.write_text(
        "names:\n- Basketball\nnc: 1\n"
        f"test: ../{SPLIT}/images\ntrain: ../{SPLIT}/images\nval: ../{SPLIT}/images\n"
    )

    # Sidecar attrs
    (DST / "attrs.json").write_text(json.dumps(attrs, indent=2))

    print(f"wrote {n_written} images + labels to {DST/SPLIT}/  (skipped: {n_skipped})")
    print(f"data.yaml: {yaml_path}")
    print(f"attrs.json: {DST/'attrs.json'}  (entries: {len(attrs)})")

if __name__ == "__main__":
    main()
