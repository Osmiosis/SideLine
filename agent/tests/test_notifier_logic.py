from agent.notifier_logic import detect_news


def test_first_pass_reports_existing_jobs_once():
    jobs = [{"id": "a", "state": "submitted", "match_name": "M1"},
            {"id": "b", "state": "uploaded", "match_name": "M2"}]
    news, seen = detect_news(set(), jobs)
    assert [(n["kind"], n["job"]["id"]) for n in news] == [
        ("approval", "a"), ("footage", "b")]
    news2, _ = detect_news(seen, jobs)
    assert news2 == []  # no repeats


def test_state_change_renotifies_same_job():
    jobs = [{"id": "a", "state": "submitted", "match_name": "M1"}]
    _, seen = detect_news(set(), jobs)
    jobs[0]["state"] = "uploaded"
    news, _ = detect_news(seen, jobs)
    assert [(n["kind"], n["job"]["id"]) for n in news] == [("footage", "a")]


def test_other_states_are_ignored():
    jobs = [{"id": "a", "state": "processing", "match_name": "M1"}]
    news, _ = detect_news(set(), jobs)
    assert news == []
