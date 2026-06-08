"""flightpath — 3D camera flight-path primitives. Day 7: ORBIT.

The first time AirLine computes a camera POSE IN 3D SPACE over time (not a 2D crop).
Pure deterministic kinematics — no rendering, no I/O — so it is fully unit-testable
by geometric invariants.

COORDINATE CONVENTION (documented, fixed):
  Right-handed world. X = right, Y = forward/depth, Z = UP (altitude).
  A target/subject sits at a 3D position; the camera orbits it.

ORBIT = a circle of fixed radius in a plane defined by (center, radius, plane_normal),
traced at constant angular speed, camera always looking at the center. The plane may
be TILTED (plane_normal need not be +Z); a level orbit is the special case
plane_normal = +Z. This is NOT a spiral, radius-ramp, or freeform path (scope guard).

Plane parameterization: given unit normal n, we build an orthonormal in-plane basis
(u, v) deterministically by Gram-Schmidt against a reference axis, so
    camera_pos(theta) = center + radius * (cos(theta) * u + sin(theta) * v)
lies in the plane through `center` with normal n, for all theta.

LOCALIZATION CAVEAT (see notes.md): the path is rigorous 3D, but a real subject's 3D
position (depth) is approximated elsewhere via a 2D->ground-plane assumption — that
approximation is NOT in this file. Here the world is defined exactly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

WORLD_UP = np.array([0.0, 0.0, 1.0])


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise ValueError("cannot normalize a zero-length vector")
    return v / n


@dataclass
class CameraPose:
    """A camera pose in 3D: position + orthonormal orientation (look-at the target)."""
    position: np.ndarray  # (3,)
    forward: np.ndarray   # unit, points from camera toward the target
    up: np.ndarray        # unit
    right: np.ndarray     # unit


def look_at(position: np.ndarray, target: np.ndarray,
            world_up: np.ndarray = WORLD_UP) -> CameraPose:
    """Build a camera pose at `position` looking at `target`."""
    forward = _unit(target - position)
    # Guard the degenerate case where forward is (anti)parallel to world_up.
    ref_up = world_up
    if abs(float(np.dot(forward, _unit(world_up)))) > 0.999:
        ref_up = np.array([1.0, 0.0, 0.0])
    right = _unit(np.cross(forward, ref_up))
    up = _unit(np.cross(right, forward))
    return CameraPose(position=position, forward=forward, up=up, right=right)


class OrbitPath:
    """Constant-radius circular orbit in a (possibly tilted) plane around a center.

    The camera looks at the center at all times. The center may be supplied
    per-step (a MOVING target) — the whole circle translates with it, so the
    subject stays centred.
    """

    def __init__(self, center: Sequence[float], radius: float,
                 plane_normal: Sequence[float] = (0.0, 0.0, 1.0),
                 angular_speed: float = 1.0, phase0: float = 0.0):
        if radius <= 0:
            raise ValueError("radius must be > 0")
        self.center0 = np.asarray(center, dtype=float)
        self.radius = float(radius)
        self.normal = _unit(np.asarray(plane_normal, dtype=float))
        self.angular_speed = float(angular_speed)
        self.phase0 = float(phase0)
        self.u, self.v = self._plane_basis(self.normal)

    @staticmethod
    def _plane_basis(n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Deterministic orthonormal (u, v) spanning the plane with normal n."""
        # Pick a reference axis not parallel to n, then Gram-Schmidt.
        ref = np.array([1.0, 0.0, 0.0]) if abs(n[2]) > 0.9 else WORLD_UP
        u = _unit(ref - np.dot(ref, n) * n)
        v = np.cross(n, u)  # already unit (n,u orthonormal) and in-plane
        return u, v

    def theta_at(self, t: float) -> float:
        return self.phase0 + self.angular_speed * t

    @property
    def period(self) -> float:
        return 2.0 * math.pi / abs(self.angular_speed)

    def center_at(self, t: float, center: Optional[Sequence[float]] = None) -> np.ndarray:
        return self.center0 if center is None else np.asarray(center, dtype=float)

    def position_at(self, t: float, center: Optional[Sequence[float]] = None) -> np.ndarray:
        c = self.center_at(t, center)
        th = self.theta_at(t)
        return c + self.radius * (math.cos(th) * self.u + math.sin(th) * self.v)

    def pose_at(self, t: float, center: Optional[Sequence[float]] = None) -> CameraPose:
        c = self.center_at(t, center)
        return look_at(self.position_at(t, c), c)

    def trajectory(self, times: Sequence[float],
                   centers: Optional[Sequence[Sequence[float]]] = None) -> list[CameraPose]:
        """Poses over `times`. `centers` (optional, same length) = a moving target."""
        out = []
        for i, t in enumerate(times):
            c = None if centers is None else centers[i]
            out.append(self.pose_at(t, c))
        return out


class PushInPath:
    """Camera moves along the camera↔target axis, distance shrinking (push-in) or
    growing (pull-out — the same primitive with end>start). Look-at stays on target.

    CONVENTION: `direction` is the unit vector FROM the target TO the camera (the
    standoff direction). The camera sits at `target + direction * distance(t)`, so
    its path is collinear with that fixed ray and it always looks back at the
    target. Distance schedules linearly from `start_distance` to `end_distance`
    over `duration` (constant speed), clamped — never overshoots the target or the
    end standoff. Pull-out is just `end_distance > start_distance`.

    Push-in's signature invariant is CHANGING distance — NOT orbit's constant radius.
    """

    def __init__(self, target: Sequence[float], direction: Sequence[float],
                 start_distance: float, end_distance: float, duration: float = 1.0):
        if start_distance <= 0 or end_distance <= 0:
            raise ValueError("distances must be > 0 (camera must not reach the target)")
        if duration <= 0:
            raise ValueError("duration must be > 0")
        self.target0 = np.asarray(target, dtype=float)
        self.direction = _unit(np.asarray(direction, dtype=float))
        self.d_start = float(start_distance)
        self.d_end = float(end_distance)
        self.duration = float(duration)

    @property
    def is_push_in(self) -> bool:
        return self.d_end < self.d_start

    def distance_at(self, t: float) -> float:
        s = min(1.0, max(0.0, t / self.duration))
        return self.d_start + (self.d_end - self.d_start) * s

    def center_at(self, t: float, center: Optional[Sequence[float]] = None) -> np.ndarray:
        return self.target0 if center is None else np.asarray(center, dtype=float)

    def position_at(self, t: float, center: Optional[Sequence[float]] = None) -> np.ndarray:
        return self.center_at(t, center) + self.direction * self.distance_at(t)

    def pose_at(self, t: float, center: Optional[Sequence[float]] = None) -> CameraPose:
        c = self.center_at(t, center)
        return look_at(self.position_at(t, c), c)


class DollyPath:
    """Camera translates along a straight axis at a held offset to the subject — the
    canonical tracking shot. Distinct from push-in (toward) and orbit (around).

    CONVENTION: the camera path is the straight line `start + dolly_dir * speed * t`.
    `offset` is the constant camera→target vector. In the TRACKING case (default,
    `center=None`) the target co-translates with the camera, so the full 3D distance
    to the target is constant ( = |offset| ) — that is dolly's correct invariant.

    For a STATIONARY target (explicit `center`), the full 3D distance does NOT stay
    constant (a straight line past a fixed point has a minimum at the perpendicular
    foot) — asserting constant distance there would be a FALSE invariant (the Day-7
    trap). What IS constant for a static target is its PERPENDICULAR standoff to the
    dolly line — use `perp_standoff()`.
    """

    def __init__(self, start: Sequence[float], dolly_dir: Sequence[float],
                 offset: Sequence[float], speed: float = 1.0):
        self.start = np.asarray(start, dtype=float)
        self.dir = _unit(np.asarray(dolly_dir, dtype=float))
        self.offset = np.asarray(offset, dtype=float)  # camera -> target
        self.speed = float(speed)

    def position_at(self, t: float, center: Optional[Sequence[float]] = None) -> np.ndarray:
        return self.start + self.dir * (self.speed * t)

    def center_at(self, t: float, center: Optional[Sequence[float]] = None) -> np.ndarray:
        # Tracking case: target co-moves with the camera at the held offset.
        if center is not None:
            return np.asarray(center, dtype=float)
        return self.position_at(t) + self.offset

    def pose_at(self, t: float, center: Optional[Sequence[float]] = None) -> CameraPose:
        return look_at(self.position_at(t, center), self.center_at(t, center))

    def perp_standoff(self, point: Sequence[float]) -> float:
        """Perpendicular distance from a fixed point to the (infinite) dolly line."""
        p = np.asarray(point, dtype=float) - self.start
        along = np.dot(p, self.dir) * self.dir
        return float(np.linalg.norm(p - along))
