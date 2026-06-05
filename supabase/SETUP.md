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
