"""Day 19 Part D: apply the trained ball-vs-not-ball APPEARANCE classifier as a pre-Kalman veto.

Catches HEAD false-positives the Day-16/17 geometric filters miss (Day-17 proved heads aren't
size/geometry-separable; appearance is). Runs the same frozen ResNet18 embedding + logistic head
trained in ball_head_classifier.py (outputs/ball_head/filter.pt), classifying each raw ball-detection
crop as ball vs not-ball and dropping the not-ball detections BEFORE the Kalman sees them.

Crop pipeline matches training EXACTLY (crop_square ctx=1.3 -> 48px -> resize 64 -> ImageNet-norm).
"""
import sys
from pathlib import Path
import numpy as np
import cv2
import torch, torch.nn as nn
import torchvision

sys.path.insert(0, str(Path(__file__).parent))
from ball_head_crops import crop_square


def load_filter(path):
    d = np.load(path, allow_pickle=True)
    return {k: d[k] for k in d.files}


def _resnet(device):
    net = torchvision.models.resnet18(weights=torchvision.models.ResNet18_Weights.DEFAULT)
    net.fc = nn.Identity(); net.eval().to(device)
    return net


def filter_detections(cache_by_frame, frames_dir, filter_path, thr=None, device=None, bs=256):
    """Return a NEW cache_by_frame keeping only detections the classifier scores as ball.

    cache_by_frame: {frame: [(cx, cy, w, h, conf)]} (load_dets_full convention: x,y are CENTER).
    Returns (filtered_cache, stats) in the SAME (cx,cy,w,h,conf) format."""
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    F = load_filter(filter_path)
    in_px = int(F["in_px"]); mean = F["mean"].astype(np.float32); std = F["std"].astype(np.float32)
    w_ = torch.tensor(F["clf_w"], device=device); b_ = torch.tensor(F["clf_b"], device=device)
    thr = float(F["thr"]) if thr is None else float(thr)
    net = _resnet(device)
    frames_dir = Path(frames_dir)

    # gather every detection crop with a back-reference (frame, position-in-list)
    crops, refs = [], []
    for f in sorted(cache_by_frame.keys()):
        dets = cache_by_frame[f]
        if not dets:
            continue
        img = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
        if img is None:
            continue
        for j, d in enumerate(dets):
            cx, cy, w, h = d[0], d[1], d[2], d[3]   # x,y are CENTER (load_dets_full)
            patch = crop_square(img, cx, cy, w, h, ctx=1.3, out=48)
            if patch is None:
                continue
            crops.append(patch); refs.append((f, j))
    keep = set()
    if crops:
        probs = np.empty(len(crops), np.float32)
        with torch.no_grad():
            for i in range(0, len(crops), bs):
                batch = crops[i:i + bs]
                x = np.stack([cv2.cvtColor(cv2.resize(c, (in_px, in_px)), cv2.COLOR_BGR2RGB) for c in batch])
                x = (x.astype(np.float32) / 255.0 - mean) / std
                x = torch.from_numpy(x.transpose(0, 3, 1, 2)).to(device)
                emb = net(x); emb = emb / (emb.norm(dim=1, keepdim=True) + 1e-8)
                logit = (emb @ w_.squeeze().unsqueeze(1)).squeeze(1) + b_.squeeze()
                probs[i:i + len(batch)] = torch.sigmoid(logit).cpu().numpy()
        for (ref, p) in zip(refs, probs):
            if p >= thr:
                keep.add(ref)
    out = {}
    n_in = sum(len(v) for v in cache_by_frame.values())
    for f, dets in cache_by_frame.items():
        kept = [d for j, d in enumerate(dets) if (f, j) in keep]
        if kept:
            out[f] = kept
    n_out = sum(len(v) for v in out.values())
    stats = dict(n_in=n_in, n_out=n_out, n_dropped=n_in - n_out, thr=thr)
    return out, stats
