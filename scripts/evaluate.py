"""Football detection evaluation harness.

Computes per-class precision / recall / AP / mAP@0.5 against SoccerNet_v3_H250
test split, with class-name-based remapping so models with different schemes
can all be evaluated in the dataset's 2-class space (ball / person).

Usage:
  python scripts/evaluate.py <model.pt> [--n 500] [--seed 42] [--imgsz 1280]
                                        [--conf 0.001] [--iou 0.5]
                                        [--root datasets/soccernet_h250]
                                        [--gt-as-pred] [--empty-preds]
                                        [--out outputs/eval_<stem>.json]

Sanity modes:
  --gt-as-pred  : feed the ground-truth boxes in as predictions (perfect detector).
                  Must produce P=R=AP=1.0 — proves matching logic is correct.
  --empty-preds : feed no predictions. Must produce R=0, P=0 (handled).
"""
import argparse, json, random, sys, time
from pathlib import Path
import numpy as np
import cv2

# Make Ultralytics import lazy so --gt-as-pred / --empty-preds don't need torch loaded
def load_model(path):
    from ultralytics import YOLO
    return YOLO(path)

CLASS_NAMES = {0: "ball", 1: "person"}
NUM_CLASSES = 2

def map_class_name_to_eval(name: str):
    """Return 0 (ball), 1 (person), or None (drop)."""
    n = name.lower()
    if "ball" in n:
        return 0
    if any(k in n for k in ("player", "goalkeeper", "referee", "person")):
        return 1
    return None

def build_remap(model_names: dict):
    """model_class_idx -> eval_class (0|1) or None to drop."""
    remap = {}
    for idx, name in model_names.items():
        remap[idx] = map_class_name_to_eval(name)
    return remap

def find_split(root: Path, split="test"):
    for img, lbl in [(root / split / "images", root / split / "labels"),
                     (root / "images" / split, root / "labels" / split)]:
        if img.is_dir() and lbl.is_dir():
            return img, lbl
    raise FileNotFoundError(f"no {split} split under {root}")

def load_gt_remap(root: Path):
    """If root/data.yaml exists, return {raw_gt_idx -> eval_idx or None} mapping
    derived from dataset class NAMES (matches the by-name convention used on the
    prediction side). Falls back to identity if no yaml is present."""
    yml = root / "data.yaml"
    if not yml.exists():
        return None
    try:
        import yaml as _yaml
        d = _yaml.safe_load(yml.read_text())
        names = d.get("names", [])
        if isinstance(names, dict):
            names = [names[i] for i in sorted(names)]
        return {i: map_class_name_to_eval(str(n)) for i, n in enumerate(names)}
    except Exception as e:
        print(f"  WARN: could not parse {yml}: {e}")
        return None

def parse_label(path: Path):
    if not path.exists(): return []
    out = []
    for line in path.read_text().splitlines():
        p = line.strip().split()
        if len(p) != 5: continue
        out.append((int(p[0]), float(p[1]), float(p[2]), float(p[3]), float(p[4])))
    return out

def yolo_to_xyxy(boxes_norm, W, H):
    """boxes_norm: list of (cx,cy,w,h) in [0,1]; returns (N,4) xyxy in pixels."""
    if not boxes_norm: return np.zeros((0, 4), dtype=np.float32)
    a = np.array(boxes_norm, dtype=np.float32)
    cx, cy, w, h = a[:, 0]*W, a[:, 1]*H, a[:, 2]*W, a[:, 3]*H
    return np.stack([cx - w/2, cy - h/2, cx + w/2, cy + h/2], axis=1)

def iou_matrix(a, b):
    """a: (N,4) xyxy. b: (M,4) xyxy. -> (N,M) iou."""
    if a.shape[0] == 0 or b.shape[0] == 0:
        return np.zeros((a.shape[0], b.shape[0]), dtype=np.float32)
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    union = area_a[:, None] + area_b[None, :] - inter
    return np.where(union > 0, inter / union, 0.0)

def match_one_image(pred_boxes, pred_confs, pred_classes, gt_boxes, gt_classes, iou_thresh=0.5):
    """
    Greedy by descending confidence within each class.
    Returns per-prediction (matched: bool, gt_idx: int|-1) and per-gt matched flag.
    """
    N, M = len(pred_boxes), len(gt_boxes)
    pred_matched = np.zeros(N, dtype=bool)
    gt_matched   = np.zeros(M, dtype=bool)
    if N == 0 or M == 0:
        return pred_matched, gt_matched

    order = np.argsort(-pred_confs)  # high conf first
    ious = iou_matrix(pred_boxes, gt_boxes)
    for pi in order:
        # eligible GTs: same class, not yet matched, IoU >= thresh
        eligible = (gt_classes == pred_classes[pi]) & ~gt_matched & (ious[pi] >= iou_thresh)
        if not eligible.any(): continue
        best = np.where(eligible)[0]
        best_gt = best[np.argmax(ious[pi, best])]
        pred_matched[pi] = True
        gt_matched[best_gt] = True
    return pred_matched, gt_matched

def compute_ap(conf_scores, is_tp, n_gt):
    """Pascal-VOC-style AP from a sorted list of (conf, tp_flag) and total GT count."""
    if n_gt == 0:
        return float("nan") if len(conf_scores) == 0 else 0.0
    if len(conf_scores) == 0:
        return 0.0
    order = np.argsort(-conf_scores)
    tp = is_tp[order].astype(np.float64)
    fp = (1 - tp).astype(np.float64)
    tp_cum = np.cumsum(tp)
    fp_cum = np.cumsum(fp)
    recall    = tp_cum / n_gt
    precision = tp_cum / np.maximum(tp_cum + fp_cum, 1e-12)
    # 11-point interpolation for stability + matches Pascal VOC convention
    ap = 0.0
    for t in np.linspace(0, 1, 11):
        mask = recall >= t
        p = precision[mask].max() if mask.any() else 0.0
        ap += p / 11
    return float(ap)

def evaluate(model_path, root, n, seed, imgsz, conf_thresh, iou_thresh, gt_as_pred, empty_preds, device=0):
    root = Path(root)
    img_dir, lbl_dir = find_split(root, "test")
    all_imgs = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    random.seed(seed)
    sample = random.sample(all_imgs, min(n, len(all_imgs)))
    print(f"sample: {len(sample)} / {len(all_imgs)} images  (seed {seed})")

    # GT remap from data.yaml NAMES (by-name, matches prediction side).
    gt_remap = load_gt_remap(root)
    if gt_remap is not None:
        print(f"GT remap (raw_idx -> eval): {gt_remap}")

    # Auto-detect which eval classes have any GT in this sample (post-remap).
    # On a ball-only dataset, person predictions would otherwise count as FPs forever.
    gt_classes_present = set()
    for p in sample:
        for c, *_ in parse_label(lbl_dir / (p.stem + ".txt")):
            mapped = gt_remap.get(c) if gt_remap is not None else c
            if mapped is not None:
                gt_classes_present.add(mapped)
    print(f"GT classes present in sample (eval space): {sorted(gt_classes_present)} ({[CLASS_NAMES[c] for c in sorted(gt_classes_present) if c in CLASS_NAMES]})")

    model = None
    remap = None
    if not gt_as_pred and not empty_preds:
        model = load_model(model_path)
        print(f"model classes: {model.names}")
        remap_raw = build_remap(model.names)
        # Restrict remap to only classes with GT present — predictions to other
        # eval classes get dropped (not counted as FPs against absent GT).
        remap = {k: (v if v in gt_classes_present else None) for k, v in remap_raw.items()}
        print(f"remap (model_idx -> eval, restricted to GT-present): {remap}")

    # Per-class accumulators
    all_confs   = {0: [], 1: []}
    all_tp      = {0: [], 1: []}
    gt_totals   = {0: 0, 1: 0}
    fp_counts   = {0: 0, 1: 0}
    per_image   = []

    t0 = time.time()
    for i, img_path in enumerate(sample):
        gt = parse_label(lbl_dir / (img_path.stem + ".txt"))
        img_for_size = cv2.imread(str(img_path))
        if img_for_size is None:
            print(f"  skip unreadable {img_path.name}"); continue
        H, W = img_for_size.shape[:2]

        # Apply GT remap by name; drop classes whose name doesn't map to {ball, person}
        if gt_remap is not None:
            gt = [(gt_remap[c], cx, cy, w, h) for c, cx, cy, w, h in gt
                  if gt_remap.get(c) is not None]
        gt_classes = np.array([c for c, *_ in gt], dtype=np.int64)
        gt_boxes   = yolo_to_xyxy([(cx, cy, w, h) for _, cx, cy, w, h in gt], W, H)
        for c in (0, 1):
            gt_totals[c] += int((gt_classes == c).sum())

        # Build predictions
        if gt_as_pred:
            pred_boxes   = gt_boxes.copy()
            pred_confs   = np.ones(len(gt_classes), dtype=np.float32)
            pred_classes = gt_classes.copy()
        elif empty_preds:
            pred_boxes   = np.zeros((0, 4), dtype=np.float32)
            pred_confs   = np.zeros((0,), dtype=np.float32)
            pred_classes = np.zeros((0,), dtype=np.int64)
        else:
            res = model(img_for_size, device=device, imgsz=imgsz, conf=conf_thresh, verbose=False)[0]
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

        # Match per class — but match_one_image handles class internally
        pred_matched, gt_matched = match_one_image(
            pred_boxes, pred_confs, pred_classes, gt_boxes, gt_classes, iou_thresh
        )

        # Record per-class
        for c in (0, 1):
            sel = (pred_classes == c)
            all_confs[c].extend(pred_confs[sel].tolist())
            all_tp[c].extend(pred_matched[sel].astype(int).tolist())
            fp_counts[c] += int((~pred_matched[sel]).sum())

        per_image.append({
            "image": img_path.name,
            "gt_ball": int((gt_classes == 0).sum()),
            "gt_person": int((gt_classes == 1).sum()),
            "pred_ball": int((pred_classes == 0).sum()),
            "pred_person": int((pred_classes == 1).sum()),
            "tp_ball": int(((pred_classes == 0) & pred_matched).sum()),
            "tp_person": int(((pred_classes == 1) & pred_matched).sum()),
        })

        if (i + 1) % 50 == 0:
            dt = time.time() - t0
            print(f"  {i+1}/{len(sample)}  {(i+1)/dt:.1f} img/s")

    # Aggregate metrics
    # Two reports per class:
    #   - precision/recall at the production confidence threshold (default 0.25)
    #     — these are the numbers you'd see deployed
    #   - AP from the full conf sweep (threshold-independent ranking)
    PROD_CONF = 0.25
    metrics = {}
    for c, cname in CLASS_NAMES.items():
        confs = np.array(all_confs[c], dtype=np.float32)
        tp    = np.array(all_tp[c], dtype=np.int32)
        n_gt  = gt_totals[c]

        # AP from full sweep
        ap = compute_ap(confs, tp, n_gt)

        # P/R at PROD_CONF (filter predictions by confidence)
        keep = confs >= PROD_CONF
        tp_prod = int(tp[keep].sum())
        fp_prod = int((1 - tp[keep]).sum())
        fn_prod = max(n_gt - tp_prod, 0)
        precision = tp_prod / (tp_prod + fp_prod) if (tp_prod + fp_prod) > 0 else 0.0
        recall    = tp_prod / n_gt if n_gt > 0 else 0.0

        # Raw counts across the full sweep (for diagnostic visibility)
        tp_all = int(tp.sum())
        fp_all = int((1 - tp).sum())

        metrics[cname] = {
            f"precision@{PROD_CONF}": round(precision, 4),
            f"recall@{PROD_CONF}":    round(recall, 4),
            "ap":                     round(ap, 4) if not np.isnan(ap) else None,
            f"tp@{PROD_CONF}": tp_prod, f"fp@{PROD_CONF}": fp_prod, f"fn@{PROD_CONF}": fn_prod,
            "tp_allconf": tp_all, "fp_allconf": fp_all,
            "n_gt": n_gt,
        }

    # Only average AP over classes that had GT in this dataset.
    aps = [v["ap"] for k, v in metrics.items()
           if isinstance(v, dict) and v.get("ap") is not None and v.get("n_gt", 0) > 0]
    map_50 = round(sum(aps) / len(aps), 4) if aps else 0.0
    metrics["mAP@0.5"] = map_50
    metrics["_classes_evaluated"] = sorted({c for c in (gt_classes_present if not gt_as_pred and not empty_preds else gt_classes_present)})

    elapsed = time.time() - t0
    metrics["_meta"] = {
        "model": str(model_path) if not (gt_as_pred or empty_preds) else ("gt_as_pred" if gt_as_pred else "empty_preds"),
        "n_images": len(sample), "seed": seed, "imgsz": imgsz,
        "conf_thresh": conf_thresh, "iou_thresh": iou_thresh,
        "elapsed_sec": round(elapsed, 1),
    }
    return metrics, per_image

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", nargs="?", default=None, help="Path to .pt weights (omit for --gt-as-pred or --empty-preds)")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--conf", type=float, default=0.001, help="low to keep PR-curve resolution")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--root", default="datasets/soccernet_h250")
    ap.add_argument("--gt-as-pred", action="store_true")
    ap.add_argument("--empty-preds", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if not args.gt_as_pred and not args.empty_preds and not args.model:
        ap.error("must provide model.pt OR --gt-as-pred OR --empty-preds")

    metrics, per_image = evaluate(
        args.model, args.root, args.n, args.seed, args.imgsz,
        args.conf, args.iou, args.gt_as_pred, args.empty_preds,
    )

    print("\n=== METRICS ===")
    print(json.dumps(metrics, indent=2))

    if args.out is None:
        tag = "gt_as_pred" if args.gt_as_pred else ("empty_preds" if args.empty_preds else Path(args.model).stem)
        args.out = f"outputs/eval/eval_{tag}.json"
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump({"metrics": metrics, "per_image": per_image}, f, indent=2)
    print(f"\nwrote {args.out}")

if __name__ == "__main__":
    main()
