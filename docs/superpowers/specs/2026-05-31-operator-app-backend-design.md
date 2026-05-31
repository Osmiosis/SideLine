# Operator App Backend — Design Spec

**Date:** 2026-05-31
**Status:** Approved (brainstorming complete) → next: implementation plan
**Source requirements:** `PRD'S/Backend_Spec_OperatorApp.md`, `Website/mptr09gx-Frontend_Design_Brief_OperatorApp.md`

---

## 0. Purpose & scope

Build the BACKEND for a LOCAL web app that lets a non-technical operator turn a recorded match into deliverables with zero code/terminal. The backend is a **thin orchestration layer**: it collects human inputs from the UI, writes them to a per-job config file, invokes the EXISTING CV pipeline scripts as background jobs, and serves the resulting deliverables. It does **not** reimplement any CV/ML logic.

### Scope decisions (confirmed with user, 2026-05-31)

1. **Frontend wiring: YES.** Build the FastAPI backend AND wire the existing `Website/index.html` mockup to it (real upload, frame, status polling, downloads). The visual design stays 100% intact — only the simulated JS functions are replaced with real `fetch` calls. End result is a runnable app, not just an API.
2. **Pipeline depth: orchestration first, real wiring incremental.** Build the full backend (jobs, queue, state machine, config contract, invocation layer). Wire `coach_analytics` + `event_highlights` to actually run on local test video. Flag remaining gaps honestly in-code and in this doc.
3. **Phases: all three** (with one necessary deferral — see §8).
4. **Test fixture: local media.** Use a short trimmed clip from `outputs/alfheim/first_half.mp4` plus `clips/basketball.mp4` / `clips/football.mp4` as upload fixtures. Use short clips for fast dev iteration; do not run the full 47-min file during development.
5. **Architecture: Approach A** — modular FastAPI package, subprocess-per-stage pipeline (clean GPU memory release per stage), SQLite job state (durable/resumable).
6. **Notifications: in-app + browser now, email/SMS as a deferred opt-in hook** (email needs internet+SMTP, which crosses the no-cloud line, so it is off by default).

### Hard constraints (from spec + this machine)

- **No cloud.** Footage never leaves the laptop. Server binds to the LAN only; no public exposure.
- **Single GPU (8 GB), 16 GB RAM.** One job at a time, stages sequential. NEVER run parallel torch/GPU processes (crashed this machine on Day 26).
- **Large files** (multi-GB videos): stream uploads to disk, never load into memory.
- **Long jobs** (~3 h/match on the 4060): web requests never block; everything long is a background job with status polling.
- **Plain-English errors only**; technical detail logged server-side.
- **Do NOT change contract field names** — the frontend collects against them exactly.
- **Do NOT hardcode SoccerNet/dataset paths** — the job-config file is the only input source (finish the Day-31 decoupling).

---

## 1. Architecture & directory layout

A `backend/` Python package at the repo root. It imports nothing from the CV scripts; it invokes them as subprocesses with arguments derived from the job config.

```
backend/
  main.py        # FastAPI app: JSON API routes + serves Website/ static frontend at "/"
  config.py      # paths, host/port, per-sport landmark templates, stage definitions
  db.py          # SQLite: jobs table (id, state, stage, progress, error, timestamps)
  jobs.py        # job CRUD, job_config.json read/write, job directory layout helpers
  schemas.py     # pydantic models matching the contract field names EXACTLY
  worker.py      # single background thread: picks next queued job, runs stages sequentially
  pipeline.py    # stage graph; each stage = subprocess call to an existing script
  adapters.py    # decode mp4 -> frames/img1; calibration_points -> homography.json
  errors.py      # map script failures -> friendly messages; server-side logging
  requirements-backend.txt
jobs/<job_id>/   # runtime data (gitignored)
docs/superpowers/specs/2026-05-31-operator-app-backend-design.md  # this file
```

- Server binds `0.0.0.0:<port>` (default 8000). On startup it resolves and prints the LAN URL (e.g. `http://192.168.x.x:8000`) so the operator can point a phone/laptop at it.
- Frontend served as static files from `Website/` at `/`.
- Reuses the existing repo `.venv` (Python 3.14) and its CV deps (opencv, torch, ultralytics). Web-only deps go in `requirements-backend.txt`.

---

## 2. Job directory & config contract

Every match is a JOB with a directory and a `job_config.json`. The UI collects inputs → backend writes the config → pipelines read it.

```
jobs/<job_id>/
  job_config.json     # the contract shape, verbatim
  raw_video.mp4       # uploaded footage (streamed to disk)
  frames/img1/*.jpg   # decode output (lets existing scripts run unchanged)
  homography.json     # calibration adapter output (mark_court.py-compatible)
  roster.json
  tags.json           # clip_id -> player name (player highlights only)
  status.json         # human-readable mirror of live state (durability)
  logs/<stage>.log    # per-stage subprocess stdout/stderr (server-side only)
  outputs/            # finished deliverables land here
```

`job_config.json` matches the spec shape 1:1:

```json
{
  "job_id": "uuid",
  "sport": "football | basketball",
  "match_name": "string",
  "match_date": "YYYY-MM-DD",
  "video_path": "raw_video.mp4",
  "calibration_points": [{"pixel_x": 0, "pixel_y": 0, "real_world_label": "string"}],
  "roster": ["name"],
  "player_tags": {"clip_id": "player_name"},
  "deliverables_requested": ["coach_analytics", "event_highlights", "player_highlights"],
  "created_at": "iso8601"
}
```

**State storage split:** SQLite holds the live job/queue state (the source of truth for the worker and the dashboard). `status.json` is mirrored per job as a human-readable, restart-survivable copy. The two backend-internal files (`frames/`, `homography.json`) are NOT contract changes — they are intermediate artifacts that let the existing scripts run unmodified.

---

## 3. Status state machine

```
created → uploading → uploaded → calibration_pending → calibrated
  → deliverables_selected → queued → decoding → detecting → tracking
  → teams → ball → analytics → events → [tagging_pending → tagging_done]
  → player_highlights → ready

  (any stage → failed, carrying a friendly error message + a logs/ pointer)
```

- **Conditional stages:** a stage runs only if its deliverable was requested. `analytics` runs only for `coach_analytics`; `events` only for `event_highlights`; `tagging_pending`/`player_highlights` only for `player_highlights`. The shared foundation (`decoding → detecting → tracking → teams → ball`) runs once for any deliverable.
- **`tagging_pending`** is the mid-pipeline human pause: the worker generates involvement/presence clips, exposes them via `GET /tagging-clips`, parks the job, and resumes to reel assembly only after `POST /tags`.
- Each stage emits `stage` + a rough `progress` % and a plain-English label for the UI ("Finding players", "Tracking ball", "Building analytics", "Clipping highlights"). No technical terms surface to the operator.

---

## 4. API endpoints + frontend wiring

### Endpoints (FastAPI, JSON) — all per the backend spec

- `POST /api/jobs` — create a job (sport, name, date) → returns `job_id`
- `POST /api/jobs/{id}/video` — streamed/chunked upload to disk, progress-reportable
- `GET  /api/jobs/{id}/frame` — a still freeze-frame from the video (court-marking screen)
- `POST /api/jobs/{id}/calibration` — save `calibration_points`
- `POST /api/jobs/{id}/roster` — save `roster`
- `GET  /api/jobs/{id}/tagging-clips` — list clips needing tags (player highlights)
- `POST /api/jobs/{id}/tags` — save `player_tags`
- `POST /api/jobs/{id}/deliverables` — set `deliverables_requested` + enqueue the job
- `GET  /api/jobs/{id}/status` — current state + stage + progress (UI polls)
- `GET  /api/jobs/{id}/outputs` — list finished deliverable files
- `GET  /api/jobs/{id}/outputs/{file}` — download a deliverable
- `GET  /api/jobs` — list all jobs (dashboard)
- `GET  /` (+ static assets) — serve the frontend

### Frontend wiring (replace simulated JS in `index.html`, design untouched)

| Mockup behavior | Real wiring |
|---|---|
| `simulateUpload()` (fake bar) | `POST /api/jobs/{id}/video`, streamed, real progress |
| hardcoded `matches` array (dashboard) | `GET /api/jobs` |
| court canvas (drawn placeholder) | `GET /api/jobs/{id}/frame` freeze-frame; `POST .../calibration` |
| roster chips (local only) | `POST /api/jobs/{id}/roster` |
| tagging screen (mock clips) | `GET .../tagging-clips`, `POST .../tags` |
| deliverable select → fake processing | `POST .../deliverables` (enqueue) |
| processing screen (fake stages) | poll `GET .../status` → stage + % |
| results screen (mock thumbnails) | `GET .../outputs`, `GET .../outputs/{file}` |

The CSS, layout, screen flow, and visual language of `index.html` are preserved exactly; only the data layer changes.

---

## 5. Pipeline wrapping (foundation + deliverables)

The worker runs the **shared foundation once**, then the requested deliverable stages. Each stage is a subprocess call to an existing script, args derived from `job_config.json` and pointed at the job directory.

### Two thin adapters (glue, NOT CV reimplementation)

1. **Decode adapter** (`adapters.py`): `raw_video.mp4` → `frames/img1/000001.jpg…` (numbered JPGs, the layout every football script already expects). This lets `coach_deliverable.py`, `clip_highlights.py`, `team_assign.py`, etc. run unchanged with their path args repointed at the job's `frames/` dir.
2. **Calibration→homography adapter** (`adapters.py`): the collected `calibration_points` (pixel coords + a `real_world_label`) are solved into a `homography.json` in the exact format `mark_court.py` emits, using a **per-sport landmark-label → real-world-meter template** (standard football pitch / basketball court landmark coordinates). This is the documented deployment calibration path (human marks points once; homography holds for the fixed camera). `cv2.findHomography` on the marked points only — no new CV.

### Stage graph

- **Foundation:** `decoding` (decode adapter) → `detecting`/`tracking` (`track_alfheim.py --video` for football; `track_basketball.py` for basketball) → `teams` (`team_assign.py` / `bball_team_assign.py`) → `ball` (`analyze_ball.py` / `analyze_ball_basketball.py`) → calibration→`homography.json` adapter.
- **coach_analytics** → `coach_deliverable.py` / `coach_deliverable_basketball.py`, pointed at job frames + `homography.json`.
- **event_highlights** → `detect_events.py` → `clip_highlights.py` (football) / `detect_events_basketball.py` → `clip_highlights_basketball.py`.
- **player_highlights** → `detect_involvement.py` → `clip_player_highlights.py` → **(tagging pause)** → `assemble_player_reels.py` (`_bb` variants for basketball).

### Honest gaps (flagged in-code and surfaced as caveats, per the incremental-wiring choice)

- **`analyze_pitch.py` is GT-validation, not the deployment homography consumer.** Deployment analytics use the marked-points `homography.json`; the GT-distance comparison in `analyze_pitch.py` is a validation feature that simply does not run without GT, and that is correct.
- **`event_highlights` quality is footage-gated.** Day-31 measured ~30% ball recall on the wide fixed Alfheim camera. The *plumbing* runs end-to-end; clip *quality/recall* validates on the real DPS camera. This is a known, documented limitation — not a backend bug.
- **`player_highlights` tag volume is footage-gated.** Days 26/30/31/32 confirmed identity fragmentation is structural at full-match scale (the tag-per-clip mechanism is the agreed workaround). The mechanism is built; tag volume/quality validates on real footage.
- **GT-zip readers** (`team_assign.py`, `detect_events.py`) read a SoccerNet zip for labels/positions that do not exist for uploaded footage. The wrapper supplies an "no-GT" invocation path (labels optional); where a script hard-requires GT, that branch is flagged and the deliverable degrades gracefully rather than crashing.

---

## 6. Background worker, queue, resumability

- **Single background thread**, started/stopped via FastAPI lifespan. It loops: pick the oldest `queued` job, run its stages sequentially, update SQLite + `status.json` after each stage.
- **One job at a time** (one GPU). No concurrent GPU work — respects the hardware rule that crashed the machine on Day 26.
- **Queue** = SQLite rows ordered by `created_at`.
- **Subprocess isolation per stage** = torch/GPU memory is fully released when each stage process exits, avoiding accumulation on the 8 GB GPU.
- **Resumability:** on server restart, a job left mid-stage is re-queued from its last *completed* stage; stage outputs already on disk let the worker skip redo where safe. A 3-hour job never dies silently.

---

## 7. Error handling

- Every subprocess stage is wrapped: non-zero exit (or timeout) → capture stdout/stderr to `jobs/<id>/logs/<stage>.log`, set job status `failed` with a **friendly** message keyed off the stage ("We couldn't read the video — please try re-uploading"; "Court setup didn't line up — re-mark the points").
- The API never returns a raw stack trace or technical detail to the client. All technical detail is server-side only.
- Empty/error states on the frontend get friendly copy, matching the design brief's "no raw errors" requirement.

---

## 8. Phase 3 mechanisms

- **Resumability** — see §6.
- **Multi-match management** — dashboard backed by `GET /api/jobs` + SQLite; jobs list with sport, name/date, status badge, thumbnail.
- **Notifications** — in-app live status badge + a browser Web Notification when a job reaches `ready` (requires the tab open / permission granted; no external service). An `on_job_ready` hook is left in `worker.py` so an email/SMS sender could be attached later.
- **Deferred by necessity:** *re-tuning CV constants for the real DPS camera.* This is impossible without DPS footage (Days 29–32). The mechanisms are built; the constant tuning happens when real footage exists. Documented, not silently skipped.
- **Email/SMS notification** — deferred opt-in hook only. It requires internet + SMTP credentials, which crosses the no-cloud principle, so it is off by default and not wired now.

---

## 9. Testing / verification

- **Backend tests (no GPU):** job CRUD, `job_config.json` round-trip, state-machine transitions, the calibration→homography adapter (solve on synthetic marked points, assert sane reconstruction error), and error→friendly-message mapping.
- **End-to-end (local media):** a short (~30 s) trimmed clip from `outputs/alfheim/first_half.mp4` and `clips/basketball.mp4` used as upload fixtures. Assert the foundation runs and `coach_analytics` + `event_highlights` produce output files in `jobs/<id>/outputs/`. Verified by actually running and observing output — not asserted blind. Short clips only during dev; the full 47-min file is not run.
- **Frontend smoke:** load the app, create a job, upload a short clip, mark calibration, select deliverables, watch status advance to `ready`, download an output — all against the real backend on localhost.

---

## 10. Tech & dependencies

- **Web:** FastAPI, uvicorn, python-multipart (streamed uploads), pydantic. → `backend/requirements-backend.txt`.
- **State:** SQLite via stdlib `sqlite3` (no external DB).
- **CV:** reuse the existing repo `.venv` and its installed deps (opencv-python, torch, ultralytics) — the backend only invokes the scripts, never re-imports their CV logic.
- **Runtime:** Python 3.14 in `.venv`; server bound to `0.0.0.0:8000` on the LAN.

---

## 11. Out of scope / explicit non-goals

- No cloud, no Celery/Redis, no heavyweight infra.
- No reimplementation of any CV/ML logic — wrap existing scripts only.
- No auth/login (secure-enough for a school LAN, no public exposure).
- No changes to the contract field names.
- No re-tuning of CV constants for the DPS camera (footage-gated; deferred).
- No multi-GPU / concurrent-job processing.
