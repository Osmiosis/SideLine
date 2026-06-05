"""Day 27 PART B: cut per-player INVOLVEMENT clips from the C-FEED (output #2, football).

Each involvement range (detect_involvement.py) + padding -> one short clip, cut from the
Day-13 follow-cam VARIANT C (player-stabilized -- the right feed for PLAYER-subject footage;
A-feed is ball-centric and wrong for "show me this kid"). Same crop math as the Day-13 renderer
(follow_cam._crop), so no pre-rendered mp4 needed -- we crop the wide source frames live.

Clips are grouped by source track id (drives Part C bulk-tagging) and tagged with timestamp +
involvement-strength (drives Part D ranking inside a player's reel).

FRAME-GATED: the SoccerNet source frames are large + gitignored and may be absent on this
machine. If so, this still writes the full clips_manifest.json (so Parts C/D are ready) and
skips the actual mp4 render with a clear notice -- re-run once frames are restored to
datasets/soccernet_tracking/test/<seq>/img1/.

Inputs:
  outputs/involvement/<seq>/involvement.json          per-track involvement ranges (Part A)
  outputs/follow_cam/<seq>/follow_cam.json            C-feed per-frame crop centres (Day-13)
  datasets/soccernet_tracking/test/<seq>/img1/*.jpg   source frames (may be absent)

Output:
  outputs/player_highlights/<seq>/clips/t<tid>_m<idx>_<sec>s.mp4   per-clip video (gitignored)
  outputs/player_highlights/<seq>/clips_manifest.json             clip records (committed-small)

Usage:
  .venv\\Scripts\\python scripts\\clip_player_highlights.py            # all seqs
  .venv\\Scripts\\python scripts\\clip_player_highlights.py SNGS-118   # one seq
  .venv\\Scripts\\python scripts\\clip_player_highlights.py --no-clips # manifest only (no render)
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent))
from follow_cam import _crop   # identical crop math as the Day-13 C-feed renderer
from video_io import to_browser_h264   # cv2 writes mp4v; browsers need H.264

FPS = 25
PAD_PRE = 50    # -2.0 s lead-in
PAD_POST = 25   # +1.0 s follow-through


def load_centers(follow_json, variant="C"):
    d = json.loads(Path(follow_json).read_text())
    C = {e["frame"]: (e["cx"], e["cy"]) for e in d["variants"][variant]}
    return C, d["crop_w"], d["crop_h"], d.get("frame_w"), d.get("frame_h")


def render_clip(seq, tid, m, C, cw, ch, frames_dir, out_path, out_w, out_h, n_frames):
    s = max(1, m["start"] - PAD_PRE)
    e = min(n_frames, m["end"] + PAD_POST)
    vw = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (out_w, out_h))
    written = 0
    for f in range(s, e + 1):
        img = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
        if img is None:
            continue
        cx, cy = C.get(f, (img.shape[1] / 2, img.shape[0] / 2))
        out = cv2.resize(_crop(img, cx, cy, cw, ch), (out_w, out_h), interpolation=cv2.INTER_LINEAR)
        cv2.rectangle(out, (0, 0), (out_w, 34), (0, 0, 0), -1)
        cv2.putText(out, f"{seq}  track {tid}  involvement {m['start_sec']:.1f}s  "
                         f"str={m['strength']}", (8, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (40, 200, 255), 1, cv2.LINE_AA)
        vw.write(out); written += 1
    vw.release()
    if written:
        to_browser_h264(out_path)   # transcode mp4v -> H.264 so the UI can play it
    return written, s, e


def process_seq(seq, args, frames_present):
    inv = json.loads(Path(args.involvement_dir, seq, "involvement.json").read_text())
    C, cw, ch, fw, fh = load_centers(Path(args.follow_dir, seq, "follow_cam.json"))
    n_frames = max(C) if C else 750
    frames_dir = Path(args.source, seq, "img1")
    clip_dir = Path(args.out, seq, "clips")
    if args.clips and frames_present:
        clip_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    rendered = 0
    for trk in inv["tracks"]:
        tid = trk["track_id"]
        for idx, m in enumerate(trk["moments"]):
            clip_name = f"t{tid:03d}_m{idx:02d}_{m['start_sec']:.0f}s.mp4"
            rec = {
                "seq": seq, "track_id": tid, "role": trk["role"], "moment_idx": idx,
                "start_frame": max(1, m["start"] - PAD_PRE),
                "end_frame": min(n_frames, m["end"] + PAD_POST),
                "involve_start_sec": m["start_sec"], "involve_end_sec": m["end_sec"],
                "strength": m["strength"], "mean_closeness": m["mean_closeness"],
                "dur_frames": m["dur_frames"],
                "clip": f"outputs/player_highlights/{seq}/clips/{clip_name}",
                "rendered": False, "kind": "involvement",
            }
            if args.clips and frames_present:
                w, s, e = render_clip(seq, tid, m, C, cw, ch, frames_dir,
                                      clip_dir / clip_name, args.clip_w, args.clip_h, n_frames)
                rec["rendered"] = w > 0
                rec["frames_written"] = w
                rendered += 1
            manifest.append(rec)

    out_seq = Path(args.out, seq); out_seq.mkdir(parents=True, exist_ok=True)
    (out_seq / "clips_manifest.json").write_text(json.dumps(
        {"seq": seq, "n_clips": len(manifest), "rendered": rendered,
         "frames_present": frames_present, "pad_pre": PAD_PRE, "pad_post": PAD_POST,
         "feed": "C (player-stabilized)", "clips": manifest}, indent=2))
    return len(manifest), rendered


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="?", default=None)
    ap.add_argument("--involvement-dir", default="outputs/involvement")
    ap.add_argument("--follow-dir", default="outputs/follow_cam")
    ap.add_argument("--source", default="datasets/soccernet_tracking")
    ap.add_argument("--out", default="outputs/player_highlights")
    ap.add_argument("--clip-w", type=int, default=854)
    ap.add_argument("--clip-h", type=int, default=480)
    ap.add_argument("--no-clips", dest="clips", action="store_false", default=True)
    args = ap.parse_args()

    seqs = [args.seq] if args.seq else \
        ["SNGS-116", "SNGS-117", "SNGS-118", "SNGS-119", "SNGS-120"]
    Path(args.out).mkdir(parents=True, exist_ok=True)

    for seq in seqs:
        fd = Path(args.source, seq, "img1")
        frames_present = fd.is_dir() and any(fd.glob("*.jpg"))
        n, rendered = process_seq(seq, args, frames_present)
        note = f"{rendered} clips rendered" if frames_present else \
            "FRAMES ABSENT -> manifest only (re-run when frames restored)"
        print(f"  {seq}: {n} involvement clips queued  | {note}")
    print(f"\n  manifests -> {args.out}/<seq>/clips_manifest.json")
    print("  (C-feed = player-stabilized; clips are per-track, tag in Part C)")


if __name__ == "__main__":
    main()
