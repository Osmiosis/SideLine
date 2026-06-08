"""gesture_eval — measure live webcam gesture recognition rate (Part A number).

WHY THIS IS SEPARATE FROM run_day4:
  The recognition rate is purely about hand -> confirmed gesture label. It needs
  MediaPipe (gestures venv) but NOT the tracker. run_day4's webcam path also pulls
  ultralytics (core_bridge), which CANNOT coexist with mediapipe in one venv — the
  quarantine forbids it. So this module imports ONLY AirLine.gestures (mediapipe is
  lazy inside MediaPipeHandSource) and never touches the CV stack.

RUN IT (in the gestures venv, from the repo root):
    set PYTHONPATH=.
    C:\\airline-gestures-venv\\Scripts\\python.exe -m AirLine.gesture_eval --reps 10

The preview window drives the test (no blocking terminal input, so the GUI never
freezes): SPACE captures one attempt, [s] skips, [q] quits. The overlay shows the
live raw classification and the spread_ratio (for tuning OPEN_PALM vs SPREAD).

Calibrate the palm/spread threshold from YOUR hand:
    ... -m AirLine.gesture_eval --calibrate
"""

from __future__ import annotations

import argparse
import time
from collections import defaultdict

from AirLine.gestures import Gesture, GestureEngine, HandClassifier

# The 5 gestures to test. "swipe" accepts either direction as correct.
TEST_PLAN = [
    ("point", "Index finger only, others curled", {Gesture.POINT}),
    ("fist", "All fingers closed into a fist", {Gesture.FIST}),
    ("open_palm", "All fingers up, held TOGETHER", {Gesture.OPEN_PALM}),
    ("spread", "All fingers up, fanned APART", {Gesture.SPREAD}),
    ("swipe", "Open hand, sweep left/right FAST across frame",
     {Gesture.SWIPE_LEFT, Gesture.SWIPE_RIGHT}),
]


def summarize(results, plan=TEST_PLAN):
    """Pure tally. results: list of (target_key, confirmed_label_str).

    Returns (rates, confusion) where rates[key] = (correct, total, pct) and
    confusion[target_key][confirmed_label] = count.
    """
    accept = {key: {g.value for g in ok} for key, _, ok in plan}
    rates = {}
    confusion = defaultdict(lambda: defaultdict(int))
    totals = defaultdict(int)
    correct = defaultdict(int)
    for target, confirmed in results:
        totals[target] += 1
        confusion[target][confirmed] += 1
        if confirmed in accept.get(target, set()):
            correct[target] += 1
    for key, _, _ in plan:
        t = totals[key]
        c = correct[key]
        rates[key] = (c, t, (100.0 * c / t) if t else 0.0)
    return rates, confusion


def _overlay(cv2, frame, clf, lm, lines, color=(0, 255, 0)):
    disp = frame.copy()
    raw = clf.classify(lm).value if lm is not None else "none"
    ratio = f"{clf.spread_ratio(lm):.2f}" if lm is not None else "-"
    y = 30
    for txt in [f"raw: {raw}   spread_ratio: {ratio}"] + lines:
        cv2.putText(disp, txt, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)
        y += 32
    return disp


def run(args):  # pragma: no cover - needs webcam + mediapipe
    import cv2
    from AirLine.gestures import MediaPipeHandSource
    source = MediaPipeHandSource()
    clf = HandClassifier(spread_threshold=args.spread_threshold)
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit(f"could not open camera {args.camera}")

    def read_lm():
        ok, frame = cap.read()
        if not ok:
            return None, None
        lm = source.landmarks(frame)
        if lm is not None and args.mirror:
            lm = [(1.0 - x, y) for (x, y) in lm]
        return frame, lm

    results, latencies = [], []
    ti, rep, mode = 0, 0, "wait"
    engine, cap_start = None, None

    print(f"\n=== gesture recognition eval ({args.reps} reps each) ===")
    print("SPACE=capture attempt, s=skip, q=quit. Watch the preview window.\n")
    while ti < len(TEST_PLAN):
        key, desc, accept = TEST_PLAN[ti]
        frame, lm = read_lm()
        if frame is None:
            continue

        if mode == "wait":
            lines = [f"{key.upper()} ({desc})", f"attempt {rep + 1}/{args.reps}  [SPACE]"]
            disp = _overlay(cv2, frame, clf, lm, lines)
        else:  # capture
            confirmed = engine.feed_landmarks(lm)
            elapsed = time.time() - cap_start
            want_swipe = key == "swipe"
            done = None
            if confirmed is not None and confirmed != Gesture.NONE:
                is_swipe = confirmed in (Gesture.SWIPE_LEFT, Gesture.SWIPE_RIGHT)
                if not (want_swipe and not is_swipe):  # for swipe target, ignore static
                    done = confirmed.value
                    latencies.append(elapsed)
            if done is None and elapsed > args.capture_seconds:
                done = "none"
            lines = [f"CAPTURING {key.upper()}...", f"{elapsed:.1f}s"]
            disp = _overlay(cv2, frame, clf, lm, lines, (0, 215, 255))
            if done is not None:
                results.append((key, done))
                print(f"  {key:10s} {rep + 1}/{args.reps} -> {done}")
                rep += 1
                mode = "wait"
                if rep >= args.reps:
                    ti, rep = ti + 1, 0

        cv2.imshow("AirLine gesture eval", disp)
        k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            break
        if mode == "wait" and k == ord(" "):
            engine = GestureEngine(confirm_frames=args.confirm_frames,
                                   swipe_dx_frac=args.swipe_dx)
            cap_start, mode = time.time(), "capture"
        elif mode == "wait" and k == ord("s"):
            results.append((key, "skipped"))
            rep += 1
            if rep >= args.reps:
                ti, rep = ti + 1, 0

    cap.release()
    cv2.destroyAllWindows()
    _report(results, latencies, args.confirm_frames)


def _report(results, latencies, confirm_frames):
    rates, confusion = summarize(results)
    print("\n===== RESULTS =====")
    for key, _, _ in TEST_PLAN:
        c, t, pct = rates[key]
        print(f"  {key:10s}: {c}/{t}  ({pct:.0f}%)")
    print("\n  OPEN_PALM vs SPREAD confusion:")
    print(f"    open_palm read as spread: {confusion['open_palm'].get('spread', 0)}"
          f"/{sum(confusion['open_palm'].values())}")
    print(f"    spread read as open_palm: {confusion['spread'].get('open_palm', 0)}"
          f"/{sum(confusion['spread'].values())}")
    if latencies:
        avg = 1000 * sum(latencies) / len(latencies)
        print(f"\n  mean held->fired latency: {avg:.0f} ms "
              f"(debounce window = {confirm_frames} frames)")
    print("\nPaste these into AirLine/notes.md (Day 5, Part A).")


def calibrate(args):  # pragma: no cover - needs webcam + mediapipe
    """Sample spread_ratio for held OPEN_PALM then SPREAD; suggest a threshold."""
    import cv2
    from AirLine.gestures import MediaPipeHandSource
    source = MediaPipeHandSource()
    clf = HandClassifier()
    cap = cv2.VideoCapture(args.camera)

    def sample(label):
        vals = []
        while True:
            ok, frame = cap.read()
            if not ok:
                continue
            lm = source.landmarks(frame)
            if lm is not None and args.mirror:
                lm = [(1.0 - x, y) for (x, y) in lm]
            r = clf.spread_ratio(lm) if lm is not None else None
            lines = [f"Hold {label}, press SPACE to sample ({len(vals)})", "q=done"]
            cv2.imshow("calibrate", _overlay(cv2, frame, clf, lm, lines))
            k = cv2.waitKey(1) & 0xFF
            if k == ord(" ") and r is not None:
                vals.append(r)
            elif k == ord("q"):
                return vals

    print("Sample OPEN_PALM (together) first, then SPREAD. SPACE to grab, q to move on.")
    palm = sample("OPEN_PALM (TOGETHER)")
    spread = sample("SPREAD (APART)")
    cap.release()
    cv2.destroyAllWindows()
    if palm and spread:
        suggested = (max(palm) + min(spread)) / 2.0
        print(f"\n  palm spread_ratio:   min {min(palm):.2f}  max {max(palm):.2f}")
        print(f"  spread spread_ratio: min {min(spread):.2f}  max {max(spread):.2f}")
        print(f"  >>> suggested spread_threshold = {suggested:.2f}")
        print(f"      (set HandClassifier(spread_threshold={suggested:.2f}) or "
              f"--spread-threshold {suggested:.2f})")
    else:
        print("not enough samples.")


def main():
    ap = argparse.ArgumentParser(description="Live webcam gesture recognition eval")
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--confirm-frames", type=int, default=6)
    ap.add_argument("--capture-seconds", type=float, default=4.0)
    ap.add_argument("--swipe-dx", type=float, default=0.14,
                    help="min normalized wrist x-travel over the window to count as a swipe")
    ap.add_argument("--spread-threshold", type=float, default=1.4)
    ap.add_argument("--mirror", action="store_true", default=True)
    ap.add_argument("--calibrate", action="store_true",
                    help="sample palm vs spread ratios and suggest a threshold")
    args = ap.parse_args()
    (calibrate if args.calibrate else run)(args)


if __name__ == "__main__":
    main()
