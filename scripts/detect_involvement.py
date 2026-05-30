"""Day 27 PART A: per-player INVOLVEMENT detection (output #2, football).

The inclusive alternative to event highlights: every player who touches the action gets
footage, not just the stars. Involvement = math on already-cached data (no frames, no GPU):

  per confident ball frame -> the single nearest player TRACK to the ball, IF within an
  "on-ball" radius -> that track gets an involvement frame. Quiet defender who cleared 3
  balls -> 3 short involvement ranges; a playmaker -> many. The distribution is the
  inclusivity signal: a few stars with many moments + a long tail of quiet players with few.

WHY height-normalized (not pitch-meters): the GT homography zip was cleaned off disk, so we
can't project to pitch. Instead we scale the on-ball radius by EACH candidate player's bbox
height (a player ~= 1.8 m tall), giving a per-player px-per-metre estimate that auto-corrects
for perspective (far players are smaller in px). Honest, frame-free, and good enough for a
plausibility-level "near the ball" involvement proxy (we never claim exact per-touch).

Lost-ball discipline (Day-24): only frames where the ball is genuinely DETECTED count.
status == "predicted" (Kalman coasting) or "lost" are NOT fabricated into involvement.

Inputs (all cached JSON/txt -- no frames needed):
  outputs/track_results/sn_soccana_botsort_gmc/<seq>.txt   player tracks (MOT, top-left xywh)
  outputs/ball_track/<seq>/trajectory.json                 ball pixel trajectory + status
  outputs/team_assign/track_teams.json                     per-track role (exclude refs)

Output:
  outputs/involvement/<seq>/involvement.json   per-track involvement ranges + strength + stats
  outputs/involvement/<seq>/distribution.png   histogram: moments-per-track (the inclusivity curve)
  outputs/involvement/summary.json             cross-seq rollup

Usage:
  .venv\\Scripts\\python scripts\\detect_involvement.py            # all 5 seqs
  .venv\\Scripts\\python scripts\\detect_involvement.py SNGS-118   # one seq
"""
import argparse, json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np

SEQS_DEFAULT = ["SNGS-116", "SNGS-117", "SNGS-118", "SNGS-119", "SNGS-120"]
FPS = 25

# --- tunables (camera/scale-dependent -> RE-TUNE at the DPS mount) ---
PLAYER_HEIGHT_M = 1.8     # assumed real player height -> px_per_m = bbox_h / 1.8
ON_BALL_RADIUS_M = 2.5    # ball "involves" the nearest player if within this many metres
MERGE_GAP_FRAMES = 12     # join involvement frames of one track if gap <= this (~0.5 s)
MIN_RANGE_FRAMES = 5      # drop sub-0.2 s blips (not a real involvement)
MIN_TRACK_FRAMES = 25     # a "substantial" track (on court ~1 s+) -> counts for inclusivity
OUTFIELD_ROLES = {"TeamA", "TeamB"}   # exclude refs/NonOutfield from player reels


def load_tracks(path: Path):
    """MOT -> {frame: [(tid, cx, cy, h)]} using bbox CENTRE and height (top-left xywh input)."""
    by_frame = defaultdict(list)
    track_frames = defaultdict(int)
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(",")
        f, tid = int(p[0]), int(p[1])
        x, y, w, h = float(p[2]), float(p[3]), float(p[4]), float(p[5])
        by_frame[f].append((tid, x + w / 2.0, y + h / 2.0, h))
        track_frames[tid] += 1
    return by_frame, track_frames


def merge_ranges(frames, gap, min_len):
    """sorted involvement frames -> list of [start, end] ranges (merge small gaps, drop blips)."""
    if not frames:
        return []
    frames = sorted(frames)
    ranges = []
    s = prev = frames[0]
    for f in frames[1:]:
        if f - prev <= gap:
            prev = f
        else:
            ranges.append([s, prev]); s = prev = f
    ranges.append([s, prev])
    return [r for r in ranges if (r[1] - r[0] + 1) >= min_len]


def process_seq(seq, args):
    track_path = Path(args.tracker_dir) / f"{seq}.txt"
    ball = json.loads(Path(args.ball_dir, seq, "trajectory.json").read_text())
    teams = json.loads(Path(args.team_file).read_text()).get(seq, {})
    role_for_tid = {int(k): v["role"] for k, v in teams.items()}

    by_frame, track_frames = load_tracks(track_path)

    # involvement frames + per-frame closeness per track
    inv_frames = defaultdict(list)         # tid -> [frame, ...]
    inv_close = defaultdict(list)          # tid -> [closeness 0..1, ...]
    n_detected = n_assigned = n_noplayer = n_outofrange = 0
    for rec in ball:
        if rec["status"] != "detected":   # lost-ball discipline: confident ball only
            continue
        n_detected += 1
        f = rec["frame"]
        bx, by = rec["x"], rec["y"]
        players = by_frame.get(f, [])
        # nearest outfield player (exclude refs) by pixel distance to ball
        best = None
        for (tid, cx, cy, h) in players:
            if role_for_tid.get(tid) not in OUTFIELD_ROLES:
                continue
            d = float(np.hypot(cx - bx, cy - by))
            radius_px = (ON_BALL_RADIUS_M / PLAYER_HEIGHT_M) * h
            if best is None or d < best[1]:
                best = (tid, d, radius_px)
        if best is None:
            n_noplayer += 1
            continue
        tid, d, radius_px = best
        if d > radius_px:
            n_outofrange += 1
            continue
        n_assigned += 1
        inv_frames[tid].append(f)
        inv_close[tid].append(max(0.0, 1.0 - d / radius_px))

    # build per-track involvement ranges + strength
    tracks_out = []
    for tid, frames in inv_frames.items():
        ranges = merge_ranges(frames, MERGE_GAP_FRAMES, MIN_RANGE_FRAMES)
        if not ranges:
            continue
        close_by_frame = dict(zip(frames, inv_close[tid]))
        moments = []
        for (s, e) in ranges:
            fr = [cf for cf in frames if s <= cf <= e]
            dur = e - s + 1
            mean_close = float(np.mean([close_by_frame[cf] for cf in fr])) if fr else 0.0
            # strength: longer + closer = stronger (for ranking inside a player's reel)
            strength = round(dur / FPS * (0.5 + mean_close), 3)
            moments.append({
                "start": s, "end": e,
                "start_sec": round((s - 1) / FPS, 2), "end_sec": round((e - 1) / FPS, 2),
                "dur_frames": dur, "n_ball_frames": len(fr),
                "mean_closeness": round(mean_close, 3), "strength": strength,
            })
        moments.sort(key=lambda m: -m["strength"])
        tracks_out.append({
            "track_id": tid,
            "role": role_for_tid.get(tid),
            "track_len_frames": track_frames[tid],
            "n_moments": len(moments),
            "total_involvement_frames": len(frames),
            "moments": moments,
        })
    tracks_out.sort(key=lambda t: -t["n_moments"])

    # inclusivity bookkeeping: every SUBSTANTIAL outfield track should ideally get >=1 moment
    substantial = [tid for tid, n in track_frames.items()
                   if n >= MIN_TRACK_FRAMES and role_for_tid.get(tid) in OUTFIELD_ROLES]
    got_moment = {t["track_id"] for t in tracks_out}
    missed = sorted(set(substantial) - got_moment)

    stats = {
        "seq": seq,
        "ball_detected_frames": n_detected,
        "frames_assigned_to_a_player": n_assigned,
        "frames_no_outfield_player": n_noplayer,
        "frames_ball_out_of_range": n_outofrange,
        "n_tracks_with_involvement": len(tracks_out),
        "n_substantial_outfield_tracks": len(substantial),
        "n_substantial_missed": len(missed),
        "missed_track_ids": missed,
        "moments_per_track": {str(t["track_id"]): t["n_moments"] for t in tracks_out},
        "params": {
            "ON_BALL_RADIUS_M": ON_BALL_RADIUS_M, "PLAYER_HEIGHT_M": PLAYER_HEIGHT_M,
            "MERGE_GAP_FRAMES": MERGE_GAP_FRAMES, "MIN_RANGE_FRAMES": MIN_RANGE_FRAMES,
            "MIN_TRACK_FRAMES": MIN_TRACK_FRAMES, "ball_status_counted": "detected",
        },
    }

    out_dir = Path(args.out, seq); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "involvement.json").write_text(json.dumps(
        {"stats": stats, "tracks": tracks_out}, indent=2))
    render_distribution(seq, tracks_out, out_dir / "distribution.png")
    return stats, tracks_out


def render_distribution(seq, tracks_out, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    counts = sorted((t["n_moments"] for t in tracks_out), reverse=True)
    fig, ax = plt.subplots(figsize=(10, 3.4), dpi=110)
    if counts:
        ax.bar(range(len(counts)), counts, color="#3c8cdc")
        ax.axhline(np.median(counts), color="#dc3c3c", ls="--", lw=1,
                   label=f"median={np.median(counts):.0f}")
        ax.legend()
    ax.set_xlabel("player track (sorted by involvement)")
    ax.set_ylabel("involvement moments")
    ax.set_title(f"{seq} - involvement per track  (stars left, quiet long-tail right = inclusivity)")
    plt.tight_layout(); plt.savefig(out_path); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="?", default=None)
    ap.add_argument("--tracker-dir", default="outputs/track_results/sn_soccana_botsort_gmc")
    ap.add_argument("--ball-dir", default="outputs/ball_track")
    ap.add_argument("--team-file", default="outputs/team_assign/track_teams.json")
    ap.add_argument("--out", default="outputs/involvement")
    args = ap.parse_args()

    seqs = [args.seq] if args.seq else SEQS_DEFAULT
    Path(args.out).mkdir(parents=True, exist_ok=True)
    rollup = {}
    for seq in seqs:
        stats, tracks = process_seq(seq, args)
        rollup[seq] = stats
        mp = sorted((t["n_moments"] for t in tracks), reverse=True)
        dist = f"max={mp[0]} median={int(np.median(mp))} min={mp[-1]}" if mp else "none"
        print(f"\n=== {seq} ===")
        print(f"  ball detected frames: {stats['ball_detected_frames']}  "
              f"assigned-to-player: {stats['frames_assigned_to_a_player']}  "
              f"(no-player {stats['frames_no_outfield_player']}, out-of-range {stats['frames_ball_out_of_range']})")
        print(f"  tracks with involvement: {stats['n_tracks_with_involvement']}  "
              f"| moments/track {dist}")
        print(f"  INCLUSIVITY: substantial outfield tracks={stats['n_substantial_outfield_tracks']}  "
              f"got footage={stats['n_substantial_outfield_tracks']-stats['n_substantial_missed']}  "
              f"MISSED={stats['n_substantial_missed']} {stats['missed_track_ids'] or ''}")

    Path(args.out, "summary.json").write_text(json.dumps(rollup, indent=2))
    # cross-seq inclusivity rollup
    tot_sub = sum(s["n_substantial_outfield_tracks"] for s in rollup.values())
    tot_missed = sum(s["n_substantial_missed"] for s in rollup.values())
    print(f"\n=== ALL {len(seqs)} seqs ===")
    print(f"  substantial outfield tracks: {tot_sub}  | with involvement footage: {tot_sub-tot_missed}  "
          f"| missed: {tot_missed}  ({100*(tot_sub-tot_missed)/max(1,tot_sub):.1f}% covered)")
    print(f"  summary -> {Path(args.out,'summary.json')}")


if __name__ == "__main__":
    main()
