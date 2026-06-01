# Operator App Backend — Plan 3-basketball: Basketball Chain

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the **basketball** CV chain into the existing pipeline engine so a basketball job produces a real coach-analytics PDF + event-highlight clips from an uploaded video + 4 marked corners — reusing everything built for football (decode + homography adapters, landmark templates, the subprocess engine, the worker).

**Architecture:** Add a `_basketball_steps()` step list to `pipeline.PIPELINES` (the engine already dispatches per `cfg.sport`). Basketball differs from football: it uses the **detection-cache + ByteTrack** tracker (`build_det_cache` → `track_from_cache`) instead of `track_alfheim`, a **separate ball-detection pass** (`build_det_cache` with the ball model → `analyze_ball_basketball`), **ResNet18-embedding** team assignment (`bball_team_embed`), and `follow_cam_basketball`. Two existing scripts need minimal additive edits: `bball_team_embed.py` (`--seq` to replace its hardcoded SportsMOT `SEQS` list) and `detect_events_basketball.py` (`--homography` + `--teams` to replace two CWD-relative hardcoded paths). `coach_deliverable_basketball.py` needs no edit — just `--win 1 <total_frames>`. The homography step writes `homography.json` to the job root AND copies it to `outputs/deliverables/<seq>/court/homography.json` where `coach_deliverable_basketball` looks for it.

**Tech Stack:** same as Plan 3 football. Models: `models/basketball_player.pt` (players), `models/basketball_ft.pt` (ball) — both present. Team assignment auto-downloads torchvision ResNet18 on first run. Test footage: `clips/basketball.mp4` (short).

**Spec:** `docs/superpowers/specs/2026-05-31-operator-app-backend-design.md`
**Research (authoritative):** `docs/superpowers/research/2026-05-31-plan3-basketball-chain.md` — exact CLI args, the 2 hardcoded-path couplings, the two-track-dir note, the `--win` override, job-dir layout.
**Builds on:** Plan 3 football (DONE) — engine, adapters, landmarks, worker all exist and are sport-agnostic.

---

## Basketball chain (job dir `jobs/<id>/`, seq = `<id>`)

| # | UI stage | key | script / adapter | edit? |
|---|----------|-----|------------------|-------|
| 1 | decoding | decode | `adapters.decode_video` | reuse |
| — | decoding | homography | `write_homography` + copy to `outputs/deliverables/<id>/court/homography.json` | reuse + copy |
| 2 | detecting | detect-players | `build_det_cache.py --detector basketball_player.pt --class-name player` | none |
| 3 | tracking | track-players | `track_from_cache.py` | none |
| 4 | ball | ball-cache | `build_det_cache.py --detector basketball_ft.pt --class-name ball` | none |
| 5 | ball | ball-kalman | `analyze_ball_basketball.py --require-player --motion-consistency` | none |
| 6 | teams | team-assign | `bball_team_embed.py --seq <id>` | **add `--seq`** |
| 7 | analytics | coach | `coach_deliverable_basketball.py --win 1 <N> --no-video` | none (CLI) |
| 8 | events | follow-cam | `follow_cam_basketball.py --no-render` | none |
| 9 | events | detect-events | `detect_events_basketball.py --homography … --teams …` | **add `--homography` + `--teams`** |
| 10 | events | clip | `clip_highlights_basketball.py --crop ball` | none |

`coach_analytics` = steps 1–7. `event_highlights` = steps 1–6, 8, 9, 10. Shared foundation = 1–6.

**Two-track-dir note:** the originals default to different track dirs (`botsort_gmc` vs `bytetrack`); the backend sidesteps this by producing ONE player-track dir (`tracks/players`) via `track_from_cache` and passing it explicitly as `--track-dir`/`--track` to every consumer.

---

## File Structure

```
scripts/
  bball_team_embed.py          # MODIFIED — add --seq (replace hardcoded SEQS)
  detect_events_basketball.py  # MODIFIED — add --homography + --teams args
backend/
  pipeline.py                  # MODIFIED — add _basketball_steps() + register in PIPELINES
tests/backend/
  test_pipeline_basketball.py  # NEW — step-list + argv tests (no GPU)
scripts/
  e2e_basketball_pipeline.py   # NEW — real end-to-end on clips/basketball.mp4 (GPU)
```

---

## Conventions
- Windows/PowerShell, repo root `C:\sports-ai`, interpreter `.venv\Scripts\python.exe`.
- Additive, minimal edits to CV scripts; verify each still parses (`--help`). Commit after each task.

---

## Task 1: `bball_team_embed.py` — add `--seq`

**Files:** Modify `scripts/bball_team_embed.py`

Research: `SEQS` hardcoded ~line 38, `COURT_SEQ` ~line 40. The script iterates the hardcoded SportsMOT list and applies a court filter only to `COURT_SEQ`.

**Edit spec (additive):**
- Add `ap.add_argument("--seq", default=None, help="single seq to process (overrides the hardcoded SEQS list)")`.
- After parse: if `args.seq`, set the working list to `[args.seq]` and set the court-filter seq to `args.seq` (so the homography/off-court filter applies to the job seq, not the SportsMOT `COURT_SEQ`). Rename the module constant to `SEQS_DEFAULT` and use a local `seqs`/`court_seq` everywhere the old `SEQS`/`COURT_SEQ` were used.
- Keep validation (`hand_labels.json`/`crops.npz`) graceful-skip as-is.

- [ ] **Step 1:** Read `scripts/bball_team_embed.py` — locate `SEQS`, `COURT_SEQ`, their uses, and the `--court` homography handling.
- [ ] **Step 2:** Apply the additive edit (`--seq` → `seqs=[args.seq]`, `court_seq=args.seq`).
- [ ] **Step 3:** Verify: `.venv\Scripts\python.exe scripts/bball_team_embed.py --help` exits 0 and lists `--seq`.
- [ ] **Step 4: Commit** `feat(pipeline): bball_team_embed --seq (single-job seq override)`

---

## Task 2: `detect_events_basketball.py` — add `--homography` + `--teams`

**Files:** Modify `scripts/detect_events_basketball.py`

Research: `load_homography(seq)` reads hardcoded `outputs/deliverables/{seq}/court/homography.json` (~line 91); `load_teams(seq, path=...)` hardcoded to `outputs/team_assign_bb/track_teams_emb.json` (~line 113). Both CWD-relative.

**Edit spec (additive):**
- Add `ap.add_argument("--homography", default=None)` and `ap.add_argument("--teams", default=None)`.
- In `load_homography`: if a `--homography` path was provided, read that; else the original hardcoded path. Thread `args.homography` into the call (pass it in, or read a module-level set from args).
- In `load_teams`: default to `args.teams` when provided, else the original path.
- Keep `SEQS_DEFAULT` positional-override behavior unchanged.

- [ ] **Step 1:** Read `scripts/detect_events_basketball.py` — `main()`, `load_homography`, `load_teams`, how seq is obtained.
- [ ] **Step 2:** Apply additive edits so the two paths are overridable; default to old behavior when omitted.
- [ ] **Step 3:** Verify: `.venv\Scripts\python.exe scripts/detect_events_basketball.py --help` exits 0 and lists `--homography` + `--teams`.
- [ ] **Step 4: Commit** `feat(pipeline): detect_events_basketball --homography + --teams`

---

## Task 3: `pipeline.py` — `_basketball_steps()` + register

**Files:** Modify `backend/pipeline.py`; Create `tests/backend/test_pipeline_basketball.py`

- [ ] **Step 1: Failing test** `tests/backend/test_pipeline_basketball.py`:
```python
from backend import pipeline
from backend.schemas import JobConfig


def _cfg(deliverables):
    return JobConfig(job_id="bjob", sport="basketball", match_name="x",
        match_date="2026-06-01", video_path="raw_video.mp4",
        calibration_points=[], roster=[], player_tags={},
        deliverables_requested=deliverables, created_at="2026-06-01T00:00:00+00:00")


def test_basketball_coach_steps():
    keys = [s.key for s in pipeline.resolve_steps(_cfg(["coach_analytics"]))]
    assert keys[:2] == ["decode", "homography"]
    assert "detect-players" in keys and "track-players" in keys
    assert "team-assign" in keys and "coach" in keys
    assert "clip" not in keys and "detect-events" not in keys


def test_basketball_events_steps():
    keys = [s.key for s in pipeline.resolve_steps(_cfg(["event_highlights"]))]
    assert "follow-cam" in keys and "detect-events" in keys and "clip" in keys
    assert "coach" not in keys


def test_basketball_both_dedupes_foundation():
    keys = [s.key for s in pipeline.resolve_steps(_cfg(["coach_analytics", "event_highlights"]))]
    assert keys.count("track-players") == 1 and keys.count("team-assign") == 1
    assert "coach" in keys and "clip" in keys


def test_basketball_team_assign_argv(tmp_path):
    steps = {s.key: s for s in pipeline.resolve_steps(_cfg(["coach_analytics"]))}
    argv = steps["team-assign"].build(pipeline.StepCtx(job_dir=tmp_path, job_id="bjob",
                                                       sport="basketball"))
    j = " ".join(argv)
    assert "bball_team_embed.py" in j and "--seq" in j and "bjob" in j
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement** in `backend/pipeline.py`. Add a helper to read seqLength for the coach `--win`, the basketball homography step (write + copy to court dir), and `_basketball_steps()`. Register in `PIPELINES`.

```python
import configparser
import shutil

def _seqlen(job_dir, seq) -> int:
    ini = job_dir / "frames" / seq / "seqinfo.ini"
    cp = configparser.ConfigParser(); cp.read(ini)
    try:
        return int(cp["Sequence"]["seqLength"])
    except Exception:
        return 100000  # fallback; coach clamps to available frames


def _basketball_steps() -> list[Step]:
    from backend import adapters
    from backend.schemas import JobConfig as _JC

    def decode(ctx):
        return lambda: adapters.decode_video(
            ctx.job_dir / "raw_video.mp4", ctx.job_dir / "frames", seq=ctx.job_id)

    def homography(ctx):
        def _run():
            cfg = _JC.model_validate_json(
                (ctx.job_dir / "job_config.json").read_text(encoding="utf-8"))
            payload = adapters.write_homography(
                [p.model_dump() for p in cfg.calibration_points], ctx.sport,
                ctx.job_dir / "homography.json")
            # coach_deliverable_basketball reads <deliverables>/<seq>/court/homography.json
            court = ctx.job_dir / "outputs" / "deliverables" / ctx.job_id / "court"
            court.mkdir(parents=True, exist_ok=True)
            shutil.copy(ctx.job_dir / "homography.json", court / "homography.json")
            return payload
        return _run

    J = lambda ctx, *p: str(ctx.job_dir.joinpath(*p))
    M = lambda name: str(config.MODELS_DIR / name)
    return [
        Step("decode", "decoding", None, decode),
        Step("homography", "decoding", None, homography),
        Step("detect-players", "detecting", None, lambda c: _py(
            _sd("build_det_cache.py"), "--detector", M("basketball_player.pt"),
            "--source", J(c, "frames"), "--out", J(c, "det_cache", "players"),
            "--class-name", "player", "--only", c.job_id)),
        Step("track-players", "tracking", None, lambda c: _py(
            _sd("track_from_cache.py"), "--cache", J(c, "det_cache", "players"),
            "--source", J(c, "frames"), "--out", J(c, "tracks", "players"))),
        Step("ball-cache", "ball", None, lambda c: _py(
            _sd("build_det_cache.py"), "--detector", M("basketball_ft.pt"),
            "--source", J(c, "frames"), "--out", J(c, "det_cache", "ball"),
            "--class-name", "ball", "--only", c.job_id)),
        Step("ball-kalman", "ball", None, lambda c: _py(
            _sd("analyze_ball_basketball.py"), c.job_id,
            "--cache-dir", J(c, "det_cache", "ball"), "--source", J(c, "frames"),
            "--out", J(c, "ball_track"), "--track-dir", J(c, "tracks", "players"),
            "--require-player", "--motion-consistency")),
        Step("team-assign", "teams", None, lambda c: _py(
            _sd("bball_team_embed.py"), "--seq", c.job_id,
            "--track", J(c, "tracks", "players"), "--frames-root", J(c, "frames"),
            "--court", J(c, "homography.json"), "--out", J(c, "team_assign"))),
        # coach_analytics tail
        Step("coach", "analytics", "coach_analytics", lambda c: _py(
            _sd("coach_deliverable_basketball.py"), c.job_id,
            "--win", "1", str(_seqlen(c.job_dir, c.job_id)),
            "--deliverables", J(c, "outputs", "deliverables"),
            "--track", J(c, "tracks", "players"), "--ball", J(c, "ball_track"),
            "--frames-root", J(c, "frames"),
            "--team-assign", J(c, "team_assign", "track_teams_emb.json"),
            "--no-video")),
        # event_highlights tail
        Step("follow-cam", "events", "event_highlights", lambda c: _py(
            _sd("follow_cam_basketball.py"), c.job_id,
            "--ball-dir", J(c, "ball_track"), "--track-dir", J(c, "tracks", "players"),
            "--source", J(c, "frames"), "--out", J(c, "follow_cam"), "--no-render")),
        Step("detect-events", "events", "event_highlights", lambda c: _py(
            _sd("detect_events_basketball.py"), c.job_id,
            "--ball-dir", J(c, "ball_track"), "--track-dir", J(c, "tracks", "players"),
            "--follow-dir", J(c, "follow_cam"), "--out", J(c, "events"),
            "--homography", J(c, "homography.json"),
            "--teams", J(c, "team_assign", "track_teams_emb.json"))),
        Step("clip", "events", "event_highlights", lambda c: _py(
            _sd("clip_highlights_basketball.py"), c.job_id,
            "--events-dir", J(c, "events"), "--follow-dir", J(c, "follow_cam"),
            "--source", J(c, "frames"), "--ball-dir", J(c, "ball_track"),
            "--out", J(c, "outputs", "event_highlights"), "--crop", "ball")),
    ]
```
Register: `PIPELINES = {"football": _football_steps, "basketball": _basketball_steps}`.

- [ ] **Step 4: Run → pass** (`tests/backend/test_pipeline_basketball.py`, no GPU). Also run the full `tests/backend` suite — still green.

- [ ] **Step 5: Commit** `feat(backend): basketball pipeline step list`

---

## Task 4: End-to-end basketball run on real footage (GPU)

**Files:** Create `scripts/e2e_basketball_pipeline.py` (clone of the football driver; sport="basketball", clip=`clips/basketball.mp4`, asserts a `*.pdf` under coach + an `event_highlights` artifact).

- [ ] **Step 1: Write the driver** — identical structure to `scripts/e2e_football_pipeline.py` but:
  - `CLIP = ROOT / "clips" / "basketball.mp4"`, `sport="basketball"`, `jobs_dir = ROOT/"build"/"e2e_jobs_bb"`.
  - calibration corners approximate to the basketball clip's dimensions (read them with cv2 first, or use generous inset corners).
  - asserts `row["state"] == "ready"`, a `.pdf` exists, and an `event_highlights` file exists.

- [ ] **Step 2: Run** `.venv\Scripts\python.exe scripts\e2e_basketball_pipeline.py`. Expect stage progress then `E2E BASKETBALL PIPELINE: OK`. **Debug real-footage failures** via `build/e2e_jobs_bb/<id>/logs/<stage>.log` + systematic-debugging — expect a few (analogous to football's GT-degradation fixes; e.g. team-assign validation skip, coach footnote, ResNet18 first-download). Fix each with a minimal additive edit; re-run (use the same per-stage manual re-run trick to avoid full GPU re-runs). Do NOT fake success.

- [ ] **Step 3: Backend suite green** `.venv\Scripts\python.exe -m pytest tests/backend -q`.

- [ ] **Step 4: Commit** `test(pipeline): real end-to-end basketball run on sample clip`

---

## Self-Review (completed during plan authoring)

**Spec coverage:** basketball coach_analytics + event_highlights wired to run on uploaded footage (spec §5, both-sports scope) — Tasks 3-4 ✅; reuses decode + homography adapters + landmarks (basketball template already in `landmarks.py`) ✅; minimal additive script edits (`--seq`, `--homography`/`--teams`) ✅; engine dispatches per sport (already built) ✅.

**Placeholder scan:** no TBD/TODO; edit tasks give the exact additive pattern + `--help` verification; the step list is concrete argv.

**Type/name consistency:** reuses `Step`/`StepCtx`/`resolve_steps`/`run_step`/`_py`/`_sd`/`config.MODELS_DIR` from the football engine. New `_basketball_steps`/`_seqlen` added. `PIPELINES` extended. `adapters.write_homography`/`decode_video` reused.

**Honest gaps (flagged):** basketball homography is fragile under camera pan (holds only seconds on panning footage) — fine for a FIXED school camera (the deployment target); the short `clips/basketball.mp4` may pan, so calibration accuracy on the test clip is indicative, not production-representative. Team validation (hand-labels) is skipped (no labels for uploaded footage). Ball recall is footage-gated as with football. The plumbing producing a PDF + clips is the deliverable here; quality validates on the real DPS court.

**Risk note:** Task 4 is the iteration point (as football was). `bball_team_embed` downloads ResNet18 on first run (needs internet once). The `--win` end is read from seqinfo seqLength; if `coach_deliverable_basketball` interprets `--win` end-exclusive or 0-indexed, adjust by ±1 (check on first run).
