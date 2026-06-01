from backend import pipeline
from backend.schemas import JobConfig


def _cfg(deliverables):
    return JobConfig(job_id="job1", sport="football", match_name="x",
        match_date="2026-05-31", video_path="raw_video.mp4",
        calibration_points=[], roster=[], player_tags={},
        deliverables_requested=deliverables, created_at="2026-05-31T00:00:00+00:00")


def test_coach_steps_include_foundation_and_coach():
    steps = pipeline.resolve_steps(_cfg(["coach_analytics"]))
    keys = [s.key for s in steps]
    assert keys[:2] == ["decode", "homography"]
    assert "players" in keys and "team-assign" in keys and "coach" in keys
    assert "clip" not in keys            # events-only step absent


def test_events_steps_include_clip_not_coach():
    steps = pipeline.resolve_steps(_cfg(["event_highlights"]))
    keys = [s.key for s in steps]
    assert "detect-events" in keys and "clip" in keys
    assert "coach" not in keys and "possession" not in keys


def test_both_dedupes_shared_foundation():
    steps = pipeline.resolve_steps(_cfg(["coach_analytics", "event_highlights"]))
    keys = [s.key for s in steps]
    assert keys.count("players") == 1 and keys.count("team-assign") == 1
    assert "coach" in keys and "clip" in keys


def test_argv_for_players_points_at_job_dir(tmp_path):
    steps = {s.key: s for s in pipeline.resolve_steps(_cfg(["coach_analytics"]))}
    argv = steps["players"].build(pipeline.StepCtx(job_dir=tmp_path, job_id="job1",
                                                   sport="football"))
    assert argv[0].endswith("python.exe") or "python" in argv[0]
    assert "track_alfheim.py" in " ".join(argv)
    assert "job1" in " ".join(argv) or str(tmp_path) in " ".join(argv)
