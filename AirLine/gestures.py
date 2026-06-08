"""gestures — the reusable gesture ENGINE (input modality layer).

Turns hand landmarks into *confirmed* gesture labels via a debounce/confirmation
layer, so the downstream camera never spasms on MediaPipe flicker. This is the
direct analog of Day 2's sub-threshold-gap logic.

LAYERING / SEPARATION SEAM:
  - This module knows about hand poses, NOT about cinematography. It emits a
    typed ``Gesture`` label; ``intent.py`` maps that to an ``IntentCommand`` and
    applies it to the proven TargetTracker / VirtualCamera. Gestures never touch
    MediaPipe internals downstream.
  - MediaPipe is imported LAZILY, only inside ``MediaPipeHandSource``. The
    classifier + debouncer are pure geometry over 21 (x, y) landmarks and are
    fully unit-testable with synthetic data — no webcam, no mediapipe install.

The webcam/MediaPipe layer is itself a stand-in for the future wearable glove:
build it solid, don't gold-plate it — the glove later replaces this source while
reusing everything downstream.
"""

from __future__ import annotations

import math
from collections import deque
from enum import Enum
from typing import Optional, Sequence

# A landmark is an (x, y) pair. MediaPipe Hands order (subset we use):
WRIST = 0
THUMB_TIP = 4
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP = 9, 10, 12
RING_PIP, RING_TIP = 14, 16
PINKY_MCP, PINKY_PIP, PINKY_TIP = 17, 18, 20

# (tip, pip) pairs for the four non-thumb fingers
_FINGERS = [(INDEX_TIP, INDEX_PIP), (MIDDLE_TIP, MIDDLE_PIP),
            (RING_TIP, RING_PIP), (PINKY_TIP, PINKY_PIP)]


class Gesture(str, Enum):
    NONE = "none"
    POINT = "point"            # index extended, others curled  -> SELECT
    FIST = "fist"              # all fingers curled             -> SHOT_TIGHT
    OPEN_PALM = "open_palm"    # all extended, fingers together -> RELEASE
    SPREAD = "spread"          # all extended, fingers apart    -> SHOT_WIDE
    SWIPE_LEFT = "swipe_left"  # extended hand moving left      -> SWITCH_PREV
    SWIPE_RIGHT = "swipe_right"  # extended hand moving right    -> SWITCH_NEXT


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _finger_extended(lm: Sequence, tip: int, pip: int) -> bool:
    """Orientation-independent: a finger is extended if its tip is farther from
    the wrist than its PIP joint."""
    return _dist(lm[tip], lm[WRIST]) > _dist(lm[pip], lm[WRIST]) * 1.05


class HandClassifier:
    """Classifies a static hand pose into a Gesture (no motion / no swipe)."""

    def __init__(self, spread_threshold: float = 1.4):
        # spread_threshold: fingertip span / knuckle span, above which an
        # all-extended hand counts as SPREAD rather than OPEN_PALM. ~1.0 = fingers
        # together; fanned hands run higher. Tune from live spread_ratio() readings
        # (gesture_eval --calibrate) — the right value is hand-specific.
        self.spread_threshold = spread_threshold

    def spread_ratio(self, lm: Sequence) -> float:
        """Finger fan-out: index-tip..pinky-tip span divided by the knuckle span
        (index-MCP..pinky-MCP). ~1.0 when fingers are together, larger when fanned.
        Scale/rotation invariant — both spans scale with the hand."""
        knuckle = _dist(lm[INDEX_MCP], lm[PINKY_MCP]) or 1e-6
        return _dist(lm[INDEX_TIP], lm[PINKY_TIP]) / knuckle

    def classify(self, lm: Sequence) -> Gesture:
        if lm is None or len(lm) < 21:
            return Gesture.NONE
        ext = [_finger_extended(lm, t, p) for t, p in _FINGERS]
        n = sum(ext)

        if n == 0:
            return Gesture.FIST
        if n == 1 and ext[0]:  # only index
            return Gesture.POINT
        if n >= 4:
            return (Gesture.SPREAD if self.spread_ratio(lm) >= self.spread_threshold
                    else Gesture.OPEN_PALM)
        return Gesture.NONE  # ambiguous (2-3 fingers) -> no command


class GestureDebouncer:
    """Fires a gesture only after it is held for ``confirm_frames`` consecutive
    frames, and fires it ONCE per confirmed transition (not every held frame).
    """

    def __init__(self, confirm_frames: int = 6):
        if confirm_frames < 1:
            raise ValueError("confirm_frames must be >= 1")
        self.confirm_frames = confirm_frames
        self._candidate = Gesture.NONE
        self._count = 0
        self._confirmed = Gesture.NONE

    def update(self, raw: Gesture) -> Optional[Gesture]:
        """Return the gesture at the frame it becomes newly confirmed, else None."""
        if raw == self._candidate:
            self._count += 1
        else:
            self._candidate = raw
            self._count = 1
        if self._count >= self.confirm_frames and self._candidate != self._confirmed:
            self._confirmed = self._candidate
            return self._confirmed
        return None


class GestureEngine:
    """Full engine: classify -> detect swipe motion -> debounce -> confirmed Gesture.

    ``feed_label`` is the pure debounce path (used by tests and any external
    classifier). ``feed_landmarks`` adds classification + horizontal-swipe
    detection on top. Confirmed swipes fire as one-shot events with a cooldown.
    """

    def __init__(self, confirm_frames: int = 6, swipe_dx_frac: float = 0.18,
                 swipe_window: int = 5, swipe_cooldown: int = 8):
        self.debouncer = GestureDebouncer(confirm_frames)
        self.classifier = HandClassifier()
        self.swipe_dx_frac = swipe_dx_frac
        self.swipe_cooldown = swipe_cooldown
        self._wrist_x = deque(maxlen=swipe_window)
        self._cooldown = 0

    def feed_label(self, g: Gesture) -> Optional[Gesture]:
        return self.debouncer.update(g)

    def feed_landmarks(self, lm: Optional[Sequence]) -> Optional[Gesture]:
        if self._cooldown > 0:
            self._cooldown -= 1

        g = self.classifier.classify(lm)

        # Horizontal swipe detection — track the wrist whenever ANY hand is present,
        # independent of pose. A fast swipe blurs and is often misclassified as
        # `none` mid-motion; gating motion tracking on a stable static label (as
        # before) cleared the buffer every frame and swipes never fired.
        if lm is not None and len(lm) >= 21:
            self._wrist_x.append(lm[WRIST][0])
            if self._cooldown == 0 and len(self._wrist_x) == self._wrist_x.maxlen:
                dx = self._wrist_x[-1] - self._wrist_x[0]
                if abs(dx) >= self.swipe_dx_frac:
                    self._cooldown = self.swipe_cooldown
                    self._wrist_x.clear()
                    # image-x increases rightward
                    return Gesture.SWIPE_RIGHT if dx > 0 else Gesture.SWIPE_LEFT
        else:
            self._wrist_x.clear()

        return self.debouncer.update(g)


class MediaPipeHandSource:  # pragma: no cover - requires webcam + mediapipe
    """Lazy MediaPipe wrapper: BGR frame -> 21 normalized (x, y) landmarks or None.

    Imported lazily so the rest of AirLine (engine, tests, scripted demo) runs
    with ZERO mediapipe dependency. Only instantiate this in the live webcam path
    AND only after the dependency has been installed in an isolated environment
    (see AirLine/requirements-gestures.txt and notes.md — do not pollute the main
    CV venv).
    """

    def __init__(self, max_hands: int = 1, min_conf: float = 0.6):
        import mediapipe as mp  # lazy
        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False, max_num_hands=max_hands,
            min_detection_confidence=min_conf, min_tracking_confidence=min_conf)

    def landmarks(self, frame_bgr):
        import cv2
        res = self._hands.process(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        if not res.multi_hand_landmarks:
            return None
        h = res.multi_hand_landmarks[0]
        return [(p.x, p.y) for p in h.landmark]
