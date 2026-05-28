"""Fine-tune yolov8m on SportsMOT basketball players.

Mirrors Day 5 train_basketball.py (which worked): imgsz=1280, batch=4, workers=2,
amp=True, cache=False, seed=42, patience=10.
"""
import argparse
from ultralytics import YOLO

DATA = "datasets/sportsmot_player_train/data.yaml"
MODEL = "yolov8m.pt"
EPOCHS = 30
PATIENCE = 10
SEED = 42

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--workers", type=int, default=2)
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
        amp=True,
        cache=False,
        device=0,
        seed=SEED,
        project="runs/train",
        name="player_ft",
        exist_ok=True,
        verbose=True,
    )
    print("\n=== DONE ===")
    print("save_dir:", results.save_dir if hasattr(results, "save_dir") else "?")

if __name__ == "__main__":
    main()
