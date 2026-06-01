"""FastAPI app: JSON API + static frontend + background worker lifespan.
HTTP layer only — delegates to JobStore/db; never touches CV logic."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend import config, db
from backend.jobs import JobStore
from backend.pipeline import stage_label
from backend.schemas import (CalibrationRequest, CreateJobRequest, DeliverablesRequest,
                             JobStatus, JobSummary, RosterRequest, TagsRequest)
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
        return JobStatus(
            job_id=job_id, state=row["state"], stage=row["stage"],
            progress=row["progress"],
            stage_label=stage_label(row["stage"]) if row["stage"] else None,
            error=row["error"])

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
            dest.unlink(missing_ok=True)
            store.write_status(job_id, state="created", stage=None, progress=0,
                               stage_label=None, error=None)
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

    @app.get("/api/jobs/{job_id}/tagging-clips")
    def get_tagging_clips(job_id: str) -> dict:
        _require_job(job_id)
        manifest_path = store.clips_manifest_path(job_id)
        if not manifest_path.exists():
            return {"ready": False, "clips": []}
        records = json.loads(manifest_path.read_text(encoding="utf-8"))
        clips = []
        for rec in records:
            clip_id = rec.get("clip_id") or rec.get("clip", "")
            # If clip field is a full path, take the basename
            if not clip_id or "/" in clip_id or "\\" in clip_id:
                clip_id = Path(clip_id).name
            clips.append({
                "clip_id": clip_id,
                "track_id": rec.get("track_id"),
                "role": rec.get("role"),
                "start_frame": rec.get("start_frame"),
                "end_frame": rec.get("end_frame"),
                "video_url": f"/api/jobs/{job_id}/tagging-clips/{clip_id}/video",
            })
        return {"ready": True, "clips": clips}

    @app.get("/api/jobs/{job_id}/tagging-clips/{clip}/video")
    def get_clip_video(job_id: str, clip: str) -> FileResponse:
        _require_job(job_id)
        try:
            path = store.clip_path(job_id, clip)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid clip name.")
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Clip not found.")
        return FileResponse(str(path), media_type="video/mp4", filename=clip)

    @app.post("/api/jobs/{job_id}/tags")
    def save_tags(job_id: str, req: TagsRequest) -> dict:
        _require_job(job_id)
        # Persist tags into job config
        store.update_config(job_id, player_tags=req.player_tags)
        # Write clip_tags.json for assemble_player_reels(_bb) to read
        store.write_clip_tags(job_id, req.player_tags)
        # Re-enqueue to reels ONLY if the job is actually parked at the tagging
        # pause; otherwise just persist the tags (don't jump to reels with no clips).
        row = db.get_job(store.conn, job_id)
        if row and row["state"] == "tagging_pending":
            store.write_status(job_id, state="queued", stage="tagging_done",
                               progress=row["progress"] or 0, stage_label=None, error=None)
            return {"state": "queued"}
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/deliverables")
    def set_deliverables(job_id: str, req: DeliverablesRequest) -> dict:
        _require_job(job_id)
        store.update_config(
            job_id, deliverables_requested=list(req.deliverables_requested))
        store.write_status(job_id, state="queued", stage=None, progress=0,
                           stage_label="Waiting in line", error=None)
        return {"state": "queued"}

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

    if config.WEBSITE_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(config.WEBSITE_DIR),
                                   html=True), name="frontend")

    return app


app = create_app()  # module-level app for `uvicorn backend.main:app`


def main() -> None:
    import uvicorn
    print(f"Operator App backend on http://{config.HOST}:{config.PORT}")
    print("Find your laptop's LAN IP (ipconfig) and open it from other devices.")
    uvicorn.run("backend.main:app", host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
