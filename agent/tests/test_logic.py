"""Pure decision logic: no network, no disk."""
from agent.logic import (decide_deliverables, map_local_status, plan_delivery,
                         should_promote)


def test_human_wait_states_become_operator_action():
    for s in ("calibration_pending", "calibrated", "tagging_pending"):
        patch = map_local_status({"state": s, "progress": 0, "stage_label": None,
                                  "error": None})
        assert patch == {"state": "operator_action",
                         "state_detail": "Waiting for studio review", "progress": 0}


def test_pipeline_states_become_processing_with_stage_label():
    patch = map_local_status({"state": "tracking", "progress": 40,
                              "stage_label": "Following players", "error": None})
    assert patch == {"state": "processing",
                     "state_detail": "Following players", "progress": 40}


def test_queued_is_processing_too():
    patch = map_local_status({"state": "queued", "progress": 0,
                              "stage_label": "Waiting in line", "error": None})
    assert patch["state"] == "processing"


def test_ready_and_failed_are_terminal_markers():
    assert map_local_status({"state": "ready", "progress": 100,
                             "stage_label": "Ready", "error": None}) == {"state": "ready"}
    patch = map_local_status({"state": "failed", "progress": 0, "stage_label": None,
                              "error": "We couldn't read the video."})
    assert patch == {"state": "failed",
                     "error_message": "We couldn't read the video."}


def test_failed_without_message_gets_generic_copy():
    patch = map_local_status({"state": "failed", "progress": 0,
                              "stage_label": None, "error": None})
    assert "went wrong" in patch["error_message"]


def test_overlong_footage_downgrades_to_analytics_only():
    dl, note = decide_deliverables(25 * 60.0, ["coach_analytics", "event_highlights"])
    assert dl == ["coach_analytics"]
    assert "20 minutes" in note


def test_segment_keeps_requested_deliverables():
    dl, note = decide_deliverables(10 * 60.0, ["event_highlights"])
    assert dl == ["event_highlights"]
    assert note is None


def test_long_footage_already_analytics_only_passes_quietly():
    dl, note = decide_deliverables(90 * 60.0, ["coach_analytics"])
    assert dl == ["coach_analytics"]
    assert note is None


def test_unreadable_video_returns_none():
    assert decide_deliverables(None, ["coach_analytics"]) is None


REAL_OUTPUTS = [
    "ball_track/L1/possession.json",
    "deliverables/L1/coach/coach_analysis.pdf",
    "deliverables/L1/coach/fig_heatmap_A.png",
    "deliverables/L1/coach/tactical_sample.mp4",
    "deliverables/L1/coach/metrics.json",
    "deliverables/L1/distances.json",
    "det_cache/ball/L1.txt",
    "events/L1/clips/07_likely_goal_candidate_55s.mp4",
    "event_highlights/auto_draft_reel.mp4",
    "event_highlights/index.json",
    "player_highlights/L1/clips/c001.mp4",
    "player_highlights/L1/reels/player_07.mp4",
]


def test_plan_delivery_routes_files_to_named_folders():
    plan = plan_delivery(
        ["coach_analytics", "event_highlights", "player_highlights"], REAL_OUTPUTS)
    assert ("deliverables/L1/coach/coach_analysis.pdf",
            "Coach analytics", "coach_analysis.pdf") in plan
    assert ("events/L1/clips/07_likely_goal_candidate_55s.mp4",
            "Event highlights", "07_likely_goal_candidate_55s.mp4") in plan
    assert ("event_highlights/auto_draft_reel.mp4",
            "Event highlights", "auto_draft_reel.mp4") in plan
    assert ("player_highlights/L1/reels/player_07.mp4",
            "Player highlights", "player_07.mp4") in plan


def test_plan_delivery_excludes_internal_files():
    plan = plan_delivery(
        ["coach_analytics", "event_highlights", "player_highlights"], REAL_OUTPUTS)
    shipped = [rel for rel, _, _ in plan]
    for internal in ("ball_track/L1/possession.json", "det_cache/ball/L1.txt",
                     "deliverables/L1/coach/metrics.json",
                     "deliverables/L1/distances.json",
                     "event_highlights/index.json",
                     "player_highlights/L1/clips/c001.mp4"):
        assert internal not in shipped


def test_plan_delivery_respects_requested_deliverables():
    plan = plan_delivery(["coach_analytics"], REAL_OUTPUTS)
    assert {sub for _, sub, _ in plan} == {"Coach analytics"}


def test_should_promote_needs_headroom():
    assert should_promote(free_bytes=4 * 1024 ** 3, threshold=3 * 1024 ** 3) is True
    assert should_promote(free_bytes=2 * 1024 ** 3, threshold=3 * 1024 ** 3) is False
