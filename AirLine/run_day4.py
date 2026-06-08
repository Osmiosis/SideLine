"""run_day4 — gestures driving the cinematography.

Two input sources, one executor (TargetTracker + VirtualCamera):

  --source scripted  (default): a per-frame raw-gesture LABEL timeline is fed
      through the REAL GestureEngine (debounce and all) — no webcam, no mediapipe.
      The timeline deliberately includes a 1-frame flicker that must NOT fire, to
      prove the debounce on-screen. Produces AirLine/outputs/day4_gestured.mp4.

  --source webcam: live MediaPipe hand landmarks from your camera drive the same
      pipeline. Requires mediapipe installed in an ISOLATED env (see Step-2 flag
      in notes.md) and a webcam — gated, not run by default.

On-screen overlay shows the raw gesture, the confirmed intent (flash), and the
resulting target/shot/state so the demo is legible.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2

from AirLine.core_bridge import run_tracker
from AirLine.target import TargetTracker, TargetState
from AirLine.camera import VirtualCamera, CameraConfig
from AirLine.gestures import Gesture, GestureEngine, INDEX_TIP
from AirLine.intent import IntentApplier, gesture_to_intent, IntentCommand

OUTPUT_DIR = Path("AirLine/outputs")
OUTPUT_PATH = OUTPUT_DIR / "day4_gestured.mp4"

# Scripted raw-gesture timeline: (start_frame, held_frames, Gesture).
# Held static gestures fire ONCE after the debounce window; swipes are one-shot.
# The lone 1-frame FIST at f70 is the debounce proof: it must NOT fire.
SCRIPT = [
    (30, 15, Gesture.POINT),       # -> SELECT (nearest-centre subject)
    (70, 1, Gesture.FIST),         # flicker: must NOT fire
    (90, 15, Gesture.FIST),        # -> SHOT_TIGHT
    (150, 1, Gesture.SWIPE_RIGHT),  # -> SWITCH_NEXT (one-shot)
    (210, 16, Gesture.SPREAD),     # -> SHOT_WIDE
    (300, 1, Gesture.SWIPE_RIGHT),  # -> SWITCH_NEXT
    (360, 16, Gesture.FIST),       # -> SHOT_TIGHT
    (450, 16, Gesture.OPEN_PALM),  # -> RELEASE
]


def _label_at(frame: int) -> Gesture:
    for start, held, g in SCRIPT:
        if start <= frame < start + held:
            return g
    return Gesture.NONE


def _overlay(out, raw, fired_cmd, flash, tracker, applier, state):
    shot = applier.shot.value if applier.shot else "-"
    lines = [
        f"raw: {raw.value}",
        f"target: {tracker.target_id}   shot: {shot}   state: {state.value}",
    ]
    cv2.rectangle(out, (0, 0), (560, 64), (0, 0, 0), -1)
    cv2.putText(out, lines[0], (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(out, lines[1], (8, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)
    if flash > 0 and fired_cmd is not None:
        cv2.putText(out, f">> {fired_cmd.value.upper()}", (8, 96),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 215, 255), 2, cv2.LINE_AA)


def run_scripted(args):
    cfg = CameraConfig()
    tracker = TargetTracker(miss_threshold=args.miss_threshold)
    camera = VirtualCamera(cfg)
    engine = GestureEngine(confirm_frames=args.confirm_frames)
    applier = IntentApplier(tracker, camera)

    src_fps = cv2.VideoCapture(args.clip).get(cv2.CAP_PROP_FPS) or 30.0
    writer = cv2.VideoWriter(str(OUTPUT_PATH), cv2.VideoWriter_fourcc(*"mp4v"),
                             src_fps, (cfg.out_w, cfg.out_h))

    fired = []          # (frame, intent)
    flicker_fired = False
    flash = 0
    last_cmd = None
    t0 = time.time()
    frames = 0

    for f, ft in enumerate(run_tracker(args.clip, sport=args.sport,
                                       device=args.device, limit=args.limit)):
        raw = _label_at(f)
        if raw in (Gesture.SWIPE_LEFT, Gesture.SWIPE_RIGHT):
            confirmed = raw                # swipes are one-shot
            engine.feed_label(Gesture.NONE)
        else:
            confirmed = engine.feed_label(raw)

        cmd = gesture_to_intent(confirmed)
        if cmd is not None:
            applier.apply(cmd, ft, frame_w=ft.frame.shape[1])
            fired.append((f, cmd))
            last_cmd, flash = cmd, 12
            if 70 <= f < 71:               # would only happen if flicker wrongly fired
                flicker_fired = True

        status = tracker.update(ft)
        crop = camera.update(status.box or tracker.last_box
                             if status.state == TargetState.LOCKED else None,
                             status.state, (ft.frame.shape[1], ft.frame.shape[0]))

        sub = ft.frame[crop.y:crop.y + crop.h, crop.x:crop.x + crop.w]
        out = cv2.resize(sub, (cfg.out_w, cfg.out_h), interpolation=cv2.INTER_LINEAR)
        _overlay(out, raw, last_cmd, flash, tracker, applier, status.state)
        flash = max(0, flash - 1)
        writer.write(out)
        frames += 1

    writer.release()
    elapsed = time.time() - t0
    latency_ms = 1000.0 * args.confirm_frames / src_fps

    print("\n=== AirLine Day 4 (scripted) ===")
    print(f"clip            : {args.clip}")
    print(f"frames          : {frames}   avg FPS {frames/elapsed:.1f}")
    print(f"confirm window  : {args.confirm_frames} frames (~{latency_ms:.0f} ms @ {src_fps:.0f}fps)")
    print(f"intents fired   : {len(fired)}")
    for f, c in fired:
        print(f"    frame {f:4d}  {c.value}")
    print(f"flicker @f70 fired? {flicker_fired}  (expected: False)")
    print(f"output          : {OUTPUT_PATH}")


def run_webcam(args):  # pragma: no cover - needs mediapipe (isolated env) + webcam
    # NOTE: a COMBINED live demo (gestures driving the football crop) needs BOTH
    # mediapipe (gestures venv) AND ultralytics (main venv) — which cannot coexist
    # in one venv (that's the whole quarantine). So this path only runs as part of
    # a future two-process bridge (capture proc emits intents -> render proc applies
    # them). For the Day-5 recognition NUMBER, you do NOT need the tracker at all —
    # use the standalone, ultralytics-free tool instead:
    #     PYTHONPATH=. C:\airline-gestures-venv\Scripts\python.exe -m AirLine.gesture_eval
    try:
        from AirLine.gestures import MediaPipeHandSource
    except ModuleNotFoundError as e:
        raise SystemExit(
            "webcam combined demo needs both stacks in one process, which the "
            "quarantine forbids. Run the recognition eval instead:\n"
            "  PYTHONPATH=. C:\\airline-gestures-venv\\Scripts\\python.exe "
            "-m AirLine.gesture_eval"
        ) from e
    cfg = CameraConfig()
    tracker = TargetTracker(miss_threshold=args.miss_threshold)
    camera = VirtualCamera(cfg)
    engine = GestureEngine(confirm_frames=args.confirm_frames)
    applier = IntentApplier(tracker, camera)
    source = MediaPipeHandSource()
    cam = cv2.VideoCapture(args.webcam)

    src_fps = cv2.VideoCapture(args.clip).get(cv2.CAP_PROP_FPS) or 30.0
    writer = cv2.VideoWriter(str(OUTPUT_PATH), cv2.VideoWriter_fourcc(*"mp4v"),
                             src_fps, (cfg.out_w, cfg.out_h))
    last_cmd, flash = None, 0
    for ft in run_tracker(args.clip, sport=args.sport, device=args.device, limit=args.limit):
        ok, wframe = cam.read()
        lm = source.landmarks(wframe) if ok else None
        if lm is not None and args.mirror:
            lm = [(1.0 - x, y) for (x, y) in lm]
        confirmed = engine.feed_landmarks(lm)
        cmd = gesture_to_intent(confirmed)
        W = ft.frame.shape[1]
        ref_x = lm[INDEX_TIP][0] * W if lm is not None else None
        if cmd is not None:
            applier.apply(cmd, ft, ref_x=ref_x, frame_w=W)
            last_cmd, flash = cmd, 12
        status = tracker.update(ft)
        crop = camera.update(status.box or tracker.last_box
                             if status.state == TargetState.LOCKED else None,
                             status.state, (W, ft.frame.shape[0]))
        sub = ft.frame[crop.y:crop.y + crop.h, crop.x:crop.x + crop.w]
        out = cv2.resize(sub, (cfg.out_w, cfg.out_h))
        _overlay(out, confirmed or Gesture.NONE, last_cmd, flash, tracker, applier, status.state)
        flash = max(0, flash - 1)
        writer.write(out)
    writer.release()
    cam.release()
    print(f"output: {OUTPUT_PATH}")


def main():
    global OUTPUT_PATH
    ap = argparse.ArgumentParser(description="AirLine Day 4 gesture-directed camera")
    ap.add_argument("clip", nargs="?", default="clips/football.mp4")
    ap.add_argument("--sport", default="football", choices=["football", "basketball"])
    ap.add_argument("--source", default="scripted", choices=["scripted", "webcam"])
    ap.add_argument("--device", default=0)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--confirm-frames", type=int, default=6)
    ap.add_argument("--miss-threshold", type=int, default=5)
    ap.add_argument("--webcam", type=int, default=0)
    ap.add_argument("--mirror", action="store_true", default=True)
    ap.add_argument("--out", default=str(OUTPUT_PATH), help="output video path")
    args = ap.parse_args()
    OUTPUT_PATH = Path(args.out)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    (run_webcam if args.source == "webcam" else run_scripted)(args)


if __name__ == "__main__":
    main()
