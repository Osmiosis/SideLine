import json

from backend import jobs


def test_create_job_makes_dir_and_config(tmp_path):
    store = jobs.JobStore(tmp_path)
    cfg = store.create(sport="football", match_name="A vs B",
                       match_date="2026-05-31")
    job_dir = store.job_dir(cfg.job_id)
    assert job_dir.is_dir()
    assert (job_dir / "outputs").is_dir()
    written = json.loads((job_dir / "job_config.json").read_text())
    assert written["sport"] == "football"
    assert written["video_path"] == "raw_video.mp4"
    assert written["deliverables_requested"] == []


def test_update_config_persists_calibration(tmp_path):
    store = jobs.JobStore(tmp_path)
    cfg = store.create(sport="basketball", match_name="x", match_date="2026-05-31")
    store.update_config(cfg.job_id, calibration_points=[
        {"pixel_x": 1, "pixel_y": 2, "real_world_label": "tl"}])
    reread = store.read_config(cfg.job_id)
    assert reread.calibration_points[0].real_world_label == "tl"


def test_write_status_mirrors_json(tmp_path):
    store = jobs.JobStore(tmp_path)
    cfg = store.create(sport="football", match_name="x", match_date="2026-05-31")
    store.write_status(cfg.job_id, state="tracking", stage="tracking",
                       progress=40, stage_label="Following players", error=None)
    status = json.loads((store.job_dir(cfg.job_id) / "status.json").read_text())
    assert status["state"] == "tracking"
    assert status["stage_label"] == "Following players"


def test_video_path_resolves_inside_job_dir(tmp_path):
    store = jobs.JobStore(tmp_path)
    cfg = store.create(sport="football", match_name="x", match_date="2026-05-31")
    vp = store.video_path(cfg.job_id)
    assert vp == store.job_dir(cfg.job_id) / "raw_video.mp4"
