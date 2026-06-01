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
        steps = pipeline.resolve_steps(cfg)
        ctx = pipeline.StepCtx(job_dir=self.store.job_dir(job_id),
                               job_id=job_id, sport=cfg.sport)
        total = len(steps)

        # Resume index: if re-enqueued after tagging, skip to the step AFTER tagging_pending.
        start_idx = 0
        if row["stage"] == "tagging_done":
            for i, s in enumerate(steps):
                if s.key == "tagging_pending":
                    start_idx = i + 1
                    break

        stage = "unknown"
        try:
            for i, step in enumerate(steps[start_idx:], start=start_idx):
                stage = step.ui_stage
                # Pause marker: park the job and return without running a command.
                if step.key == "tagging_pending":
                    self.store.write_status(job_id, state="tagging_pending",
                        stage="tagging_pending",
                        progress=round(100 * i / total),
                        stage_label=pipeline.stage_label("tagging_pending"), error=None)
                    return True
                self.store.write_status(job_id, state=step.ui_stage, stage=step.ui_stage,
                    progress=round(100 * i / total),
                    stage_label=pipeline.stage_label(step.ui_stage), error=None)
                pipeline.run_step(step, ctx, self.store.job_dir(job_id) / "logs")
            self.store.write_status(job_id, state="ready", stage="ready", progress=100,
                stage_label=pipeline.stage_label("ready"), error=None)
        except Exception:  # noqa: BLE001 — friendly out, detail to log
            errors.log_stage_failure(
                self.store.job_dir(job_id), stage=stage,
                detail=traceback.format_exc())
            self.store.write_status(
                job_id, state="failed", stage=stage,
                progress=0, stage_label=None,
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
