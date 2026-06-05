"""End-to-end proof of the Drive relay: mint a resumable session URI for an
approved job, PUT real bytes to it, confirm the file lands in the operator's
Drive, then (Task 6) complete-upload flips the job to 'uploaded'."""
import os

import requests

from conftest import (ADMIN_HEADERS, FUNCTIONS_URL, rest, user_headers)


def google_token() -> str:
    """Test-side Drive access (for cleanup/assertions), same refresh token."""
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"],
        "grant_type": "refresh_token"})
    r.raise_for_status()
    return r.json()["access_token"]


def make_approved_job(user_id: str) -> str:
    r = requests.post(rest("jobs"), headers={**ADMIN_HEADERS,
                      "Content-Type": "application/json",
                      "Prefer": "return=representation"},
                      json={"user_id": user_id, "sport": "football",
                            "match_name": "drive flow test",
                            "declared_duration_min": 10,
                            "deliverables": ["coach_analytics"],
                            "state": "approved"})
    assert r.status_code == 201, r.text
    return r.json()[0]["id"]


def drive_cleanup(folder_id: str | None):
    if folder_id:
        requests.delete(f"https://www.googleapis.com/drive/v3/files/{folder_id}",
                        headers={"Authorization": f"Bearer {google_token()}"})


def test_mint_and_upload_small_file(two_users):
    job_id = make_approved_job(two_users["a_id"])
    payload = b"\x00" * 4096  # content is irrelevant; Drive stores bytes
    folder_id = None
    try:
        # 1. mint: only the job owner, only on an approved job
        r = requests.post(f"{FUNCTIONS_URL}/mint-upload",
                          headers=user_headers(two_users["a_tok"]),
                          json={"job_id": job_id, "file_size": len(payload),
                                "mime_type": "video/mp4"})
        assert r.status_code == 200, r.text
        session_uri = r.json()["session_uri"]
        assert session_uri.startswith("https://")

        # job flipped to uploading + folder recorded
        job = requests.get(rest(f"jobs?id=eq.{job_id}"), headers=ADMIN_HEADERS).json()[0]
        assert job["state"] == "uploading"
        folder_id = job["drive_folder_id"]
        assert folder_id

        # 2. PUT the whole file to the session URI — NO auth header needed
        r = requests.put(session_uri, data=payload,
                         headers={"Content-Length": str(len(payload))})
        assert r.status_code in (200, 201), r.text
        file_id = r.json()["id"]

        # 3. the file really exists in the operator's Drive, inside the job folder
        f = requests.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}?fields=size,parents",
            headers={"Authorization": f"Bearer {google_token()}"}).json()
        assert int(f["size"]) == len(payload)
        assert folder_id in f["parents"]
    finally:
        drive_cleanup(folder_id)


def test_mint_refused_for_non_owner_and_wrong_state(two_users):
    job_id = make_approved_job(two_users["a_id"])
    # non-owner
    r = requests.post(f"{FUNCTIONS_URL}/mint-upload",
                      headers=user_headers(two_users["b_tok"]),
                      json={"job_id": job_id, "file_size": 1024})
    assert r.status_code == 404, r.text
    # wrong state
    requests.patch(rest(f"jobs?id=eq.{job_id}"), headers=ADMIN_HEADERS,
                   json={"state": "submitted"})
    r = requests.post(f"{FUNCTIONS_URL}/mint-upload",
                      headers=user_headers(two_users["a_tok"]),
                      json={"job_id": job_id, "file_size": 1024})
    assert r.status_code == 409, r.text
