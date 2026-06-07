"""Service-role REST client against the real Supabase project."""
import uuid

import requests

from agent import cloud
from agent.config import settings

H = {"apikey": settings.service_key,
     "Authorization": f"Bearer {settings.service_key}",
     "Content-Type": "application/json", "Prefer": "return=representation"}


def _make_user_and_job():
    tag = uuid.uuid4().hex[:8]
    r = requests.post(f"{settings.supabase_url}/auth/v1/admin/users", headers=H,
                      json={"email": f"agent-test-{tag}@example.com",
                            "password": "agent-test-123!", "email_confirm": True})
    r.raise_for_status()
    uid = r.json()["id"]
    r = requests.post(f"{settings.supabase_url}/rest/v1/jobs", headers=H,
                      json={"user_id": uid, "sport": "football",
                            "match_name": f"agent cloud test {tag}",
                            "declared_duration_min": 5,
                            "deliverables": ["coach_analytics"],
                            "state": "uploaded"})
    r.raise_for_status()
    return uid, r.json()[0]["id"]


def _cleanup(uid):
    requests.delete(f"{settings.supabase_url}/rest/v1/jobs?user_id=eq.{uid}", headers=H)
    requests.delete(f"{settings.supabase_url}/auth/v1/admin/users/{uid}", headers=H)


def test_fetch_update_email_roundtrip():
    uid, job_id = _make_user_and_job()
    try:
        jobs = cloud.jobs_in_state("uploaded")
        assert any(j["id"] == job_id for j in jobs)

        cloud.update_job(job_id, state="processing", state_detail="Testing",
                         progress=42, local_job_id="abc123")
        job = cloud.get_job(job_id)
        assert job["state"] == "processing"
        assert job["progress"] == 42
        assert job["local_job_id"] == "abc123"

        email = cloud.user_email(uid)
        assert email.startswith("agent-test-")
    finally:
        _cleanup(uid)


def test_jobs_in_state_is_oldest_first():
    uid, _ = _make_user_and_job()
    try:
        jobs = cloud.jobs_in_state("uploaded")
        created = [j["created_at"] for j in jobs]
        assert created == sorted(created)
    finally:
        _cleanup(uid)
