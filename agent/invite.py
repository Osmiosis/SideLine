"""Mint a one-time sign-in code for a reviewer — no email required.

This project runs on a $0 stack with no reliable transactional email, so the
operator hands out sign-in codes directly instead. This calls Supabase's admin
`generate_link` (service-role) to create the reviewer's account (if new) and
mint a one-time code, then prints a ready-to-send message. Share the code by
any channel; the reviewer enters their email + code at the site to sign in.

A typed code can't be consumed by link-preview/prefetch bots (unlike a magic
link), and the session persists after first sign-in, so each reviewer normally
needs one code per device.

Usage:
    .venv\\Scripts\\python -m agent.invite reviewer@example.com
    .venv\\Scripts\\python -m agent.invite reviewer@example.com --site https://sideline-d8c.pages.dev

The code expires in ~1 hour (Supabase OTP expiry). Re-run to mint a fresh one.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

from agent.config import settings

DEFAULT_SITE = settings.site_origin or "https://sideline-d8c.pages.dev"


def mint_code(email: str) -> dict:
    """Call admin generate_link; return the parsed properties (incl. email_otp)."""
    url = f"{settings.supabase_url}/auth/v1/admin/generate_link"
    body = json.dumps({"type": "magiclink", "email": email}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "apikey": settings.service_key,
            "Authorization": f"Bearer {settings.service_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise SystemExit(f"Supabase error {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Could not reach Supabase ({e.reason}). Is the project awake?")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mint a reviewer sign-in code (no email).")
    ap.add_argument("email", help="reviewer's email address")
    ap.add_argument("--site", default=DEFAULT_SITE, help="site URL to show in the message")
    args = ap.parse_args(argv)

    email = args.email.strip().lower()
    props = mint_code(email)
    code = props.get("email_otp")
    if not code:
        raise SystemExit(
            "generate_link succeeded but returned no code (email_otp). "
            "Check the Supabase GoTrue version / auth settings."
        )

    print()
    print(f"  Sign-in code for {email}:")
    print(f"      {code}")
    print()
    print("  Send the reviewer this (code expires in ~1 hour):")
    print("  " + "-" * 60)
    print(f"  Sign in to Sideline: open {args.site}")
    print(f"  Enter your email ({email}) and this code: {code}")
    print("  " + "-" * 60)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
