import shutil
import subprocess

import cv2
import numpy as np
import pytest

from scripts.video_io import to_browser_h264

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed")


def _probe_codec(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name", "-of",
         "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True)
    return out.stdout.strip()


def _make_mp4v(path, frames=10, w=64, h=48):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (w, h))
    for i in range(frames):
        vw.write(np.full((h, w, 3), i * 10 % 255, dtype=np.uint8))
    vw.release()


def test_cv2_default_is_not_browser_playable(tmp_path):
    p = tmp_path / "clip.mp4"
    _make_mp4v(p)
    # This is the bug: cv2's default mp4v fourcc is MPEG-4 Part 2, which browsers
    # cannot decode -> <video> stays blank.
    assert _probe_codec(p) == "mpeg4"


def test_to_browser_h264_makes_clip_playable(tmp_path):
    p = tmp_path / "clip.mp4"
    _make_mp4v(p)
    assert to_browser_h264(p) is True
    assert _probe_codec(p) == "h264"


def test_to_browser_h264_missing_file_returns_false(tmp_path):
    assert to_browser_h264(tmp_path / "nope.mp4") is False
