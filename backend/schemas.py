"""Pydantic models. This module is the single source of contract field names —
they must match PRD'S/Backend_Spec_OperatorApp.md and the frontend exactly."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.config import DELIVERABLES, SPORTS

Sport = Literal["football", "basketball"]
Deliverable = Literal["coach_analytics", "event_highlights", "player_highlights"]


class CreateJobRequest(BaseModel):
    sport: Sport
    match_name: str = Field(min_length=1)
    match_date: str  # YYYY-MM-DD (frontend supplies; not strictly validated here)


class CalibrationPoint(BaseModel):
    pixel_x: int
    pixel_y: int
    real_world_label: str


class CalibrationRequest(BaseModel):
    calibration_points: list[CalibrationPoint]


class RosterRequest(BaseModel):
    roster: list[str]


class TagsRequest(BaseModel):
    player_tags: dict[str, str]  # clip_id -> player_name


class DeliverablesRequest(BaseModel):
    deliverables_requested: list[Deliverable] = Field(min_length=1)


class JobConfig(BaseModel):
    """The on-disk job_config.json contract shape (field names are frozen)."""
    job_id: str
    sport: Sport
    match_name: str
    match_date: str
    video_path: str
    calibration_points: list[CalibrationPoint]
    roster: list[str]
    player_tags: dict[str, str]
    deliverables_requested: list[Deliverable]
    created_at: str


class JobSummary(BaseModel):
    """Dashboard list item."""
    job_id: str
    sport: Sport
    match_name: str
    match_date: str
    state: str
    created_at: str


class JobStatus(BaseModel):
    """status endpoint payload."""
    job_id: str
    state: str
    stage: str | None
    progress: int  # 0..100
    stage_label: str | None  # plain-English label for the UI
    error: str | None  # friendly message when state == "failed"


# sanity: the Literals above must stay in lockstep with config.
assert set(SPORTS) == {"football", "basketball"}
assert set(DELIVERABLES) == {
    "coach_analytics", "event_highlights", "player_highlights"
}
