# Online Hosting Plan 3.1: Rehearsal Fixes + Operator Notifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the two defects the Plan 3 rehearsal exposed (unorganized Drive delivery; local UI dropping calibration-pending jobs onto the progress screen) and add the operator notifier (Windows toasts for "approval requested" and "footage received", with a click-to-start-studio button).

**Architecture:** Delivery becomes a pure planning function (`plan_delivery`) mapping the backend's raw `/outputs` listing to per-deliverable Drive folders ("Coach analytics" / "Event highlights" / "Player highlights"), filtered to user-facing files only. The UI fix is a two-line state-routing change in `Website/index.html`. The notifier is a new standalone script (`agent/notifier.py`) polling Supabase and raising interactable Windows toasts via the `windows-toasts` package; its "what's new" decision logic is pure and tested.

**Tech Stack:** existing agent stack + `windows-toasts` (pip), Windows toast actions, PowerShell startup shortcut.

**Conventions:** user handles all git (report files per task, no commit steps). Real outputs observed in the rehearsal (job `361e2321…`): `deliverables/<id>/coach/*.{pdf,png,mp4,json}`, `deliverables/<id>/*.{png,json}`, `events/<id>/clips/*.mp4`, `event_highlights/*.{mp4,json,md,jpg}`, `player_highlights/<id>/{clips,reels}/*.mp4`, plus internal `ball_track/`, `det_cache/`, `tracks/` — only a subset is user-facing.

---

### Task 1: Organized, filtered delivery

**Files:**
- Modify: `agent/logic.py` (replace `drive_name`/`files_to_upload` with `plan_delivery`)
- Modify: `agent/relay.py` (`deliver()` uses the plan + per-deliverable Drive subfolders)
- Modify: `agent/tests/test_logic.py`, `agent/tests/test_relay.py`

- [ ] **Step 1: Replace the delivery tests in `agent/tests/test_logic.py`**

Delete `test_files_to_upload_skips_already_delivered` and add:

```python
REAL_OUTPUTS = [
    "ball_track/L1/possession.json",
    "deliverables/L1/coach/coach_analysis.pdf",
    "deliverables/L1/coach/fig_heatmap_A.png",
    "deliverables/L1/coach/tactical_sample.mp4",
    "deliverables/L1/coach/metrics.json",
    "deliverables/L1/distances.json",
    "det_cache/ball/L1.txt",
    "events/L1/clips/07_likely_goal_candidate_55s.mp4",
    "event_highlights/auto_draft_reel.mp4",
    "event_highlights/index.json",
    "player_highlights/L1/clips/c001.mp4",
    "player_highlights/L1/reels/player_07.mp4",
]


def test_plan_delivery_routes_files_to_named_folders():
    plan = plan_delivery(
        ["coach_analytics", "event_highlights", "player_highlights"], REAL_OUTPUTS)
    assert ("deliverables/L1/coach/coach_analysis.pdf",
            "Coach analytics", "coach_analysis.pdf") in plan
    assert ("events/L1/clips/07_likely_goal_candidate_55s.mp4",
            "Event highlights", "07_likely_goal_candidate_55s.mp4") in plan
    assert ("event_highlights/auto_draft_reel.mp4",
            "Event highlights", "auto_draft_reel.mp4") in plan
    assert ("player_highlights/L1/reels/player_07.mp4",
            "Player highlights", "player_07.mp4") in plan


def test_plan_delivery_excludes_internal_files():
    plan = plan_delivery(
        ["coach_analytics", "event_highlights", "player_highlights"], REAL_OUTPUTS)
    shipped = [rel for rel, _, _ in plan]
    for internal in ("ball_track/L1/possession.json", "det_cache/ball/L1.txt",
                     "deliverables/L1/coach/metrics.json",
                     "deliverables/L1/distances.json",
                     "event_highlights/index.json",
                     "player_highlights/L1/clips/c001.mp4"):
        assert internal not in shipped


def test_plan_delivery_respects_requested_deliverables():
    plan = plan_delivery(["coach_analytics"], REAL_OUTPUTS)
    assert {sub for _, sub, _ in plan} == {"Coach analytics"}
```

- [ ] **Step 2: Run to verify failure** — `pytest agent/tests/test_logic.py -v` → FAIL (`plan_delivery` not defined; old test removed).

- [ ] **Step 3: In `agent/logic.py`**, delete `drive_name` and `files_to_upload`, add:

```python
def plan_delivery(requested, output_paths):
    """Map the backend's raw outputs listing to user-facing Drive uploads.

    Returns [(rel_path, drive_folder_label, file_name)] containing ONLY files
    the user should see, organised per requested deliverable.
    """
    plan = []
    for rel in output_paths:
        p = rel.replace("\\", "/")
        parts = p.split("/")
        name = parts[-1]
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ("coach_analytics" in requested and len(parts) >= 4
                and parts[0] == "deliverables" and parts[2] == "coach"
                and ext != "json"):
            plan.append((rel, "Coach analytics", name))
        elif ("event_highlights" in requested and ext == "mp4"
              and (parts[0] == "event_highlights"
                   or (parts[0] == "events" and "clips" in parts))):
            plan.append((rel, "Event highlights", name))
        elif ("player_highlights" in requested and ext == "mp4"
              and parts[0] == "player_highlights" and "reels" in parts):
            plan.append((rel, "Player highlights", name))
    return plan
```

- [ ] **Step 4: Rewrite `deliver()` in `agent/relay.py`** (replace the folder/upload block; import `plan_delivery` instead of `files_to_upload`):

```python
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
```

- [ ] **Step 5: Update `agent/tests/test_relay.py`** — `FakeBackend.output_paths` returns a realistic mix; `FakeDrive.upload_file` logs `("upload", folder_id, name)`; deliver tests assert organized placement:

```python
    def output_paths(self, job_id):
        return ["deliverables/L1/coach/report.pdf",
                "deliverables/L1/coach/metrics.json",
                "det_cache/ball/L1.txt",
                "events/L1/clips/01_goal.mp4"]
```

In `test_deliver_uploads_then_flips_ready`: job deliverables are `["coach_analytics", "event_highlights"]` (already), so expect uploads `report.pdf` into `folder-Coach analytics` and `01_goal.mp4` into `folder-Event highlights`, and NEITHER `metrics.json` NOR the det_cache file anywhere. In `test_deliver_skips_files_already_in_drive`: `drv.existing = {"report.pdf", "01_goal.mp4"}` → zero uploads, state still flips `ready`.

- [ ] **Step 6: Run** `pytest agent/tests/test_logic.py agent/tests/test_relay.py -v` → all pass.

---

### Task 2: Local UI — route calibration-pending jobs to court setup

**Files:**
- Modify: `Website/index.html:1021` (state mapping), `:1023-1025` (badge), `:1040-1042` (click routing)

- [ ] **Step 1: Apply the three edits**

Line 1021 mapping gains a `court` status:

```javascript
status:(j.state==='ready'?'ready':j.state==='failed'?'draft':j.state==='calibration_pending'?'court':'proc'), seed:(j.match_name.length*7)%30}));
```

Badge ternary gains a court case (before the draft fallback):

```javascript
    const badge = m.status==='ready'?'<span class="badge ready"><span class="led"></span>Ready</span>'
      : m.status==='proc'?'<span class="badge proc"><span class="led"></span>Processing</span>'
      : m.status==='court'?'<span class="badge proc"><span class="led"></span>Court setup</span>'
      : '<span class="badge draft"><span class="led"></span>Draft</span>';
```

Click handler routes court → the calibration view (`go('court')` calls `initCourt()` which loads the freeze-frame):

```javascript
      go(m.status==='ready'?'results':m.status==='court'?'court':'processing');
```

(both the demo line 1040 and the real line 1042 — keep the demo line unchanged, demo cards never have `court`.)

- [ ] **Step 2: Manual check** — with the backend running and a local job in `calibration_pending` (next rehearsal provides one), the dashboard card shows "Court setup" and clicking it lands on the corner-marking screen.

---

### Task 3: Operator notifier (Windows toasts)

**Files:**
- Create: `agent/notifier_logic.py` + `agent/tests/test_notifier_logic.py`
- Create: `agent/notifier.py`
- Modify: `agent/requirements-agent.txt` (+ `windows-toasts>=1.1`)
- Modify: `supabase/SETUP.md` (startup instructions)

- [ ] **Step 1: Write the failing tests** (`agent/tests/test_notifier_logic.py`):

```python
from agent.notifier_logic import detect_news


def test_first_pass_reports_existing_jobs_once():
    jobs = [{"id": "a", "state": "submitted", "match_name": "M1"},
            {"id": "b", "state": "uploaded", "match_name": "M2"}]
    news, seen = detect_news(set(), jobs)
    assert [(n["kind"], n["job"]["id"]) for n in news] == [
        ("approval", "a"), ("footage", "b")]
    news2, _ = detect_news(seen, jobs)
    assert news2 == []  # no repeats


def test_state_change_renotifies_same_job():
    jobs = [{"id": "a", "state": "submitted", "match_name": "M1"}]
    _, seen = detect_news(set(), jobs)
    jobs[0]["state"] = "uploaded"
    news, _ = detect_news(seen, jobs)
    assert [(n["kind"], n["job"]["id"]) for n in news] == [("footage", "a")]


def test_other_states_are_ignored():
    jobs = [{"id": "a", "state": "processing", "match_name": "M1"}]
    news, _ = detect_news(set(), jobs)
    assert news == []
```

- [ ] **Step 2: Write `agent/notifier_logic.py`**:

```python
"""Pure 'what should I toast about?' logic for the operator notifier."""

_KINDS = {"submitted": "approval", "uploaded": "footage"}


def detect_news(seen: set, jobs: list[dict]):
    """Return (news, new_seen). A job re-notifies when its STATE changes,
    so keys are (id, state) pairs."""
    news = []
    new_seen = set(seen)
    for job in jobs:
        kind = _KINDS.get(job["state"])
        if not kind:
            continue
        key = (job["id"], job["state"])
        if key in new_seen:
            continue
        new_seen.add(key)
        news.append({"kind": kind, "job": job})
    return news, new_seen
```

- [ ] **Step 3: Tests pass** — `pytest agent/tests/test_notifier_logic.py -v` → 3 passed.

- [ ] **Step 4: Install the toast dependency** — append `windows-toasts>=1.1` to `agent/requirements-agent.txt`, run `.\.venv\Scripts\pip install windows-toasts`.

- [ ] **Step 5: Write `agent/notifier.py`** (toast shell around the pure logic):

```python
"""Operator notifier: polls Supabase, raises Windows toasts.

    .venv\\Scripts\\pythonw -m agent.notifier     # silent, for Startup
    .venv\\Scripts\\python  -m agent.notifier     # with console, for testing

- job submitted -> "awaiting approval" toast; button opens the admin page
- job uploaded  -> "footage received" toast; button starts the backend +
  agent in two PowerShell windows and opens the local studio UI
"""
import subprocess
import sys
import time
import webbrowser

from windows_toasts import (InteractableWindowsToaster, Toast,
                            ToastActivatedEventArgs, ToastButton)

from agent import cloud
from agent.config import settings
from agent.notifier_logic import detect_news

REPO = __file__.rsplit("\\", 2)[0] if "\\" in __file__ else "."
PY = sys.executable.replace("pythonw.exe", "python.exe")


def start_studio() -> None:
    flags = subprocess.CREATE_NEW_CONSOLE
    subprocess.Popen([PY, "-m", "backend.main"], cwd=REPO, creationflags=flags)
    time.sleep(3)  # backend first, then the agent
    subprocess.Popen([PY, "-m", "agent.run"], cwd=REPO, creationflags=flags)
    time.sleep(2)
    webbrowser.open(settings.backend_url)


def _on_click(args: ToastActivatedEventArgs) -> None:
    if args.arguments == "start_studio":
        start_studio()
    elif args.arguments == "open_admin":
        webbrowser.open(f"{settings.site_origin}/admin.html")


def show(toaster, title: str, body: str, button: str, action: str) -> None:
    toast = Toast([title, body])
    toast.AddAction(ToastButton(button, action))
    toast.on_activated = _on_click
    toaster.show_toast(toast)


def main() -> None:
    toaster = InteractableWindowsToaster("Sideline Studio")
    seen: set = set()
    first = True
    print(f"notifier: polling every {settings.poll_seconds}s")
    while True:
        try:
            jobs = (cloud.jobs_in_state("submitted")
                    + cloud.jobs_in_state("uploaded"))
            news, seen = detect_news(seen, jobs)
            if first:           # don't toast a backlog on startup, just learn it
                news, first = [], False
            for n in news:
                job = n["job"]
                if n["kind"] == "approval":
                    show(toaster, "New match awaiting approval",
                         f"{job['match_name']} — open the admin page to "
                         "approve or reject.", "Open admin page", "open_admin")
                else:
                    show(toaster, "Footage received",
                         f"{job['match_name']} is parked in Drive — start the "
                         "studio to process it.", "Start studio", "start_studio")
        except Exception as e:  # noqa: BLE001 — keep watching (spec §8)
            print(f"notifier: pass failed ({e}); retrying")
        time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Live smoke test** — run `.\.venv\Scripts\python -m agent.notifier` in a console; submit a test job from the alt account → within 60 s a toast appears; click "Open admin page" → browser opens the admin view. (The "first pass learns silently" behavior means pre-existing pending jobs don't spam at startup.)

- [ ] **Step 7: Startup shortcut** — record in `supabase/SETUP.md`:

```markdown
### Operator notifier (Plan 3.1)

Always-on watcher: `.venv\Scripts\pythonw.exe -m agent.notifier` (no console).
Auto-start at login: Win+R → `shell:startup` → create shortcut with target
  C:\sports-ai\.venv\Scripts\pythonw.exe -m agent.notifier
and "Start in" = C:\sports-ai.
Toasts: "awaiting approval" (button → admin page) and "footage received"
(button → starts backend + agent consoles and opens http://localhost:8000).
```

- [ ] **Step 8: Full agent suite** — `pytest agent/tests -v` → 34 passed (29 − 1 removed + 3 delivery-plan + 3 notifier).

---

## Exit criteria

- [ ] Delivered Drive folder contains ONLY named subfolders ("Coach analytics" / "Event highlights" / "Player highlights") with user-facing files — no json/txt/internal artifacts (verified on the next real delivery).
- [ ] Local dashboard shows "Court setup" on calibration-pending jobs and clicking lands on the corner-marking screen.
- [ ] Toast appears within 60 s of a submission; "Start studio" button brings up both consoles + the local UI.
- [ ] `pytest agent/tests -v` green; site + cloud suites unaffected.
