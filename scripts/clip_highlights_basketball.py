"""Day 25 (Part C/D): clip RANKED basketball highlight moments from the A-feed + package.

Reads the ranked candidate moments (detect_events_basketball.py) and cuts each from the
Day-15/16 basketball follow-cam VARIANT A (ball-faithful, head-FP-cleaned) by cropping the wide
SportsMOT frames with A's per-frame crop centers (same crop math as the follow-cam renderer).

Curation package, RANKED best-first (the shot-dense answer): the editor skims top-down,
made-baskets/blocks first, routine attempts last. The USER is the perceptual arbiter -- this
surfaces clips + contact sheets + ranked index; it does NOT self-declare quality.

Honest labels: likely_made_basket (NOT a confirmed score), block_proxy / steal_proxy (proxies),
shot_attempt, fast_break. Fouls are the AUDIO lever (not built), same as football.

Outputs:
  outputs/events_bb/<seq>/clips/<rank>_<type>.mp4                  per-moment clips (gitignored)
  outputs/deliverables/event_highlights_basketball/
    index.md / index.json        RANKED curation list (rank, interest, type, conf, timestamp)
    contact_<seq>.jpg            per-seq visual skim (rows in RANK order)
    sample_highlight.mp4         the #1 ranked moment (committed)
    auto_draft_reel.mp4          top-N ranked concatenated (gitignored)
    README.md

Usage:
  python scripts/clip_highlights_basketball.py
  python scripts/clip_highlights_basketball.py --no-clips    # index + sheets only
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent))
from follow_cam import _crop, bidir_smooth, interp_fill, clamp_centers

SEQS_DEFAULT = ["v_00HRwkvvjtQ_c007"]
FPS = 25
TYPE_COLOR = {  # BGR
    "likely_made_basket": (40, 220, 40), "fast_break": (240, 180, 40),
    "block_proxy": (40, 200, 255), "steal_proxy": (200, 120, 240), "shot_attempt": (180, 180, 180),
}


def load_A(follow_json):
    d = json.loads(Path(follow_json).read_text())
    return {e["frame"]: (e["cx"], e["cy"]) for e in d["variants"]["A"]}, d["crop_w"], d["crop_h"]


def build_ball_centers(traj, W, H, cw, ch, fps=25, cutoff=1.2, order=2):
    """STRICT ball-tracking crop path for highlight clips. Follow the Kalman ball every
    detected/predicted frame; interpolate LOST gaps linearly between real sightings (so the camera
    traverses to where the ball reappears -- e.g. launch -> rim during a shot, instead of holding on
    the shooter like the follow-cam's possession-handoff A-feed). Bidirectionally smoothed + clamped.
    This is what lets the viewer SEE the ball reach the hoop / make-or-miss."""
    n = len(traj)
    bx = np.full(n, np.nan); by = np.full(n, np.nan)
    for i, r in enumerate(traj):
        if r.get("x") is not None:          # detected OR predicted (lost -> NaN -> interpolated)
            bx[i] = r["x"]; by[i] = r["y"]
    bx = bidir_smooth(interp_fill(bx), cutoff, fps, order)
    by = bidir_smooth(interp_fill(by), cutoff, fps, order)
    bx, by = clamp_centers(bx, by, cw, ch, W, H)
    return {i + 1: (float(bx[i]), float(by[i])) for i in range(n)}


def tag(m):
    types = "+".join(t.replace("_", " ") for t in m["types"])
    return f"#{m['rank']} {types}  int={m['interest']} c={m['confidence']}  [{m['start_sec']:.1f}-{m['end_sec']:.1f}s]"


def render_clip(seq, m, A, cw, ch, frames_dir, out_path, out_w, out_h):
    vw = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (out_w, out_h))
    written = 0
    for i in range(m["start"], m["end"] + 1):
        f = i + 1
        img = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
        if img is None:
            continue
        cx, cy = A.get(f, (img.shape[1] / 2, img.shape[0] / 2))
        out = cv2.resize(_crop(img, cx, cy, cw, ch), (out_w, out_h), interpolation=cv2.INTER_LINEAR)
        cv2.rectangle(out, (0, 0), (out_w, 30), (0, 0, 0), -1)
        col = TYPE_COLOR.get(m["top_type"], (255, 255, 255))
        cv2.putText(out, f"{seq}  {tag(m)}", (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)
        vw.write(out); written += 1
    vw.release()
    return written


def contact_sheet(seq, moments, A, cw, ch, frames_dir, out_path, cols=5, tile_w=300):
    if not moments:
        return
    tile_h = int(round(tile_w * ch / cw)) + 22
    sheet = np.full((len(moments) * (tile_h + 6), cols * tile_w, 3), 30, np.uint8)
    for r, m in enumerate(moments):
        idxs = np.linspace(m["start"], m["end"], cols).astype(int)
        for c, i in enumerate(idxs):
            f = i + 1
            img = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
            if img is None:
                continue
            crop = cv2.resize(_crop(img, *A.get(f, (img.shape[1] / 2, img.shape[0] / 2)), cw, ch),
                              (tile_w, tile_h - 22))
            y0 = r * (tile_h + 6)
            sheet[y0 + 22:y0 + tile_h, c * tile_w:(c + 1) * tile_w] = crop
        cv2.putText(sheet, tag(m), (6, r * (tile_h + 6) + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    TYPE_COLOR.get(m["top_type"], (255, 255, 255)), 1, cv2.LINE_AA)
    cv2.imwrite(str(out_path), sheet, [cv2.IMWRITE_JPEG_QUALITY, 82])


def reel(picks, frames_root, out_path, out_w, out_h, gap=8):
    vw = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (out_w, out_h))
    nf = 0
    for (seq, m, A, cw, ch) in picks:
        frames_dir = Path(frames_root) / seq / "img1"
        for i in range(m["start"], m["end"] + 1):
            f = i + 1
            img = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
            if img is None:
                continue
            out = cv2.resize(_crop(img, *A.get(f, (img.shape[1] / 2, img.shape[0] / 2)), cw, ch),
                             (out_w, out_h), interpolation=cv2.INTER_LINEAR)
            cv2.rectangle(out, (0, 0), (out_w, 28), (0, 0, 0), -1)
            cv2.putText(out, f"AUTO-DRAFT (human-curate)  {tag(m)}", (8, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.46, (40, 220, 40), 1, cv2.LINE_AA)
            vw.write(out); nf += 1
        for _ in range(gap):
            vw.write(np.zeros((out_h, out_w, 3), np.uint8)); nf += 1
    vw.release()
    return nf


def write_index_md(index, path):
    lines = ["# Basketball Event Highlight Candidates - RANKED (output #3 parity)", "",
             "**Output #3, basketball half** (Student Council reel). HIGH-RECALL + **INTEREST-RANKED**:",
             "basketball is shot-dense, so the set is sorted best-first (made-baskets/blocks top, routine",
             "attempts bottom) -- the editor skims top-down and isn't drowned. Motion-only; AUDIO (whistle/",
             "crowd) is the documented next lever for fouls + made-basket confirmation.", "",
             "Honest labels: `likely_made_basket` (NOT a confirmed score - no net/height, plausibility-level",
             "ball track), `block_proxy` / `steal_proxy` (proxies), `shot_attempt`, `fast_break`. Hoop zone",
             "from the Day-21 manual court homography -> a DPS court-marking setup dependency. Thresholds",
             "camera-scale-dependent -> RE-TUNE at the DPS mount. **The USER is the perceptual arbiter.**", "",
             "| rank | interest | type(s) | conf | t (s) | clip |",
             "|------|----------|---------|------|-------|------|"]
    for r in sorted(index, key=lambda r: r["rank"]):
        lines.append(f"| {r['rank']} | {r['interest']} | {', '.join(r['types'])} | {r['confidence']} | "
                     f"{r['start_sec']:.1f}-{r['end_sec']:.1f} | `{Path(r['clip']).name}` |")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="?", default=None)
    ap.add_argument("--events-dir", default="outputs/events_bb")
    ap.add_argument("--follow-dir", default="outputs/follow_cam_bb")
    ap.add_argument("--source", default="datasets/sportsmot_basketball")
    ap.add_argument("--out", default="outputs/deliverables/event_highlights_basketball")
    ap.add_argument("--clip-w", type=int, default=854)
    ap.add_argument("--clip-h", type=int, default=480)
    ap.add_argument("--no-clips", dest="clips", action="store_false", default=True)
    ap.add_argument("--reel-top", type=int, default=8)
    ap.add_argument("--ball-dir", default="outputs/ball_track_bb")
    ap.add_argument("--crop", choices=["ball", "follow_A"], default="ball",
                    help="ball = strict ball-tracking crop (follows ball to the rim); "
                         "follow_A = the Day-15/16 possession-handoff A-feed (holds on shooter when ball lost)")
    args = ap.parse_args()

    seqs = [args.seq] if args.seq else SEQS_DEFAULT
    out_root = Path(args.out); out_root.mkdir(parents=True, exist_ok=True)
    index = []; reel_pool = []
    for seq in seqs:
        ev = json.loads((Path(args.events_dir) / seq / "events.json").read_text())
        moments = ev["ranked_moments"]
        fcj = json.loads((Path(args.follow_dir) / seq / "follow_cam.json").read_text())
        cw, ch = fcj["crop_w"], fcj["crop_h"]
        if args.crop == "ball":
            traj = json.loads((Path(args.ball_dir) / seq / "trajectory.json").read_text())
            A = build_ball_centers(traj, fcj["frame_w"], fcj["frame_h"], cw, ch, fps=FPS)
        else:
            A, cw, ch = load_A(Path(args.follow_dir) / seq / "follow_cam.json")
        frames_dir = Path(args.source) / seq / "img1"
        clip_dir = Path(args.events_dir) / seq / "clips"
        if args.clips:
            clip_dir.mkdir(parents=True, exist_ok=True)
        for m in moments:
            clip_name = f"{m['rank']:02d}_{m['top_type']}.mp4"
            rec = {"seq": seq, "rank": m["rank"], "interest": m["interest"], "types": m["types"],
                   "top_type": m["top_type"], "confidence": m["confidence"],
                   "start_sec": m["start_sec"], "end_sec": m["end_sec"],
                   "start_frame": m["start"] + 1, "end_frame": m["end"] + 1,
                   "clip": f"outputs/events_bb/{seq}/clips/{clip_name}"}
            if args.clips:
                rec["frames"] = render_clip(seq, m, A, cw, ch, frames_dir, clip_dir / clip_name,
                                            args.clip_w, args.clip_h)
            index.append(rec)
            reel_pool.append((m["interest"], seq, m, A, cw, ch))
        contact_sheet(seq, moments, A, cw, ch, frames_dir, out_root / f"contact_{seq}.jpg")
        print(f"  {seq}: {len(moments)} ranked moments clipped")

    (out_root / "index.json").write_text(json.dumps(index, indent=2))
    write_index_md(index, out_root / "index.md")

    if args.clips and reel_pool:
        reel_pool.sort(key=lambda t: -t[0])
        picks = reel_pool[:args.reel_top]
        nf = reel([(s, m, A, cw, ch) for (_, s, m, A, cw, ch) in picks], args.source,
                  out_root / "auto_draft_reel.mp4", 854, 480)
        print(f"  auto_draft_reel.mp4: {len(picks)} moments, {nf} frames (LOCAL; gitignored)")
        top = reel_pool[0]
        nf2 = reel([(top[1], top[2], top[3], top[4], top[5])], args.source,
                   out_root / "sample_highlight.mp4", 640, 360)
        print(f"  sample_highlight.mp4: rank #{top[2]['rank']} {top[2]['top_type']} ({nf2} frames, committed)")

    print(f"\n  ranked candidate moments: {len(index)} | package -> {out_root}")


if __name__ == "__main__":
    main()
