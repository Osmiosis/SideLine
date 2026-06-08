"""target — AirLine's notion of "the current target".

This is the first behaviour SideLine never had: a state manager that locks onto
ONE subject by track ID and follows it across frames, degrading gracefully when
that ID disappears (the known ByteTrack fragmentation case).

It is pure logic over the track data ``core_bridge`` already produces — ZERO new
perception. It does NOT re-identify a lost target under a new ID; that is a
future PRD. When the target is lost, it stays lost and says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from AirLine.core_bridge import FrameTracks


class TargetState(str, Enum):
    IDLE = "IDLE"      # nothing selected
    LOCKED = "LOCKED"  # target selected and present (or in a sub-threshold gap)
    LOST = "LOST"      # target ID gone for >= threshold frames (confirmed)


@dataclass
class TargetStatus:
    state: TargetState
    track_id: Optional[int]
    box: Optional[tuple[float, float, float, float]]  # this frame's box, if visible
    missing_frames: int  # consecutive frames the target has been absent


class TargetTracker:
    """Locks onto a track ID and reports LOCKED / LOST / IDLE per frame.

    A single-frame gap is normal jitter, so a transient miss keeps the state
    LOCKED. Only a sustained gap (>= ``miss_threshold`` consecutive frames)
    confirms LOST. Once confirmed LOST the tracker stays LOST until a new
    ``select()`` — it never silently re-acquires (re-ID is deferred).
    """

    def __init__(self, miss_threshold: int = 5):
        if miss_threshold < 1:
            raise ValueError("miss_threshold must be >= 1")
        self.miss_threshold = miss_threshold
        self.target_id: Optional[int] = None
        self.last_box: Optional[tuple[float, float, float, float]] = None
        self._missing = 0
        self._confirmed_lost = False

    def select(self, track_id: int) -> None:
        """Lock onto a subject. Resets any prior loss state."""
        self.target_id = track_id
        self.last_box = None
        self._missing = 0
        self._confirmed_lost = False

    def clear(self) -> None:
        """Deselect — return to IDLE."""
        self.target_id = None
        self.last_box = None
        self._missing = 0
        self._confirmed_lost = False

    def update(self, frame_tracks: FrameTracks) -> TargetStatus:
        """Process one frame's tracks and report the target's status."""
        if self.target_id is None:
            return TargetStatus(TargetState.IDLE, None, None, 0)

        # Sticky LOST: once confirmed, never silently re-acquire.
        if self._confirmed_lost:
            return TargetStatus(TargetState.LOST, self.target_id, None, self._missing)

        det = next(
            (d for d in frame_tracks.detections if d.track_id == self.target_id),
            None,
        )
        if det is not None:
            self._missing = 0
            self.last_box = det.box
            return TargetStatus(TargetState.LOCKED, self.target_id, det.box, 0)

        # Target absent this frame.
        self._missing += 1
        if self._missing >= self.miss_threshold:
            self._confirmed_lost = True
            return TargetStatus(TargetState.LOST, self.target_id, None, self._missing)

        # Sub-threshold gap: still LOCKED, just not visible this frame.
        return TargetStatus(TargetState.LOCKED, self.target_id, None, self._missing)
