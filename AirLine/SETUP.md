# AirLine — Environment Setup

AirLine deliberately uses **two Python environments** because the gesture stack and
the CV/render stack have **mutually incompatible dependencies** (proven Day 5):

| | main `.venv` | gestures venv |
|---|---|---|
| location | `.venv/` (in repo, gitignored) | `C:\airline-gestures-venv` (outside repo) |
| python | 3.11 | 3.11 |
| key deps | **numpy 2.4.4**, ultralytics, torch 2.11+cu128, opencv | **mediapipe 0.10.21**, **numpy 1.26.4**, **protobuf 4.25.9**, opencv |
| runs | tracker, target, camera, intent, **render** process, all tests | MediaPipe hand landmarks, **capture** process |
| must NOT contain | mediapipe | ultralytics / torch |

`mediapipe 0.10.x` requires `numpy<2` and `protobuf<5`; the CV stack is built on
numpy 2. Installing both in one env force-downgrades numpy/protobuf and breaks the
tracker — so they are quarantined. The two processes talk over a localhost socket
(see `AirLine/bridge_protocol.py`).

## Rebuild the main `.venv`
```bat
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r backend\requirements-backend.txt
:: (plus the CV deps already present: ultralytics, torch, opencv-python)
```
Verify: `.venv\Scripts\python -c "import numpy,ultralytics;print(numpy.__version__)"` → `2.4.4`, no mediapipe.
Run tests: `.venv\Scripts\python -m pytest -q --ignore=tests/backend/test_video_io.py`

## Rebuild the gestures venv
```bat
py -3.11 -m venv C:\airline-gestures-venv
C:\airline-gestures-venv\Scripts\python -m pip install --upgrade pip
C:\airline-gestures-venv\Scripts\python -m pip install -r AirLine\requirements-gestures.txt
```
Verify: `C:\airline-gestures-venv\Scripts\python -c "import mediapipe,numpy;print(mediapipe.__version__,numpy.__version__)"` → `0.10.21 1.26.4`.

## Run the live gesture-directed demo (Day 6 two-process bridge)
Two terminals, from the repo root, with `set PYTHONPATH=.` in each:
```bat
:: terminal 1 — render (main venv): warms model, waits for capture, writes day6_live.mp4
.venv\Scripts\python -m AirLine.bridge_render clips\football.mp4 --port 8765

:: terminal 2 — capture (gestures venv): your hand drives it
C:\airline-gestures-venv\Scripts\python -m AirLine.bridge_capture --host 127.0.0.1 --port 8765
```
Hands-free smoke test (mock capture, runs in the main venv):
```bat
.venv\Scripts\python -m AirLine.bridge_capture --mock --port 8765
```

## Recognition / latency tooling
- `AirLine.gesture_eval` (gestures venv) — webcam gesture recognition-rate test.
- `AirLine.run_day4 --source scripted` (main venv) — scripted cinematography demo.
