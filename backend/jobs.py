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
