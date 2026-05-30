"""Day 28 PART C+D: presence fallback + assemble per-player reels + VERIFY INCLUSIVITY (basketball).

Three jobs (basketball half-court parity with football Day-27):

1. PRESENCE-CLIP FALLBACK (the inclusivity guarantee -- HEAVIER on basketball):
   the gap involvement definition (detect_involvement_bb.py) concentrates on ball-handlers, so most
   on-court players get NO involvement clip. Every SUBSTANTIAL outfield track with zero involvement
   gets its longest contiguous visible stretch CLIPPED from the C-feed (centred, capped to keep reels
   watchable). Unlike football (which only DEFINED the presence stretch), basketball actually RENDERS
   it -- because here presence is the majority of coverage, not a tail.

2. VERIFY INCLUSIVITY (data-only -- the GOAL CHECK): every substantial outfield track must get
   footage (involvement clip OR rendered presence clip) -> target 100% by construction.

3. ASSEMBLE reels (FRAME-GATED): group clips by user tag (clip_tags.json from Part C tagging) or by
   track id (draft), rank involvement-strength first then presence, concat with a title card.

C-FEED SCOPE: the cleaned player-stabilized C-feed (Day-15/16 head-FP work) exists only for c001 and
c007. Those are the clippable/renderable deliverable seqs (100% inclusivity, rendered). c003/c005/c008
have involvement MEASURED (Part A) but no cleaned C-feed -> clipping pending; reported transparently.

Inputs:
  outputs/involvement_bb/<seq>/involvement.json            Part A
  outputs/player_highlights_bb/<seq>/clips_manifest.json   Part B (involvement clips)
  outputs/track_results/bb_ftdet_botsort_gmc/<seq>.txt     for presence stretches
  outputs/team_assign_bb/track_teams_bb.json               roles
  outputs/follow_cam_bb/<seq>/follow_cam.json + frames     C-feed render (C-feed seqs only)

Output:
  outputs/player_highlights_bb/<seq>/clips/p<tid>_presence.mp4   presence clips (gitignored)
  outputs/player_highlights_bb/<seq>/clips_manifest.json         updated (involve + presence)
  outputs/player_highlights_bb/<seq>/inclusivity_report.json     goal check
  outputs/deliverables/player_highlights_basketball/             package (md, summary, dists, reel)

Usage:
  .venv\\Scripts\\python scripts\\assemble_player_reels_bb.py             # report + presence + reels
  .venv\\Scripts\\python scripts\\assemble_player_reels_bb.py --no-render  # report only (no clips/reels)
"""
import argparse, json, sys, shutil
from collections import defaultdict
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent))
from follow_cam import _crop
from detect_involvement_bb import (load_tracks, MIN_TRACK_FRAMES, OUTFIELD_ROLES,
                                    MERGE_GAP_FRAMES, SEQS_DEFAULT)

FPS = 25
PRESENCE_MAX_FRAMES = 125   # cap a presence clip at ~5 s (centred on the longest visible stretch)
PRESENCE_MIN_FRAMES = 25    # need ~1 s of contiguous visibility to be worth a clip


def longest_visible_stretch(frames):
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


def cap_stretch(stretch):
    """centre a long visible stretch and cap to PRESENCE_MAX_FRAMES."""
    s, e = stretch
    if e - s + 1 <= PRESENCE_MAX_FRAMES:
        return s, e
    mid = (s + e) // 2
    half = PRESENCE_MAX_FRAMES // 2
    return mid - half, mid + half


def cfeed(seq, args):
    p = Path(args.follow_dir, seq, "follow_cam.json")
    if not p.is_file():
        return None
    d = json.loads(p.read_text())
    C = {ev["frame"]: (ev["cx"], ev["cy"]) for ev in d["variants"]["C"]}
    return C, d["crop_w"], d["crop_h"]


def render_presence_clip(seq, tid, s, e, C, cw, ch, frames_dir, out_path):
    vw = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (cw, ch))
    written = 0
    for f in range(s, e + 1):
        img = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
        if img is None:
            continue
        cx, cy = C.get(f, (img.shape[1] / 2, img.shape[0] / 2))
        out = _crop(img, cx, cy, cw, ch)
        cv2.rectangle(out, (0, 0), (cw, 30), (0, 0, 0), -1)
        cv2.putText(out, f"{seq[-4:]}  track {tid}  PRESENCE (on court)", (8, 21),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 220, 120), 1, cv2.LINE_AA)
        vw.write(out); written += 1
    vw.release()
    return written


def process_seq(seq, args):
    inv = json.loads(Path(args.involvement_dir, seq, "involvement.json").read_text())
    teams = json.loads(Path(args.team_file).read_text()).get(seq, {})
    role_for_tid = {int(k): v["role"] for k, v in teams.items()}
    by_frame, track_frames = load_tracks(Path(args.tracker_dir, f"{seq}.txt"))
    track_frame_list = defaultdict(list)
    for f, players in by_frame.items():
        for (tid, *_rest) in players:
            track_frame_list[tid].append(f)

    moments_per_track = {t["track_id"]: t["n_moments"] for t in inv["tracks"]}
    substantial = sorted(tid for tid, n in track_frames.items()
                         if n >= MIN_TRACK_FRAMES and role_for_tid.get(tid) in OUTFIELD_ROLES)

    cf = cfeed(seq, args)
    frames_dir = Path(args.source, seq, "img1")
    frames_present = frames_dir.is_dir() and any(frames_dir.glob("*.jpg"))
    can_render = cf is not None and frames_present and args.render

    # load involvement manifest (Part B); presence clips get appended
    man_path = Path(args.clips_dir, seq, "clips_manifest.json")
    manifest = json.loads(man_path.read_text())["clips"] if man_path.exists() else []
    manifest = [m for m in manifest if m.get("kind") != "presence"]   # rebuild presence fresh
    clip_dir = Path(args.clips_dir, seq, "clips")
    if can_render:
        clip_dir.mkdir(parents=True, exist_ok=True)

    players, n_presence_rendered = [], 0
    for tid in substantial:
        n_mom = moments_per_track.get(tid, 0)
        rec = {"track_id": tid, "role": role_for_tid.get(tid),
               "track_len_frames": track_frames[tid], "n_involvement_clips": n_mom,
               "via": "involvement" if n_mom > 0 else "presence", "presence_clip": None}
        if n_mom == 0:
            stretch = longest_visible_stretch(track_frame_list[tid])
            if stretch and (stretch[1] - stretch[0] + 1) >= PRESENCE_MIN_FRAMES:
                s, e = cap_stretch(stretch)
                rec["presence_stretch"] = {"start_frame": s, "end_frame": e,
                                           "dur_sec": round((e - s + 1) / FPS, 2)}
                clip_name = f"p{tid:03d}_presence.mp4"
                pclip = {"seq": seq, "track_id": tid, "role": rec["role"], "moment_idx": 0,
                         "start_frame": s, "end_frame": e, "involve_start_sec": round((s - 1) / FPS, 2),
                         "involve_end_sec": round((e - 1) / FPS, 2), "strength": 0.0,
                         "mean_closeness": 0.0, "dur_frames": e - s + 1,
                         "clip": f"outputs/player_highlights_bb/{seq}/clips/{clip_name}",
                         "rendered": False, "kind": "presence"}
                if can_render:
                    w = render_presence_clip(seq, tid, s, e, cf[0], cf[1], cf[2],
                                             frames_dir, clip_dir / clip_name)
                    pclip["rendered"] = w > 0
                    pclip["frames_written"] = w
                    n_presence_rendered += 1
                    rec["presence_clip"] = pclip["clip"]
                manifest.append(pclip)
            else:
                rec["reason_no_footage"] = "no contiguous visible stretch >= 1 s"
        players.append(rec)

    covered = sum(1 for p in players if p["n_involvement_clips"] > 0 or p.get("presence_stretch"))
    clip_counts = [p["n_involvement_clips"] + (1 if p.get("presence_stretch") else 0) for p in players]
    report = {
        "seq": seq, "has_cleaned_cfeed": cf is not None,
        "n_substantial_players": len(players),
        "covered_with_footage": covered,
        "covered_pct": round(100 * covered / max(1, len(players)), 1),
        "via_involvement": sum(1 for p in players if p["n_involvement_clips"] > 0),
        "via_presence_fallback": sum(1 for p in players if p["via"] == "presence" and p.get("presence_stretch")),
        "presence_clips_rendered": n_presence_rendered,
        "clips_per_player": {"min": int(min(clip_counts)) if clip_counts else 0,
                             "median": int(np.median(clip_counts)) if clip_counts else 0,
                             "max": int(max(clip_counts)) if clip_counts else 0},
        "players": players,
    }
    Path(args.clips_dir, seq).mkdir(parents=True, exist_ok=True)
    Path(args.clips_dir, seq, "inclusivity_report.json").write_text(json.dumps(report, indent=2))
    if can_render or man_path.exists():
        man_path.write_text(json.dumps(
            {"seq": seq, "n_clips": len(manifest), "feed": "C (player-stabilized)",
             "kinds": {"involvement": sum(1 for m in manifest if m["kind"] == "involvement"),
                       "presence": sum(1 for m in manifest if m["kind"] == "presence")},
             "clips": manifest}, indent=2))
    return report, manifest, cf


def assemble_reels(seq, args, manifest, cf):
    if cf is None:
        return 0, None
    frames_dir = Path(args.source, seq, "img1")
    if not (frames_dir.is_dir() and any(frames_dir.glob("*.jpg"))):
        return 0, None
    C, cw, ch = cf
    tags_path = Path(args.clips_dir, seq, "clip_tags.json")
    tags = json.loads(tags_path.read_text()) if tags_path.exists() else {}
    tags = {k: v for k, v in tags.items() if not k.startswith("__")}

    groups = defaultdict(list)
    for rec in manifest:
        name = tags.get(Path(rec["clip"]).name)
        if name == "__skip__":
            continue
        if name is None:
            name = f"track_{rec['track_id']:03d}"
        groups[name].append(rec)

    out_w, out_h = cw, ch   # native C crop (640x360)
    reel_dir = Path(args.clips_dir, seq, "reels"); reel_dir.mkdir(parents=True, exist_ok=True)

    def render_reel(name, recs, out_path, ow, oh):
        # involvement first (by strength), then presence
        recs = sorted(recs, key=lambda r: (r["kind"] != "involvement", -r["strength"]))
        vw = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (ow, oh))
        title = np.zeros((oh, ow, 3), np.uint8)
        cv2.putText(title, name, (30, oh // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3, cv2.LINE_AA)
        n_inv = sum(1 for r in recs if r["kind"] == "involvement")
        cv2.putText(title, f"{len(recs)} clips ({n_inv} involvement + {len(recs)-n_inv} presence) - {seq[-4:]}",
                    (30, oh // 2 + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1, cv2.LINE_AA)
        for _ in range(int(FPS * 1.2)):
            vw.write(title)
        for rec in recs:
            tag = "PRESENCE" if rec["kind"] == "presence" else f"{rec['involve_start_sec']:.1f}s"
            for f in range(rec["start_frame"], rec["end_frame"] + 1):
                img = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
                if img is None:
                    continue
                cx, cy = C.get(f, (img.shape[1] / 2, img.shape[0] / 2))
                out = cv2.resize(_crop(img, cx, cy, cw, ch), (ow, oh))
                cv2.rectangle(out, (0, 0), (ow, 30), (0, 0, 0), -1)
                cv2.putText(out, f"{name}  ({tag})", (8, 21), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (40, 200, 255), 1, cv2.LINE_AA)
                vw.write(out)
            for _ in range(6):
                vw.write(np.zeros((oh, ow, 3), np.uint8))
        vw.release()

    n_reels, best = 0, None
    for name, recs in groups.items():
        render_reel(name, recs, reel_dir / f"{name}.mp4", out_w, out_h)
        n_reels += 1
        if best is None or len(recs) > best[0]:
            best = (len(recs), seq, name, recs, render_reel)
    return n_reels, best


def write_rollup_md(reports, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    cfeed_seqs = [r for r in reports if r["has_cleaned_cfeed"]]
    L = ["# Inclusive Player Highlights - basketball (output #2, SportsMOT proxy for DPS)", "",
         "**Parity with football (Day-27).** Same mechanism -- per-player reels, human tag-per-clip,",
         "presence fallback -- but involvement was RE-DERIVED for the half-court (see below).", "",
         "**Why a fixed radius fails in basketball:** football involvement = nearest player within ~2.5 m.",
         "On a half-court all players cluster near the ball; a fixed radius marks ~1.5 players/frame and",
         "74% of all players involved -> no discrimination. The chosen `gap` definition (nearest AND clearly",
         "closer than the 2nd-nearest) concentrates 96% of involvement on the top-3 ball-handlers, so",
         "involvement means ball-handler -- and the presence fallback (heavier here than football) covers",
         "everyone else.", "",
         "**Identity = human tag-per-clip** (identical house kits -> auto-ID impossible, Day-26).", "",
         "**Coverage = involvement clips + RENDERED presence clips** (basketball renders presence, not just",
         "defines it -- it's the majority of coverage here).", "",
         "## Clippable deliverable (cleaned C-feed available: c001, c007)", "",
         "| seq | substantial | covered | via involvement | via presence | clips/player (min/med/max) |",
         "|-----|-------------|---------|-----------------|--------------|----------------------------|"]
    tp = tc = 0
    for r in cfeed_seqs:
        cp = r["clips_per_player"]
        L.append(f"| {r['seq'][-4:]} | {r['n_substantial_players']} | {r['covered_with_footage']} "
                 f"({r['covered_pct']}%) | {r['via_involvement']} | {r['via_presence_fallback']} | "
                 f"{cp['min']}/{cp['median']}/{cp['max']} |")
        tp += r["n_substantial_players"]; tc += r["covered_with_footage"]
    L += ["", f"**Total (C-feed seqs): {tc}/{tp} substantial players get footage "
          f"({100*tc/max(1,tp):.1f}%)** -- involvement for ball-handlers, presence clips for the rest.", ""]
    other = [r for r in reports if not r["has_cleaned_cfeed"]]
    if other:
        L += ["## Involvement measured, clipping pending (no cleaned C-feed: c003, c005, c008)", "",
              "The Day-15/16 follow-cam head-FP cleaning produced a player-stabilized C-feed only for c001/c007.",
              "These seqs have involvement MEASURED (Part A) but no cleaned feed to clip from:", "",
              "| seq | substantial | would-be via involvement |",
              "|-----|-------------|--------------------------|"]
        for r in other:
            L.append(f"| {r['seq'][-4:]} | {r['n_substantial_players']} | {r['via_involvement']} |")
        L.append("")
    L += ["## Honest caveats",
          "- involvement leans on the plausibility-level basketball ball track (Day-19, noisier than",
          "  football's RMSE-validated) -> more presence reliance, by design.",
          "- nearest-player proxy, NOT exact per-touch; lost-ball frames excluded (confident ball only).",
          "- height-normalized radius re-tuned for basketball; re-tune at the DPS camera mount.",
          "- house-kit ID-switch means one player may span several track ids -> tag-per-clip re-unites them.",
          "- SportsMOT proxy validates METHOD; real target = DPS.", ""]
    Path(path).write_text("\n".join(L), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="?", default=None)
    ap.add_argument("--involvement-dir", default="outputs/involvement_bb")
    ap.add_argument("--clips-dir", default="outputs/player_highlights_bb")
    ap.add_argument("--tracker-dir", default="outputs/track_results/bb_ftdet_botsort_gmc")
    ap.add_argument("--team-file", default="outputs/team_assign_bb/track_teams_bb.json")
    ap.add_argument("--follow-dir", default="outputs/follow_cam_bb")
    ap.add_argument("--source", default="datasets/sportsmot_basketball")
    ap.add_argument("--out", default="outputs/deliverables/player_highlights_basketball")
    ap.add_argument("--no-render", dest="render", action="store_false", default=True)
    args = ap.parse_args()

    seqs = [args.seq] if args.seq else SEQS_DEFAULT
    out_root = Path(args.out); out_root.mkdir(parents=True, exist_ok=True)
    reports, global_best = [], None
    for seq in seqs:
        rep, manifest, cf = process_seq(seq, args)
        reports.append(rep)
        n_reels = 0
        if args.render and cf is not None:
            n_reels, best = assemble_reels(seq, args, manifest, cf)
            if best and (global_best is None or best[0] > global_best[0]):
                global_best = best
        cp = rep["clips_per_player"]
        feed = "C-feed" if rep["has_cleaned_cfeed"] else "NO C-feed"
        print(f"  {seq[-4:]} [{feed}]: {rep['covered_with_footage']}/{rep['n_substantial_players']} covered "
              f"({rep['covered_pct']}%)  involve={rep['via_involvement']} presence={rep['via_presence_fallback']} "
              f"(rendered {rep['presence_clips_rendered']})  reels={n_reels}")
        dist = Path(args.involvement_dir, seq, "distribution.png")
        if dist.exists():
            shutil.copy(dist, out_root / f"distribution_{seq[-4:]}.png")

    write_rollup_md(reports, out_root / "inclusivity.md")
    (out_root / "inclusivity_summary.json").write_text(json.dumps(
        {r["seq"]: {k: r[k] for k in ("has_cleaned_cfeed", "n_substantial_players",
         "covered_with_footage", "covered_pct", "via_involvement", "via_presence_fallback",
         "presence_clips_rendered", "clips_per_player")} for r in reports}, indent=2))
    if global_best:
        _, bseq, bname, brecs, render_reel = global_best
        render_reel(bname, brecs, out_root / "sample_reel.mp4", 640, 360)
        print(f"  sample_reel.mp4 -> {bseq[-4:]} {bname} ({len(brecs)} clips, 640x360, committed)")

    cfeed_reports = [r for r in reports if r["has_cleaned_cfeed"]]
    tp = sum(r["n_substantial_players"] for r in cfeed_reports)
    tc = sum(r["covered_with_footage"] for r in cfeed_reports)
    print(f"\n  INCLUSIVITY (C-feed seqs c001/c007): {tc}/{tp} substantial players get footage "
          f"({100*tc/max(1,tp):.1f}%)")
    print(f"  package -> {out_root}")


if __name__ == "__main__":
    main()
