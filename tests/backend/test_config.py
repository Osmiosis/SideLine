from backend import config


def test_sports_are_football_and_basketball():
    assert config.SPORTS == ("football", "basketball")


def test_deliverable_stage_lists_exist_for_each_deliverable():
    for d in ("coach_analytics", "event_highlights", "player_highlights"):
        assert d in config.DELIVERABLE_STAGES
        assert isinstance(config.DELIVERABLE_STAGES[d], tuple)
        assert len(config.DELIVERABLE_STAGES[d]) >= 1


def test_foundation_stages_are_shared_prefix():
    assert config.FOUNDATION_STAGES == (
        "decoding", "detecting", "tracking", "teams", "ball",
    )


def test_jobs_dir_is_under_repo_root():
    assert config.JOBS_DIR.name == "jobs"
    assert config.WEBSITE_DIR.name == "Website"
