"""3D orbit invariants (Day 7). These prove the path math — the videos are secondary.

The orbit can be TILTED, so altitude is NOT constant in general and must NOT be
asserted (false invariant). The fundamental invariants tested here: constant 3D
radius, look-at correctness, in-plane, period closure, constant angular speed,
moving-target tracking, and altitude-constant ONLY for the level special case.
"""

from __future__ import annotations

import math

import numpy as np

from AirLine.flightpath import OrbitPath, look_at, WORLD_UP

TOL = 1e-9
TIMES = [i * 0.13 for i in range(60)]  # arbitrary sampling


def _tilted():
    # plane normal tilted ~30deg from vertical (about the X axis)
    a = math.radians(30)
    return OrbitPath(center=[2.0, -1.0, 3.0], radius=5.0,
                     plane_normal=[0.0, math.sin(a), math.cos(a)],
                     angular_speed=0.7, phase0=0.3)


def _level():
    return OrbitPath(center=[0.0, 0.0, 2.0], radius=4.0,
                     plane_normal=[0.0, 0.0, 1.0], angular_speed=1.1)


def test_constant_3d_radius_even_when_tilted():
    p = _tilted()
    radii = [np.linalg.norm(p.position_at(t) - p.center0) for t in TIMES]
    assert max(radii) - min(radii) < TOL
    assert abs(np.mean(radii) - p.radius) < TOL


def test_look_at_points_at_target():
    p = _tilted()
    for t in TIMES:
        pose = p.pose_at(t)
        to_target = p.center0 - pose.position
        cos = np.dot(pose.forward, to_target) / np.linalg.norm(to_target)
        assert abs(cos - 1.0) < TOL  # forward aligned with camera->target


def test_camera_stays_in_orbital_plane():
    p = _tilted()
    for t in TIMES:
        offset = p.position_at(t) - p.center0
        assert abs(np.dot(offset, p.normal)) < TOL  # zero out-of-plane component


def test_period_closure():
    p = _tilted()
    start = p.position_at(0.0)
    after = p.position_at(p.period)
    assert np.linalg.norm(after - start) < 1e-7


def test_constant_angular_speed():
    p = _tilted()
    dt = 0.2
    angles = []
    for k in range(20):
        a = p.position_at(k * dt) - p.center0
        b = p.position_at((k + 1) * dt) - p.center0
        cos = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
        angles.append(math.acos(max(-1.0, min(1.0, cos))))
    assert max(angles) - min(angles) < 1e-9  # equal angle per equal dt


def test_orthonormal_pose_basis():
    p = _tilted()
    pose = p.pose_at(1.234)
    for a in (pose.forward, pose.up, pose.right):
        assert abs(np.linalg.norm(a) - 1.0) < TOL
    assert abs(np.dot(pose.forward, pose.up)) < TOL
    assert abs(np.dot(pose.forward, pose.right)) < TOL
    assert abs(np.dot(pose.up, pose.right)) < TOL


def test_moving_target_stays_centred():
    p = _tilted()
    # target drifts in +X over time
    centers = [[0.5 * t, 0.0, 1.0] for t in TIMES]
    for i, t in enumerate(TIMES):
        pose = p.pose_at(t, center=centers[i])
        c = np.asarray(centers[i])
        # radius still measured against the moving center
        assert abs(np.linalg.norm(pose.position - c) - p.radius) < TOL
        # still looking at the (moved) target
        to_t = c - pose.position
        assert abs(np.dot(pose.forward, to_t) / np.linalg.norm(to_t) - 1.0) < TOL


def test_level_orbit_has_constant_altitude_special_case():
    p = _level()
    zs = [p.position_at(t)[2] for t in TIMES]
    assert max(zs) - min(zs) < TOL          # level => constant altitude
    assert abs(zs[0] - p.center0[2]) < TOL  # at the center's height


def test_tilted_orbit_altitude_varies_proving_generalization():
    p = _tilted()
    zs = [p.position_at(t)[2] for t in TIMES]
    assert max(zs) - min(zs) > 1.0  # tilted => altitude genuinely changes


def test_invalid_inputs_rejected():
    import pytest
    with pytest.raises(ValueError):
        OrbitPath(center=[0, 0, 0], radius=0.0)
    with pytest.raises(ValueError):
        OrbitPath(center=[0, 0, 0], radius=1.0, plane_normal=[0, 0, 0])
