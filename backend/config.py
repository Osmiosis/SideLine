"""Static configuration for the Operator App backend. Constants only — no logic."""
from __future__ import annotations

import sys as _sys
from pathlib import Path

# Repo root = parent of the backend/ package directory.
REPO_ROOT: Path = Path(__file__).resolve().parent.parent
JOBS_DIR: Path = REPO_ROOT / "jobs"
WEBSITE_DIR: Path = REPO_ROOT / "Website"

PYTHON_EXE: str = _sys.executable           # the venv interpreter running the server
SCRIPTS_DIR: Path = REPO_ROOT / "scripts"
MODELS_DIR: Path = REPO_ROOT / "models"

# Network
HOST: str = "0.0.0.0"
PORT: int = 8000

# Domain
SPORTS: tuple[str, ...] = ("football", "basketball")
DELIVERABLES: tuple[str, ...] = (
    "coach_analytics",
    "event_highlights",
    "player_highlights",
)

# Stage graph. Foundation runs once for any deliverable; per-deliverable stages
# append after it. The worker computes the concrete stage list per job from the
# requested deliverables (see worker.py).
FOUNDATION_STAGES: tuple[str, ...] = (
    "decoding",
    "detecting",
    "tracking",
    "teams",
    "ball",
)
DELIVERABLE_STAGES: dict[str, tuple[str, ...]] = {
    "coach_analytics": ("analytics",),
    "event_highlights": ("events",),
    # tagging_pending is a human pause; tagging_done resumes to reel assembly.
    "player_highlights": ("tagging_pending", "tagging_done", "player_highlights"),
}
