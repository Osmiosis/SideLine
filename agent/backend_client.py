"""Thin client for the LOCAL backend FastAPI (backend/main.py endpoints).
The agent never touches the local SQLite directly — one writer: the server."""
import requests

from agent.config import settings

B = settings.backend_url


def is_up() -> bool:
    try:
        requests.get(f"{B}/api/jobs", timeout=5).raise_for_status()
        return True
    except requests.RequestException:
        return False


def create_job(sport: str, match_name: str, match_date: str) -> str:
    r = requests.post(f"{B}/api/jobs", json={
        "sport": sport, "match_name": match_name, "match_date": match_date},
        timeout=30)
    r.raise_for_status()
    return r.json()["job_id"]


def upload_video(job_id: str, path: str) -> None:
    # the endpoint consumes the RAW request body (request.stream()),
    # NOT multipart — send the file object directly
    with open(path, "rb") as f:
        r = requests.post(f"{B}/api/jobs/{job_id}/video", data=f,
                          headers={"Content-Type": "video/mp4"}, timeout=3600)
    r.raise_for_status()


def set_deliverables(job_id: str, deliverables: list[str]) -> None:
    r = requests.post(f"{B}/api/jobs/{job_id}/deliverables",
                      json={"deliverables_requested": deliverables}, timeout=30)
    r.raise_for_status()


def status(job_id: str) -> dict:
    r = requests.get(f"{B}/api/jobs/{job_id}/status", timeout=30)
    r.raise_for_status()
    return r.json()


def output_paths(job_id: str) -> list[str]:
    r = requests.get(f"{B}/api/jobs/{job_id}/outputs", timeout=30)
    r.raise_for_status()
    return r.json()


def download_output(job_id: str, rel_path: str, dest: str) -> None:
    with requests.get(f"{B}/api/jobs/{job_id}/outputs/{rel_path}",
                      stream=True, timeout=3600) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                f.write(chunk)
