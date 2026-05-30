"""Run TrackEval (HOTA/MOTA/IDF1) on our SportsMOT basketball subset against a tracker output dir.

Stages our GT into TrackEval's expected layout, then evaluates the named tracker.

Layout TrackEval requires (built automatically from our actual data):
  staging/gt/mot_challenge/SportsMOT-basketball-val/<seq>/{gt/gt.txt, seqinfo.ini}
  staging/gt/mot_challenge/seqmaps/SportsMOT-basketball-val.txt
  staging/trackers/mot_challenge/SportsMOT-basketball-val/<tracker>/data/<seq>.txt

Tracker output dir is expected to contain `<seq>.txt` files in MOT format.

Usage:
  python scripts/eval_track.py <tracker_output_dir> --tracker-name <name> \
    [--source datasets/sportsmot_basketball] [--staging outputs/track_eval_staging]
"""
import argparse, shutil
from pathlib import Path
import sys

import trackeval

BENCHMARK = "SportsMOT"
SPLIT = "basketball-val"  # default; override via --split

def stage_gt(source: Path, staging: Path, seqs: list, split: str):
    """Copy/relink GT + seqinfo into TrackEval's expected tree."""
    gt_base = staging / "gt" / "mot_challenge" / f"{BENCHMARK}-{split}"
    seqmaps = staging / "gt" / "mot_challenge" / "seqmaps"
    gt_base.mkdir(parents=True, exist_ok=True)
    seqmaps.mkdir(parents=True, exist_ok=True)

    for seq in seqs:
        seq_src = source / seq
        seq_dst = gt_base / seq
        (seq_dst / "gt").mkdir(parents=True, exist_ok=True)
        # copy gt.txt + seqinfo.ini (small files)
        shutil.copy2(seq_src / "gt" / "gt.txt", seq_dst / "gt" / "gt.txt")
        shutil.copy2(seq_src / "seqinfo.ini", seq_dst / "seqinfo.ini")

    # seqmap file: one column "name", header + seq names
    sm_path = seqmaps / f"{BENCHMARK}-{split}.txt"
    sm_path.write_text("name\n" + "\n".join(seqs) + "\n")
    print(f"staged {len(seqs)} GT seqs at {gt_base}")
    return gt_base.parent.parent  # staging/gt

def stage_tracker(tracker_dir: Path, staging: Path, tracker_name: str, seqs: list, split: str):
    """Copy tracker outputs into TrackEval tree."""
    out_base = staging / "trackers" / "mot_challenge" / f"{BENCHMARK}-{split}" / tracker_name / "data"
    out_base.mkdir(parents=True, exist_ok=True)
    n = 0
    for seq in seqs:
        src = tracker_dir / f"{seq}.txt"
        if not src.exists():
            print(f"  WARN: tracker output missing for {seq}: {src}")
            continue
        shutil.copy2(src, out_base / f"{seq}.txt")
        n += 1
    print(f"staged {n} tracker files at {out_base}")

def evaluate(tracker_dir, tracker_name, source="datasets/sportsmot_basketball",
             staging="outputs/track_eval_staging", split=SPLIT, reset_staging=False):
    """Stage GT + tracker outputs, run TrackEval, return COMBINED_SEQ headline metrics as a dict.

    Returns: {HOTA, DetA, AssA, MOTA, IDF1, IDsw} (floats; IDsw int).
    """
    source = Path(source)
    staging = Path(staging)
    if reset_staging and staging.exists():
        shutil.rmtree(staging)

    # Auto-detect seqs from source dir
    seqs = sorted(d.name for d in source.iterdir() if d.is_dir() and (d / "seqinfo.ini").exists())
    print(f"sequences: {seqs}")

    stage_gt(source, staging, seqs, split)
    stage_tracker(Path(tracker_dir), staging, tracker_name, seqs, split)

    # Configure TrackEval
    eval_cfg = trackeval.Evaluator.get_default_eval_config()
    eval_cfg["PRINT_ONLY_COMBINED"] = True
    eval_cfg["USE_PARALLEL"] = False
    eval_cfg["DISPLAY_LESS_PROGRESS"] = True
    eval_cfg["TIME_PROGRESS"] = False

    from trackeval.datasets.mot_challenge_2d_box import MotChallenge2DBox
    ds_cfg = MotChallenge2DBox.get_default_dataset_config()
    ds_cfg["GT_FOLDER"] = str(staging / "gt" / "mot_challenge")
    ds_cfg["TRACKERS_FOLDER"] = str(staging / "trackers" / "mot_challenge")
    ds_cfg["BENCHMARK"] = BENCHMARK
    ds_cfg["SPLIT_TO_EVAL"] = split
    ds_cfg["TRACKERS_TO_EVAL"] = [tracker_name]
    ds_cfg["CLASSES_TO_EVAL"] = ["pedestrian"]
    ds_cfg["DO_PREPROC"] = False  # SportsMOT has no distractor preproc
    ds_cfg["PRINT_CONFIG"] = False

    metrics_list = [
        trackeval.metrics.HOTA(),
        trackeval.metrics.CLEAR({"PRINT_CONFIG": False, "THRESHOLD": 0.5}),
        trackeval.metrics.Identity({"PRINT_CONFIG": False, "THRESHOLD": 0.5}),
    ]

    evaluator = trackeval.Evaluator(eval_cfg)
    dataset = MotChallenge2DBox(ds_cfg)
    output_res, _ = evaluator.evaluate([dataset], metrics_list)

    res = output_res["MotChallenge2DBox"][tracker_name]["COMBINED_SEQ"]["pedestrian"]
    return {
        "HOTA": float(res["HOTA"]["HOTA"].mean()),
        "DetA": float(res["HOTA"]["DetA"].mean()),
        "AssA": float(res["HOTA"]["AssA"].mean()),
        "MOTA": float(res["CLEAR"]["MOTA"]),
        "IDF1": float(res["Identity"]["IDF1"]),
        "IDsw": int(res["CLEAR"]["IDSW"]),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tracker_dir", help="Directory with <seq>.txt MOT-format tracker outputs")
    ap.add_argument("--tracker-name", required=True, help="Used as a label in TrackEval reports")
    ap.add_argument("--source", default="datasets/sportsmot_basketball", help="SportsMOT extracted dir")
    ap.add_argument("--staging", default="outputs/track_eval_staging", help="Temp TrackEval layout root")
    ap.add_argument("--split", default=SPLIT, help="TrackEval split label, e.g. basketball-val, football-val")
    ap.add_argument("--reset-staging", action="store_true", help="Wipe staging first")
    args = ap.parse_args()

    m = evaluate(args.tracker_dir, args.tracker_name, args.source, args.staging,
                 args.split, args.reset_staging)

    # Pull the "COMBINED_SEQ" summary metrics
    print("\n=== HEADLINE METRICS ===")
    print(f"  HOTA: {m['HOTA']:.3f}    DetA: {m['DetA']:.3f}    AssA: {m['AssA']:.3f}")
    print(f"  MOTA: {m['MOTA']:.3f}    IDF1: {m['IDF1']:.3f}    IDsw: {m['IDsw']}")

if __name__ == "__main__":
    main()
