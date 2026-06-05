"""Eyes-on demo of the Plan 1 Drive relay. Creates a throwaway user + job,
approves it, mints a resumable session URI, uploads a small file through it,
and completes the job — then LEAVES the file in Drive so you can see it.

Run:    .venv\\Scripts\\python agent\\demo_drive_relay.py
Verify: drive.google.com (operator account) -> "SportsAI Submissions" folder.
Clean up afterwards by deleting the demo folder in Drive (trash frees quota).
"""
import os
import sys
import uuid

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "supabase", "tests", ".env"))

URL = os.environ["SUPABASE_URL"]
ANON = os.environ["SUPABASE_ANON_KEY"]
SERVICE = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
FUNCTIONS_URL = os.environ.get("FUNCTIONS_URL", f"{URL}/functions/v1")
ADMIN = {"apikey": SERVICE, "Authorization": f"Bearer {SERVICE}",
         "Content-Type": "application/json", "Prefer": "return=representation"}


def main() -> None:
    tag = uuid.uuid4().hex[:8]
    email, password = f"demo-{tag}@example.com", "demo-password-123!"

    # 1. throwaway user signs up + signs in
    r = requests.post(f"{URL}/auth/v1/admin/users", headers=ADMIN,
                      json={"email": email, "password": password, "email_confirm": True})
    r.raise_for_status()
    user_id = r.json()["id"]
    r = requests.post(f"{URL}/auth/v1/token?grant_type=password",
                      headers={"apikey": ANON}, json={"email": email, "password": password})
    r.raise_for_status()
    token = r.json()["access_token"]
    user = {"apikey": ANON, "Authorization": f"Bearer {token}",
            "Content-Type": "application/json", "Prefer": "return=representation"}
    print(f"1. user created + signed in: {email}")

    # 2. user submits a job; operator approves it (service role stands in)
    r = requests.post(f"{URL}/rest/v1/jobs", headers=user,
                      json={"user_id": user_id, "sport": "football",
                            "match_name": f"Demo match {tag}",
                            "declared_duration_min": 10,
                            "deliverables": ["coach_analytics"]})
    r.raise_for_status()
    job_id = r.json()[0]["id"]
    requests.patch(f"{URL}/rest/v1/jobs?id=eq.{job_id}", headers=ADMIN,
                   json={"state": "approved"}).raise_for_status()
    print(f"2. job submitted + approved: {job_id}")

    # 3. mint a resumable session URI (the user never sees Google credentials)
    payload = b"SportsAI drive relay demo " * 1024  # ~26 KB
    r = requests.post(f"{FUNCTIONS_URL}/mint-upload", headers=user,
                      json={"job_id": job_id, "file_size": len(payload),
                            "mime_type": "text/plain"})
    r.raise_for_status()
    session_uri = r.json()["session_uri"]
    print("3. session URI minted (starts:", session_uri[:60] + "...)")

    # 4. upload straight to Google — note: NO auth header on this request
    r = requests.put(session_uri, data=payload,
                     headers={"Content-Length": str(len(payload))})
    r.raise_for_status()
    file_id = r.json()["id"]
    print(f"4. {len(payload)} bytes uploaded directly to Drive, file id {file_id}")

    # 5. complete the job
    r = requests.post(f"{FUNCTIONS_URL}/complete-upload", headers=user,
                      json={"job_id": job_id, "drive_file_id": file_id})
    r.raise_for_status()
    state = requests.get(f"{URL}/rest/v1/jobs?id=eq.{job_id}&select=state,drive_folder_id",
                         headers=ADMIN).json()[0]
    print(f"5. job state: {state['state']}")
    print(f"\nDone. Open drive.google.com (operator account) -> 'SportsAI Submissions'")
    print(f"-> folder ending _{job_id[:8]} -> raw_video.mp4 ({len(payload)} bytes).")
    print("Delete that folder in Drive when you're done looking.")

    # leave the Drive file; remove the throwaway auth user + job row
    requests.delete(f"{URL}/rest/v1/jobs?id=eq.{job_id}", headers=ADMIN)
    requests.delete(f"{URL}/auth/v1/admin/users/{user_id}", headers=ADMIN)


if __name__ == "__main__":
    sys.exit(main())
