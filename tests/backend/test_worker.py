from backend import worker, pipeline
from backend.jobs import JobStore


def _make_queued_job(store, deliverables):
    cfg = store.create(sport="football", match_name="x", match_date="2026-05-31")
    store.update_config(cfg.job_id, deliverables_requested=deliverables)
    store.write_status(cfg.job_id, state="queued", stage=None, progress=0,
                       stage_label="Waiting in line", error=None)
    return cfg.job_id


def test_run_one_completes_football_job(tmp_path, monkeypatch):
    store = JobStore(tmp_path)
    cfg = store.create(sport="football", match_name="x", match_date="2026-05-31")
    store.update_config(cfg.job_id, deliverables_requested=["coach_analytics"])
    store.write_status(cfg.job_id, state="queued", stage=None, progress=0,
                       stage_label=None, error=None)
    monkeypatch.setattr(pipeline, "run_step", lambda step, ctx, logs: None)
    worker.Worker(store).run_one()
    from backend import db
    assert db.get_job(store.conn, cfg.job_id)["state"] == "ready"


def test_run_one_marks_failed_with_friendly_error(tmp_path, monkeypatch):
    store = JobStore(tmp_path)
    jid = _make_queued_job(store, ["coach_analytics"])

    def _boom(step, ctx, logs):
        raise RuntimeError("internal traceback detail that must not leak")

    monkeypatch.setattr(pipeline, "run_step", _boom)
    worker.Worker(store).run_one()

    from backend import db
    row = db.get_job(store.conn, jid)
    assert row["state"] == "failed"
    assert row["error"]  # friendly message present
    assert "traceback" not in row["error"].lower()
    assert "RuntimeError" not in (row["error"] or "")
    # technical detail is logged server-side only
    logs = list((store.job_dir(jid) / "logs").glob("*.log"))
    assert logs and "internal traceback detail" in logs[0].read_text(encoding="utf-8")


def test_run_one_no_queued_job_is_noop(tmp_path):
    store = JobStore(tmp_path)
    w = worker.Worker(store)
    assert w.run_one() is False  # nothing to do
