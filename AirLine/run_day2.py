"""run_day2 — AirLine Day 2 proof: lock onto ONE subject and follow it.

Runs tracks via ``core_bridge`` (exactly as Day 1), feeds each frame to a
``TargetTracker``, and renders output where the locked target is visually
distinct and every other subject is de-emphasised, with a live on-screen state
label (LOCKED / TARGET LOST / IDLE). Honestly shows the fragmentation case: when
the target's ID drops for good, the video says TARGET LOST — it does not freeze
the box or follow the wrong subject.

Selection is a deterministic stand-in (NOT gestures — that's Day 4+):
    --target-id 7     lock that track ID
    --auto-first      lock the first ID seen stable for a few frames (default)

Usage:
    python -m AirLine.run_day2 clips/football.mp4 --sport football --auto-first
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2

from AirLine.core_bridge import run_tracker
from AirLine.target import TargetTracker, TargetState

OUTPUT_DIR = Path("AirLine/outputs")
OUTPUT_PATH = OUTPUT_DIR / "day2_target.mp4"

TARGET_COLOR = (0, 255, 0)     # bright green — the locked subject
DIM_COLOR = (110, 110, 110)    # grey — everyone else
LOST_COLOR = (0, 0, 255)       # red — lost label

# auto-first: lock the first ID that persists this many consecutive frames.
STABLE_FRAMES = 3


def _pick_auto_first(candidate_counts, frame_tracks):
    """Update consecutive-appearance counts; return an ID once it is stable."""
    seen = {d.track_id for d in frame_tracks.detections if d.track_id is not None}
    for tid in list(candidate_counts):
        if tid not in seen:
            del candidate_counts[tid]
    for tid in seen:
        candidate_counts[tid] = candidate_counts.get(tid, 0) + 1
        if candidate_counts[tid] >= STABLE_FRAMES:
            return tid
    return None


def _draw_others(frame, frame_tracks, target_id):
    for d in frame_tracks.detections:
        if d.track_id == target_id:
            continue
        x1, y1, x2, y2 = (int(v) for v in d.box)
        cv2.rectangle(frame, (x1, y1), (x2, y2), DIM_COLOR, 1)


def _draw_target(frame, box):
    x1, y1, x2, y2 = (int(v) for v in box)
    cv2.rectangle(frame, (x1, y1), (x2, y2), TARGET_COLOR, 3)
    cv2.circle(frame, ((x1 + x2) // 2, (y1 + y2) // 2), 4, TARGET_COLOR, -1)


def _draw_label(frame, status):
    if status.state == TargetState.LOCKED:
        text, color = f"LOCKED id={status.track_id}", TARGET_COLOR
    elif status.state == TargetState.LOST:
        text, color = f"TARGET LOST id={status.track_id}", LOST_COLOR
    else:
        text, color = "IDLE", (200, 200, 200)
    cv2.rectangle(frame, (0, 0), (360, 34), (0, 0, 0), -1)
    cv2.putText(frame, text, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)


def main() -> None:
    ap = argparse.ArgumentParser(description="AirLine Day 2 target lock-and-follow")
    ap.add_argument("clip")
    ap.add_argument("--sport", default="football", choices=["football", "basketball"])
    ap.add_argument("--device", default=0)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--target-id", type=int, default=None, help="lock this track ID")
    ap.add_argument("--auto-first", action="store_true",
                    help="lock the first stable ID seen (default if no --target-id)")
    ap.add_argument("--miss-threshold", type=int, default=5,
                    help="consecutive missing frames before confirming LOST")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tracker = TargetTracker(miss_threshold=args.miss_threshold)
    if args.target_id is not None:
        tracker.select(args.target_id)

    src_fps = cv2.VideoCapture(args.clip).get(cv2.CAP_PROP_FPS) or 25.0

    writer = None
    candidate_counts: dict[int, int] = {}
    frames = locked = lost = idle = 0
    first_lost_frame = None
    t0 = time.time()

    for ft in run_tracker(args.clip, sport=args.sport, device=args.device, limit=args.limit):
        # auto-first selection (only if nothing chosen yet)
        if tracker.target_id is None and (args.auto_first or args.target_id is None):
            pick = _pick_auto_first(candidate_counts, ft)
            if pick is not None:
                tracker.select(pick)

        status = tracker.update(ft)
        frames += 1
        if status.state == TargetState.LOCKED:
            locked += 1
        elif status.state == TargetState.LOST:
            lost += 1
            if first_lost_frame is None:
                first_lost_frame = frames - 1
        else:
            idle += 1

        if ft.frame is not None:
            if writer is None:
                h, w = ft.frame.shape[:2]
                writer = cv2.VideoWriter(
                    str(OUTPUT_PATH), cv2.VideoWriter_fourcc(*"mp4v"), src_fps, (w, h)
                )
            _draw_others(ft.frame, ft, tracker.target_id)
            box = status.box or tracker.last_box
            if status.state == TargetState.LOCKED and box is not None:
                _draw_target(ft.frame, box)
            _draw_label(ft.frame, status)
            writer.write(ft.frame)

    if writer is not None:
        writer.release()

    elapsed = time.time() - t0
    avg_fps = frames / elapsed if elapsed > 0 else 0.0
    lost_ts = (first_lost_frame / src_fps) if first_lost_frame is not None else None

    print("\n=== AirLine Day 2 ===")
    print(f"clip            : {args.clip}  (sport={args.sport})")
    print(f"locked target id: {tracker.target_id}")
    print(f"frames          : {frames}")
    print(f"LOCKED / LOST   : {locked} / {lost}  (IDLE {idle})")
    print(f"first LOST frame : {first_lost_frame}"
          + (f"  (~{lost_ts:.1f}s @ {src_fps:.0f}fps)" if lost_ts is not None else "  (never lost)"))
    print(f"avg FPS         : {avg_fps:.1f}")
    print(f"annotated output: {OUTPUT_PATH if writer is not None else '(none)'}")


if __name__ == "__main__":
    main()
