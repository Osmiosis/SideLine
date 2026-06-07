"""Operator notifier: polls Supabase, raises Windows toasts.

    .venv\\Scripts\\pythonw -m agent.notifier     # silent, for Startup
    .venv\\Scripts\\python  -m agent.notifier     # with console, for testing

- job submitted -> "awaiting approval" toast; button opens the admin page
- job uploaded  -> "footage received" toast; button starts the backend +
  agent in two PowerShell windows and opens the local studio UI
"""
import os
import subprocess
import sys
import time
import webbrowser

from windows_toasts import (InteractableWindowsToaster, Toast,
                            ToastActivatedEventArgs, ToastButton)

from agent import cloud
from agent.config import settings
from agent.notifier_logic import detect_news

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
