"""core_bridge — the ONE deliberate seam between AirLine and the SideLine CV core.

This is the only place AirLine reaches into SideLine's tracking stack. It calls
the *existing*, validated tracker (Ultralytics YOLO + ByteTrack, configured
exactly as ``scripts/track_football.py`` / ``scripts/track_basketball.py``) and
returns the result in a plain, AirLine-owned data structure.

Design rule (Day 1 PRD): this file does NOT reimplement tracking and does NOT
edit any CV script. It replicates the validated invocation parameters verbatim
so behaviour is identical to the SideLine pipeline. If SideLine's internals
move later, only this file changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

import numpy as np
from ultralytics import YOLO

# --- validated SideLine config (mirrors scripts/track_*.py — do not diverge) ---
MODELS = {
    "football": "models/football.pt",
    "basketball": "models/basketball.pt",
}

# Exact track() params used by the validated trackers. Keeping these here, in one
# place, is the whole point of the bridge.
TRACK_PARAMS = dict(
    stream=True,
    imgsz=1280,
    tracker="bytetrack.yaml",
    persist=True,
    verbose=False,
)


@dataclass
class Detection:
    """One tracked subject in one frame (AirLine-owned, framework-agnostic)."""

    track_id: Optional[int]          # None until ByteTrack assigns an ID
    cls: int                         # class index
    cls_name: str                    # human-readable class (e.g. "player", "ball")
    box: tuple[float, float, float, float]  # xyxy in pixels


@dataclass
class FrameTracks:
    """All detections for a single frame, plus the raw frame for rendering."""

    index: int
    detections: list[Detection] = field(default_factory=list)
    frame: Optional[np.ndarray] = None  # BGR image (orig_img) — optional


def _to_numpy(x):
    """Coerce a torch tensor OR numpy array OR None to numpy (or None)."""
    if x is None:
        return None
    if hasattr(x, "cpu"):
        x = x.cpu()
    if hasattr(x, "numpy"):
        x = x.numpy()
    return np.asarray(x)


def resolve_model(sport_or_path: str) -> str:
    """Map a sport key ('football'/'basketball') to its model path, or pass a path through."""
    return MODELS.get(sport_or_path, sport_or_path)


def load_model(sport_or_path: str = "football") -> YOLO:
    """Load the validated SideLine YOLO model. Same weights the CV core uses."""
    return YOLO(resolve_model(sport_or_path))


def _result_to_frame(index: int, res, keep_frame: bool) -> FrameTracks:
    """Convert one Ultralytics Results object into an AirLine FrameTracks."""
    boxes = res.boxes
    names = getattr(res, "names", {}) or {}

    cls = _to_numpy(getattr(boxes, "cls", None))
    xyxy = _to_numpy(getattr(boxes, "xyxy", None))
    ids = _to_numpy(getattr(boxes, "id", None))

    dets: list[Detection] = []
    n = 0 if cls is None else len(cls)
    for i in range(n):
        c = int(cls[i])
        tid = None if ids is None else int(ids[i])
        box = tuple(float(v) for v in xyxy[i]) if xyxy is not None else (0.0, 0.0, 0.0, 0.0)
        dets.append(
            Detection(track_id=tid, cls=c, cls_name=str(names.get(c, c)), box=box)
        )

    frame = res.orig_img if (keep_frame and hasattr(res, "orig_img")) else None
    return FrameTracks(index=index, detections=dets, frame=frame)


def run_tracker(
    clip_path: str,
    sport: str = "football",
    device: int | str = 0,
    model: Optional[YOLO] = None,
    limit: Optional[int] = None,
    keep_frame: bool = True,
) -> Iterator[FrameTracks]:
    """Run the validated SideLine tracker on a clip; yield AirLine FrameTracks.

    Parameters mirror the CV core. ``device`` defaults to 0 (GPU) to match the
    validated pipeline; tests mock the model so no GPU is required. ``limit``
    stops early (handy for smoke runs). This is a generator — it streams.
    """
    if not Path(clip_path).exists():
        raise FileNotFoundError(f"clip not found: {clip_path}")

    model = model or load_model(sport)
    stream = model.track(source=clip_path, device=device, **TRACK_PARAMS)

    for index, res in enumerate(stream):
        yield _result_to_frame(index, res, keep_frame)
        if limit is not None and index + 1 >= limit:
            break
