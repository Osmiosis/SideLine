"""Supabase access for the agent (service role; the ONLY place it is used
PC-side). Plain PostgREST + GoTrue admin endpoints via requests."""
import requests

from agent.config import settings

_H = {"apikey": settings.service_key,
      "Authorization": f"Bearer {settings.service_key}",
      "Content-Type": "application/json"}


def _rest(path: str) -> str:
    return f"{settings.supabase_url}/rest/v1/{path}"


def jobs_in_state(state: str) -> list[dict]:
    """All jobs in `state`, oldest first (FIFO fairness)."""
    r = requests.get(_rest(f"jobs?state=eq.{state}&order=created_at.asc"),
                     headers=_H, timeout=30)
    r.raise_for_status()
    return r.json()


def get_job(job_id: str) -> dict | None:
    r = requests.get(_rest(f"jobs?id=eq.{job_id}"), headers=_H, timeout=30)
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def update_job(job_id: str, **fields) -> None:
    r = requests.patch(_rest(f"jobs?id=eq.{job_id}"), headers=_H, json=fields,
                       timeout=30)
    r.raise_for_status()


def user_email(user_id: str) -> str | None:
    r = requests.get(f"{settings.supabase_url}/auth/v1/admin/users/{user_id}",
                     headers=_H, timeout=30)
    if not r.ok:
        return None
    return r.json().get("email")
