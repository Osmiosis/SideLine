from backend import pipeline
from backend.schemas import JobConfig


def _cfg(sport, deliverables):
    return JobConfig(job_id="j", sport=sport, match_name="x", match_date="2026-06-01",
        video_path="raw_video.mp4", calibration_points=[], roster=[], player_tags={},
        deliverables_requested=deliverables, created_at="2026-06-01T00:00:00+00:00")


def test_ph_steps_present_and_ordered_football():
    keys = [s.key for s in pipeline.resolve_steps(_cfg("football", ["player_highlights"]))]
    for k in ("involvement", "clip-candidates", "tagging_pending", "reels"):
        assert k in keys
    assert keys.index("clip-candidates") < keys.index("tagging_pending") < keys.index("reels")
    assert "follow-cam" in keys  # PH needs follow_cam even without events


def test_ph_steps_present_basketball():
    keys = [s.key for s in pipeline.resolve_steps(_cfg("basketball", ["player_highlights"]))]
    for k in ("involvement", "clip-candidates", "tagging_pending", "reels", "follow-cam"):
        assert k in keys


def test_coach_only_has_no_ph_or_followcam_football():
    keys = [s.key for s in pipeline.resolve_steps(_cfg("football", ["coach_analytics"]))]
    assert "tagging_pending" not in keys and "reels" not in keys
    assert "follow-cam" not in keys


def test_tagging_pending_step_builds_none(tmp_path):
    steps = {s.key: s for s in pipeline.resolve_steps(_cfg("football", ["player_highlights"]))}
    built = steps["tagging_pending"].build(
        pipeline.StepCtx(job_dir=tmp_path, job_id="j", sport="football"))
    assert built is None
