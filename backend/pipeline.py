"""Real subprocess pipeline engine + per-sport step lists.

Plan 3 replaces the Plan-1 stub runner with a proper Step-based engine.
`stage_label()` is kept (used by worker + API). `resolve_stages` and
`run_stage_stub` are DELETED — replaced by `resolve_steps` + `run_step`.
"""
from __future__ import annotations

import configparser
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from backend import config, adapters
from backend.schemas import JobConfig

_STAGE_LABELS: dict[str, str] = {
    "decoding": "Reading the video",
    "detecting": "Finding players",
    "tracking": "Following players",
    "teams": "Sorting teams",
    "ball": "Tracking the ball",
    "analytics": "Building analytics",
    "events": "Finding key moments",
    "tagging_pending": "Waiting for player names",
    "tagging_done": "Names received",
    "player_highlights": "Building player reels",
    "ready": "Ready",
    "queued": "Waiting in line",
}


def stage_label(stage: str) -> str:
    return _STAGE_LABELS.get(stage, stage.replace("_", " ").capitalize())


# ---------------------------------------------------------------------------
# Step engine
# ---------------------------------------------------------------------------

@dataclass
class StepCtx:
    job_dir: Path
    job_id: str
    sport: str


@dataclass
class Step:
    key: str
    ui_stage: str
    deliverable: str | None | set[str]  # None = foundation (always runs); set = runs if ANY requested
    build: Callable[[StepCtx], object]  # returns argv list (subprocess) OR callable() OR None


def _py(*args) -> list[str]:
    return [config.PYTHON_EXE, *[str(a) for a in args]]


def _sd(name: str) -> str:
    return str(config.SCRIPTS_DIR / name)


def _football_steps() -> list[Step]:
    def decode(ctx):
        return lambda: adapters.decode_video(
            ctx.job_dir / "raw_video.mp4", ctx.job_dir / "frames", seq=ctx.job_id)

    def homography(ctx):
        cfg = JobConfig.model_validate_json(
            (ctx.job_dir / "job_config.json").read_text(encoding="utf-8"))
        return lambda: adapters.write_homography(
            [p.model_dump() for p in cfg.calibration_points], ctx.sport,
            ctx.job_dir / "homography.json")

    J = lambda ctx, *p: str(ctx.job_dir.joinpath(*p))
    return [
        Step("decode", "decoding", None, decode),
        Step("homography", "decoding", None, homography),
        Step("players", "tracking", None, lambda c: _py(
            _sd("track_alfheim.py"), "--video", J(c, "raw_video.mp4"),
            "--out", J(c, "outputs", "tracks", f"{c.job_id}.txt"),
            "--model", str(config.MODELS_DIR / "soccana.pt"), "--classes", "0")),
        Step("ball-cache", "ball", None, lambda c: _py(
            _sd("build_det_cache.py"), "--detector", str(config.MODELS_DIR / "soccana.pt"),
            "--source", J(c, "frames"), "--out", J(c, "outputs", "det_cache", "ball"),
            "--class-name", "ball", "--only", c.job_id)),
        Step("ball-kalman", "ball", None, lambda c: _py(
            _sd("analyze_ball.py"), c.job_id,
            "--cache-dir", J(c, "outputs", "det_cache", "ball"),
            "--source", J(c, "frames"), "--out", J(c, "outputs", "ball_track"),
            "--homography", J(c, "homography.json"))),
        Step("pitch-proj", "tracking", None, lambda c: _py(
            _sd("analyze_pitch.py"), c.job_id,
            "--tracker", J(c, "outputs", "tracks"),
            "--out", J(c, "outputs", "deliverables"),
            "--homography", J(c, "homography.json"))),
        Step("team-assign", "teams", None, lambda c: _py(
            _sd("team_assign.py"), "--seqs", c.job_id,
            "--tracker-dir", J(c, "outputs", "tracks"),
            "--data-root", J(c, "frames"),
            "--out", J(c, "outputs", "team_assign"),
            "--sample-seq", c.job_id, "--zip", "")),
        # coach_analytics tail
        Step("possession", "analytics", "coach_analytics", lambda c: _py(
            _sd("compute_possession.py"), c.job_id, "--source", J(c, "frames"),
            "--tracker-dir", J(c, "outputs", "tracks"),
            "--ball-track-dir", J(c, "outputs", "ball_track"),
            "--team-assign-dir", J(c, "outputs", "team_assign"),
            "--homography", J(c, "homography.json"))),
        Step("coach", "analytics", "coach_analytics", lambda c: _py(
            _sd("coach_deliverable.py"), c.job_id,
            "--deliverables", J(c, "outputs", "deliverables"),
            "--ball-dir", J(c, "outputs", "ball_track"),
            "--team-assign", J(c, "outputs", "team_assign", "track_teams.json"),
            "--track-dir", J(c, "outputs", "tracks"),
            "--frames", J(c, "frames"))),   # renders tactical_sample.mp4 for the coach tab
        # event_highlights tail
        Step("detect-events", "events", "event_highlights", lambda c: _py(
            _sd("detect_events.py"), c.job_id,
            "--ball-dir", J(c, "outputs", "ball_track"),
            "--track-dir", J(c, "outputs", "tracks"),
            "--team-json", J(c, "outputs", "team_assign", "track_teams.json"),
            "--zip", "", "--out", J(c, "outputs", "events"))),
        Step("follow-cam", "events", {"event_highlights", "player_highlights"}, lambda c: _py(
            _sd("follow_cam.py"), c.job_id,
            "--ball-dir", J(c, "outputs", "ball_track"),
            "--track-dir", J(c, "outputs", "tracks"),
            "--source", J(c, "frames"), "--gt-zip", "",
            "--out", J(c, "outputs", "follow_cam"), "--no-render")),
        Step("clip", "events", "event_highlights", lambda c: _py(
            _sd("clip_highlights.py"), c.job_id,
            "--events-dir", J(c, "outputs", "events"),
            "--follow-dir", J(c, "outputs", "follow_cam"),
            "--source", J(c, "frames"),
            "--out", J(c, "outputs", "event_highlights"))),
        # player_highlights tail (Part 1: involvement + clip-candidates; pause; Part 2: reels)
        Step("involvement", "player_highlights", "player_highlights", lambda c: _py(
            _sd("detect_involvement.py"), c.job_id,
            "--tracker-dir", J(c, "outputs", "tracks"),
            "--ball-dir", J(c, "outputs", "ball_track"),
            "--team-file", J(c, "outputs", "team_assign", "track_teams.json"),
            "--out", J(c, "involvement"))),
        Step("clip-candidates", "player_highlights", "player_highlights", lambda c: _py(
            _sd("clip_player_highlights.py"), c.job_id,
            "--involvement-dir", J(c, "involvement"),
            "--follow-dir", J(c, "outputs", "follow_cam"),
            "--source", J(c, "frames"),
            "--out", J(c, "outputs", "player_highlights"))),
        Step("tagging_pending", "tagging_pending", "player_highlights",
             lambda c: None),
        Step("reels", "player_highlights", "player_highlights", lambda c: _py(
            _sd("assemble_player_reels.py"), c.job_id,
            "--involvement-dir", J(c, "involvement"),
            "--clips-dir", J(c, "outputs", "player_highlights"),
            "--tracker-dir", J(c, "outputs", "tracks"),
            "--team-file", J(c, "outputs", "team_assign", "track_teams.json"),
            "--follow-dir", J(c, "outputs", "follow_cam"),
            "--source", J(c, "frames"),
            "--out", J(c, "outputs", "player_highlights"),
            "--render-seqs", c.job_id)),
    ]


def _seqlen(job_dir: Path, seq: str) -> int:
    ini = job_dir / "frames" / seq / "seqinfo.ini"
    cp = configparser.ConfigParser()
    cp.read(ini)
    try:
        return int(cp["Sequence"]["seqLength"])
    except Exception:
        return 100000  # fallback; coach clamps to available frames


def _basketball_steps() -> list[Step]:
    def decode(ctx):
        return lambda: adapters.decode_video(
            ctx.job_dir / "raw_video.mp4", ctx.job_dir / "frames", seq=ctx.job_id)

    def homography(ctx):
        def _run():
            cfg = JobConfig.model_validate_json(
                (ctx.job_dir / "job_config.json").read_text(encoding="utf-8"))
            payload = adapters.write_homography(
                [p.model_dump() for p in cfg.calibration_points], ctx.sport,
                ctx.job_dir / "homography.json")
            # coach_deliverable_basketball reads <deliverables>/<seq>/court/homography.json
            court = ctx.job_dir / "outputs" / "deliverables" / ctx.job_id / "court"
            court.mkdir(parents=True, exist_ok=True)
            shutil.copy(ctx.job_dir / "homography.json", court / "homography.json")
            return payload
        return _run

    J = lambda ctx, *p: str(ctx.job_dir.joinpath(*p))
    M = lambda name: str(config.MODELS_DIR / name)
    return [
        Step("decode", "decoding", None, decode),
        Step("homography", "decoding", None, homography),
        Step("detect-players", "detecting", None, lambda c: _py(
            _sd("build_det_cache.py"), "--detector", M("basketball_player.pt"),
            "--source", J(c, "frames"), "--out", J(c, "det_cache", "players"),
            "--class-name", "player", "--only", c.job_id)),
        Step("track-players", "tracking", None, lambda c: _py(
            _sd("track_from_cache.py"), "--cache", J(c, "det_cache", "players"),
            "--source", J(c, "frames"), "--out", J(c, "tracks", "players"))),
        Step("ball-cache", "ball", None, lambda c: _py(
            _sd("build_det_cache.py"), "--detector", M("basketball_ft.pt"),
            "--source", J(c, "frames"), "--out", J(c, "det_cache", "ball"),
            "--class-name", "ball", "--only", c.job_id)),
        Step("ball-kalman", "ball", None, lambda c: _py(
            _sd("analyze_ball_basketball.py"), c.job_id,
            "--cache-dir", J(c, "det_cache", "ball"), "--source", J(c, "frames"),
            "--out", J(c, "ball_track"), "--track-dir", J(c, "tracks", "players"),
            "--require-player", "--motion-consistency")),
        Step("team-assign", "teams", None, lambda c: _py(
            _sd("bball_team_embed.py"), "--seq", c.job_id,
            "--track", J(c, "tracks", "players"), "--frames-root", J(c, "frames"),
            "--court", J(c, "homography.json"), "--out", J(c, "team_assign"))),
        # coach_analytics tail
        Step("coach", "analytics", "coach_analytics", lambda c: _py(
            _sd("coach_deliverable_basketball.py"), c.job_id,
            "--win", "1", str(_seqlen(c.job_dir, c.job_id)),
            "--deliverables", J(c, "outputs", "deliverables"),
            "--track", J(c, "tracks", "players"), "--ball", J(c, "ball_track"),
            "--frames-root", J(c, "frames"),
            "--team-assign", J(c, "team_assign", "track_teams_emb.json"),
            "--no-video")),
        # event_highlights tail
        Step("follow-cam", "events", {"event_highlights", "player_highlights"}, lambda c: _py(
            _sd("follow_cam_basketball.py"), c.job_id,
            "--ball-dir", J(c, "ball_track"), "--track-dir", J(c, "tracks", "players"),
            "--source", J(c, "frames"), "--out", J(c, "follow_cam"), "--no-render")),
        Step("detect-events", "events", "event_highlights", lambda c: _py(
            _sd("detect_events_basketball.py"), c.job_id,
            "--ball-dir", J(c, "ball_track"), "--track-dir", J(c, "tracks", "players"),
            "--follow-dir", J(c, "follow_cam"), "--out", J(c, "events"),
            "--homography", J(c, "homography.json"),
            "--teams", J(c, "team_assign", "track_teams_emb.json"))),
        Step("clip", "events", "event_highlights", lambda c: _py(
            _sd("clip_highlights_basketball.py"), c.job_id,
            "--events-dir", J(c, "events"), "--follow-dir", J(c, "follow_cam"),
            "--source", J(c, "frames"), "--ball-dir", J(c, "ball_track"),
            "--out", J(c, "outputs", "event_highlights"), "--crop", "ball")),
        # player_highlights tail (Part 1: involvement + clip-candidates; pause; Part 2: reels)
        Step("involvement", "player_highlights", "player_highlights", lambda c: _py(
            _sd("detect_involvement_bb.py"), c.job_id,
            "--tracker-dir", J(c, "tracks", "players"),
            "--ball-dir", J(c, "ball_track"),
            "--team-file", J(c, "team_assign", "track_teams_emb.json"),
            "--out", J(c, "involvement"))),
        Step("clip-candidates", "player_highlights", "player_highlights", lambda c: _py(
            _sd("clip_player_highlights_bb.py"), c.job_id,
            "--involvement-dir", J(c, "involvement"),
            "--follow-dir", J(c, "follow_cam"),
            "--source", J(c, "frames"),
            "--out", J(c, "outputs", "player_highlights"))),
        Step("tagging_pending", "tagging_pending", "player_highlights",
             lambda c: None),
        Step("reels", "player_highlights", "player_highlights", lambda c: _py(
            _sd("assemble_player_reels_bb.py"), c.job_id,
            "--involvement-dir", J(c, "involvement"),
            "--clips-dir", J(c, "outputs", "player_highlights"),
            "--tracker-dir", J(c, "tracks", "players"),
            "--team-file", J(c, "team_assign", "track_teams_emb.json"),
            "--follow-dir", J(c, "follow_cam"),
            "--source", J(c, "frames"),
            "--out", J(c, "outputs", "player_highlights"))),
    ]


PIPELINES: dict[str, Callable[[], list[Step]]] = {
    "football": _football_steps,
    "basketball": _basketball_steps,
}


def resolve_steps(cfg: JobConfig) -> list[Step]:
    sport = cfg.sport
    if sport not in PIPELINES:
        raise ValueError(f"no pipeline for sport {sport}")
    requested = set(cfg.deliverables_requested)
    out = []
    for s in PIPELINES[sport]():
        d = s.deliverable
        if d is None:
            out.append(s)
        elif isinstance(d, set):
            if d & requested:  # any intersection → include
                out.append(s)
        else:
            if d in requested:
                out.append(s)
    return out


def run_step(step: Step, ctx: StepCtx, log_dir: Path) -> None:
    """Run one step: a callable adapter or a subprocess. Tee output to a log;
    raise on failure. A None build is a no-op (used by tagging_pending pause marker)."""
    built = step.build(ctx)
    if built is None:
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{step.key}.log"
    if callable(built):
        with open(log_path, "w", encoding="utf-8") as lf:
            lf.write(f"[adapter step {step.key}]\n")
            result = built()
            lf.write(f"ok: {result}\n")
        return
    with open(log_path, "w", encoding="utf-8") as lf:
        proc = subprocess.run(built, cwd=str(config.REPO_ROOT),
                              stdout=lf, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"step {step.key} exited {proc.returncode}; see {log_path}")
