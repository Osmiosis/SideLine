"""Create (or update) the shared reviewer/demo account — email + password admin.

Hand this one login to reviewers so they can sign in on any device and see the
full product, including the admin views. You choose the password; it is read
from a prompt (no echo, not stored in shell history) or the SIDELINE_DEMO_PASSWORD
env var. This script never prints the password.

Usage:
    .venv\\Scripts\\python -m agent.create_demo_user demo@sideline.review
    # or non-interactive:
    set SIDELINE_DEMO_PASSWORD=... & .venv\\Scripts\\python -m agent.create_demo_user demo@sideline.review

What it does, against the live project (service-role):
  1. Creates the user with the password, email pre-confirmed (can sign in at once).
     If the user already exists, its password is reset to the one you enter.
  2. Adds the user to public.app_admins so it has full admin access.

To rotate the password later, just re-run it with a new one.
"""
import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from agent.config import settings


def _req(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    url = f"{settings.supabase_url}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "apikey": settings.service_key,
            "Authorization": f"Bearer {settings.service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode() or "{}"
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        return e.code, {"_error": e.read().decode(errors="replace")}
    except urllib.error.URLError as e:
        raise SystemExit(f"Could not reach Supabase ({e.reason}). Is the project awake?")


def find_user_id(email: str) -> str | None:
    status, body = _req("GET", f"/auth/v1/admin/users?email={urllib.parse.quote(email)}")
    if status == 200:
        users = body.get("users", body if isinstance(body, list) else [])
        for u in users:
            if (u.get("email") or "").lower() == email:
                return u.get("id")
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Create/update the shared demo admin account.")
    ap.add_argument("email", help="demo account email, e.g. demo@sideline.review")
    args = ap.parse_args(argv)
    email = args.email.strip().lower()

    password = os.environ.get("SIDELINE_DEMO_PASSWORD") or getpass.getpass("Choose a password for the demo account: ")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")

    existing = find_user_id(email)
    if existing:
        status, body = _req("PUT", f"/auth/v1/admin/users/{existing}",
                            {"password": password, "email_confirm": True})
        uid = existing
        action = "updated (password reset)"
    else:
        status, body = _req("POST", "/auth/v1/admin/users",
                            {"email": email, "password": password, "email_confirm": True})
        uid = body.get("id")
        action = "created"

    if not uid:
        raise SystemExit(f"Failed to create/update user: {body.get('_error', body)}")

    # Grant admin. Ignore duplicate-key (already an admin).
    status, body = _req("POST", "/rest/v1/app_admins", {"user_id": uid})
    if status not in (200, 201, 409) and "duplicate" not in json.dumps(body).lower():
        print(f"  ! warning: could not add to app_admins ({status}): {body.get('_error', body)}")
    admin_note = "admin access granted"

    print()
    print(f"  Demo account {action}: {email}")
    print(f"  {admin_note}.")
    print(f"  Share with reviewers: open {settings.site_origin or 'https://sideline-d8c.pages.dev'}")
    print(f"  Email: {email}   Password: (the one you just set)")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
