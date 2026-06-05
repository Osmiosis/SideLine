import cv2
import numpy as np


def _new_job(client, name="x"):
    return client.post("/api/jobs", json={
        "sport": "football", "match_name": name,
        "match_date": "2026-05-31"}).json()["job_id"]


def _make_tiny_mp4(path, frames=10, w=64, h=48, fps=10.0):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for i in range(frames):
        vw.write(np.full((h, w, 3), i * 10 % 255, dtype=np.uint8))
    vw.release()


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00")


def test_stats_empty(client):
    s = client.get("/api/stats").json()
    assert s == {"matches_processed": 0, "ready_to_download": 0,
                 "footage_hours": 0.0, "footage_seconds": 0.0,
                 "highlights_created": 0}


def test_matches_processed_counts_all_jobs(client):
    _new_job(client); _new_job(client)
    assert client.get("/api/stats").json()["matches_processed"] == 2


def test_ready_to_download_counts_ready_state(client):
    a = _new_job(client); _new_job(client)
    store = client.app.state.store
    store.write_status(a, state="ready", stage="ready", progress=100,
                       stage_label=None, error=None)
    assert client.get("/api/stats").json()["ready_to_download"] == 1


def test_footage_hours_sums_durations(client):
    a = _new_job(client); b = _new_job(client)
    store = client.app.state.store
    store.set_duration(a, 3600.0)   # 1.0 h
    store.set_duration(b, 1800.0)   # 0.5 h
    assert client.get("/api/stats").json()["footage_hours"] == 1.5


def test_highlights_counts_event_player_and_draft(client, tmp_path):
    jid = _new_job(client)
    store = client.app.state.store
    out = store.job_dir(jid) / "outputs"
    _touch(out / "events" / jid / "clips" / "00_goal.mp4")
    _touch(out / "events" / jid / "clips" / "01_save.mp4")
    _touch(out / "player_highlights" / jid / "reels" / "maya.mp4")
    _touch(out / "event_highlights" / "auto_draft_reel.mp4")
    # non-highlights that must NOT be counted:
    _touch(out / "deliverables" / jid / "coach" / "tactical_sample.mp4")
    _touch(out / "event_highlights" / "index.json")
    assert client.get("/api/stats").json()["highlights_created"] == 4


def test_upload_records_duration(client, tmp_path):
    jid = _new_job(client)
    src = tmp_path / "tiny.mp4"
    _make_tiny_mp4(src, frames=10, fps=10.0)   # 1.0 s
    with open(src, "rb") as f:
        client.post(f"/api/jobs/{jid}/video", content=f.read(),
                    headers={"content-type": "application/octet-stream"})
    from backend import db
    row = db.get_job(client.app.state.store.conn, jid)
    assert row["duration_sec"] is not None
    assert 0.5 < row["duration_sec"] < 2.0
