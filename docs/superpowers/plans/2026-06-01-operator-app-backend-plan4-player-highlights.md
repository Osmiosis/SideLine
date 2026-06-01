# Operator App Backend — Plan 4: Player Highlights (tagging flow)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Player Highlights (output #2) end-to-end for both sports: the pipeline generates involvement clips, **pauses for the operator to tag "who is this?"**, then assembles a named reel per player. This adds the mid-pipeline human pause the state machine was designed for (Plan 1), two new endpoints (`GET /tagging-clips`, re-enqueueing `POST /tags`), and wires the frontend's existing tagging screen.

**Architecture:** The pipeline engine gains player-highlights steps per sport: `involvement` → `clip-candidates` (emits taggable clips + `clips_manifest.json`) → **`tagging_pending`** (a pause marker) → `reels` (consumes `clip_tags.json` → named reels). The worker parks at `tagging_pending` and stops; `GET /tagging-clips` serves the manifest + clip mp4s; `POST /tags` writes `clip_tags.json` into the job and re-enqueues with a resume marker so the worker skips the (already-done, GPU-expensive) foundation and runs only `reels`. Per the research, the CV scripts need **no code edits** — only CLI args pointed at the job dir and the operator's tags written to the path `assemble_player_reels(_bb)` already reads. The frontend re-enables the Player Highlights card, routes through the roster+tagging screens when it's selected, and the processing screen navigates to tagging when the job reaches `tagging_pending`.

**Tech Stack:** as Plans 1–3. No new deps. Test footage: `clips/football.mp4`, `clips/basketball.mp4`.

**Spec:** `docs/superpowers/specs/...design.md` (§3 state machine `tagging_pending`, §5 player_highlights two-part, §4 `/tagging-clips` + `/tags`)
**Research (authoritative):**
- `docs/superpowers/research/2026-06-01-plan4-football-playerhighlights.md`
- `docs/superpowers/research/2026-06-01-plan4-basketball-playerhighlights.md`
**Builds on:** Plans 1–3 (DONE). Engine: `Step`/`StepCtx`/`resolve_steps`/`run_step`/`PIPELINES` with `_football_steps`/`_basketball_steps`. Worker drops the old tagging branch (Plan 3) — this plan reintroduces it cleanly.

---

## Contract (from research — do not change)

- `clip_tags.json` at `jobs/<id>/player_highlights/<seq>/clip_tags.json`, shape `{ "<clip_basename.mp4>": "<player name>" | "__skip__" }`. `assemble_player_reels(_bb).py` already reads exactly this path+shape — no edit.
- clip_id = the clip mp4 basename: `t{tid:03d}_m{idx:02d}_{start_sec:.0f}s.mp4` (involvement) / `p{tid:03d}_presence.mp4` (presence fallback).
- `clips_manifest.json` (written by `clip_player_highlights(_bb)`) holds per-clip entries (clip_id, track_id, role, start/end frame, strength). `GET /tagging-clips` returns these + a served mp4 URL per clip.
- follow_cam JSON is a prerequisite for both involvement clipping AND events; it must run if `event_highlights` OR `player_highlights` is requested.

---

## File Structure

```
backend/
  pipeline.py   # MOD — Step.deliverable may be a set; add PH steps (both sports); follow_cam shared by events+PH
  worker.py     # MOD — reintroduce tagging_pending pause + resume-to-reels
  main.py       # MOD — GET /tagging-clips, GET /tagging-clips/{clip}/video, POST /tags (re-enqueue)
  jobs.py       # MOD — helper to write clip_tags.json into the job
tests/backend/
  test_pipeline_ph.py     # NEW — PH steps resolve per sport; deliverable-set filtering
  test_worker_tagging.py  # NEW — park at tagging_pending; resume runs only reels
  test_api_tagging.py     # NEW — /tagging-clips + /tags (with monkeypatched run_step)
scripts/
  e2e_player_highlights_football.py    # NEW — two-part e2e (GPU)
  e2e_player_highlights_basketball.py  # NEW — two-part e2e (GPU)
```

(Frontend `Website/index.html` + `app.js` modified for the tagging UX — Task 5.)

---

## Conventions
- Windows/PowerShell, repo root `C:\sports-ai`, interpreter `.venv\Scripts\python.exe`, node for JS checks. Commit after each task.
- CV scripts: CLI-only wiring; if a script truly needs an edit, make it additive + note it (research says none needed — verify).

---

## Task 1: engine — player-highlights steps (both sports)

**Files:** Modify `backend/pipeline.py`; Create `tests/backend/test_pipeline_ph.py`

**Design:**
- Generalize `Step.deliverable`: allow `None` (foundation, always), a `str`, or a `set[str]` (runs if ANY requested). Update `resolve_steps` to check membership accordingly.
- Make `follow-cam` deliverable = `{"event_highlights", "player_highlights"}` (runs for either).
- Append PH steps to BOTH sport lists, all `deliverable="player_highlights"`, in this order AFTER the events tail:
  - `involvement` (ui_stage `player_highlights`)
  - `clip-candidates` (ui_stage `player_highlights`)
  - `tagging_pending` (ui_stage `tagging_pending`, build returns `None` — pure pause marker, the worker handles it)
  - `reels` (ui_stage `player_highlights`)
- Football commands (research-confirmed; seq=`<id>`, J=job paths):
  - involvement: `detect_involvement.py <id> --tracker-dir tracks --ball-dir ball_track --team-file team_assign/track_teams.json --out involvement`
  - clip-candidates: `clip_player_highlights.py <id> --involvement-dir involvement --follow-dir follow_cam --source frames --out player_highlights`
  - reels: `assemble_player_reels.py <id> --involvement-dir involvement --clips-dir player_highlights --tracker-dir tracks --team-file team_assign/track_teams.json --follow-dir follow_cam --source frames --out outputs/player_highlights --render-seqs <id>`
- Basketball commands (mirror, `_bb` scripts, team file = `track_teams_emb.json`; confirm exact arg names against the basketball research doc + `--help`):
  - involvement: `detect_involvement_bb.py <id> --tracker-dir tracks/players --ball-dir ball_track --team-file team_assign/track_teams_emb.json --out involvement`
  - clip-candidates: `clip_player_highlights_bb.py <id> --involvement-dir involvement --follow-dir follow_cam --source frames --ball-dir ball_track --out player_highlights`
  - reels: `assemble_player_reels_bb.py <id> --involvement-dir involvement --clips-dir player_highlights --tracker-dir tracks/players --team-file team_assign/track_teams_emb.json --follow-dir follow_cam --source frames --out outputs/player_highlights --render-seqs <id>`

- [ ] **Step 1: Failing test** `tests/backend/test_pipeline_ph.py`:
```python
from backend import pipeline
from backend.schemas import JobConfig


def _cfg(sport, deliverables):
    return JobConfig(job_id="j", sport=sport, match_name="x", match_date="2026-06-01",
        video_path="raw_video.mp4", calibration_points=[], roster=[], player_tags={},
        deliverables_requested=deliverables, created_at="2026-06-01T00:00:00+00:00")


def test_ph_steps_present_and_ordered_football():
    keys = [s.key for s in pipeline.resolve_steps(_cfg("football", ["player_highlights"]))]
    for k in ("involvement", "clip-candidates", "tagging_pending", "reels"):
        assert k in keys
    assert keys.index("clip-candidates") < keys.index("tagging_pending") < keys.index("reels")
    assert "follow-cam" in keys  # PH needs follow_cam even without events


def test_ph_steps_present_basketball():
    keys = [s.key for s in pipeline.resolve_steps(_cfg("basketball", ["player_highlights"]))]
    for k in ("involvement", "clip-candidates", "tagging_pending", "reels", "follow-cam"):
        assert k in keys


def test_coach_only_has_no_ph_or_followcam_football():
    keys = [s.key for s in pipeline.resolve_steps(_cfg("football", ["coach_analytics"]))]
    assert "tagging_pending" not in keys and "reels" not in keys
    assert "follow-cam" not in keys


def test_tagging_pending_step_builds_none(tmp_path):
    steps = {s.key: s for s in pipeline.resolve_steps(_cfg("football", ["player_highlights"]))}
    built = steps["tagging_pending"].build(
        pipeline.StepCtx(job_dir=tmp_path, job_id="j", sport="football"))
    assert built is None
```

- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** — generalize `resolve_steps` deliverable check; add the PH steps to both sport lists; set follow-cam deliverable to the set. Update `stage_label` to include `"player_highlights"` ("Building player reels") and keep `"tagging_pending"` ("Waiting for player names"). For football, `follow-cam` already exists in the events tail — change its `deliverable` to `{"event_highlights","player_highlights"}` and ensure it's only listed once.
- [ ] **Step 4: Run → pass**, plus full `tests/backend` suite green.
- [ ] **Step 5: Commit** `feat(backend): player-highlights pipeline steps + set-valued deliverable filter`

---

## Task 2: worker — tagging pause + resume

**Files:** Modify `backend/worker.py`; Create `tests/backend/test_worker_tagging.py`

**Design:** In `run_one`:
- Compute a resume start index. Read the job row's `stage`; if it equals the sentinel `"tagging_done"`, set `start_idx` to the index AFTER the `tagging_pending` step (skip all already-done foundation/part-1 steps). Else `start_idx = 0`.
- Iterate `steps[start_idx:]`. For the `tagging_pending` step: write status `state="tagging_pending", stage="tagging_pending"` and **return** (park). Do not run a command.
- All other steps run via `run_step` as today. On completion, `ready`.
- The `reels` step runs only after resume (it's after `tagging_pending`).

- [ ] **Step 1: Failing test** `tests/backend/test_worker_tagging.py`:
```python
from backend import db, pipeline, worker
from backend.jobs import JobStore


def _queued_ph_job(store):
    cfg = store.create(sport="football", match_name="x", match_date="2026-06-01")
    store.update_config(cfg.job_id, deliverables_requested=["player_highlights"])
    store.write_status(cfg.job_id, state="queued", stage=None, progress=0,
                       stage_label=None, error=None)
    return cfg.job_id


def test_parks_at_tagging_pending(tmp_path, monkeypatch):
    store = JobStore(tmp_path); jid = _queued_ph_job(store)
    ran = []
    monkeypatch.setattr(pipeline, "run_step", lambda step, ctx, logs: ran.append(step.key))
    worker.Worker(store).run_one()
    row = db.get_job(store.conn, jid)
    assert row["state"] == "tagging_pending"
    assert "reels" not in ran            # reels not run before tagging
    assert "involvement" in ran          # part-1 ran


def test_resume_runs_only_reels(tmp_path, monkeypatch):
    store = JobStore(tmp_path); jid = _queued_ph_job(store)
    monkeypatch.setattr(pipeline, "run_step", lambda step, ctx, logs: None)
    w = worker.Worker(store); w.run_one()                 # parks
    # simulate /tags: re-enqueue with the resume sentinel
    store.write_status(jid, state="queued", stage="tagging_done", progress=50,
                       stage_label=None, error=None)
    ran = []
    monkeypatch.setattr(pipeline, "run_step", lambda step, ctx, logs: ran.append(step.key))
    w.run_one()                                            # resumes
    row = db.get_job(store.conn, jid)
    assert row["state"] == "ready"
    assert ran == ["reels"]              # ONLY reels re-ran (foundation skipped)
```

- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** the resume-index + pause logic in `run_one`. Keep the failure-path (friendly error + log) and `start()/stop()/_loop()`.
- [ ] **Step 4: Run → pass**, full suite green.
- [ ] **Step 5: Commit** `feat(backend): worker tagging pause + resume-to-reels`

---

## Task 3: API — `/tagging-clips` + `/tags`

**Files:** Modify `backend/main.py`, `backend/jobs.py`; Create `tests/backend/test_api_tagging.py`

**Design:**
- `jobs.py`: add `clips_manifest_path(job_id)` → `player_highlights/<id>/clips_manifest.json`; `write_clip_tags(job_id, tags: dict)` → writes `player_highlights/<id>/clip_tags.json`; `clip_path(job_id, clip)` → `player_highlights/<id>/clips/<clip>` with traversal guard.
- `GET /api/jobs/{id}/tagging-clips` → read `clips_manifest.json`; return a list of `{clip_id, track_id, role, start_frame, end_frame, video_url}` where `video_url = /api/jobs/{id}/tagging-clips/{clip_id}/video`. If the manifest doesn't exist yet (job not at tagging_pending), return `{"ready": false, "clips": []}`.
- `GET /api/jobs/{id}/tagging-clips/{clip}/video` → serve the clip mp4 (FileResponse, traversal-guard `clip`).
- `POST /api/jobs/{id}/tags` `{player_tags: {clip_id: name}}` → persist into job_config (existing) AND write `clip_tags.json` via `jobs.write_clip_tags` AND re-enqueue: `store.write_status(id, state="queued", stage="tagging_done", ...)` so the worker resumes to reels. (Only meaningful when state was `tagging_pending`; if not, still persist tags.)

- [ ] **Step 1: Failing test** `tests/backend/test_api_tagging.py` (uses the conftest `client`, monkeypatches `pipeline.run_step` to write a fake manifest + clip so the flow is GPU-free):
```python
import json


def _ph_job(client):
    return client.post("/api/jobs", json={"sport": "football", "match_name": "x",
        "match_date": "2026-06-01"}).json()["job_id"]


def test_tagging_clips_empty_before_pause(client):
    jid = _ph_job(client)
    r = client.get(f"/api/jobs/{jid}/tagging-clips")
    assert r.status_code == 200
    assert r.json()["clips"] == []


def test_tags_writes_clip_tags_and_requeues(client):
    jid = _ph_job(client)
    store = client.app.state.store
    # simulate a parked job with a manifest + one clip on disk
    ph = store.job_dir(jid) / "player_highlights" / jid
    (ph / "clips").mkdir(parents=True)
    (ph / "clips" / "t001_m00_5s.mp4").write_bytes(b"fakeclip")
    (store.job_dir(jid) / "player_highlights" / jid / "clips_manifest.json").write_text(
        json.dumps([{"clip_id": "t001_m00_5s.mp4", "track_id": 1, "role": "TeamA",
                     "start_frame": 1, "end_frame": 50}]))
    store.write_status(jid, state="tagging_pending", stage="tagging_pending",
                       progress=60, stage_label=None, error=None)

    listing = client.get(f"/api/jobs/{jid}/tagging-clips").json()
    assert listing["clips"][0]["clip_id"] == "t001_m00_5s.mp4"
    assert listing["clips"][0]["video_url"].endswith("/t001_m00_5s.mp4/video")
    vid = client.get(f"/api/jobs/{jid}/tagging-clips/t001_m00_5s.mp4/video")
    assert vid.status_code == 200 and vid.content == b"fakeclip"

    r = client.post(f"/api/jobs/{jid}/tags",
                    json={"player_tags": {"t001_m00_5s.mp4": "Alex"}})
    assert r.status_code == 200
    tags = json.loads((ph / "clip_tags.json").read_text())
    assert tags == {"t001_m00_5s.mp4": "Alex"}
    assert client.get(f"/api/jobs/{jid}/status").json()["state"] == "queued"
```

- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** the `jobs.py` helpers + the three routes in `main.py` (traversal-guard the `{clip}` param like the outputs download). 
- [ ] **Step 4: Run → pass**, full suite green.
- [ ] **Step 5: Commit** `feat(backend): tagging-clips listing/video + tags write + re-enqueue`

---

## Task 4: frontend — re-enable + wire the tagging flow

**Files:** Modify `Website/app.js`, `Website/index.html`

**Design (preserve visuals; the tagging screen `v-roster` already exists from the mockup — wire it):**
- `app.js`: add `API.getTaggingClips(id)`, `API.tagClipVideoUrl(id, clip)`, and update `setTags` to POST `{player_tags}` to `/tags`.
- Deliverables card: remove the `.soon` / "Coming soon" treatment from `player_highlights` (Task 5 of Plan 2 added it) so it's selectable again.
- Routing: when `player_highlights` is among the selected deliverables, the court "Confirm" should route to `roster` (the roster+tagging screen) instead of straight to `deliverables`; the roster screen's "continue" goes to `deliverables`. When PH is NOT selected, keep court→deliverables. (Simplest: court always → deliverables; the **tagging** screen is reached from the processing screen when the job hits `tagging_pending` — see next.)
- **Tagging is driven by job state, not pre-collected:** the operator can't tag until the pipeline has generated clips. So: Processing screen poll — when `state === "tagging_pending"`, navigate to the tagging screen (`go('roster')` or a dedicated tagging view) and load real clips from `GET /tagging-clips`. Wire the existing `tagRoster` buttons (roster names) + `clipStage`/`clipTrack` to show each real clip's video; "tag" calls accumulate `{clip_id: name}`; a "Done tagging" action `POST /tags` → returns to processing (which resumes polling → reels → ready).
- Roster: the roster names the operator entered (Plan 2 `saveRoster`) populate the tag buttons. Ensure roster is collected before processing (the roster screen, reachable in the flow, or a roster step before generate).
- Results: the player-reels grid (`playerGrid`) — replace the Plan-2 "coming soon" note with real reels from `GET /outputs` filtered to the `player_highlights/` reel files, each a download link.

**Note:** keep it functional and on-design; per-clip tagging is fine for the MVP (bulk-by-track is a Plan-5 nicety — the basketball research flagged full-match volume, but short clips here produce few clips).

- [ ] **Step 1:** `app.js` — add `getTaggingClips`, `tagClipVideoUrl`, `setTags` (POST /tags). `node --check`; node tests still pass.
- [ ] **Step 2:** Deliverables — remove `player_highlights` coming-soon (card selectable + enqueues).
- [ ] **Step 3:** Processing → on `tagging_pending`, go to the tagging screen + load `/tagging-clips`; wire clip playback + roster-name tagging + "Done tagging" → `POST /tags` → back to processing.
- [ ] **Step 4:** Results — real player reels from `/outputs` (`player_highlights/*` files) with downloads.
- [ ] **Step 5:** Syntax-check inline JS (`node --check build/_inline.js`) + `node --test tests/frontend/api.test.mjs`. Manual note for Task 6 browser pass.
- [ ] **Step 6: Commit** `feat(frontend): wire player-highlights tagging flow + re-enable the deliverable`

---

## Task 5: end-to-end — football player highlights (GPU, two-part)

**Files:** Create `scripts/e2e_player_highlights_football.py`

Drives the real two-part flow without a browser: create job (sport football, deliverables `["player_highlights"]`), copy `clips/football.mp4`, set calibration + roster, enqueue, `worker.run_one()` → assert `state == tagging_pending` and `clips_manifest.json` exists; read the manifest, build a `{clip_id: roster_name}` map (tag each clip to a roster name, round-robin), `POST`-equivalent: write `clip_tags.json` via `store` + re-enqueue (`state=queued, stage=tagging_done`); `worker.run_one()` again → assert `state == ready` and at least one reel mp4 exists under `outputs/player_highlights/`.

- [ ] **Step 1:** Write the driver (mirror `e2e_football_pipeline.py`; two `run_one()` calls around a tag-writing step; use `JobStore` helpers directly — no HTTP needed).
- [ ] **Step 2: Run** `.venv\Scripts\python.exe scripts\e2e_player_highlights_football.py`. **Debug real-footage issues** via `build/e2e_jobs_ph/<id>/logs/<stage>.log` + systematic-debugging (expect a couple of GT/dir-degradation fixes like Plan 3 — additive guards only). Iterate per-stage against the existing job dir to avoid GPU re-runs. End on `E2E PH FOOTBALL: OK`.
- [ ] **Step 3:** Backend suite green.
- [ ] **Step 4: Commit** `test(pipeline): two-part player-highlights football e2e`

---

## Task 6: end-to-end — basketball player highlights (GPU, two-part)

**Files:** Create `scripts/e2e_player_highlights_basketball.py`

Same as Task 5 with sport `basketball`, `clips/basketball.mp4`, the `_bb` chain. Note the basketball research caveats: presence-fallback clips (`p{tid}_presence.mp4`) may appear in the manifest — tag or `__skip__` them; `assemble_player_reels_bb` is safe to re-run.

- [ ] **Step 1:** Write the driver.
- [ ] **Step 2: Run + debug** to `E2E PH BASKETBALL: OK`.
- [ ] **Step 3:** Backend suite green.
- [ ] **Step 4: Commit** `test(pipeline): two-part player-highlights basketball e2e`

---

## Self-Review (completed during plan authoring)

**Spec coverage:** `tagging_pending` pause in the state machine (§3) — Task 2 ✅; player_highlights two-part (generate→pause→assemble) (§5) — Tasks 1-2 ✅; `GET /tagging-clips` + `POST /tags` (§4) — Task 3 ✅; frontend tagging screen wired + card re-enabled — Task 4 ✅; both sports — Tasks 5-6 ✅; tags contract `{clip_id: player_name}` written to the path the scripts read — Task 3 (research-confirmed shape) ✅.

**Placeholder scan:** no TBD/TODO; commands are concrete (arg names cross-referenced to the research docs; implementers confirm via `--help`).

**Type/name consistency:** reuses `Step`/`StepCtx`/`resolve_steps`/`run_step`; generalizes `Step.deliverable` to `None|str|set` consistently in `resolve_steps`. Sentinel `"tagging_done"` used by `/tags` (Task 3) and the worker resume (Task 2) — same string. `clip_tags.json` path identical in jobs.py, the worker's `reels` step input, and the e2e drivers.

**Honest gaps (flagged):** identity fragmentation (Days 26/30/31/32) means many clips at full-match scale → tagging is high-volume (Day-31: thousands/half). Plan 4 builds the *mechanism* and validates on short clips (few clips); bulk-by-track tagging UX is a Plan-5 nicety. Reel *quality* (correct player per clip) depends on the operator's tags + track continuity — footage-gated, the agreed tag-per-clip workaround. No CV-script edits expected (research) — if the e2e surfaces one, keep it minimal/additive.

**Risk:** Tasks 5-6 are the iteration points (real footage). Reuse the Plan-3 fast-debug loop (re-run single stages against `build/e2e_jobs_ph*`). The frontend tagging UX (Task 4) is state-driven (reached on `tagging_pending`) — verify the processing→tagging→processing→results transition in the Task-6 browser pass.
