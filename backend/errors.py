"""Map pipeline failures to operator-friendly text; log technical detail to disk.
The API must NEVER surface raw stack traces — friendly text out, detail to logs/."""
from __future__ import annotations

from pathlib import Path

_STAGE_MESSAGES: dict[str, str] = {
    "decoding": "We couldn't read the video. Please try uploading it again.",
    "detecting": "Something went wrong while finding players. Please try again.",
    "tracking": "Something went wrong while following players. Please try again.",
    "teams": "Something went wrong while sorting the teams. Please try again.",
    "ball": "Something went wrong while tracking the ball. Please try again.",
    "analytics": "Something went wrong while building the analytics. Please try again.",
    "events": "Something went wrong while finding key moments. Please try again.",
    "player_highlights": "Something went wrong while building player reels. Please try again.",
}

_GENERIC = "Something went wrong while processing this match. Please try again."


def friendly_message(stage: str) -> str:
    return _STAGE_MESSAGES.get(stage, _GENERIC)


def log_stage_failure(job_dir: Path, *, stage: str, detail: str) -> Path:
    logs = job_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / f"{stage}.log"
    log_path.write_text(detail, encoding="utf-8")
    return log_path
