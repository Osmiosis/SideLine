"""Adapters that turn a job's raw inputs into the shapes the existing CV scripts
expect. NO CV logic — just decode + a homography solve."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from backend import landmarks


def decode_video(video_path: Path | str, frames_root: Path | str, *, seq: str,
                 frame_rate_default: float = 25.0) -> dict:
    """Extract frames to <frames_root>/<seq>/img1/%06d.jpg (1-indexed) and write
    seqinfo.ini. Returns {n_frames, width, height, frame_rate}."""
    video_path = Path(video_path)
    seq_dir = Path(frames_root) / seq
    img1 = seq_dir / "img1"
    img1.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    fr = cap.get(cv2.CAP_PROP_FPS) or frame_rate_default
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            n += 1
            cv2.imwrite(str(img1 / f"{n:06d}.jpg"), frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 92])
    finally:
        cap.release()

    (seq_dir / "seqinfo.ini").write_text(
        "[Sequence]\n"
        f"name={seq}\n"
        f"seqLength={n}\n"
        f"frameRate={round(fr) or 25}\n"
        "imDir=img1\n"
        "imExt=.jpg\n"
        f"imWidth={w}\n"
        f"imHeight={h}\n", encoding="utf-8")
    return {"n_frames": n, "width": w, "height": h, "frame_rate": fr}


def write_homography(calibration_points: list[dict], sport: str,
                     out_path: Path | str) -> dict:
    """Solve H from the 4 marked points + per-sport landmark template; write
    homography.json in the mark_court.py schema. H_court_from_img maps pixels
    -> pitch metres (the matrix downstream scripts feed to perspectiveTransform)."""
    labels = [p["real_world_label"] for p in calibration_points]
    src = np.array([[p["pixel_x"], p["pixel_y"]] for p in calibration_points],
                   dtype=np.float32)
    dst = np.array(landmarks.world_points(sport, labels), dtype=np.float32)
    H_ci, _ = cv2.findHomography(src, dst)   # pixel -> metres
    H_ic, _ = cv2.findHomography(dst, src)   # metres -> pixel
    payload = {
        "seq": None, "sport": sport,
        "H_court_from_img": H_ci.tolist(),
        "H_img_from_court": H_ic.tolist(),
        "points": [{"name": labels[i], "img": [float(src[i][0]), float(src[i][1])],
                    "court": [float(dst[i][0]), float(dst[i][1])]}
                   for i in range(len(labels))],
        "method": "operator-marked (4-corner findHomography)",
        "n_clicked": len(labels), "n_used": len(labels),
    }
    Path(out_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
