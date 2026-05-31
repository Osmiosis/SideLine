import cv2
import numpy as np


def _make_tiny_mp4(path, frames=10, w=64, h=48):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(str(path), fourcc, 10.0, (w, h))
    for i in range(frames):
        img = np.full((h, w, 3), i * 10 % 255, dtype=np.uint8)
        vw.write(img)
    vw.release()


def _new_job(client):
    return client.post("/api/jobs", json={
        "sport": "football", "match_name": "x",
        "match_date": "2026-05-31"}).json()["job_id"]


def test_upload_then_frame(client, tmp_path):
    jid = _new_job(client)
    src = tmp_path / "tiny.mp4"
    _make_tiny_mp4(src)
    with open(src, "rb") as f:
        r = client.post(f"/api/jobs/{jid}/video", content=f.read(),
                        headers={"content-type": "application/octet-stream"})
    assert r.status_code == 200
    assert r.json()["state"] == "calibration_pending"

    fr = client.get(f"/api/jobs/{jid}/frame")
    assert fr.status_code == 200
    assert fr.headers["content-type"] == "image/jpeg"
    assert len(fr.content) > 100


def test_frame_before_upload_is_409(client):
    jid = _new_job(client)
    fr = client.get(f"/api/jobs/{jid}/frame")
    assert fr.status_code == 409
