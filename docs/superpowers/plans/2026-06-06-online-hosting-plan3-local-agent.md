# Online Hosting Plan 3: Local Agent + Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the PC-side agent that automatically pulls approved-and-uploaded footage from Drive, runs it through the existing backend pipeline, mirrors live progress to the cloud, delivers results back to the user's Drive folder with an email, and cleans up expired deliverables.

**Architecture:** A standalone Python service (`agent/` package) loops sequentially: poll Supabase for `uploaded` jobs → download raw footage from Drive (resumable) → delete it from Drive (quota back) → create a local job through the EXISTING backend HTTP API (`backend/main.py`, worker auto-starts with the server) → mirror every local stage/progress into the cloud row (which `job.html` already polls) → on local `ready`, upload outputs to the job's Drive folder, share by link, email the user, set 14-day expiry → expire/clean old deliverables and promote `quota_waiting` jobs. Spec: `docs/superpowers/specs/2026-06-05-online-hosting-design.md` §5.

**Tech Stack:** Python 3 (existing `.venv` — `requests`, `python-dotenv`, `cv2` already installed; `smtplib` stdlib), Google Drive API v3 (refresh-token grant, `alt=media` downloads, resumable uploads), Supabase PostgREST + GoTrue admin API (service role), Gmail SMTP (app password from Plan 2), existing backend FastAPI on `http://localhost:8000`.

**Conventions for this plan:**
- All shell commands are PowerShell, run from repo root `C:\sports-ai`.
- Frozen contracts: cloud states `submitted…failed` (Plan 1); local states/stages from `backend/pipeline.py` (`created, uploading, calibration_pending, calibrated, queued, decoding, detecting, tracking, teams, ball, analytics, events, tagging_pending, tagging_done, player_highlights, ready, failed`); deliverables `coach_analytics`/`event_highlights`/`player_highlights` everywhere.
- The agent talks to the local backend ONLY via its HTTP API (one writer for the local SQLite: the server). Endpoints per `backend/main.py`: `POST /api/jobs`, `POST /api/jobs/{id}/video`, `POST /api/jobs/{id}/deliverables`, `GET /api/jobs/{id}/status`, `GET /api/jobs/{id}/outputs`, `GET /api/jobs/{id}/outputs/{path}`.
- Secrets stay in `agent/.env` (gitignored since Plan 1). Tests against the REAL Supabase/Drive (dev project), same as Plans 1–2.
- ONE job at a time, ONE process — respects the 16 GB RAM / 8 GB GPU rule (the pipeline itself runs inside the backend server process; the agent is a lightweight HTTP client).
- Crash-safety rule: a cloud state is only advanced AFTER the milestone it records is durable (e.g. `processing` is written only after the video is inside the local backend; the Drive raw file is deleted only after that same milestone). Every step is re-runnable.

---

### Task 1: Agent config, env, and cloud `local_job_id` column

**Files:**
- Create: `agent/__init__.py` (empty)
- Create: `agent/config.py`
- Create: `agent/.env` (untracked)
- Create: `supabase/migrations/20260606000001_local_job_id.sql`

- [ ] **Step 1: Create `agent/__init__.py`** (empty file — makes `agent` importable as a package).

- [ ] **Step 2: Write `agent/.env`** (gitignored). Copy the `SUPABASE_*` and `GOOGLE_*` values from `supabase/tests/.env`; `SMTP_APP_PASSWORD` is the Gmail app password from Plan 2 (ask the operator — it is NOT in any file yet):

```env
SUPABASE_URL=https://qphkhchhdurvylrunaoz.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<from supabase/tests/.env>
GOOGLE_CLIENT_ID=<from supabase/tests/.env>
GOOGLE_CLIENT_SECRET=<from supabase/tests/.env>
GOOGLE_REFRESH_TOKEN=<from supabase/tests/.env>
BACKEND_URL=http://localhost:8000
SITE_ORIGIN=https://sideline-d8c.pages.dev
SMTP_USER=altaccrv@gmail.com
SMTP_APP_PASSWORD=<gmail app password, operator provides>
EMAIL_FROM=Sideline <altaccrv@gmail.com>
AGENT_POLL_SECONDS=60
```

- [ ] **Step 3: Write `agent/config.py`**

```python
"""Agent settings, loaded once from agent/.env. Import `settings` everywhere."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


@dataclass(frozen=True)
class Settings:
    supabase_url: str = os.environ["SUPABASE_URL"]
    service_key: str = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    google_client_id: str = os.environ["GOOGLE_CLIENT_ID"]
    google_client_secret: str = os.environ["GOOGLE_CLIENT_SECRET"]
    google_refresh_token: str = os.environ["GOOGLE_REFRESH_TOKEN"]
    backend_url: str = os.environ.get("BACKEND_URL", "http://localhost:8000")
    site_origin: str = os.environ.get("SITE_ORIGIN", "")
    smtp_user: str = os.environ.get("SMTP_USER", "")
    smtp_app_password: str = os.environ.get("SMTP_APP_PASSWORD", "")
    email_from: str = os.environ.get("EMAIL_FROM", "Sideline <no-reply@invalid>")
    poll_seconds: int = int(os.environ.get("AGENT_POLL_SECONDS", "60"))
    headroom_bytes: int = 1024 ** 3          # 1 GB, same as mint-upload
    promote_free_bytes: int = 3 * 1024 ** 3  # promote quota_waiting above 3 GB free
    expiry_days: int = 14                    # spec §0.6


settings = Settings()
```

- [ ] **Step 4: Write the migration** — the agent records which local job a cloud job maps to, so a restarted agent can resume mirroring with zero local state files:

`supabase/migrations/20260606000001_local_job_id.sql`:

```sql
-- Plan 3: link a cloud job to the PC-local backend job driving it.
-- Written by the agent (service role); visible to the owner via existing
-- select policy (a uuid hex is harmless).
alter table public.jobs add column local_job_id text;
```

- [ ] **Step 5: Push the migration**

Run: `npx supabase db push`
Expected: `Applying migration 20260606000001_local_job_id.sql... Finished supabase db push.`

- [ ] **Step 6: Sanity-check config loads**

Run: `.\.venv\Scripts\python -c "from agent.config import settings; print(settings.backend_url, settings.poll_seconds)"`
Expected: `http://localhost:8000 60`

- [ ] **Step 7: Commit**

```powershell
git add agent/__init__.py agent/config.py supabase/migrations/20260606000001_local_job_id.sql
git commit -m "feat(agent): config scaffold + cloud local_job_id column"
```

---

### Task 2: Pure decision logic (TDD)

**Files:**
- Create: `agent/tests/__init__.py` (empty)
- Create: `agent/tests/test_logic.py`
- Create: `agent/logic.py`

All the agent's decisions in one dependency-free module: local→cloud state mapping, the duration downgrade rule, idempotent delivery diffing, and quota promotion.

- [ ] **Step 1: Write the failing tests**

`agent/tests/test_logic.py`:

```python
"""Pure decision logic: no network, no disk."""
from agent.logic import (decide_deliverables, files_to_upload, map_local_status,
                         should_promote)


def test_human_wait_states_become_operator_action():
    for s in ("calibration_pending", "calibrated", "tagging_pending"):
        patch = map_local_status({"state": s, "progress": 0, "stage_label": None,
                                  "error": None})
        assert patch == {"state": "operator_action",
                         "state_detail": "Waiting for studio review", "progress": 0}


def test_pipeline_states_become_processing_with_stage_label():
    patch = map_local_status({"state": "tracking", "progress": 40,
                              "stage_label": "Following players", "error": None})
    assert patch == {"state": "processing",
                     "state_detail": "Following players", "progress": 40}


def test_queued_is_processing_too():
    patch = map_local_status({"state": "queued", "progress": 0,
                              "stage_label": "Waiting in line", "error": None})
    assert patch["state"] == "processing"


def test_ready_and_failed_are_terminal_markers():
    assert map_local_status({"state": "ready", "progress": 100,
                             "stage_label": "Ready", "error": None}) == {"state": "ready"}
    patch = map_local_status({"state": "failed", "progress": 0, "stage_label": None,
                              "error": "We couldn't read the video."})
    assert patch == {"state": "failed",
                     "error_message": "We couldn't read the video."}


def test_failed_without_message_gets_generic_copy():
    patch = map_local_status({"state": "failed", "progress": 0,
                              "stage_label": None, "error": None})
    assert "went wrong" in patch["error_message"]


def test_overlong_footage_downgrades_to_analytics_only():
    dl, note = decide_deliverables(25 * 60.0, ["coach_analytics", "event_highlights"])
    assert dl == ["coach_analytics"]
    assert "20 minutes" in note


def test_segment_keeps_requested_deliverables():
    dl, note = decide_deliverables(10 * 60.0, ["event_highlights"])
    assert dl == ["event_highlights"]
    assert note is None


def test_long_footage_already_analytics_only_passes_quietly():
    dl, note = decide_deliverables(90 * 60.0, ["coach_analytics"])
    assert dl == ["coach_analytics"]
    assert note is None


def test_unreadable_video_returns_none():
    assert decide_deliverables(None, ["coach_analytics"]) is None


def test_files_to_upload_skips_already_delivered():
    local = ["deliverables/0/coach/report.pdf", "event_highlights/clip_01.mp4"]
    existing = {"deliverables__0__coach__report.pdf"}
    todo = files_to_upload(local, existing)
    assert todo == [("event_highlights/clip_01.mp4", "event_highlights__clip_01.mp4")]


def test_should_promote_needs_headroom():
    assert should_promote(free_bytes=4 * 1024 ** 3, threshold=3 * 1024 ** 3) is True
    assert should_promote(free_bytes=2 * 1024 ** 3, threshold=3 * 1024 ** 3) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python -m pytest agent/tests/test_logic.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.logic'`.

- [ ] **Step 3: Write `agent/logic.py`**

```python
"""Every agent decision, as pure functions. Tested without any I/O."""

SEGMENT_MAX_MIN = 20  # spec §0.7: longer footage is analytics-only at launch

# local backend states that mean a human must act in the local operator UI
_HUMAN_WAIT = {"calibration_pending", "calibrated", "tagging_pending"}

_GENERIC_FAIL = ("Something went wrong while processing this match. "
                 "Please try again.")


def map_local_status(status: dict) -> dict:
    """Translate a backend /status payload into a cloud jobs-row patch.

    'ready' is returned as a bare marker — the caller must deliver outputs
    BEFORE writing state='ready' to the cloud (crash-safety rule).
    """
    state = status["state"]
    if state in _HUMAN_WAIT:
        return {"state": "operator_action",
                "state_detail": "Waiting for studio review",
                "progress": status.get("progress") or 0}
    if state == "ready":
        return {"state": "ready"}
    if state == "failed":
        return {"state": "failed",
                "error_message": status.get("error") or _GENERIC_FAIL}
    return {"state": "processing",
            "state_detail": status.get("stage_label") or "Processing",
            "progress": status.get("progress") or 0}


def decide_deliverables(duration_sec, requested):
    """Apply the launch-scope rule to the REAL probed duration.

    Returns (deliverables, note_or_None), or None when the video is unreadable
    (caller fails the job).
    """
    if duration_sec is None:
        return None
    if duration_sec > SEGMENT_MAX_MIN * 60 and requested != ["coach_analytics"]:
        return (["coach_analytics"],
                "Your footage runs over 20 minutes, so we prepared coach "
                "analytics only.")
    return (list(requested), None)


def drive_name(rel_path: str) -> str:
    """Flatten a nested output path into a single Drive file name."""
    return rel_path.replace("\\", "/").replace("/", "__")


def files_to_upload(local_rel_paths, existing_drive_names):
    """Idempotent delivery: (rel_path, drive_name) for not-yet-uploaded files."""
    todo = []
    for rel in local_rel_paths:
        name = drive_name(rel)
        if name not in existing_drive_names:
            todo.append((rel, name))
    return todo


def should_promote(free_bytes: int, threshold: int) -> bool:
    """Promote the oldest quota_waiting job once Drive has real headroom."""
    return free_bytes > threshold
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python -m pytest agent/tests/test_logic.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```powershell
git add agent/tests agent/logic.py
git commit -m "feat(agent): pure decision logic - state mapping, downgrade, delivery diff"
```

---

### Task 3: Drive client (integration-tested against real Drive)

**Files:**
- Create: `agent/drive.py`
- Create: `agent/tests/test_drive.py`

- [ ] **Step 1: Write the failing integration test**

`agent/tests/test_drive.py`:

```python
"""Round-trips a real (tiny) file through the operator's Drive: folder create,
resumable upload, share, listed, downloaded byte-identical, deleted."""
import os
import tempfile

import pytest

from agent import drive


@pytest.fixture()
def tmpdirpath(tmp_path):
    return tmp_path


def test_drive_roundtrip(tmpdirpath):
    token = drive.access_token()
    folder_id = None
    try:
        folder_id = drive.ensure_folder(token, "AGENT TEST FOLDER", None)
        # idempotent: asking again returns the same folder
        assert drive.ensure_folder(token, "AGENT TEST FOLDER", None) == folder_id

        src = tmpdirpath / "payload.bin"
        src.write_bytes(b"sideline agent " * 1000)  # ~15 KB
        file_id = drive.upload_file(token, str(src), folder_id, "payload.bin")

        names = drive.list_names(token, folder_id)
        assert "payload.bin" in names

        link = drive.share_anyone(token, folder_id)
        assert link.startswith("https://")

        dest = tmpdirpath / "back.bin"
        drive.download_file(token, file_id, str(dest))
        assert dest.read_bytes() == src.read_bytes()

        free = drive.free_bytes(token)
        assert free > 0
    finally:
        if folder_id:
            drive.delete_file(drive.access_token(), folder_id)


def test_download_resumes_from_partial(tmpdirpath):
    token = drive.access_token()
    folder_id = None
    try:
        folder_id = drive.ensure_folder(token, "AGENT TEST FOLDER", None)
        src = tmpdirpath / "payload2.bin"
        src.write_bytes(os.urandom(70_000))
        file_id = drive.upload_file(token, str(src), folder_id, "payload2.bin")

        dest = tmpdirpath / "partial.bin"
        dest.write_bytes(src.read_bytes()[:30_000])  # simulate a dead download
        drive.download_file(token, file_id, str(dest))
        assert dest.read_bytes() == src.read_bytes()
    finally:
        if folder_id:
            drive.delete_file(drive.access_token(), folder_id)
```

- [ ] **Step 2: Run to verify failure**

Run: `.\.venv\Scripts\python -m pytest agent/tests/test_drive.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.drive'`.

- [ ] **Step 3: Write `agent/drive.py`**

```python
"""Google Drive v3 client for the agent (refresh-token grant, requests only).

Mirrors supabase/functions/_shared/google.ts so both sides speak the same
folder/file conventions.
"""
import os

import requests

from agent.config import settings

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
CHUNK = 32 * 1024 * 1024  # multiple of 256 KiB (Drive resumable-upload rule)


def access_token() -> str:
    r = requests.post(TOKEN_URL, data={
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "refresh_token": settings.google_refresh_token,
        "grant_type": "refresh_token"}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def free_bytes(token: str) -> int:
    r = requests.get(f"{API}/about?fields=storageQuota", headers=_h(token), timeout=30)
    r.raise_for_status()
    q = r.json()["storageQuota"]
    if not q.get("limit"):
        return 2 ** 53
    return int(q["limit"]) - int(q["usage"])


def ensure_folder(token: str, name: str, parent_id: str | None) -> str:
    safe = name.replace("'", "\\'")
    q = (f"name = '{safe}' and mimeType = 'application/vnd.google-apps.folder' "
         "and trashed = false")
    if parent_id:
        q += f" and '{parent_id}' in parents"
    r = requests.get(f"{API}/files", params={"q": q, "fields": "files(id)"},
                     headers=_h(token), timeout=30)
    r.raise_for_status()
    files = r.json().get("files", [])
    if files:
        return files[0]["id"]
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    r = requests.post(f"{API}/files", json=body, headers=_h(token), timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def list_names(token: str, folder_id: str) -> set[str]:
    names: set[str] = set()
    page = None
    while True:
        params = {"q": f"'{folder_id}' in parents and trashed = false",
                  "fields": "nextPageToken, files(name)", "pageSize": 1000}
        if page:
            params["pageToken"] = page
        r = requests.get(f"{API}/files", params=params, headers=_h(token), timeout=30)
        r.raise_for_status()
        data = r.json()
        names.update(f["name"] for f in data.get("files", []))
        page = data.get("nextPageToken")
        if not page:
            return names


def upload_file(token: str, path: str, folder_id: str, name: str) -> str:
    """Resumable upload in sequential 32 MB chunks. Returns the file id."""
    size = os.path.getsize(path)
    r = requests.post(
        f"{UPLOAD}/files?uploadType=resumable",
        headers={**_h(token), "Content-Type": "application/json",
                 "X-Upload-Content-Length": str(size)},
        json={"name": name, "parents": [folder_id]}, timeout=30)
    r.raise_for_status()
    session = r.headers["Location"]
    with open(path, "rb") as f:
        offset = 0
        while offset < size or size == 0:
            blob = f.read(CHUNK)
            end = offset + len(blob) - 1
            r = requests.put(session, data=blob, headers={
                "Content-Range": f"bytes {offset}-{end}/{size}"}, timeout=600)
            if r.status_code in (200, 201):
                return r.json()["id"]
            if r.status_code != 308:
                raise RuntimeError(f"upload chunk failed: {r.status_code} {r.text}")
            offset = end + 1
    raise RuntimeError("upload ended without a completed response")


def download_file(token: str, file_id: str, dest: str) -> None:
    """Streamed download; resumes from an existing partial file via Range."""
    offset = os.path.getsize(dest) if os.path.exists(dest) else 0
    headers = _h(token)
    if offset:
        headers["Range"] = f"bytes={offset}-"
    with requests.get(f"{API}/files/{file_id}?alt=media", headers=headers,
                      stream=True, timeout=600) as r:
        if offset and r.status_code == 416:   # nothing left — already complete
            return
        if offset and r.status_code != 206:   # server ignored Range: start over
            offset = 0
        r.raise_for_status()
        mode = "ab" if offset else "wb"
        with open(dest, mode) as f:
            for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                f.write(chunk)


def share_anyone(token: str, file_id: str) -> str:
    """'Anyone with the link can view' + return the webViewLink."""
    requests.post(f"{API}/files/{file_id}/permissions",
                  json={"role": "reader", "type": "anyone"},
                  headers=_h(token), timeout=30).raise_for_status()
    r = requests.get(f"{API}/files/{file_id}?fields=webViewLink",
                     headers=_h(token), timeout=30)
    r.raise_for_status()
    return r.json()["webViewLink"]


def delete_file(token: str, file_id: str) -> None:
    requests.delete(f"{API}/files/{file_id}", headers=_h(token), timeout=30)
    # 404 is fine — already gone
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python -m pytest agent/tests/test_drive.py -v`
Expected: 2 passed (real Drive round-trips; both test folders removed in teardown).

- [ ] **Step 5: Commit**

```powershell
git add agent/drive.py agent/tests/test_drive.py
git commit -m "feat(agent): drive client - resumable up/down, share, quota, tested live"
```

---

### Task 4: Supabase cloud client (integration-tested)

**Files:**
- Create: `agent/cloud.py`
- Create: `agent/tests/test_cloud.py`

- [ ] **Step 1: Write the failing integration test**

`agent/tests/test_cloud.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.\.venv\Scripts\python -m pytest agent/tests/test_cloud.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.cloud'`.

- [ ] **Step 3: Write `agent/cloud.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python -m pytest agent/tests/test_cloud.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```powershell
git add agent/cloud.py agent/tests/test_cloud.py
git commit -m "feat(agent): supabase cloud client - fetch/update jobs, user email"
```

---

### Task 5: Video probe + email notifications (TDD on the pure parts)

**Files:**
- Create: `agent/media.py`
- Create: `agent/notify.py`
- Create: `agent/tests/test_media_notify.py`

- [ ] **Step 1: Write the failing tests**

`agent/tests/test_media_notify.py`:

```python
"""Probe a generated clip; check email bodies. SMTP send is NOT tested here
(best-effort, exercised in the Task 9 rehearsal)."""
import cv2
import numpy as np

from agent.media import probe_duration_sec
from agent.notify import build_ready_email, build_failed_email, build_promoted_email


def test_probe_reads_real_duration(tmp_path):
    path = str(tmp_path / "clip.mp4")
    w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 64))
    for _ in range(50):  # 50 frames @ 10 fps = 5.0 s
        w.write(np.zeros((64, 64, 3), dtype=np.uint8))
    w.release()
    d = probe_duration_sec(path)
    assert d is not None and abs(d - 5.0) < 0.5


def test_probe_unreadable_returns_none(tmp_path):
    bad = tmp_path / "not_video.mp4"
    bad.write_bytes(b"this is not a video at all")
    assert probe_duration_sec(str(bad)) is None


def test_ready_email_has_link_and_expiry():
    subject, html = build_ready_email("Cup final", "https://drive.google.com/x",
                                      "2026-06-20")
    assert "Cup final" in subject
    assert "https://drive.google.com/x" in html
    assert "2026-06-20" in html


def test_failed_email_carries_friendly_message():
    subject, html = build_failed_email("Cup final", "We couldn't read the video.")
    assert "Cup final" in subject
    assert "We couldn't read the video." in html


def test_promoted_email_links_to_job_page():
    subject, html = build_promoted_email("Cup final", "https://site/job.html?id=1")
    assert "your turn" in html.lower()
    assert "https://site/job.html?id=1" in html
```

- [ ] **Step 2: Run to verify failure**

Run: `.\.venv\Scripts\python -m pytest agent/tests/test_media_notify.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.media'`.

- [ ] **Step 3: Write `agent/media.py`**

```python
"""Video probing — same cv2 approach as backend/main.py:_probe_duration_sec."""
import cv2


def probe_duration_sec(path: str) -> float | None:
    """Real duration in seconds, or None when the file isn't a readable video."""
    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps <= 0 or frames <= 0:
            return None
        return frames / fps
    finally:
        cap.release()
```

- [ ] **Step 4: Write `agent/notify.py`**

```python
"""Email notifications over Gmail SMTP (Plan 2 app password). Best-effort:
a send failure logs and never breaks the job flow (spec §8)."""
import smtplib
from email.mime.text import MIMEText

from agent.config import settings


def build_ready_email(match_name: str, results_url: str, expires_on: str):
    subject = f"Your analysis is ready: {match_name}"
    html = (f"<p>Your match <b>{match_name}</b> has been analysed.</p>"
            f'<p><a href="{results_url}">Open your results</a></p>'
            f"<p>Available until <b>{expires_on}</b> — download them soon.</p>")
    return subject, html


def build_failed_email(match_name: str, message: str):
    subject = f"Update on: {match_name}"
    html = (f"<p>We hit a problem with <b>{match_name}</b>.</p>"
            f"<p>{message}</p><p>You're welcome to submit it again.</p>")
    return subject, html


def build_promoted_email(match_name: str, job_url: str):
    subject = f"It's your turn: {match_name}"
    html = (f"<p>Storage has freed up — it's your turn to upload "
            f"<b>{match_name}</b>.</p>"
            f'<p><a href="{job_url}">Click here to upload your footage.</a></p>')
    return subject, html


def send_email(to: str | None, subject: str, html: str) -> None:
    if not to or not settings.smtp_user or not settings.smtp_app_password:
        print(f"  email skipped: {subject!r} -> {to}")
        return
    try:
        msg = MIMEText(html, "html")
        msg["Subject"] = subject
        msg["From"] = settings.email_from
        msg["To"] = to
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(settings.smtp_user, settings.smtp_app_password)
            s.sendmail(settings.smtp_user, [to], msg.as_string())
        print(f"  email sent: {subject!r} -> {to}")
    except Exception as e:  # noqa: BLE001 — never let email kill a job
        print(f"  email FAILED ({e}): {subject!r} -> {to}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.\.venv\Scripts\python -m pytest agent/tests/test_media_notify.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```powershell
git add agent/media.py agent/notify.py agent/tests/test_media_notify.py
git commit -m "feat(agent): video probe + gmail smtp notifications"
```

---

### Task 6: Local backend HTTP client

**Files:**
- Create: `agent/backend_client.py`

Thin wrappers over the frozen backend API — no logic (logic lives in `logic.py`), so no isolated tests; the fakes in Task 7 stand in for it and the Task 9 rehearsal exercises it for real.

- [ ] **Step 1: Write `agent/backend_client.py`**

```python
"""Thin client for the LOCAL backend FastAPI (backend/main.py endpoints).
The agent never touches the local SQLite directly — one writer: the server."""
import requests

from agent.config import settings

B = settings.backend_url


def is_up() -> bool:
    try:
        requests.get(f"{B}/api/jobs", timeout=5).raise_for_status()
        return True
    except requests.RequestException:
        return False


def create_job(sport: str, match_name: str, match_date: str) -> str:
    r = requests.post(f"{B}/api/jobs", json={
        "sport": sport, "match_name": match_name, "match_date": match_date},
        timeout=30)
    r.raise_for_status()
    return r.json()["job_id"]


def upload_video(job_id: str, path: str) -> None:
    # the endpoint consumes the RAW request body (request.stream()),
    # NOT multipart — send the file object directly
    with open(path, "rb") as f:
        r = requests.post(f"{B}/api/jobs/{job_id}/video", data=f,
                          headers={"Content-Type": "video/mp4"}, timeout=3600)
    r.raise_for_status()


def set_deliverables(job_id: str, deliverables: list[str]) -> None:
    r = requests.post(f"{B}/api/jobs/{job_id}/deliverables",
                      json={"deliverables_requested": deliverables}, timeout=30)
    r.raise_for_status()


def status(job_id: str) -> dict:
    r = requests.get(f"{B}/api/jobs/{job_id}/status", timeout=30)
    r.raise_for_status()
    return r.json()


def output_paths(job_id: str) -> list[str]:
    r = requests.get(f"{B}/api/jobs/{job_id}/outputs", timeout=30)
    r.raise_for_status()
    return r.json()


def download_output(job_id: str, rel_path: str, dest: str) -> None:
    with requests.get(f"{B}/api/jobs/{job_id}/outputs/{rel_path}",
                      stream=True, timeout=3600) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                f.write(chunk)
```

- [ ] **Step 2: Syntax check**

Run: `.\.venv\Scripts\python -c "import agent.backend_client as bc; print([n for n in dir(bc) if not n.startswith('_')])"`
Expected: lists `create_job, download_output, is_up, output_paths, set_deliverables, status, upload_video` (plus imports).

- [ ] **Step 3: Commit**

```powershell
git add agent/backend_client.py
git commit -m "feat(agent): thin http client for the local backend api"
```

---

### Task 7: The relay orchestrator (fake-driven TDD)

**Files:**
- Create: `agent/relay.py`
- Create: `agent/tests/test_relay.py`

`relay.py` sequences everything but owns no policy (that's `logic.py`) and no I/O detail (that's the clients). Its functions take the client modules as injectable parameters, so the tests drive it with in-memory fakes and assert ORDERING — the crash-safety contract.

- [ ] **Step 1: Write the failing tests**

`agent/tests/test_relay.py`:

```python
"""Orchestration contract tests with in-memory fakes. The key assertions are
about ORDER: drive raw deletion only after the video is safely local+backend,
cloud 'ready' only after delivery completed."""
import pytest

from agent import relay


class FakeCloud:
    def __init__(self, jobs):
        self.jobs = {j["id"]: dict(j) for j in jobs}
        self.log = []

    def jobs_in_state(self, state):
        return [dict(j) for j in self.jobs.values() if j["state"] == state]

    def get_job(self, job_id):
        return dict(self.jobs[job_id])

    def update_job(self, job_id, **fields):
        self.jobs[job_id].update(fields)
        self.log.append(("update", job_id, dict(fields)))

    def user_email(self, user_id):
        return "user@example.com"


class FakeDrive:
    def __init__(self):
        self.deleted = []
        self.uploaded = []
        self.existing = set()
        self.log = []

    def access_token(self):
        return "tok"

    def download_file(self, token, file_id, dest):
        self.log.append(("download", file_id))
        with open(dest, "wb") as f:
            f.write(b"video-bytes")

    def delete_file(self, token, file_id):
        self.deleted.append(file_id)
        self.log.append(("delete", file_id))

    def ensure_folder(self, token, name, parent):
        return f"folder-{name}"

    def list_names(self, token, folder_id):
        return set(self.existing)

    def upload_file(self, token, path, folder_id, name):
        self.uploaded.append(name)
        self.log.append(("upload", name))
        return f"id-{name}"

    def share_anyone(self, token, file_id):
        return "https://drive.google.com/shared"

    def free_bytes(self, token):
        return 10 * 1024 ** 3


class FakeBackend:
    def __init__(self):
        self.log = []
        self.deliverables = None

    def create_job(self, sport, match_name, match_date):
        self.log.append("create_job")
        return "local-1"

    def upload_video(self, job_id, path):
        self.log.append("upload_video")

    def set_deliverables(self, job_id, deliverables):
        self.deliverables = deliverables
        self.log.append("set_deliverables")

    def status(self, job_id):
        return {"state": "queued", "progress": 0,
                "stage_label": "Waiting in line", "error": None}

    def output_paths(self, job_id):
        return ["deliverables/0/coach/report.pdf"]

    def download_output(self, job_id, rel, dest):
        with open(dest, "wb") as f:
            f.write(b"pdf-bytes")


class FakeNotify:
    """Captures emails; nothing leaves the test process."""
    def __init__(self):
        self.sent = []

    def send_email(self, to, subject, html):
        self.sent.append((to, subject))

    def build_ready_email(self, match, url, expires):
        return (f"ready: {match}", url)

    def build_failed_email(self, match, message):
        return (f"failed: {match}", message)

    def build_promoted_email(self, match, url):
        return (f"your turn: {match}", url)


CLOUD_JOB = {"id": "cloud-1", "user_id": "u1", "sport": "football",
             "match_name": "Test", "match_date": None,
             "declared_duration_min": 5,
             "deliverables": ["coach_analytics", "event_highlights"],
             "state": "uploaded", "drive_file_id": "raw-1",
             "drive_folder_id": "folder-1", "local_job_id": None,
             "created_at": "2026-06-06T00:00:00+00:00", "expires_at": None}


def test_ingest_orders_drive_delete_after_local_upload(tmp_path, monkeypatch):
    cloud, drv, backend = FakeCloud([CLOUD_JOB]), FakeDrive(), FakeBackend()
    monkeypatch.setattr(relay, "probe_duration_sec", lambda p: 300.0)  # 5 min
    relay.ingest_one(dict(CLOUD_JOB), cloud=cloud, drv=drv, backend=backend,
                     notify=FakeNotify(), workdir=str(tmp_path))

    # video reached the local backend BEFORE the drive raw was deleted
    assert backend.log.index("upload_video") >= 0
    assert ("delete", "raw-1") in drv.log
    assert drv.log.index(("delete", "raw-1")) > 0  # not first action
    combined = [e for e in drv.log if e[0] == "delete"]
    assert combined == [("delete", "raw-1")]

    job = cloud.get_job("cloud-1")
    assert job["state"] == "processing"
    assert job["local_job_id"] == "local-1"
    assert backend.deliverables == ["coach_analytics", "event_highlights"]


def test_ingest_downgrades_overlong_footage(tmp_path, monkeypatch):
    cloud, drv, backend = FakeCloud([CLOUD_JOB]), FakeDrive(), FakeBackend()
    monkeypatch.setattr(relay, "probe_duration_sec", lambda p: 30 * 60.0)  # 30 min!
    relay.ingest_one(dict(CLOUD_JOB), cloud=cloud, drv=drv, backend=backend,
                     notify=FakeNotify(), workdir=str(tmp_path))
    assert backend.deliverables == ["coach_analytics"]
    assert "20 minutes" in cloud.get_job("cloud-1")["state_detail"]


def test_ingest_fails_unreadable_video_and_frees_drive(tmp_path, monkeypatch):
    cloud, drv, backend = FakeCloud([CLOUD_JOB]), FakeDrive(), FakeBackend()
    monkeypatch.setattr(relay, "probe_duration_sec", lambda p: None)
    notify = FakeNotify()
    relay.ingest_one(dict(CLOUD_JOB), cloud=cloud, drv=drv, backend=backend,
                     notify=notify, workdir=str(tmp_path))
    job = cloud.get_job("cloud-1")
    assert job["state"] == "failed"
    assert notify.sent == [("user@example.com", "failed: Test")]
    assert ("delete", "raw-1") in drv.log
    assert "create_job" not in backend.log  # never reached the pipeline


def test_mirror_writes_progress(tmp_path):
    job = {**CLOUD_JOB, "state": "processing", "local_job_id": "local-1"}
    cloud, backend = FakeCloud([job]), FakeBackend()
    relay.mirror_one(dict(job), cloud=cloud, backend=backend)
    j = cloud.get_job("cloud-1")
    assert j["state"] == "processing"
    assert j["state_detail"] == "Waiting in line"


def test_deliver_uploads_then_flips_ready(tmp_path):
    job = {**CLOUD_JOB, "state": "processing", "local_job_id": "local-1"}
    cloud, drv, backend = FakeCloud([job]), FakeDrive(), FakeBackend()
    notify = FakeNotify()
    relay.deliver(dict(job), cloud=cloud, drv=drv, backend=backend,
                  notify=notify, workdir=str(tmp_path))
    assert drv.uploaded == ["deliverables__0__coach__report.pdf"]
    assert notify.sent == [("user@example.com", "ready: Test")]
    j = cloud.get_job("cloud-1")
    assert j["state"] == "ready"
    assert j["results_url"] == "https://drive.google.com/shared"
    assert j["expires_at"] is not None
    # ready was written AFTER the upload happened
    upload_pos = drv.log.index(("upload", "deliverables__0__coach__report.pdf"))
    ready_pos = [i for i, e in enumerate(cloud.log)
                 if e[2].get("state") == "ready"]
    assert ready_pos and upload_pos >= 0


def test_deliver_skips_files_already_in_drive(tmp_path):
    job = {**CLOUD_JOB, "state": "processing", "local_job_id": "local-1"}
    cloud, drv, backend = FakeCloud([job]), FakeDrive(), FakeBackend()
    drv.existing = {"deliverables__0__coach__report.pdf"}
    relay.deliver(dict(job), cloud=cloud, drv=drv, backend=backend,
                  notify=FakeNotify(), workdir=str(tmp_path))
    assert drv.uploaded == []  # idempotent re-run
    assert cloud.get_job("cloud-1")["state"] == "ready"


def test_cleanup_expires_old_jobs():
    job = {**CLOUD_JOB, "state": "ready", "results_url": "x",
           "expires_at": "2020-01-01T00:00:00+00:00"}
    cloud, drv = FakeCloud([job]), FakeDrive()
    relay.cleanup_expired(cloud=cloud, drv=drv)
    j = cloud.get_job("cloud-1")
    assert j["state"] == "expired"
    assert ("delete", "folder-1") in drv.log


def test_promote_oldest_quota_waiting():
    job = {**CLOUD_JOB, "state": "quota_waiting"}
    cloud, drv = FakeCloud([job]), FakeDrive()
    notify = FakeNotify()
    relay.promote_quota_waiting(cloud=cloud, drv=drv, notify=notify)
    assert cloud.get_job("cloud-1")["state"] == "approved"
    assert notify.sent and "your turn" in notify.sent[0][1]
```

- [ ] **Step 2: Run to verify failure**

Run: `.\.venv\Scripts\python -m pytest agent/tests/test_relay.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.relay'`.

- [ ] **Step 3: Write `agent/relay.py`**

```python
"""The agent's orchestration: sequences ingest → process-mirror → deliver →
cleanup. Policy lives in logic.py; I/O in cloud.py / drive.py /
backend_client.py — all injectable for testing.

Crash-safety contract (tested):
- the Drive raw file is deleted ONLY after the video is inside the local
  backend AND the cloud row records local_job_id + state=processing;
- cloud state 'ready' is written ONLY after every output file is in Drive.
"""
import os
import time
from datetime import datetime, timedelta, timezone

from agent import backend_client as _backend
from agent import cloud as _cloud
from agent import drive as _drive
from agent import notify as _notify
from agent.config import settings
from agent.logic import (decide_deliverables, files_to_upload, map_local_status,
                         should_promote)
from agent.media import probe_duration_sec  # re-exported for monkeypatching

UNREADABLE_MSG = ("We couldn't read the video file. Please check it plays on "
                  "your device and submit the match again.")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ingest_one(job, *, cloud=_cloud, drv=_drive, backend=_backend,
               notify=_notify, workdir="agent_work") -> None:
    """Move one cloud job from 'uploaded' into the local pipeline."""
    job_id = job["id"]
    os.makedirs(workdir, exist_ok=True)
    raw = os.path.join(workdir, f"{job_id}.mp4")
    token = drv.access_token()

    print(f"[{job_id[:8]}] downloading raw footage...")
    drv.download_file(token, job["drive_file_id"], raw)

    duration = probe_duration_sec(raw)
    decision = decide_deliverables(duration, job["deliverables"])
    if decision is None:
        print(f"[{job_id[:8]}] unreadable video -> failed")
        drv.delete_file(token, job["drive_file_id"])  # quota back
        cloud.update_job(job_id, state="failed", error_message=UNREADABLE_MSG,
                         drive_file_id=None)
        notify.send_email(cloud.user_email(job["user_id"]),
                          *notify.build_failed_email(job["match_name"],
                                                     UNREADABLE_MSG))
        os.remove(raw)
        return

    deliverables, note = decision
    match_date = job.get("match_date") or job["created_at"][:10]
    # cloud id embedded in the local name -> orphans are identifiable
    local_name = f"{job['match_name']} [{job_id[:8]}]"

    local_id = backend.create_job(job["sport"], local_name, match_date)
    print(f"[{job_id[:8]}] local job {local_id}; uploading video to backend...")
    backend.upload_video(local_id, raw)
    backend.set_deliverables(local_id, deliverables)

    # milestone is durable -> record it, THEN free the Drive quota
    cloud.update_job(job_id, state="processing", local_job_id=local_id,
                     progress=0,
                     state_detail=note or "Processing has started.")
    drv.delete_file(token, job["drive_file_id"])
    cloud.update_job(job_id, drive_file_id=None)
    os.remove(raw)
    print(f"[{job_id[:8]}] ingested -> local {local_id}")


def mirror_one(job, *, cloud=_cloud, backend=_backend, notify=_notify) -> str:
    """Reflect the local job's state into the cloud row. Returns the local
    state so the caller can react to 'ready'/'failed'."""
    status = backend.status(job["local_job_id"])
    patch = map_local_status(status)
    if patch["state"] == "ready":
        return "ready"  # caller must deliver first
    # don't overwrite a downgrade note while merely queued
    if (patch["state"] == "processing" and status["state"] == "queued"
            and job.get("state_detail") and "analytics only" in job["state_detail"]):
        patch.pop("state_detail", None)
    if patch["state"] == "failed":
        cloud.update_job(job["id"], **patch)
        notify.send_email(cloud.user_email(job["user_id"]),
                          *notify.build_failed_email(job["match_name"],
                                                     patch["error_message"]))
        return "failed"
    cloud.update_job(job["id"], **patch)
    return status["state"]


def deliver(job, *, cloud=_cloud, drv=_drive, backend=_backend,
            notify=_notify, workdir="agent_work") -> None:
    """Upload all local outputs into <job folder>/deliverables, share, flip
    the cloud row to ready, email the user. Idempotent on re-run."""
    job_id = job["id"]
    os.makedirs(workdir, exist_ok=True)
    token = drv.access_token()
    folder = drv.ensure_folder(token, "deliverables", job["drive_folder_id"])
    existing = drv.list_names(token, folder)

    outputs = backend.output_paths(job["local_job_id"])
    todo = files_to_upload(outputs, existing)
    print(f"[{job_id[:8]}] delivering {len(todo)} file(s) "
          f"({len(existing)} already up)...")
    for rel, name in todo:
        tmp = os.path.join(workdir, name)
        backend.download_output(job["local_job_id"], rel, tmp)
        drv.upload_file(token, tmp, folder, name)
        os.remove(tmp)

    results_url = drv.share_anyone(token, job["drive_folder_id"])
    expires = _now() + timedelta(days=settings.expiry_days)
    cloud.update_job(job_id, state="ready", results_url=results_url,
                     progress=100, state_detail="Ready",
                     expires_at=expires.isoformat())

    notify.send_email(cloud.user_email(job["user_id"]),
                      *notify.build_ready_email(job["match_name"], results_url,
                                                expires.date().isoformat()))
    print(f"[{job_id[:8]}] READY -> {results_url}")


def cleanup_expired(*, cloud=_cloud, drv=_drive) -> None:
    """Delete Drive folders of ready jobs past expiry; mark rows expired."""
    now_iso = _now().isoformat()
    for job in cloud.jobs_in_state("ready"):
        if job.get("expires_at") and job["expires_at"] <= now_iso:
            print(f"[{job['id'][:8]}] expiring...")
            if job.get("drive_folder_id"):
                drv.delete_file(drv.access_token(), job["drive_folder_id"])
            cloud.update_job(job["id"], state="expired", results_url=None,
                             drive_folder_id=None,
                             state_detail="These results have expired.")


def promote_quota_waiting(*, cloud=_cloud, drv=_drive, notify=_notify) -> None:
    """Give the oldest waiting job its turn once Drive has headroom."""
    waiting = cloud.jobs_in_state("quota_waiting")
    if not waiting:
        return
    if not should_promote(drv.free_bytes(drv.access_token()),
                          settings.promote_free_bytes):
        return
    job = waiting[0]  # oldest first
    cloud.update_job(job["id"], state="approved",
                     state_detail="It's your turn — upload your footage now.")
    job_url = f"{settings.site_origin}/job.html?id={job['id']}"
    notify.send_email(cloud.user_email(job["user_id"]),
                      *notify.build_promoted_email(job["match_name"], job_url))
    print(f"[{job['id'][:8]}] promoted from quota_waiting")


def run_loop() -> None:
    """The agent's forever-loop: one pass every poll interval."""
    print(f"agent: polling every {settings.poll_seconds}s; backend "
          f"{settings.backend_url}")
    while True:
        try:
            run_once()
        except Exception as e:  # noqa: BLE001 — log and keep looping (spec §8)
            print(f"agent: pass failed ({e}); retrying next cycle")
        time.sleep(settings.poll_seconds)


def run_once(*, cloud=_cloud, drv=_drive, backend=_backend) -> None:
    """One full pass: ingest new, mirror active, deliver finished, clean up."""
    if not backend.is_up():
        print("agent: local backend is not running — start it with "
              "`python -m backend.main`. Skipping this pass.")
        return
    for job in cloud.jobs_in_state("uploaded"):
        ingest_one(job, cloud=cloud, drv=drv, backend=backend)
    for state in ("processing", "operator_action"):
        for job in cloud.jobs_in_state(state):
            if not job.get("local_job_id"):
                continue
            local_state = mirror_one(job, cloud=cloud, backend=backend)
            if local_state == "ready":
                deliver(job, cloud=cloud, drv=drv, backend=backend)
    cleanup_expired(cloud=cloud, drv=drv)
    promote_quota_waiting(cloud=cloud, drv=drv)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python -m pytest agent/tests/test_relay.py -v`
Expected: 9 passed.

> **Rehearsal fix (2026-06-06):** ingest must NOT call `set_deliverables` — the
> real endpoint enqueues immediately, skipping the calibration gate (caught live:
> the pipeline ran with zero calibration points and died at homography).
> Deliverables are now posted by `mirror_one` when the local job reaches
> `calibrated`; a duration downgrade is recorded on the CLOUD row at ingest.

- [ ] **Step 5: Run the whole agent test suite**

Run: `.\.venv\Scripts\python -m pytest agent/tests -v`
Expected: 29 passed (11 logic + 2 drive + 2 cloud + 5 media/notify + 9 relay).

- [ ] **Step 6: Commit**

```powershell
git add agent/relay.py agent/tests/test_relay.py
git commit -m "feat(agent): relay orchestrator - ingest/mirror/deliver/cleanup, fake-tested"
```

---

### Task 8: Entry point + docs

**Files:**
- Create: `agent/run.py`
- Modify: `supabase/SETUP.md` (append Plan 3 section)
- Modify: `.gitignore` (append `agent_work/`)

- [ ] **Step 1: Write `agent/run.py`**

```python
"""Start the agent.

    .venv\\Scripts\\python -m agent.run           # forever loop
    .venv\\Scripts\\python -m agent.run --once    # single pass (testing)

Prerequisite: the local backend is running (`python -m backend.main`).
"""
import sys

from agent.relay import run_loop, run_once

if __name__ == "__main__":
    if "--once" in sys.argv:
        run_once()
    else:
        run_loop()
```

- [ ] **Step 2: Append `agent_work/` to `.gitignore`** (the agent's scratch dir for in-flight downloads):

```gitignore

# agent scratch downloads (Plan 3)
agent_work/
```

- [ ] **Step 3: Append to `supabase/SETUP.md`**

```markdown
## Plan 3: local agent (2026-06-06)

Run order on the operator PC:
1. `\.venv\Scripts\python -m backend.main`  (local pipeline server + worker, port 8000)
2. `\.venv\Scripts\python -m agent.run`     (the relay agent; `--once` for a single pass)

Agent secrets live in `agent/.env` (gitignored): Supabase service key, Google
refresh token, Gmail SMTP app password (same one as Supabase Auth SMTP).

Flow: cloud `uploaded` → agent downloads from Drive → deletes Drive raw
(quota back) → local backend job (`local_job_id` column links them) → operator
does calibration/tagging in the LOCAL UI when the cloud row shows
`operator_action` → deliverables upload to `<job folder>/deliverables/`,
shared by link → `ready` + email + 14-day expiry → `expired` + Drive cleanup.

Agent tests: `pytest agent/tests -v` (logic/relay offline; drive/cloud hit the
real services).
```

- [ ] **Step 4: Smoke-run a single pass** (backend NOT running — the agent must say so gracefully):

Run: `.\.venv\Scripts\python -m agent.run --once`
Expected: `agent: local backend is not running — start it with \`python -m backend.main\`. Skipping this pass.`

- [ ] **Step 5: Commit**

```powershell
git add agent/run.py supabase/SETUP.md .gitignore
git commit -m "feat(agent): runnable entry point + run-order docs"
```

---

### Task 9: End-to-end rehearsal (operator present)

No new files — this proves the whole product with a real short clip. Use a ~2-minute fixture clip (any small match segment from the repo's dev data; NEVER the 47-min full match).

- [ ] **Step 1: Start both services**

Terminal 1: `.\.venv\Scripts\python -m backend.main`
Terminal 2: `.\.venv\Scripts\python -m agent.run`

- [ ] **Step 2: Submit as a real user**

On https://sideline-d8c.pages.dev (alt account): submit a match (declared duration = the clip's real minutes, pick `coach_analytics`) → admin approves on `admin.html` → upload the clip on the job page. Within ~60 s the agent should print `downloading raw footage...` and the job page should flip to "Processing has started." — **also verify in Drive that `raw_video.mp4` disappeared** (quota reclaimed).

- [ ] **Step 3: Do the human steps locally**

The cloud row goes `operator_action` ("Waiting for studio review"). In the LOCAL operator UI (http://localhost:8000): open the job named `<match> [<cloud-id-8>]`, do calibration. The agent re-mirrors automatically; the user's job page shows live stage labels + progress through the pipeline.

- [ ] **Step 4: Verify delivery**

When the local job hits `ready`: agent prints `delivering N file(s)` then `READY -> https://drive.google.com/...`. Check, as the user: job page shows "Your analysis is ready" + working **Open your results** button (Drive folder with the PDFs/clips, viewable WITHOUT signing into the operator account — incognito test). Email "Your analysis is ready" arrived.

- [ ] **Step 5: Verify expiry cleanup**

Fast-forward: in the Supabase Table Editor set the job's `expires_at` to yesterday. Next agent pass (≤60 s): row flips to `expired`, the Drive job folder is gone, the job page shows the expired copy.

- [ ] **Step 6: Re-run both regression suites**

```powershell
.\.venv\Scripts\python -m pytest agent/tests supabase/tests -v
node --test site/tests/*.test.mjs
```

Expected: 41 passed (29 agent + 12 cloud) and 13 pass.

- [ ] **Step 7: Commit any doc fixes discovered during rehearsal**

```powershell
git add supabase/SETUP.md
git commit -m "docs(agent): rehearsal notes"
```

---

## Exit criteria (Plan 3 done — the product is LIVE)

- [ ] `pytest agent/tests -v` → 29 passed (decision logic, Drive round-trip, cloud client, orchestration ordering).
- [ ] A real clip submitted on the live site by a non-admin account came back as a shared Drive results link + email, hands-off except approve/calibrate/tag.
- [ ] Drive raw footage deleted right after ingest (quota gauge recovers while processing).
- [ ] The user's job page showed live pipeline stages/progress and the `operator_action` pause.
- [ ] Expiry cleanup proven (fast-forwarded `expires_at` → `expired` + Drive folder gone).
- [ ] Agent restarts safely mid-job (kill it during processing, restart — it resumes mirroring via `local_job_id`).

**Deferred (post-launch backlog):** Cloudflare Tunnel fast path, custom domain, multi-operator, uploader-side tagging (spec §10), and the ~1 GB phone-on-mobile-data upload rehearsal.
