from backend import worker
from backend.jobs import JobStore


def _make_queued_job(store, deliverables):
    cfg = store.create(sport="football", match_name="x", match_date="2026-05-31")
    store.update_config(cfg.job_id, deliverables_requested=deliverables)
    store.write_status(cfg.job_id, state="queued", stage=None, progress=0,
                       stage_label="Waiting in line", error=None)
    return cfg.job_id


def test_run_one_completes_analytics_job_to_ready(tmp_path):
    store = JobStore(tmp_path)
    jid = _make_queued_job(store, ["coach_analytics"])
    w = worker.Worker(store)
    w.run_one()
    from backend import db
    row = db.get_job(store.conn, jid)
    assert row["state"] == "ready"
    assert row["progress"] == 100
    assert (store.job_dir(jid) / "outputs" / "analytics.stub.txt").exists()


def test_run_one_parks_player_highlights_at_tagging(tmp_path):
    store = JobStore(tmp_path)
    jid = _make_queued_job(store, ["player_highlights"])
    w = worker.Worker(store)
    w.run_one()
    from backend import db
    row = db.get_job(store.conn, jid)
    assert row["state"] == "tagging_pending"


def test_run_one_resumes_after_tagging(tmp_path):
    store = JobStore(tmp_path)
    jid = _make_queued_job(store, ["player_highlights"])
    w = worker.Worker(store)
    w.run_one()  # parks at tagging_pending
    # simulate tags submitted: flip back to queued
    store.write_status(jid, state="queued", stage="tagging_done", progress=50,
                       stage_label="Names received", error=None)
    w.run_one()  # resumes
    from backend import db
    row = db.get_job(store.conn, jid)
    assert row["state"] == "ready"
    assert (store.job_dir(jid) / "outputs" / "player_highlights.stub.txt").exists()


def test_run_one_no_queued_job_is_noop(tmp_path):
    store = JobStore(tmp_path)
    w = worker.Worker(store)
    assert w.run_one() is False  # nothing to do
