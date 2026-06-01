import json
import configparser

import cv2
import numpy as np

from backend import adapters


def _make_mp4(path, n=8, w=64, h=48):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (w, h))
    for i in range(n):
        vw.write(np.full((h, w, 3), i, dtype=np.uint8))
    vw.release()


def test_decode_writes_frames_and_seqinfo(tmp_path):
    src = tmp_path / "v.mp4"; _make_mp4(src, n=8)
    info = adapters.decode_video(src, tmp_path / "frames", seq="job1")
    img1 = tmp_path / "frames" / "job1" / "img1"
    jpgs = sorted(img1.glob("*.jpg"))
    assert len(jpgs) == info["n_frames"] >= 1
    assert jpgs[0].name == "000001.jpg"          # 6-digit, 1-indexed
    ini = configparser.ConfigParser()
    ini.read(tmp_path / "frames" / "job1" / "seqinfo.ini")
    assert int(ini["Sequence"]["seqLength"]) == info["n_frames"]
    assert ini["Sequence"]["imDir"] == "img1"


def test_write_homography_solves_and_matches_schema(tmp_path):
    # four pixel corners of a 1000x500 image mapped to football pitch corners
    cal = [
        {"pixel_x": 0, "pixel_y": 0, "real_world_label": "far-left corner"},
        {"pixel_x": 1000, "pixel_y": 0, "real_world_label": "far-right corner"},
        {"pixel_x": 1000, "pixel_y": 500, "real_world_label": "near-right corner"},
        {"pixel_x": 0, "pixel_y": 500, "real_world_label": "near-left corner"},
    ]
    out = tmp_path / "homography.json"
    adapters.write_homography(cal, "football", out)
    h = json.loads(out.read_text())
    assert "H_court_from_img" in h and "H_img_from_court" in h
    H = np.array(h["H_court_from_img"], dtype=np.float64)
    assert H.shape == (3, 3)
    # a known pixel maps near its pitch metre target
    p = cv2.perspectiveTransform(np.array([[[0.0, 0.0]]], np.float32), H)[0][0]
    assert abs(p[0] - (-52.5)) < 1.0 and abs(p[1] - 34.0) < 1.0


def test_write_homography_rejects_degenerate_points(tmp_path):
    import pytest
    # all four points collinear -> findHomography returns None
    cal = [
        {"pixel_x": 0, "pixel_y": 0, "real_world_label": "far-left corner"},
        {"pixel_x": 10, "pixel_y": 0, "real_world_label": "far-right corner"},
        {"pixel_x": 20, "pixel_y": 0, "real_world_label": "near-right corner"},
        {"pixel_x": 30, "pixel_y": 0, "real_world_label": "near-left corner"},
    ]
    with pytest.raises(ValueError):
        adapters.write_homography(cal, "football", tmp_path / "h.json")
