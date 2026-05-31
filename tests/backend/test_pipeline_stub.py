from backend import pipeline
from backend.schemas import JobConfig


def _cfg(deliverables):
    return JobConfig(
        job_id="j1", sport="football", match_name="x", match_date="2026-05-31",
        video_path="raw_video.mp4", calibration_points=[], roster=[],
        player_tags={}, deliverables_requested=deliverables,
        created_at="2026-05-31T00:00:00+00:00",
    )


def test_resolve_stages_foundation_then_analytics():
    stages = pipeline.resolve_stages(_cfg(["coach_analytics"]))
    assert stages == ["decoding", "detecting", "tracking", "teams", "ball",
                      "analytics"]


def test_resolve_stages_dedupes_foundation_for_multiple_deliverables():
    stages = pipeline.resolve_stages(
        _cfg(["coach_analytics", "event_highlights"]))
    # foundation appears once, then analytics, then events
    assert stages == ["decoding", "detecting", "tracking", "teams", "ball",
                      "analytics", "events"]


def test_stage_label_is_plain_english():
    assert pipeline.stage_label("tracking") == "Following players"
    assert pipeline.stage_label("ready") == "Ready"


def test_stub_run_stage_writes_marker(tmp_path):
    # The stub must create an outputs marker so e2e can assert progress.
    pipeline.run_stage_stub(tmp_path, "analytics")
    assert (tmp_path / "outputs" / "analytics.stub.txt").exists()
