"""RLS contract: users see/insert only their own jobs; nobody self-approves;
full matches are analytics-only (spec §0.7, §3)."""
import requests

from conftest import rest, user_headers, ADMIN_HEADERS


def submit_payload(user_id, duration=15, deliverables=None):
    return {
        "user_id": user_id,
        "sport": "football",
        "match_name": "RLS test match",
        "declared_duration_min": duration,
        "deliverables": deliverables or ["coach_analytics", "event_highlights"],
    }


def test_user_inserts_and_reads_own_job(two_users):
    r = requests.post(rest("jobs"), headers=user_headers(two_users["a_tok"]),
                      json=submit_payload(two_users["a_id"]))
    assert r.status_code == 201, r.text
    job = r.json()[0]
    assert job["state"] == "submitted"

    r = requests.get(rest("jobs?select=id"), headers=user_headers(two_users["a_tok"]))
    assert len(r.json()) == 1
    r = requests.get(rest("jobs?select=id"), headers=user_headers(two_users["b_tok"]))
    assert len(r.json()) == 0  # B cannot see A's job


def test_user_cannot_insert_for_someone_else(two_users):
    r = requests.post(rest("jobs"), headers=user_headers(two_users["b_tok"]),
                      json=submit_payload(two_users["a_id"]))  # B forging A's id
    assert r.status_code in (401, 403), r.text


def test_full_match_is_analytics_only(two_users):
    bad = submit_payload(two_users["a_id"], duration=90,
                         deliverables=["coach_analytics", "event_highlights"])
    r = requests.post(rest("jobs"), headers=user_headers(two_users["a_tok"]), json=bad)
    assert r.status_code in (400, 403), r.text  # CHECK constraint rejects it

    ok = submit_payload(two_users["a_id"], duration=90, deliverables=["coach_analytics"])
    r = requests.post(rest("jobs"), headers=user_headers(two_users["a_tok"]), json=ok)
    assert r.status_code == 201, r.text


def test_user_cannot_update_state(two_users):
    r = requests.post(rest("jobs"), headers=user_headers(two_users["a_tok"]),
                      json=submit_payload(two_users["a_id"]))
    job_id = r.json()[0]["id"]
    # attempt self-approval — no UPDATE policy exists, so this affects 0 rows
    requests.patch(rest(f"jobs?id=eq.{job_id}"),
                   headers=user_headers(two_users["a_tok"]), json={"state": "approved"})
    r = requests.get(rest(f"jobs?id=eq.{job_id}&select=state"), headers=ADMIN_HEADERS)
    assert r.json()[0]["state"] == "submitted"
