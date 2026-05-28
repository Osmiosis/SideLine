"""Fine-tune yolov8m on YOLOBball (ball-only basketball detector).

Per Day 5 PRD:
- base weights: yolov8m.pt (COCO-pretrained)
- imgsz=1280 to match eval resolution
- epochs=50 with early-stopping patience=10
- batch=-1 (autobatch)
- fixed seed for reproducibility
- runs save under runs/train/bball_ft/ (gitignored)

If OOM at imgsz=1280, retry with imgsz=960 (this script does it once).
"""
from ultralytics import YOLO
import torch, sys

DATA   = "datasets/basketball_yolobball/data.yaml"
MODEL  = "yolov8m.pt"
EPOCHS = 50
PATIENCE = 10
SEED   = 42

import argparse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--workers", type=int, default=2,
                    help="dataloader workers; lower = more stable on Windows; 0 = single-process")
    ap.add_argument("--epochs", type=int, default=EPOCHS)
    args = ap.parse_args()

    print(f"=== train imgsz={args.imgsz} batch={args.batch} workers={args.workers} epochs={args.epochs} ===", flush=True)
    model = YOLO(MODEL)
    results = model.train(
        data=DATA,
        imgsz=args.imgsz,
        epochs=args.epochs,
        patience=PATIENCE,
        batch=args.batch,
        workers=args.workers,
        amp=True,          # mixed precision — saves VRAM headroom on 4060 8GB
        cache=False,       # do not RAM-cache (already tight)
        device=0,
        seed=SEED,
        project="runs/train",
        name="bball_ft",
        exist_ok=True,
        verbose=True,
    )
    print("\n=== DONE ===")
    print("save_dir:", results.save_dir if hasattr(results, "save_dir") else "?")

if __name__ == "__main__":
    main()
