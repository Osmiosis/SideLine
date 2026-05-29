"""Day 18: TrackNet DATA SCOUTING for basketball ball tracking (scout only -- NO training).

Goal: find ONE accessible dataset of CONSECUTIVE video frames + PER-FRAME ball pixel position for
basketball, to (later) train a TrackNet-style temporal ball detector. The Day-15/16/17 spatial
patches (wobble, corner-FP, head-FP) could not stop head-latching; Day-17 proved heads are NOT
size-separable from the ball (bbox-area ratio ~1.0), so the discriminating signal is TEMPORAL
(motion) -- TrackNet's domain. But TrackNet needs consecutive-frame ball GT, which is scarce/gated.

SKEPTICISM RULE (the data-trust gate): a dataset described well in a paper/README is NOT a confirmed
asset. Only "usable" once frames + per-frame ball coords are actually on disk and a sample renders
with the label ON the ball. This script encodes the make-or-break check we ran by hand.

------------------------------------------------------------------------------------------------
SCOUTING RESULT (2026-05-29) -- checked in priority order, all four candidates:

  1. WASB-SBDT (github nttcom/WASB-SBDT, MIT)        BLOCKED
       ball coords: LIVE  -- CVAT XML, per-frame <points frame=N points="x,y"/>, CONSECUTIVE
                            (Google Drive uc?id=1eH3n4uB4d8T-YKLRh46SshD0jYqQbnGF, ~5 MB).
       frames:      GATED  -- NBA_data (Rui Yan "SAM"/NUST-NBA181), ~135 GB. Source page
                            ruiyan1995.github.io/SAM.html is 404; archived page gates it behind an
                            email request (ruiyan@njust.edu.cn, academic-only) + a Baidu Cloud share.
       => coords in hand, FRAMES not obtainable without an academic email request. Closest real source.

  2. DeepSport ballistic (kaggle gabrielvanzandycke/ballistic-raw-sequences, CC BY-NC-SA 4.0)  NO BALL GT
       frames:      LIVE  -- ~4.27 GB, Kaggle (free token gate only). CONSECUTIVE (per instant: a
                            2-frame pair ~40ms apart; instants step ~160ms within an id).
       ball coords: ABSENT in the files. Hands-on inspection (this script) of every per-instant
                            JSON shows ONLY {calibration, timestamp, sequence_timestamps, players:
                            [{status,level,pos_feet}], ...}. "ball"/"center"/"Point3D" appear 0 times.
       (The sibling deepsportradar/basketball-instants-dataset HAS ball 3D GT -- but SINGLE instants,
        not consecutive. The consecutive ballistic ball-trajectory GT is withheld to the EvalAI
        challenge server. So DeepSport gives consecutive-frames OR ball-GT, never both.)

  3. SportsTrack (Han et al. 2024, Applied Sciences 14(4):1376)  BLOCKED
       Real self-built basketball ball-per-frame set (~2196 train / 1464 test frames, 1280x720) but
       NO public download (author-request only). (The arXiv "SportsTrack" 2211.07173 is a different
       thing -- a player MOT tracker, not a ball dataset.)

  4. TrackID3x3 (Yamada et al. 2025, github open-starlab/TrackID3x3, CC BY 4.0)  DOES-NOT-FIT
       Real, openly downloadable, consecutive frames -- but PLAYER/pose/ID only, ZERO ball annotation
       (and 3x3, not 5v5).

WINNER: none clean. Decision -> NO-GO on an off-the-shelf TrackNet source (see notes.md ## Day 18).
The one REAL consecutive-frame basketball ball set is WASB's (NBA_data frames + WASB CVAT ball XML),
gated behind an academic email request -- a GO-pending-access path, not a no-credential download.
------------------------------------------------------------------------------------------------

This script provides the two reproducible checks we used (no dataset is committed):
  list-files : enumerate a Kaggle dataset's file tree (needs a Kaggle token).
  inspect    : the make-or-break check -- does a downloaded DeepSport instant JSON contain a BALL
               annotation? (Reports keys + ball-keyword counts; the data-trust gate.)

Usage:
  python scripts/scout_tracknet_data.py list-files gabrielvanzandycke/ballistic-raw-sequences
  python scripts/scout_tracknet_data.py inspect datasets/_dl_ballistic/camcourt1_1572364075764.json
"""
import argparse, json, sys
from pathlib import Path


def list_files(slug: str, max_pages: int = 40):
    """Enumerate a Kaggle dataset file tree (free Kaggle token required: ~/.kaggle/kaggle.json
    or KAGGLE_USERNAME/KAGGLE_KEY, or an access_token the CLI accepts)."""
    import kaggle
    api = kaggle.api
    names, tok = [], None
    for _ in range(max_pages):
        r = api.dataset_list_files(slug, page_token=tok)
        fs = [f.name for f in r.files]
        names += fs
        tok = getattr(r, "nextPageToken", None) or getattr(r, "next_page_token", None)
        if not tok or not fs:
            break
    import collections, os
    exts = collections.Counter(os.path.splitext(n)[1] for n in names)
    tops = collections.Counter(n.split("/")[0] for n in names)
    print(f"{slug}: {len(names)} files | extensions={dict(exts)}")
    print(f"  top-level: {dict(tops)}")
    # any file that looks like a ball/annotation manifest (the thing TrackNet would need)
    cand = [n for n in names if any(k in n.lower() for k in ("ball", "annot", "traj", "label"))]
    print(f"  ball/annotation-looking files: {cand[:20] if cand else 'NONE'}")
    return names


BALL_KEYS = ("ball", "center", "point3d", "annotation", "trajectory")


def inspect(path: str):
    """The data-trust gate: does this DeepSport instant JSON actually contain a BALL annotation?
    (Day-18 finding: ballistic-raw-sequences JSONs do NOT -- only calibration + player pos_feet.)"""
    p = Path(path)
    if not p.exists():
        print(f"!! {p} not present (datasets are gitignored / not committed). "
              f"Download a sample first:\n   kaggle datasets download "
              f"gabrielvanzandycke/ballistic-raw-sequences -f <path/to/instant.json> -p datasets/_dl_ballistic")
        return
    txt = p.read_text()
    d = json.loads(txt)
    print(f"=== {p.name} ===")
    print(f"  top-level keys: {list(d.keys())}")
    low = txt.lower()
    counts = {k: low.count(k) for k in BALL_KEYS}
    print(f"  ball-keyword counts: {counts}")
    has_ball = any(counts[k] for k in ("ball", "center", "point3d"))
    print(f"  sequence_timestamps: {d.get('sequence_timestamps')}  (consecutive-frame pair?)")
    print(f"  players: {len(d.get('players', []))} entries (pos_feet); calibration present: "
          f"{'calibration' in d}")
    print(f"  >> BALL ANNOTATION PRESENT: {has_ball}  "
          f"{'(usable for TrackNet GT)' if has_ball else '(NO ball GT -> NOT usable as-is)'}")
    return has_ball


def main():
    ap = argparse.ArgumentParser(description="Day-18 TrackNet data scouting (scout only).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lf = sub.add_parser("list-files"); lf.add_argument("slug")
    ins = sub.add_parser("inspect"); ins.add_argument("json_path")
    args = ap.parse_args()
    if args.cmd == "list-files":
        list_files(args.slug)
    elif args.cmd == "inspect":
        inspect(args.json_path)


if __name__ == "__main__":
    main()
