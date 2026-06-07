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
