"""camera — AirLine's virtual cinematography camera (pure geometry/motion).

Given, per frame, the locked target's box (or None) and the TargetTracker state,
this maintains a smoothed crop rectangle that:

  1. ADAPTIVE FOLLOW (LOCKED): exponential smoothing on the crop centre whose
     factor scales with how far the target is from the current centre — heavy
     smoothing (calm) when centred, light smoothing (snappy) when the subject
     breaks fast. A small velocity lookahead anticipates motion. Crop size eases
     tighter when stable, wider when fast (gently, to avoid zoom pumping).

  2. DRIFT-TO-WIDE (LOST): on losing the target it eases from the crop-at-loss to
     a wide establishing framing over a short duration, then HOLDS the wide shot.
     It does not hunt or pan (that would imply re-ID, which is deferred).

ZERO new CV — this is motion math over the box TargetTracker already provides.
No I/O, no rendering here: update() just returns a Crop, so it is unit-testable
without any video.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from AirLine.target import TargetState


class Shot(Enum):
    """Named shot types the virtual camera can be asked to hold.

    AUTO is the default speed-adaptive follow framing (Day 3 behaviour, unchanged).
    TIGHT / WIDE are explicit framings requested via ``request_shot``. This enum is
    the extension point for future shots (push-in / orbit / dolly) — those are NOT
    implemented here and require flight-path logic in a later PRD. Do not add them
    until that exists.
    """

    AUTO = "auto"
    TIGHT = "tight"
    WIDE = "wide"
    ORBIT = "orbit"  # Day 7: engages a 3D orbit flight-path (see flightpath.py).
    # The 2D VirtualCamera treats ORBIT as a pass-through for crop framing (no view
    # synthesis exists from one fixed clip); the orbit is realized as a 3D camera
    # pose path by flightpath.OrbitPath + the sim. So ORBIT does not alter the 2D
    # zoom/follow/drift logic — tight/wide/AUTO stay provably unchanged.


@dataclass
class CameraConfig:
    # output framing
    out_w: int = 1280
    out_h: int = 720
    # --- adaptive follow smoothing ---
    alpha_min: float = 0.05      # heavy smoothing (calm) when target is centred
    alpha_max: float = 0.45      # light smoothing (snappy) when target is far
    response_radius_frac: float = 0.22  # error (frac of W) at which alpha hits max
    lookahead: float = 3.0       # frames of target-velocity lookahead
    # --- zoom / crop size easing ---
    zoom_tight_frac: float = 0.55   # crop height (frac of H) when subject is stable
    zoom_wide_follow_frac: float = 0.72  # crop height (frac of H) when subject is fast
    zoom_alpha: float = 0.08     # crop-size easing rate (slow → anti-pump)
    speed_to_widen_frac: float = 0.04   # target speed (frac of W /frame) → full widen
    # --- explicit named shots (request_shot) ---
    shot_tight_frac: float = 0.38   # crop height (frac of H) for Shot.TIGHT
    shot_wide_frac: float = 0.95    # crop height (frac of H) for Shot.WIDE
    # --- drift-to-wide on loss ---
    drift_frames: int = 30       # eased frames from crop-at-loss to wide establishing

    @property
    def aspect(self) -> float:
        return self.out_w / self.out_h


@dataclass
class Crop:
    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def _lerp(a, b, p):
    return a + (b - a) * p


def _smoothstep(p):
    p = _clamp(p, 0.0, 1.0)
    return p * p * (3.0 - 2.0 * p)


class VirtualCamera:
    def __init__(self, config: Optional[CameraConfig] = None):
        self.cfg = config or CameraConfig()
        self._init = False
        self.cx = 0.0
        self.cy = 0.0
        self.ch = 0.0  # crop height (width derived from aspect)
        self._prev_tx: Optional[float] = None
        self._prev_ty: Optional[float] = None
        self._drift_active = False
        self._drift_t = 0
        self._drift_start = (0.0, 0.0, 0.0)  # cx, cy, ch at loss
        self._shot = Shot.AUTO

    def request_shot(self, shot: Shot) -> None:
        """Ask the camera to hold a named shot (TIGHT / WIDE / AUTO).

        This is a dispatch seam only: it selects the zoom TARGET while LOCKED. The
        existing easing (``zoom_alpha``) still applies, so a shot change eases in
        rather than jumping — consistent with Day-3 smoothing. It does NOT alter
        the follow / responsiveness / drift motion logic.
        """
        self._shot = shot

    @property
    def shot(self) -> Shot:
        return self._shot

    def _zoom_target_h(self, z: float, H: int) -> float:
        """Resolve the crop-height target for the current shot. AUTO is the
        unchanged speed-adaptive Day-3 framing; TIGHT/WIDE are explicit sizes."""
        cfg = self.cfg
        if self._shot == Shot.TIGHT:
            return cfg.shot_tight_frac * H
        if self._shot == Shot.WIDE:
            return cfg.shot_wide_frac * H
        return _lerp(cfg.zoom_tight_frac, cfg.zoom_wide_follow_frac, z) * H

    # --- framing helpers ---
    def _wide_h(self, W, H) -> float:
        """Tallest crop that fits the frame at the output aspect (full establishing)."""
        return min(H, W / self.cfg.aspect)

    def _ensure_init(self, W, H):
        if not self._init:
            self.ch = self._wide_h(W, H)
            self.cx = W / 2.0
            self.cy = H / 2.0
            self._init = True

    def _resolve_crop(self, W, H) -> Crop:
        """Clamp current (cx, cy, ch) to a valid in-bounds crop at output aspect."""
        h = _clamp(self.ch, 1.0, self._wide_h(W, H))
        w = h * self.cfg.aspect
        if w > W:  # safety; shouldn't trigger given _wide_h
            w = W
            h = w / self.cfg.aspect
        cx = _clamp(self.cx, w / 2.0, W - w / 2.0)
        cy = _clamp(self.cy, h / 2.0, H - h / 2.0)
        # write clamped values back so state stays consistent frame-to-frame
        self.cx, self.cy, self.ch = cx, cy, h
        x = int(round(cx - w / 2.0))
        y = int(round(cy - h / 2.0))
        wi = int(round(w))
        hi = int(round(h))
        x = int(_clamp(x, 0, W - wi))
        y = int(_clamp(y, 0, H - hi))
        return Crop(x, y, wi, hi)

    def update(self, target_box, state: TargetState, frame_size) -> Crop:
        W, H = frame_size
        self._ensure_init(W, H)
        cfg = self.cfg

        if state == TargetState.LOCKED and target_box is not None:
            self._drift_active = False
            tx = (target_box[0] + target_box[2]) / 2.0
            ty = (target_box[1] + target_box[3]) / 2.0

            if self._prev_tx is None:
                vx = vy = 0.0
            else:
                vx = tx - self._prev_tx
                vy = ty - self._prev_ty
            self._prev_tx, self._prev_ty = tx, ty

            # velocity lookahead — anticipate, don't merely chase
            gx = tx + cfg.lookahead * vx
            gy = ty + cfg.lookahead * vy

            # error-scaled smoothing: small error → calm, large error → snappy
            err = math.hypot(gx - self.cx, gy - self.cy)
            err_norm = _clamp(err / (cfg.response_radius_frac * W), 0.0, 1.0)
            alpha = _lerp(cfg.alpha_min, cfg.alpha_max, err_norm)
            self.cx += alpha * (gx - self.cx)
            self.cy += alpha * (gy - self.cy)

            # zoom: AUTO = speed-adaptive (tight when stable, wider when fast);
            # TIGHT/WIDE = explicit named shot. Eased either way (anti-pump).
            speed = math.hypot(vx, vy) / W
            z = _clamp(speed / cfg.speed_to_widen_frac, 0.0, 1.0)
            target_h = self._zoom_target_h(z, H)
            self.ch += cfg.zoom_alpha * (target_h - self.ch)

        elif state == TargetState.LOST:
            if not self._drift_active:
                self._drift_active = True
                self._drift_t = 0
                self._drift_start = (self.cx, self.cy, self.ch)
            self._drift_t = min(cfg.drift_frames, self._drift_t + 1)
            p = _smoothstep(self._drift_t / cfg.drift_frames)
            scx, scy, sch = self._drift_start
            self.cx = _lerp(scx, W / 2.0, p)
            self.cy = _lerp(scy, H / 2.0, p)
            self.ch = _lerp(sch, self._wide_h(W, H), p)
            self._prev_tx = self._prev_ty = None

        else:  # IDLE — nothing selected yet: sit on the wide establishing shot
            self.cx, self.cy = W / 2.0, H / 2.0
            self.ch = self._wide_h(W, H)
            self._prev_tx = self._prev_ty = None
            self._drift_active = False

        return self._resolve_crop(W, H)
