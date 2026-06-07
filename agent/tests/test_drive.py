"""Round-trips a real (tiny) file through the operator's Drive: folder create,
resumable upload, share, listed, downloaded byte-identical, deleted."""
import os

import pytest

from agent import drive


@pytest.fixture()
def tmpdirpath(tmp_path):
    return tmp_path


def test_drive_roundtrip(tmpdirpath):
    token = drive.access_token()
    folder_id = None
    try:
        folder_id = drive.ensure_folder(token, "AGENT TEST FOLDER", None)
        # idempotent: asking again returns the same folder
        assert drive.ensure_folder(token, "AGENT TEST FOLDER", None) == folder_id

        src = tmpdirpath / "payload.bin"
        src.write_bytes(b"sideline agent " * 1000)  # ~15 KB
        file_id = drive.upload_file(token, str(src), folder_id, "payload.bin")

        names = drive.list_names(token, folder_id)
        assert "payload.bin" in names

        link = drive.share_anyone(token, folder_id)
        assert link.startswith("https://")

        dest = tmpdirpath / "back.bin"
        drive.download_file(token, file_id, str(dest))
        assert dest.read_bytes() == src.read_bytes()

        free = drive.free_bytes(token)
        assert free > 0
    finally:
        if folder_id:
            drive.delete_file(drive.access_token(), folder_id)


def test_download_resumes_from_partial(tmpdirpath):
    token = drive.access_token()
    folder_id = None
    try:
        folder_id = drive.ensure_folder(token, "AGENT TEST FOLDER", None)
        src = tmpdirpath / "payload2.bin"
        src.write_bytes(os.urandom(70_000))
        file_id = drive.upload_file(token, str(src), folder_id, "payload2.bin")

        dest = tmpdirpath / "partial.bin"
        dest.write_bytes(src.read_bytes()[:30_000])  # simulate a dead download
        drive.download_file(token, file_id, str(dest))
        assert dest.read_bytes() == src.read_bytes()
    finally:
        if folder_id:
            drive.delete_file(drive.access_token(), folder_id)
