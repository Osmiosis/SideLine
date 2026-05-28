"""ByteTrack parameter sweep over a cached detection set.

In-process, no subprocess overhead. For each (config) in the sweep:
  1. run track_from_cache.track_seq on every seq with that config
  2. invoke TrackEval inline, capture HOTA/DetA/AssA/MOTA/IDF1/IDsw
  3. append a row to outputs/eval/day9_sweep_<tag>.csv

Sweep strategy (per PRD): one-param-at-a-time from defaults, then combine winners.

Usage:
  python scripts/sweep_tracker.py --cache outputs/det_cache/sn_soccana \
      --source datasets/soccernet_tracking --split soccernet-test \
      --tag sn_soccana --out outputs/eval/day9_sweep_sn_soccana.csv \
      --grid '{"track_buffer":[30,60,90,120],"match_thresh":[0.7,0.8,0.9],"new_track_thresh":[0.6,0.7,0.8]}'
"""
import argparse, csv, json, shutil, sys, time, traceback
from pathlib import Path
from itertools import product

sys.path.insert(0, str(Path(__file__).parent))
from track_from_cache import track_seq  # noqa: E402

import trackeval  # noqa: E402

BENCHMARK = "SportsMOT"

def stage_gt_once(source: Path, staging: Path, seqs: list, split: str):
    gt_base = staging / "gt" / "mot_challenge" / f"{BENCHMARK}-{split}"
    seqmaps = staging / "gt" / "mot_challenge" / "seqmaps"
    gt_base.mkdir(parents=True, exist_ok=True)
    seqmaps.mkdir(parents=True, exist_ok=True)
    for seq in seqs:
        seq_src = source / seq
        seq_dst = gt_base / seq
        (seq_dst / "gt").mkdir(parents=True, exist_ok=True)
        shutil.copy2(seq_src / "gt" / "gt.txt", seq_dst / "gt" / "gt.txt")
        shutil.copy2(seq_src / "seqinfo.ini", seq_dst / "seqinfo.ini")
    (seqmaps / f"{BENCHMARK}-{split}.txt").write_text("name\n" + "\n".join(seqs) + "\n")

def stage_tracker(staging: Path, tracker_name: str, tracker_dir: Path, seqs: list, split: str):
    out_base = staging / "trackers" / "mot_challenge" / f"{BENCHMARK}-{split}" / tracker_name / "data"
    out_base.mkdir(parents=True, exist_ok=True)
    for seq in seqs:
        src = tracker_dir / f"{seq}.txt"
        if src.exists():
            shutil.copy2(src, out_base / f"{seq}.txt")

def eval_one(staging: Path, tracker_name: str, split: str):
    from trackeval.datasets.mot_challenge_2d_box import MotChallenge2DBox
    eval_cfg = trackeval.Evaluator.get_default_eval_config()
    eval_cfg["PRINT_ONLY_COMBINED"] = True
    eval_cfg["USE_PARALLEL"] = False
    eval_cfg["DISPLAY_LESS_PROGRESS"] = True
    eval_cfg["TIME_PROGRESS"] = False
    eval_cfg["PRINT_RESULTS"] = False
    eval_cfg["OUTPUT_SUMMARY"] = False
    eval_cfg["OUTPUT_DETAILED"] = False
    eval_cfg["PLOT_CURVES"] = False
    ds_cfg = MotChallenge2DBox.get_default_dataset_config()
    ds_cfg["GT_FOLDER"] = str(staging / "gt" / "mot_challenge")
    ds_cfg["TRACKERS_FOLDER"] = str(staging / "trackers" / "mot_challenge")
    ds_cfg["BENCHMARK"] = BENCHMARK
    ds_cfg["SPLIT_TO_EVAL"] = split
    ds_cfg["TRACKERS_TO_EVAL"] = [tracker_name]
    ds_cfg["CLASSES_TO_EVAL"] = ["pedestrian"]
    ds_cfg["DO_PREPROC"] = False
    ds_cfg["PRINT_CONFIG"] = False
    metrics = [
        trackeval.metrics.HOTA(),
        trackeval.metrics.CLEAR({"PRINT_CONFIG": False, "THRESHOLD": 0.5}),
        trackeval.metrics.Identity({"PRINT_CONFIG": False, "THRESHOLD": 0.5}),
    ]
    ev = trackeval.Evaluator(eval_cfg)
    ds = MotChallenge2DBox(ds_cfg)
    res, _ = ev.evaluate([ds], metrics)
    r = res["MotChallenge2DBox"][tracker_name]["COMBINED_SEQ"]["pedestrian"]
    return {
        "HOTA": float(r["HOTA"]["HOTA"].mean()),
        "DetA": float(r["HOTA"]["DetA"].mean()),
        "AssA": float(r["HOTA"]["AssA"].mean()),
        "MOTA": float(r["CLEAR"]["MOTA"]),
        "IDF1": float(r["Identity"]["IDF1"]),
        "IDsw": int(r["CLEAR"]["IDSW"]),
        "n_pred_ids": int(r["Count"]["IDs"]),
    }

def config_tag(cfg: dict) -> str:
    if not cfg:
        return "default"
    return "_".join(f"{k}{cfg[k]}" for k in sorted(cfg))

def expand_grid(grid: dict, mode: str):
    """mode='oat' = one-at-a-time (default + each axis varied alone); mode='full' = cartesian."""
    if mode == "full":
        keys = list(grid)
        for combo in product(*(grid[k] for k in keys)):
            yield dict(zip(keys, combo))
        return
    # one-at-a-time: emit default + each (k, v) override
    yield {}
    seen = {("",)}
    for k, vs in grid.items():
        for v in vs:
            key = (k, v)
            if key in seen: continue
            seen.add(key)
            yield {k: v}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--tag", required=True, help="Prefix for tracker dir names + CSV row")
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--work-dir", default="outputs/track_results/_sweep")
    ap.add_argument("--staging", default="outputs/track_eval_staging")
    ap.add_argument("--grid", required=True, help='JSON, e.g. {"track_buffer":[30,60],"match_thresh":[0.7,0.8]}')
    ap.add_argument("--mode", choices=["oat", "full", "configs"], default="oat",
                    help='oat = default + each axis alone; full = cartesian; configs = treat --grid as list of dicts')
    args = ap.parse_args()

    source = Path(args.source); cache = Path(args.cache)
    work = Path(args.work_dir) / args.tag; work.mkdir(parents=True, exist_ok=True)
    staging = Path(args.staging)
    if staging.exists(): shutil.rmtree(staging)
    seqs = sorted(d.name for d in source.iterdir() if d.is_dir() and (d / "seqinfo.ini").exists())
    print(f"seqs: {seqs}")
    stage_gt_once(source, staging, seqs, args.split)

    grid = json.loads(args.grid)
    if args.mode == "configs":
        configs = list(grid)  # grid is actually a list of dicts in this mode
    else:
        configs = list(expand_grid(grid, args.mode))
    print(f"will run {len(configs)} configs")

    csv_path = Path(args.out_csv); csv_path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["tag", "config", "HOTA", "DetA", "AssA", "MOTA", "IDF1", "IDsw", "n_pred_ids", "wall_s"]
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if write_header: w.writeheader()
        for i, cfg in enumerate(configs):
            t = config_tag(cfg)
            tracker_name = f"{args.tag}__{t}"
            tracker_dir = work / t
            t0 = time.time()
            try:
                for seq in seqs:
                    track_seq(cache / f"{seq}.txt", source / seq, tracker_dir / f"{seq}.txt", cfg)
                stage_tracker(staging, tracker_name, tracker_dir, seqs, args.split)
                m = eval_one(staging, tracker_name, args.split)
            except Exception as e:
                print(f"[{i+1}/{len(configs)}] {t}  FAILED: {e}")
                traceback.print_exc()
                continue
            dt = time.time() - t0
            row = {"tag": args.tag, "config": json.dumps(cfg, sort_keys=True), **m, "wall_s": round(dt, 1)}
            w.writerow(row); f.flush()
            print(f"[{i+1}/{len(configs)}] {t:40s}  HOTA={m['HOTA']:.3f}  AssA={m['AssA']:.3f}  IDF1={m['IDF1']:.3f}  IDsw={m['IDsw']}  ({dt:.1f}s)")

if __name__ == "__main__":
    main()
