from backend import db


def test_init_and_insert_and_get(tmp_path):
    conn = db.connect(tmp_path / "jobs.sqlite3")
    db.init_schema(conn)
    db.insert_job(conn, job_id="j1", sport="football",
                  match_name="A vs B", match_date="2026-05-31",
                  created_at="2026-05-31T00:00:00+00:00")
    row = db.get_job(conn, "j1")
    assert row["job_id"] == "j1"
    assert row["state"] == "created"
    assert row["progress"] == 0


def test_update_state_and_stage(tmp_path):
    conn = db.connect(tmp_path / "jobs.sqlite3")
    db.init_schema(conn)
    db.insert_job(conn, job_id="j1", sport="football",
                  match_name="A", match_date="2026-05-31",
                  created_at="2026-05-31T00:00:00+00:00")
    db.update_job(conn, "j1", state="tracking", stage="tracking", progress=40)
    row = db.get_job(conn, "j1")
    assert row["state"] == "tracking"
    assert row["stage"] == "tracking"
    assert row["progress"] == 40


def test_list_jobs_orders_newest_first(tmp_path):
    conn = db.connect(tmp_path / "jobs.sqlite3")
    db.init_schema(conn)
    db.insert_job(conn, job_id="old", sport="football", match_name="O",
                  match_date="2026-05-30", created_at="2026-05-30T00:00:00+00:00")
    db.insert_job(conn, job_id="new", sport="basketball", match_name="N",
                  match_date="2026-05-31", created_at="2026-05-31T00:00:00+00:00")
    ids = [r["job_id"] for r in db.list_jobs(conn)]
    assert ids == ["new", "old"]


def test_next_queued_returns_oldest_queued(tmp_path):
    conn = db.connect(tmp_path / "jobs.sqlite3")
    db.init_schema(conn)
    db.insert_job(conn, job_id="a", sport="football", match_name="A",
                  match_date="2026-05-31", created_at="2026-05-31T00:00:01+00:00")
    db.insert_job(conn, job_id="b", sport="football", match_name="B",
                  match_date="2026-05-31", created_at="2026-05-31T00:00:02+00:00")
    db.update_job(conn, "a", state="queued")
    db.update_job(conn, "b", state="queued")
    assert db.next_queued(conn)["job_id"] == "a"
