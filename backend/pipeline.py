"""Stage graph resolution + a STUB stage runner.

Plan 1 only: every stage is faked. Plan 3 replaces `run_stage_stub` with real
subprocess calls to the CV scripts (see the spec, section 5). The stage LIST
logic here is real and reused by the worker in all plans."""
from __future__ import annotations

import time
from pathlib import Path

from backend.config import DELIVERABLE_STAGES, FOUNDATION_STAGES
from backend.schemas import JobConfig

_STAGE_LABELS: dict[str, str] = {
    "decoding": "Reading the video",
    "detecting": "Finding players",
    "tracking": "Following players",
    "teams": "Sorting teams",
    "ball": "Tracking the ball",
    "analytics": "Building analytics",
    "events": "Finding key moments",
    "tagging_pending": "Waiting for player names",
    "tagging_done": "Names received",
    "player_highlights": "Building player reels",
    "ready": "Ready",
    "queued": "Waiting in line",
}


def stage_label(stage: str) -> str:
    return _STAGE_LABELS.get(stage, stage.replace("_", " ").capitalize())


def resolve_stages(cfg: JobConfig) -> list[str]:
    """Foundation once, then per-deliverable stages in DELIVERABLES order."""
    stages: list[str] = list(FOUNDATION_STAGES)
    for d in ("coach_analytics", "event_highlights", "player_highlights"):
        if d in cfg.deliverables_requested:
            for s in DELIVERABLE_STAGES[d]:
                if s not in stages:
                    stages.append(s)
    return stages


def run_stage_stub(job_dir: Path, stage: str) -> None:
    """Fake a stage: brief sleep + write a marker file into outputs/.
    Replaced by real subprocess invocation in Plan 3."""
    time.sleep(0.05)
    outputs = job_dir / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / f"{stage}.stub.txt").write_text(
        f"stub output for stage {stage}\n", encoding="utf-8")
