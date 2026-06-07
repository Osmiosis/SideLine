"""Every agent decision, as pure functions. Tested without any I/O."""

SEGMENT_MAX_MIN = 20  # spec §0.7: longer footage is analytics-only at launch

# local backend states that mean a human must act in the local operator UI
_HUMAN_WAIT = {"calibration_pending", "calibrated", "tagging_pending"}

_GENERIC_FAIL = ("Something went wrong while processing this match. "
                 "Please try again.")


def map_local_status(status: dict) -> dict:
    """Translate a backend /status payload into a cloud jobs-row patch.

    'ready' is returned as a bare marker — the caller must deliver outputs
    BEFORE writing state='ready' to the cloud (crash-safety rule).
    """
    state = status["state"]
    if state in _HUMAN_WAIT:
        return {"state": "operator_action",
                "state_detail": "Waiting for studio review",
                "progress": status.get("progress") or 0}
    if state == "ready":
        return {"state": "ready"}
    if state == "failed":
        return {"state": "failed",
                "error_message": status.get("error") or _GENERIC_FAIL}
    return {"state": "processing",
            "state_detail": status.get("stage_label") or "Processing",
            "progress": status.get("progress") or 0}


def decide_deliverables(duration_sec, requested):
    """Apply the launch-scope rule to the REAL probed duration.

    Returns (deliverables, note_or_None), or None when the video is unreadable
    (caller fails the job).
    """
    if duration_sec is None:
        return None
    if duration_sec > SEGMENT_MAX_MIN * 60 and requested != ["coach_analytics"]:
        return (["coach_analytics"],
                "Your footage runs over 20 minutes, so we prepared coach "
                "analytics only.")
    return (list(requested), None)


def plan_delivery(requested, output_paths):
    """Map the backend's raw outputs listing to user-facing Drive uploads.

    Returns [(rel_path, drive_folder_label, file_name)] containing ONLY files
    the user should see, organised per requested deliverable.
    """
    plan = []
    for rel in output_paths:
        p = rel.replace("\\", "/")
        parts = p.split("/")
        name = parts[-1]
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ("coach_analytics" in requested and len(parts) >= 4
                and parts[0] == "deliverables" and parts[2] == "coach"
                and ext != "json"):
            plan.append((rel, "Coach analytics", name))
        elif ("event_highlights" in requested and ext == "mp4"
              and (parts[0] == "event_highlights"
                   or (parts[0] == "events" and "clips" in parts))):
            plan.append((rel, "Event highlights", name))
        elif ("player_highlights" in requested and ext == "mp4"
              and parts[0] == "player_highlights" and "reels" in parts):
            plan.append((rel, "Player highlights", name))
    return plan


def should_promote(free_bytes: int, threshold: int) -> bool:
    """Promote the oldest quota_waiting job once Drive has real headroom."""
    return free_bytes > threshold
