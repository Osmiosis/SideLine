"""Tests for the gesture engine — debounce, flicker-rejection, fire-once,
classification, and mapping. Synthetic landmarks/labels; no webcam, no mediapipe.
"""

from __future__ import annotations

from AirLine.gestures import (
    Gesture, GestureDebouncer, GestureEngine, HandClassifier,
)
from AirLine.intent import gesture_to_intent, IntentCommand


# --- synthetic 21-landmark hands -------------------------------------------
def _hand(extended):
    """Build 21 (x,y) landmarks. `extended` = set of finger names extended.

    Layout: wrist at (0.5, 1.0); fingers point UP (smaller y). A finger's TIP is
    placed far from the wrist when extended, near the PIP when curled.
    """
    lm = [(0.5, 1.0)] * 21
    lm[9] = (0.5, 0.6)    # middle MCP (hand-size reference)
    lm[5] = (0.42, 0.65)  # index MCP (knuckle) — for spread_ratio
    lm[17] = (0.66, 0.65)  # pinky MCP (knuckle) — for spread_ratio
    # base x positions for each finger
    bx = {"index": 0.42, "middle": 0.50, "ring": 0.58, "pinky": 0.66}
    # (tip_idx, pip_idx)
    fmap = {"index": (8, 6), "middle": (12, 10), "ring": (16, 14), "pinky": (20, 18)}
    for name, (tip, pip) in fmap.items():
        x = bx[name]
        lm[pip] = (x, 0.7)
        lm[tip] = (x, 0.30) if name in extended else (x, 0.74)  # extended=far, curled=near
    # thumb (unused by classifier counts)
    lm[4] = (0.30, 0.7)
    return lm


def _spread_hand():
    """All extended AND fanned out (index far-left, pinky far-right)."""
    lm = _hand({"index", "middle", "ring", "pinky"})
    lm[8] = (0.05, 0.30)   # index tip far left
    lm[20] = (0.95, 0.30)  # pinky tip far right
    return lm


def test_classifier_fist():
    assert HandClassifier().classify(_hand(set())) == Gesture.FIST


def test_classifier_point():
    assert HandClassifier().classify(_hand({"index"})) == Gesture.POINT


def test_classifier_open_palm_vs_spread():
    c = HandClassifier()
    assert c.classify(_hand({"index", "middle", "ring", "pinky"})) == Gesture.OPEN_PALM
    assert c.classify(_spread_hand()) == Gesture.SPREAD


def test_classifier_none_on_garbage():
    assert HandClassifier().classify(None) == Gesture.NONE
    assert HandClassifier().classify([(0, 0)] * 5) == Gesture.NONE


# --- debounce ---------------------------------------------------------------
def test_debounce_fires_after_n_held_frames():
    d = GestureDebouncer(confirm_frames=6)
    out = [d.update(Gesture.FIST) for _ in range(6)]
    assert out[:5] == [None] * 5
    assert out[5] == Gesture.FIST  # fires exactly on the 6th held frame


def test_debounce_rejects_subthreshold_flicker():
    d = GestureDebouncer(confirm_frames=6)
    fired = [d.update(Gesture.FIST) for _ in range(3)]  # only 3 frames
    fired += [d.update(Gesture.NONE) for _ in range(6)]
    assert all(f is None for f in fired[:3])            # never confirmed
    # NONE confirms (so a later real gesture can fire) but maps to no command
    assert gesture_to_intent(Gesture.NONE) is None


def test_debounce_fires_once_not_every_held_frame():
    d = GestureDebouncer(confirm_frames=3)
    out = [d.update(Gesture.FIST) for _ in range(10)]
    assert out.count(Gesture.FIST) == 1  # single fire across a long hold


def test_debounce_new_gesture_after_transition_fires():
    d = GestureDebouncer(confirm_frames=3)
    [d.update(Gesture.FIST) for _ in range(3)]
    [d.update(Gesture.NONE) for _ in range(3)]
    out = [d.update(Gesture.SPREAD) for _ in range(3)]
    assert out[-1] == Gesture.SPREAD


def test_invalid_confirm_frames_rejected():
    import pytest
    with pytest.raises(ValueError):
        GestureDebouncer(confirm_frames=0)


# --- mapping ----------------------------------------------------------------
def test_gesture_to_intent_mapping():
    assert gesture_to_intent(Gesture.POINT) == IntentCommand.SELECT
    assert gesture_to_intent(Gesture.FIST) == IntentCommand.SHOT_TIGHT
    assert gesture_to_intent(Gesture.SPREAD) == IntentCommand.SHOT_WIDE
    assert gesture_to_intent(Gesture.OPEN_PALM) == IntentCommand.RELEASE
    assert gesture_to_intent(Gesture.SWIPE_RIGHT) == IntentCommand.SWITCH_NEXT
    assert gesture_to_intent(Gesture.SWIPE_LEFT) == IntentCommand.SWITCH_PREV
    assert gesture_to_intent(Gesture.NONE) is None
    assert gesture_to_intent(None) is None


# --- engine: classification + debounce together -----------------------------
def test_engine_feed_landmarks_confirms_fist():
    eng = GestureEngine(confirm_frames=5)
    fist = _hand(set())
    out = [eng.feed_landmarks(fist) for _ in range(5)]
    assert out[-1] == Gesture.FIST and out[:-1] == [None] * 4


def test_gesture_eval_summarize_rates_and_confusion():
    from AirLine.gesture_eval import summarize
    results = [
        ("point", "point"), ("point", "point"), ("point", "none"),     # 2/3
        ("open_palm", "open_palm"), ("open_palm", "spread"),            # 1/2, 1 confused
        ("spread", "spread"), ("spread", "spread"),                     # 2/2
        ("swipe", "swipe_right"), ("swipe", "swipe_left"),              # 2/2 (either dir)
    ]
    rates, confusion = summarize(results)
    assert rates["point"] == (2, 3, pytest_approx(2 / 3 * 100))
    assert rates["spread"] == (2, 2, 100.0)
    assert rates["swipe"][0] == 2  # both directions count as correct
    assert confusion["open_palm"]["spread"] == 1  # the flagged confusion shows up


def pytest_approx(v):
    import pytest
    return pytest.approx(v)


def test_engine_detects_horizontal_swipe():
    eng = GestureEngine(confirm_frames=6, swipe_dx_frac=0.18, swipe_window=5)
    # an open palm gliding rightward across frames
    result = None
    for i in range(5):
        h = _hand({"index", "middle", "ring", "pinky"})
        shift = 0.10 * i  # wrist drifts right
        h = [(x + shift, y) for (x, y) in h]
        result = eng.feed_landmarks(h)
    assert result == Gesture.SWIPE_RIGHT
