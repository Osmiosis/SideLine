"""Per-sport calibration landmark templates: map the frontend's corner labels
to real-world metre coordinates (centre-origin). Used to build the homography
from the operator's 4 marked points."""
from __future__ import annotations

# FIFA pitch 105 x 68 m -> corners at (+/-52.5, +/-34). "far" = top of frame
# (positive y), "near" = bottom (negative y); left = negative x.
_FOOTBALL = {
    "far-left corner": (-52.5, 34.0),
    "far-right corner": (52.5, 34.0),
    "near-right corner": (52.5, -34.0),
    "near-left corner": (-52.5, -34.0),
}
# FIBA court 28 x 15 m -> corners at (+/-14.0, +/-7.5).
_BASKETBALL = {
    "far-left corner": (-14.0, 7.5),
    "far-right corner": (14.0, 7.5),
    "near-right corner": (14.0, -7.5),
    "near-left corner": (-14.0, -7.5),
}
_TEMPLATES = {"football": _FOOTBALL, "basketball": _BASKETBALL}


def template(sport: str) -> dict[str, tuple[float, float]]:
    return _TEMPLATES[sport]


def world_points(sport: str, labels: list[str]) -> list[list[float]]:
    t = template(sport)
    return [list(t[label]) for label in labels]
