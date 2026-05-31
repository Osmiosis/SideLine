import pytest
from pydantic import ValidationError

from backend import schemas


def test_create_job_request_requires_valid_sport():
    req = schemas.CreateJobRequest(
        sport="football", match_name="U14 vs Rivals", match_date="2026-05-31"
    )
    assert req.sport == "football"
    with pytest.raises(ValidationError):
        schemas.CreateJobRequest(
            sport="cricket", match_name="x", match_date="2026-05-31"
        )


def test_calibration_point_field_names_match_contract():
    p = schemas.CalibrationPoint(pixel_x=10, pixel_y=20, real_world_label="top_left")
    dumped = p.model_dump()
    assert set(dumped) == {"pixel_x", "pixel_y", "real_world_label"}


def test_deliverables_request_rejects_unknown_deliverable():
    schemas.DeliverablesRequest(deliverables_requested=["coach_analytics"])
    with pytest.raises(ValidationError):
        schemas.DeliverablesRequest(deliverables_requested=["make_me_famous"])


def test_job_config_round_trips_contract_fields():
    cfg = schemas.JobConfig(
        job_id="abc",
        sport="basketball",
        match_name="Finals",
        match_date="2026-05-31",
        video_path="raw_video.mp4",
        calibration_points=[],
        roster=[],
        player_tags={},
        deliverables_requested=["event_highlights"],
        created_at="2026-05-31T00:00:00+00:00",
    )
    keys = set(cfg.model_dump().keys())
    assert keys == {
        "job_id", "sport", "match_name", "match_date", "video_path",
        "calibration_points", "roster", "player_tags",
        "deliverables_requested", "created_at",
    }
