# Supabase Setup Checklist — sports-ai cloud foundation (Plan 1)

Reproducible setup record for the online-hosting cloud layer. **No secret values live in this
file** — only project coordinates and the locations where secrets are stored.

## Project coordinates

| Field          | Value                                                              |
| -------------- | ------------------------------------------------------------------ |
| Project name   | `sports-ai`                                                        |
| Project ref    | `qphkhchhdurvylrunaoz`                                             |
| Dashboard URL  | https://supabase.com/dashboard/project/qphkhchhdurvylrunaoz        |
| API URL        | https://qphkhchhdurvylrunaoz.supabase.co                          |

## API keys (new-style)

This project uses Supabase's **new-style API keys**:

- `sb_publishable_*` replaces the legacy **anon** key.
- `sb_secret_*` replaces the legacy **service_role** key.

We keep the **legacy env var names** (`SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`) so the rest
of the codebase reads keys uniformly regardless of key style.

### Where each secret lives (all UNTRACKED — see root `.gitignore`)

| Secret(s)                                              | Location                | Notes                                                              |
| ------------------------------------------------------ | ----------------------- | ------------------------------------------------------------------ |
| Publishable key + secret key (+ URL, functions URL)    | `supabase/tests/.env`   | Used by the Python integration tests.                              |
| Google OAuth + Resend Edge Function secrets            | `supabase/.env`         | Later pushed via `npx supabase secrets set --env-file supabase/.env`. |
| Google OAuth Desktop-app client JSON                   | `agent/client_secret.json` | Downloaded from Google Cloud Console → Credentials (created in **Task 3**); used by `agent/get_refresh_token.py` and later by the local agent. |
| Local agent secrets (Supabase secret key + Google refresh token) | `agent/.env`  | Populated in **Plan 3** when the agent is built.                   |

## Manual steps already done

- [x] Created a free Supabase project (region and organization chosen by the operator).
- [x] Collected the publishable + secret API keys from **Settings → API** and stored them in
  `supabase/tests/.env`.
- [x] Ran `npx supabase init` (created `supabase/config.toml` and `supabase/.gitignore`).

## Manual steps still pending

- [ ] `npx supabase login` — interactive browser authentication (operator runs this).
- [ ] `npx supabase link --project-ref qphkhchhdurvylrunaoz` — prompts for the database password.
- [ ] Google Cloud OAuth setup — see **Task 3** (placeholder below); produces
  `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`.
- [ ] Resend account — added in a later plan (Plan 3); produces `RESEND_API_KEY` and the verified
  production sender for `EMAIL_FROM`.
- [ ] Register the operator admin row — **Plan 1 Task 9**.

### Task 3 — Google Cloud OAuth

Produces `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` for the `drive.file`
scope. The operator does the console steps; the script mints the refresh token.

- [ ] [console.cloud.google.com](https://console.cloud.google.com) → **New project** named
  `sports-ai-relay` (free, no billing required).
- [ ] **APIs & Services → Library** → enable **Google Drive API**.
- [ ] **OAuth consent screen → External** → set the app name + support email → **do not add any
  scopes here** → save.
- [ ] **Publishing status → "In production"**. **CRITICAL:** while in **Testing** status, refresh
  tokens expire after **7 days**. `drive.file` is a **non-sensitive** scope, so moving to
  production needs **no verification review**.
- [ ] **Credentials → Create credentials → OAuth client ID → Desktop app** → download the JSON to
  `agent/client_secret.json` (gitignored).
- [ ] Run `.venv\Scripts\python agent\get_refresh_token.py` (opens a browser, consent once) →
  paste the three printed `GOOGLE_*` lines into **both** `supabase/.env` and
  `supabase/tests/.env`.

## Auth note

Magic-link email auth is **enabled by default** on new Supabase projects (the Email provider is
ON). The built-in email sender is **rate-limited (~3–4 emails / hour / address)** — fine for dev.
A production-grade sender arrives with **Resend in Plan 3**.

## Plan 1 final state (2026-06-05)

All four Edge Functions are **deployed** on project `qphkhchhdurvylrunaoz`:
`mint-upload`, `complete-upload`, `decide`, `quota`. Function secrets were pushed with
`npx supabase secrets set --env-file supabase/.env`.

Full integration suite: `.venv\Scripts\python -m pytest supabase/tests -v` → **12 passed**
(4 RLS + 2 drive flow + 4 decide + 2 quota) against the live project.

Drive relay account: the refresh token belongs to the operator Drive account recorded in
`supabase/.env` (15 GB free tier). Re-mint anytime with `agent/get_refresh_token.py`.

### Registering the real operator as admin (deferred to Plan 2)

The throwaway-admin path is fully tested. Once the operator's real account exists in
`auth.users` (first magic-link sign-in via the Plan 2 site), run in the dashboard SQL editor:

```sql
insert into public.app_admins (user_id)
select id from auth.users where email = '<operator email>';
```

## Plan 2 final state (2026-06-06)

- Public site: `site/` deployed to Cloudflare Pages → **https://sideline-d8c.pages.dev**
  (project `sideline`; redeploy with `npx wrangler pages deploy site --project-name sideline`).
  Pages serves pretty URLs (`/job.html` 308→ `/job`, query string preserved — email links work).
- Local dev: `npx wrangler pages dev site` → http://localhost:8788.
- Supabase Auth URL configuration: Site URL = the pages.dev URL; Redirect URLs allow
  `https://sideline-d8c.pages.dev/*` AND `http://localhost:8788/*` (local dev sign-in).
- Function secret `SITE_ORIGIN` = https://sideline-d8c.pages.dev (drives `decide` email links
  and the CORS origin bound into Drive resumable sessions).
- Operator admin registered in `public.app_admins` (vibha.aarav@gmail.com, 2026-06-06).
- Upload path proven end-to-end from a real browser: 314.8 MB file → chunked PUT (32 MB
  chunks) → Drive → `complete-upload` → state `uploaded`. Test artifacts cleaned up.
- Site unit tests: `node --test site/tests/*.test.mjs` → 13 pass
  (note: the bare directory form `node --test site/tests/` does NOT work on Node 24/Windows).
- Cloud regression: `pytest supabase/tests -v` → 12 passed.

### Custom SMTP (added 2026-06-06)

Supabase Auth sends via **Gmail SMTP** (no Resend, no domain needed — $0):
host `smtp.gmail.com`, port 465, username/sender = the operator relay Gmail account,
password = a Google **app password** (myaccount.google.com/apppasswords, requires 2FA;
revocable anytime). Configured in dashboard → Project Settings → Auth → SMTP Settings.
Auth email rate limit auto-raised to 30/hour (was 2/hour project-wide on built-in sender).
Gmail allows ~500 emails/day — plenty at club scale. Plan 3 notification emails can reuse
this instead of Resend.

Tip: a sign-in link can be minted WITHOUT email (rate-limit-proof) via the admin API:
`POST {SUPABASE_URL}/auth/v1/admin/generate_link` with `{"type":"magiclink","email":...,
"options":{"redirect_to":"https://sideline-d8c.pages.dev"}}` (service role key).

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

### Operator notifier (Plan 3.1)

Always-on watcher: `.venv\Scripts\pythonw.exe -m agent.notifier` (no console).
Auto-start at login: Win+R -> `shell:startup` -> create shortcut with target
  C:\sports-ai\.venv\Scripts\pythonw.exe -m agent.notifier
and "Start in" = C:\sports-ai.
Toasts: "awaiting approval" (button -> admin page) and "footage received"
(button -> starts backend + agent consoles and opens http://localhost:8000).
Delivery layout (Plan 3.1): Drive job folder contains named subfolders
"Coach analytics" / "Event highlights" / "Player highlights" with user-facing
files only (no json/internal artifacts).
