"""Probe a generated clip; check email bodies. SMTP send is NOT tested here
(best-effort, exercised in the Task 9 rehearsal)."""
import cv2
import numpy as np

from agent.media import probe_duration_sec
from agent.notify import build_ready_email, build_failed_email, build_promoted_email


def test_probe_reads_real_duration(tmp_path):
    path = str(tmp_path / "clip.mp4")
    w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 64))
    for _ in range(50):  # 50 frames @ 10 fps = 5.0 s
        w.write(np.zeros((64, 64, 3), dtype=np.uint8))
    w.release()
    d = probe_duration_sec(path)
    assert d is not None and abs(d - 5.0) < 0.5


def test_probe_unreadable_returns_none(tmp_path):
    bad = tmp_path / "not_video.mp4"
    bad.write_bytes(b"this is not a video at all")
    assert probe_duration_sec(str(bad)) is None


def test_ready_email_has_link_and_expiry():
    subject, html = build_ready_email("Cup final", "https://drive.google.com/x",
                                      "2026-06-20")
    assert "Cup final" in subject
    assert "https://drive.google.com/x" in html
    assert "2026-06-20" in html


def test_failed_email_carries_friendly_message():
    subject, html = build_failed_email("Cup final", "We couldn't read the video.")
    assert "Cup final" in subject
    assert "We couldn't read the video." in html


def test_promoted_email_links_to_job_page():
    subject, html = build_promoted_email("Cup final", "https://site/job.html?id=1")
    assert "your turn" in html.lower()
    assert "https://site/job.html?id=1" in html
