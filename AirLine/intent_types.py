"""intent_types — the stdlib-safe half of the intent layer.

`IntentCommand` and the gesture→intent mapping live here so they can be imported
WITHOUT pulling the CV stack. `intent.py` re-exports them (so existing imports keep
working) and adds `IntentApplier`, which needs the camera/target and therefore the
heavy stack.

Why split: the Day-6 capture process runs in `.venv-gestures` (mediapipe, no
ultralytics). It must emit `IntentCommand`s but cannot import `intent.py`, which
reaches `core_bridge → ultralytics`. This module depends only on `AirLine.gestures`
(stdlib; mediapipe is lazy) so it imports cleanly in BOTH venvs.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from AirLine.gestures import Gesture


class IntentCommand(str, Enum):
    SELECT = "select"
    SWITCH_NEXT = "switch_next"
    SWITCH_PREV = "switch_prev"
    RELEASE = "release"
    SHOT_TIGHT = "shot_tight"
    SHOT_WIDE = "shot_wide"
    SHOT_ORBIT = "shot_orbit"  # Day 7: engage the 3D orbit path (no gesture maps to it)


_GESTURE_TO_INTENT = {
    Gesture.POINT: IntentCommand.SELECT,
    Gesture.SWIPE_RIGHT: IntentCommand.SWITCH_NEXT,
    Gesture.SWIPE_LEFT: IntentCommand.SWITCH_PREV,
    Gesture.OPEN_PALM: IntentCommand.RELEASE,
    Gesture.FIST: IntentCommand.SHOT_TIGHT,
    Gesture.SPREAD: IntentCommand.SHOT_WIDE,
}


def gesture_to_intent(g: Optional[Gesture]) -> Optional[IntentCommand]:
    """Map a confirmed gesture to an intent command (None for NONE/unknown)."""
    if g is None:
        return None
    return _GESTURE_TO_INTENT.get(g)
