"""Shared helpers for cloud integration tests. Talks to the REAL Supabase project."""
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

URL = os.environ["SUPABASE_URL"]
ANON = os.environ["SUPABASE_ANON_KEY"]
SERVICE = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
FUNCTIONS_URL = os.environ.get("FUNCTIONS_URL", f"{URL}/functions/v1")

ADMIN_HEADERS = {"apikey": SERVICE, "Authorization": f"Bearer {SERVICE}"}


def create_user(email: str, password: str) -> str:
    """Create a confirmed user via the GoTrue admin API. Returns user id."""
    r = requests.post(
        f"{URL}/auth/v1/admin/users",
        headers=ADMIN_HEADERS,
        json={"email": email, "password": password, "email_confirm": True},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def sign_in(email: str, password: str) -> str:
    """Password grant (tests only; the site uses magic links). Returns access token."""
    r = requests.post(
        f"{URL}/auth/v1/token?grant_type=password",
        headers={"apikey": ANON},
        json={"email": email, "password": password},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def delete_user(user_id: str) -> None:
    requests.delete(f"{URL}/auth/v1/admin/users/{user_id}", headers=ADMIN_HEADERS)


def user_headers(token: str) -> dict:
    return {"apikey": ANON, "Authorization": f"Bearer {token}",
            "Content-Type": "application/json", "Prefer": "return=representation"}


def rest(path: str) -> str:
    return f"{URL}/rest/v1/{path}"


@pytest.fixture()
def two_users():
    """Two throwaway confirmed users; cleaned up (and their jobs) after the test."""
    tag = uuid.uuid4().hex[:8]
    a_email, b_email = f"test-a-{tag}@example.com", f"test-b-{tag}@example.com"
    a_id = create_user(a_email, "test-password-123!")
    b_id = create_user(b_email, "test-password-123!")
    a_tok = sign_in(a_email, "test-password-123!")
    b_tok = sign_in(b_email, "test-password-123!")
    yield {"a_id": a_id, "b_id": b_id, "a_tok": a_tok, "b_tok": b_tok,
           "a_email": a_email, "b_email": b_email}
    for uid in (a_id, b_id):
        requests.delete(rest(f"jobs?user_id=eq.{uid}"), headers=ADMIN_HEADERS)
        requests.delete(rest(f"app_admins?user_id=eq.{uid}"), headers=ADMIN_HEADERS)
        delete_user(uid)
