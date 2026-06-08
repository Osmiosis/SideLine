"""run_day7 — orbit primitive proof.

(1) Drives ORBIT through the EXISTING intent seam (mock/scripted IntentCommand →
    IntentApplier → camera.request_shot(ORBIT)) — no new gesture.
(2) Reports the 3D orbit invariants (the real proof) for a level, a tilted, and a
    tilted + moving-target orbit.
(3) Renders BOTH schematic videos (rotating 3D + tri-view orthographic) for the
    headline tilted + moving orbit.

    python -m AirLine.run_day7
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from AirLine.core_bridge import Detection, FrameTracks
from AirLine.target import TargetTracker
from AirLine.camera import VirtualCamera, Shot
from AirLine.intent import IntentApplier
from AirLine.intent_types import IntentCommand
from AirLine.flightpath import OrbitPath

OUTPUT_DIR = Path("AirLine/outputs")


def _demo_seam() -> bool:
    """Prove SHOT_ORBIT routes through the existing seam to camera.request_shot(ORBIT)."""
    cam = VirtualCamera()
    tracker = TargetTracker()
    applier = IntentApplier(tracker, cam)
    ft = FrameTracks(index=0, detections=[
        Detection(track_id=9, cls=0, cls_name="player", box=(630, 0, 650, 40)),
    ])
    applier.apply(IntentCommand.SELECT, ft, frame_w=1280)
    applier.apply(IntentCommand.SHOT_ORBIT, ft, frame_w=1280)
    ok = (tracker.target_id == 9 and cam.shot == Shot.ORBIT)
    print(f"[seam] SELECT->lock id {tracker.target_id}, SHOT_ORBIT->camera.shot={cam.shot.value}"
          f"  ({'OK' if ok else 'FAIL'})")
    return ok


def _invariants(path: OrbitPath, n=400, centers_fn=None):
    ts = np.linspace(0.0, path.period, n)
    radii, look_err, out_plane = [], [], []
    for t in ts:
        c = None if centers_fn is None else centers_fn(t)
        center = path.center_at(t, c)
        pos = path.position_at(t, c)
        radii.append(float(np.linalg.norm(pos - center)))
        pose = path.pose_at(t, c)
        to_t = center - pos
        cosang = np.dot(pose.forward, to_t) / np.linalg.norm(to_t)
        look_err.append(math.degrees(math.acos(max(-1.0, min(1.0, cosang)))))
        out_plane.append(abs(float(np.dot(pos - center, path.normal))))
    radii = np.array(radii)
    res = {
        "radius_mean": radii.mean(),
        "radius_dev": radii.max() - radii.min(),
        "lookat_err_max_deg": max(look_err),
        "out_of_plane_max": max(out_plane),
        "altitude_dev": float(np.ptp([path.position_at(t, None if centers_fn is None
                                      else centers_fn(t))[2] for t in ts])),
    }
    if centers_fn is None:  # period closure only meaningful for a static center
        res["closure_err"] = float(np.linalg.norm(
            path.position_at(path.period) - path.position_at(0.0)))
    return res


def _report(name, inv):
    print(f"\n[{name}]")
    print(f"  3D radius        : mean {inv['radius_mean']:.4f}  dev {inv['radius_dev']:.2e}")
    print(f"  look-at err (max): {inv['lookat_err_max_deg']:.2e} deg")
    print(f"  out-of-plane max : {inv['out_of_plane_max']:.2e}")
    print(f"  altitude dev     : {inv['altitude_dev']:.4f}  "
          f"({'~0 => level' if inv['altitude_dev'] < 1e-9 else 'varies => tilted'})")
    if "closure_err" in inv:
        print(f"  period closure   : {inv['closure_err']:.2e}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=== AirLine Day 7 — 3D orbit primitive ===")
    _demo_seam()

    level = OrbitPath(center=[0, 0, 2.0], radius=4.0,
                      plane_normal=[0, 0, 1], angular_speed=1.0)
    tilt = math.radians(35)
    tilted = OrbitPath(center=[0, 0, 3.0], radius=5.0,
                       plane_normal=[0, math.sin(tilt), math.cos(tilt)],
                       angular_speed=0.9)
    moving_center = lambda t: [0.6 * t, 0.0, 1.5]  # target walks +X

    _report("level (normal=+Z)", _invariants(level))
    _report("tilted 35deg (static)", _invariants(tilted))
    _report("tilted 35deg + moving target", _invariants(tilted, centers_fn=moving_center))

    # Render BOTH videos for the headline tilted + moving orbit.
    print("\n[render] writing schematic videos (matplotlib)...")
    from AirLine.sim_orbit3d import render_3d, render_triview
    p3d = render_3d(tilted, str(OUTPUT_DIR / "day7_orbit_3d"),
                    centers_fn=moving_center, title="orbit: tilted 35deg, moving target")
    ptri = render_triview(tilted, str(OUTPUT_DIR / "day7_orbit_triview"),
                          centers_fn=moving_center, title="orbit: tilted 35deg, moving target")
    print(f"[render] 3D     : {p3d}")
    print(f"[render] triview: {ptri}")


if __name__ == "__main__":
    main()
