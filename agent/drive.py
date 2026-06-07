"""Google Drive v3 client for the agent (refresh-token grant, requests only).

Mirrors supabase/functions/_shared/google.ts so both sides speak the same
folder/file conventions.
"""
import os

import requests

from agent.config import settings

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
CHUNK = 32 * 1024 * 1024  # multiple of 256 KiB (Drive resumable-upload rule)


def access_token() -> str:
    r = requests.post(TOKEN_URL, data={
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "refresh_token": settings.google_refresh_token,
        "grant_type": "refresh_token"}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def free_bytes(token: str) -> int:
    r = requests.get(f"{API}/about?fields=storageQuota", headers=_h(token), timeout=30)
    r.raise_for_status()
    q = r.json()["storageQuota"]
    if not q.get("limit"):
        return 2 ** 53
    return int(q["limit"]) - int(q["usage"])


def ensure_folder(token: str, name: str, parent_id: str | None) -> str:
    safe = name.replace("'", "\\'")
    q = (f"name = '{safe}' and mimeType = 'application/vnd.google-apps.folder' "
         "and trashed = false")
    if parent_id:
        q += f" and '{parent_id}' in parents"
    r = requests.get(f"{API}/files", params={"q": q, "fields": "files(id)"},
                     headers=_h(token), timeout=30)
    r.raise_for_status()
    files = r.json().get("files", [])
    if files:
        return files[0]["id"]
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    r = requests.post(f"{API}/files", json=body, headers=_h(token), timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def list_names(token: str, folder_id: str) -> set[str]:
    names: set[str] = set()
    page = None
    while True:
        params = {"q": f"'{folder_id}' in parents and trashed = false",
                  "fields": "nextPageToken, files(name)", "pageSize": 1000}
        if page:
            params["pageToken"] = page
        r = requests.get(f"{API}/files", params=params, headers=_h(token), timeout=30)
        r.raise_for_status()
        data = r.json()
        names.update(f["name"] for f in data.get("files", []))
        page = data.get("nextPageToken")
        if not page:
            return names


def upload_file(token: str, path: str, folder_id: str, name: str) -> str:
    """Resumable upload in sequential 32 MB chunks. Returns the file id."""
    size = os.path.getsize(path)
    r = requests.post(
        f"{UPLOAD}/files?uploadType=resumable",
        headers={**_h(token), "Content-Type": "application/json",
                 "X-Upload-Content-Length": str(size)},
        json={"name": name, "parents": [folder_id]}, timeout=30)
    r.raise_for_status()
    session = r.headers["Location"]
    with open(path, "rb") as f:
        offset = 0
        while offset < size or size == 0:
            blob = f.read(CHUNK)
            end = offset + len(blob) - 1
            r = requests.put(session, data=blob, headers={
                "Content-Range": f"bytes {offset}-{end}/{size}"}, timeout=600)
            if r.status_code in (200, 201):
                return r.json()["id"]
            if r.status_code != 308:
                raise RuntimeError(f"upload chunk failed: {r.status_code} {r.text}")
            offset = end + 1
    raise RuntimeError("upload ended without a completed response")


def download_file(token: str, file_id: str, dest: str) -> None:
    """Streamed download; resumes from an existing partial file via Range."""
    offset = os.path.getsize(dest) if os.path.exists(dest) else 0
    headers = _h(token)
    if offset:
        headers["Range"] = f"bytes={offset}-"
    with requests.get(f"{API}/files/{file_id}?alt=media", headers=headers,
                      stream=True, timeout=600) as r:
        if offset and r.status_code == 416:   # nothing left — already complete
            return
        if offset and r.status_code != 206:   # server ignored Range: start over
            offset = 0
        r.raise_for_status()
        mode = "ab" if offset else "wb"
        with open(dest, mode) as f:
            for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                f.write(chunk)


def share_anyone(token: str, file_id: str) -> str:
    """'Anyone with the link can view' + return the webViewLink."""
    requests.post(f"{API}/files/{file_id}/permissions",
                  json={"role": "reader", "type": "anyone"},
                  headers=_h(token), timeout=30).raise_for_status()
    r = requests.get(f"{API}/files/{file_id}?fields=webViewLink",
                     headers=_h(token), timeout=30)
    r.raise_for_status()
    return r.json()["webViewLink"]


def delete_file(token: str, file_id: str) -> None:
    requests.delete(f"{API}/files/{file_id}", headers=_h(token), timeout=30)
    # 404 is fine — already gone
