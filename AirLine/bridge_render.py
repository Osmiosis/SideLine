"""bridge_render — the render process (Day 6).

Runs in the main `.venv` (ultralytics, NO mediapipe). Acts as the socket SERVER:
waits for the capture process to connect, then plays the football clip through the
unchanged `core_bridge` + `IntentApplier`, applying each received intent live and
measuring latency. Writes `AirLine/outputs/day6_live.mp4`.

    python -m AirLine.bridge_render --port 8765
    # then start capture (real, gestures venv) or `bridge_capture --mock`

Latency clocks: both processes share one machine and one wall clock (time.time()),
so transport+apply = render-receive-time − send-timestamp is valid with no
cross-process clock offset. gesture→confirmed comes from the capture side
(payload "confirm_ms"); total ≈ confirm_ms + transport+apply (+ one render-frame).
"""

from __future__ import annotations

import argparse
import socket
import time
from pathlib import Path

import cv2

from AirLine.bridge_protocol import decode, is_known
from AirLine.intent_types import IntentCommand
from AirLine.core_bridge import run_tracker, load_model
from AirLine.target import TargetTracker, TargetState
from AirLine.camera import VirtualCamera, CameraConfig
from AirLine.intent import IntentApplier

OUTPUT_DIR = Path("AirLine/outputs")
OUTPUT_PATH = OUTPUT_DIR / "day6_live.mp4"


def _accept(port, wait_s):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(1)
    srv.settimeout(wait_s)
    print(f"[render] listening on 127.0.0.1:{port} (waiting {wait_s}s for capture)...")
    conn, addr = srv.accept()
    conn.setblocking(False)
    print(f"[render] capture connected from {addr}")
    return srv, conn


def _drain(conn, buf):
    """Read whatever is available; return (list_of_complete_lines, new_buf)."""
    try:
        chunk = conn.recv(65536)
        if chunk:
            buf += chunk
    except BlockingIOError:
        pass
    except (ConnectionResetError, OSError):
        return None, buf  # peer gone
    lines = []
    while b"\n" in buf:
        line, buf = buf.split(b"\n", 1)
        if line.strip():
            lines.append(line)
    return lines, buf


def _overlay(out, msg_label, recv_lat_ms, tracker, applier, state):
    shot = applier.shot.value if applier.shot else "-"
    cv2.rectangle(out, (0, 0), (620, 64), (0, 0, 0), -1)
    cv2.putText(out, f"intent: {msg_label}   +{recv_lat_ms:.0f}ms", (8, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 215, 255), 2, cv2.LINE_AA)
    cv2.putText(out, f"target: {tracker.target_id}   shot: {shot}   state: {state.value}",
                (8, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (0, 255, 0) if state == TargetState.LOCKED else (0, 0, 255), 1, cv2.LINE_AA)


def main():
    ap = argparse.ArgumentParser(description="AirLine Day 6 render process")
    ap.add_argument("clip", nargs="?", default="clips/football.mp4")
    ap.add_argument("--sport", default="football", choices=["football", "basketball"])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--device", default=0)
    ap.add_argument("--wait", type=float, default=30.0, help="seconds to wait for capture")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    cfg = CameraConfig()
    tracker = TargetTracker()
    camera = VirtualCamera(cfg)
    applier = IntentApplier(tracker, camera)

    # Warm-load the model BEFORE accepting, so model-load time never contaminates
    # the transport+apply latency measurement (only socket + render cadence count).
    print("[render] warming up tracker model...")
    model = load_model(args.sport)

    srv, conn = _accept(args.port, args.wait)
    src_fps = cv2.VideoCapture(args.clip).get(cv2.CAP_PROP_FPS) or 30.0
    writer = cv2.VideoWriter(str(OUTPUT_PATH), cv2.VideoWriter_fourcc(*"mp4v"),
                             src_fps, (cfg.out_w, cfg.out_h))

    buf = b""
    last_label, flash = "-", 0
    transport_lat, confirm_lat = [], []
    applied = 0
    peer_gone = False

    for ft in run_tracker(args.clip, sport=args.sport, device=args.device,
                          model=model, limit=args.limit):
        if not peer_gone:
            lines, buf = _drain(conn, buf)
            if lines is None:
                peer_gone = True
            else:
                for line in lines:
                    msg = decode(line)
                    if not is_known(msg):
                        continue  # malformed/unknown ignored — never crashes render
                    recv_lat = (time.time() - msg.ts) * 1000.0
                    transport_lat.append(recv_lat)
                    if "confirm_ms" in msg.payload:
                        confirm_lat.append(float(msg.payload["confirm_ms"]))
                    ref_x = None
                    if "ref_x" in msg.payload:  # normalized [0,1] -> pixels
                        ref_x = float(msg.payload["ref_x"]) * ft.frame.shape[1]
                    applier.apply(IntentCommand(msg.intent), ft, ref_x=ref_x,
                                  frame_w=ft.frame.shape[1])
                    last_label, flash = msg.intent, 18
                    applied += 1
                    print(f"[render] applied {msg.intent}  transport+apply={recv_lat:.0f}ms")

        status = tracker.update(ft)
        crop = camera.update(status.box or tracker.last_box
                             if status.state == TargetState.LOCKED else None,
                             status.state, (ft.frame.shape[1], ft.frame.shape[0]))
        sub = ft.frame[crop.y:crop.y + crop.h, crop.x:crop.x + crop.w]
        out = cv2.resize(sub, (cfg.out_w, cfg.out_h), interpolation=cv2.INTER_LINEAR)
        _overlay(out, last_label if flash > 0 else "-", transport_lat[-1] if transport_lat else 0.0,
                 tracker, applier, status.state)
        flash = max(0, flash - 1)
        writer.write(out)

    writer.release()
    conn.close()
    srv.close()

    def stats(xs):
        return (sum(xs) / len(xs), max(xs)) if xs else (0.0, 0.0)
    t_mean, t_max = stats(transport_lat)
    c_mean, c_max = stats(confirm_lat)

    print("\n=== AirLine Day 6 — latency breakdown ===")
    print(f"intents applied        : {applied}")
    print(f"gesture->confirmed      : mean {c_mean:.0f} ms  worst {c_max:.0f} ms  (capture side)")
    print(f"transport+apply         : mean {t_mean:.0f} ms  worst {t_max:.0f} ms  (send->applied)")
    print(f"~total hand->screen     : mean {c_mean + t_mean:.0f} ms  worst {c_max + t_max:.0f} ms")
    print(f"clock                   : shared system wall clock (same machine), no offset")
    print(f"output                  : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
