"""First AirLine test. Proves the core_bridge seam returns a non-empty,
correctly-shaped track structure — using a MOCKED detector so CI needs no GPU
and no real clip. Mirrors the mocking discipline in tests/backend/.
"""

from __future__ import annotations

import numpy as np
import pytest

from AirLine import core_bridge
from AirLine.core_bridge import Detection, FrameTracks, run_tracker, resolve_model


# --- fakes that quack like Ultralytics Results/Boxes -------------------------
class _FakeBoxes:
    def __init__(self, cls, xyxy, ids):
        self.cls = np.asarray(cls, dtype=float)
        self.xyxy = np.asarray(xyxy, dtype=float)
        self.id = None if ids is None else np.asarray(ids, dtype=float)


class _FakeResult:
    def __init__(self, cls, xyxy, ids, names, frame):
        self.boxes = _FakeBoxes(cls, xyxy, ids)
        self.names = names
        self.orig_img = frame


class _FakeModel:
    """Stand-in for YOLO: .track() yields two frames of fake detections."""

    NAMES = {0: "player", 1: "ball"}

    def __init__(self, *_, **__):
        pass

    def track(self, source=None, device=0, **params):
        # frame 0: two players + one ball, all with IDs
        yield _FakeResult(
            cls=[0, 0, 1],
            xyxy=[[10, 10, 30, 60], [40, 40, 60, 90], [50, 50, 56, 56]],
            ids=[1, 2, 3],
            names=self.NAMES,
            frame=np.zeros((100, 100, 3), dtype=np.uint8),
        )
        # frame 1: one player, no track ID yet (id is None)
        yield _FakeResult(
            cls=[0],
            xyxy=[[12, 12, 32, 62]],
            ids=None,
            names=self.NAMES,
            frame=np.zeros((100, 100, 3), dtype=np.uint8),
        )


@pytest.fixture
def fake_clip(tmp_path):
    p = tmp_path / "fixture.mp4"
    p.write_bytes(b"\x00")  # exists; content irrelevant (model is mocked)
    return str(p)


def test_bridge_returns_nonempty_correctly_shaped_tracks(fake_clip):
    model = _FakeModel()
    frames = list(run_tracker(fake_clip, model=model))

    assert len(frames) == 2
    assert all(isinstance(f, FrameTracks) for f in frames)

    f0 = frames[0]
    assert f0.index == 0
    assert len(f0.detections) == 3
    d = f0.detections[0]
    assert isinstance(d, Detection)
    assert d.track_id == 1
    assert d.cls == 0
    assert d.cls_name == "player"
    assert len(d.box) == 4 and all(isinstance(v, float) for v in d.box)
    # ball detection present and named
    assert any(det.cls_name == "ball" for det in f0.detections)
    # frame image carried through for rendering
    assert f0.frame is not None and f0.frame.shape == (100, 100, 3)


def test_bridge_handles_frames_without_track_ids(fake_clip):
    frames = list(run_tracker(fake_clip, model=_FakeModel()))
    f1 = frames[1]
    assert len(f1.detections) == 1
    assert f1.detections[0].track_id is None  # ByteTrack hasn't assigned yet


def test_limit_stops_early(fake_clip):
    frames = list(run_tracker(fake_clip, model=_FakeModel(), limit=1))
    assert len(frames) == 1


def test_missing_clip_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        list(run_tracker(str(tmp_path / "nope.mp4"), model=_FakeModel()))


def test_resolve_model_maps_sport_keys_and_passes_paths_through():
    assert resolve_model("football").endswith("football.pt")
    assert resolve_model("basketball").endswith("basketball.pt")
    assert resolve_model("models/custom.pt") == "models/custom.pt"


def test_track_params_match_validated_config():
    # Guards against silent drift from the SideLine tracker invocation.
    assert core_bridge.TRACK_PARAMS["tracker"] == "bytetrack.yaml"
    assert core_bridge.TRACK_PARAMS["imgsz"] == 1280
    assert core_bridge.TRACK_PARAMS["persist"] is True
