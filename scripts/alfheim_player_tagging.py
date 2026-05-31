"""Day 31 PART C (+ PART A decoupling): full-match PLAYER-HIGHLIGHT TAGGING VOLUME.

THE deployment-viability number for output #2 at full-match scale. Decoupled from SoccerNet:
takes a generic MOT + fps + (optional) ball track + (optional) homography -- NO <seq> structure,
NO GSR labels, NO follow_cam. This generality is itself operator-app progress (runs on arbitrary
footage). Logic is the Day-27 design (involvement nearest-player-to-ball + presence fallback),
re-expressed generically.

THE KEY FRAMING (why this number is robust to ball recall):
  Every SUBSTANTIAL track must be tagged by a human (assign it to a real player) -- that is the
  tagging unit. PRESENCE fallback gives every substantial track >=1 clip with NO ball needed.
  INVOLVEMENT (needs a ball) only ADDS clips per track. So:
     MINIMUM tagging volume  = number of substantial tracks            (presence, ball-free)
     ACTUAL tagging volume   = involvement clips + presence clips      (>= minimum)
  => the viable/prohibitive verdict holds even if the wide-cam ball track is poor/absent.

Fragmentation reality (Day-30): identity fragments to ~191 track-IDs per real player, so a
"per-player reel" pre-tagging is really a TRACK reel; the human tagging is what reconstitutes
real players. This script quantifies exactly how much tagging that takes for a 45-min match.

Inputs:
  --mot     MOT txt (frame,id,x,y,w,h,...) -- Alfheim: the Day-30 re-linked (safe -18%) tracks
  --fps     EFFECTIVE fps of the MOT timeline (Alfheim stride-2 over 30fps -> 15.0)
  --ball    (optional) ball track json {mot_frame: [x,y,conf]} -> enables involvement clips
  --min-sec substantial-track threshold in seconds (default 1.0)

Output (outputs/alfheim/player_tagging/):
  tagging_volume.json   the numbers (total clips, involve/presence split, tag-time, inclusivity)
  clips_per_track.png   distribution (the inclusivity / tagging-load curve)

Usage:
  .venv\\Scripts\\python scripts\\alfheim_player_tagging.py \
     --mot outputs/track_results/alfheim_fh_cam1/first_half_relink_mod.txt --fps 15
"""
import argparse, json
from collections import defaultdict
from pathlib import Path
import numpy as np

# --- involvement tunables (height-normalized; camera-scale-independent enough for a proxy) ---
PLAYER_HEIGHT_M = 1.8
ON_BALL_RADIUS_M = 2.5
PX_PER_M_FALLBACK = None     # use bbox height per player

# seconds-per-tag scenarios (human watches a short clip + assigns/confirms a name)
TAG_SEC_SCENARIOS = {"fast_5s": 5, "realistic_10s": 10, "careful_20s": 20}


def load_mot(path):
    by_frame = defaultdict(list)        # f -> [(tid, cx, cy, h)]
    frames_of = defaultdict(list)       # tid -> [f,...]
    tf = defaultdict(int)
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(",")
        f, tid = int(p[0]), int(p[1])
        x, y, w, h = float(p[2]), float(p[3]), float(p[4]), float(p[5])
        by_frame[f].append((tid, x + w / 2.0, y + h / 2.0, h))
        frames_of[tid].append(f)
        tf[tid] += 1
    return by_frame, frames_of, tf


def merge_ranges(frames, gap, min_len):
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


def longest_stretch(frames, gap):
    if not frames:
        return None
    frames = sorted(frames)
    best = cur = [frames[0], frames[0]]
    for f in frames[1:]:
        if f - cur[1] <= gap:
            cur[1] = f
        else:
            if cur[1] - cur[0] > best[1] - best[0]:
                best = cur
            cur = [f, f]
    if cur[1] - cur[0] > best[1] - best[0]:
        best = cur
    return best


def compute_involvement(by_frame, ball, fps, gap, min_range):
    """ball: {mot_frame:int -> (x,y)}. Returns tid -> [moment_ranges]. Height-normalized radius."""
    inv_frames = defaultdict(list)
    n_ball = 0; n_assigned = 0
    for f, (bx, by) in ball.items():
        players = by_frame.get(f, [])
        if not players:
            continue
        n_ball += 1
        best = None
        for (tid, cx, cy, h) in players:
            d = float(np.hypot(cx - bx, cy - by))
            radius_px = (ON_BALL_RADIUS_M / PLAYER_HEIGHT_M) * h
            if best is None or d < best[1]:
                best = (tid, d, radius_px)
        if best is None or best[1] > best[2]:
            continue
        n_assigned += 1
        inv_frames[best[0]].append(f)
    moments = {}
    for tid, frs in inv_frames.items():
        r = merge_ranges(frs, gap, min_range)
        if r:
            moments[tid] = r
    return moments, n_ball, n_assigned


def load_ball(path, src_fps_ratio):
    """probe/full ball json {src_frame: [x,y,conf]} -> {mot_frame: (x,y)}. mot_frame=src/ratio."""
    raw = json.loads(Path(path).read_text())
    out = {}
    for sf, v in raw.items():
        mf = int(round(int(sf) / src_fps_ratio))
        out[mf] = (v[0], v[1])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mot", default="outputs/track_results/alfheim_fh_cam1/first_half_relink_mod.txt")
    ap.add_argument("--fps", type=float, default=15.0, help="EFFECTIVE mot fps (stride-2 over 30 -> 15)")
    ap.add_argument("--ball", default=None, help="optional ball json {src_frame:[x,y,conf]}")
    ap.add_argument("--ball-src-ratio", type=float, default=2.0,
                    help="ball src-frame -> mot-frame divisor (src 30fps / mot 15fps = 2)")
    ap.add_argument("--min-sec", type=float, default=1.0, help="substantial-track threshold (s)")
    ap.add_argument("--merge-gap-sec", type=float, default=0.8, help="join involvement frames within (s)")
    ap.add_argument("--min-range-sec", type=float, default=0.33, help="drop sub-this involvement blips (s)")
    ap.add_argument("--out", default="outputs/alfheim/player_tagging")
    args = ap.parse_args()

    by_frame, frames_of, tf = load_mot(args.mot)
    fps = args.fps
    min_track = int(round(args.min_sec * fps))
    gap = max(1, int(round(args.merge_gap_sec * fps)))
    min_range = max(1, int(round(args.min_range_sec * fps)))
    fmax = max(by_frame) if by_frame else 0
    minutes = fmax / fps / 60.0

    substantial = sorted([tid for tid, n in tf.items() if n >= min_track])

    # involvement (optional, ball-gated)
    moments = {}; ball_meta = {"ball_used": False}
    if args.ball and Path(args.ball).exists():
        ball = load_ball(args.ball, args.ball_src_ratio)
        moments, n_ball, n_assigned = compute_involvement(by_frame, ball, fps, gap, min_range)
        ball_meta = {"ball_used": True, "ball_frames": len(ball),
                     "ball_frames_in_mot_range": n_ball,
                     "frames_assigned_to_player": n_assigned,
                     "tracks_with_involvement": len(moments)}

    # per substantial track: involvement clips (1 per moment) OR 1 presence clip
    via_involvement = 0; via_presence = 0
    involvement_clips = 0
    clips_per_track = []
    for tid in substantial:
        mlist = moments.get(tid, [])
        n_inv = len(mlist)
        if n_inv > 0:
            via_involvement += 1
            involvement_clips += n_inv
            clips_per_track.append(n_inv)
        else:
            via_presence += 1
            clips_per_track.append(1)   # one presence clip
    presence_clips = via_presence
    total_clips = involvement_clips + presence_clips

    # tagging-time estimates
    tag_time = {}
    for name, sec in TAG_SEC_SCENARIOS.items():
        tot = total_clips * sec
        tag_time[name] = {"sec_per_tag": sec, "total_sec": tot,
                          "total_min": round(tot / 60, 1), "total_hours": round(tot / 3600, 2)}
    # minimum-volume (presence-only, ball-free lower bound = every substantial track tagged once)
    min_vol = len(substantial)
    min_tag_time = {name: round(min_vol * sec / 60, 1) for name, sec in TAG_SEC_SCENARIOS.items()}

    report = {
        "mot": args.mot, "fps_effective": fps, "match_minutes": round(minutes, 1),
        "total_tracks": len(tf), "min_track_frames": min_track, "min_track_sec": args.min_sec,
        "n_substantial_tracks": len(substantial),
        "ball": ball_meta,
        "tagging_volume": {
            "total_clips": total_clips,
            "via_involvement_tracks": via_involvement, "involvement_clips": involvement_clips,
            "via_presence_tracks": via_presence, "presence_clips": presence_clips,
            "presence_share_pct": round(100 * presence_clips / max(1, total_clips), 1),
        },
        "MINIMUM_tagging_volume_ball_free": {
            "clips": min_vol, "note": "presence-only lower bound: 1 tag per substantial track",
            "tag_time_min": min_tag_time,
        },
        "estimated_human_tag_time": tag_time,
        "clips_per_track": {
            "min": int(min(clips_per_track)) if clips_per_track else 0,
            "median": float(np.median(clips_per_track)) if clips_per_track else 0,
            "mean": round(float(np.mean(clips_per_track)), 2) if clips_per_track else 0,
            "max": int(max(clips_per_track)) if clips_per_track else 0,
        },
        "inclusivity": {
            "substantial_tracks_with_footage": via_involvement + via_presence,
            "coverage_pct": 100.0,
            "note": ("100% of substantial tracks get >=1 clip (presence guarantees it). BUT with "
                     "~191 track-IDs per real player (Day-30 fragmentation), these are TRACK reels, "
                     "not player reels -- the human tagging is what reconstitutes the ~22 real players."),
        },
    }
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / "tagging_volume.json").write_text(json.dumps(report, indent=2))

    # distribution plot
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    counts = sorted(clips_per_track, reverse=True)
    fig, ax = plt.subplots(figsize=(11, 3.6), dpi=110)
    if counts:
        ax.bar(range(len(counts)), counts, color="#3c8cdc", width=1.0)
        ax.axhline(np.median(counts), color="#dc3c3c", ls="--", lw=1, label=f"median={np.median(counts):.0f}")
        ax.legend()
    ax.set_xlabel(f"substantial track ({len(substantial)} total, sorted by clip count)")
    ax.set_ylabel("clips to tag")
    ax.set_title(f"Alfheim full-match player-highlight tagging load  "
                 f"({total_clips} clips over {minutes:.0f} min)")
    plt.tight_layout(); plt.savefig(out / "clips_per_track.png"); plt.close(fig)

    # console summary
    print(f"\n=== Alfheim full-match player tagging volume ({minutes:.1f} min) ===")
    print(f"  total tracks={len(tf)}  substantial(>= {args.min_sec}s)={len(substantial)}")
    print(f"  ball used: {ball_meta['ball_used']}"
          + (f"  involvement-tracks={ball_meta.get('tracks_with_involvement')}" if ball_meta['ball_used'] else ""))
    tv = report["tagging_volume"]
    print(f"  TOTAL CLIPS TO TAG = {tv['total_clips']}  "
          f"(involvement {tv['involvement_clips']} from {tv['via_involvement_tracks']} tracks "
          f"+ presence {tv['presence_clips']})  presence-share={tv['presence_share_pct']}%")
    print(f"  MINIMUM (ball-free presence lower bound) = {min_vol} tags")
    print(f"  est. human tag time: " + "  ".join(
        f"{k}={v['total_min']}min({v['total_hours']}h)" for k, v in tag_time.items()))
    print(f"  -> {out}/tagging_volume.json")


if __name__ == "__main__":
    main()
