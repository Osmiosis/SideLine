"""bridge_capture — the capture process (Day 6).

Runs in `.venv-gestures` for the real webcam path (mediapipe, NO ultralytics) or
anywhere for `--mock` (scripted intents, no mediapipe). Connects to the render
process and emits a typed IntentMessage ONLY on confirmed-intent transitions
(the Day-4 debounce already gates this — no per-frame spam).

Real:
    set PYTHONPATH=.
    C:\\airline-gestures-venv\\Scripts\\python.exe -m AirLine.bridge_capture --host 127.0.0.1 --port 8765
Mock (hands-free, runs in main venv too):
    python -m AirLine.bridge_capture --mock
"""

from __future__ import annotations

import argparse
import socket
import time

from AirLine.bridge_protocol import IntentMessage, encode
from AirLine.intent_types import IntentCommand, gesture_to_intent

# Mock timeline: (delay_before_seconds, IntentCommand). Spread across ~clip length
# so the rendered cinematography visibly changes over time.
MOCK_SCRIPT = [
    (1.5, IntentCommand.SELECT),
    (3.0, IntentCommand.SHOT_TIGHT),
    (3.0, IntentCommand.SWITCH_NEXT),
    (3.0, IntentCommand.SHOT_WIDE),
    (3.0, IntentCommand.SWITCH_NEXT),
    (3.0, IntentCommand.SHOT_TIGHT),
    (3.0, IntentCommand.RELEASE),
]


def _send(sock, seq, intent_value, payload):
    msg = IntentMessage(intent=intent_value, ts=time.time(), seq=seq, payload=payload)
    sock.sendall(encode(msg))
    return msg


def _connect_with_retry(host, port, total_wait=40.0):
    """Render warms its model before it listens, so retry until it's up."""
    deadline = time.time() + total_wait
    while True:
        try:
            return socket.create_connection((host, port), timeout=5)
        except (ConnectionRefusedError, OSError):
            if time.time() > deadline:
                raise
            time.sleep(0.5)


def run_mock(args):
    sock = _connect_with_retry(args.host, args.port)
    print(f"[capture/mock] connected to {args.host}:{args.port}")
    seq = 0
    try:
        for delay, cmd in MOCK_SCRIPT:
            time.sleep(delay)
            _send(sock, seq, cmd.value, {"ref_x": 0.5, "confirm_ms": 432.0})
            print(f"[capture/mock] sent #{seq} {cmd.value}")
            seq += 1
    finally:
        time.sleep(0.5)
        sock.close()
        print("[capture/mock] done")


def run_real(args):  # pragma: no cover - needs webcam + mediapipe
    import cv2
    from AirLine.gestures import Gesture, GestureEngine, HandClassifier, MediaPipeHandSource

    source = MediaPipeHandSource()
    engine = GestureEngine(confirm_frames=args.confirm_frames)
    clf = HandClassifier(spread_threshold=args.spread_threshold)
    cap = cv2.VideoCapture(args.camera)
    sock = socket.create_connection((args.host, args.port), timeout=10)
    print(f"[capture] connected to {args.host}:{args.port}. q in preview to quit.")

    seq = 0
    raw_prev, raw_started = None, time.time()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue
            lm = source.landmarks(frame)
            if lm is not None and args.mirror:
                lm = [(1.0 - x, y) for (x, y) in lm]

            # track gesture->confirmed latency: when did the current raw pose begin?
            raw = clf.classify(lm) if lm is not None else Gesture.NONE
            if raw != raw_prev:
                raw_prev, raw_started = raw, time.time()

            confirmed = engine.feed_landmarks(lm)
            cmd = gesture_to_intent(confirmed)
            if cmd is not None:
                ref_x = lm[8][0] if lm is not None else 0.5  # index-tip x, normalized
                confirm_ms = 1000.0 * (time.time() - raw_started)
                try:
                    _send(sock, seq, cmd.value, {"ref_x": ref_x, "confirm_ms": confirm_ms})
                except (ConnectionError, OSError):
                    print("[capture] render disconnected (clip ended) — stopping.")
                    break
                print(f"[capture] sent #{seq} {cmd.value}  confirm={confirm_ms:.0f}ms")
                seq += 1

            disp = frame.copy()
            cv2.putText(disp, f"raw: {raw.value}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.imshow("AirLine capture (q=quit)", disp)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        sock.close()
        print("[capture] closed")


def main():
    ap = argparse.ArgumentParser(description="AirLine Day 6 gesture capture process")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--mock", action="store_true", help="emit scripted intents, no webcam")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--confirm-frames", type=int, default=6)
    ap.add_argument("--spread-threshold", type=float, default=1.4)
    ap.add_argument("--mirror", action="store_true", default=True)
    args = ap.parse_args()
    (run_mock if args.mock else run_real)(args)


if __name__ == "__main__":
    main()
