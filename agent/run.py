"""Start the agent.

    .venv\\Scripts\\python -m agent.run           # forever loop
    .venv\\Scripts\\python -m agent.run --once    # single pass (testing)

Prerequisite: the local backend is running (`python -m backend.main`).
"""
import sys

from agent.relay import run_loop, run_once

if __name__ == "__main__":
    if "--once" in sys.argv:
        run_once()
    else:
        run_loop()
