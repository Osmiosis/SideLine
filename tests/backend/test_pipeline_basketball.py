from backend import pipeline
from backend.schemas import JobConfig


def _cfg(deliverables):
    return JobConfig(job_id="bjob", sport="basketball", match_name="x",
        match_date="2026-06-01", video_path="raw_video.mp4",
        calibration_points=[], roster=[], player_tags={},
        deliverables_requested=deliverables, created_at="2026-06-01T00:00:00+00:00")


def test_basketball_coach_steps():
    keys = [s.key for s in pipeline.resolve_steps(_cfg(["coach_analytics"]))]
    assert keys[:2] == ["decode", "homography"]
    assert "detect-players" in keys and "track-players" in keys
    assert "team-assign" in keys and "coach" in keys
    assert "clip" not in keys and "detect-events" not in keys


def test_basketball_events_steps():
    keys = [s.key for s in pipeline.resolve_steps(_cfg(["event_highlights"]))]
    assert "follow-cam" in keys and "detect-events" in keys and "clip" in keys
    assert "coach" not in keys


def test_basketball_both_dedupes_foundation():
    keys = [s.key for s in pipeline.resolve_steps(_cfg(["coach_analytics", "event_highlights"]))]
    assert keys.count("track-players") == 1 and keys.count("team-assign") == 1
    assert "coach" in keys and "clip" in keys


def test_basketball_team_assign_argv(tmp_path):
    steps = {s.key: s for s in pipeline.resolve_steps(_cfg(["coach_analytics"]))}
    argv = steps["team-assign"].build(pipeline.StepCtx(job_dir=tmp_path, job_id="bjob",
                                                       sport="basketball"))
    j = " ".join(argv)
    assert "bball_team_embed.py" in j and "--seq" in j and "bjob" in j
