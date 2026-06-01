import json


def _ph_job(client):
    return client.post("/api/jobs", json={"sport": "football", "match_name": "x",
        "match_date": "2026-06-01"}).json()["job_id"]


def test_tagging_clips_empty_before_pause(client):
    jid = _ph_job(client)
    r = client.get(f"/api/jobs/{jid}/tagging-clips")
    assert r.status_code == 200
    assert r.json()["clips"] == []


def test_tags_writes_clip_tags_and_requeues(client):
    jid = _ph_job(client)
    store = client.app.state.store
    # simulate a parked job with a manifest + one clip on disk
    ph = store.job_dir(jid) / "player_highlights" / jid
    (ph / "clips").mkdir(parents=True)
    (ph / "clips" / "t001_m00_5s.mp4").write_bytes(b"fakeclip")
    (store.job_dir(jid) / "player_highlights" / jid / "clips_manifest.json").write_text(
        json.dumps([{"clip_id": "t001_m00_5s.mp4", "track_id": 1, "role": "TeamA",
                     "start_frame": 1, "end_frame": 50}]))
    store.write_status(jid, state="tagging_pending", stage="tagging_pending",
                       progress=60, stage_label=None, error=None)

    listing = client.get(f"/api/jobs/{jid}/tagging-clips").json()
    assert listing["clips"][0]["clip_id"] == "t001_m00_5s.mp4"
    assert listing["clips"][0]["video_url"].endswith("/t001_m00_5s.mp4/video")
    vid = client.get(f"/api/jobs/{jid}/tagging-clips/t001_m00_5s.mp4/video")
    assert vid.status_code == 200 and vid.content == b"fakeclip"

    r = client.post(f"/api/jobs/{jid}/tags",
                    json={"player_tags": {"t001_m00_5s.mp4": "Alex"}})
    assert r.status_code == 200
    tags = json.loads((ph / "clip_tags.json").read_text())
    assert tags == {"t001_m00_5s.mp4": "Alex"}
    assert client.get(f"/api/jobs/{jid}/status").json()["state"] == "queued"
