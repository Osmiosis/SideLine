from backend import db, pipeline, worker
from backend.jobs import JobStore


def _queued_ph_job(store):
    cfg = store.create(sport="football", match_name="x", match_date="2026-06-01")
    store.update_config(cfg.job_id, deliverables_requested=["player_highlights"])
    store.write_status(cfg.job_id, state="queued", stage=None, progress=0,
                       stage_label=None, error=None)
    return cfg.job_id


def test_parks_at_tagging_pending(tmp_path, monkeypatch):
    store = JobStore(tmp_path); jid = _queued_ph_job(store)
    ran = []
    monkeypatch.setattr(pipeline, "run_step", lambda step, ctx, logs: ran.append(step.key))
    worker.Worker(store).run_one()
    row = db.get_job(store.conn, jid)
    assert row["state"] == "tagging_pending"
    assert "reels" not in ran            # reels not run before tagging
    assert "involvement" in ran          # part-1 ran


def test_resume_runs_only_reels(tmp_path, monkeypatch):
    store = JobStore(tmp_path); jid = _queued_ph_job(store)
    monkeypatch.setattr(pipeline, "run_step", lambda step, ctx, logs: None)
    w = worker.Worker(store); w.run_one()                 # parks
    # simulate /tags: re-enqueue with the resume sentinel
    store.write_status(jid, state="queued", stage="tagging_done", progress=50,
                       stage_label=None, error=None)
    ran = []
    monkeypatch.setattr(pipeline, "run_step", lambda step, ctx, logs: ran.append(step.key))
    w.run_one()                                            # resumes
    row = db.get_job(store.conn, jid)
    assert row["state"] == "ready"
    assert ran == ["reels"]              # ONLY reels re-ran (foundation skipped)
