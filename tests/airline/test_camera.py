"""Tests for AirLine's VirtualCamera — pure motion geometry, no clip, no GPU.

Covers: stationary-stays-put, big-jump-responsiveness (bounded, no wild
overshoot), gentle-motion-lags, lost-drifts-to-wide-and-holds, always-in-bounds.
"""

from __future__ import annotations

import math

from AirLine.camera import VirtualCamera, CameraConfig, Crop
from AirLine.target import TargetState

W, H = 1280, 720


def _box(cx, cy, w=40, h=80):
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def _settle(cam, cx, cy, n=60):
    crop = None
    for _ in range(n):
        crop = cam.update(_box(cx, cy), TargetState.LOCKED, (W, H))
    return crop


def test_in_bounds_always_even_at_corners():
    cam = VirtualCamera()
    pts = [(0, 0), (W, 0), (0, H), (W, H), (W // 2, H // 2), (5, H - 5), (W - 5, 5)]
    for i in range(200):
        cx, cy = pts[i % len(pts)]
        crop = cam.update(_box(cx, cy), TargetState.LOCKED, (W, H))
        assert crop.x >= 0 and crop.y >= 0
        assert crop.x + crop.w <= W
        assert crop.y + crop.h <= H
        assert crop.w > 0 and crop.h > 0


def test_stationary_centred_target_stays_put():
    cam = VirtualCamera()
    _settle(cam, W // 2, H // 2, n=80)
    # measure residual movement once settled
    prev = cam.update(_box(W // 2, H // 2), TargetState.LOCKED, (W, H))
    moves = []
    for _ in range(20):
        c = cam.update(_box(W // 2, H // 2), TargetState.LOCKED, (W, H))
        moves.append(math.hypot(c.cx - prev.cx, c.cy - prev.cy))
        prev = c
    # essentially no jitter (residual is just int-rounding as zoom finishes easing)
    assert max(moves) < 1.5
    assert abs(prev.cx - W / 2) < 2 and abs(prev.cy - H / 2) < 2


def test_gentle_motion_lags_not_snaps():
    cam = VirtualCamera()
    _settle(cam, W // 2, H // 2, n=60)
    # nudge target a small step; camera should move LESS than the target (lag)
    tx = W // 2 + 8
    before = cam.cx
    cam.update(_box(tx, H // 2), TargetState.LOCKED, (W, H))
    cam_step = cam.cx - before
    assert 0 < cam_step < 8  # moved toward it, but did not snap onto it


def test_big_jump_is_responsive_and_bounded():
    cam = VirtualCamera()
    _settle(cam, W // 2, H // 2, n=60)
    tx = int(W * 0.66)  # sudden break right, still reachable by a zoomed crop
    last = None
    recentre_frame = None
    for f in range(40):
        c = cam.update(_box(tx, H // 2), TargetState.LOCKED, (W, H))
        # responsiveness: camera centre catches up to the subject
        if recentre_frame is None and abs(c.cx - tx) < 0.05 * W:
            recentre_frame = f
        # subject must never slide out of the crop while we catch up
        assert c.x <= tx <= c.x + c.w
        last = c
    assert recentre_frame is not None and recentre_frame <= 30  # catches up quickly
    assert last.cx <= tx + 0.05 * W  # no wild overshoot past the target


def test_lost_drifts_to_wide_then_holds():
    cfg = CameraConfig()
    cam = VirtualCamera(cfg)
    # lock tight on a corner-ish subject so the crop is far from wide
    _settle(cam, 300, 250, n=60)
    locked_h = cam.ch
    wide_h = min(H, W / cfg.aspect)
    assert locked_h < wide_h - 10  # we really were zoomed in

    # now LOST for well over the drift duration
    crop = None
    for _ in range(cfg.drift_frames + 20):
        crop = cam.update(None, TargetState.LOST, (W, H))
    # converged to wide establishing, centred
    assert abs(cam.ch - wide_h) < 2
    assert abs(crop.cx - W / 2) < 2 and abs(crop.cy - H / 2) < 2

    # holds (no hunting): further LOST frames don't move it
    held = cam.update(None, TargetState.LOST, (W, H))
    assert abs(held.cx - crop.cx) < 0.5 and abs(held.cy - crop.cy) < 0.5


def test_idle_sits_on_wide_establishing():
    cfg = CameraConfig()
    cam = VirtualCamera(cfg)
    crop = cam.update(None, TargetState.IDLE, (W, H))
    assert abs(crop.cx - W / 2) < 2 and abs(crop.cy - H / 2) < 2
    assert abs(cam.ch - min(H, W / cfg.aspect)) < 2


def test_crop_keeps_output_aspect():
    cfg = CameraConfig()
    cam = VirtualCamera(cfg)
    crop = _settle(cam, W // 2, H // 2, n=40)
    assert abs(crop.w / crop.h - cfg.aspect) < 0.02
