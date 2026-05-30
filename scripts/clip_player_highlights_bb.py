"""Day 28 PART B: cut per-player INVOLVEMENT clips from the BASKETBALL C-FEED (output #2).

Reuses the Day-27 mechanism: each involvement range (detect_involvement_bb.py, gap mode) + padding
-> one short clip, cropped LIVE from the wide source frames using the Day-15/16 follow-cam VARIANT C
(player-stabilized -- the right feed for "show me this kid"; the A-feed is ball-centric and wrong
for player-subject footage). Same crop math as the follow-cam renderer (follow_cam._crop), so no
pre-rendered mp4 is needed.

BASKETBALL SCOPE: the cleaned C-feed (follow_cam.json) exists only for c001 and c007 (Day-15/16
follow-cam work). Seqs without a C-feed are skipped with a clear notice -- involvement was still
measured for them (Part A) but they have no player-stabilized feed to clip from.

The C crop is 640x360 from a 1280x720 source, so clips render at native 640x360 (no upscale).

Inputs:
  outputs/involvement_bb/<seq>/involvement.json            per-track involvement ranges (Part A)
  outputs/follow_cam_bb/<seq>/follow_cam.json              C-feed per-frame crop centres (Day-15/16)
  datasets/sportsmot_basketball/<seq>/img1/*.jpg           source frames

Output:
  outputs/player_highlights_bb/<seq>/clips/t<tid>_m<idx>_<sec>s.mp4   per-clip video (gitignored)
  outputs/player_highlights_bb/<seq>/clips_manifest.json             clip records (committed-small)

Usage:
  .venv\\Scripts\\python scripts\\clip_player_highlights_bb.py            # all C-feed seqs
  .venv\\Scripts\\python scripts\\clip_player_highlights_bb.py v_00HRwkvvjtQ_c001
  .venv\\Scripts\\python scripts\\clip_player_highlights_bb.py --no-clips # manifest only
"""
import argparse, json, sys
from pathlib import Path
import cv2

sys.path.insert(0, str(Path(__file__).parent))
from follow_cam import _crop   # identical crop math as the Day-15/16 C-feed renderer

SEQS_DEFAULT = ["v_00HRwkvvjtQ_c001", "v_00HRwkvvjtQ_c003", "v_00HRwkvvjtQ_c005",
                "v_00HRwkvvjtQ_c007", "v_00HRwkvvjtQ_c008"]
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
        cv2.rectangle(out, (0, 0), (out_w, 30), (0, 0, 0), -1)
        cv2.putText(out, f"{seq[-4:]}  track {tid}  involvement {m['start_sec']:.1f}s  str={m['strength']}",
                    (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 200, 255), 1, cv2.LINE_AA)
        vw.write(out); written += 1
    vw.release()
    return written, s, e


def process_seq(seq, args, frames_present, follow_json):
    inv = json.loads(Path(args.involvement_dir, seq, "involvement.json").read_text())
    C, cw, ch, fw, fh = load_centers(follow_json)
    n_frames = max(C) if C else 750
    out_w = args.clip_w or cw          # default = native C crop (640x360)
    out_h = args.clip_h or ch
    frames_dir = Path(args.source, seq, "img1")
    clip_dir = Path(args.out, seq, "clips")
    if args.clips and frames_present:
        clip_dir.mkdir(parents=True, exist_ok=True)

    manifest, rendered = [], 0
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
                "clip": f"outputs/player_highlights_bb/{seq}/clips/{clip_name}",
                "rendered": False, "kind": "involvement",
            }
            if args.clips and frames_present:
                w, s, e = render_clip(seq, tid, m, C, cw, ch, frames_dir,
                                      clip_dir / clip_name, out_w, out_h, n_frames)
                rec["rendered"] = w > 0
                rec["frames_written"] = w
                rendered += 1
            manifest.append(rec)

    out_seq = Path(args.out, seq); out_seq.mkdir(parents=True, exist_ok=True)
    (out_seq / "clips_manifest.json").write_text(json.dumps(
        {"seq": seq, "n_clips": len(manifest), "rendered": rendered,
         "frames_present": frames_present, "pad_pre": PAD_PRE, "pad_post": PAD_POST,
         "feed": "C (player-stabilized)", "clip_wh": [out_w, out_h], "clips": manifest}, indent=2))
    return len(manifest), rendered


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="?", default=None)
    ap.add_argument("--involvement-dir", default="outputs/involvement_bb")
    ap.add_argument("--follow-dir", default="outputs/follow_cam_bb")
    ap.add_argument("--source", default="datasets/sportsmot_basketball")
    ap.add_argument("--out", default="outputs/player_highlights_bb")
    ap.add_argument("--clip-w", type=int, default=None, help="default = native C crop width")
    ap.add_argument("--clip-h", type=int, default=None)
    ap.add_argument("--no-clips", dest="clips", action="store_false", default=True)
    args = ap.parse_args()

    seqs = [args.seq] if args.seq else SEQS_DEFAULT
    Path(args.out).mkdir(parents=True, exist_ok=True)
    skipped = []
    for seq in seqs:
        follow_json = Path(args.follow_dir, seq, "follow_cam.json")
        if not follow_json.is_file():
            skipped.append(seq)
            print(f"  {seq}: NO C-feed (follow_cam.json absent) -> skipped (no player-stabilized feed)")
            continue
        fd = Path(args.source, seq, "img1")
        frames_present = fd.is_dir() and any(fd.glob("*.jpg"))
        n, rendered = process_seq(seq, args, frames_present, follow_json)
        note = f"{rendered} clips rendered" if frames_present else \
            "FRAMES ABSENT -> manifest only"
        print(f"  {seq}: {n} involvement clips queued  | {note}")
    print(f"\n  manifests -> {args.out}/<seq>/clips_manifest.json")
    if skipped:
        print(f"  C-feed unavailable (clipping skipped): {', '.join(s[-4:] for s in skipped)}")


if __name__ == "__main__":
    main()
