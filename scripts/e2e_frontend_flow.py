"""End-to-end driver mirroring the wired UI's request sequence.
Run: .venv\\Scripts\\python.exe scripts\\e2e_frontend_flow.py
Exits 0 on success, non-zero on any failed step."""
import sys, tempfile
from pathlib import Path

# make the repo root importable when run directly (not via pytest)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
from fastapi.testclient import TestClient

from backend.main import create_app


def _tiny_mp4(path):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 48))
    for _ in range(5):
        vw.write(np.zeros((48, 64, 3), np.uint8))
    vw.release()


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    app = create_app(jobs_dir=tmp / "jobs", start_worker=False)
    c = TestClient(app)

    # 1. Setup: create job (sport + name + date)
    jid = c.post("/api/jobs", json={"sport": "football",
                 "match_name": "Wired Flow", "match_date": "2026-05-31"}).json()["job_id"]
    print("created", jid)

    # 2. Setup: stream upload (raw body, like XHR.send(file))
    vid = tmp / "v.mp4"; _tiny_mp4(vid)
    r = c.post(f"/api/jobs/{jid}/video", content=vid.read_bytes(),
               headers={"content-type": "application/octet-stream"})
    assert r.status_code == 200 and r.json()["state"] == "calibration_pending", r.text
    print("uploaded")

    # 3. Court: fetch frame, then save calibration (4 corner labels)
    assert c.get(f"/api/jobs/{jid}/frame").status_code == 200
    pts = [{"pixel_x": 9, "pixel_y": 9, "real_world_label": "far-left corner"},
           {"pixel_x": 55, "pixel_y": 9, "real_world_label": "far-right corner"},
           {"pixel_x": 58, "pixel_y": 40, "real_world_label": "near-right corner"},
           {"pixel_x": 5, "pixel_y": 40, "real_world_label": "near-left corner"}]
    assert c.post(f"/api/jobs/{jid}/calibration",
                  json={"calibration_points": pts}).status_code == 200
    print("calibrated")

    # 4. Deliverables: enqueue the two settled deliverables
    r = c.post(f"/api/jobs/{jid}/deliverables",
               json={"deliverables_requested": ["coach_analytics", "event_highlights"]})
    assert r.status_code == 200 and r.json()["state"] == "queued", r.text
    print("queued")

    # 5. Processing: run the worker (stub), then poll status to ready
    app.state.worker.run_one()
    st = c.get(f"/api/jobs/{jid}/status").json()
    assert st["state"] == "ready" and st["progress"] == 100, st
    print("ready")

    # 6. Results: list + download outputs
    files = c.get(f"/api/jobs/{jid}/outputs").json()
    assert "analytics.stub.txt" in files and "events.stub.txt" in files, files
    dl = c.get(f"/api/jobs/{jid}/outputs/analytics.stub.txt")
    assert dl.status_code == 200, dl.status_code
    print("downloaded", files)

    # 7. Dashboard: the job shows up in the list
    listing = c.get("/api/jobs").json()
    assert any(j["job_id"] == jid for j in listing), listing
    print("listed")

    print("E2E FRONTEND FLOW: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
