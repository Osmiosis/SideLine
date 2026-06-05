# Online Hosting — Design Spec ("Approve-first, Drive-relay, local muscle")

**Date:** 2026-06-05
**Status:** Approved (brainstorming complete) → next: implementation plan
**Builds on:** `docs/superpowers/specs/2026-05-31-operator-app-backend-design.md` (local Operator App — unchanged, reused as the processing engine)

---

## 0. Purpose & scope

Put the Operator App online so **anyone can submit match footage from their own device**, the operator (admin) **approves or rejects** each submission from any device, the footage is **processed on the operator's PC** by the existing CV pipeline, and the user **automatically receives a download link** for the deliverables.

This is a **relay architecture**, not a cloud port: the cloud holds only metadata, auth, and temporary file parking. All compute stays on the operator's PC. The existing `backend/` package, worker, pipeline, and operator UI (calibration, tagging) are reused unchanged.

### Hard constraints (confirmed with user, 2026-06-05)

1. **Absolutely free.** Every component must run on a genuinely free tier. No credit-card-on-file services (this rules out Cloudflare R2 for delivery; Google Drive is used instead).
2. **Multi-GB uploads (1–8 GB full matches)** must work **while the operator's PC is off**. Footage parks in the operator's Google Drive (15 GB free) until the PC comes online.
3. **Scale: small real userbase** — a school/club, a few uploads per day, users mostly known to the operator.
4. **Approve-first:** footage is uploaded only AFTER the operator approves the submission. Junk never touches the Drive quota; approval is the throttle when space is tight.
5. **Auth: email magic links** (Supabase Auth). No passwords. Operator logs in as an admin user.
6. **Results delivery: automatic.** Deliverables are pushed back to the job's Drive folder, shared by link, and the user is emailed. Works with the PC subsequently off.
7. **Deliverable scope at launch:** full matches → **coach analytics only** (the one output proven at full-match scale, Day 29–31). Segments ≤ 20 min → all three outputs (analytics, event highlights, player highlights). Enforced at submission, verified after download.

### Decided trade-offs

- **15 GB Drive quota is the bottleneck**: roughly 1–2 pending full matches at a time. Mitigated by approve-first gating, quota check before unlocking uploads, deleting raw footage immediately after ingest, and deleting deliverables after 14 days.
- Site lives at a free `*.pages.dev` subdomain. A custom domain (~$10/yr) is the only conceivable cost and is optional/deferred.
- Uploads require the PC owner to do nothing, but processing latency depends on when the PC is next online. Status page sets this expectation ("queued — processing begins when the studio comes online").

---

## 1. Architecture overview

```
 User's browser                    Free cloud                       Operator's PC (when on)
┌──────────────┐   submit    ┌─────────────────────┐   poll    ┌─────────────────────┐
│ Website       │──────────▶│ Supabase (free)      │◀─────────│ Local Agent (Python) │
│ (Cloudflare   │  magic-link│  • Postgres: jobs    │           │  • pulls approved    │
│  Pages, free) │◀──────────│  • Auth: magic links │           │    footage from Drive│
│               │            │  • Edge Fn: mints    │           │  • runs existing     │
│  chunked      │            │    Drive upload URIs │           │    backend pipeline  │
│  upload ──────┼────────┐   └─────────────────────┘           │  • pushes results to │
└──────────────┘         │   ┌─────────────────────┐           │    Drive, updates DB │
                          └─▶│ Operator's G. Drive  │◀─────────│  • deletes to free   │
   operator, any device      │  folder per job      │           │    quota             │
       ┌──────────────┐      │  raw in / results out│           └─────────────────────┘
       │ Admin page:   │      └─────────────────────┘
       │ approve/reject│──▶ Supabase
       └──────────────┘
```

Five components, each independently testable:

| # | Component | Hosting | Role |
|---|-----------|---------|------|
| 1 | **Public website** | Cloudflare Pages (free, unlimited bandwidth) | Login, submission form, chunked uploader, job status page, admin approve/reject view |
| 2 | **Supabase project** | Supabase free tier | Postgres `jobs` table (+RLS), magic-link auth, Edge Function that mints Drive upload sessions |
| 3 | **Google Drive + OAuth** | Google (free) | Parking lot for raw footage in, deliverables out; one OAuth client (`drive.file` scope) owned by the operator |
| 4 | **Local agent** | Operator's PC | New small Python service: polls Supabase, downloads approved footage, drives the EXISTING `backend/` pipeline, uploads results, cleans up |
| 5 | **Email notifications** | Resend free tier (100/day) | "Approved — upload now" and "Your analysis is ready" emails |

The existing local Operator App (FastAPI + `Website/` UI) keeps running on the PC for the human-in-the-loop steps (calibration, player tagging) exactly as today.

---

## 2. The upload trick: Drive resumable session URIs

Uploading a stranger's multi-GB file into the **operator's** Drive, from the browser, without exposing credentials:

1. Browser asks the Supabase Edge Function for an upload session (only possible when the job is in state `approved`).
2. The Edge Function — which holds the operator's **refresh token as a server-side secret** — does, server-side:
   - refreshes an access token (`drive.file` scope);
   - checks Drive free space (`about.get`); if `< file_size + 1 GB` headroom → respond "queued, try later" and mark job `quota_waiting`;
   - creates the job folder `SportsAI Submissions/<YYYY-MM-DD>_<match-name>_<job-id>/`;
   - initiates a **resumable upload session** (`POST .../upload/drive/v3/files?uploadType=resumable`) targeting that folder;
   - returns ONLY the session URI to the browser.
3. The browser PUTs the file to the session URI in chunks (multiple-of-256 KiB chunks, ~32 MB each) with a progress bar. **The session URI itself authenticates** — no Authorization header, no token in the browser. It can write exactly one file and read nothing.
4. Session URIs are valid for one week and support resume-after-disconnect (query the URI with `Content-Range: bytes */total` to learn the offset and continue).

Security properties: the worst an attacker with a leaked session URI can do is overwrite that one in-flight upload. The refresh token never leaves the Edge Function's secrets. `drive.file` scope means even the operator's own token can only see files this app created — not the rest of their Drive.

---

## 3. Data model (Supabase Postgres)

One table is the source of truth; the existing local SQLite remains an internal implementation detail of the PC-side pipeline.

```sql
jobs (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid references auth.users not null,
  sport           text not null check (sport in ('football','basketball')),
  match_name      text not null,
  match_date      date,
  declared_duration_min  int not null,            -- user-declared; verified after download
  deliverables    text[] not null,                 -- requested outputs
  state           text not null default 'submitted',
  state_detail    text,                            -- stage name / friendly progress message
  progress        int default 0,                   -- 0-100 within current stage
  drive_folder_id text,                            -- set when approved
  drive_file_id   text,                            -- set when upload completes
  file_size_bytes bigint,
  results_url     text,                            -- shared Drive link when ready
  error_message   text,                            -- plain-English only
  reject_reason   text,
  created_at      timestamptz default now(),
  updated_at      timestamptz default now(),
  expires_at      timestamptz                      -- results cleanup time (ready + 14 days)
)
```

**Row-Level Security:** users `select` only their own rows and `insert` rows for themselves; only the admin role updates `state` to `approved`/`rejected`; all other state transitions are written by the agent via the `service_role` key (held only on the operator's PC) and by the Edge Function. Users never update rows directly — all user-triggered transitions go through Edge Function endpoints that validate them.

**Admin identification:** the operator's auth user id is stored in a `app_admins` table; RLS policies and the website's admin view key off membership.

---

## 4. Job state machine

```
submitted ──(admin approves)──▶ approved ──(quota ok, session minted)──▶ uploading
    │                              │
    └─(admin rejects)─▶ rejected   └─(quota full)─▶ quota_waiting ─(space freed)─▶ approved
uploading ──(browser finishes, Edge Fn verifies size)──▶ uploaded
uploaded ──(agent downloads + verifies duration)──▶ processing
processing ──(stages stream progress)──▶ [operator_action]* ──▶ processing … ──▶ ready
ready ──(+14 days, agent cleanup)──▶ expired
any state ──(unrecoverable failure)──▶ failed   (plain-English error_message)
```

\* `operator_action` = calibration / player tagging done in the existing LOCAL operator UI; the cloud row shows "waiting for studio review" so the user understands the pause.

Duration verification: after download, the agent probes the real video duration. If a "segment" job turns out to be > 20 min, the agent downgrades deliverables to analytics-only and records a friendly note in `state_detail` (no hard failure).

Notifications (Resend, fired by the agent or Edge Function on transition):
- `approved` → "You're approved — click to upload your footage" (link to job page)
- `rejected` → reason
- `ready` → "Your analysis is ready" + results link (+ expiry date)

---

## 5. Local agent (new code, PC-side)

A small standalone Python service (`agent/` package at repo root), started manually or at login. It is the ONLY component holding the Supabase `service_role` key and Drive refresh token locally.

Responsibilities (single loop, sequential — one job at a time, respecting the 8 GB GPU / no-parallel-shells rule):

1. **Poll** Supabase every ~60 s for rows in `uploaded` (also re-checks `quota_waiting` after cleanups).
2. **Ingest:** download `drive_file_id` to `jobs/<job_id>/raw_video.mp4` via the Drive API (chunked, resumable); verify size/duration; **delete the raw file from Drive immediately** (quota back); create the local job through the existing backend's job machinery (reusing `jobs.py` / `schemas.py` contract — field names unchanged).
3. **Process:** enqueue into the existing worker/pipeline. Mirror every local stage transition + progress into the Supabase row (`processing` / `state_detail` / `progress`). When the local job pauses for calibration/tagging, set `operator_action`.
4. **Deliver:** on local `ready`, upload `jobs/<job_id>/outputs/` to `<drive job folder>/deliverables/`, set "anyone with link can view" on the folder, write `results_url`, `state=ready`, `expires_at = now + 14 days`, trigger the ready email.
5. **Cleanup:** on each loop, delete Drive deliverable folders past `expires_at`, mark rows `expired`; promote the oldest `quota_waiting` job if space allows.

**Idempotency / crash safety:** every step is resumable — downloads resume by byte offset; the existing worker already resumes mid-job from the last completed stage; uploads of deliverables are re-attempted by listing what already exists in the folder. The agent writes no state it cannot reconstruct from Supabase + local disk.

---

## 6. Website changes

The public site is a **separate deployment** of an adapted copy of the existing front-end design (`Website/` look & feel preserved), living in `site/` and deployed to Cloudflare Pages. The local `Website/` operator UI is untouched.

Pages/views (plain HTML/JS + `@supabase/supabase-js` from CDN — keep the no-framework approach):

1. **Login** — email field → magic link → session.
2. **Submit** — sport, match name, date, declared duration, deliverable picker (auto-restricts to analytics-only when duration > 20 min). Creates the `jobs` row in `submitted`.
3. **My jobs / status** — list + per-job page; polls the row; shows friendly state copy, progress bar, results download button when `ready`, expiry countdown.
4. **Upload** — appears on the job page once `approved`: file picker → calls Edge Function → chunked PUT loop to the session URI with progress, pause/resume, and retry-on-disconnect (resume offset via `Content-Range: bytes */total` probe).
5. **Admin** (visible to admin only) — pending submissions with Approve / Reject(+reason) buttons; quota gauge (free Drive space, reported by the Edge Function); all-jobs dashboard.

Plain-English copy everywhere; technical details never shown to users (mirrors the existing backend's error philosophy).

---

## 7. Setup inventory (one-time, all free)

| Step | What |
|---|---|
| Google Cloud | Create project → enable Drive API → OAuth client (Desktop) → one-time consent as operator with `drive.file` scope → store refresh token as Supabase secret + agent-side `.env` |
| Supabase | Create project → run schema migration + RLS policies → enable email magic-link auth → deploy Edge Function (`mint-upload`, `quota`) → set secrets |
| Cloudflare Pages | Connect repo (or `wrangler pages deploy site/`) → set Supabase URL + anon key as build-time config |
| Resend | Free account → API key → verified sender → key into agent `.env` + Edge Function secret |
| PC | `agent/.env` with Supabase service key + Google refresh token; run agent alongside existing backend |

Secrets never enter the repo: `.env` files gitignored; browser only ever sees the Supabase anon key (safe by design — RLS enforces access).

---

## 8. Error handling

| Failure | Behaviour |
|---|---|
| Upload interrupted | Browser resumes from last confirmed offset (session URI valid 7 days); job stays `uploading` |
| Session URI expires unused | Edge Function mints a fresh one on request; folder reused |
| Drive quota full at approval | Job → `quota_waiting`, user told "you're in line — we'll email you"; auto-promoted after cleanup |
| Wrong/corrupt file (not a video, wrong duration) | Agent fails ingest → `failed` with plain-English message; Drive file deleted; user may resubmit |
| Pipeline stage failure | Existing error mapping → friendly `error_message`, `failed`; raw already deleted, logs stay local |
| Agent offline for days | Nothing breaks: uploads still land in Drive; jobs queue in `uploaded`; status copy explains the wait |
| Supabase/Resend outage | Agent retries with backoff; transitions are idempotent |

---

## 9. Testing strategy

- **Edge Function:** unit-test quota math + state validation locally (`supabase functions serve`); integration-test session minting against a throwaway Drive folder with a small file.
- **Uploader:** test chunked upload + kill-and-resume with a ~300 MB file on a throttled connection; verify progress and resume offset handling.
- **Agent:** dry-run mode against a `test` Supabase row + a 2-min fixture clip (existing dev fixtures, per the backend spec — never the 47-min file during development); assert full lifecycle `submitted → ready → expired` including Drive cleanup.
- **RLS:** automated checks that user A cannot read user B's rows and cannot self-approve.
- **End-to-end rehearsal:** one real ~1 GB upload from a phone on mobile data before inviting users.

---

## 10. Out of scope (deferred)

- Direct-to-PC upload fast path via Cloudflare Tunnel when the PC is online (Approach B — future enhancement).
- Custom domain.
- Multiple operators / multiple PCs; payment/quotas per user; CAPTCHA (invite-by-email keeps spam manageable at this scale).
- Letting uploaders do their own player tagging (interesting later — would attack the Day-31 tagging-hours blocker).
- Any change to the CV pipeline itself or the local Operator App contract.
