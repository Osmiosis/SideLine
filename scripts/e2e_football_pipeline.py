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
