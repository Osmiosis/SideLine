"""Spot-check the eval harness on a single image.

Renders one image with GT boxes (green) AND model predictions (red/orange/yellow
by TP/FP), labels TP/FP/FN counts on the canvas. Lets the developer eyeball
whether the harness's TP/FP/FN match what they see.

Usage:
  python scripts/spot_check.py <model.pt> <image.jpg> [--imgsz 1280] [--conf 0.25] [--iou 0.5]
                                                       [--root datasets/soccernet_h250]
                                                       [--out outputs/spot_check.png]
"""
import argparse
from pathlib import Path
import numpy as np
import cv2

import sys
sys.path.insert(0, str(Path(__file__).parent))
from evaluate import (
    load_model, build_remap, find_split, parse_label, yolo_to_xyxy,
    match_one_image, CLASS_NAMES,
)

def draw_box(img, x1, y1, x2, y2, color, label, thickness=2):
    cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    y_text = max(0, int(y1) - 5)
    cv2.rectangle(img, (int(x1), y_text - th - 2), (int(x1) + tw, y_text + 2), color, -1)
    cv2.putText(img, label, (int(x1), y_text), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("image")
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--root", default="datasets/soccernet_h250")
    ap.add_argument("--out", default="outputs/frames/spot_check.png")
    args = ap.parse_args()

    img_path = Path(args.image)
    if not img_path.is_absolute():
        # try to resolve under dataset test/images
        try:
            img_dir, lbl_dir = find_split(Path(args.root), "test")
            if (img_dir / img_path.name).exists():
                img_path = img_dir / img_path.name
        except Exception:
            pass
    if not img_path.exists():
        sys.exit(f"image not found: {args.image}")

    # Locate matching label
    img_dir, lbl_dir = find_split(Path(args.root), "test")
    lbl_path = lbl_dir / (img_path.stem + ".txt")
    if not lbl_path.exists():
        sys.exit(f"label not found: {lbl_path}")

    img = cv2.imread(str(img_path))
    H, W = img.shape[:2]
    canvas = img.copy()

    # GT
    gt = parse_label(lbl_path)
    gt_classes = np.array([c for c, *_ in gt], dtype=np.int64)
    gt_boxes   = yolo_to_xyxy([(cx, cy, w, h) for _, cx, cy, w, h in gt], W, H)

    # Predictions (production threshold)
    model = load_model(args.model)
    remap = build_remap(model.names)
    res = model(img, device=0, imgsz=args.imgsz, conf=args.conf, verbose=False)[0]
    mcls = res.boxes.cls.cpu().numpy().astype(int)
    mconf = res.boxes.conf.cpu().numpy()
    mxyxy = res.boxes.xyxy.cpu().numpy()
    keep_pb, keep_pc, keep_cl = [], [], []
    for box, cf, mc in zip(mxyxy, mconf, mcls):
        eval_c = remap.get(int(mc))
        if eval_c is None: continue
        keep_pb.append(box); keep_pc.append(cf); keep_cl.append(eval_c)
    pred_boxes   = np.asarray(keep_pb, dtype=np.float32).reshape(-1, 4)
    pred_confs   = np.asarray(keep_pc, dtype=np.float32)
    pred_classes = np.asarray(keep_cl, dtype=np.int64)

    pred_matched, gt_matched = match_one_image(
        pred_boxes, pred_confs, pred_classes, gt_boxes, gt_classes, args.iou
    )

    # Draw GT first (green for matched=TP-target, blue for unmatched=FN)
    for i, (cls, box) in enumerate(zip(gt_classes, gt_boxes)):
        if gt_matched[i]:
            color = (0, 200, 0)  # green — was matched (TP target)
            tag = "GT-matched"
        else:
            color = (255, 0, 0)  # blue (BGR) — FN
            tag = "FN"
        draw_box(canvas, *box, color, f"{tag}:{CLASS_NAMES[int(cls)]}", 2)

    # Draw predictions (yellow=TP, red=FP)
    for i, (cls, box, cf) in enumerate(zip(pred_classes, pred_boxes, pred_confs)):
        if pred_matched[i]:
            color = (0, 255, 255)  # yellow — TP
            tag = "TP"
        else:
            color = (0, 0, 255)  # red — FP
            tag = "FP"
        draw_box(canvas, *box, color, f"{tag}:{CLASS_NAMES[int(cls)]} {cf:.2f}", 1)

    # Summary text
    tp_ball = int(((pred_classes == 0) & pred_matched).sum())
    fp_ball = int(((pred_classes == 0) & ~pred_matched).sum())
    fn_ball = int(((gt_classes == 0) & ~gt_matched).sum())
    tp_pers = int(((pred_classes == 1) & pred_matched).sum())
    fp_pers = int(((pred_classes == 1) & ~pred_matched).sum())
    fn_pers = int(((gt_classes == 1) & ~gt_matched).sum())

    summary = (
        f"image: {img_path.name}  model: {Path(args.model).name}  conf>={args.conf} iou>={args.iou}\n"
        f"ball:   TP={tp_ball}  FP={fp_ball}  FN={fn_ball}\n"
        f"person: TP={tp_pers}  FP={fp_pers}  FN={fn_pers}"
    )
    print(summary)
    # also overlay on canvas
    for li, line in enumerate(summary.splitlines()):
        y = 25 + li * 22
        cv2.putText(canvas, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
        cv2.putText(canvas, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(args.out, canvas)
    print(f"wrote {args.out}")

if __name__ == "__main__":
    main()
