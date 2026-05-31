# Operator App Backend — Plan 1: Skeleton + State Machine + Stub Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A runnable FastAPI backend where a job flows `created → … → ready` through the full state machine and produces a placeholder output file, driven by a single background worker — with NO real CV yet (a stub pipeline stands in).

**Architecture:** Modular `backend/` package (Approach A from the spec). FastAPI serves a JSON API + the static `Website/` frontend. Job state lives in SQLite (durable) mirrored to a per-job `status.json`. A single background thread runs queued jobs one stage at a time. In this plan every stage is a STUB (sleeps briefly, advances state, writes placeholder output) so the entire orchestration is testable without a GPU. Plans 2–5 swap the stub for real script subprocesses, wire the frontend, and add polish.

**Tech Stack:** Python 3.11.9 (repo `.venv`), FastAPI, uvicorn, pydantic v2, python-multipart, stdlib `sqlite3`, pytest + httpx (FastAPI `TestClient`), opencv (for the frame endpoint).

**Spec:** `docs/superpowers/specs/2026-05-31-operator-app-backend-design.md`

---

## File Structure (created by this plan)

```
backend/
  __init__.py              # marks package
  config.py                # paths, host/port, sport set, per-deliverable stage lists
  schemas.py               # pydantic models matching the contract field names
  db.py                    # SQLite: connection + jobs table CRUD
  jobs.py                  # job directory layout, job_config.json + status.json IO
  errors.py                # friendly-message mapping + server-side logging helper
  pipeline.py              # stage registry + STUB stage runner
  worker.py                # single background-thread queue runner
  main.py                  # FastAPI app: routes + static frontend + worker lifespan
  requirements-backend.txt # fastapi, uvicorn[standard], python-multipart, pydantic
tests/backend/
  __init__.py
  conftest.py              # tmp JOBS_DIR fixture + TestClient app fixture
  test_schemas.py
  test_db.py
  test_jobs.py
  test_errors.py
  test_pipeline_stub.py
  test_worker.py
  test_api_jobs.py
  test_api_inputs.py
  test_api_outputs.py
  test_e2e_stub_flow.py
jobs/                      # runtime data, gitignored (created at runtime)
```

**Responsibilities (one job each):**
- `config.py` — constants only, no logic.
- `schemas.py` — request/response shapes; the single source of contract field names.
- `db.py` — SQLite mechanics; knows nothing about HTTP or pipelines.
- `jobs.py` — on-disk job artifacts (dirs, `job_config.json`, `status.json`); uses `db.py`.
- `errors.py` — turns stage/exception into operator-friendly text; logs detail to a file.
- `pipeline.py` — declares which stages exist and (in Plan 1) a stub that fakes them.
- `worker.py` — pulls queued jobs from `db.py`, runs `pipeline.py` stages, updates state.
- `main.py` — HTTP layer only; delegates to `jobs.py`/`db.py`; never touches CV.

---

## Conventions for every task

- All `python`/`pytest`/`pip` commands run with the repo venv interpreter: **`.venv\Scripts\python.exe`** (Windows/PowerShell). Example: `.venv\Scripts\python.exe -m pytest tests/backend/test_db.py -v`.
- Run commands from the repo root `C:\sports-ai`.
- Commit after each task with the shown message.

---

## Task 1: Scaffolding, dependencies, gitignore

**Files:**
- Create: `backend/__init__.py` (empty)
- Create: `backend/requirements-backend.txt`
- Create: `tests/backend/__init__.py` (empty)
- Modify: `.gitignore` (append a `jobs/` ignore rule)

- [ ] **Step 1: Create the package markers**

Create `backend/__init__.py` with a single line:

```python
"""Operator App backend — thin FastAPI orchestration layer over the CV pipeline."""
```

Create `tests/backend/__init__.py` as an empty file (0 bytes).

- [ ] **Step 2: Declare web dependencies**

Create `backend/requirements-backend.txt`:

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
python-multipart==0.0.20
pydantic==2.10.4
```

- [ ] **Step 3: Install the web dependencies into the repo venv**

Run: `.venv\Scripts\python.exe -m pip install -r backend\requirements-backend.txt`
Expected: ends with `Successfully installed fastapi-... uvicorn-... python-multipart-... pydantic-...` (pydantic may already be satisfied via another package — that is fine).

- [ ] **Step 4: Verify FastAPI imports in the venv**

Run: `.venv\Scripts\python.exe -c "import fastapi, uvicorn, multipart, pydantic; print('ok', fastapi.__version__)"`
Expected: `ok 0.115.6`

- [ ] **Step 5: Ignore the runtime jobs directory**

Append to `.gitignore` (new lines at end of file):

```
# Operator App backend runtime job data
jobs/
```

- [ ] **Step 6: Commit**

```bash
git add backend/__init__.py backend/requirements-backend.txt tests/backend/__init__.py .gitignore
git commit -m "feat(backend): scaffold package, web deps, ignore jobs/"
```

---

## Task 2: `config.py` — constants

**Files:**
- Create: `backend/config.py`
- Test: `tests/backend/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/backend/test_config.py`:

```python
from backend import config


def test_sports_are_football_and_basketball():
    assert config.SPORTS == ("football", "basketball")


def test_deliverable_stage_lists_exist_for_each_deliverable():
    for d in ("coach_analytics", "event_highlights", "player_highlights"):
        assert d in config.DELIVERABLE_STAGES
        assert isinstance(config.DELIVERABLE_STAGES[d], tuple)
        assert len(config.DELIVERABLE_STAGES[d]) >= 1


def test_foundation_stages_are_shared_prefix():
    assert config.FOUNDATION_STAGES == (
        "decoding", "detecting", "tracking", "teams", "ball",
    )


def test_jobs_dir_is_under_repo_root():
    assert config.JOBS_DIR.name == "jobs"
    assert config.WEBSITE_DIR.name == "Website"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.config'`

- [ ] **Step 3: Write the implementation**

Create `backend/config.py`:

```python
"""Static configuration for the Operator App backend. Constants only — no logic."""
from __future__ import annotations

from pathlib import Path

# Repo root = parent of the backend/ package directory.
REPO_ROOT: Path = Path(__file__).resolve().parent.parent
JOBS_DIR: Path = REPO_ROOT / "jobs"
WEBSITE_DIR: Path = REPO_ROOT / "Website"

# Network
HOST: str = "0.0.0.0"
PORT: int = 8000

# Domain
SPORTS: tuple[str, ...] = ("football", "basketball")
DELIVERABLES: tuple[str, ...] = (
    "coach_analytics",
    "event_highlights",
    "player_highlights",
)

# Stage graph. Foundation runs once for any deliverable; per-deliverable stages
# append after it. The worker computes the concrete stage list per job from the
# requested deliverables (see worker.py).
FOUNDATION_STAGES: tuple[str, ...] = (
    "decoding",
    "detecting",
    "tracking",
    "teams",
    "ball",
)
DELIVERABLE_STAGES: dict[str, tuple[str, ...]] = {
    "coach_analytics": ("analytics",),
    "event_highlights": ("events",),
    # tagging_pending is a human pause; tagging_done resumes to reel assembly.
    "player_highlights": ("tagging_pending", "tagging_done", "player_highlights"),
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_config.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/config.py tests/backend/test_config.py
git commit -m "feat(backend): config constants + stage graph"
```

---

## Task 3: `schemas.py` — pydantic contract models

**Files:**
- Create: `backend/schemas.py`
- Test: `tests/backend/test_schemas.py`

- [ ] **Step 1: Write the failing test**

Create `tests/backend/test_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from backend import schemas


def test_create_job_request_requires_valid_sport():
    req = schemas.CreateJobRequest(
        sport="football", match_name="U14 vs Rivals", match_date="2026-05-31"
    )
    assert req.sport == "football"
    with pytest.raises(ValidationError):
        schemas.CreateJobRequest(
            sport="cricket", match_name="x", match_date="2026-05-31"
        )


def test_calibration_point_field_names_match_contract():
    p = schemas.CalibrationPoint(pixel_x=10, pixel_y=20, real_world_label="top_left")
    dumped = p.model_dump()
    assert set(dumped) == {"pixel_x", "pixel_y", "real_world_label"}


def test_deliverables_request_rejects_unknown_deliverable():
    schemas.DeliverablesRequest(deliverables_requested=["coach_analytics"])
    with pytest.raises(ValidationError):
        schemas.DeliverablesRequest(deliverables_requested=["make_me_famous"])


def test_job_config_round_trips_contract_fields():
    cfg = schemas.JobConfig(
        job_id="abc",
        sport="basketball",
        match_name="Finals",
        match_date="2026-05-31",
        video_path="raw_video.mp4",
        calibration_points=[],
        roster=[],
        player_tags={},
        deliverables_requested=["event_highlights"],
        created_at="2026-05-31T00:00:00+00:00",
    )
    keys = set(cfg.model_dump().keys())
    assert keys == {
        "job_id", "sport", "match_name", "match_date", "video_path",
        "calibration_points", "roster", "player_tags",
        "deliverables_requested", "created_at",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.schemas'`

- [ ] **Step 3: Write the implementation**

Create `backend/schemas.py`:

```python
"""Pydantic models. This module is the single source of contract field names —
they must match PRD'S/Backend_Spec_OperatorApp.md and the frontend exactly."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.config import DELIVERABLES, SPORTS

Sport = Literal["football", "basketball"]
Deliverable = Literal["coach_analytics", "event_highlights", "player_highlights"]


class CreateJobRequest(BaseModel):
    sport: Sport
    match_name: str = Field(min_length=1)
    match_date: str  # YYYY-MM-DD (frontend supplies; not strictly validated here)


class CalibrationPoint(BaseModel):
    pixel_x: int
    pixel_y: int
    real_world_label: str


class CalibrationRequest(BaseModel):
    calibration_points: list[CalibrationPoint]


class RosterRequest(BaseModel):
    roster: list[str]


class TagsRequest(BaseModel):
    player_tags: dict[str, str]  # clip_id -> player_name


class DeliverablesRequest(BaseModel):
    deliverables_requested: list[Deliverable] = Field(min_length=1)


class JobConfig(BaseModel):
    """The on-disk job_config.json contract shape (field names are frozen)."""
    job_id: str
    sport: Sport
    match_name: str
    match_date: str
    video_path: str
    calibration_points: list[CalibrationPoint]
    roster: list[str]
    player_tags: dict[str, str]
    deliverables_requested: list[Deliverable]
    created_at: str


class JobSummary(BaseModel):
    """Dashboard list item."""
    job_id: str
    sport: Sport
    match_name: str
    match_date: str
    state: str
    created_at: str


class JobStatus(BaseModel):
    """status endpoint payload."""
    job_id: str
    state: str
    stage: str | None
    progress: int  # 0..100
    stage_label: str | None  # plain-English label for the UI
    error: str | None  # friendly message when state == "failed"


# sanity: the Literals above must stay in lockstep with config.
assert set(SPORTS) == {"football", "basketball"}
assert set(DELIVERABLES) == {
    "coach_analytics", "event_highlights", "player_highlights"
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_schemas.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/schemas.py tests/backend/test_schemas.py
git commit -m "feat(backend): pydantic contract schemas"
```

---

## Task 4: `db.py` — SQLite job store

**Files:**
- Create: `backend/db.py`
- Test: `tests/backend/test_db.py`

- [ ] **Step 1: Write the failing test**

Create `tests/backend/test_db.py`:

```python
from backend import db


def test_init_and_insert_and_get(tmp_path):
    conn = db.connect(tmp_path / "jobs.sqlite3")
    db.init_schema(conn)
    db.insert_job(conn, job_id="j1", sport="football",
                  match_name="A vs B", match_date="2026-05-31",
                  created_at="2026-05-31T00:00:00+00:00")
    row = db.get_job(conn, "j1")
    assert row["job_id"] == "j1"
    assert row["state"] == "created"
    assert row["progress"] == 0


def test_update_state_and_stage(tmp_path):
    conn = db.connect(tmp_path / "jobs.sqlite3")
    db.init_schema(conn)
    db.insert_job(conn, job_id="j1", sport="football",
                  match_name="A", match_date="2026-05-31",
                  created_at="2026-05-31T00:00:00+00:00")
    db.update_job(conn, "j1", state="tracking", stage="tracking", progress=40)
    row = db.get_job(conn, "j1")
    assert row["state"] == "tracking"
    assert row["stage"] == "tracking"
    assert row["progress"] == 40


def test_list_jobs_orders_newest_first(tmp_path):
    conn = db.connect(tmp_path / "jobs.sqlite3")
    db.init_schema(conn)
    db.insert_job(conn, job_id="old", sport="football", match_name="O",
                  match_date="2026-05-30", created_at="2026-05-30T00:00:00+00:00")
    db.insert_job(conn, job_id="new", sport="basketball", match_name="N",
                  match_date="2026-05-31", created_at="2026-05-31T00:00:00+00:00")
    ids = [r["job_id"] for r in db.list_jobs(conn)]
    assert ids == ["new", "old"]


def test_next_queued_returns_oldest_queued(tmp_path):
    conn = db.connect(tmp_path / "jobs.sqlite3")
    db.init_schema(conn)
    db.insert_job(conn, job_id="a", sport="football", match_name="A",
                  match_date="2026-05-31", created_at="2026-05-31T00:00:01+00:00")
    db.insert_job(conn, job_id="b", sport="football", match_name="B",
                  match_date="2026-05-31", created_at="2026-05-31T00:00:02+00:00")
    db.update_job(conn, "a", state="queued")
    db.update_job(conn, "b", state="queued")
    assert db.next_queued(conn)["job_id"] == "a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.db'`

- [ ] **Step 3: Write the implementation**

Create `backend/db.py`:

```python
"""SQLite job store. Knows nothing about HTTP or pipelines."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id      TEXT PRIMARY KEY,
            sport       TEXT NOT NULL,
            match_name  TEXT NOT NULL,
            match_date  TEXT NOT NULL,
            state       TEXT NOT NULL DEFAULT 'created',
            stage       TEXT,
            progress    INTEGER NOT NULL DEFAULT 0,
            error       TEXT,
            created_at  TEXT NOT NULL
        )
        """
    )
    conn.commit()


def insert_job(conn: sqlite3.Connection, *, job_id: str, sport: str,
               match_name: str, match_date: str, created_at: str) -> None:
    conn.execute(
        "INSERT INTO jobs (job_id, sport, match_name, match_date, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (job_id, sport, match_name, match_date, created_at),
    )
    conn.commit()


def get_job(conn: sqlite3.Connection, job_id: str) -> sqlite3.Row | None:
    cur = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
    return cur.fetchone()


def update_job(conn: sqlite3.Connection, job_id: str, **fields: Any) -> None:
    allowed = {"state", "stage", "progress", "error"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    cols = ", ".join(f"{k} = ?" for k in sets)
    conn.execute(
        f"UPDATE jobs SET {cols} WHERE job_id = ?",
        (*sets.values(), job_id),
    )
    conn.commit()


def list_jobs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    cur = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC")
    return cur.fetchall()


def next_queued(conn: sqlite3.Connection) -> sqlite3.Row | None:
    cur = conn.execute(
        "SELECT * FROM jobs WHERE state = 'queued' ORDER BY created_at ASC LIMIT 1"
    )
    return cur.fetchone()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_db.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/db.py tests/backend/test_db.py
git commit -m "feat(backend): SQLite job store"
```

---

## Task 5: `errors.py` — friendly messages + logging

**Files:**
- Create: `backend/errors.py`
- Test: `tests/backend/test_errors.py`

- [ ] **Step 1: Write the failing test**

Create `tests/backend/test_errors.py`:

```python
from backend import errors


def test_friendly_message_known_stage():
    assert errors.friendly_message("decoding") == (
        "We couldn't read the video. Please try uploading it again."
    )
    assert errors.friendly_message("analytics") == (
        "Something went wrong while building the analytics. Please try again."
    )


def test_friendly_message_unknown_stage_has_generic_fallback():
    msg = errors.friendly_message("some_future_stage")
    assert "went wrong" in msg.lower()


def test_log_stage_failure_writes_file(tmp_path):
    log_path = errors.log_stage_failure(
        tmp_path, stage="tracking", detail="Traceback: boom"
    )
    assert log_path.exists()
    assert "boom" in log_path.read_text(encoding="utf-8")
    assert log_path.name == "tracking.log"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_errors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.errors'`

- [ ] **Step 3: Write the implementation**

Create `backend/errors.py`:

```python
"""Map pipeline failures to operator-friendly text; log technical detail to disk.
The API must NEVER surface raw stack traces — friendly text out, detail to logs/."""
from __future__ import annotations

from pathlib import Path

_STAGE_MESSAGES: dict[str, str] = {
    "decoding": "We couldn't read the video. Please try uploading it again.",
    "detecting": "Something went wrong while finding players. Please try again.",
    "tracking": "Something went wrong while following players. Please try again.",
    "teams": "Something went wrong while sorting the teams. Please try again.",
    "ball": "Something went wrong while tracking the ball. Please try again.",
    "analytics": "Something went wrong while building the analytics. Please try again.",
    "events": "Something went wrong while finding key moments. Please try again.",
    "player_highlights": "Something went wrong while building player reels. Please try again.",
}

_GENERIC = "Something went wrong while processing this match. Please try again."


def friendly_message(stage: str) -> str:
    return _STAGE_MESSAGES.get(stage, _GENERIC)


def log_stage_failure(job_dir: Path, *, stage: str, detail: str) -> Path:
    logs = job_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / f"{stage}.log"
    log_path.write_text(detail, encoding="utf-8")
    return log_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_errors.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/errors.py tests/backend/test_errors.py
git commit -m "feat(backend): friendly error mapping + stage logging"
```

---

## Task 6: `jobs.py` — on-disk job artifacts

**Files:**
- Create: `backend/jobs.py`
- Test: `tests/backend/test_jobs.py`

- [ ] **Step 1: Write the failing test**

Create `tests/backend/test_jobs.py`:

```python
import json

from backend import jobs


def test_create_job_makes_dir_and_config(tmp_path):
    store = jobs.JobStore(tmp_path)
    cfg = store.create(sport="football", match_name="A vs B",
                       match_date="2026-05-31")
    job_dir = store.job_dir(cfg.job_id)
    assert job_dir.is_dir()
    assert (job_dir / "outputs").is_dir()
    written = json.loads((job_dir / "job_config.json").read_text())
    assert written["sport"] == "football"
    assert written["video_path"] == "raw_video.mp4"
    assert written["deliverables_requested"] == []


def test_update_config_persists_calibration(tmp_path):
    store = jobs.JobStore(tmp_path)
    cfg = store.create(sport="basketball", match_name="x", match_date="2026-05-31")
    store.update_config(cfg.job_id, calibration_points=[
        {"pixel_x": 1, "pixel_y": 2, "real_world_label": "tl"}])
    reread = store.read_config(cfg.job_id)
    assert reread.calibration_points[0].real_world_label == "tl"


def test_write_status_mirrors_json(tmp_path):
    store = jobs.JobStore(tmp_path)
    cfg = store.create(sport="football", match_name="x", match_date="2026-05-31")
    store.write_status(cfg.job_id, state="tracking", stage="tracking",
                       progress=40, stage_label="Following players", error=None)
    status = json.loads((store.job_dir(cfg.job_id) / "status.json").read_text())
    assert status["state"] == "tracking"
    assert status["stage_label"] == "Following players"


def test_video_path_resolves_inside_job_dir(tmp_path):
    store = jobs.JobStore(tmp_path)
    cfg = store.create(sport="football", match_name="x", match_date="2026-05-31")
    vp = store.video_path(cfg.job_id)
    assert vp == store.job_dir(cfg.job_id) / "raw_video.mp4"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.jobs'`

- [ ] **Step 3: Write the implementation**

Create `backend/jobs.py`:

```python
"""On-disk job artifacts: directories, job_config.json, status.json.
Holds the SQLite connection and keeps DB rows + config file in sync."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend import db
from backend.schemas import JobConfig


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, jobs_dir: Path):
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.conn = db.connect(self.jobs_dir / "jobs.sqlite3")
        db.init_schema(self.conn)

    # ---- paths ----
    def job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / job_id

    def video_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "raw_video.mp4"

    def config_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job_config.json"

    def status_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "status.json"

    # ---- lifecycle ----
    def create(self, *, sport: str, match_name: str, match_date: str) -> JobConfig:
        job_id = uuid.uuid4().hex
        created_at = _now_iso()
        d = self.job_dir(job_id)
        (d / "outputs").mkdir(parents=True, exist_ok=True)
        cfg = JobConfig(
            job_id=job_id, sport=sport, match_name=match_name,
            match_date=match_date, video_path="raw_video.mp4",
            calibration_points=[], roster=[], player_tags={},
            deliverables_requested=[], created_at=created_at,
        )
        self._write_config(cfg)
        db.insert_job(self.conn, job_id=job_id, sport=sport,
                      match_name=match_name, match_date=match_date,
                      created_at=created_at)
        self.write_status(job_id, state="created", stage=None, progress=0,
                          stage_label=None, error=None)
        return cfg

    def _write_config(self, cfg: JobConfig) -> None:
        self.config_path(cfg.job_id).write_text(
            json.dumps(cfg.model_dump(), indent=2), encoding="utf-8")

    def read_config(self, job_id: str) -> JobConfig:
        return JobConfig.model_validate_json(
            self.config_path(job_id).read_text(encoding="utf-8"))

    def update_config(self, job_id: str, **fields) -> JobConfig:
        cfg = self.read_config(job_id)
        data = cfg.model_dump()
        data.update(fields)
        new_cfg = JobConfig.model_validate(data)
        self._write_config(new_cfg)
        return new_cfg

    def write_status(self, job_id: str, *, state: str, stage: str | None,
                     progress: int, stage_label: str | None,
                     error: str | None) -> None:
        db.update_job(self.conn, job_id, state=state, stage=stage,
                      progress=progress, error=error)
        payload = {
            "job_id": job_id, "state": state, "stage": stage,
            "progress": progress, "stage_label": stage_label, "error": error,
        }
        self.status_path(job_id).write_text(
            json.dumps(payload, indent=2), encoding="utf-8")

    def exists(self, job_id: str) -> bool:
        return self.config_path(job_id).exists()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_jobs.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/jobs.py tests/backend/test_jobs.py
git commit -m "feat(backend): on-disk job store (config + status + sqlite sync)"
```

---

## Task 7: `pipeline.py` — stage list resolution + STUB runner

**Files:**
- Create: `backend/pipeline.py`
- Test: `tests/backend/test_pipeline_stub.py`

- [ ] **Step 1: Write the failing test**

Create `tests/backend/test_pipeline_stub.py`:

```python
from backend import pipeline
from backend.schemas import JobConfig


def _cfg(deliverables):
    return JobConfig(
        job_id="j1", sport="football", match_name="x", match_date="2026-05-31",
        video_path="raw_video.mp4", calibration_points=[], roster=[],
        player_tags={}, deliverables_requested=deliverables,
        created_at="2026-05-31T00:00:00+00:00",
    )


def test_resolve_stages_foundation_then_analytics():
    stages = pipeline.resolve_stages(_cfg(["coach_analytics"]))
    assert stages == ["decoding", "detecting", "tracking", "teams", "ball",
                      "analytics"]


def test_resolve_stages_dedupes_foundation_for_multiple_deliverables():
    stages = pipeline.resolve_stages(
        _cfg(["coach_analytics", "event_highlights"]))
    # foundation appears once, then analytics, then events
    assert stages == ["decoding", "detecting", "tracking", "teams", "ball",
                      "analytics", "events"]


def test_stage_label_is_plain_english():
    assert pipeline.stage_label("tracking") == "Following players"
    assert pipeline.stage_label("ready") == "Ready"


def test_stub_run_stage_writes_marker(tmp_path):
    # The stub must create an outputs marker so e2e can assert progress.
    pipeline.run_stage_stub(tmp_path, "analytics")
    assert (tmp_path / "outputs" / "analytics.stub.txt").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_pipeline_stub.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.pipeline'`

- [ ] **Step 3: Write the implementation**

Create `backend/pipeline.py`:

```python
"""Stage graph resolution + a STUB stage runner.

Plan 1 only: every stage is faked. Plan 3 replaces `run_stage_stub` with real
subprocess calls to the CV scripts (see the spec, section 5). The stage LIST
logic here is real and reused by the worker in all plans."""
from __future__ import annotations

import time
from pathlib import Path

from backend.config import DELIVERABLE_STAGES, FOUNDATION_STAGES
from backend.schemas import JobConfig

_STAGE_LABELS: dict[str, str] = {
    "decoding": "Reading the video",
    "detecting": "Finding players",
    "tracking": "Following players",
    "teams": "Sorting teams",
    "ball": "Tracking the ball",
    "analytics": "Building analytics",
    "events": "Finding key moments",
    "tagging_pending": "Waiting for player names",
    "tagging_done": "Names received",
    "player_highlights": "Building player reels",
    "ready": "Ready",
    "queued": "Waiting in line",
}


def stage_label(stage: str) -> str:
    return _STAGE_LABELS.get(stage, stage.replace("_", " ").capitalize())


def resolve_stages(cfg: JobConfig) -> list[str]:
    """Foundation once, then per-deliverable stages in DELIVERABLES order."""
    stages: list[str] = list(FOUNDATION_STAGES)
    for d in ("coach_analytics", "event_highlights", "player_highlights"):
        if d in cfg.deliverables_requested:
            for s in DELIVERABLE_STAGES[d]:
                if s not in stages:
                    stages.append(s)
    return stages


def run_stage_stub(job_dir: Path, stage: str) -> None:
    """Fake a stage: brief sleep + write a marker file into outputs/.
    Replaced by real subprocess invocation in Plan 3."""
    time.sleep(0.05)
    outputs = job_dir / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / f"{stage}.stub.txt").write_text(
        f"stub output for stage {stage}\n", encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_pipeline_stub.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline.py tests/backend/test_pipeline_stub.py
git commit -m "feat(backend): stage resolution + stub stage runner"
```

---

## Task 8: `worker.py` — background queue runner

**Files:**
- Create: `backend/worker.py`
- Test: `tests/backend/test_worker.py`

**Design notes for the engineer:**
- The worker is a single thread. It loops: find the next `queued` job, run its stages in order, update state after each. For `player_highlights`, when it reaches the `tagging_pending` stage it sets state `tagging_pending` and STOPS working that job (parks it) until something flips it back to `queued` (Plan 4 wires the `/tags` endpoint to do that; in Plan 1 the test drives it manually).
- Progress % = `round(100 * completed_stages / total_stages)`.
- The worker exposes a `run_one()` method (process exactly one job to completion-or-park) so tests are deterministic without sleeping on a thread. The actual thread loop just calls `run_one()` repeatedly.

- [ ] **Step 1: Write the failing test**

Create `tests/backend/test_worker.py`:

```python
from backend import worker
from backend.jobs import JobStore


def _make_queued_job(store, deliverables):
    cfg = store.create(sport="football", match_name="x", match_date="2026-05-31")
    store.update_config(cfg.job_id, deliverables_requested=deliverables)
    store.write_status(cfg.job_id, state="queued", stage=None, progress=0,
                       stage_label="Waiting in line", error=None)
    return cfg.job_id


def test_run_one_completes_analytics_job_to_ready(tmp_path):
    store = JobStore(tmp_path)
    jid = _make_queued_job(store, ["coach_analytics"])
    w = worker.Worker(store)
    w.run_one()
    from backend import db
    row = db.get_job(store.conn, jid)
    assert row["state"] == "ready"
    assert row["progress"] == 100
    assert (store.job_dir(jid) / "outputs" / "analytics.stub.txt").exists()


def test_run_one_parks_player_highlights_at_tagging(tmp_path):
    store = JobStore(tmp_path)
    jid = _make_queued_job(store, ["player_highlights"])
    w = worker.Worker(store)
    w.run_one()
    from backend import db
    row = db.get_job(store.conn, jid)
    assert row["state"] == "tagging_pending"


def test_run_one_resumes_after_tagging(tmp_path):
    store = JobStore(tmp_path)
    jid = _make_queued_job(store, ["player_highlights"])
    w = worker.Worker(store)
    w.run_one()  # parks at tagging_pending
    # simulate tags submitted: flip back to queued
    store.write_status(jid, state="queued", stage="tagging_done", progress=50,
                       stage_label="Names received", error=None)
    w.run_one()  # resumes
    from backend import db
    row = db.get_job(store.conn, jid)
    assert row["state"] == "ready"
    assert (store.job_dir(jid) / "outputs" / "player_highlights.stub.txt").exists()


def test_run_one_no_queued_job_is_noop(tmp_path):
    store = JobStore(tmp_path)
    w = worker.Worker(store)
    assert w.run_one() is False  # nothing to do
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_worker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.worker'`

- [ ] **Step 3: Write the implementation**

Create `backend/worker.py`:

```python
"""Single background-thread queue runner. One job at a time (one GPU).

run_one(): process the next queued job until it finishes (ready), parks
(tagging_pending), or fails. Returns True if it acted on a job, else False.
The thread loop simply calls run_one() repeatedly with a short idle sleep."""
from __future__ import annotations

import threading
import time
import traceback

from backend import db, errors, pipeline
from backend.jobs import JobStore


class Worker:
    def __init__(self, store: JobStore):
        self.store = store
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---- core unit (deterministic, used by tests) ----
    def run_one(self) -> bool:
        row = db.next_queued(self.store.conn)
        if row is None:
            return False
        job_id = row["job_id"]
        cfg = self.store.read_config(job_id)
        stages = pipeline.resolve_stages(cfg)

        # Resume point: if a stage is recorded and it's past tagging, skip done ones.
        start_idx = 0
        recorded = row["stage"]
        if recorded == "tagging_done" and "tagging_done" in stages:
            start_idx = stages.index("tagging_done") + 1

        total = len(stages)
        try:
            for i in range(start_idx, total):
                stage = stages[i]
                progress = round(100 * i / total)

                if stage == "tagging_pending":
                    # human pause: park the job and stop here.
                    self.store.write_status(
                        job_id, state="tagging_pending", stage="tagging_pending",
                        progress=progress,
                        stage_label=pipeline.stage_label("tagging_pending"),
                        error=None)
                    return True

                if stage == "tagging_done":
                    # bookkeeping marker only; no work.
                    continue

                # mark in-progress, run the (stub) stage, then advance.
                self.store.write_status(
                    job_id, state=stage, stage=stage, progress=progress,
                    stage_label=pipeline.stage_label(stage), error=None)
                pipeline.run_stage_stub(self.store.job_dir(job_id), stage)

            self.store.write_status(
                job_id, state="ready", stage="ready", progress=100,
                stage_label=pipeline.stage_label("ready"), error=None)
        except Exception:  # noqa: BLE001 — friendly out, detail to log
            stage = locals().get("stage", "unknown")
            errors.log_stage_failure(
                self.store.job_dir(job_id), stage=stage,
                detail=traceback.format_exc())
            self.store.write_status(
                job_id, state="failed", stage=stage,
                progress=row["progress"] or 0, stage_label=None,
                error=errors.friendly_message(stage))
        return True

    # ---- thread loop (used by the running server) ----
    def _loop(self) -> None:
        while not self._stop.is_set():
            acted = self.run_one()
            if not acted:
                time.sleep(0.5)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_worker.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/worker.py tests/backend/test_worker.py
git commit -m "feat(backend): background queue worker (stub stages, tagging pause)"
```

---

## Task 9: `main.py` (part A) — app factory, job CRUD, status, list

**Files:**
- Create: `backend/main.py`
- Create: `tests/backend/conftest.py`
- Test: `tests/backend/test_api_jobs.py`

**Design note:** `create_app(jobs_dir, start_worker=False)` builds the FastAPI app with a `JobStore` and `Worker` attached to `app.state`. Tests build the app with `start_worker=False` and drive `app.state.worker.run_one()` manually. The real server (bottom of file) calls `create_app(config.JOBS_DIR, start_worker=True)`.

- [ ] **Step 1: Write the shared test fixtures**

Create `tests/backend/conftest.py`:

```python
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(jobs_dir=tmp_path / "jobs", start_worker=False)


@pytest.fixture
def client(app):
    return TestClient(app)
```

- [ ] **Step 2: Write the failing test**

Create `tests/backend/test_api_jobs.py`:

```python
def test_create_job_returns_id(client):
    r = client.post("/api/jobs", json={
        "sport": "football", "match_name": "A vs B", "match_date": "2026-05-31"})
    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body and len(body["job_id"]) > 0


def test_create_job_rejects_bad_sport(client):
    r = client.post("/api/jobs", json={
        "sport": "cricket", "match_name": "x", "match_date": "2026-05-31"})
    assert r.status_code == 422


def test_status_after_create_is_created(client):
    jid = client.post("/api/jobs", json={
        "sport": "football", "match_name": "x",
        "match_date": "2026-05-31"}).json()["job_id"]
    r = client.get(f"/api/jobs/{jid}/status")
    assert r.status_code == 200
    assert r.json()["state"] == "created"


def test_status_unknown_job_is_404(client):
    r = client.get("/api/jobs/doesnotexist/status")
    assert r.status_code == 404


def test_list_jobs_returns_created_job(client):
    client.post("/api/jobs", json={
        "sport": "basketball", "match_name": "Finals",
        "match_date": "2026-05-31"})
    r = client.get("/api/jobs")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["match_name"] == "Finals"
    assert items[0]["state"] == "created"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_api_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.main'`

- [ ] **Step 4: Write the implementation**

Create `backend/main.py`:

```python
"""FastAPI app: JSON API + static frontend + background worker lifespan.
HTTP layer only — delegates to JobStore/db; never touches CV logic."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException

from backend import config, db
from backend.jobs import JobStore
from backend.schemas import (CreateJobRequest, JobStatus, JobSummary)
from backend.worker import Worker


def create_app(jobs_dir: Path | str = config.JOBS_DIR,
               start_worker: bool = True) -> FastAPI:
    app = FastAPI(title="Operator App Backend")
    store = JobStore(Path(jobs_dir))
    worker = Worker(store)
    app.state.store = store
    app.state.worker = worker

    @app.on_event("startup")
    def _startup() -> None:
        if start_worker:
            worker.start()

    @app.on_event("shutdown")
    def _shutdown() -> None:
        worker.stop()

    def _require_job(job_id: str) -> None:
        if not store.exists(job_id):
            raise HTTPException(status_code=404, detail="Match not found.")

    @app.post("/api/jobs")
    def create_job(req: CreateJobRequest) -> dict:
        cfg = store.create(sport=req.sport, match_name=req.match_name,
                           match_date=req.match_date)
        return {"job_id": cfg.job_id}

    @app.get("/api/jobs")
    def list_jobs() -> list[JobSummary]:
        rows = db.list_jobs(store.conn)
        return [JobSummary(job_id=r["job_id"], sport=r["sport"],
                           match_name=r["match_name"], match_date=r["match_date"],
                           state=r["state"], created_at=r["created_at"])
                for r in rows]

    @app.get("/api/jobs/{job_id}/status")
    def job_status(job_id: str) -> JobStatus:
        _require_job(job_id)
        row = db.get_job(store.conn, job_id)
        from backend.pipeline import stage_label
        return JobStatus(
            job_id=job_id, state=row["state"], stage=row["stage"],
            progress=row["progress"],
            stage_label=stage_label(row["stage"]) if row["stage"] else None,
            error=row["error"])

    return app
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_api_jobs.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/main.py tests/backend/conftest.py tests/backend/test_api_jobs.py
git commit -m "feat(backend): API app factory + job create/list/status"
```

---

## Task 10: `main.py` (part B) — video upload + frame extraction

**Files:**
- Modify: `backend/main.py` (add two routes inside `create_app`, before `return app`)
- Test: `tests/backend/test_api_video.py`
- Test asset: uses `clips/football.mp4` if present; otherwise the test writes a tiny synthetic mp4 via opencv.

**Design note:** Upload streams the request body to `raw_video.mp4` in chunks (never `await file.read()` the whole file). The frame endpoint uses `cv2.VideoCapture` to grab one frame and returns it as JPEG bytes.

- [ ] **Step 1: Write the failing test**

Create `tests/backend/test_api_video.py`:

```python
import cv2
import numpy as np


def _make_tiny_mp4(path, frames=10, w=64, h=48):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(str(path), fourcc, 10.0, (w, h))
    for i in range(frames):
        img = np.full((h, w, 3), i * 10 % 255, dtype=np.uint8)
        vw.write(img)
    vw.release()


def _new_job(client):
    return client.post("/api/jobs", json={
        "sport": "football", "match_name": "x",
        "match_date": "2026-05-31"}).json()["job_id"]


def test_upload_then_frame(client, tmp_path):
    jid = _new_job(client)
    src = tmp_path / "tiny.mp4"
    _make_tiny_mp4(src)
    with open(src, "rb") as f:
        r = client.post(f"/api/jobs/{jid}/video", content=f.read(),
                        headers={"content-type": "application/octet-stream"})
    assert r.status_code == 200
    assert r.json()["state"] == "calibration_pending"

    fr = client.get(f"/api/jobs/{jid}/frame")
    assert fr.status_code == 200
    assert fr.headers["content-type"] == "image/jpeg"
    assert len(fr.content) > 100


def test_frame_before_upload_is_409(client):
    jid = _new_job(client)
    fr = client.get(f"/api/jobs/{jid}/frame")
    assert fr.status_code == 409
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_api_video.py -v`
Expected: FAIL — upload route returns 404/405 (route not defined yet)

- [ ] **Step 3: Add the routes**

In `backend/main.py`, add these imports at the top (with the others):

```python
import cv2
from fastapi import Request, Response
```

Then inside `create_app`, immediately before `return app`, add:

```python
    @app.post("/api/jobs/{job_id}/video")
    async def upload_video(job_id: str, request: Request) -> dict:
        _require_job(job_id)
        store.write_status(job_id, state="uploading", stage=None, progress=0,
                           stage_label="Uploading footage", error=None)
        dest = store.video_path(job_id)
        with open(dest, "wb") as out:
            async for chunk in request.stream():
                out.write(chunk)
        if dest.stat().st_size == 0:
            raise HTTPException(status_code=400, detail="No video received.")
        store.write_status(job_id, state="calibration_pending", stage=None,
                           progress=0, stage_label="Ready for court setup",
                           error=None)
        return {"state": "calibration_pending"}

    @app.get("/api/jobs/{job_id}/frame")
    def get_frame(job_id: str) -> Response:
        _require_job(job_id)
        vp = store.video_path(job_id)
        if not vp.exists() or vp.stat().st_size == 0:
            raise HTTPException(status_code=409,
                                detail="Upload a video before court setup.")
        cap = cv2.VideoCapture(str(vp))
        try:
            ok, frame = cap.read()
        finally:
            cap.release()
        if not ok:
            raise HTTPException(status_code=409,
                                detail="We couldn't read a frame from the video.")
        ok, buf = cv2.imencode(".jpg", frame)
        if not ok:
            raise HTTPException(status_code=500, detail="Frame encode failed.")
        return Response(content=buf.tobytes(), media_type="image/jpeg")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_api_video.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/backend/test_api_video.py
git commit -m "feat(backend): streamed video upload + frame extraction"
```

---

## Task 11: `main.py` (part C) — calibration, roster, deliverables, tags

**Files:**
- Modify: `backend/main.py` (add four routes before `return app`)
- Test: `tests/backend/test_api_inputs.py`

**Design note:** `/calibration`, `/roster`, `/tags` persist to the config and advance status where appropriate. `/deliverables` writes `deliverables_requested` AND enqueues the job (state `queued`) so the worker will pick it up.

- [ ] **Step 1: Write the failing test**

Create `tests/backend/test_api_inputs.py`:

```python
def _job_with_video(client, tmp_path):
    import cv2, numpy as np
    jid = client.post("/api/jobs", json={
        "sport": "football", "match_name": "x",
        "match_date": "2026-05-31"}).json()["job_id"]
    p = tmp_path / "v.mp4"
    vw = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 48))
    for i in range(5):
        vw.write(np.zeros((48, 64, 3), np.uint8))
    vw.release()
    with open(p, "rb") as f:
        client.post(f"/api/jobs/{jid}/video", content=f.read(),
                    headers={"content-type": "application/octet-stream"})
    return jid


def test_calibration_persists(client, tmp_path):
    jid = _job_with_video(client, tmp_path)
    r = client.post(f"/api/jobs/{jid}/calibration", json={"calibration_points": [
        {"pixel_x": 1, "pixel_y": 2, "real_world_label": "tl"}]})
    assert r.status_code == 200
    cfg = client.app.state.store.read_config(jid)
    assert cfg.calibration_points[0].real_world_label == "tl"


def test_roster_persists(client, tmp_path):
    jid = _job_with_video(client, tmp_path)
    r = client.post(f"/api/jobs/{jid}/roster",
                    json={"roster": ["Alex", "Sam"]})
    assert r.status_code == 200
    assert client.app.state.store.read_config(jid).roster == ["Alex", "Sam"]


def test_deliverables_enqueues_job(client, tmp_path):
    jid = _job_with_video(client, tmp_path)
    r = client.post(f"/api/jobs/{jid}/deliverables",
                    json={"deliverables_requested": ["coach_analytics"]})
    assert r.status_code == 200
    assert client.get(f"/api/jobs/{jid}/status").json()["state"] == "queued"


def test_tags_persist(client, tmp_path):
    jid = _job_with_video(client, tmp_path)
    r = client.post(f"/api/jobs/{jid}/tags",
                    json={"player_tags": {"clip_0001": "Alex"}})
    assert r.status_code == 200
    assert client.app.state.store.read_config(jid).player_tags == {
        "clip_0001": "Alex"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_api_inputs.py -v`
Expected: FAIL — routes return 404/405 (not defined yet)

- [ ] **Step 3: Add the routes**

In `backend/main.py`, extend the schema import line to include the input request models:

```python
from backend.schemas import (CalibrationRequest, CreateJobRequest, DeliverablesRequest,
                             JobStatus, JobSummary, RosterRequest, TagsRequest)
```

Then inside `create_app`, before `return app`, add:

```python
    @app.post("/api/jobs/{job_id}/calibration")
    def save_calibration(job_id: str, req: CalibrationRequest) -> dict:
        _require_job(job_id)
        store.update_config(job_id, calibration_points=[
            p.model_dump() for p in req.calibration_points])
        store.write_status(job_id, state="calibrated", stage=None, progress=0,
                           stage_label="Court setup saved", error=None)
        return {"state": "calibrated"}

    @app.post("/api/jobs/{job_id}/roster")
    def save_roster(job_id: str, req: RosterRequest) -> dict:
        _require_job(job_id)
        store.update_config(job_id, roster=req.roster)
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/tags")
    def save_tags(job_id: str, req: TagsRequest) -> dict:
        _require_job(job_id)
        store.update_config(job_id, player_tags=req.player_tags)
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/deliverables")
    def set_deliverables(job_id: str, req: DeliverablesRequest) -> dict:
        _require_job(job_id)
        store.update_config(
            job_id, deliverables_requested=list(req.deliverables_requested))
        store.write_status(job_id, state="queued", stage=None, progress=0,
                           stage_label="Waiting in line", error=None)
        return {"state": "queued"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_api_inputs.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/backend/test_api_inputs.py
git commit -m "feat(backend): calibration/roster/tags/deliverables routes"
```

---

## Task 12: `main.py` (part D) — outputs listing/download + static frontend

**Files:**
- Modify: `backend/main.py` (add two output routes + static mount)
- Test: `tests/backend/test_api_outputs.py`

**Design note:** outputs listing returns filenames inside `jobs/<id>/outputs`. Download serves a single file with a path-traversal guard (reject names containing `/`, `\`, or `..`). The static frontend is mounted LAST so it doesn't shadow `/api/...` routes.

- [ ] **Step 1: Write the failing test**

Create `tests/backend/test_api_outputs.py`:

```python
def _new_job(client):
    return client.post("/api/jobs", json={
        "sport": "football", "match_name": "x",
        "match_date": "2026-05-31"}).json()["job_id"]


def test_outputs_empty_initially(client):
    jid = _new_job(client)
    r = client.get(f"/api/jobs/{jid}/outputs")
    assert r.status_code == 200
    assert r.json() == []


def test_outputs_list_and_download(client):
    jid = _new_job(client)
    out_dir = client.app.state.store.job_dir(jid) / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.pdf").write_bytes(b"%PDF-1.4 fake")
    listing = client.get(f"/api/jobs/{jid}/outputs").json()
    assert "report.pdf" in listing
    dl = client.get(f"/api/jobs/{jid}/outputs/report.pdf")
    assert dl.status_code == 200
    assert dl.content == b"%PDF-1.4 fake"


def test_download_path_traversal_blocked(client):
    jid = _new_job(client)
    r = client.get(f"/api/jobs/{jid}/outputs/..%2f..%2fjobs.sqlite3")
    assert r.status_code in (400, 404)


def test_root_serves_frontend(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_api_outputs.py -v`
Expected: FAIL — output routes 404; `/` not served yet

- [ ] **Step 3: Add the routes + static mount**

In `backend/main.py`, add to the top imports:

```python
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
```

Inside `create_app`, before `return app`, add the output routes:

```python
    @app.get("/api/jobs/{job_id}/outputs")
    def list_outputs(job_id: str) -> list[str]:
        _require_job(job_id)
        out_dir = store.job_dir(job_id) / "outputs"
        if not out_dir.is_dir():
            return []
        return sorted(p.name for p in out_dir.iterdir() if p.is_file())

    @app.get("/api/jobs/{job_id}/outputs/{filename}")
    def download_output(job_id: str, filename: str) -> FileResponse:
        _require_job(job_id)
        if "/" in filename or "\\" in filename or ".." in filename:
            raise HTTPException(status_code=400, detail="Invalid file name.")
        path = store.job_dir(job_id) / "outputs" / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail="File not found.")
        return FileResponse(str(path), filename=filename)
```

Then, as the LAST statement before `return app`, mount the frontend (only if the directory exists, so tests in a bare tmp dir still work — the repo `Website/` always exists in practice):

```python
    if config.WEBSITE_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(config.WEBSITE_DIR),
                                   html=True), name="frontend")
```

Finally, add the module entrypoint at the very bottom of the file (outside `create_app`):

```python
app = create_app()  # module-level app for `uvicorn backend.main:app`


def main() -> None:
    import uvicorn
    print(f"Operator App backend on http://{config.HOST}:{config.PORT}")
    print("Find your laptop's LAN IP (ipconfig) and open it from other devices.")
    uvicorn.run("backend.main:app", host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_api_outputs.py -v`
Expected: PASS (4 passed). The `test_root_serves_frontend` test passes because `create_app` mounts the real repo `Website/` (which contains `index.html`).

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/backend/test_api_outputs.py
git commit -m "feat(backend): outputs listing/download + static frontend mount"
```

---

## Task 13: End-to-end stub flow test

**Files:**
- Test: `tests/backend/test_e2e_stub_flow.py`

**Design note:** This proves the whole orchestration works without a GPU: create → upload → calibration → deliverables(enqueue) → worker.run_one() → ready → list+download output. Uses `start_worker=False` and drives the worker manually for determinism.

- [ ] **Step 1: Write the test**

Create `tests/backend/test_e2e_stub_flow.py`:

```python
import cv2
import numpy as np


def _tiny_mp4(path):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 48))
    for _ in range(5):
        vw.write(np.zeros((48, 64, 3), np.uint8))
    vw.release()


def test_full_stub_flow_to_ready(client, tmp_path):
    # 1. create
    jid = client.post("/api/jobs", json={
        "sport": "football", "match_name": "U14 Final",
        "match_date": "2026-05-31"}).json()["job_id"]

    # 2. upload
    src = tmp_path / "tiny.mp4"
    _tiny_mp4(src)
    with open(src, "rb") as f:
        client.post(f"/api/jobs/{jid}/video", content=f.read(),
                    headers={"content-type": "application/octet-stream"})

    # 3. calibration
    client.post(f"/api/jobs/{jid}/calibration", json={"calibration_points": [
        {"pixel_x": 0, "pixel_y": 0, "real_world_label": "tl"},
        {"pixel_x": 63, "pixel_y": 0, "real_world_label": "tr"},
        {"pixel_x": 63, "pixel_y": 47, "real_world_label": "br"},
        {"pixel_x": 0, "pixel_y": 47, "real_world_label": "bl"}]})

    # 4. select deliverables (enqueues)
    client.post(f"/api/jobs/{jid}/deliverables", json={
        "deliverables_requested": ["coach_analytics", "event_highlights"]})
    assert client.get(f"/api/jobs/{jid}/status").json()["state"] == "queued"

    # 5. run the worker (deterministic)
    assert client.app.state.worker.run_one() is True

    # 6. ready + outputs present
    status = client.get(f"/api/jobs/{jid}/status").json()
    assert status["state"] == "ready"
    assert status["progress"] == 100
    outputs = client.get(f"/api/jobs/{jid}/outputs").json()
    assert "analytics.stub.txt" in outputs
    assert "events.stub.txt" in outputs
    dl = client.get(f"/api/jobs/{jid}/outputs/analytics.stub.txt")
    assert dl.status_code == 200
```

- [ ] **Step 2: Run the test**

Run: `.venv\Scripts\python.exe -m pytest tests/backend/test_e2e_stub_flow.py -v`
Expected: PASS (1 passed)

- [ ] **Step 3: Run the FULL backend test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/backend -v`
Expected: PASS (all tests across all files green)

- [ ] **Step 4: Manual smoke (optional but recommended)**

Run: `.venv\Scripts\python.exe -m backend.main`
Expected: prints `Operator App backend on http://0.0.0.0:8000` and the LAN hint; opening `http://localhost:8000/` in a browser serves the existing `index.html` mockup. Stop with Ctrl+C.

- [ ] **Step 5: Commit**

```bash
git add tests/backend/test_e2e_stub_flow.py
git commit -m "test(backend): end-to-end stub flow create->ready->download"
```

---

## Self-Review (completed during plan authoring)

**Spec coverage (Plan 1 portion):**
- API endpoints (spec §4) — Tasks 9–12 cover create, list, status, video, frame, calibration, roster, tags, deliverables, outputs list/download, static serve. ✅ (`/tagging-clips` is deferred to Plan 4, where the tagging flow is wired — noted explicitly.)
- Job-config-file contract (spec §2) — Tasks 3, 6. ✅
- State machine (spec §3) — Tasks 7, 8 (stub stages; `tagging_pending` pause implemented). ✅
- Background worker, one-at-a-time, durable SQLite state (spec §6) — Tasks 4, 8. ✅
- Friendly errors + server-side logs (spec §7) — Task 5, used in Task 8. ✅
- Streamed upload, no full read into memory (spec constraints) — Task 10. ✅
- LAN bind + URL hint (spec §1) — Task 12 entrypoint. ✅
- **Deferred to later plans (by design, not gaps):** real CV stage wiring + adapters (Plan 3), frontend `fetch` wiring (Plan 2), `/tagging-clips` + reel assembly (Plan 4), browser notifications + resumability-on-restart hardening (Plan 5). Resumability of the *stage resume point* is already scaffolded in `worker.run_one` (the `tagging_done` skip).

**Placeholder scan:** No TBD/TODO/"handle errors appropriately" — every code step has complete code. ✅

**Type/name consistency:** `JobStore` methods (`create`, `read_config`, `update_config`, `write_status`, `job_dir`, `video_path`, `exists`) are used identically in Tasks 6–13. `pipeline.resolve_stages` / `stage_label` / `run_stage_stub`, `db.next_queued` / `get_job` / `update_job` / `list_jobs`, and `Worker.run_one` names match across tasks. Schema names (`CreateJobRequest`, `CalibrationRequest`, `RosterRequest`, `TagsRequest`, `DeliverablesRequest`, `JobStatus`, `JobSummary`, `JobConfig`, `CalibrationPoint`) are consistent. ✅

**Note on FastAPI lifecycle:** the plan uses `@app.on_event("startup"/"shutdown")`. If the installed FastAPI version emits deprecation warnings for these, that is acceptable for Plan 1; Plan 5 may migrate to the `lifespan=` context manager. This does not block any test.
