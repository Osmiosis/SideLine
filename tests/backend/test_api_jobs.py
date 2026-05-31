def test_create_job_returns_id(client):
    r = client.post("/api/jobs", json={
        "sport": "football", "match_name": "A vs B", "match_date": "2026-05-31"})
    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body and len(body["job_id"]) > 0


def test_create_job_rejects_bad_sport(client):
    r = client.post("/api/jobs", json={
        "sport": "cricket", "match_name": "x", "match_date": "2026-05-31"})
    assert r.status_code == 422


def test_status_after_create_is_created(client):
    jid = client.post("/api/jobs", json={
        "sport": "football", "match_name": "x",
        "match_date": "2026-05-31"}).json()["job_id"]
    r = client.get(f"/api/jobs/{jid}/status")
    assert r.status_code == 200
    assert r.json()["state"] == "created"


def test_status_unknown_job_is_404(client):
    r = client.get("/api/jobs/doesnotexist/status")
    assert r.status_code == 404


def test_list_jobs_returns_created_job(client):
    client.post("/api/jobs", json={
        "sport": "basketball", "match_name": "Finals",
        "match_date": "2026-05-31"})
    r = client.get("/api/jobs")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["match_name"] == "Finals"
    assert items[0]["state"] == "created"
