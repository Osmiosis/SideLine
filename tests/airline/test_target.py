"""Tests for AirLine's TargetTracker — locked / lost / sub-threshold-gap / idle.

Pure synthetic frame-track data; fast and deterministic, no real clip, no GPU.
"""

from __future__ import annotations

import pytest

from AirLine.core_bridge import Detection, FrameTracks
from AirLine.target import TargetTracker, TargetState


def _frame(index, ids):
    """Build a FrameTracks containing the given track IDs as 'player' boxes."""
    dets = [
        Detection(track_id=i, cls=0, cls_name="player", box=(i, i, i + 10, i + 20))
        for i in ids
    ]
    return FrameTracks(index=index, detections=dets)


def test_idle_when_nothing_selected():
    t = TargetTracker()
    status = t.update(_frame(0, [1, 2, 3]))
    assert status.state == TargetState.IDLE
    assert status.track_id is None
    assert status.box is None


def test_locked_when_target_present_with_correct_box():
    t = TargetTracker()
    t.select(7)
    status = t.update(_frame(0, [5, 7, 9]))
    assert status.state == TargetState.LOCKED
    assert status.track_id == 7
    assert status.box == (7, 7, 17, 27)
    assert status.missing_frames == 0


def test_single_frame_gap_stays_locked():
    """A 1-frame drop under threshold must NOT flip to LOST (no overreaction)."""
    t = TargetTracker(miss_threshold=5)
    t.select(7)
    t.update(_frame(0, [7]))            # present
    status = t.update(_frame(1, [1, 2]))  # 7 missing for 1 frame
    assert status.state == TargetState.LOCKED
    assert status.missing_frames == 1
    # recovers cleanly
    status = t.update(_frame(2, [7]))
    assert status.state == TargetState.LOCKED
    assert status.missing_frames == 0


def test_sustained_gap_becomes_lost_at_threshold():
    t = TargetTracker(miss_threshold=3)
    t.select(7)
    t.update(_frame(0, [7]))
    assert t.update(_frame(1, [1])).state == TargetState.LOCKED   # miss 1
    assert t.update(_frame(2, [1])).state == TargetState.LOCKED   # miss 2
    status = t.update(_frame(3, [1]))                             # miss 3 == threshold
    assert status.state == TargetState.LOST
    assert status.missing_frames == 3


def test_lost_is_sticky_no_silent_reacquire():
    """Once confirmed LOST, the same ID reappearing must NOT silently re-lock."""
    t = TargetTracker(miss_threshold=2)
    t.select(7)
    t.update(_frame(0, [7]))
    t.update(_frame(1, [1]))            # miss 1
    assert t.update(_frame(2, [1])).state == TargetState.LOST  # confirmed
    status = t.update(_frame(3, [7]))  # 7 is back, but we stay LOST
    assert status.state == TargetState.LOST


def test_reselect_clears_lost_state():
    t = TargetTracker(miss_threshold=2)
    t.select(7)
    t.update(_frame(0, [1]))
    t.update(_frame(1, [1]))           # LOST
    t.select(1)                        # explicit new target
    status = t.update(_frame(2, [1]))
    assert status.state == TargetState.LOCKED
    assert status.track_id == 1


def test_clear_returns_to_idle():
    t = TargetTracker()
    t.select(7)
    t.clear()
    assert t.update(_frame(0, [7])).state == TargetState.IDLE


def test_invalid_threshold_rejected():
    with pytest.raises(ValueError):
        TargetTracker(miss_threshold=0)
