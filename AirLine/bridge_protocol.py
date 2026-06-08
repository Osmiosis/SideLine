"""bridge_protocol — the wire format between capture and render processes.

PURE STDLIB. Imported by BOTH the gestures venv (capture) and the main venv
(render), so it must not import mediapipe or ultralytics — not even transitively.
Intent is carried as a plain string (the IntentCommand value); validation against
the known set is done here without importing the enum, and a unit test asserts the
local set stays in sync with IntentCommand so they can't drift.

Transport is newline-delimited JSON over a localhost TCP socket — one JSON object
per line. A malformed line decodes to None and must never crash the render process.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

# Kept in sync with intent_types.IntentCommand by test_bridge_protocol.
KNOWN_INTENTS = frozenset({
    "select", "switch_next", "switch_prev", "release", "shot_tight", "shot_wide",
})


@dataclass
class IntentMessage:
    intent: str                       # IntentCommand value, e.g. "select"
    ts: float                         # send-side wall-clock time.time()
    seq: int = 0                      # sequence number (ordering / loss detection)
    payload: dict = field(default_factory=dict)  # e.g. {"ref_x": 0.4, "confirm_ms": 210}


def encode(msg: IntentMessage) -> bytes:
    """Serialize one message as a single newline-terminated JSON line."""
    return (json.dumps({
        "intent": msg.intent, "ts": msg.ts, "seq": msg.seq, "payload": msg.payload,
    }) + "\n").encode("utf-8")


def decode(line) -> Optional[IntentMessage]:
    """Parse one line (bytes or str) into an IntentMessage, or None if malformed.

    Never raises — a bad transport must not be able to take down the render side.
    """
    try:
        if isinstance(line, (bytes, bytearray)):
            line = line.decode("utf-8")
        d = json.loads(line)
        if not isinstance(d, dict):
            return None
        intent = d["intent"]
        if not isinstance(intent, str):
            return None
        ts = float(d["ts"])
        seq = int(d.get("seq", 0))
        payload = d.get("payload", {})
        if not isinstance(payload, dict):
            return None
        return IntentMessage(intent=intent, ts=ts, seq=seq, payload=payload)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def is_known(msg: Optional[IntentMessage]) -> bool:
    """True if msg decoded and carries a recognised intent."""
    return msg is not None and msg.intent in KNOWN_INTENTS
