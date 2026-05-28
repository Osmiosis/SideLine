"""Inspect SoccerNet_v3_H250 test split.

Auto-detects layout (test/images + test/labels  OR  images/test + labels/test).
Verifies image/label parity, tallies class distribution, renders 3 GT samples.

Usage: python scripts/inspect_dataset.py [DATASET_ROOT]
       default DATASET_ROOT = datasets/soccernet_h250
"""
import sys, random
from pathlib import Path
import cv2

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "datasets/soccernet_h250")
CLASS_NAMES = {0: "ball", 1: "person"}
SAMPLE_SEED = 42
NUM_GT_SAMPLES = 3

def find_split(root: Path, split: str):
    """Return (images_dir, labels_dir) for `split`, supporting both layouts."""
    candidates = [
        (root / split / "images", root / split / "labels"),
        (root / "images" / split, root / "labels" / split),
    ]
    for img, lbl in candidates:
        if img.is_dir() and lbl.is_dir():
            return img, lbl
    raise FileNotFoundError(f"No '{split}' split under {root}. Tried: {candidates}")

def list_images(img_dir: Path):
    exts = {".jpg", ".jpeg", ".png"}
    return sorted(p for p in img_dir.iterdir() if p.suffix.lower() in exts)

def parse_label(path: Path):
    """Return list of (cls, cx, cy, w, h) — all floats except cls (int)."""
    if not path.exists(): return []
    rows = []
    for line in path.read_text().splitlines():
        parts = line.strip().split()
        if len(parts) != 5: continue
        cls, cx, cy, w, h = int(parts[0]), *map(float, parts[1:])
        rows.append((cls, cx, cy, w, h))
    return rows

def draw_gt(img_path: Path, lbl_path: Path, out_path: Path):
    img = cv2.imread(str(img_path))
    if img is None:
        print(f"  ! cannot read {img_path}"); return
    H, W = img.shape[:2]
    for cls, cx, cy, w, h in parse_label(lbl_path):
        x1 = int((cx - w/2) * W); y1 = int((cy - h/2) * H)
        x2 = int((cx + w/2) * W); y2 = int((cy + h/2) * H)
        color = (0, 0, 255) if cls == 0 else (0, 255, 0)  # ball=red, person=green
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        cv2.putText(img, CLASS_NAMES.get(cls, str(cls)), (x1, max(0, y1-5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), img)

def main():
    print(f"ROOT = {ROOT}")
    img_dir, lbl_dir = find_split(ROOT, "test")
    print(f"images: {img_dir}")
    print(f"labels: {lbl_dir}")

    imgs = list_images(img_dir)
    print(f"\nimage count: {len(imgs)}")

    missing = []
    cls_counts = {}
    for p in imgs:
        lbl = lbl_dir / (p.stem + ".txt")
        if not lbl.exists():
            missing.append(p.name); continue
        for cls, *_ in parse_label(lbl):
            cls_counts[cls] = cls_counts.get(cls, 0) + 1

    print(f"labels present: {len(imgs) - len(missing)} / {len(imgs)}")
    if missing:
        print(f"  WARNING: {len(missing)} images without labels (first 5): {missing[:5]}")

    print(f"\nclass instance counts:")
    for cls in sorted(cls_counts):
        print(f"  {cls} ({CLASS_NAMES.get(cls, '?')}): {cls_counts[cls]}")

    # Render GT samples
    random.seed(SAMPLE_SEED)
    # Prefer samples that actually contain a ball — that's the class we care about
    with_ball = [p for p in imgs if any(c == 0 for c, *_ in parse_label(lbl_dir / (p.stem + ".txt")))]
    pool = with_ball if len(with_ball) >= NUM_GT_SAMPLES else imgs
    sample = random.sample(pool, NUM_GT_SAMPLES)
    print(f"\nRendering {NUM_GT_SAMPLES} GT samples (from {'ball-containing' if pool is with_ball else 'all'} pool):")
    for i, p in enumerate(sample):
        out = Path("outputs") / f"gt_sample_{i+1}.png"
        draw_gt(p, lbl_dir / (p.stem + ".txt"), out)
        print(f"  {p.name} -> {out}")

    print("\nDeveloper: open outputs/gt_sample_*.png and verify boxes sit on real ball/players.")

if __name__ == "__main__":
    main()
