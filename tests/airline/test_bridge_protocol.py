"""Tests for the Day-6 bridge protocol: round-trip, malformed-safety, in-sync with
IntentCommand, and the decoded-intent -> IntentApplier path. Main venv; no socket,
no webcam.
"""

from __future__ import annotations

from AirLine.bridge_protocol import (
    IntentMessage, encode, decode, is_known, KNOWN_INTENTS,
)
from AirLine.intent_types import IntentCommand


def test_round_trip_preserves_fields():
    msg = IntentMessage(intent="select", ts=123.5, seq=7, payload={"ref_x": 0.4})
    out = decode(encode(msg))
    assert out is not None
    assert (out.intent, out.ts, out.seq, out.payload) == ("select", 123.5, 7, {"ref_x": 0.4})


def test_round_trip_accepts_str_or_bytes():
    line = encode(IntentMessage("release", 1.0))
    assert decode(line).intent == "release"            # bytes
    assert decode(line.decode("utf-8")).intent == "release"  # str


def test_known_intents_match_enum():
    # Guard against drift between the stdlib protocol set and IntentCommand.
    assert KNOWN_INTENTS == {c.value for c in IntentCommand}


def test_is_known_filters_unknown_intent():
    assert is_known(decode(encode(IntentMessage("select", 1.0))))
    assert not is_known(decode(encode(IntentMessage("teleport", 1.0))))


def test_malformed_messages_decode_to_none_never_raise():
    bad = [
        b"not json at all",
        b"{}",                              # missing intent/ts
        b'{"intent": 5, "ts": 1.0}',        # intent not a string
        b'{"intent": "select"}',            # missing ts
        b'{"intent": "select", "ts": "x"}',  # ts not floatable
        b'{"intent": "select", "ts": 1.0, "payload": 7}',  # payload not a dict
        b"",                                 # empty
        b"[1,2,3]",                          # json but not an object
        b"\x80\x81 garbage bytes",
    ]
    for line in bad:
        assert decode(line) is None
        assert not is_known(decode(line))


def test_decoded_intent_drives_intent_applier():
    # The render-side path: decode a wire message, then apply it via IntentApplier.
    from AirLine.core_bridge import Detection, FrameTracks
    from AirLine.target import TargetTracker
    from AirLine.camera import VirtualCamera, Shot
    from AirLine.intent import IntentApplier

    cam = VirtualCamera()
    tr = TargetTracker()
    ap = IntentApplier(tr, cam)
    ft = FrameTracks(index=0, detections=[
        Detection(track_id=2, cls=0, cls_name="player", box=(635, 0, 645, 40)),
    ])

    msg = decode(encode(IntentMessage("select", 1.0, payload={"ref_x": 0.5})))
    ref_x = msg.payload["ref_x"] * 1280
    ap.apply(IntentCommand(msg.intent), ft, ref_x=ref_x, frame_w=1280)
    assert tr.target_id == 2

    msg2 = decode(encode(IntentMessage("shot_tight", 2.0)))
    ap.apply(IntentCommand(msg2.intent), ft, frame_w=1280)
    assert cam.shot == Shot.TIGHT
