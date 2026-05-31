def _new_job(client):
    return client.post("/api/jobs", json={
        "sport": "football", "match_name": "x",
        "match_date": "2026-05-31"}).json()["job_id"]


def test_outputs_empty_initially(client):
    jid = _new_job(client)
    r = client.get(f"/api/jobs/{jid}/outputs")
    assert r.status_code == 200
    assert r.json() == []


def test_outputs_list_and_download(client):
    jid = _new_job(client)
    out_dir = client.app.state.store.job_dir(jid) / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.pdf").write_bytes(b"%PDF-1.4 fake")
    listing = client.get(f"/api/jobs/{jid}/outputs").json()
    assert "report.pdf" in listing
    dl = client.get(f"/api/jobs/{jid}/outputs/report.pdf")
    assert dl.status_code == 200
    assert dl.content == b"%PDF-1.4 fake"


def test_download_path_traversal_blocked(client):
    jid = _new_job(client)
    r = client.get(f"/api/jobs/{jid}/outputs/..%2f..%2fjobs.sqlite3")
    assert r.status_code in (400, 404)


def test_root_serves_frontend(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
