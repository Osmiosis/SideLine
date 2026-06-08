"""Tests for the intent wiring — confirmed intents applied onto TargetTracker
and CameraConfig. Synthetic frame-tracks; no clip, no camera.py edits.
"""

from __future__ import annotations

from AirLine.core_bridge import Detection, FrameTracks
from AirLine.target import TargetTracker
from AirLine.camera import VirtualCamera, Shot
from AirLine.intent import IntentApplier, IntentCommand


def _frame(ids_and_x):
    dets = [Detection(track_id=i, cls=0, cls_name="player", box=(x - 5, 0, x + 5, 40))
            for (i, x) in ids_and_x]
    return FrameTracks(index=0, detections=dets)


def _applier():
    cam = VirtualCamera()
    tr = TargetTracker()
    return IntentApplier(tr, cam), tr, cam


def test_select_locks_subject_nearest_reference_x():
    ap, tr, _ = _applier()
    ft = _frame([(1, 100), (2, 640), (3, 1200)])
    ap.apply(IntentCommand.SELECT, ft, ref_x=630)  # nearest is id 2 @640
    assert tr.target_id == 2


def test_select_defaults_to_frame_centre_when_no_ref():
    ap, tr, _ = _applier()
    ft = _frame([(1, 100), (2, 640), (3, 1200)])
    ap.apply(IntentCommand.SELECT, ft, frame_w=1280)  # centre 640 -> id 2
    assert tr.target_id == 2


def test_switch_next_and_prev_cycle_visible_ids():
    ap, tr, _ = _applier()
    ft = _frame([(1, 100), (2, 640), (3, 1200)])
    tr.select(2)
    ap.apply(IntentCommand.SWITCH_NEXT, ft)
    assert tr.target_id == 3
    ap.apply(IntentCommand.SWITCH_NEXT, ft)
    assert tr.target_id == 1   # wraps
    ap.apply(IntentCommand.SWITCH_PREV, ft)
    assert tr.target_id == 3


def test_switch_without_current_picks_first():
    ap, tr, _ = _applier()
    ft = _frame([(7, 100), (9, 640)])
    ap.apply(IntentCommand.SWITCH_NEXT, ft)
    assert tr.target_id == 7


def test_release_clears_target_and_shot():
    ap, tr, cam = _applier()
    ft = _frame([(1, 100)])
    tr.select(1)
    ap.apply(IntentCommand.SHOT_TIGHT, ft)
    ap.apply(IntentCommand.RELEASE, ft)
    assert tr.target_id is None
    assert ap.shot is None
    assert cam.shot == Shot.AUTO  # release resets the camera shot


def test_shot_tight_and_wide_request_named_camera_shots():
    ap, _, cam = _applier()
    ft = _frame([(1, 100)])
    ap.apply(IntentCommand.SHOT_TIGHT, ft)
    assert cam.shot == Shot.TIGHT
    assert ap.shot == IntentCommand.SHOT_TIGHT
    ap.apply(IntentCommand.SHOT_WIDE, ft)
    assert cam.shot == Shot.WIDE
    assert ap.shot == IntentCommand.SHOT_WIDE


def test_shot_orbit_routes_to_camera_orbit():
    ap, _, cam = _applier()
    ft = _frame([(1, 100)])
    ap.apply(IntentCommand.SHOT_ORBIT, ft)
    assert cam.shot == Shot.ORBIT
    assert ap.shot == IntentCommand.SHOT_ORBIT


def test_day8_shots_route_through_seam():
    ap, _, cam = _applier()
    ft = _frame([(1, 100)])
    for cmd, want in [(IntentCommand.SHOT_PUSH_IN, Shot.PUSH_IN),
                      (IntentCommand.SHOT_PULL_OUT, Shot.PULL_OUT),
                      (IntentCommand.SHOT_DOLLY, Shot.DOLLY)]:
        ap.apply(cmd, ft)
        assert cam.shot == want
        assert ap.shot == cmd


def test_orbit_does_not_change_auto_crop_behaviour():
    """Requesting ORBIT must not alter the 2D follow/zoom crop (regression guard)."""
    from AirLine.target import TargetState
    a = VirtualCamera()
    b = VirtualCamera()
    b.request_shot(Shot.ORBIT)
    box = (700 - 20, 360 - 40, 700 + 20, 360 + 40)
    for _ in range(40):
        ca = a.update(box, TargetState.LOCKED, (1280, 720))
        cb = b.update(box, TargetState.LOCKED, (1280, 720))
    assert (ca.x, ca.y, ca.w, ca.h) == (cb.x, cb.y, cb.w, cb.h)


def test_none_command_is_noop():
    ap, tr, _ = _applier()
    ft = _frame([(1, 100)])
    ap.apply(None, ft)
    assert tr.target_id is None


def test_select_with_no_visible_ids_is_safe():
    ap, tr, _ = _applier()
    ft = FrameTracks(index=0, detections=[])
    ap.apply(IntentCommand.SELECT, ft, frame_w=1280)
    assert tr.target_id is None
