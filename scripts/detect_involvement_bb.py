"""Day 28 PART A: per-player INVOLVEMENT for BASKETBALL -- re-derived for the half-court.

Day-27 football involvement = "single nearest player within ~2.5 m of the ball." That works
on a spread pitch. Basketball is a half-court game in a tiny space: with a fixed radius nearly
EVERY player sits within range of the ball, and because the "nearest" assignment churns frame
to frame in a crowd, involvement smears across all 10 players -> no discrimination between the
ball-handler and a kid standing in the corner. A smaller radius alone does NOT fix this.

So this script MEASURES BEFORE CLIPPING. It implements three involvement definitions and reports
the per-track distribution for each, so we can pick the one that DISCRIMINATES (a few ball-handler
stars + a quiet long tail) rather than "everyone involved every frame":

  mode=radius   ALL outfield players within the on-ball radius are "involved" (the BAD baseline
                that proves a fixed radius marks the whole crowd in a half-court).
  mode=nearest  only the SINGLE closest outfield player (within radius) is involved -- the
                Day-27 mechanism, one player per frame.
  mode=gap      nearest AND meaningfully closer than the 2nd-nearest (d2 >= GAP_FACTOR * d1):
                the ball is clearly THEIRS, not contested-equidistant. Filters ambiguous crowd
                frames -> concentrates involvement on real ball-handlers. (lean choice)

Shared with Day-27:
  * height-normalized radius (no homography): radius_px = (R_m / PLAYER_HEIGHT_M) * bbox_h, so
    far/small players auto-get a smaller px radius. Re-tuned for basketball scale.
  * lost-ball discipline (Day-24): only status=="detected" ball frames count; predicted/lost
    are never fabricated into involvement.
  * OUTFIELD_ROLES excludes Referee/Excluded.

Inputs (all cached, frame-free):
  outputs/track_results/bb_ftdet_botsort_gmc/<seq>.txt   player tracks (MOT, top-left xywh)
  outputs/ball_track_bb/<seq>/trajectory.json            ball pixel trajectory + status
  outputs/team_assign_bb/track_teams_bb.json             per-track role (exclude refs/excluded)

Output:
  outputs/involvement_bb/<seq>/involvement.json   per-track ranges + strength + stats (chosen mode)
  outputs/involvement_bb/<seq>/distribution.png   moments-per-track histogram
  outputs/involvement_bb/summary.json             cross-seq rollup
  outputs/involvement_bb/_compare.json            (--compare) all-mode discrimination table

Usage:
  .venv\\Scripts\\python scripts\\detect_involvement_bb.py --compare        # measure all 3 modes
  .venv\\Scripts\\python scripts\\detect_involvement_bb.py --mode gap        # write chosen mode, all seqs
  .venv\\Scripts\\python scripts\\detect_involvement_bb.py --mode gap v_00HRwkvvjtQ_c001
"""
import argparse, json
from collections import defaultdict
from pathlib import Path
import numpy as np

SEQS_DEFAULT = ["v_00HRwkvvjtQ_c001", "v_00HRwkvvjtQ_c003", "v_00HRwkvvjtQ_c005",
                "v_00HRwkvvjtQ_c007", "v_00HRwkvvjtQ_c008"]
FPS = 25

# --- tunables (camera/scale-dependent -> RE-TUNE at the DPS mount) ---
PLAYER_HEIGHT_M = 1.9     # basketball player ~1.9 m -> px_per_m = bbox_h / 1.9
ON_BALL_RADIUS_M = 1.8    # tighter than football's 2.5: half-court is congested
GAP_FACTOR = 1.6          # gap mode: 2nd-nearest must be >=1.6x the nearest's distance
MERGE_GAP_FRAMES = 12     # join involvement frames of one track if gap <= this (~0.5 s)
MIN_RANGE_FRAMES = 5      # drop sub-0.2 s blips
MIN_TRACK_FRAMES = 25     # a "substantial" track (~1 s+ on court) -> counts for inclusivity
OUTFIELD_ROLES = {"TeamA", "TeamB"}   # exclude Referee / Excluded


def load_tracks(path: Path):
    """MOT -> {frame: [(tid, cx, cy, h)]} using bbox CENTRE + height (top-left xywh input)."""
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
    if not frames:
        return []
    frames = sorted(frames)
    ranges, s, prev = [], frames[0], frames[0]
    for f in frames[1:]:
        if f - prev <= gap:
            prev = f
        else:
            ranges.append([s, prev]); s = prev = f
    ranges.append([s, prev])
    return [r for r in ranges if (r[1] - r[0] + 1) >= min_len]


def assign_frame(players_outfield, bx, by, mode):
    """Return list of (tid, closeness 0..1) involved THIS frame under `mode`.

    players_outfield: [(tid, cx, cy, radius_px, d)] precomputed distance to ball.
    """
    if not players_outfield:
        return []
    ranked = sorted(players_outfield, key=lambda t: t[4])   # by distance
    tid0, _, _, r0, d0 = ranked[0]
    if mode == "radius":
        # everyone within their own height-normalized radius (the BAD baseline)
        return [(t[0], max(0.0, 1.0 - t[4] / t[3])) for t in ranked if t[4] <= t[3]]
    if d0 > r0:
        return []                                            # nearest not even on-ball
    if mode == "nearest":
        return [(tid0, max(0.0, 1.0 - d0 / r0))]
    if mode == "gap":
        if len(ranked) >= 2:
            d1 = ranked[1][4]
            if d1 < GAP_FACTOR * d0:                         # contested / equidistant crowd
                return []
        return [(tid0, max(0.0, 1.0 - d0 / r0))]
    raise ValueError(mode)


def compute(seq, args, mode):
    track_path = Path(args.tracker_dir) / f"{seq}.txt"
    ball = json.loads(Path(args.ball_dir, seq, "trajectory.json").read_text())
    teams = json.loads(Path(args.team_file).read_text()).get(seq, {})
    role_for_tid = {int(k): v["role"] for k, v in teams.items()}
    by_frame, track_frames = load_tracks(track_path)

    inv_frames = defaultdict(list)
    inv_close = defaultdict(list)
    n_detected = n_assigned_frames = 0
    players_marked = 0                       # total (tid,frame) involvement marks
    for rec in ball:
        if rec["status"] != "detected":      # lost-ball discipline
            continue
        n_detected += 1
        f, bx, by = rec["frame"], rec["x"], rec["y"]
        cand = []
        for (tid, cx, cy, h) in by_frame.get(f, []):
            if role_for_tid.get(tid) not in OUTFIELD_ROLES:
                continue
            d = float(np.hypot(cx - bx, cy - by))
            radius_px = (ON_BALL_RADIUS_M / PLAYER_HEIGHT_M) * h
            cand.append((tid, cx, cy, radius_px, d))
        marks = assign_frame(cand, bx, by, mode)
        if marks:
            n_assigned_frames += 1
            players_marked += len(marks)
        for tid, close in marks:
            inv_frames[tid].append(f)
            inv_close[tid].append(close)

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
            moments.append({
                "start": s, "end": e,
                "start_sec": round((s - 1) / FPS, 2), "end_sec": round((e - 1) / FPS, 2),
                "dur_frames": dur, "n_ball_frames": len(fr),
                "mean_closeness": round(mean_close, 3),
                "strength": round(dur / FPS * (0.5 + mean_close), 3),
            })
        moments.sort(key=lambda m: -m["strength"])
        tracks_out.append({
            "track_id": tid, "role": role_for_tid.get(tid),
            "track_len_frames": track_frames[tid], "n_moments": len(moments),
            "total_involvement_frames": len(frames), "moments": moments,
        })
    tracks_out.sort(key=lambda t: -t["n_moments"])

    substantial = [tid for tid, n in track_frames.items()
                   if n >= MIN_TRACK_FRAMES and role_for_tid.get(tid) in OUTFIELD_ROLES]
    got = {t["track_id"] for t in tracks_out}
    missed = sorted(set(substantial) - got)

    # discrimination metrics
    inv_counts = sorted((t["total_involvement_frames"] for t in tracks_out), reverse=True)
    tot_inv = sum(inv_counts)
    top3_share = round(sum(inv_counts[:3]) / tot_inv, 3) if tot_inv else 0.0
    involved_frac = round(len(tracks_out) / max(1, len(substantial)), 3)
    players_per_assigned = round(players_marked / max(1, n_assigned_frames), 2)

    stats = {
        "seq": seq, "mode": mode,
        "ball_detected_frames": n_detected,
        "frames_with_involvement": n_assigned_frames,
        "n_tracks_with_involvement": len(tracks_out),
        "n_substantial_outfield_tracks": len(substantial),
        "n_substantial_missed": len(missed), "missed_track_ids": missed,
        # discrimination signals:
        "involved_fraction_of_substantial": involved_frac,   # 1.0 = everyone gets involved (bad)
        "players_marked_per_frame": players_per_assigned,     # >1 = crowd marking (bad)
        "top3_involvement_share": top3_share,                 # high = concentrated on stars (good)
        "moments_per_track": {str(t["track_id"]): t["n_moments"] for t in tracks_out},
        "params": {"ON_BALL_RADIUS_M": ON_BALL_RADIUS_M, "PLAYER_HEIGHT_M": PLAYER_HEIGHT_M,
                   "GAP_FACTOR": GAP_FACTOR, "MERGE_GAP_FRAMES": MERGE_GAP_FRAMES,
                   "MIN_RANGE_FRAMES": MIN_RANGE_FRAMES, "MIN_TRACK_FRAMES": MIN_TRACK_FRAMES,
                   "ball_status_counted": "detected"},
    }
    return stats, tracks_out


def render_distribution(seq, mode, tracks_out, out_path):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    counts = sorted((t["n_moments"] for t in tracks_out), reverse=True)
    fig, ax = plt.subplots(figsize=(10, 3.4), dpi=110)
    if counts:
        ax.bar(range(len(counts)), counts, color="#dc7d3c")
        ax.axhline(np.median(counts), color="#3c3cdc", ls="--", lw=1,
                   label=f"median={np.median(counts):.0f}")
        ax.legend()
    ax.set_xlabel("player track (sorted by involvement)")
    ax.set_ylabel("involvement moments")
    ax.set_title(f"{seq}  [{mode}]  involvement per track  (stars left, quiet tail right)")
    plt.tight_layout(); plt.savefig(out_path); plt.close(fig)


def write_canonical(seq, args, mode):
    stats, tracks_out = compute(seq, args, mode)
    out_dir = Path(args.out, seq); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "involvement.json").write_text(json.dumps(
        {"stats": stats, "tracks": tracks_out}, indent=2))
    render_distribution(seq, mode, tracks_out, out_dir / "distribution.png")
    return stats, tracks_out


def run_compare(seqs, args):
    modes = ["radius", "nearest", "gap"]
    table = {m: {} for m in modes}
    print("\n=== INVOLVEMENT DEFINITION COMPARISON (measure-before-clip gate) ===")
    print("GOOD = discriminates: low involved-fraction, ~1 player/frame, high top-3 share.")
    print("BAD  = fixed radius marks the crowd: involved-fraction ~1.0, >1 player/frame.\n")
    hdr = f"{'seq':<22}{'mode':<9}{'sub':>4}{'invd':>5}{'inv_frac':>9}{'pl/frm':>8}{'top3sh':>8}{'miss':>6}"
    print(hdr); print("-" * len(hdr))
    for seq in seqs:
        for m in modes:
            s, _ = compute(seq, args, m)
            table[m][seq] = s
            print(f"{seq:<22}{m:<9}{s['n_substantial_outfield_tracks']:>4}"
                  f"{s['n_tracks_with_involvement']:>5}{s['involved_fraction_of_substantial']:>9}"
                  f"{s['players_marked_per_frame']:>8}{s['top3_involvement_share']:>8}"
                  f"{s['n_substantial_missed']:>6}")
        print()
    # aggregate per mode
    print("=== AGGREGATE per mode (mean across seqs) ===")
    agg = {}
    for m in modes:
        ss = list(table[m].values())
        agg[m] = {
            "mean_involved_fraction": round(np.mean([x["involved_fraction_of_substantial"] for x in ss]), 3),
            "mean_players_per_frame": round(np.mean([x["players_marked_per_frame"] for x in ss]), 2),
            "mean_top3_share": round(np.mean([x["top3_involvement_share"] for x in ss]), 3),
            "total_substantial": int(sum(x["n_substantial_outfield_tracks"] for x in ss)),
            "total_with_involvement": int(sum(x["n_tracks_with_involvement"] for x in ss)),
            "total_missed": int(sum(x["n_substantial_missed"] for x in ss)),
        }
        print(f"  {m:<9} involved_frac={agg[m]['mean_involved_fraction']:<6} "
              f"players/frame={agg[m]['mean_players_per_frame']:<5} "
              f"top3_share={agg[m]['mean_top3_share']:<6} "
              f"covered={agg[m]['total_with_involvement']}/{agg[m]['total_substantial']}")
    Path(args.out).mkdir(parents=True, exist_ok=True)
    Path(args.out, "_compare.json").write_text(json.dumps(
        {"per_seq": table, "aggregate": agg}, indent=2))
    print(f"\n  compare -> {Path(args.out, '_compare.json')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="?", default=None)
    ap.add_argument("--mode", choices=["radius", "nearest", "gap"], default="gap")
    ap.add_argument("--compare", action="store_true", help="run all 3 modes, print table, no canonical write")
    ap.add_argument("--tracker-dir", default="outputs/track_results/bb_ftdet_botsort_gmc")
    ap.add_argument("--ball-dir", default="outputs/ball_track_bb")
    ap.add_argument("--team-file", default="outputs/team_assign_bb/track_teams_bb.json")
    ap.add_argument("--out", default="outputs/involvement_bb")
    args = ap.parse_args()

    seqs = [args.seq] if args.seq else SEQS_DEFAULT
    if args.compare:
        run_compare(seqs, args)
        return

    Path(args.out).mkdir(parents=True, exist_ok=True)
    rollup = {}
    for seq in seqs:
        stats, tracks = write_canonical(seq, args, args.mode)
        rollup[seq] = stats
        mp = sorted((t["n_moments"] for t in tracks), reverse=True)
        dist = f"max={mp[0]} median={int(np.median(mp))} min={mp[-1]}" if mp else "none"
        print(f"\n=== {seq}  [{args.mode}] ===")
        print(f"  ball detected={stats['ball_detected_frames']}  frames w/ involvement={stats['frames_with_involvement']}")
        print(f"  tracks involved={stats['n_tracks_with_involvement']}  | moments/track {dist}")
        print(f"  discrimination: involved_frac={stats['involved_fraction_of_substantial']} "
              f"players/frame={stats['players_marked_per_frame']} top3_share={stats['top3_involvement_share']}")
        print(f"  INCLUSIVITY: substantial={stats['n_substantial_outfield_tracks']} "
              f"got_involvement={stats['n_tracks_with_involvement']} "
              f"MISSED={stats['n_substantial_missed']} {stats['missed_track_ids'] or ''}")
    Path(args.out, "summary.json").write_text(json.dumps(rollup, indent=2))
    tot_sub = sum(s["n_substantial_outfield_tracks"] for s in rollup.values())
    tot_miss = sum(s["n_substantial_missed"] for s in rollup.values())
    print(f"\n=== ALL {len(seqs)} seqs [{args.mode}] ===")
    print(f"  substantial={tot_sub}  involvement-covered={tot_sub-tot_miss}  "
          f"need-presence-fallback={tot_miss}")


if __name__ == "__main__":
    main()
