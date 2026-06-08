"""run_day1 — AirLine Day 1 proof entry point.

Loads a clip, runs the validated SideLine tracker through ``core_bridge``, and:
  (a) prints a summary (frames, avg FPS, unique track IDs, avg subjects/frame),
  (b) writes an annotated video to ``AirLine/outputs/day1_tracks.mp4`` — drawn by
      AirLine from its OWN track data (no dependency on Ultralytics' plot()),
      which is itself the proof that the bridge returns usable tracks.

Usage:
    python -m AirLine.run_day1 clips/day1_test.mp4 --sport football
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2

from AirLine.core_bridge import run_tracker

OUTPUT_DIR = Path("AirLine/outputs")
OUTPUT_PATH = OUTPUT_DIR / "day1_tracks.mp4"

# Deterministic per-ID colour so the same subject keeps the same box colour.
def _color(track_id: int | None) -> tuple[int, int, int]:
    if track_id is None:
        return (128, 128, 128)
    h = (track_id * 47) % 180
    # cheap HSV->BGR without importing numpy: use cv2 on a 1x1 pixel
    import numpy as np
    px = np.uint8([[[h, 200, 255]]])
    b, g, r = cv2.cvtColor(px, cv2.COLOR_HSV2BGR)[0][0]
    return (int(b), int(g), int(r))


def _draw(frame, ft) -> None:
    for d in ft.detections:
        x1, y1, x2, y2 = (int(v) for v in d.box)
        col = _color(d.track_id)
        cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)
        label = f"{d.cls_name}" + (f" #{d.track_id}" if d.track_id is not None else "")
        cv2.putText(frame, label, (x1, max(0, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)


def main() -> None:
    ap = argparse.ArgumentParser(description="AirLine Day 1 tracker proof")
    ap.add_argument("clip", help="path to input clip")
    ap.add_argument("--sport", default="football", choices=["football", "basketball"])
    ap.add_argument("--device", default=0, help="torch device (default 0 = GPU)")
    ap.add_argument("--limit", type=int, default=None, help="stop after N frames")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    writer = None
    frames = 0
    subjects = 0
    unique: set[int] = set()
    t0 = time.time()

    for ft in run_tracker(args.clip, sport=args.sport, device=args.device, limit=args.limit):
        frames += 1
        subjects += len(ft.detections)
        for d in ft.detections:
            if d.track_id is not None:
                unique.add(d.track_id)

        if ft.frame is not None:
            if writer is None:
                h, w = ft.frame.shape[:2]
                src_fps = cv2.VideoCapture(args.clip).get(cv2.CAP_PROP_FPS) or 25.0
                writer = cv2.VideoWriter(
                    str(OUTPUT_PATH), cv2.VideoWriter_fourcc(*"mp4v"), src_fps, (w, h)
                )
            _draw(ft.frame, ft)
            writer.write(ft.frame)

    if writer is not None:
        writer.release()

    elapsed = time.time() - t0
    avg_fps = frames / elapsed if elapsed > 0 else 0.0
    avg_subjects = subjects / frames if frames else 0.0

    print("\n=== AirLine Day 1 ===")
    print(f"clip            : {args.clip}  (sport={args.sport})")
    print(f"frames processed: {frames}")
    print(f"avg FPS         : {avg_fps:.1f}")
    print(f"unique track IDs: {len(unique)}")
    print(f"avg subjects/frm: {avg_subjects:.1f}")
    print(f"annotated output: {OUTPUT_PATH if writer is not None else '(none — no frames)'}")


if __name__ == "__main__":
    main()
