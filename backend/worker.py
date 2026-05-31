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
        stage = "unknown"
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
