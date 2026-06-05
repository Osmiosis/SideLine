# Online Hosting Plan 1: Cloud Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the free cloud layer — Supabase (jobs table + RLS + magic-link auth + 4 Edge Functions) and Google Drive OAuth — proven end-to-end by uploading a real file into the operator's Drive through a minted resumable session URI.

**Architecture:** Supabase Postgres is the source of truth for job state; Deno Edge Functions hold the operator's Google refresh token as a secret and mint Drive resumable-upload session URIs so browsers upload multi-GB files directly to Google without ever seeing credentials. Spec: `docs/superpowers/specs/2026-06-05-online-hosting-design.md`.

**Tech Stack:** Supabase (Postgres, GoTrue auth, Deno Edge Functions, CLI via `npx supabase`), Google Drive API v3 (OAuth `drive.file` scope), Resend (email, optional in this plan), Python `pytest`+`requests` for integration tests (matches the repo's Python-centric tooling).

**Conventions for this plan:**
- All shell commands are PowerShell, run from repo root `C:\sports-ai`.
- Contract names are FROZEN: sports `football`/`basketball`; deliverables `coach_analytics`/`event_highlights`/`player_highlights`; job states `submitted, approved, quota_waiting, uploading, uploaded, processing, operator_action, ready, expired, rejected, failed` (spec §4).
- Tests run against the REAL Supabase project (it is a dev project until launch). No Docker / local Supabase stack required.
- Secrets NEVER enter git. Files `supabase/.env`, `supabase/tests/.env`, `agent/client_secret.json`, `agent/.env` are gitignored in Task 1.

---

### Task 1: Accounts, CLI, and repo scaffolding

**Files:**
- Create: `supabase/SETUP.md`
- Modify: `.gitignore` (append — READ it first; do not rewrite existing entries)

- [ ] **Step 1: Verify prerequisites**

Run: `node --version` (need ≥18; if missing, install LTS from nodejs.org) and `npx supabase --version` (downloads CLI on first use; any version ≥1.200 is fine).

- [ ] **Step 2: Manual account setup (operator does this in a browser, ~10 min)**

These cannot be automated; the executor pauses and asks the operator to complete them:
1. Create a free account at supabase.com → **New project** (name `sports-ai`, region closest to operator, generate a DB password and store it in a password manager).
2. From the project dashboard collect: **Project ref** (Settings → General), **Project URL**, **anon key**, **service_role key** (Settings → API).

- [ ] **Step 3: Initialize and link the Supabase repo scaffolding**

```powershell
npx supabase init           # creates supabase/config.toml
npx supabase link --project-ref <PROJECT_REF>   # prompts for the DB password
```

Expected: `Finished supabase link.`

- [ ] **Step 4: Append secret paths to .gitignore**

Read the existing `.gitignore` first (it has hand-maintained entries — do NOT rewrite it). Append this block at the end:

```gitignore
# online-hosting secrets (Plan 1)
supabase/.env
supabase/tests/.env
agent/.env
agent/client_secret.json
```

- [ ] **Step 5: Create the secrets env files (untracked)**

`supabase/.env` (function secrets — Google/Resend values filled in Task 4):

```env
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=
RESEND_API_KEY=
EMAIL_FROM=SportsAI <onboarding@resend.dev>
SITE_ORIGIN=http://localhost:8788
```

`supabase/tests/.env` (test credentials):

```env
SUPABASE_URL=https://<PROJECT_REF>.supabase.co
SUPABASE_ANON_KEY=<anon key>
SUPABASE_SERVICE_ROLE_KEY=<service_role key>
FUNCTIONS_URL=https://<PROJECT_REF>.supabase.co/functions/v1
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=
```

- [ ] **Step 6: Write `supabase/SETUP.md`**

A checklist doc recording: project ref, dashboard URLs, where each key lives (which env file / `supabase secrets`), and the manual steps from Step 2 and Task 4 so the setup is reproducible. No secret VALUES in this file — only locations.

- [ ] **Step 7: Enable magic-link auth**

In the Supabase dashboard → Authentication → Providers: Email provider ON, "Confirm email" ON (default). Magic links work out of the box on the free tier (rate-limited to ~3-4 emails/hour per address with the built-in sender — fine for dev; production sender comes with Resend in Plan 3). Record this in SETUP.md.

- [ ] **Step 8: Commit**

```powershell
git add supabase/config.toml supabase/SETUP.md .gitignore
git commit -m "chore(cloud): supabase scaffolding, setup checklist, secret gitignores"
```

---

### Task 2: Database schema + RLS migration (test-first)

**Files:**
- Create: `supabase/migrations/20260605000001_jobs.sql`
- Create: `supabase/tests/conftest.py`
- Create: `supabase/tests/test_rls.py`
- Create: `agent/requirements-agent.txt`

- [ ] **Step 1: Install test deps into the existing venv**

`agent/requirements-agent.txt`:

```text
requests>=2.31
python-dotenv>=1.0
pytest>=8.0
google-auth-oauthlib>=1.2
```

Run: `.\.venv\Scripts\pip install -r agent/requirements-agent.txt`

- [ ] **Step 2: Write the test helpers**

`supabase/tests/conftest.py`:

```python
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
```

- [ ] **Step 3: Write the failing RLS tests**

`supabase/tests/test_rls.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.\.venv\Scripts\python -m pytest supabase/tests/test_rls.py -v`
Expected: FAIL — PostgREST 404 `relation "public.jobs" does not exist` style errors (table missing).

- [ ] **Step 5: Write the migration**

`supabase/migrations/20260605000001_jobs.sql`:

```sql
-- Online hosting Plan 1: jobs table + admin registry + RLS (spec §3-4).

create table public.jobs (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users (id) on delete cascade,
  sport           text not null check (sport in ('football','basketball')),
  match_name      text not null check (char_length(match_name) between 1 and 120),
  match_date      date,
  declared_duration_min int not null check (declared_duration_min between 1 and 240),
  deliverables    text[] not null,
  state           text not null default 'submitted' check (state in
    ('submitted','approved','quota_waiting','uploading','uploaded','processing',
     'operator_action','ready','expired','rejected','failed')),
  state_detail    text,
  progress        int not null default 0 check (progress between 0 and 100),
  drive_folder_id text,
  drive_file_id   text,
  file_size_bytes bigint,
  results_url     text,
  error_message   text,
  reject_reason   text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  expires_at      timestamptz,
  -- contract: deliverable names are frozen
  constraint jobs_deliverables_valid check (
    deliverables <@ array['coach_analytics','event_highlights','player_highlights']::text[]
    and array_length(deliverables, 1) >= 1),
  -- spec §0.7: full matches (>20 min) are analytics-only at launch
  constraint jobs_fullmatch_analytics_only check (
    declared_duration_min <= 20 or deliverables = array['coach_analytics']::text[])
);

create table public.app_admins (
  user_id uuid primary key references auth.users (id) on delete cascade
);

create or replace function public.is_admin() returns boolean
language sql stable security invoker as
$$ select exists (select 1 from public.app_admins where user_id = auth.uid()) $$;

create or replace function public.touch_updated_at() returns trigger
language plpgsql as
$$ begin new.updated_at = now(); return new; end $$;

create trigger jobs_touch before update on public.jobs
  for each row execute function public.touch_updated_at();

alter table public.jobs enable row level security;
alter table public.app_admins enable row level security;

-- Users read their own jobs; the admin reads all.
create policy jobs_select on public.jobs for select
  using (auth.uid() = user_id or public.is_admin());

-- Users create jobs only for themselves, only in 'submitted'.
create policy jobs_insert on public.jobs for insert
  with check (auth.uid() = user_id and state = 'submitted');

-- NO update/delete policies: all state transitions go through Edge Functions
-- (service role) or the PC agent (service role). Spec §3.

-- Users may check whether THEY are an admin (drives the site's admin view).
create policy app_admins_select_self on public.app_admins for select
  using (auth.uid() = user_id);
```

- [ ] **Step 6: Push the migration**

Run: `npx supabase db push`
Expected: `Applying migration 20260605000001_jobs.sql... Finished supabase db push.`

- [ ] **Step 7: Run tests to verify they pass**

Run: `.\.venv\Scripts\python -m pytest supabase/tests/test_rls.py -v`
Expected: 4 passed.

- [ ] **Step 8: Commit**

```powershell
git add supabase/migrations supabase/tests/conftest.py supabase/tests/test_rls.py agent/requirements-agent.txt
git commit -m "feat(cloud): jobs schema with RLS + launch-scope constraints, tested"
```

---

### Task 3: Google OAuth bootstrap (refresh token in hand)

**Files:**
- Create: `agent/get_refresh_token.py`
- Modify: `supabase/SETUP.md` (append the Google steps)

- [ ] **Step 1: Manual Google Cloud setup (operator, ~10 min)**

1. console.cloud.google.com → New project `sports-ai-relay` (free, no billing needed).
2. APIs & Services → Library → enable **Google Drive API**.
3. OAuth consent screen → External → fill app name/email → **add no scopes here** → save.
4. **Publishing status → "In production"** (CRITICAL: in "Testing" status refresh tokens expire after 7 days; `drive.file` is a non-sensitive scope so production needs no verification review).
5. Credentials → Create credentials → OAuth client ID → **Desktop app** → download the JSON to `C:\sports-ai\agent\client_secret.json` (gitignored in Task 1).

- [ ] **Step 2: Write the bootstrap script**

`agent/get_refresh_token.py`:

```python
"""One-time: mint the operator's Google refresh token (drive.file scope)
and smoke-test it against the Drive API. Prints values to paste into env files.
Run: .venv\\Scripts\\python agent\\get_refresh_token.py
"""
import json
import pathlib

import requests
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CLIENT_SECRET = pathlib.Path(__file__).with_name("client_secret.json")


def main() -> None:
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    # access_type=offline + prompt=consent forces a refresh token to be issued
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    r = requests.get(
        "https://www.googleapis.com/drive/v3/about?fields=storageQuota,user",
        headers={"Authorization": f"Bearer {creds.token}"}, timeout=30)
    r.raise_for_status()
    about = r.json()
    quota = about["storageQuota"]
    free_gb = (int(quota["limit"]) - int(quota["usage"])) / 1024**3

    client = json.loads(CLIENT_SECRET.read_text())["installed"]
    print(f"\nDrive OK for {about['user']['emailAddress']} — {free_gb:.1f} GB free")
    print("\nPaste into supabase/.env AND supabase/tests/.env:")
    print(f"GOOGLE_CLIENT_ID={client['client_id']}")
    print(f"GOOGLE_CLIENT_SECRET={client['client_secret']}")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run it (opens a browser; operator consents once)**

Run: `.\.venv\Scripts\python agent\get_refresh_token.py`
Expected: `Drive OK for <operator email> — 13.x GB free` plus three env lines.

- [ ] **Step 4: Store the values**

Paste the three `GOOGLE_*` lines into `supabase/.env` and `supabase/tests/.env`. Append the manual steps + storage locations to `supabase/SETUP.md`.

- [ ] **Step 5: Commit**

```powershell
git add agent/get_refresh_token.py supabase/SETUP.md
git commit -m "feat(cloud): google oauth bootstrap script (drive.file refresh token)"
```

---

### Task 4: Shared Edge Function helpers

**Files:**
- Create: `supabase/functions/_shared/http.ts`
- Create: `supabase/functions/_shared/google.ts`
- Create: `supabase/functions/_shared/email.ts`
- Create: `supabase/functions/_shared/auth.ts`

These pure helpers are exercised by the integration tests in Tasks 5–8 (no isolated Deno unit tests — the risk lives in the Google/Supabase interactions, which only integration tests cover).

- [ ] **Step 1: Write `http.ts`**

```ts
export const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}
```

- [ ] **Step 2: Write `google.ts`**

```ts
// Drive API helpers. The refresh token is a function secret; access tokens
// are minted per-invocation (they live ~1h; functions are short-lived).
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const API = "https://www.googleapis.com/drive/v3";
const UPLOAD = "https://www.googleapis.com/upload/drive/v3";

export async function getAccessToken(): Promise<string> {
  const res = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: Deno.env.get("GOOGLE_CLIENT_ID")!,
      client_secret: Deno.env.get("GOOGLE_CLIENT_SECRET")!,
      refresh_token: Deno.env.get("GOOGLE_REFRESH_TOKEN")!,
      grant_type: "refresh_token",
    }),
  });
  if (!res.ok) throw new Error(`google token refresh failed: ${res.status}`);
  return (await res.json()).access_token;
}

export async function driveFreeBytes(token: string): Promise<number> {
  const res = await fetch(`${API}/about?fields=storageQuota`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`drive about failed: ${res.status}`);
  const { storageQuota } = await res.json();
  if (!storageQuota.limit) return Number.MAX_SAFE_INTEGER; // unlimited plan
  return Number(storageQuota.limit) - Number(storageQuota.usage);
}

export async function findOrCreateFolder(
  token: string, name: string, parentId: string | null,
): Promise<string> {
  const safe = name.replace(/'/g, "\\'");
  let q = `name = '${safe}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false`;
  if (parentId) q += ` and '${parentId}' in parents`;
  const list = await fetch(
    `${API}/files?q=${encodeURIComponent(q)}&fields=files(id)`,
    { headers: { Authorization: `Bearer ${token}` } },
  ).then((r) => r.json());
  if (list.files?.length) return list.files[0].id;

  const res = await fetch(`${API}/files`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      mimeType: "application/vnd.google-apps.folder",
      ...(parentId ? { parents: [parentId] } : {}),
    }),
  });
  if (!res.ok) throw new Error(`folder create failed: ${res.status}`);
  return (await res.json()).id;
}

export async function initResumableSession(
  token: string, fileName: string, folderId: string,
  fileSize: number, mimeType: string, origin: string,
): Promise<string> {
  // IMPORTANT: the Origin header set HERE binds CORS for the browser's
  // subsequent PUTs to the session URI. Without it, browser uploads fail.
  const res = await fetch(`${UPLOAD}/files?uploadType=resumable`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      "X-Upload-Content-Type": mimeType,
      "X-Upload-Content-Length": String(fileSize),
      Origin: origin,
    },
    body: JSON.stringify({ name: fileName, parents: [folderId] }),
  });
  const uri = res.headers.get("Location");
  if (!res.ok || !uri) throw new Error(`resumable init failed: ${res.status}`);
  return uri;
}

export async function getFile(
  token: string, fileId: string,
): Promise<{ id: string; name: string; size?: string; parents?: string[] } | null> {
  const res = await fetch(`${API}/files/${fileId}?fields=id,name,size,parents`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.ok ? await res.json() : null;
}

export async function deleteFile(token: string, fileId: string): Promise<void> {
  await fetch(`${API}/files/${fileId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  }); // 404s are fine (already gone)
}
```

- [ ] **Step 3: Write `email.ts`**

```ts
// Resend wrapper. Email is best-effort: missing key or send failure must
// never fail the request (spec §8) — it logs and moves on.
export async function sendEmail(
  to: string, subject: string, html: string,
): Promise<void> {
  const key = Deno.env.get("RESEND_API_KEY");
  if (!key) {
    console.warn(`email skipped (no RESEND_API_KEY): "${subject}" -> ${to}`);
    return;
  }
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: Deno.env.get("EMAIL_FROM") ?? "SportsAI <onboarding@resend.dev>",
      to: [to],
      subject,
      html,
    }),
  });
  if (!res.ok) console.error("email send failed:", res.status, await res.text());
}
```

- [ ] **Step 4: Write `auth.ts`**

```ts
import { createClient, SupabaseClient } from "npm:@supabase/supabase-js@2";

export function serviceClient(): SupabaseClient {
  return createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );
}

/** Resolve the calling user from the request's Authorization header. */
export async function getCaller(req: Request) {
  const anon = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_ANON_KEY")!,
    { global: { headers: { Authorization: req.headers.get("Authorization") ?? "" } } },
  );
  const { data: { user } } = await anon.auth.getUser();
  return user; // null when not signed in
}

export async function isAdmin(svc: SupabaseClient, userId: string): Promise<boolean> {
  const { data } = await svc.from("app_admins").select("user_id")
    .eq("user_id", userId).maybeSingle();
  return data !== null;
}
```

- [ ] **Step 5: Commit**

```powershell
git add supabase/functions/_shared
git commit -m "feat(cloud): shared edge function helpers (drive, email, auth, cors)"
```

---

### Task 5: `mint-upload` Edge Function (the core trick)

**Files:**
- Create: `supabase/functions/mint-upload/index.ts`
- Create: `supabase/tests/test_drive_flow.py` (first half)

- [ ] **Step 1: Write the failing integration test**

`supabase/tests/test_drive_flow.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.\.venv\Scripts\python -m pytest supabase/tests/test_drive_flow.py -v`
Expected: FAIL — 404 from `FUNCTIONS_URL/mint-upload` (function not deployed).

- [ ] **Step 3: Write the function**

`supabase/functions/mint-upload/index.ts`:

```ts
import { corsHeaders, json } from "../_shared/http.ts";
import { getCaller, serviceClient } from "../_shared/auth.ts";
import {
  driveFreeBytes, findOrCreateFolder, getAccessToken, initResumableSession,
} from "../_shared/google.ts";

const HEADROOM = 1024 ** 3; // keep 1 GB free after the upload (spec §2)
const ROOT_FOLDER = "SportsAI Submissions";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const user = await getCaller(req);
    if (!user) return json({ error: "Please sign in first." }, 401);

    const { job_id, file_size, mime_type } = await req.json();
    if (!job_id || !Number.isFinite(file_size) || file_size <= 0) {
      return json({ error: "Missing job_id or file_size." }, 400);
    }

    const svc = serviceClient();
    const { data: job } = await svc.from("jobs").select("*").eq("id", job_id).single();
    if (!job || job.user_id !== user.id) return json({ error: "Job not found." }, 404);
    if (!["approved", "uploading", "quota_waiting"].includes(job.state)) {
      return json({ error: "This job is not ready for upload." }, 409);
    }

    const token = await getAccessToken();
    const free = await driveFreeBytes(token);
    if (free < file_size + HEADROOM) {
      await svc.from("jobs").update({
        state: "quota_waiting",
        state_detail:
          "Our storage is full right now — you're in line. We'll email you when it's your turn.",
      }).eq("id", job_id);
      return json({
        queued: true,
        message: "Storage is full right now — you're in line and we'll email you.",
      }, 200);
    }

    let folderId = job.drive_folder_id;
    if (!folderId) {
      const rootId = await findOrCreateFolder(token, ROOT_FOLDER, null);
      const safeName = job.match_name.replace(/[^a-zA-Z0-9 _-]/g, "").slice(0, 40);
      const folderName =
        `${job.created_at.slice(0, 10)}_${safeName}_${job_id.slice(0, 8)}`;
      folderId = await findOrCreateFolder(token, folderName, rootId);
    }

    const origin = req.headers.get("Origin") ??
      Deno.env.get("SITE_ORIGIN") ?? "http://localhost:8788";
    const sessionUri = await initResumableSession(
      token, "raw_video.mp4", folderId, file_size, mime_type ?? "video/mp4", origin,
    );

    await svc.from("jobs").update({
      state: "uploading",
      drive_folder_id: folderId,
      file_size_bytes: file_size,
      state_detail: "Uploading footage",
    }).eq("id", job_id);

    return json({ session_uri: sessionUri }, 200);
  } catch (e) {
    console.error("mint-upload:", e);
    return json({ error: "Something went wrong on our side. Please try again." }, 500);
  }
});
```

- [ ] **Step 4: Deploy and set secrets**

```powershell
npx supabase secrets set --env-file supabase/.env
npx supabase functions deploy mint-upload
```

Expected: `Deployed Function mint-upload` (SUPABASE_URL / keys are auto-injected in hosted functions; only our `.env` values need setting).

- [ ] **Step 5: Run tests to verify they pass**

Run: `.\.venv\Scripts\python -m pytest supabase/tests/test_drive_flow.py -v`
Expected: 2 passed — a real 4 KB file round-tripped into the operator's Drive and was cleaned up.

- [ ] **Step 6: Commit**

```powershell
git add supabase/functions/mint-upload supabase/tests/test_drive_flow.py
git commit -m "feat(cloud): mint-upload edge fn - drive resumable session URIs, quota gate"
```

---

### Task 6: `complete-upload` Edge Function

**Files:**
- Create: `supabase/functions/complete-upload/index.ts`
- Modify: `supabase/tests/test_drive_flow.py` (extend `test_mint_and_upload_small_file`)

- [ ] **Step 1: Extend the integration test (failing)**

In `test_mint_and_upload_small_file`, after the `folder_id in f["parents"]` assert, add:

```python
        # 4. complete-upload verifies the file and flips state to 'uploaded'
        r = requests.post(f"{FUNCTIONS_URL}/complete-upload",
                          headers=user_headers(two_users["a_tok"]),
                          json={"job_id": job_id, "drive_file_id": file_id})
        assert r.status_code == 200, r.text
        job = requests.get(rest(f"jobs?id=eq.{job_id}"), headers=ADMIN_HEADERS).json()[0]
        assert job["state"] == "uploaded"
        assert job["drive_file_id"] == file_id
        assert job["file_size_bytes"] == len(payload)
```

Run: `.\.venv\Scripts\python -m pytest supabase/tests/test_drive_flow.py -v`
Expected: FAIL at step 4 (404, function not deployed).

- [ ] **Step 2: Write the function**

`supabase/functions/complete-upload/index.ts`:

```ts
import { corsHeaders, json } from "../_shared/http.ts";
import { getCaller, serviceClient } from "../_shared/auth.ts";
import { getAccessToken, getFile } from "../_shared/google.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const user = await getCaller(req);
    if (!user) return json({ error: "Please sign in first." }, 401);

    const { job_id, drive_file_id } = await req.json();
    if (!job_id || !drive_file_id) {
      return json({ error: "Missing job_id or drive_file_id." }, 400);
    }

    const svc = serviceClient();
    const { data: job } = await svc.from("jobs").select("*").eq("id", job_id).single();
    if (!job || job.user_id !== user.id) return json({ error: "Job not found." }, 404);
    if (job.state !== "uploading") {
      return json({ error: "This job is not in an uploading state." }, 409);
    }

    const token = await getAccessToken();
    const file = await getFile(token, drive_file_id);
    if (!file || !file.parents?.includes(job.drive_folder_id)) {
      return json({
        error: "We couldn't verify your upload. Please try uploading again.",
      }, 400);
    }

    await svc.from("jobs").update({
      state: "uploaded",
      drive_file_id,
      file_size_bytes: Number(file.size ?? 0),
      progress: 0,
      state_detail:
        "Footage received — processing starts when the studio comes online.",
    }).eq("id", job_id);

    return json({ ok: true }, 200);
  } catch (e) {
    console.error("complete-upload:", e);
    return json({ error: "Something went wrong on our side. Please try again." }, 500);
  }
});
```

- [ ] **Step 3: Deploy and verify tests pass**

```powershell
npx supabase functions deploy complete-upload
.\.venv\Scripts\python -m pytest supabase/tests/test_drive_flow.py -v
```

Expected: 2 passed (full mint → PUT → complete → `uploaded` lifecycle).

- [ ] **Step 4: Commit**

```powershell
git add supabase/functions/complete-upload supabase/tests/test_drive_flow.py
git commit -m "feat(cloud): complete-upload edge fn - verify drive file, state=uploaded"
```

---

### Task 7: `decide` Edge Function (admin approve/reject + email)

**Files:**
- Create: `supabase/functions/decide/index.ts`
- Create: `supabase/tests/test_decide.py`

- [ ] **Step 1: Write the failing test**

`supabase/tests/test_decide.py`:

```python
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
```

Run: `.\.venv\Scripts\python -m pytest supabase/tests/test_decide.py -v`
Expected: FAIL (404, function not deployed).

- [ ] **Step 2: Write the function**

`supabase/functions/decide/index.ts`:

```ts
import { corsHeaders, json } from "../_shared/http.ts";
import { getCaller, isAdmin, serviceClient } from "../_shared/auth.ts";
import { deleteFile, getAccessToken } from "../_shared/google.ts";
import { sendEmail } from "../_shared/email.ts";

// reject is allowed from any state that isn't already terminal
const REJECTABLE = [
  "submitted", "approved", "quota_waiting", "uploading", "uploaded",
];
const APPROVABLE = ["submitted", "quota_waiting"];

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const user = await getCaller(req);
    if (!user) return json({ error: "Please sign in first." }, 401);

    const svc = serviceClient();
    if (!(await isAdmin(svc, user.id))) {
      return json({ error: "Admins only." }, 403);
    }

    const { job_id, action, reason } = await req.json();
    if (!job_id || !["approve", "reject"].includes(action)) {
      return json({ error: "Missing job_id or invalid action." }, 400);
    }

    const { data: job } = await svc.from("jobs").select("*").eq("id", job_id).single();
    if (!job) return json({ error: "Job not found." }, 404);

    const { data: target } = await svc.auth.admin.getUserById(job.user_id);
    const email = target?.user?.email;
    const jobUrl = `${Deno.env.get("SITE_ORIGIN") ?? ""}/job.html?id=${job_id}`;

    if (action === "approve") {
      if (!APPROVABLE.includes(job.state)) {
        return json({ error: `Cannot approve a job in state '${job.state}'.` }, 409);
      }
      await svc.from("jobs").update({
        state: "approved",
        state_detail: "Approved — ready for your upload.",
      }).eq("id", job_id);
      if (email) {
        await sendEmail(email, `Approved: ${job.match_name}`,
          `<p>Your match <b>${job.match_name}</b> was approved.</p>
           <p><a href="${jobUrl}">Click here to upload your footage.</a></p>`);
      }
    } else {
      if (!REJECTABLE.includes(job.state)) {
        return json({ error: `Cannot reject a job in state '${job.state}'.` }, 409);
      }
      // free any quota the job already consumed
      if (job.drive_folder_id) {
        await deleteFile(await getAccessToken(), job.drive_folder_id);
      }
      await svc.from("jobs").update({
        state: "rejected",
        reject_reason: reason ?? null,
        drive_file_id: null,
        drive_folder_id: null,
        state_detail: "This submission was not accepted.",
      }).eq("id", job_id);
      if (email) {
        await sendEmail(email, `Update on: ${job.match_name}`,
          `<p>Your submission <b>${job.match_name}</b> wasn't accepted.</p>
           ${reason ? `<p>Reason: ${reason}</p>` : ""}`);
      }
    }
    return json({ ok: true }, 200);
  } catch (e) {
    console.error("decide:", e);
    return json({ error: "Something went wrong on our side. Please try again." }, 500);
  }
});
```

- [ ] **Step 3: Deploy and verify tests pass**

```powershell
npx supabase functions deploy decide
.\.venv\Scripts\python -m pytest supabase/tests/test_decide.py -v
```

Expected: 4 passed.

- [ ] **Step 4: Commit**

```powershell
git add supabase/functions/decide supabase/tests/test_decide.py
git commit -m "feat(cloud): decide edge fn - admin approve/reject with email + drive cleanup"
```

---

### Task 8: `quota` Edge Function (admin storage gauge)

**Files:**
- Create: `supabase/functions/quota/index.ts`
- Create: `supabase/tests/test_quota.py`

- [ ] **Step 1: Write the failing test**

`supabase/tests/test_quota.py`:

```python
import requests

from conftest import FUNCTIONS_URL, user_headers
from test_decide import make_admin


def test_quota_admin_only(two_users):
    r = requests.get(f"{FUNCTIONS_URL}/quota",
                     headers=user_headers(two_users["a_tok"]))
    assert r.status_code == 403, r.text


def test_quota_returns_drive_numbers(two_users):
    make_admin(two_users["a_id"])
    r = requests.get(f"{FUNCTIONS_URL}/quota",
                     headers=user_headers(two_users["a_tok"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["free_bytes"] > 0
    assert body["limit_bytes"] >= body["usage_bytes"]
```

Run: `.\.venv\Scripts\python -m pytest supabase/tests/test_quota.py -v`
Expected: FAIL (404, function not deployed).

- [ ] **Step 2: Write the function**

`supabase/functions/quota/index.ts`:

```ts
import { corsHeaders, json } from "../_shared/http.ts";
import { getCaller, isAdmin, serviceClient } from "../_shared/auth.ts";
import { getAccessToken } from "../_shared/google.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const user = await getCaller(req);
    if (!user) return json({ error: "Please sign in first." }, 401);
    const svc = serviceClient();
    if (!(await isAdmin(svc, user.id))) return json({ error: "Admins only." }, 403);

    const token = await getAccessToken();
    const res = await fetch(
      "https://www.googleapis.com/drive/v3/about?fields=storageQuota",
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const { storageQuota } = await res.json();
    const limit = Number(storageQuota.limit ?? 0);
    const usage = Number(storageQuota.usage ?? 0);
    return json({
      limit_bytes: limit,
      usage_bytes: usage,
      free_bytes: limit ? limit - usage : Number.MAX_SAFE_INTEGER,
    }, 200);
  } catch (e) {
    console.error("quota:", e);
    return json({ error: "Something went wrong on our side." }, 500);
  }
});
```

- [ ] **Step 3: Deploy and verify tests pass**

```powershell
npx supabase functions deploy quota
.\.venv\Scripts\python -m pytest supabase/tests/test_quota.py -v
```

Expected: 2 passed.

- [ ] **Step 4: Commit**

```powershell
git add supabase/functions/quota supabase/tests/test_quota.py
git commit -m "feat(cloud): quota edge fn - admin drive storage gauge"
```

---

### Task 9: Full-suite verification + operator admin row

- [ ] **Step 1: Register the real operator as admin**

The operator signs in once (any client — easiest is the Supabase dashboard → Authentication → Users after a magic-link sign-in from Plan 2, OR create directly): dashboard → SQL editor:

```sql
-- after the operator's real account exists in auth.users:
insert into public.app_admins (user_id)
select id from auth.users where email = '<operator email>';
```

Record in `supabase/SETUP.md`. (Tests already cover admin behavior with throwaway admins; this step is production data, safe to defer until Plan 2 sign-in exists.)

- [ ] **Step 2: Run the entire cloud test suite**

Run: `.\.venv\Scripts\python -m pytest supabase/tests -v`
Expected: 12 passed (4 RLS + 2 drive flow + 4 decide + 2 quota). If any fail, fix before proceeding — Plans 2 and 3 build directly on these contracts.

- [ ] **Step 3: Commit any SETUP.md updates and close out**

```powershell
git add supabase/SETUP.md
git commit -m "docs(cloud): record admin registration + final plan1 setup state"
```

---

## Exit criteria (Plan 1 done)

- [ ] `pytest supabase/tests -v` → all green against the live project.
- [ ] A real file uploaded into the operator's Drive via a minted session URI, with zero credentials in the client.
- [ ] Jobs cannot be read cross-user, forged, self-approved, or given disallowed deliverables (RLS + CHECK proven).
- [ ] All four functions deployed: `mint-upload`, `complete-upload`, `decide`, `quota`.
- [ ] `supabase/SETUP.md` lets the operator rebuild every account/secret from scratch.

**Next:** Plan 2 (public website on Cloudflare Pages) and Plan 3 (local agent + delivery) — written once Plan 1's deployed URLs exist.
