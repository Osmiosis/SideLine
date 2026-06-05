"""Admin approve/reject via the decide function. Email sends are best-effort
(skipped when RESEND_API_KEY is unset) so tests don't depend on Resend."""
import requests

from conftest import ADMIN_HEADERS, FUNCTIONS_URL, rest, user_headers


def make_job(user_id: str, state: str = "submitted") -> str:
    r = requests.post(rest("jobs"), headers={**ADMIN_HEADERS,
                      "Content-Type": "application/json",
                      "Prefer": "return=representation"},
                      json={"user_id": user_id, "sport": "basketball",
                            "match_name": "decide test",
                            "declared_duration_min": 10,
                            "deliverables": ["coach_analytics"], "state": state})
    assert r.status_code == 201, r.text
    return r.json()[0]["id"]


def make_admin(user_id: str):
    r = requests.post(rest("app_admins"), headers={**ADMIN_HEADERS,
                      "Content-Type": "application/json"}, json={"user_id": user_id})
    assert r.status_code in (200, 201), r.text


def get_state(job_id: str) -> dict:
    return requests.get(rest(f"jobs?id=eq.{job_id}"), headers=ADMIN_HEADERS).json()[0]


def test_admin_approves(two_users):
    make_admin(two_users["b_id"])          # B is the operator
    job_id = make_job(two_users["a_id"])   # A submitted
    r = requests.post(f"{FUNCTIONS_URL}/decide",
                      headers=user_headers(two_users["b_tok"]),
                      json={"job_id": job_id, "action": "approve"})
    assert r.status_code == 200, r.text
    assert get_state(job_id)["state"] == "approved"


def test_admin_rejects_with_reason(two_users):
    make_admin(two_users["b_id"])
    job_id = make_job(two_users["a_id"])
    r = requests.post(f"{FUNCTIONS_URL}/decide",
                      headers=user_headers(two_users["b_tok"]),
                      json={"job_id": job_id, "action": "reject",
                            "reason": "Footage is not from a fixed camera."})
    assert r.status_code == 200, r.text
    job = get_state(job_id)
    assert job["state"] == "rejected"
    assert job["reject_reason"] == "Footage is not from a fixed camera."


def test_non_admin_cannot_decide(two_users):
    job_id = make_job(two_users["a_id"])
    r = requests.post(f"{FUNCTIONS_URL}/decide",
                      headers=user_headers(two_users["a_tok"]),  # A is not admin
                      json={"job_id": job_id, "action": "approve"})
    assert r.status_code == 403, r.text
    assert get_state(job_id)["state"] == "submitted"


def test_approve_only_from_valid_states(two_users):
    make_admin(two_users["b_id"])
    job_id = make_job(two_users["a_id"], state="ready")
    r = requests.post(f"{FUNCTIONS_URL}/decide",
                      headers=user_headers(two_users["b_tok"]),
                      json={"job_id": job_id, "action": "approve"})
    assert r.status_code == 409, r.text
