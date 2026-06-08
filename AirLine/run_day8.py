"""run_day8 — push-in / pull-out / dolly proof (completes the shot vocabulary).

(1) Drives the three new shots through the EXISTING intent seam.
(2) Reports each primitive's OWN invariants (push-in = changing distance; dolly =
    straight-line at held offset) — NOT orbit's constant radius.
(3) Renders rotating-3D + tri-view videos for push-in and dolly off the real paths.

    python -m AirLine.run_day8
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from AirLine.core_bridge import Detection, FrameTracks
from AirLine.target import TargetTracker
from AirLine.camera import VirtualCamera, Shot
from AirLine.intent import IntentApplier
from AirLine.intent_types import IntentCommand
from AirLine.flightpath import PushInPath, DollyPath
from AirLine.sim_orbit3d import render_3d, render_triview

OUTPUT_DIR = Path("AirLine/outputs")


def _demo_seam():
    cam, tracker = VirtualCamera(), TargetTracker()
    ap = IntentApplier(tracker, cam)
    ft = FrameTracks(index=0, detections=[
        Detection(track_id=4, cls=0, cls_name="player", box=(630, 0, 650, 40))])
    ap.apply(IntentCommand.SELECT, ft, frame_w=1280)
    for cmd, want in [(IntentCommand.SHOT_PUSH_IN, Shot.PUSH_IN),
                      (IntentCommand.SHOT_PULL_OUT, Shot.PULL_OUT),
                      (IntentCommand.SHOT_DOLLY, Shot.DOLLY)]:
        ap.apply(cmd, ft, frame_w=1280)
        print(f"[seam] {cmd.value} -> camera.shot={cam.shot.value} "
              f"({'OK' if cam.shot == want else 'FAIL'})")


def _look_err_max(path, times, centers=None):
    errs = []
    for i, t in enumerate(times):
        c = None if centers is None else centers[i]
        pose = path.pose_at(t, c)
        tgt = path.center_at(t, c)
        to_t = tgt - pose.position
        cos = np.dot(pose.forward, to_t) / np.linalg.norm(to_t)
        errs.append(np.degrees(np.arccos(np.clip(cos, -1, 1))))
    return max(errs)


def _report_pushin(p, times):
    d = [np.linalg.norm(p.position_at(t) - p.target0) for t in times]
    lateral = max(np.linalg.norm(np.cross(p.position_at(t) - p.target0, p.direction))
                  for t in times)
    print(f"\n[push-in]  ({'push-in' if p.is_push_in else 'pull-out'})")
    print(f"  distance start->end : {d[0]:.3f} -> {d[-1]:.3f}  (configured {p.d_start}->{p.d_end})")
    print(f"  monotonic decreasing: {all(d[i+1] <= d[i] + 1e-9 for i in range(len(d)-1))}")
    print(f"  lateral drift (max) : {lateral:.2e}  (0 => straight at target)")
    print(f"  look-at err (max)   : {_look_err_max(p, times):.2e} deg")


def _report_dolly(p, times):
    base = p.position_at(0.0)
    collinear = max(np.linalg.norm(np.cross(p.position_at(t) - base, p.dir)) for t in times)
    track_d = [np.linalg.norm(p.position_at(t) - p.center_at(t)) for t in times]  # tracking
    fixed = [4.0, 0.0, 1.0]
    static_d = [np.linalg.norm(p.position_at(t) - np.asarray(fixed)) for t in times]
    print(f"\n[dolly]")
    print(f"  camera path collinear: {collinear:.2e}  (0 => straight line)")
    print(f"  tracking distance dev: {max(track_d)-min(track_d):.2e}  (~0 => held offset)")
    print(f"  static-target dist    : varies {min(static_d):.3f}..{max(static_d):.3f} "
          f"(NOT constant — honest); perp standoff {p.perp_standoff(fixed):.3f}")
    print(f"  look-at err (max)    : {_look_err_max(p, times):.2e} deg")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=== AirLine Day 8 — push-in / pull-out / dolly ===")
    _demo_seam()

    times = list(np.linspace(0.0, 1.0, 80))
    pushin = PushInPath(target=[0, 0, 1.0], direction=[0, -1, 0.35],
                        start_distance=12.0, end_distance=3.0, duration=1.0)
    pullout = PushInPath(target=[0, 0, 1.0], direction=[0, -1, 0.35],
                         start_distance=3.0, end_distance=12.0, duration=1.0)
    dolly = DollyPath(start=[-10, -7, 2.5], dolly_dir=[1, 0, 0],
                      offset=[0, 7, -1.5], speed=20.0)

    _report_pushin(pushin, times)
    _report_pushin(pullout, times)
    _report_dolly(dolly, list(np.linspace(0.0, 1.0, 80)))

    print("\n[render] writing schematic videos...")
    # push-in toward a slightly moving target
    pc = lambda t: [0.4 * t, 0.0, 1.0]
    print("  push-in 3D     :", render_3d(pushin, str(OUTPUT_DIR / "day8_pushin"),
          centers_fn=pc, t_max=1.0, title="push-in (toward target)"))
    print("  push-in triview:", render_triview(pushin, str(OUTPUT_DIR / "day8_pushin_triview"),
          centers_fn=pc, t_max=1.0, title="push-in (toward target)"))
    # dolly tracking a moving subject (the canonical tracking shot)
    print("  dolly 3D       :", render_3d(dolly, str(OUTPUT_DIR / "day8_dolly"),
          t_max=1.0, title="dolly (tracking)"))
    print("  dolly triview  :", render_triview(dolly, str(OUTPUT_DIR / "day8_dolly_triview"),
          t_max=1.0, title="dolly (tracking)"))

    print("\nShot vocabulary COMPLETE: tight / wide / orbit / push-in / pull-out / dolly")


if __name__ == "__main__":
    main()
