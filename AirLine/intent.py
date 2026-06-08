"""intent — the meaning layer + thin glue onto the proven executor.

Two responsibilities, both deliberately thin (the heavy lifting already exists
in TargetTracker and VirtualCamera):

  1. ``gesture_to_intent`` — map a confirmed Gesture to a typed IntentCommand.
     This is the separation seam: gestures (modality) -> intents (meaning).
  2. ``IntentApplier`` — apply an IntentCommand to the existing pipeline:
        SELECT / SWITCH_NEXT / SWITCH_PREV / RELEASE -> TargetTracker
        SHOT_TIGHT / SHOT_WIDE                       -> camera zoom (via CameraConfig)

Camera shot-size is driven by mutating the camera's PUBLIC CameraConfig tunables
(zoom fractions) — NOT by editing camera.py or changing the VirtualCamera
contract. A "shot type" intent overrides the speed-adaptive zoom with an explicit
size, which is exactly what it should do.
"""

from __future__ import annotations

from typing import Optional

from AirLine.target import TargetTracker, TargetState
from AirLine.camera import VirtualCamera, Shot
from AirLine.core_bridge import FrameTracks
# IntentCommand + gesture_to_intent live in the stdlib-safe module so the Day-6
# capture process (gestures venv, no ultralytics) can import them. Re-exported here
# so existing `from AirLine.intent import IntentCommand, gesture_to_intent` keeps working.
from AirLine.intent_types import IntentCommand, gesture_to_intent


# Shot intents map to named camera shots (resolved inside the camera, not here).
_INTENT_TO_SHOT = {
    IntentCommand.SHOT_TIGHT: Shot.TIGHT,
    IntentCommand.SHOT_WIDE: Shot.WIDE,
    IntentCommand.SHOT_ORBIT: Shot.ORBIT,
    IntentCommand.SHOT_PUSH_IN: Shot.PUSH_IN,
    IntentCommand.SHOT_PULL_OUT: Shot.PULL_OUT,
    IntentCommand.SHOT_DOLLY: Shot.DOLLY,
}


def _visible_ids(frame_tracks: FrameTracks) -> list[int]:
    seen: list[int] = []
    for d in frame_tracks.detections:
        if d.track_id is not None and d.track_id not in seen:
            seen.append(d.track_id)
    return seen


def _center_x(box) -> float:
    return (box[0] + box[2]) / 2.0


class IntentApplier:
    """Applies confirmed IntentCommands onto a TargetTracker + VirtualCamera.

    Shot intents are dispatched to the camera's named-shot API (``request_shot``);
    this layer no longer pokes CameraConfig zoom values. It says "request shot X",
    the camera decides how to execute it.
    """

    def __init__(self, tracker: TargetTracker, camera: VirtualCamera):
        self.tracker = tracker
        self.camera = camera
        self.shot: Optional[IntentCommand] = None  # current shot intent, for display

    def apply(self, cmd: Optional[IntentCommand], frame_tracks: FrameTracks,
              ref_x: Optional[float] = None, frame_w: Optional[int] = None) -> None:
        if cmd is None:
            return
        ids = _visible_ids(frame_tracks)

        if cmd == IntentCommand.SELECT:
            if not ids:
                return
            # v1 simplification (per PRD): lock the subject whose box centre-x is
            # nearest the reference point (fingertip-x, or frame centre if none).
            if ref_x is None:
                ref_x = (frame_w / 2.0) if frame_w else 0.0
            best = min(frame_tracks.detections,
                       key=lambda d: abs(_center_x(d.box) - ref_x)
                       if d.track_id is not None else float("inf"))
            if best.track_id is not None:
                self.tracker.select(best.track_id)

        elif cmd in (IntentCommand.SWITCH_NEXT, IntentCommand.SWITCH_PREV):
            if not ids:
                return
            step = 1 if cmd == IntentCommand.SWITCH_NEXT else -1
            cur = self.tracker.target_id
            if cur in ids:
                self.tracker.select(ids[(ids.index(cur) + step) % len(ids)])
            else:
                self.tracker.select(ids[0])

        elif cmd == IntentCommand.RELEASE:
            self.tracker.clear()
            self.camera.request_shot(Shot.AUTO)
            self.shot = None

        elif cmd in _INTENT_TO_SHOT:
            self.camera.request_shot(_INTENT_TO_SHOT[cmd])
            self.shot = cmd
