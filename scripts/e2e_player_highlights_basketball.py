"""Two-part player-highlights e2e (basketball) on clips/basketball.mp4. GPU; minutes.
Runs to tagging_pending, tags each clip to a roster name, resumes to reels.
Run: .venv\\Scripts\\python.exe scripts\\e2e_player_highlights_basketball.py"""
import sys, json, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.jobs import JobStore
from backend.worker import Worker
from backend import db

ROOT = Path(__file__).resolve().parent.parent
CLIP = ROOT / "clips" / "basketball.mp4"
ROSTER = ["Alex", "Sam", "Jordan", "Riley", "Casey", "Morgan"]


def main() -> int:
    jobs_dir = ROOT / "build" / "e2e_jobs_ph_bb"
    if jobs_dir.exists():
        shutil.rmtree(jobs_dir)
    store = JobStore(jobs_dir)
    cfg = store.create(sport="basketball", match_name="PH Basketball", match_date="2026-06-01")
    jid = cfg.job_id
    shutil.copy(CLIP, store.video_path(jid))
    store.update_config(jid, calibration_points=[
        {"pixel_x": 40, "pixel_y": 60, "real_world_label": "far-left corner"},
        {"pixel_x": 600, "pixel_y": 60, "real_world_label": "far-right corner"},
        {"pixel_x": 620, "pixel_y": 350, "real_world_label": "near-right corner"},
        {"pixel_x": 20, "pixel_y": 350, "real_world_label": "near-left corner"}],
        roster=ROSTER, deliverables_requested=["player_highlights"])
    store.write_status(jid, state="queued", stage=None, progress=0,
                       stage_label=None, error=None)

    # Part 1: run to the tagging pause
    Worker(store).run_one()
    row = db.get_job(store.conn, jid)
    print("after part1:", row["state"], "stage:", row["stage"], "error:", row["error"])
    assert row["state"] == "tagging_pending", f"expected pause, got {row['state']} ({row['error']})"

    manifest = json.loads(store.clips_manifest_path(jid).read_text())
    clips = manifest["clips"] if isinstance(manifest, dict) else manifest
    print(f"taggable clips: {len(clips)}")
    assert len(clips) >= 1, "no taggable clips generated"

    tags = {Path(c["clip"]).name: ROSTER[i % len(ROSTER)] for i, c in enumerate(clips)}
    store.write_clip_tags(jid, tags)
    print("wrote tags:", tags)

    # Part 2: resume to reels
    store.write_status(jid, state="queued", stage="tagging_done", progress=60,
                       stage_label=None, error=None)
    Worker(store).run_one()
    row = db.get_job(store.conn, jid)
    print("after part2:", row["state"], "stage:", row["stage"], "error:", row["error"])

    out = store.job_dir(jid) / "outputs"
    reels = sorted(str(p.relative_to(out)) for p in out.rglob("*.mp4")
                   if "player_highlights" in str(p))
    print("reels:", reels)
    assert row["state"] == "ready", f"job failed at {row['stage']}: {row['error']}"
    assert reels, "no player reels produced"
    print("E2E PH BASKETBALL: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
