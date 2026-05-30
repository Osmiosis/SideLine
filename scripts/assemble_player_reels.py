"""Day 27 PART D: assemble per-player reels + VERIFY INCLUSIVITY (output #2, football).

Two jobs:

1. VERIFY INCLUSIVITY (data-only -- runs WITHOUT frames; this is the GOAL CHECK):
   list every SUBSTANTIAL outfield track (on court long enough to be a real player) and confirm
   each gets footage. Involvement detection (Part A) covers players who got near the ball; the
   honest gap is players who were on court but NEVER near a confident ball (deep defenders, GK,
   brief fragments). For TRUE inclusivity ("every kid seen" -- the DPS value + VEO differentiator)
   those get a PRESENCE-CLIP FALLBACK: their longest contiguous visible stretch is clipped so they
   still appear in the reel set. Reports min/median/max clips per player + who needed a fallback.

2. ASSEMBLE reels (FRAME-GATED -- needs source frames): group clips by the user's tag
   (clip_tags.json from Part C), rank by involvement-strength (best first), concat with a per-reel
   title card. With no tags yet, falls back to per-TRACK draft reels (track id as a stand-in name)
   so the pipeline is runnable end-to-end before tagging.

Inputs:
  outputs/involvement/<seq>/involvement.json            Part A
  outputs/player_highlights/<seq>/clips_manifest.json   Part B
  outputs/player_highlights/<seq>/clip_tags.json        Part C (optional)
  outputs/track_results/sn_soccana_botsort_gmc/<seq>.txt  for presence-fallback stretches
  outputs/follow_cam/<seq>/follow_cam.json + source frames  for the actual render (optional)

Output:
  outputs/player_highlights/<seq>/inclusivity_report.json   the goal check (committed-small)
  outputs/deliverables/player_highlights_football/inclusivity.md   human-readable rollup
  outputs/player_highlights/<seq>/reels/<name>.mp4          per-player reel (gitignored)

Usage:
  .venv\\Scripts\\python scripts\\assemble_player_reels.py            # all seqs (report + reels if frames)
  .venv\\Scripts\\python scripts\\assemble_player_reels.py --no-render # report only
"""
import argparse, json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent))
from follow_cam import _crop
from detect_involvement import load_tracks, MIN_TRACK_FRAMES, OUTFIELD_ROLES, MERGE_GAP_FRAMES

FPS = 25


def longest_visible_stretch(frames):
    """sorted track frames -> [start, end] of the longest near-contiguous run (presence clip)."""
    if not frames:
        return None
    frames = sorted(frames)
    best = cur = [frames[0], frames[0]]
    for f in frames[1:]:
        if f - cur[1] <= MERGE_GAP_FRAMES:
            cur[1] = f
        else:
            if cur[1] - cur[0] > best[1] - best[0]:
                best = cur
            cur = [f, f]
    if cur[1] - cur[0] > best[1] - best[0]:
        best = cur
    return best


def verify_inclusivity(seq, args):
    inv = json.loads(Path(args.involvement_dir, seq, "involvement.json").read_text())
    teams = json.loads(Path(args.team_file).read_text()).get(seq, {})
    role_for_tid = {int(k): v["role"] for k, v in teams.items()}
    by_frame, track_frames = load_tracks(Path(args.tracker_dir, f"{seq}.txt"))
    track_frame_list = defaultdict(list)
    for f, players in by_frame.items():
        for (tid, *_rest) in players:
            track_frame_list[tid].append(f)

    moments_per_track = {t["track_id"]: t["n_moments"] for t in inv["tracks"]}
    substantial = [tid for tid, n in track_frames.items()
                   if n >= MIN_TRACK_FRAMES and role_for_tid.get(tid) in OUTFIELD_ROLES]

    players = []
    fallbacks = []
    for tid in sorted(substantial):
        n_mom = moments_per_track.get(tid, 0)
        rec = {"track_id": tid, "role": role_for_tid.get(tid),
               "track_len_frames": track_frames[tid], "n_involvement_clips": n_mom}
        if n_mom == 0:
            stretch = longest_visible_stretch(track_frame_list[tid])
            rec["presence_fallback"] = {
                "start_frame": stretch[0], "end_frame": stretch[1],
                "dur_sec": round((stretch[1] - stretch[0] + 1) / FPS, 2)} if stretch else None
            rec["reason_no_involvement"] = "on court but never within on-ball radius of a confident ball"
            fallbacks.append(rec)
        players.append(rec)

    clip_counts = [p["n_involvement_clips"] for p in players]
    covered = sum(1 for p in players if p["n_involvement_clips"] > 0 or p.get("presence_fallback"))
    report = {
        "seq": seq,
        "n_substantial_players": len(players),
        "covered_with_footage": covered,
        "covered_pct": round(100 * covered / max(1, len(players)), 1),
        "via_involvement": sum(1 for p in players if p["n_involvement_clips"] > 0),
        "via_presence_fallback": len(fallbacks),
        "clips_per_player": {
            "min": int(min(clip_counts)) if clip_counts else 0,
            "median": int(np.median(clip_counts)) if clip_counts else 0,
            "max": int(max(clip_counts)) if clip_counts else 0},
        "players": players,
    }
    Path(args.clips_dir, seq).mkdir(parents=True, exist_ok=True)
    Path(args.clips_dir, seq, "inclusivity_report.json").write_text(json.dumps(report, indent=2))
    return report


def assemble_reels(seq, args, frames_present):
    """group clips by user tag (or track id), rank by strength, concat with title card."""
    if not frames_present:
        return 0
    man = json.loads(Path(args.clips_dir, seq, "clips_manifest.json").read_text())
    tags_path = Path(args.clips_dir, seq, "clip_tags.json")
    tags = json.loads(tags_path.read_text()) if tags_path.exists() else {}
    tags = {k: v for k, v in tags.items() if not k.startswith("__")}

    groups = defaultdict(list)
    for rec in man["clips"]:
        name = tags.get(Path(rec["clip"]).name)
        if name == "__skip__":
            continue
        if name is None:                       # untagged -> per-track draft
            name = f"track_{rec['track_id']:03d}"
        groups[name].append(rec)

    d = json.loads(Path(args.follow_dir, seq, "follow_cam.json").read_text())
    C = {e["frame"]: (e["cx"], e["cy"]) for e in d["variants"]["C"]}
    cw, ch = d["crop_w"], d["crop_h"]
    frames_dir = Path(args.source, seq, "img1")
    out_w, out_h = 854, 480
    reel_dir = Path(args.clips_dir, seq, "reels"); reel_dir.mkdir(parents=True, exist_ok=True)

    n_reels = 0
    for name, recs in groups.items():
        recs.sort(key=lambda r: -r["strength"])     # best involvement first
        vw = cv2.VideoWriter(str(reel_dir / f"{name}.mp4"),
                             cv2.VideoWriter_fourcc(*"mp4v"), FPS, (out_w, out_h))
        title = np.zeros((out_h, out_w, 3), np.uint8)
        cv2.putText(title, name, (40, out_h // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.6,
                    (255, 255, 255), 3, cv2.LINE_AA)
        cv2.putText(title, f"{len(recs)} clips - player highlights ({seq})",
                    (40, out_h // 2 + 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 1, cv2.LINE_AA)
        for _ in range(int(FPS * 1.2)):
            vw.write(title)
        for rec in recs:
            for f in range(rec["start_frame"], rec["end_frame"] + 1):
                img = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
                if img is None:
                    continue
                cx, cy = C.get(f, (img.shape[1] / 2, img.shape[0] / 2))
                out = cv2.resize(_crop(img, cx, cy, cw, ch), (out_w, out_h))
                cv2.rectangle(out, (0, 0), (out_w, 30), (0, 0, 0), -1)
                cv2.putText(out, f"{name}  ({rec['involve_start_sec']:.1f}s)", (8, 21),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (40, 200, 255), 1, cv2.LINE_AA)
                vw.write(out)
            for _ in range(6):
                vw.write(np.zeros((out_h, out_w, 3), np.uint8))
        vw.release(); n_reels += 1
    return n_reels


def write_rollup_md(reports, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Inclusive Player Highlights - football (output #2, SoccerNet proxy for DPS)", "",
             "**The inclusivity goal:** event highlights (output #3) surface only exciting moments",
             "-> stars get footage, quiet kids get nothing. Player highlights must include EVERYONE",
             "(the DPS value: every child seen; parents want THEIR kid -- a genuine differentiator",
             "vs VEO/Pixellot's star/ball focus).", "",
             "**Identity = human tag-per-clip**, NOT auto-ReID: identical house kits (no numbers/names)",
             "make auto-identity impossible (Day-26 ReID: AssA +0.004). Each short clip = one visible",
             "person -> the user names it unambiguously.", "",
             "**Coverage = involvement clips + presence-clip fallback** for on-court players who were",
             "never near a confident ball (deep defenders / GK / brief fragments), so nobody is left out.", "",
             "| seq | substantial players | covered | via involvement | via presence-fallback | clips/player (min/med/max) |",
             "|-----|--------------------|---------|-----------------|----------------------|----------------------------|"]
    tot_p = tot_c = 0
    for r in reports:
        cp = r["clips_per_player"]
        lines.append(f"| {r['seq']} | {r['n_substantial_players']} | "
                     f"{r['covered_with_footage']} ({r['covered_pct']}%) | {r['via_involvement']} | "
                     f"{r['via_presence_fallback']} | {cp['min']}/{cp['median']}/{cp['max']} |")
        tot_p += r["n_substantial_players"]; tot_c += r["covered_with_footage"]
    lines += ["",
              f"**Total: {tot_c}/{tot_p} substantial outfield players get footage "
              f"({100*tot_c/max(1,tot_p):.1f}%)** "
              f"-- involvement clips for near-ball players, presence clips for the rest.", "",
              "Honest caveats: involvement = nearest-player proxy (plausibility-level near-ball, NOT",
              "exact per-touch); SoccerNet footage (DPS-pending); house-kit ID-switch means one player",
              "may span several track ids -> tag-per-clip re-unites them under one name; tagging is",
              "manual effort (one name per short clip, bulk-named per un-switched track).", ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="?", default=None)
    ap.add_argument("--involvement-dir", default="outputs/involvement")
    ap.add_argument("--clips-dir", default="outputs/player_highlights")
    ap.add_argument("--tracker-dir", default="outputs/track_results/sn_soccana_botsort_gmc")
    ap.add_argument("--team-file", default="outputs/team_assign/track_teams.json")
    ap.add_argument("--follow-dir", default="outputs/follow_cam")
    ap.add_argument("--source", default="datasets/soccernet_tracking/test")
    ap.add_argument("--out", default="outputs/deliverables/player_highlights_football")
    ap.add_argument("--no-render", dest="render", action="store_false", default=True)
    args = ap.parse_args()

    seqs = [args.seq] if args.seq else \
        ["SNGS-116", "SNGS-117", "SNGS-118", "SNGS-119", "SNGS-120"]
    reports = []
    for seq in seqs:
        rep = verify_inclusivity(seq, args)
        reports.append(rep)
        fd = Path(args.source, seq, "img1")
        frames_present = fd.is_dir() and any(fd.glob("*.jpg"))
        n_reels = assemble_reels(seq, args, frames_present) if args.render else 0
        cp = rep["clips_per_player"]
        rendered = f"{n_reels} reels rendered" if frames_present and args.render else \
            "reels NOT rendered (frames absent)"
        print(f"  {seq}: {rep['covered_with_footage']}/{rep['n_substantial_players']} players covered "
              f"({rep['covered_pct']}%)  [involve {rep['via_involvement']} + presence {rep['via_presence_fallback']}]  "
              f"clips/player {cp['min']}/{cp['median']}/{cp['max']}  | {rendered}")

    write_rollup_md(reports, Path(args.out, "inclusivity.md"))
    tot_p = sum(r["n_substantial_players"] for r in reports)
    tot_c = sum(r["covered_with_footage"] for r in reports)
    print(f"\n  INCLUSIVITY (all {len(seqs)} seqs): {tot_c}/{tot_p} substantial players get footage "
          f"({100*tot_c/max(1,tot_p):.1f}%)")
    print(f"  rollup -> {Path(args.out,'inclusivity.md')}")


if __name__ == "__main__":
    main()
