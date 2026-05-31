def _job_with_video(client, tmp_path):
    import cv2, numpy as np
    jid = client.post("/api/jobs", json={
        "sport": "football", "match_name": "x",
        "match_date": "2026-05-31"}).json()["job_id"]
    p = tmp_path / "v.mp4"
    vw = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 48))
    for i in range(5):
        vw.write(np.zeros((48, 64, 3), np.uint8))
    vw.release()
    with open(p, "rb") as f:
        client.post(f"/api/jobs/{jid}/video", content=f.read(),
                    headers={"content-type": "application/octet-stream"})
    return jid


def test_calibration_persists(client, tmp_path):
    jid = _job_with_video(client, tmp_path)
    r = client.post(f"/api/jobs/{jid}/calibration", json={"calibration_points": [
        {"pixel_x": 1, "pixel_y": 2, "real_world_label": "tl"}]})
    assert r.status_code == 200
    cfg = client.app.state.store.read_config(jid)
    assert cfg.calibration_points[0].real_world_label == "tl"


def test_roster_persists(client, tmp_path):
    jid = _job_with_video(client, tmp_path)
    r = client.post(f"/api/jobs/{jid}/roster",
                    json={"roster": ["Alex", "Sam"]})
    assert r.status_code == 200
    assert client.app.state.store.read_config(jid).roster == ["Alex", "Sam"]


def test_deliverables_enqueues_job(client, tmp_path):
    jid = _job_with_video(client, tmp_path)
    r = client.post(f"/api/jobs/{jid}/deliverables",
                    json={"deliverables_requested": ["coach_analytics"]})
    assert r.status_code == 200
    assert client.get(f"/api/jobs/{jid}/status").json()["state"] == "queued"


def test_tags_persist(client, tmp_path):
    jid = _job_with_video(client, tmp_path)
    r = client.post(f"/api/jobs/{jid}/tags",
                    json={"player_tags": {"clip_0001": "Alex"}})
    assert r.status_code == 200
    assert client.app.state.store.read_config(jid).player_tags == {
        "clip_0001": "Alex"}
