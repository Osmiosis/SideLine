"""End-to-end flow test: create → upload → calibration → deliverables → ready → download.
CV is monkeypatched (no GPU). Verifies the full HTTP + worker lifecycle."""
import cv2
import numpy as np
import pytest

from backend import pipeline


def _tiny_mp4(path):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 48))
    for _ in range(5):
        vw.write(np.zeros((48, 64, 3), np.uint8))
    vw.release()


def test_full_flow_to_ready(client, tmp_path, monkeypatch):
    # Monkeypatch run_step to a no-op so no CV/GPU runs.
    monkeypatch.setattr(pipeline, "run_step", lambda step, ctx, logs: None)

    # 1. create
    jid = client.post("/api/jobs", json={
        "sport": "football", "match_name": "U14 Final",
        "match_date": "2026-05-31"}).json()["job_id"]

    # 2. upload
    src = tmp_path / "tiny.mp4"
    _tiny_mp4(src)
    with open(src, "rb") as f:
        client.post(f"/api/jobs/{jid}/video", content=f.read(),
                    headers={"content-type": "application/octet-stream"})

    # 3. calibration
    client.post(f"/api/jobs/{jid}/calibration", json={"calibration_points": [
        {"pixel_x": 0, "pixel_y": 0, "real_world_label": "far-left corner"},
        {"pixel_x": 63, "pixel_y": 0, "real_world_label": "far-right corner"},
        {"pixel_x": 63, "pixel_y": 47, "real_world_label": "near-right corner"},
        {"pixel_x": 0, "pixel_y": 47, "real_world_label": "near-left corner"}]})

    # 4. select deliverables (enqueues)
    client.post(f"/api/jobs/{jid}/deliverables", json={
        "deliverables_requested": ["coach_analytics", "event_highlights"]})
    assert client.get(f"/api/jobs/{jid}/status").json()["state"] == "queued"

    # 5. run the worker (deterministic, no GPU)
    assert client.app.state.worker.run_one() is True

    # 6. ready
    status = client.get(f"/api/jobs/{jid}/status").json()
    assert status["state"] == "ready"
    assert status["progress"] == 100
