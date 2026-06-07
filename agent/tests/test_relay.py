"""Orchestration contract tests with in-memory fakes. The key assertions are
about ORDER: drive raw deletion only after the video is safely local+backend,
cloud 'ready' only after delivery completed."""
from agent import relay


class FakeCloud:
    def __init__(self, jobs):
        self.jobs = {j["id"]: dict(j) for j in jobs}
        self.log = []

    def jobs_in_state(self, state):
        return [dict(j) for j in self.jobs.values() if j["state"] == state]

    def get_job(self, job_id):
        return dict(self.jobs[job_id])

    def update_job(self, job_id, **fields):
        self.jobs[job_id].update(fields)
        self.log.append(("update", job_id, dict(fields)))

    def user_email(self, user_id):
        return "user@example.com"


class FakeDrive:
    def __init__(self):
        self.deleted = []
        self.uploaded = []
        self.existing = set()
        self.log = []

    def access_token(self):
        return "tok"

    def download_file(self, token, file_id, dest):
        self.log.append(("download", file_id))
        with open(dest, "wb") as f:
            f.write(b"video-bytes")

    def delete_file(self, token, file_id):
        self.deleted.append(file_id)
        self.log.append(("delete", file_id))

    def ensure_folder(self, token, name, parent):
        return f"folder-{name}"

    def list_names(self, token, folder_id):
        return set(self.existing)

    def upload_file(self, token, path, folder_id, name):
        self.uploaded.append((folder_id, name))
        self.log.append(("upload", folder_id, name))
        return f"id-{name}"

    def share_anyone(self, token, file_id):
        return "https://drive.google.com/shared"

    def free_bytes(self, token):
        return 10 * 1024 ** 3


class FakeBackend:
    def __init__(self):
        self.log = []
        self.deliverables = None
        self.status_value = {"state": "queued", "progress": 0,
                             "stage_label": "Waiting in line", "error": None}

    def create_job(self, sport, match_name, match_date):
        self.log.append("create_job")
        return "local-1"

    def upload_video(self, job_id, path):
        self.log.append("upload_video")

    def set_deliverables(self, job_id, deliverables):
        self.deliverables = deliverables
        self.log.append("set_deliverables")
        # enqueueing flips the local job to queued, like the real endpoint
        self.status_value = {"state": "queued", "progress": 0,
                             "stage_label": "Waiting in line", "error": None}

    def status(self, job_id):
        return dict(self.status_value)

    def output_paths(self, job_id):
        return ["deliverables/L1/coach/report.pdf",
                "deliverables/L1/coach/metrics.json",
                "det_cache/ball/L1.txt",
                "events/L1/clips/01_goal.mp4"]

    def download_output(self, job_id, rel, dest):
        with open(dest, "wb") as f:
            f.write(b"pdf-bytes")


class FakeNotify:
    """Captures emails; nothing leaves the test process."""
    def __init__(self):
        self.sent = []

    def send_email(self, to, subject, html):
        self.sent.append((to, subject))

    def build_ready_email(self, match, url, expires):
        return (f"ready: {match}", url)

    def build_failed_email(self, match, message):
        return (f"failed: {match}", message)

    def build_promoted_email(self, match, url):
        return (f"your turn: {match}", url)


CLOUD_JOB = {"id": "cloud-1", "user_id": "u1", "sport": "football",
             "match_name": "Test", "match_date": None,
             "declared_duration_min": 5,
             "deliverables": ["coach_analytics", "event_highlights"],
             "state": "uploaded", "drive_file_id": "raw-1",
             "drive_folder_id": "folder-1", "local_job_id": None,
             "created_at": "2026-06-06T00:00:00+00:00", "expires_at": None}


def test_ingest_orders_drive_delete_after_local_upload(tmp_path, monkeypatch):
    cloud, drv, backend = FakeCloud([CLOUD_JOB]), FakeDrive(), FakeBackend()
    monkeypatch.setattr(relay, "probe_duration_sec", lambda p: 300.0)  # 5 min
    relay.ingest_one(dict(CLOUD_JOB), cloud=cloud, drv=drv, backend=backend,
                     notify=FakeNotify(), workdir=str(tmp_path))

    # video reached the local backend BEFORE the drive raw was deleted
    assert backend.log.index("upload_video") >= 0
    assert ("delete", "raw-1") in drv.log
    assert drv.log.index(("delete", "raw-1")) > 0  # not first action
    combined = [e for e in drv.log if e[0] == "delete"]
    assert combined == [("delete", "raw-1")]

    job = cloud.get_job("cloud-1")
    assert job["state"] == "processing"
    assert job["local_job_id"] == "local-1"
    # ingest must NOT enqueue — that would skip the calibration gate
    assert "set_deliverables" not in backend.log
    assert backend.deliverables is None


def test_ingest_downgrades_overlong_footage(tmp_path, monkeypatch):
    cloud, drv, backend = FakeCloud([CLOUD_JOB]), FakeDrive(), FakeBackend()
    monkeypatch.setattr(relay, "probe_duration_sec", lambda p: 30 * 60.0)  # 30 min!
    relay.ingest_one(dict(CLOUD_JOB), cloud=cloud, drv=drv, backend=backend,
                     notify=FakeNotify(), workdir=str(tmp_path))
    # the downgrade lands on the CLOUD row (read back at enqueue time)
    assert cloud.get_job("cloud-1")["deliverables"] == ["coach_analytics"]
    assert "20 minutes" in cloud.get_job("cloud-1")["state_detail"]


def test_mirror_enqueues_once_calibrated(tmp_path):
    job = {**CLOUD_JOB, "state": "operator_action", "local_job_id": "local-1"}
    cloud, backend = FakeCloud([job]), FakeBackend()
    backend.status_value = {"state": "calibrated", "progress": 0,
                            "stage_label": None, "error": None}
    state = relay.mirror_one(dict(job), cloud=cloud, backend=backend)
    assert backend.deliverables == ["coach_analytics", "event_highlights"]
    assert state == "queued"  # enqueued and re-read
    assert cloud.get_job("cloud-1")["state"] == "processing"


def test_ingest_fails_unreadable_video_and_frees_drive(tmp_path, monkeypatch):
    cloud, drv, backend = FakeCloud([CLOUD_JOB]), FakeDrive(), FakeBackend()
    monkeypatch.setattr(relay, "probe_duration_sec", lambda p: None)
    notify = FakeNotify()
    relay.ingest_one(dict(CLOUD_JOB), cloud=cloud, drv=drv, backend=backend,
                     notify=notify, workdir=str(tmp_path))
    job = cloud.get_job("cloud-1")
    assert job["state"] == "failed"
    assert notify.sent == [("user@example.com", "failed: Test")]
    assert ("delete", "raw-1") in drv.log
    assert "create_job" not in backend.log  # never reached the pipeline


def test_mirror_writes_progress(tmp_path):
    job = {**CLOUD_JOB, "state": "processing", "local_job_id": "local-1"}
    cloud, backend = FakeCloud([job]), FakeBackend()
    relay.mirror_one(dict(job), cloud=cloud, backend=backend)
    j = cloud.get_job("cloud-1")
    assert j["state"] == "processing"
    assert j["state_detail"] == "Waiting in line"


def test_deliver_uploads_organized_then_flips_ready(tmp_path):
    job = {**CLOUD_JOB, "state": "processing", "local_job_id": "local-1"}
    cloud, drv, backend = FakeCloud([job]), FakeDrive(), FakeBackend()
    notify = FakeNotify()
    relay.deliver(dict(job), cloud=cloud, drv=drv, backend=backend,
                  notify=notify, workdir=str(tmp_path))
    # user-facing files land in NAMED per-deliverable folders...
    assert ("folder-Coach analytics", "report.pdf") in drv.uploaded
    assert ("folder-Event highlights", "01_goal.mp4") in drv.uploaded
    # ...and internal artifacts never ship
    names = [n for _, n in drv.uploaded]
    assert "metrics.json" not in names
    assert "L1.txt" not in names
    assert notify.sent == [("user@example.com", "ready: Test")]
    j = cloud.get_job("cloud-1")
    assert j["state"] == "ready"
    assert j["results_url"] == "https://drive.google.com/shared"
    assert j["expires_at"] is not None
    # ready was written AFTER the uploads happened
    upload_pos = max(i for i, e in enumerate(drv.log) if e[0] == "upload")
    ready_pos = [i for i, e in enumerate(cloud.log)
                 if e[2].get("state") == "ready"]
    assert ready_pos and upload_pos >= 0


def test_deliver_skips_files_already_in_drive(tmp_path):
    job = {**CLOUD_JOB, "state": "processing", "local_job_id": "local-1"}
    cloud, drv, backend = FakeCloud([job]), FakeDrive(), FakeBackend()
    drv.existing = {"report.pdf", "01_goal.mp4"}
    relay.deliver(dict(job), cloud=cloud, drv=drv, backend=backend,
                  notify=FakeNotify(), workdir=str(tmp_path))
    assert drv.uploaded == []  # idempotent re-run
    assert cloud.get_job("cloud-1")["state"] == "ready"


def test_cleanup_expires_old_jobs():
    job = {**CLOUD_JOB, "state": "ready", "results_url": "x",
           "expires_at": "2020-01-01T00:00:00+00:00"}
    cloud, drv = FakeCloud([job]), FakeDrive()
    relay.cleanup_expired(cloud=cloud, drv=drv)
    j = cloud.get_job("cloud-1")
    assert j["state"] == "expired"
    assert ("delete", "folder-1") in drv.log


def test_promote_oldest_quota_waiting():
    job = {**CLOUD_JOB, "state": "quota_waiting"}
    cloud, drv = FakeCloud([job]), FakeDrive()
    notify = FakeNotify()
    relay.promote_quota_waiting(cloud=cloud, drv=drv, notify=notify)
    assert cloud.get_job("cloud-1")["state"] == "approved"
    assert notify.sent and "your turn" in notify.sent[0][1]
