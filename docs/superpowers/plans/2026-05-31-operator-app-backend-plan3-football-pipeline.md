# Operator App Backend — Plan 3: Real Pipeline Engine + Football Chain

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Plan-1 stub pipeline with the REAL CV pipeline for **football**, so a job produces actual deliverables — a coach-analytics PDF + tactical figures and ranked event-highlight clips — from an uploaded football video + 4 marked calibration points. Build the sport-agnostic engine (decode + homography adapters, a real subprocess stage-runner, a per-sport pipeline definition) so **Plan 3-basketball** can reuse it.

**Architecture:** Two new adapters in `backend/` turn a job's raw inputs into the shapes the existing CV scripts expect: `decode_video` (mp4 → `frames/<seq>/img1/%06d.jpg` + `seqinfo.ini`) and `write_homography` (4 calibration points + a per-sport landmark template → `homography.json` in the `mark_court.py` schema). `pipeline.py` gains a real `run_step` subprocess runner and a per-sport ordered step list (each step = a UI stage tag + an argv builder pointed at the job dir). The worker runs adapters + subprocess steps in order, capturing output to `logs/<stage>.log` and surfacing friendly failures. The existing football scripts get **minimal, sanctioned edits** (per spec §2: "scripts get adapted minimally to accept this config") to break three GT/SoccerNet couplings: add `--homography` to `analyze_ball.py`/`analyze_pitch.py`/`compute_possession.py` (use a static marked H instead of GT-derived per-frame H), and add `--seqs` to `team_assign.py` (replace the hardcoded SoccerNet sequence list). No CV/ML logic is reimplemented — only input plumbing.

**Tech Stack:** Python 3.11.9 `.venv` (torch/opencv/ultralytics + FastAPI), cv2 for frame decode, `cv2.findHomography` for calibration, subprocess for stage execution, pytest. Test footage: `clips/football.mp4` (540 frames, 29.97 fps, 1280×720 — short, GPU-fast).

**Spec:** `docs/superpowers/specs/2026-05-31-operator-app-backend-design.md` (§2, §5)
**Research:** `docs/superpowers/research/2026-05-31-plan3-football-chain.md` (authoritative — exact script interfaces, GT couplings, decode layout, homography schema)
**Builds on:** Plans 1 (skeleton+stub) and 2 (frontend wiring), both DONE.

---

## What the engine must run (from the research doc)

Football chain (job dir `jobs/<id>/`, seq name = `<id>`):

| # | UI stage | Step | Script / adapter | Needs edit? |
|---|----------|------|------------------|-------------|
| 1 | decoding | decode | `adapters.decode_video` (mp4 → `frames/<id>/img1/%06d.jpg` + seqinfo.ini) | new adapter |
| — | decoding | homography | `adapters.write_homography` (calibration → `homography.json`) | new adapter |
| 2 | tracking | players | `track_alfheim.py --video … --classes 0` | none (takes mp4) |
| 3 | ball | ball-cache | `build_det_cache.py --class-name ball` | none (needs frames+seqinfo ✓) |
| 4 | ball | ball-kalman | `analyze_ball.py --homography …` | **add `--homography`** |
| 5 | tracking | pitch-proj | `analyze_pitch.py --homography …` | **add `--homography`** |
| 6 | teams | team-assign | `team_assign.py --seqs <id> …` | **add `--seqs`** + skip GT validation |
| 7 | analytics | possession | `compute_possession.py --homography …` | **add `--homography`** |
| 8 | analytics | coach | `coach_deliverable.py … --contact-only` | none (pure CLI) |
| 9 | events | detect-events | `detect_events.py --zip "" …` | none (`--zip ""` skips GT) |
| 10 | events | follow-cam | `follow_cam.py --gt-zip "" --no-render` | none |
| 11 | events | clip | `clip_highlights.py …` | none |

`coach_analytics` deliverable = steps 1–8. `event_highlights` = steps 1–6,9,10,11. Shared foundation = 1–6.

---

## File Structure

```
backend/
  landmarks.py      # NEW — per-sport label -> real-world-metre templates
  adapters.py       # NEW — decode_video(), write_homography()
  pipeline.py       # MODIFIED — real run_step() + football PIPELINE step list (replaces stub)
  worker.py         # MODIFIED — run adapter steps + subprocess steps in order
  config.py         # MODIFIED — PYTHON_EXE, SCRIPTS_DIR, MODELS paths
scripts/
  analyze_ball.py        # MODIFIED — add --homography (static H)
  analyze_pitch.py       # MODIFIED — add --homography
  compute_possession.py  # MODIFIED — add --homography
  team_assign.py         # MODIFIED — add --seqs, guard GT validation
tests/backend/
  test_landmarks.py        # NEW
  test_adapters.py         # NEW
  test_pipeline_football.py# NEW (step-list resolution + argv building, no GPU)
scripts/
  e2e_football_pipeline.py # NEW — real end-to-end on clips/football.mp4 (GPU)
```

**Decoupling note:** the script edits are additive (`--homography`, `--seqs` default to the old behavior when omitted), so the scripts still run on SoccerNet exactly as before — no regression to existing research workflows.

---

## Conventions
- Windows/PowerShell, repo root `C:\sports-ai`. Interpreter `.venv\Scripts\python.exe` for everything.
- Commit after each task with the shown message.
- The CV scripts are real research code — make **additive, minimal** edits; never restructure their logic. After editing a script, run it `--help` to confirm it still parses.

---

## Task 1: `landmarks.py` — per-sport calibration templates

The frontend collects 4 corner points with labels `far-left corner`, `far-right corner`, `near-right corner`, `near-left corner` (see `CALIB_PTS` in index.html). Map each label to real-world metres per sport.

**Files:** Create `backend/landmarks.py`, `tests/backend/test_landmarks.py`

- [ ] **Step 1: Failing test**

`tests/backend/test_landmarks.py`:
```python
from backend import landmarks


def test_football_has_four_corners_in_metres():
    t = landmarks.template("football")
    assert set(t) == {"far-left corner", "far-right corner",
                      "near-right corner", "near-left corner"}
    # FIFA pitch 105 x 68 m, centre origin -> corners at (+/-52.5, +/-34)
    xs = sorted({abs(x) for x, y in t.values()})
    ys = sorted({abs(y) for x, y in t.values()})
    assert xs == [52.5] and ys == [34.0]


def test_basketball_has_four_corners():
    t = landmarks.template("basketball")
    assert set(t) == {"far-left corner", "far-right corner",
                      "near-right corner", "near-left corner"}


def test_world_points_orders_to_labels():
    labels = ["far-left corner", "near-left corner"]
    pts = landmarks.world_points("football", labels)
    assert pts == [list(landmarks.template("football")[l]) for l in labels]
```

- [ ] **Step 2: Run → fail** (`.venv\Scripts\python.exe -m pytest tests/backend/test_landmarks.py -v`)

- [ ] **Step 3: Implement** `backend/landmarks.py`:
```python
"""Per-sport calibration landmark templates: map the frontend's corner labels
to real-world metre coordinates (centre-origin). Used to build the homography
from the operator's 4 marked points."""
from __future__ import annotations

# FIFA pitch 105 x 68 m -> corners at (+/-52.5, +/-34). "far" = top of frame
# (positive y), "near" = bottom (negative y); left = negative x.
_FOOTBALL = {
    "far-left corner": (-52.5, 34.0),
    "far-right corner": (52.5, 34.0),
    "near-right corner": (52.5, -34.0),
    "near-left corner": (-52.5, -34.0),
}
# FIBA court 28 x 15 m -> corners at (+/-14.0, +/-7.5).
_BASKETBALL = {
    "far-left corner": (-14.0, 7.5),
    "far-right corner": (14.0, 7.5),
    "near-right corner": (14.0, -7.5),
    "near-left corner": (-14.0, -7.5),
}
_TEMPLATES = {"football": _FOOTBALL, "basketball": _BASKETBALL}


def template(sport: str) -> dict[str, tuple[float, float]]:
    return _TEMPLATES[sport]


def world_points(sport: str, labels: list[str]) -> list[list[float]]:
    t = template(sport)
    return [list(t[label]) for label in labels]
```

- [ ] **Step 4: Run → pass.** **Step 5: Commit** `feat(backend): per-sport calibration landmark templates`

---

## Task 2: `adapters.py` — decode + homography

**Files:** Create `backend/adapters.py`, `tests/backend/test_adapters.py`

- [ ] **Step 1: Failing test** `tests/backend/test_adapters.py`:
```python
import json
import configparser

import cv2
import numpy as np

from backend import adapters


def _make_mp4(path, n=8, w=64, h=48):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (w, h))
    for i in range(n):
        vw.write(np.full((h, w, 3), i, dtype=np.uint8))
    vw.release()


def test_decode_writes_frames_and_seqinfo(tmp_path):
    src = tmp_path / "v.mp4"; _make_mp4(src, n=8)
    info = adapters.decode_video(src, tmp_path / "frames", seq="job1")
    img1 = tmp_path / "frames" / "job1" / "img1"
    jpgs = sorted(img1.glob("*.jpg"))
    assert len(jpgs) == info["n_frames"] >= 1
    assert jpgs[0].name == "000001.jpg"          # 6-digit, 1-indexed
    ini = configparser.ConfigParser()
    ini.read(tmp_path / "frames" / "job1" / "seqinfo.ini")
    assert int(ini["Sequence"]["seqLength"]) == info["n_frames"]
    assert ini["Sequence"]["imDir"] == "img1"


def test_write_homography_solves_and_matches_schema(tmp_path):
    # four pixel corners of a 1000x500 image mapped to football pitch corners
    cal = [
        {"pixel_x": 0, "pixel_y": 0, "real_world_label": "far-left corner"},
        {"pixel_x": 1000, "pixel_y": 0, "real_world_label": "far-right corner"},
        {"pixel_x": 1000, "pixel_y": 500, "real_world_label": "near-right corner"},
        {"pixel_x": 0, "pixel_y": 500, "real_world_label": "near-left corner"},
    ]
    out = tmp_path / "homography.json"
    adapters.write_homography(cal, "football", out)
    h = json.loads(out.read_text())
    assert "H_court_from_img" in h and "H_img_from_court" in h
    H = np.array(h["H_court_from_img"], dtype=np.float64)
    assert H.shape == (3, 3)
    # a known pixel maps near its pitch metre target
    p = cv2.perspectiveTransform(np.array([[[0.0, 0.0]]], np.float32), H)[0][0]
    assert abs(p[0] - (-52.5)) < 1.0 and abs(p[1] - 34.0) < 1.0
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement** `backend/adapters.py`:
```python
"""Adapters that turn a job's raw inputs into the shapes the existing CV scripts
expect. NO CV logic — just decode + a homography solve."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from backend import landmarks


def decode_video(video_path: Path | str, frames_root: Path | str, *, seq: str,
                 frame_rate_default: float = 25.0) -> dict:
    """Extract frames to <frames_root>/<seq>/img1/%06d.jpg (1-indexed) and write
    seqinfo.ini. Returns {n_frames, width, height, frame_rate}."""
    video_path = Path(video_path)
    seq_dir = Path(frames_root) / seq
    img1 = seq_dir / "img1"
    img1.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    fr = cap.get(cv2.CAP_PROP_FPS) or frame_rate_default
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            n += 1
            cv2.imwrite(str(img1 / f"{n:06d}.jpg"), frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 92])
    finally:
        cap.release()

    (seq_dir / "seqinfo.ini").write_text(
        "[Sequence]\n"
        f"name={seq}\n"
        f"seqLength={n}\n"
        f"frameRate={round(fr) or 25}\n"
        "imDir=img1\n"
        "imExt=.jpg\n"
        f"imWidth={w}\n"
        f"imHeight={h}\n", encoding="utf-8")
    return {"n_frames": n, "width": w, "height": h, "frame_rate": fr}


def write_homography(calibration_points: list[dict], sport: str,
                     out_path: Path | str) -> dict:
    """Solve H from the 4 marked points + per-sport landmark template; write
    homography.json in the mark_court.py schema. H_court_from_img maps pixels
    -> pitch metres (the matrix downstream scripts feed to perspectiveTransform)."""
    labels = [p["real_world_label"] for p in calibration_points]
    src = np.array([[p["pixel_x"], p["pixel_y"]] for p in calibration_points],
                   dtype=np.float32)
    dst = np.array(landmarks.world_points(sport, labels), dtype=np.float32)
    H_ci, _ = cv2.findHomography(src, dst)   # pixel -> metres
    H_ic, _ = cv2.findHomography(dst, src)   # metres -> pixel
    payload = {
        "seq": None, "sport": sport,
        "H_court_from_img": H_ci.tolist(),
        "H_img_from_court": H_ic.tolist(),
        "points": [{"name": labels[i], "img": [float(src[i][0]), float(src[i][1])],
                    "court": [float(dst[i][0]), float(dst[i][1])]}
                   for i in range(len(labels))],
        "method": "operator-marked (4-corner findHomography)",
        "n_clicked": len(labels), "n_used": len(labels),
    }
    Path(out_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
```

- [ ] **Step 4: Run → pass.** **Step 5: Commit** `feat(backend): decode + homography adapters`

---

## Task 3: `analyze_ball.py` — add `--homography`

**Files:** Modify `scripts/analyze_ball.py`

**Edit spec (additive — preserves SoccerNet behavior when `--homography` omitted):**
- Read the script's `main()` and the region around `derive_per_frame_H(load_gt(...))` (research: ~lines 354-356) and the seqinfo n_frames read (~lines 332-334).
- Add CLI arg: `ap.add_argument("--homography", default=None, help="path to homography.json; use this static H instead of GT-derived per-frame H")`.
- Add a small helper near the top:
```python
def _static_H_by_frame(homography_path, n_frames):
    import json, numpy as np
    H = np.array(json.load(open(homography_path))["H_court_from_img"], dtype=np.float64)
    return {f: H for f in range(1, n_frames + 1)}
```
- Where `H_by_frame` is currently derived from GT, branch: if `args.homography` is set, `H_by_frame = _static_H_by_frame(args.homography, n_frames)` and SKIP `load_gt`/`derive_per_frame_H` and the GT-validation block (wrap the validation in `if not args.homography:` or `try/except`). Keep `project_trajectory(records, H_by_frame, ...)` unchanged.
- For seqinfo: if `--homography` is set and seqinfo.ini exists (decode writes it), the existing read works. Leave as-is (decode guarantees seqinfo.ini).

- [ ] **Step 1:** Read `scripts/analyze_ball.py` `main()` + the H-derivation + validation blocks.
- [ ] **Step 2:** Apply the additive edit above.
- [ ] **Step 3:** Verify it still parses and the new arg exists: `​.venv\Scripts\python.exe scripts/analyze_ball.py --help` → shows `--homography`. Exit 0.
- [ ] **Step 4: Commit** `feat(pipeline): analyze_ball --homography (static marked H, decouples from GT)`

---

## Task 4: `analyze_pitch.py` — add `--homography`

**Files:** Modify `scripts/analyze_pitch.py`

Same pattern as Task 3. Research: GT H derived ~line 221-227 (`derive_per_frame_H(load_gt(zip, seq))`). The GT-distance comparison (~254-263) is validation-only — guard it behind `if not args.homography:`.
- Add `--homography` arg (default None).
- Reuse a `_static_H_by_frame(path, n_frames)` helper (n_frames = max frame in the tracker MOT, or from seqinfo). When set, build the static H dict and skip GT load.

- [ ] **Step 1:** Read `analyze_pitch.py` `main()` + H block. Note how `n_frames` is known (derive from tracker if needed).
- [ ] **Step 2:** Apply additive edit.
- [ ] **Step 3:** `​.venv\Scripts\python.exe scripts/analyze_pitch.py --help` shows `--homography`, exit 0.
- [ ] **Step 4: Commit** `feat(pipeline): analyze_pitch --homography`

---

## Task 5: `compute_possession.py` — add `--homography`

**Files:** Modify `scripts/compute_possession.py`

Same pattern. Research: GT H ~lines 83-85. Add `--homography`; when set, static H dict; skip GT load.

- [ ] **Step 1:** Read `compute_possession.py` `main()` + H block.
- [ ] **Step 2:** Apply additive edit.
- [ ] **Step 3:** `--help` shows `--homography`, exit 0.
- [ ] **Step 4: Commit** `feat(pipeline): compute_possession --homography`

---

## Task 6: `team_assign.py` — add `--seqs`, guard GT validation

**Files:** Modify `scripts/team_assign.py`

Research: `SEQS = ["SNGS-116"..."SNGS-120"]` hardcoded at ~line 36; validation + heatmaps use the GT zip (~508-514).
- Add `ap.add_argument("--seqs", default=None, help="comma-separated seq names; overrides the hardcoded SoccerNet list")`.
- After parsing: `SEQS = args.seqs.split(",") if args.seqs else SEQS_DEFAULT` (rename the module constant to `SEQS_DEFAULT` or assign a local `seqs`). Use that local everywhere the old `SEQS` was used.
- Guard the GT-validation call and `render_team_heatmaps()` (which calls `derive_per_frame_H`) so a missing/empty zip doesn't crash: wrap in `try/except Exception: pass`, or `if Path(args.zip).exists():`. The core `track_teams.json` output must still be written.

- [ ] **Step 1:** Read `team_assign.py` — the `SEQS` constant, its uses, and Part D validation/heatmap calls.
- [ ] **Step 2:** Apply additive edits (seqs override + guarded validation).
- [ ] **Step 3:** `​.venv\Scripts\python.exe scripts/team_assign.py --help` shows `--seqs`, exit 0.
- [ ] **Step 4: Commit** `feat(pipeline): team_assign --seqs + guard GT validation`

---

## Task 7: `pipeline.py` — real `run_step` + football step list

**Files:** Modify `backend/pipeline.py`, `backend/config.py`; Create `tests/backend/test_pipeline_football.py`

**Design:** Replace the stub with a real engine. A PIPELINE per sport is an ordered list of `Step` objects; each Step has a `ui_stage` (one of the Plan-1 stage names, for status display), a `key` (unique), and a `build(ctx)` that returns either an argv list (subprocess) or a Python callable (for the decode/homography adapters). The worker runs them in order. `resolve_steps(cfg)` filters the per-deliverable steps like `resolve_stages` did.

- [ ] **Step 1: Add config paths.** In `backend/config.py` add:
```python
import sys as _sys
PYTHON_EXE: str = _sys.executable           # the venv interpreter running the server
SCRIPTS_DIR = REPO_ROOT / "scripts"
MODELS_DIR = REPO_ROOT / "models"
```

- [ ] **Step 2: Failing test** `tests/backend/test_pipeline_football.py`:
```python
from backend import pipeline
from backend.schemas import JobConfig


def _cfg(deliverables):
    return JobConfig(job_id="job1", sport="football", match_name="x",
        match_date="2026-05-31", video_path="raw_video.mp4",
        calibration_points=[], roster=[], player_tags={},
        deliverables_requested=deliverables, created_at="2026-05-31T00:00:00+00:00")


def test_coach_steps_include_foundation_and_coach():
    steps = pipeline.resolve_steps(_cfg(["coach_analytics"]))
    keys = [s.key for s in steps]
    assert keys[:2] == ["decode", "homography"]
    assert "players" in keys and "team-assign" in keys and "coach" in keys
    assert "clip" not in keys            # events-only step absent


def test_events_steps_include_clip_not_coach():
    steps = pipeline.resolve_steps(_cfg(["event_highlights"]))
    keys = [s.key for s in steps]
    assert "detect-events" in keys and "clip" in keys
    assert "coach" not in keys and "possession" not in keys


def test_both_dedupes_shared_foundation():
    steps = pipeline.resolve_steps(_cfg(["coach_analytics", "event_highlights"]))
    keys = [s.key for s in steps]
    assert keys.count("players") == 1 and keys.count("team-assign") == 1
    assert "coach" in keys and "clip" in keys


def test_argv_for_players_points_at_job_dir(tmp_path):
    steps = {s.key: s for s in pipeline.resolve_steps(_cfg(["coach_analytics"]))}
    argv = steps["players"].build(pipeline.StepCtx(job_dir=tmp_path, job_id="job1",
                                                   sport="football"))
    assert argv[0].endswith("python.exe") or "python" in argv[0]
    assert "track_alfheim.py" in " ".join(argv)
    assert "job1" in " ".join(argv) or str(tmp_path) in " ".join(argv)
```

- [ ] **Step 3: Run → fail.**

- [ ] **Step 4: Implement** the engine in `backend/pipeline.py`. Keep `stage_label()` (extend labels as needed). Replace `run_stage_stub`/`resolve_stages` with:
```python
from __future__ import annotations
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from backend import config, adapters
from backend.schemas import JobConfig


@dataclass
class StepCtx:
    job_dir: Path
    job_id: str
    sport: str


@dataclass
class Step:
    key: str
    ui_stage: str
    deliverable: str | None          # None = foundation (always runs)
    build: Callable[[StepCtx], object]  # returns argv list (subprocess) OR callable()


def _py(*args) -> list[str]:
    return [config.PYTHON_EXE, *[str(a) for a in args]]


def _sd(name: str) -> str:
    return str(config.SCRIPTS_DIR / name)


def _football_steps() -> list[Step]:
    def decode(ctx):
        return lambda: adapters.decode_video(
            ctx.job_dir / "raw_video.mp4", ctx.job_dir / "frames", seq=ctx.job_id)

    def homography(ctx):
        import json
        cfg = JobConfig.model_validate_json(
            (ctx.job_dir / "job_config.json").read_text(encoding="utf-8"))
        return lambda: adapters.write_homography(
            [p.model_dump() for p in cfg.calibration_points], ctx.sport,
            ctx.job_dir / "homography.json")

    J = lambda ctx, *p: str(ctx.job_dir.joinpath(*p))
    return [
        Step("decode", "decoding", None, decode),
        Step("homography", "decoding", None, homography),
        Step("players", "tracking", None, lambda c: _py(
            _sd("track_alfheim.py"), "--video", J(c, "raw_video.mp4"),
            "--out", J(c, "outputs", "tracks", f"{c.job_id}.txt"),
            "--model", str(config.MODELS_DIR / "soccana.pt"), "--classes", "0")),
        Step("ball-cache", "ball", None, lambda c: _py(
            _sd("build_det_cache.py"), "--detector", str(config.MODELS_DIR / "soccana.pt"),
            "--source", J(c, "frames"), "--out", J(c, "outputs", "det_cache", "ball"),
            "--class-name", "ball", "--only", c.job_id)),
        Step("ball-kalman", "ball", None, lambda c: _py(
            _sd("analyze_ball.py"), c.job_id,
            "--cache-dir", J(c, "outputs", "det_cache", "ball"),
            "--source", J(c, "frames"), "--out", J(c, "outputs", "ball_track"),
            "--homography", J(c, "homography.json"))),
        Step("pitch-proj", "tracking", None, lambda c: _py(
            _sd("analyze_pitch.py"), c.job_id,
            "--tracker", J(c, "outputs", "tracks"),
            "--out", J(c, "outputs", "deliverables"),
            "--homography", J(c, "homography.json"))),
        Step("team-assign", "teams", None, lambda c: _py(
            _sd("team_assign.py"), "--seqs", c.job_id,
            "--tracker-dir", J(c, "outputs", "tracks"),
            "--data-root", J(c, "frames"),
            "--out", J(c, "outputs", "team_assign"),
            "--sample-seq", c.job_id, "--zip", "")),
        # coach_analytics tail
        Step("possession", "analytics", "coach_analytics", lambda c: _py(
            _sd("compute_possession.py"), c.job_id, "--source", J(c, "frames"),
            "--tracker-dir", J(c, "outputs", "tracks"),
            "--ball-track-dir", J(c, "outputs", "ball_track"),
            "--team-assign-dir", J(c, "outputs", "team_assign"),
            "--homography", J(c, "homography.json"))),
        Step("coach", "analytics", "coach_analytics", lambda c: _py(
            _sd("coach_deliverable.py"), c.job_id,
            "--deliverables", J(c, "outputs", "deliverables"),
            "--ball-dir", J(c, "outputs", "ball_track"),
            "--team-assign", J(c, "outputs", "team_assign", "track_teams.json"),
            "--track-dir", J(c, "outputs", "tracks"),
            "--frames", J(c, "frames"), "--contact-only")),
        # event_highlights tail
        Step("detect-events", "events", "event_highlights", lambda c: _py(
            _sd("detect_events.py"), c.job_id,
            "--ball-dir", J(c, "outputs", "ball_track"),
            "--track-dir", J(c, "outputs", "tracks"),
            "--team-json", J(c, "outputs", "team_assign", "track_teams.json"),
            "--zip", "", "--out", J(c, "outputs", "events"))),
        Step("follow-cam", "events", "event_highlights", lambda c: _py(
            _sd("follow_cam.py"), c.job_id,
            "--ball-dir", J(c, "outputs", "ball_track"),
            "--track-dir", J(c, "outputs", "tracks"),
            "--source", J(c, "frames"), "--gt-zip", "",
            "--out", J(c, "outputs", "follow_cam"), "--no-render")),
        Step("clip", "events", "event_highlights", lambda c: _py(
            _sd("clip_highlights.py"), c.job_id,
            "--events-dir", J(c, "outputs", "events"),
            "--follow-dir", J(c, "outputs", "follow_cam"),
            "--source", J(c, "frames"),
            "--out", J(c, "outputs", "event_highlights"))),
    ]


PIPELINES: dict[str, Callable[[], list[Step]]] = {"football": _football_steps}


def resolve_steps(cfg: JobConfig) -> list[Step]:
    sport = cfg.sport
    if sport not in PIPELINES:
        raise ValueError(f"no pipeline for sport {sport}")
    out = []
    for s in PIPELINES[sport]():
        if s.deliverable is None or s.deliverable in cfg.deliverables_requested:
            out.append(s)
    return out


def run_step(step: Step, ctx: StepCtx, log_dir: Path) -> None:
    """Run one step: a callable adapter or a subprocess. Tee output to a log;
    raise CalledProcessError / the adapter's exception on failure."""
    built = step.build(ctx)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{step.key}.log"
    if callable(built):
        with open(log_path, "w", encoding="utf-8") as lf:
            lf.write(f"[adapter step {step.key}]\n")
            result = built()
            lf.write(f"ok: {result}\n")
        return
    with open(log_path, "w", encoding="utf-8") as lf:
        proc = subprocess.run(built, cwd=str(config.REPO_ROOT),
                              stdout=lf, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"step {step.key} exited {proc.returncode}; see {log_path}")
```
Keep `stage_label()` from Plan 1 (add any missing labels). DELETE `run_stage_stub` and the old `resolve_stages`.

- [ ] **Step 5: Run → pass** (`tests/backend/test_pipeline_football.py`). These tests build argv only — no GPU.

- [ ] **Step 6: Commit** `feat(backend): real subprocess pipeline engine + football step list`

---

## Task 8: `worker.py` — run real steps

**Files:** Modify `backend/worker.py`; update `tests/backend/test_worker.py`

The worker currently calls `pipeline.resolve_stages` + `run_stage_stub`. Switch to `resolve_steps` + `run_step`, reporting `ui_stage` + progress per step. The `tagging_pending` pause is football-irrelevant for Plan 3 (no player_highlights), but KEEP the pause logic for Plan 4 — simply: player_highlights isn't in football's steps, so it never triggers. Remove the stub-specific test expectations (`*.stub.txt`).

- [ ] **Step 1: Update `run_one`** to:
```python
cfg = self.store.read_config(job_id)
steps = pipeline.resolve_steps(cfg)
ctx = pipeline.StepCtx(job_dir=self.store.job_dir(job_id), job_id=job_id, sport=cfg.sport)
total = len(steps)
stage = "unknown"
try:
    for i, step in enumerate(steps):
        stage = step.ui_stage
        self.store.write_status(job_id, state=step.ui_stage, stage=step.ui_stage,
            progress=round(100 * i / total),
            stage_label=pipeline.stage_label(step.ui_stage), error=None)
        pipeline.run_step(step, ctx, self.store.job_dir(job_id) / "logs")
    self.store.write_status(job_id, state="ready", stage="ready", progress=100,
        stage_label=pipeline.stage_label("ready"), error=None)
except Exception:
    errors.log_stage_failure(self.store.job_dir(job_id), stage=stage,
        detail=traceback.format_exc())
    self.store.write_status(job_id, state="failed", stage=stage,
        progress=0, stage_label=None, error=errors.friendly_message(stage))
return True
```
(Drop the old `tagging_done` resume branch and stub references; Plan 4 will reintroduce a tagging pause for the player_highlights step.)

- [ ] **Step 2: Update `tests/backend/test_worker.py`** — replace the stub-based tests with ones that monkeypatch `pipeline.run_step` to a no-op and assert the job reaches `ready` running the football step list, plus the failure-path test (monkeypatch `run_step` to raise → state `failed`, friendly error, log written). Example:
```python
def test_run_one_completes_football_job(tmp_path, monkeypatch):
    from backend import pipeline
    store = JobStore(tmp_path)
    cfg = store.create(sport="football", match_name="x", match_date="2026-05-31")
    store.update_config(cfg.job_id, deliverables_requested=["coach_analytics"])
    store.write_status(cfg.job_id, state="queued", stage=None, progress=0,
                       stage_label=None, error=None)
    monkeypatch.setattr(pipeline, "run_step", lambda step, ctx, logs: None)
    worker.Worker(store).run_one()
    from backend import db
    assert db.get_job(store.conn, cfg.job_id)["state"] == "ready"
```
Keep the failure-path test (monkeypatch `run_step` to raise) and the no-queued-job no-op test.

- [ ] **Step 3: Run the full backend suite** `.venv\Scripts\python.exe -m pytest tests/backend -q` → all green (the Plan-1 e2e stub-flow test `test_e2e_stub_flow.py` asserts `*.stub.txt`; UPDATE it to monkeypatch `pipeline.run_step` to a no-op so it still verifies the create→ready→download flow without GPU — or mark it to use a fake step. Make it green.)

- [ ] **Step 4: Commit** `feat(backend): worker runs the real pipeline steps`

---

## Task 9: End-to-end football run on real footage (GPU)

**Files:** Create `scripts/e2e_football_pipeline.py`

This is the real proof: decode → track → ball → teams → analytics + events on `clips/football.mp4`, asserting real deliverables. It uses the worker against a real job; it WILL use the GPU and take a few minutes on the 540-frame clip.

- [ ] **Step 1: Write the driver** `scripts/e2e_football_pipeline.py`:
```python
"""Real end-to-end football pipeline on clips/football.mp4. GPU; minutes.
Run: .venv\\Scripts\\python.exe scripts\\e2e_football_pipeline.py"""
import sys, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.jobs import JobStore
from backend.worker import Worker
from backend import db

ROOT = Path(__file__).resolve().parent.parent
CLIP = ROOT / "clips" / "football.mp4"


def main() -> int:
    jobs_dir = ROOT / "build" / "e2e_jobs"
    if jobs_dir.exists():
        shutil.rmtree(jobs_dir)
    store = JobStore(jobs_dir)
    cfg = store.create(sport="football", match_name="E2E", match_date="2026-05-31")
    jid = cfg.job_id
    shutil.copy(CLIP, store.video_path(jid))
    # 4 corner calibration (approx, 1280x720 clip)
    store.update_config(jid, calibration_points=[
        {"pixel_x": 100, "pixel_y": 120, "real_world_label": "far-left corner"},
        {"pixel_x": 1180, "pixel_y": 120, "real_world_label": "far-right corner"},
        {"pixel_x": 1240, "pixel_y": 700, "real_world_label": "near-right corner"},
        {"pixel_x": 40, "pixel_y": 700, "real_world_label": "near-left corner"}],
        deliverables_requested=["coach_analytics", "event_highlights"])
    store.write_status(jid, state="queued", stage=None, progress=0,
                       stage_label=None, error=None)
    Worker(store).run_one()
    row = db.get_job(store.conn, jid)
    print("final state:", row["state"], "stage:", row["stage"], "error:", row["error"])
    out = store.job_dir(jid) / "outputs"
    produced = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
    print("outputs:", produced)
    assert row["state"] == "ready", f"job failed at {row['stage']}: {row['error']}"
    # real coach + event artifacts exist
    assert any(p.endswith(".pdf") for p in produced), "no coach PDF"
    assert any("event_highlights" in p for p in produced), "no event highlights"
    print("E2E FOOTBALL PIPELINE: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it** `.venv\Scripts\python.exe scripts\e2e_football_pipeline.py`. Expected: prints stages, ends `E2E FOOTBALL PIPELINE: OK`. **This is where real-footage bugs surface** — if a stage fails, read `build/e2e_jobs/<id>/logs/<stage>.log`, use the systematic-debugging skill, fix the specific script/adapter, re-run. Iterate until green. (Do NOT fake success — a failing stage is a real finding to fix or flag honestly.)

- [ ] **Step 3: Backend suite still green** `.venv\Scripts\python.exe -m pytest tests/backend -q`.

- [ ] **Step 4: Commit** `test(pipeline): real end-to-end football run on sample clip`

---

## Self-Review (completed during plan authoring)

**Spec coverage:** decode adapter (spec §5) — Task 2 ✅; calibration→homography adapter (§5) — Task 2 ✅; foundation chain + coach_analytics + event_highlights wired to run (§5) — Tasks 7-9 ✅; "scripts adapted minimally to accept config, finish Day-31 decoupling" (§2) — Tasks 3-6 (additive `--homography`/`--seqs`) ✅; subprocess isolation per stage + friendly failures + logs (§1/§6/§7) — Task 7 `run_step` ✅; honest gaps (§5) — see below.

**Honest gaps flagged (per the chosen "flag gaps" approach):** GT-validation metrics are intentionally skipped (no GT for uploaded footage) — coach PDF accuracy footnotes will be absent; event detection runs without the GSR action label. Event-highlights *quality* is footage-gated (Day-31 ~30% ball recall on wide fixed cam); the clip on `clips/football.mp4` (a tighter clip) should do better, but recall is not guaranteed — the plumbing producing clips is the deliverable here. Calibration accuracy depends on the operator's 4 corner clicks (Plan-2 `object-fit:fill` makes pixel mapping exact).

**Placeholder scan:** no TBD/TODO; the script-edit tasks (3-6) give an exact additive pattern + a verification (`--help`), appropriate for edits to real research code whose exact surrounding lines the implementer confirms by reading.

**Type/name consistency:** `Step`/`StepCtx`/`resolve_steps`/`run_step` defined in Task 7 and used in Task 8. `adapters.decode_video`/`write_homography` (Task 2) used in Task 7's step builders. `landmarks.world_points` (Task 1) used by `write_homography`. `config.PYTHON_EXE`/`SCRIPTS_DIR`/`MODELS_DIR` (Task 7 Step 1) used in step builders.

**Risk note:** Task 9 is the real-footage integration point and the likely source of iteration — the CV scripts may carry implicit SoccerNet assumptions beyond the three the research found. Budget for debugging there; each fix should be a minimal, additive script edit + a note. If a stage proves infeasible on this footage, flag it honestly (degrade that deliverable) rather than faking output.

**Out of scope (next plan):** basketball chain (reuses this engine via a `_basketball_steps()` added to `PIPELINES` + the basketball script edits from the basketball research doc); player_highlights/tagging (Plan 4).
