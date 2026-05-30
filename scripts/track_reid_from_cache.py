"""Day-26: BoT-SORT WITH appearance-ReID over CACHED detections + frames.

Identical to track_botsort_from_cache.py (GMC + Day-9 tuned thresholds) EXCEPT the
ReID appearance arm is ENABLED. This isolates the measured delta to ReID alone:
keep gmc_method=sparseOptFlow, keep the Day-9 match_thresh, add with_reid=True.

Why a real encoder model (not model="auto"): ultralytics' "auto" ReID path expects
the YOLO detector to have ALREADY produced per-detection embeddings and passes them in
as `img` (init_track -> encoder(img, bboxes) where encoder just .cpu()s `img`). Our
cached pipeline feeds raw frames (cv2.imread), so "auto" would iterate image rows as
"features" -> garbage. Instead we point `model` at a real YOLO .pt; ultralytics' ReID
class then crops each box (save_one_box) and extracts layer (-2) backbone embeddings.
We use the SAME football detector that produced the cached detections (models/soccana.pt)
so appearance features come from a football-trained backbone.

ReID runs a YOLO forward per detection crop -> GPU step, heavier than the GMC-only
sweep. We process seq-by-seq and clear CUDA cache between seqs (TDR/OOM guard, per the
earlier VIDEO_TDR days).

Usage (Day-9 SoccerNet config + ReID):
  python scripts/track_reid_from_cache.py \
      --cache outputs/det_cache/sn_soccana \
      --source datasets/soccernet_tracking \
      --out outputs/track_results/sn_soccana_botsort_reid \
      --reid-model models/soccana.pt \
      --param match_thresh=0.9
"""
import argparse, time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import cv2
import torch
import yaml

import sys
sys.path.insert(0, str(Path(__file__).parent))
from track_from_cache import parse_seqinfo, load_cache, boxes_to_track_input  # noqa: E402


class ResNetReID:
    """Frozen ResNet18 (ImageNet) crop encoder -> 512-d L2-normalised appearance embedding.

    Drop-in for ultralytics BOTSORT.encoder: __call__(img, dets) where dets[:, :4] are
    xywh-CENTER boxes (as init_track passes them). Returns one feature vector per box.
    Same backbone/normalisation the project used for team-assignment torso embeddings
    (Day 22/23) — a real identity descriptor, unlike the YOLO detection-head feature map.
    """

    def __init__(self, device=None, size=(128, 64)):
        import torchvision as tv
        import torch.nn as nn
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        backbone = tv.models.resnet18(weights=tv.models.ResNet18_Weights.IMAGENET1K_V1)
        self.model = nn.Sequential(*list(backbone.children())[:-1]).eval().to(self.device)
        self.mean = torch.tensor([0.485, 0.456, 0.406], device=self.device).view(1, 3, 1, 1)
        self.std = torch.tensor([0.229, 0.224, 0.225], device=self.device).view(1, 3, 1, 1)
        self.size = size  # H, W

    @torch.no_grad()
    def __call__(self, img, dets):
        H, W = img.shape[:2]
        xc, yc, w, h = dets[:, 0], dets[:, 1], dets[:, 2], dets[:, 3]
        x1 = np.clip((xc - w / 2).astype(int), 0, W - 1)
        y1 = np.clip((yc - h / 2).astype(int), 0, H - 1)
        x2 = np.clip((xc + w / 2).astype(int), 1, W)
        y2 = np.clip((yc + h / 2).astype(int), 1, H)
        batch = []
        for i in range(len(dets)):
            crop = img[y1[i]:max(y2[i], y1[i] + 1), x1[i]:max(x2[i], x1[i] + 1)]
            if crop.size == 0:
                crop = np.zeros((8, 8, 3), np.uint8)
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            rgb = cv2.resize(rgb, (self.size[1], self.size[0]), interpolation=cv2.INTER_LINEAR)
            batch.append(rgb)
        arr = np.stack(batch).astype(np.float32) / 255.0
        t = torch.from_numpy(arr).permute(0, 3, 1, 2).to(self.device)
        t = (t - self.mean) / self.std
        feats = torch.nn.functional.normalize(self.model(t).flatten(1), dim=1)
        return [f.cpu().numpy() for f in feats]


def make_botsort_reid(overrides: dict, frame_rate: int, reid_model: str, backbone: str):
    from ultralytics.trackers.bot_sort import BOTSORT
    import ultralytics
    yml = Path(ultralytics.__file__).parent / "cfg" / "trackers" / "botsort.yaml"
    cfg = yaml.safe_load(yml.read_text())
    cfg["frame_rate"] = frame_rate
    if overrides:
        cfg.update(overrides)
    # The ReID arm: the ONLY change vs the Day-9 GMC baseline.
    cfg["with_reid"] = True
    if backbone == "resnet18":
        cfg["model"] = "auto"  # stop ultralytics building its own (broken) YOLO encoder
        tracker = BOTSORT(SimpleNamespace(**cfg))
        tracker.encoder = ResNetReID()  # swap in the discriminative appearance encoder
    else:  # "yolo" — ultralytics-native: crop -> YOLO layer(-2) feature map (non-discriminative)
        cfg["model"] = reid_model
        tracker = BOTSORT(SimpleNamespace(**cfg))
    return tracker, cfg

def track_seq(cache_path: Path, seq_dir: Path, out_path: Path, overrides: dict,
              reid_model: str, backbone: str):
    info = parse_seqinfo(seq_dir)
    img_dir = seq_dir / "img1"
    by_frame = load_cache(cache_path)
    tracker, _ = make_botsort_reid(overrides, info["frameRate"], reid_model, backbone)
    out_lines = []
    for f in range(1, info["seqLength"] + 1):
        img = cv2.imread(str(img_dir / f"{f:06d}.jpg"))  # frame for GMC + ReID crops
        if img is None:
            continue
        det_obj = boxes_to_track_input(by_frame.get(f, []), (info["imHeight"], info["imWidth"]))
        online = tracker.update(det_obj, img=img)
        if online is None or len(online) == 0:
            continue
        for row in online:
            x1, y1, x2, y2 = row[:4]
            tid = int(row[4]); cf = float(row[5])
            w = float(x2 - x1); h = float(y2 - y1)
            out_lines.append(f"{f},{tid},{x1:.2f},{y1:.2f},{w:.2f},{h:.2f},{cf:.4f},-1,-1,-1")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out_lines) + ("\n" if out_lines else ""))
    return len(out_lines)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--reid-backbone", default="resnet18", choices=["resnet18", "yolo"],
                    help="resnet18 = frozen ImageNet ResNet18 crop encoder (discriminative); "
                         "yolo = ultralytics-native ReID(model) detection-feature map")
    ap.add_argument("--reid-model", default="models/soccana.pt",
                    help="YOLO .pt used as the ReID encoder when --reid-backbone yolo")
    ap.add_argument("--param", action="append", default=[],
                    help="Override botsort.yaml: e.g. --param match_thresh=0.9")
    ap.add_argument("--only", default=None, help="Run a single seq by name (smoke test)")
    args = ap.parse_args()

    overrides = {}
    for p in args.param:
        k, v = p.split("=", 1)
        try:    v = int(v)
        except ValueError:
            try: v = float(v)
            except ValueError:
                if v.lower() in ("true", "false"): v = v.lower() == "true"
        overrides[k] = v
    print(f"reid_backbone: {args.reid_backbone}  reid_model: {args.reid_model}  overrides: {overrides}")

    source = Path(args.source); cache = Path(args.cache); out = Path(args.out)
    seqs = sorted(d for d in source.iterdir() if d.is_dir() and (d / "seqinfo.ini").exists())
    if args.only:
        seqs = [d for d in seqs if d.name == args.only]
    for seq_dir in seqs:
        t0 = time.time()
        n = track_seq(cache / f"{seq_dir.name}.txt", seq_dir, out / f"{seq_dir.name}.txt",
                      overrides, args.reid_model, args.reid_backbone)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()  # TDR/OOM guard between seqs
        print(f"  {seq_dir.name}: {n} rows  ({time.time()-t0:.1f}s)")

if __name__ == "__main__":
    main()
