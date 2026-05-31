"""Day 31 PART B-probe: cheap ball-recall probe on a short Alfheim window.

The soccana ball detector was validated on SoccerNet BROADCAST footage (ball is fairly
large). Alfheim is a WIDE FIXED ELEVATED single camera -> the ball is TINY (few px, on
grass, at distance). Before trusting any 47-min event-density number, MEASURE ball recall
cheaply on a short window. If recall is poor, a full pass just measures the DETECTOR's
failure, not real event density (the metric-vs-reality trap).

MINIMAL by design (addendum): raw soccana Ball detection, no Kalman, no homography. Just:
  - per-frame raw recall (fraction of processed frames with >=1 Ball detection)
  - confidence distribution
  - multi-ball rate (frames with >1 Ball box -> FP / ambiguity indicator)
  - a handful of sample frames with the top Ball box drawn + a zoom crop (perceptual check:
    does the box sit on the actual ball, or on a line/head/noise -- the wide-cam FP risk?)

Outputs (outputs/alfheim/ball_probe/):
  probe_summary.json   window, recall, conf stats, multi-ball rate
  ball_window.json     {frame: [x,y,conf]} best ball per processed frame (reuse if gate passes)
  sample_*.png         evenly-spaced frames, top ball box + zoom crop

Usage:
  .venv\\Scripts\\python scripts\\alfheim_ball_probe.py \
      --video outputs/alfheim/first_half.mp4 --start 18000 --end 36000 --stride 4
"""
import argparse, json
from pathlib import Path
import numpy as np
import cv2

BALL_CLASS = 1   # soccana: 0=Player, 1=Ball, 2=Referee


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default="outputs/alfheim/first_half.mp4")
    ap.add_argument("--model", default="models/soccana.pt")
    ap.add_argument("--start", type=int, default=18000, help="source start frame (30fps)")
    ap.add_argument("--end", type=int, default=36000, help="source end frame")
    ap.add_argument("--stride", type=int, default=4, help="process every Nth source frame")
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--conf", type=float, default=0.15, help="low conf floor (recall-biased probe)")
    ap.add_argument("--device", default="0")
    ap.add_argument("--n-samples", type=int, default=8)
    ap.add_argument("--out", default="outputs/alfheim/ball_probe")
    args = ap.parse_args()

    from ultralytics import YOLO
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    model = YOLO(args.model)
    print(f"[probe] model={args.model} names={model.names} window=[{args.start},{args.end}] "
          f"stride={args.stride} conf>={args.conf}", flush=True)

    cap = cv2.VideoCapture(args.video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, args.start)

    ball_by_frame = {}          # source-frame -> [x, y, conf]
    n_proc = 0; n_with_ball = 0; n_multi = 0
    confs = []
    sample_frames = []          # (frame_idx, image, ball_box_or_None)
    # pick sample frame indices evenly across the window
    sample_targets = set(np.linspace(args.start, args.end - 1, args.n_samples).astype(int).tolist())

    f = args.start
    while f < args.end:
        ok, img = cap.read()
        if not ok:
            break
        if (f - args.start) % args.stride == 0:
            res = model.predict(img, imgsz=args.imgsz, conf=args.conf, classes=[BALL_CLASS],
                                device=args.device, verbose=False)[0]
            n_proc += 1
            best = None
            if res.boxes is not None and len(res.boxes) > 0:
                xywh = res.boxes.xywh.cpu().numpy()
                cf = res.boxes.conf.cpu().numpy()
                if len(cf) > 1:
                    n_multi += 1
                bi = int(np.argmax(cf))
                cx, cy = float(xywh[bi][0]), float(xywh[bi][1])
                best = [cx, cy, float(cf[bi])]
                ball_by_frame[f] = best
                n_with_ball += 1
                confs.append(float(cf[bi]))
            # capture sample frames near targets
            if any(abs(f - t) <= args.stride for t in sample_targets) and len(sample_frames) < args.n_samples:
                sample_frames.append((f, img.copy(), best))
        f += 1
        if (f - args.start) % 2000 == 0:
            print(f"[probe] src_frame {f}  proc={n_proc}  with_ball={n_with_ball}  "
                  f"recall={n_with_ball/max(1,n_proc):.2%}", flush=True)
    cap.release()

    confs = np.array(confs) if confs else np.array([0.0])
    recall = n_with_ball / max(1, n_proc)
    summary = {
        "video": args.video, "window_src_frames": [args.start, args.end], "stride": args.stride,
        "fps_src": 30, "conf_floor": args.conf,
        "n_processed": n_proc, "n_with_ball": n_with_ball,
        "raw_recall": round(recall, 4),
        "multi_ball_frames": n_multi, "multi_ball_rate": round(n_multi / max(1, n_proc), 4),
        "conf_mean": round(float(confs.mean()), 3),
        "conf_median": round(float(np.median(confs)), 3),
        "conf_p10": round(float(np.percentile(confs, 10)), 3),
        "conf_p90": round(float(np.percentile(confs, 90)), 3),
    }
    (out / "probe_summary.json").write_text(json.dumps(summary, indent=2))
    (out / "ball_window.json").write_text(json.dumps(ball_by_frame))

    # render sample frames: full frame + 160px zoom crop on the top ball box
    for i, (fr, img, box) in enumerate(sample_frames):
        vis = img.copy()
        if box is not None:
            x, y, c = box
            cv2.circle(vis, (int(x), int(y)), 18, (0, 0, 255), 2)
            cv2.putText(vis, f"ball conf={c:.2f}", (int(x) + 20, int(y)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cw = 80
            x0, y0 = max(0, int(x) - cw), max(0, int(y) - cw)
            crop = img[y0:int(y) + cw, x0:int(x) + cw]
            if crop.size:
                crop = cv2.resize(crop, (240, 240), interpolation=cv2.INTER_NEAREST)
                vis[0:240, 0:240] = crop
                cv2.rectangle(vis, (0, 0), (240, 240), (0, 255, 0), 2)
        else:
            cv2.putText(vis, "NO BALL", (40, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        cv2.imwrite(str(out / f"sample_{i:02d}_f{fr}.png"), vis)

    print(f"\n[probe] DONE proc={n_proc}  with_ball={n_with_ball}  RAW RECALL={recall:.2%}  "
          f"conf med={summary['conf_median']}  multi-ball={summary['multi_ball_rate']:.2%}", flush=True)
    print(f"[probe] -> {out}/probe_summary.json  + {len(sample_frames)} sample frames", flush=True)


if __name__ == "__main__":
    main()
