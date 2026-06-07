"""The agent's orchestration: sequences ingest → process-mirror → deliver →
cleanup. Policy lives in logic.py; I/O in cloud.py / drive.py /
backend_client.py — all injectable for testing.

Crash-safety contract (tested):
- the Drive raw file is deleted ONLY after the video is inside the local
  backend AND the cloud row records local_job_id + state=processing;
- cloud state 'ready' is written ONLY after every output file is in Drive.
"""
import os
import time
from datetime import datetime, timedelta, timezone

from agent import backend_client as _backend
from agent import cloud as _cloud
from agent import drive as _drive
from agent import notify as _notify
from agent.config import settings
from agent.logic import (decide_deliverables, map_local_status, plan_delivery,
                         should_promote)
from agent.media import probe_duration_sec  # re-exported for monkeypatching

UNREADABLE_MSG = ("We couldn't read the video file. Please check it plays on "
                  "your device and submit the match again.")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ingest_one(job, *, cloud=_cloud, drv=_drive, backend=_backend,
               notify=_notify, workdir="agent_work") -> None:
    """Move one cloud job from 'uploaded' into the local pipeline."""
    job_id = job["id"]
    os.makedirs(workdir, exist_ok=True)
    raw = os.path.join(workdir, f"{job_id}.mp4")
    token = drv.access_token()

    print(f"[{job_id[:8]}] downloading raw footage...")
    drv.download_file(token, job["drive_file_id"], raw)

    duration = probe_duration_sec(raw)
    decision = decide_deliverables(duration, job["deliverables"])
    if decision is None:
        print(f"[{job_id[:8]}] unreadable video -> failed")
        drv.delete_file(token, job["drive_file_id"])  # quota back
        cloud.update_job(job_id, state="failed", error_message=UNREADABLE_MSG,
                         drive_file_id=None)
        notify.send_email(cloud.user_email(job["user_id"]),
                          *notify.build_failed_email(job["match_name"],
                                                     UNREADABLE_MSG))
        os.remove(raw)
        return

    deliverables, note = decision
    if note:
        # downgrade is recorded on the cloud row — it is the source of truth
        # mirror_one reads when it enqueues after calibration
        cloud.update_job(job_id, deliverables=deliverables)
    match_date = job.get("match_date") or job["created_at"][:10]
    # cloud id embedded in the local name -> orphans are identifiable
    local_name = f"{job['match_name']} [{job_id[:8]}]"

    local_id = backend.create_job(job["sport"], local_name, match_date)
    print(f"[{job_id[:8]}] local job {local_id}; uploading video to backend...")
    backend.upload_video(local_id, raw)
    # deliverables are NOT set here: that would enqueue the job and skip the
    # calibration gate. mirror_one enqueues once the operator has calibrated.

    # milestone is durable -> record it, THEN free the Drive quota
    cloud.update_job(job_id, state="processing", local_job_id=local_id,
                     progress=0,
                     state_detail=note or "Processing has started.")
    drv.delete_file(token, job["drive_file_id"])
    cloud.update_job(job_id, drive_file_id=None)
    os.remove(raw)
    print(f"[{job_id[:8]}] ingested -> local {local_id}")


def mirror_one(job, *, cloud=_cloud, backend=_backend, notify=_notify) -> str:
    """Reflect the local job's state into the cloud row. Returns the local
    state so the caller can react to 'ready'/'failed'."""
    status = backend.status(job["local_job_id"])
    if status["state"] == "calibrated":
        # court setup done in the local UI -> NOW enqueue with the user's
        # (possibly downgraded) deliverables; the worker takes it from here
        print(f"[{job['id'][:8]}] calibrated -> enqueueing "
              f"{job['deliverables']}")
        backend.set_deliverables(job["local_job_id"], job["deliverables"])
        status = backend.status(job["local_job_id"])
    patch = map_local_status(status)
    if patch["state"] == "ready":
        return "ready"  # caller must deliver first
    # don't overwrite a downgrade note while merely queued
    if (patch["state"] == "processing" and status["state"] == "queued"
            and job.get("state_detail") and "analytics only" in job["state_detail"]):
        patch.pop("state_detail", None)
    if patch["state"] == "failed":
        cloud.update_job(job["id"], **patch)
        notify.send_email(cloud.user_email(job["user_id"]),
                          *notify.build_failed_email(job["match_name"],
                                                     patch["error_message"]))
        return "failed"
    cloud.update_job(job["id"], **patch)
    return status["state"]


def deliver(job, *, cloud=_cloud, drv=_drive, backend=_backend,
            notify=_notify, workdir="agent_work") -> None:
    """Upload all local outputs into <job folder>/deliverables, share, flip
    the cloud row to ready, email the user. Idempotent on re-run."""
    job_id = job["id"]
    os.makedirs(workdir, exist_ok=True)
    token = drv.access_token()

    outputs = backend.output_paths(job["local_job_id"])
    plan = plan_delivery(job["deliverables"], outputs)
    folders: dict = {}
    existing: dict = {}
    uploaded = 0
    for rel, sub, name in plan:
        if sub not in folders:
            folders[sub] = drv.ensure_folder(token, sub, job["drive_folder_id"])
            existing[sub] = drv.list_names(token, folders[sub])
        if name in existing[sub]:
            continue  # idempotent re-run
        tmp = os.path.join(workdir, name)
        backend.download_output(job["local_job_id"], rel, tmp)
        drv.upload_file(token, tmp, folders[sub], name)
        os.remove(tmp)
        uploaded += 1
    print(f"[{job_id[:8]}] delivered {uploaded} file(s) "
          f"({len(plan) - uploaded} already up)")

    results_url = drv.share_anyone(token, job["drive_folder_id"])
    expires = _now() + timedelta(days=settings.expiry_days)
    cloud.update_job(job_id, state="ready", results_url=results_url,
                     progress=100, state_detail="Ready",
                     expires_at=expires.isoformat())

    notify.send_email(cloud.user_email(job["user_id"]),
                      *notify.build_ready_email(job["match_name"], results_url,
                                                expires.date().isoformat()))
    print(f"[{job_id[:8]}] READY -> {results_url}")


def cleanup_expired(*, cloud=_cloud, drv=_drive) -> None:
    """Delete Drive folders of ready jobs past expiry; mark rows expired."""
    now_iso = _now().isoformat()
    for job in cloud.jobs_in_state("ready"):
        if job.get("expires_at") and job["expires_at"] <= now_iso:
            print(f"[{job['id'][:8]}] expiring...")
            if job.get("drive_folder_id"):
                drv.delete_file(drv.access_token(), job["drive_folder_id"])
            cloud.update_job(job["id"], state="expired", results_url=None,
                             drive_folder_id=None,
                             state_detail="These results have expired.")


def promote_quota_waiting(*, cloud=_cloud, drv=_drive, notify=_notify) -> None:
    """Give the oldest waiting job its turn once Drive has headroom."""
    waiting = cloud.jobs_in_state("quota_waiting")
    if not waiting:
        return
    if not should_promote(drv.free_bytes(drv.access_token()),
                          settings.promote_free_bytes):
        return
    job = waiting[0]  # oldest first
    cloud.update_job(job["id"], state="approved",
                     state_detail="It's your turn — upload your footage now.")
    job_url = f"{settings.site_origin}/job.html?id={job['id']}"
    notify.send_email(cloud.user_email(job["user_id"]),
                      *notify.build_promoted_email(job["match_name"], job_url))
    print(f"[{job['id'][:8]}] promoted from quota_waiting")


def run_loop() -> None:
    """The agent's forever-loop: one pass every poll interval."""
    print(f"agent: polling every {settings.poll_seconds}s; backend "
          f"{settings.backend_url}")
    while True:
        try:
            run_once()
        except Exception as e:  # noqa: BLE001 — log and keep looping (spec §8)
            print(f"agent: pass failed ({e}); retrying next cycle")
        time.sleep(settings.poll_seconds)


def run_once(*, cloud=_cloud, drv=_drive, backend=_backend) -> None:
    """One full pass: ingest new, mirror active, deliver finished, clean up."""
    if not backend.is_up():
        print("agent: local backend is not running — start it with "
              "`python -m backend.main`. Skipping this pass.")
        return
    for job in cloud.jobs_in_state("uploaded"):
        ingest_one(job, cloud=cloud, drv=drv, backend=backend)
    for state in ("processing", "operator_action"):
        for job in cloud.jobs_in_state(state):
            if not job.get("local_job_id"):
                continue
            local_state = mirror_one(job, cloud=cloud, backend=backend)
            if local_state == "ready":
                deliver(job, cloud=cloud, drv=drv, backend=backend)
    cleanup_expired(cloud=cloud, drv=drv)
    promote_quota_waiting(cloud=cloud, drv=drv)
