"""run_day3 — AirLine Day 3 proof: an operated following shot.

Pipeline per frame:
    core_bridge tracks -> TargetTracker.update -> VirtualCamera -> crop+resize
    -> AirLine/outputs/day3_follow.mp4

The primary deliverable is the cropped follow video. With --debug-pip it also
draws the wide frame with the crop rectangle overlaid (picture-in-picture) for
eyeballing the camera's decisions.

Reports a jitter proxy (mean crop-centre px/frame while LOCKED) and a
responsiveness proxy (frames to re-centre after the fastest target jump).

Usage:
    python -m AirLine.run_day3 clips/football.mp4 --sport football --auto-first
"""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import cv2

from AirLine.core_bridge import run_tracker
from AirLine.target import TargetTracker, TargetState
from AirLine.camera import VirtualCamera, CameraConfig

OUTPUT_DIR = Path("AirLine/outputs")
OUTPUT_PATH = OUTPUT_DIR / "day3_follow.mp4"

STABLE_FRAMES = 3  # auto-first: lock first ID stable this many consecutive frames


def _pick_auto_first(counts, ft):
    seen = {d.track_id for d in ft.detections if d.track_id is not None}
    for tid in list(counts):
        if tid not in seen:
            del counts[tid]
    for tid in seen:
        counts[tid] = counts.get(tid, 0) + 1
        if counts[tid] >= STABLE_FRAMES:
            return tid
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="AirLine Day 3 virtual follow camera")
    ap.add_argument("clip")
    ap.add_argument("--sport", default="football", choices=["football", "basketball"])
    ap.add_argument("--device", default=0)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--target-id", type=int, default=None)
    ap.add_argument("--auto-first", action="store_true")
    ap.add_argument("--miss-threshold", type=int, default=5)
    ap.add_argument("--debug-pip", action="store_true",
                    help="overlay wide frame + crop rect in a corner")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = CameraConfig()
    tracker = TargetTracker(miss_threshold=args.miss_threshold)
    camera = VirtualCamera(cfg)
    # --target-id selection is DEFERRED until that id is first seen, so a subject
    # that appears mid-clip locks correctly instead of confirming LOST before it
    # ever shows up. (Stand-in input only — does not touch any Day 1/2 contract.)
    requested_id = args.target_id

    src_fps = cv2.VideoCapture(args.clip).get(cv2.CAP_PROP_FPS) or 25.0
    writer = cv2.VideoWriter(
        str(OUTPUT_PATH), cv2.VideoWriter_fourcc(*"mp4v"), src_fps, (cfg.out_w, cfg.out_h)
    )

    counts: dict[int, int] = {}
    frames = locked = lost = 0
    first_lost_frame = None
    # jitter (LOCKED-phase crop-centre movement)
    prev_c = None
    jitter_sum = 0.0
    jitter_n = 0
    # responsiveness bookkeeping
    prev_t = None
    biggest_jump = 0.0
    biggest_jump_frame = None
    t0 = time.time()

    for ft in run_tracker(args.clip, sport=args.sport, device=args.device, limit=args.limit):
        if tracker.target_id is None:
            if requested_id is not None:
                if any(d.track_id == requested_id for d in ft.detections):
                    tracker.select(requested_id)
            elif args.auto_first or args.target_id is None:
                pick = _pick_auto_first(counts, ft)
                if pick is not None:
                    tracker.select(pick)

        status = tracker.update(ft)
        box = status.box or tracker.last_box
        frame = ft.frame
        H, W = frame.shape[:2]
        crop = camera.update(box if status.state == TargetState.LOCKED else None,
                             status.state, (W, H))

        frames += 1
        if status.state == TargetState.LOCKED:
            locked += 1
            c = (crop.cx, crop.cy)
            if prev_c is not None:
                jitter_sum += math.hypot(c[0] - prev_c[0], c[1] - prev_c[1])
                jitter_n += 1
            prev_c = c
            if box is not None:
                tc = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)
                if prev_t is not None:
                    j = math.hypot(tc[0] - prev_t[0], tc[1] - prev_t[1])
                    if j > biggest_jump:
                        biggest_jump, biggest_jump_frame = j, frames - 1
                prev_t = tc
        else:
            if status.state == TargetState.LOST:
                lost += 1
                if first_lost_frame is None:
                    first_lost_frame = frames - 1
            prev_c = None
            prev_t = None

        # crop + resize to fixed output
        sub = frame[crop.y:crop.y + crop.h, crop.x:crop.x + crop.w]
        out = cv2.resize(sub, (cfg.out_w, cfg.out_h), interpolation=cv2.INTER_LINEAR)

        if args.debug_pip:
            pip_w = cfg.out_w // 4
            pip_h = int(pip_w * H / W)
            wide = cv2.resize(frame, (pip_w, pip_h))
            sx, sy = pip_w / W, pip_h / H
            cv2.rectangle(wide, (int(crop.x * sx), int(crop.y * sy)),
                          (int((crop.x + crop.w) * sx), int((crop.y + crop.h) * sy)),
                          (0, 255, 0), 1)
            out[0:pip_h, cfg.out_w - pip_w:cfg.out_w] = wide
        label = (f"LOCKED id={status.track_id}" if status.state == TargetState.LOCKED
                 else "TARGET LOST" if status.state == TargetState.LOST else "IDLE")
        cv2.putText(out, label, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (0, 255, 0) if status.state == TargetState.LOCKED else (0, 0, 255),
                    2, cv2.LINE_AA)
        writer.write(out)

    writer.release()
    elapsed = time.time() - t0
    avg_fps = frames / elapsed if elapsed > 0 else 0.0
    jitter = jitter_sum / jitter_n if jitter_n else 0.0
    lost_ts = (first_lost_frame / src_fps) if first_lost_frame is not None else None

    print("\n=== AirLine Day 3 ===")
    print(f"clip             : {args.clip}  (sport={args.sport})")
    print(f"locked target id : {tracker.target_id}")
    print(f"frames           : {frames}   LOCKED {locked} / LOST {lost}")
    print(f"first LOST frame : {first_lost_frame}"
          + (f"  (~{lost_ts:.1f}s)" if lost_ts is not None else "  (never)"))
    print(f"jitter (LOCKED)  : {jitter:.2f} px/frame mean crop-centre movement")
    if biggest_jump_frame is not None:
        print(f"fastest target jump: {biggest_jump:.0f}px at frame {biggest_jump_frame}")
    print(f"avg FPS          : {avg_fps:.1f}")
    print(f"output           : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
