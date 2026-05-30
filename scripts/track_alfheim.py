"""Day 29 PART B: run player detection+tracking on a stitched full-match video, at SCALE.

The scale-stress-test core. Day-9 production = BoT-SORT + sparseOptFlow GMC on a detection cache;
on a fresh video (no cache) the faithful one-pass equivalent is Ultralytics `model.track` with
botsort.yaml (GMC is inside the tracker). stream=True keeps memory flat over a 47-min video.

Exports MOT (frame,id,x,y,w,h,conf,-1,-1,-1) and the SCALE FINDINGS:
  - total UNIQUE track IDs over the whole half (ID-accumulation = the key scale metric)
  - runtime + processing fps
  - peak GPU VRAM + process RAM (the RTX-4060 feasibility question; Day-26 RAM lesson)
Writes incrementally (chunked flush) so a long run never holds the whole MOT in memory.

Usage:
  .venv\\Scripts\\python scripts\\track_alfheim.py --video outputs/alfheim/first_half.mp4 \
      --out outputs/track_results/alfheim_fh_cam1/first_half.txt --model models/soccana.pt
"""
import argparse, time, os
from pathlib import Path


def peak_ram_mb():
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / 1e6
    except Exception:
        return -1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="models/soccana.pt")
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--tracker", default="botsort.yaml")
    ap.add_argument("--classes", default="0", help="comma class ids to keep (0=player)")
    ap.add_argument("--vid-stride", type=int, default=1)
    ap.add_argument("--device", default="0")
    ap.add_argument("--flush-every", type=int, default=2000)
    args = ap.parse_args()

    import torch
    from ultralytics import YOLO
    classes = [int(c) for c in args.classes.split(",")]
    out_path = Path(args.out); out_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path = out_path.with_suffix(".stats.json")

    model = YOLO(args.model)
    print(f"[track] model={args.model} classes={model.names} keep={classes} "
          f"imgsz={args.imgsz} tracker={args.tracker} video={args.video}", flush=True)

    if args.device.isdigit() and torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()

    unique = set()
    n_rows = 0
    frames = 0
    peak_ram = 0.0
    buf = []
    t0 = time.time()
    fout = open(out_path, "w")
    try:
        for res in model.track(source=args.video, stream=True, device=args.device,
                               imgsz=args.imgsz, tracker=args.tracker, persist=True,
                               classes=classes, vid_stride=args.vid_stride, verbose=False):
            frames += 1
            if res.boxes is not None and res.boxes.id is not None:
                xywh = res.boxes.xywh.cpu().numpy()           # center x,y,w,h
                ids = res.boxes.id.cpu().numpy()
                confs = res.boxes.conf.cpu().numpy()
                for (cx, cy, w, h), tid, cf in zip(xywh, ids, confs):
                    tid = int(tid); unique.add(tid)
                    x = cx - w / 2.0; y = cy - h / 2.0       # MOT = top-left
                    buf.append(f"{frames},{tid},{x:.2f},{y:.2f},{w:.2f},{h:.2f},{cf:.4f},-1,-1,-1")
                    n_rows += 1
            if frames % args.flush_every == 0:
                fout.write("\n".join(buf) + "\n"); buf.clear()
                peak_ram = max(peak_ram, peak_ram_mb())
                el = time.time() - t0
                print(f"[track] frame {frames}  ids_so_far={len(unique)}  rows={n_rows}  "
                      f"{frames/el:.1f} fps  {el:.0f}s  ram={peak_ram:.0f}MB", flush=True)
        if buf:
            fout.write("\n".join(buf) + "\n")
    finally:
        fout.close()

    el = time.time() - t0
    peak_ram = max(peak_ram, peak_ram_mb())
    peak_vram = (torch.cuda.max_memory_allocated() / 1e6) if torch.cuda.is_available() else -1
    import json
    stats = {
        "video": args.video, "model": args.model, "tracker": args.tracker, "imgsz": args.imgsz,
        "frames": frames, "mot_rows": n_rows, "unique_track_ids": len(unique),
        "runtime_sec": round(el, 1), "proc_fps": round(frames / max(1e-9, el), 2),
        "peak_ram_mb": round(peak_ram, 0), "peak_vram_mb": round(peak_vram, 0),
        "ids_per_min": round(len(unique) / max(1e-9, el / 60), 1),
    }
    stats_path.write_text(json.dumps(stats, indent=2))
    print(f"\n[track] DONE frames={frames} unique_ids={len(unique)} rows={n_rows} "
          f"runtime={el:.0f}s ({stats['proc_fps']} fps) peak_vram={peak_vram:.0f}MB peak_ram={peak_ram:.0f}MB",
          flush=True)
    print(f"[track] MOT -> {out_path}\n[track] stats -> {stats_path}", flush=True)


if __name__ == "__main__":
    main()
