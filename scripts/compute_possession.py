"""Day 12 bonus: possession proxy from ball position + team assignments.

Per frame: pitch-project all tracker player feet, find closest player to ball pitch position,
attribute that frame to their team. Aggregate per seq -> possession %.

Skips:
  - Frames where the ball has no pitch coord (no Kalman output, no homography)
  - Aerial-suspect frames (ball pitch position is unreliable when ball is in the air)
  - Frames where no player track is on the field

Output:
  outputs/ball_track/<seq>/possession.json
  outputs/ball_track/<seq>/possession_summary.png   (timeline of who has the ball)

Usage:
  python scripts/compute_possession.py [SNGS-118]
"""
import argparse, json, sys, zipfile
from collections import defaultdict, Counter
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent))
from analyze_pitch import load_gt, derive_per_frame_H, load_tracker as load_tracker_feet

SEQS_DEFAULT = ["SNGS-116", "SNGS-117", "SNGS-118", "SNGS-119", "SNGS-120"]
MAX_CLAIM_DIST_M = 5.0   # ball claimed only if closest player is within this distance

def load_tracker_xywh(path: Path):
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip(): continue
        p = line.split(",")
        f = int(p[0]); tid = int(p[1])
        x = float(p[2]); y = float(p[3]); w = float(p[4]); h = float(p[5])
        rows.append((f, tid, x, y, w, h))
    return rows

def render_possession_timeline(seq: str, per_frame: list, n_frames: int, out_path: Path):
    """Stacked bar (one row): green for TeamA, red for TeamB, grey for none/aerial/no-ball."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    color_map = {"TeamA": "#3cdc3c", "TeamB": "#dc3c3c", None: "#454545"}
    arr = np.zeros((1, n_frames, 3))
    for f, who in per_frame:
        c = color_map.get(who, "#454545")
        rgb = tuple(int(c[i:i+2], 16)/255 for i in (1, 3, 5))
        arr[0, f-1] = rgb
    fig, ax = plt.subplots(figsize=(12, 1.4), dpi=110)
    ax.imshow(arr, aspect="auto")
    ax.set_yticks([])
    ax.set_xlabel("frame")
    ax.set_title(f"{seq} - Possession timeline (green=TeamA, red=TeamB, grey=neutral)")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close(fig)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="?", default=None)
    ap.add_argument("--zip", default="datasets/soccernet_gsr/test.zip")
    ap.add_argument("--source", default="datasets/soccernet_tracking")
    ap.add_argument("--tracker-dir", default="outputs/track_results/sn_soccana_botsort_gmc")
    ap.add_argument("--ball-track-dir", default="outputs/ball_track")
    ap.add_argument("--team-assign-dir", default="outputs/team_assign")
    args = ap.parse_args()

    seqs = [args.seq] if args.seq else SEQS_DEFAULT

    # Load Day-11 team assignments (the same file for all seqs)
    team_data = json.loads(Path(args.team_assign_dir, "track_teams.json").read_text())

    summary = {}
    for seq in seqs:
        print(f"\n=== {seq} ===")
        # Load ball Kalman trajectory
        ball_traj = json.loads(Path(args.ball_track_dir, seq, "trajectory.json").read_text())
        # Load Day-9 tracker player output
        track_path = Path(args.tracker_dir, f"{seq}.txt")
        player_rows = load_tracker_xywh(track_path)
        # Load Day-10 H per frame (from GT correspondences)
        gt_pts = load_gt(Path(args.zip), seq)
        H_by_frame, _ = derive_per_frame_H(gt_pts)
        # Team labels per (seq, tid)
        team_for_tid = {int(k): v["role"] for k, v in team_data[seq].items()}

        # Group player rows by frame; project feet to pitch
        player_pitch_by_frame = defaultdict(list)  # {frame: [(tid, x_m, y_m)]}
        for (f, tid, x, y, w, h) in player_rows:
            H = H_by_frame.get(f)
            if H is None: continue
            role = team_for_tid.get(tid)
            if role not in ("TeamA", "TeamB"): continue  # skip refs + unflagged
            feet = np.array([[[x + w/2, y + h]]], dtype=np.float32)
            pt = cv2.perspectiveTransform(feet, H).ravel()
            player_pitch_by_frame[f].append((tid, float(pt[0]), float(pt[1]), role))

        # For each ball-frame, find closest player to ball
        per_frame = []
        possession_counts = Counter()
        n_no_ball = n_no_pitch = n_aerial = n_no_players = n_far = 0
        for rec in ball_traj:
            f = rec["frame"]
            if rec["status"] == "lost" or rec["pitch_x_m"] is None:
                if rec["status"] == "lost": n_no_ball += 1
                else: n_no_pitch += 1
                per_frame.append((f, None)); continue
            if rec.get("aerial_suspect"):
                n_aerial += 1
                per_frame.append((f, None)); continue
            bx, by = rec["pitch_x_m"], rec["pitch_y_m"]
            players = player_pitch_by_frame.get(f, [])
            if not players:
                n_no_players += 1
                per_frame.append((f, None)); continue
            dists = [(np.hypot(p[1] - bx, p[2] - by), p[3]) for p in players]
            dists.sort(key=lambda x: x[0])
            closest_d, closest_team = dists[0]
            if closest_d > MAX_CLAIM_DIST_M:
                n_far += 1
                per_frame.append((f, None))  # ball too far from any player -> neutral
            else:
                possession_counts[closest_team] += 1
                per_frame.append((f, closest_team))

        n_counted = sum(possession_counts.values())
        teamA_pct = 100 * possession_counts["TeamA"] / max(1, n_counted)
        teamB_pct = 100 * possession_counts["TeamB"] / max(1, n_counted)
        print(f"  TeamA possession: {teamA_pct:.1f}%   TeamB possession: {teamB_pct:.1f}%   "
              f"(n_counted={n_counted})")
        print(f"  excluded: no-ball-track={n_no_ball}, no-pitch={n_no_pitch}, aerial={n_aerial}, "
              f"no-players={n_no_players}, ball-too-far={n_far}")

        # Persist
        out_dir = Path(args.ball_track_dir, seq)
        (out_dir / "possession.json").write_text(json.dumps({
            "teamA_pct": teamA_pct, "teamB_pct": teamB_pct,
            "n_counted": n_counted, "n_total": len(ball_traj),
            "excluded": {"no_ball_track": n_no_ball, "no_pitch": n_no_pitch,
                         "aerial": n_aerial, "no_players": n_no_players, "ball_too_far": n_far},
            "per_frame": per_frame,
        }, indent=2))

        # Timeline render
        render_possession_timeline(seq, per_frame, len(ball_traj), out_dir / "possession_timeline.png")
        summary[seq] = {"TeamA": teamA_pct, "TeamB": teamB_pct, "n_counted": n_counted}

    if len(summary) > 1:
        print(f"\n=== combined possession across {len(summary)} seqs ===")
        for s, v in summary.items():
            print(f"  {s}: A={v['TeamA']:.1f}%  B={v['TeamB']:.1f}%  (n={v['n_counted']})")

if __name__ == "__main__":
    main()
