"""Day 24 (Part C/D): clip highlight-candidate MOMENTS from the A-feed + package for curation.

Reads the high-recall candidate moments (detect_events.py) and cuts each one from the
Day-13 follow-cam VARIANT A (ball-faithful incl. shots/high balls -- the right feed for
ball-centric events), by cropping the wide source frames with A's per-frame crop centers
(same crop math as follow_cam.render_video; no dependency on a pre-rendered mp4).

Output = a CURATION-READY package: per-moment clips + a skim index (timestamp, type,
confidence) a human (Student Council editor) picks from, + per-seq contact sheets to eyeball,
+ an optional auto-draft reel (top-confidence moments concatenated, clearly marked
"AUTO-DRAFT, human-curate"). HIGH RECALL: the set over-includes; the editor discards.

Validation:
  - LABEL-ANCHORED (sparse): the GSR clip-level action (1 known event/clip @ action_position)
    -> does a candidate moment cover it? Reports recall over the 5 labeled events. The
    shot-detector trust check: SNGS-118 'Shots off target', stoppage check: SNGS-120 'Foul'.
  - PERCEPTUAL (primary for precision): contact sheets + clips to WATCH. Labels are 1/clip so
    they can't score false positives -> the eye judges FP tolerance + missed-by-eye.

Honest type labels (never overclaimed): 'likely_goal_candidate' (NOT goal), 'stoppage_review'
(NOT foul), 'tackle_proxy', 'shot', 'fast_transition'.

Outputs:
  outputs/events/<seq>/clips/<i>_<type>_<t>.mp4                 per-moment clips (gitignored)
  outputs/deliverables/event_highlights_football/
    index.json / index.md                                      curation skim list (committed)
    contact_<seq>.png                                          per-seq visual skim (committed)
    auto_draft_reel.mp4                                        top-N concatenated (gitignored)
    README.md                                                  package doc (committed)

Usage:
  python scripts/clip_highlights.py                 # all 5 seqs, clips + sheets + reel
  python scripts/clip_highlights.py --no-clips      # index + contact sheets only (fast)
"""
import argparse, json, math, sys
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent))
from follow_cam import _crop  # identical crop math as the Day-13 A-feed renderer

SEQS_DEFAULT = ["SNGS-116", "SNGS-117", "SNGS-118", "SNGS-119", "SNGS-120"]
FPS = 25
TYPE_COLOR = {  # BGR overlay tags
    "shot": (40, 220, 40), "fast_transition": (240, 180, 40),
    "likely_goal_candidate": (40, 200, 255), "tackle_proxy": (200, 120, 240),
    "stoppage_review": (170, 170, 170),
}


def load_A_centers(follow_json):
    d = json.loads(Path(follow_json).read_text())
    A = {e["frame"]: (e["cx"], e["cy"]) for e in d["variants"]["A"]}
    return A, d["crop_w"], d["crop_h"]


def tag_text(m):
    types = "+".join(t.replace("_", " ") for t in m["types"])
    return f"{types}  c={m['confidence']}  [{m['start_sec']:.1f}-{m['end_sec']:.1f}s]"


def render_clip(seq, m, A, cw, ch, frames_dir, out_path, out_w, out_h, label):
    vw = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (out_w, out_h))
    written = 0
    for i in range(m["start"], m["end"] + 1):
        f = i + 1
        img = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
        if img is None:
            continue
        cx, cy = A.get(f, (img.shape[1] / 2, img.shape[0] / 2))
        out = cv2.resize(_crop(img, cx, cy, cw, ch), (out_w, out_h), interpolation=cv2.INTER_LINEAR)
        # tag bar
        cv2.rectangle(out, (0, 0), (out_w, 34), (0, 0, 0), -1)
        col = TYPE_COLOR.get(m["types"][0], (255, 255, 255))
        cv2.putText(out, f"{seq}  {tag_text(m)}", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 1, cv2.LINE_AA)
        vw.write(out); written += 1
    vw.release()
    return written


def contact_sheet(seq, moments, A, cw, ch, frames_dir, out_path, label,
                  cols=5, tile_w=300):
    """One row per moment: `cols` thumbnails across the moment (A-feed crop), labelled."""
    if not moments:
        return
    tile_h = int(round(tile_w * ch / cw)); tile_h += 22  # header strip per tile-row
    rows = len(moments)
    sheet = np.full((rows * (tile_h + 6), cols * tile_w, 3), 30, np.uint8)
    af = label.get("approx_frame")
    for r, m in enumerate(moments):
        idxs = np.linspace(m["start"], m["end"], cols).astype(int)
        covers = af is not None and m["start"] <= af - 1 <= m["end"]
        for c, i in enumerate(idxs):
            f = i + 1
            img = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
            if img is None:
                continue
            crop = cv2.resize(_crop(img, *A.get(f, (img.shape[1] / 2, img.shape[0] / 2)), cw, ch),
                              (tile_w, tile_h - 22))
            y0 = r * (tile_h + 6)
            sheet[y0 + 22:y0 + tile_h, c * tile_w:(c + 1) * tile_w] = crop
        col = TYPE_COLOR.get(m["types"][0], (255, 255, 255))
        hdr = f"{tag_text(m)}" + ("   <-- covers GSR label" if covers else "")
        cv2.putText(sheet, hdr, (6, r * (tile_h + 6) + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)
    cv2.imwrite(str(out_path), sheet, [cv2.IMWRITE_JPEG_QUALITY, 82])  # JPG -> lean for git


def auto_draft_reel(picks, source, out_path, out_w=854, out_h=480, gap_frames=8):
    """Concatenate chosen moments (seq, m, A, cw, ch) into one rough reel, clearly marked."""
    vw = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (out_w, out_h))
    n_written = 0
    for (seq, m, A, cw, ch) in picks:
        frames_dir = Path(source) / seq / "img1"
        for i in range(m["start"], m["end"] + 1):
            f = i + 1
            img = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
            if img is None:
                continue
            out = cv2.resize(_crop(img, *A.get(f, (img.shape[1] / 2, img.shape[0] / 2)), cw, ch),
                             (out_w, out_h), interpolation=cv2.INTER_LINEAR)
            cv2.rectangle(out, (0, 0), (out_w, 30), (0, 0, 0), -1)
            cv2.putText(out, f"AUTO-DRAFT (human-curate)  {seq}  {tag_text(m)}",
                        (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 220, 40), 1, cv2.LINE_AA)
            vw.write(out); n_written += 1
        for _ in range(gap_frames):  # short black separator
            vw.write(np.zeros((out_h, out_w, 3), np.uint8)); n_written += 1
    vw.release()
    return n_written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="?", default=None)
    ap.add_argument("--events-dir", default="outputs/events")
    ap.add_argument("--follow-dir", default="outputs/follow_cam")
    ap.add_argument("--source", default="datasets/soccernet_tracking")
    ap.add_argument("--out", default="outputs/deliverables/event_highlights_football")
    ap.add_argument("--clip-w", type=int, default=854)
    ap.add_argument("--clip-h", type=int, default=480)
    ap.add_argument("--no-clips", dest="clips", action="store_false", default=True)
    ap.add_argument("--reel-top", type=int, default=8, help="top-confidence moments in auto-draft reel")
    args = ap.parse_args()

    seqs = [args.seq] if args.seq else SEQS_DEFAULT
    out_root = Path(args.out); out_root.mkdir(parents=True, exist_ok=True)

    index = []            # flat skim list
    reel_pool = []        # (conf, seq, m, A, cw, ch)
    n_labels = 0; n_label_covered = 0
    for seq in seqs:
        ev = json.loads((Path(args.events_dir) / seq / "events.json").read_text())
        moments = ev["merged_windows"]; label = ev["label"]
        A, cw, ch = load_A_centers(Path(args.follow_dir) / seq / "follow_cam.json")
        frames_dir = Path(args.source) / seq / "img1"
        af = label.get("approx_frame")
        if af is not None:
            n_labels += 1
            if any(m["start"] <= af - 1 <= m["end"] for m in moments):
                n_label_covered += 1

        clip_dir = Path(args.events_dir) / seq / "clips"
        if args.clips:
            clip_dir.mkdir(parents=True, exist_ok=True)
        for j, m in enumerate(moments):
            covers = af is not None and m["start"] <= af - 1 <= m["end"]
            rec = {"seq": seq, "idx": j, "types": m["types"], "confidence": m["confidence"],
                   "start_sec": m["start_sec"], "end_sec": m["end_sec"],
                   "start_frame": m["start"] + 1, "end_frame": m["end"] + 1,
                   "covers_gsr_label": covers,
                   "gsr_label": label.get("action_class") if covers else None}
            clip_name = f"{j:02d}_{m['types'][0]}_{m['start_sec']:.0f}s.mp4"
            rec["clip"] = f"outputs/events/{seq}/clips/{clip_name}"
            if args.clips:
                w = render_clip(seq, m, A, cw, ch, frames_dir, clip_dir / clip_name,
                                args.clip_w, args.clip_h, label)
                rec["frames"] = w
            index.append(rec)
            reel_pool.append((m["confidence"], seq, m, A, cw, ch))

        contact_sheet(seq, moments, A, cw, ch, frames_dir, out_root / f"contact_{seq}.jpg", label)
        print(f"  {seq}: {len(moments)} moments clipped"
              + (f" (GSR '{label['action_class']}' covered)" if af and any(
                  m['start'] <= af - 1 <= m['end'] for m in moments) else ""))

    # ---- index files (the curation skim list) ----
    (out_root / "index.json").write_text(json.dumps(index, indent=2))
    write_index_md(index, n_labels, n_label_covered, out_root / "index.md")

    # ---- auto-draft reel: top-N by confidence (time-ordered within) ----
    if args.clips and reel_pool:
        reel_pool.sort(key=lambda t: -t[0])
        picks = reel_pool[:args.reel_top]
        picks.sort(key=lambda t: (t[1], t[2]["start"]))  # group by seq, chronological
        nf = auto_draft_reel([(s, m, A, cw, ch) for (_, s, m, A, cw, ch) in picks],
                             args.source, out_root / "auto_draft_reel.mp4")
        print(f"  auto_draft_reel.mp4: {len(picks)} moments, {nf} frames (LOCAL; gitignored - 31MB)")
        # small COMMITTABLE demo: the single top-confidence moment, downscaled
        top = max(reel_pool, key=lambda t: t[0])
        nf2 = auto_draft_reel([(top[1], top[2], top[3], top[4], top[5])],
                              args.source, out_root / "sample_highlight.mp4", out_w=640, out_h=360)
        print(f"  sample_highlight.mp4: top moment {top[1]} c={top[0]} ({nf2} frames, 640x360, committed)")

    print(f"\n  candidate moments: {len(index)} | "
          f"label-anchored recall: {n_label_covered}/{n_labels} clips covered")
    print(f"  package -> {out_root}")


def write_index_md(index, n_labels, n_cov, path):
    lines = ["# Event Highlight Candidates - football (SoccerNet proxy for DPS)", "",
             "**Output #3** (Student Council / school Instagram). HIGH-RECALL candidate set: a",
             "human curates -> picks the keepers, discards false positives. Motion-only (audio is",
             "the documented next lever for fouls + goal-confirmation).", "",
             "Honest type labels: `likely_goal_candidate` (NOT a goal - no goal-line/net detection;",
             "catches saves/near-misses too), `stoppage_review` (NOT a foul - motion can't judge that),",
             "`tackle_proxy` (noisy), `shot`, `fast_transition`. Thresholds are camera-scale-dependent",
             "-> RE-TUNE at the DPS mount.", "",
             f"**Label-anchored recall:** {n_cov}/{n_labels} GSR-labeled clip actions fall inside a candidate moment.", "",
             "| seq | t (s) | type(s) | conf | covers GSR label | clip |",
             "|-----|-------|---------|------|------------------|------|"]
    for r in sorted(index, key=lambda r: (r["seq"], r["start_sec"])):
        types = ", ".join(r["types"])
        cov = f"YES ({r['gsr_label']})" if r["covers_gsr_label"] else ""
        lines.append(f"| {r['seq']} | {r['start_sec']:.1f}-{r['end_sec']:.1f} | {types} | "
                     f"{r['confidence']} | {cov} | `{Path(r['clip']).name}` |")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
