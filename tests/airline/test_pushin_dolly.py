"""Day-8 invariants for push-in/pull-out and dolly. CRITICAL DISCIPLINE (Day-7
lesson): each primitive asserts its OWN correct invariants — push-in's signature is
CHANGING distance (never orbit's constant radius); dolly's is straight-line
translation at a held offset (never push-in's decreasing distance).
"""

from __future__ import annotations

import math

import numpy as np

from AirLine.flightpath import PushInPath, DollyPath

TOL = 1e-9
TIMES = [i / 49.0 for i in range(50)]  # 0..1


# ============================ PUSH-IN / PULL-OUT ============================
def _pushin():
    return PushInPath(target=[1.0, 2.0, 0.5], direction=[0.0, -1.0, 0.4],
                      start_distance=10.0, end_distance=3.0, duration=1.0)


def test_pushin_distance_monotonic_decreasing():
    p = _pushin()
    d = [np.linalg.norm(p.position_at(t) - p.target0) for t in TIMES]
    assert all(d[i + 1] < d[i] + TOL for i in range(len(d) - 1))  # non-increasing
    assert d[0] > d[-1]                                            # net decrease
    assert p.is_push_in


def test_pushin_endpoints_match_configured_distances():
    p = _pushin()
    assert abs(np.linalg.norm(p.position_at(0.0) - p.target0) - 10.0) < TOL
    assert abs(np.linalg.norm(p.position_at(1.0) - p.target0) - 3.0) < TOL


def test_pushin_no_overshoot_below_end_standoff():
    p = _pushin()
    d = [np.linalg.norm(p.position_at(t) - p.target0) for t in TIMES]
    assert min(d) >= p.d_end - TOL          # never passes the end standoff
    assert max(d) <= p.d_start + TOL


def test_pushin_look_at_locked():
    p = _pushin()
    for t in TIMES:
        pose = p.pose_at(t)
        to_t = p.target0 - pose.position
        assert abs(np.dot(pose.forward, to_t) / np.linalg.norm(to_t) - 1.0) < TOL


def test_pushin_no_lateral_drift_collinear_with_axis():
    p = _pushin()
    for t in TIMES:
        offset = p.position_at(t) - p.target0
        # position lies on the ray target + direction*d  =>  parallel to direction
        cross = np.cross(offset, p.direction)
        assert np.linalg.norm(cross) < TOL


def test_pullout_is_increasing_distance_sign_flip():
    p = PushInPath(target=[0, 0, 0], direction=[1, 0, 0],
                   start_distance=2.0, end_distance=8.0, duration=1.0)
    d = [np.linalg.norm(p.position_at(t) - p.target0) for t in TIMES]
    assert all(d[i + 1] > d[i] - TOL for i in range(len(d) - 1))  # increasing
    assert not p.is_push_in


def test_pushin_moving_target_reduces_distance_and_tracks():
    p = _pushin()
    centers = [[0.4 * t, 2.0, 0.5] for t in TIMES]  # target drifts in +X
    d = [np.linalg.norm(p.position_at(t, centers[i]) - np.asarray(centers[i]))
         for i, t in enumerate(TIMES)]
    assert d[0] > d[-1]                                  # still pushing in
    for i, t in enumerate(TIMES):                        # still framed
        pose = p.pose_at(t, centers[i])
        to_t = np.asarray(centers[i]) - pose.position
        assert abs(np.dot(pose.forward, to_t) / np.linalg.norm(to_t) - 1.0) < TOL


# ================================== DOLLY ==================================
def _dolly():
    return DollyPath(start=[0.0, -8.0, 2.0], dolly_dir=[1.0, 0.0, 0.0],
                     offset=[0.0, 8.0, -1.0], speed=2.0)


def test_dolly_camera_path_is_straight_line():
    p = _dolly()
    base = p.position_at(0.0)
    for t in TIMES:
        offset = p.position_at(t) - base
        assert np.linalg.norm(np.cross(offset, p.dir)) < TOL  # collinear with axis


def test_dolly_constant_speed():
    p = _dolly()
    dt = 0.1
    steps = [np.linalg.norm(p.position_at((k + 1) * dt) - p.position_at(k * dt))
             for k in range(10)]
    assert max(steps) - min(steps) < TOL
    assert abs(steps[0] - p.speed * dt) < TOL


def test_dolly_tracking_holds_constant_distance_and_frame():
    """TRACKING case (target co-moves): full 3D distance == |offset|, constant."""
    p = _dolly()
    off_norm = float(np.linalg.norm(p.offset))
    for t in TIMES:
        pose = p.pose_at(t)                       # center=None -> tracking
        d = np.linalg.norm(pose.position - p.center_at(t))
        assert abs(d - off_norm) < TOL            # constant distance (NOT push-in's!)
        to_t = p.center_at(t) - pose.position
        assert abs(np.dot(pose.forward, to_t) / np.linalg.norm(to_t) - 1.0) < TOL


def test_dolly_static_target_distance_varies_perp_standoff_constant():
    """Honest invariant: past a STATIONARY target, full distance is NOT constant
    (min at the perpendicular foot); the perpendicular standoff IS constant."""
    p = _dolly()
    fixed = [5.0, 0.0, 1.0]
    dists = [np.linalg.norm(p.position_at(t) - np.asarray(fixed))
             for t in [0.0, 0.5, 1.0, 2.0, 3.0]]
    assert max(dists) - min(dists) > 0.5          # genuinely varies (no false invariant)
    standoff = p.perp_standoff(fixed)
    assert min(dists) >= standoff - 1e-6          # closest approach == perp standoff
    assert abs(min(dists) - standoff) < 0.5       # min near the foot


def test_dolly_tracking_moving_target_along_axis_stays_framed():
    p = _dolly()
    # subject moves along the dolly axis; camera maintains offset, keeps it framed
    centers = [list(p.start + p.offset + p.dir * (p.speed * t)) for t in TIMES]
    for i, t in enumerate(TIMES):
        pose = p.pose_at(t, centers[i])
        to_t = np.asarray(centers[i]) - pose.position
        assert abs(np.dot(pose.forward, to_t) / np.linalg.norm(to_t) - 1.0) < TOL
