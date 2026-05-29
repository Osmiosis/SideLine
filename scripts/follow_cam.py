"""Day 13: broadcast-style FOLLOW-CAM (virtual camera) for football, SoccerNet.

We digitally crop a fixed 16:9 window out of the wide 1920x1080 frame and steer
its center to follow the action -- exactly the VEO / Pixellot dual-wide -> digital-crop
architecture. The documented pro techniques (NOT invented here):

  1. Crop target = ball + player-density BLEND, not raw ball. Confident ball -> follow
     ball; uncertain/aerial/missing ball -> fall back to player mass. Kills whip-pans on
     long kicks and swings-to-nowhere on lost-ball frames.
  2. BIDIRECTIONAL lookahead smoothing. We post-process, so the whole future trajectory
     is known. A forward-backward low-pass (scipy filtfilt, zero phase lag) smooths the
     crop-center path far better than any causal real-time tracker. This is the single
     biggest "looks professional" factor.
  3. ASYMMETRIC pan limits. Accel easing INTO a motion higher than decel easing OUT
     (responsive start, gentle landing) -- the human-operator feel.
  4. CONSTANT-VELOCITY preference via a soft dead-zone (don't move for tiny target moves)
     + heavy smoothing -> smooth holds and glides, not nervous micro-adjustment.

Build order (matches PRD): RAW -> A (smoothed ball) -> B (blended) -> C (B + limits/deadzone).

Evaluation is PERCEPTUAL (no ground-truth crop). The eye is the arbiter -- we render
videos + a contact sheet + crop-center/velocity plots to LOOK at. Proxy metrics
(ball-in-safe-zone %, crop-center jerk, action-in-frame %) are supporting evidence only.

Inputs:
  outputs/ball_track/<seq>/trajectory.json                 (Day 12, pixel ball + flags)
  outputs/track_results/sn_soccana_botsort_gmc/<seq>.txt   (Day 9, player tracks, MOT)
  datasets/soccernet_tracking/<seq>/img1/<frame>.jpg       (wide frames)

Outputs (outputs/follow_cam/<seq>/, gitignored):
  follow_cam.json          final (C) crop-center path -> feeds player highlights / event reels
  metrics.json             RAW/A/B/C proxy metrics
  path_plot.png            crop-center x,y vs frame (raw ball vs A/B/C)
  speed_plot.png           crop-center speed vs frame (whip-pans = spikes)
  contact_sheet_C.png      12 crops across the clip (the final follow-cam, by eye)
  abc_frames.png           A vs B vs C at a few moments (side-by-side)
  follow_<variant>.mp4     rendered crop videos (local; *.mp4 is gitignored)
  abc_montage.mp4          A|B|C side-by-side for a segment (local)

Usage:
  python scripts/follow_cam.py SNGS-118 --no-render      # fast: metrics + plots + frames
  python scripts/follow_cam.py SNGS-118                  # + render videos
  python scripts/follow_cam.py                           # all default seqs
"""
import argparse, json, math, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt

sys.path.insert(0, str(Path(__file__).parent))
from analyze_ball import load_ball_gt  # GT ball (pixel) for the GT-in-crop sanity metric

SEQS_DEFAULT = ["SNGS-118", "SNGS-120"]


# ======================= loaders =======================
def load_ball(ball_dir: Path, seq: str):
    return json.loads((Path(ball_dir) / seq / "trajectory.json").read_text())


def load_players(track_path: Path):
    """MOT tracker output -> {frame: [(cx, cy, w, h), ...]} in PIXEL space (bbox centers)."""
    by_frame = defaultdict(list)
    for line in Path(track_path).read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(",")
        f = int(p[0]); x = float(p[2]); y = float(p[3]); w = float(p[4]); h = float(p[5])
        by_frame[f].append((x + w / 2, y + h / 2, w, h))
    return by_frame


# ======================= signal helpers =======================
def interp_fill(v):
    """Linear-interpolate non-finite entries of a 1D array; edge-hold the ends."""
    v = np.asarray(v, dtype=float).copy()
    idx = np.arange(len(v)); good = np.isfinite(v)
    if good.sum() == 0:
        return np.zeros_like(v)
    v[~good] = np.interp(idx[~good], idx[good], v[good])
    return v


def moving_average(v, win):
    if win <= 1:
        return np.asarray(v, float).copy()
    k = win // 2
    pad = np.pad(np.asarray(v, float), (k, k), mode="edge")
    ker = np.ones(2 * k + 1) / (2 * k + 1)
    return np.convolve(pad, ker, mode="valid")[:len(v)]


def bidir_smooth(v, cutoff_hz, fps, order):
    """Zero-phase forward-backward Butterworth low-pass (the key smoothness technique)."""
    wn = min(max(cutoff_hz / (fps / 2.0), 1e-3), 0.99)
    b, a = butter(order, wn)
    return filtfilt(b, a, np.asarray(v, float))


def clamp_centers(cx, cy, cw, ch, W, H):
    """Keep the crop window fully inside the frame (no cropping outside the image)."""
    hw, hh = cw / 2.0, ch / 2.0
    return np.clip(cx, hw, W - hw), np.clip(cy, hh, H - hh)


# ======================= target construction =======================
def ball_arrays(recs):
    n = len(recs)
    bx = np.full(n, np.nan); by = np.full(n, np.nan)
    aerial = np.zeros(n, bool); conf = np.zeros(n); status = []
    for i, r in enumerate(recs):
        status.append(r["status"])
        aerial[i] = bool(r.get("aerial_suspect"))
        if r.get("x") is not None:
            bx[i] = r["x"]; by[i] = r["y"]
        if r.get("picked_conf") is not None:
            conf[i] = r["picked_conf"]
    return bx, by, status, aerial, conf


def player_centroid(by_frame, n_frames, trim=0.15):
    """Robust (trimmed-mean) centroid of player box-centers per frame -- the 'player mass'.

    Trims the farthest `trim` fraction from the per-frame median so a lone keeper/ref far
    upfield can't drag the centroid. Empty frames are interpolated. Returns (px, py, count)."""
    px = np.full(n_frames, np.nan); py = np.full(n_frames, np.nan); count = np.zeros(n_frames, int)
    for f in range(1, n_frames + 1):
        pl = by_frame.get(f, [])
        count[f - 1] = len(pl)
        if not pl:
            continue
        pts = np.array([(c[0], c[1]) for c in pl], dtype=float)
        med = np.median(pts, axis=0)
        d = np.hypot(pts[:, 0] - med[0], pts[:, 1] - med[1])
        if len(pts) >= 7:
            keep = d <= np.quantile(d, 1 - trim)
            if keep.sum() >= 3:
                pts = pts[keep]
        m = pts.mean(axis=0)
        px[f - 1] = m[0]; py[f - 1] = m[1]
    return interp_fill(px), interp_fill(py), count


def compute_w_ball(status, aerial, conf, w_det, w_pred, w_aerial, pred_decay):
    """Per-frame ball weight in [0,1]. High when ball confidently detected; decays through
    predict-only streaks; suppressed when aerial-suspect; 0 when lost (-> pure player mass).

    NOTE (documented tradeoff): suppressing the aerial ball keeps B/C calm and ground-focused
    on long kicks, but means B/C do NOT chase the ball into the air -- variant A (ball-only)
    is the one that tracks shots / high passes. Kept this way intentionally so the three
    variants stay distinct (A = ball-faithful incl. aerial; B/C = stabilized blend)."""
    n = len(status); w = np.zeros(n); streak = 0
    for i in range(n):
        s = status[i]
        if s == "detected":
            base = w_aerial if aerial[i] else w_det
            streak = 0
        elif s == "predicted":
            streak += 1
            base = w_pred * math.exp(-(streak - 1) / pred_decay)
            if aerial[i]:
                base = min(base, w_aerial * 0.7)
        else:  # lost
            streak += 1
            base = 0.0
        w[i] = base
    return w


def asym_rate_limit(cx, cy, vmax, a_accel, a_decel, dz):
    """Stable (non-oscillating) velocity/accel limiter with soft dead-zone -- human feel.

    The crop velocity is capped by the BRAKING DISTANCE to the target, v <= sqrt(2*a_decel*err),
    so the camera can always decelerate to rest exactly at the target -> it can never overshoot,
    hence never oscillates (a naive chaser with a_accel>a_decel self-oscillates -- it speeds up
    faster than it can brake). Asymmetric feel is preserved: a_accel (launch) may exceed a_decel
    (gentle landing). A soft dead-zone holds the camera for sub-dz target offsets (locked-off
    feel, kills micro-jitter). Applied AFTER bidirectional smoothing, so on already-smooth input
    it mostly tracks the target and only tames the rare fast segment / adds the dead-zone holds."""
    def lim(s):
        s = np.asarray(s, float)
        out = np.empty_like(s); cam = s[0]; vel = 0.0; out[0] = cam
        for i in range(1, len(s)):
            err = s[i] - cam
            mag = max(0.0, abs(err) - dz)                       # soft dead-zone
            v_des = math.copysign(min(vmax, math.sqrt(2 * a_decel * mag)), err) if mag > 0 else 0.0
            dv = v_des - vel
            cap = a_accel if abs(v_des) > abs(vel) else a_decel  # asymmetric: launch vs landing
            if abs(dv) > cap:
                dv = math.copysign(cap, dv)
            vel += dv
            cam += vel
            out[i] = cam
        return out
    return lim(cx), lim(cy)


def build_variants(recs, players_by_frame, args, W, H):
    """Return {RAW,A,B,C: (cx,cy)} clamped, plus meta for metrics/plots."""
    n = len(recs)
    cw = int(round(W / args.zoom)); cw -= cw % 2
    ch = int(round(cw * H / W)); ch -= ch % 2  # match frame aspect (16:9)

    bx, by, status, aerial, conf = ball_arrays(recs)
    px, py, pcount = player_centroid(players_by_frame, n)

    # RAW: naive ball-center, gaps linearly filled (the thing we must NOT ship)
    rbx, rby = interp_fill(bx), interp_fill(by)

    # A: bidirectionally smoothed ball-only target
    ax = bidir_smooth(rbx, args.cutoff, args.fps, args.order)
    ay = bidir_smooth(rby, args.cutoff, args.fps, args.order)

    # B: blended target = w*ball + (1-w)*player_centroid, then smoothed
    w = compute_w_ball(status, aerial, conf, args.w_det, args.w_pred, args.w_aerial, args.pred_decay)
    w = np.clip(moving_average(w, args.w_smooth), 0.0, 1.0)  # smooth handoffs ball<->mass
    blx, bly = px.copy(), py.copy()
    m = (w > 0) & np.isfinite(bx)
    blx[m] = w[m] * bx[m] + (1 - w[m]) * px[m]
    bly[m] = w[m] * by[m] + (1 - w[m]) * py[m]
    bxs = bidir_smooth(blx, args.cutoff, args.fps, args.order)
    bys = bidir_smooth(bly, args.cutoff, args.fps, args.order)

    # C: B + asymmetric pan limits + dead-zone
    cxc, cyc = asym_rate_limit(bxs, bys, args.vmax, args.a_accel, args.a_decel, args.deadzone)

    variants = {
        "RAW": clamp_centers(rbx.copy(), rby.copy(), cw, ch, W, H),
        "A":   clamp_centers(ax, ay, cw, ch, W, H),
        "B":   clamp_centers(bxs, bys, cw, ch, W, H),
        "C":   clamp_centers(cxc, cyc, cw, ch, W, H),
    }
    meta = dict(cw=cw, ch=ch, W=W, H=H, bx=bx, by=by, status=status, aerial=aerial,
                px=px, py=py, pcount=pcount, w=w, players=players_by_frame)
    return variants, meta


# ======================= metrics (supporting evidence only) =======================
def compute_metrics(centers, meta, gt_ball=None, safe_frac=0.7):
    cx, cy = centers
    cw, ch, W, H = meta["cw"], meta["ch"], meta["W"], meta["H"]
    bx, by, status = meta["bx"], meta["by"], meta["status"]
    n = len(cx)

    # ball-in-safe-zone %: detected ball inside central safe_frac box of the crop
    hw, hh = cw / 2 * safe_frac, ch / 2 * safe_frac
    det = [i for i in range(n) if status[i] == "detected" and np.isfinite(bx[i])]
    insz = sum(1 for i in det if abs(bx[i] - cx[i]) <= hw and abs(by[i] - cy[i]) <= hh)
    ball_safe = insz / len(det) if det else None

    # crop-center jerk (smoothness): mean magnitude of 2nd/3rd derivative
    P = np.stack([cx, cy], axis=1)
    acc = np.diff(P, n=2, axis=0); jerk = np.diff(P, n=3, axis=0)
    mean_acc = float(np.hypot(acc[:, 0], acc[:, 1]).mean())
    mean_jerk = float(np.hypot(jerk[:, 0], jerk[:, 1]).mean())

    # action-in-frame %: fraction of player detections inside the crop, averaged over frames
    fr = []
    for f in range(1, n + 1):
        pl = meta["players"].get(f, [])
        if not pl:
            continue
        i = f - 1
        x0, x1 = cx[i] - cw / 2, cx[i] + cw / 2
        y0, y1 = cy[i] - ch / 2, cy[i] + ch / 2
        inside = sum(1 for c in pl if x0 <= c[0] <= x1 and y0 <= c[1] <= y1)
        fr.append(inside / len(pl))
    action = float(np.mean(fr)) if fr else None

    # clamp fraction: how often the crop is pinned to a frame edge (wanted to go off-frame)
    hwf, hhf = cw / 2.0, ch / 2.0
    clamped = np.mean((cx <= hwf + 0.5) | (cx >= W - hwf - 0.5) |
                      (cy <= hhf + 0.5) | (cy >= H - hhf - 0.5))

    # GT-ball-in-crop %: did the crop keep the *true* ball in shot (full window)?
    gt_in = None
    if gt_ball:
        hit = tot = 0
        for f, v in gt_ball.items():
            if 1 <= f <= n:
                i = f - 1; tot += 1
                if abs(v[0] - cx[i]) <= cw / 2 and abs(v[1] - cy[i]) <= ch / 2:
                    hit += 1
        gt_in = hit / tot if tot else None

    return dict(ball_in_safe_zone=ball_safe, mean_accel_px=mean_acc, mean_jerk_px=mean_jerk,
                action_in_frame=action, clamp_fraction=float(clamped), gt_ball_in_crop=gt_in,
                n_detected=len(det))


# ======================= rendering / visuals =======================
def _crop(img, cx_i, cy_i, cw, ch):
    x0 = int(round(cx_i - cw / 2)); y0 = int(round(cy_i - ch / 2))
    x0 = max(0, min(x0, img.shape[1] - cw)); y0 = max(0, min(y0, img.shape[0] - ch))
    return img[y0:y0 + ch, x0:x0 + cw]


def render_video(seq, centers, cw, ch, source, out_path, out_w, out_h, fps=25, label=None):
    cx, cy = centers
    vw = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (out_w, out_h))
    frames_dir = Path(source) / seq / "img1"
    written = 0
    for i in range(len(cx)):
        img = cv2.imread(str(frames_dir / f"{i + 1:06d}.jpg"))
        if img is None:
            continue
        out = cv2.resize(_crop(img, cx[i], cy[i], cw, ch), (out_w, out_h), interpolation=cv2.INTER_LINEAR)
        if label:
            cv2.putText(out, label, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (40, 240, 40), 2)
        vw.write(out); written += 1
    vw.release()
    return written


def render_montage(seq, variants, cw, ch, source, out_path, seg, tile_w=640, fps=25):
    s, e = seg
    tile_h = int(round(tile_w * ch / cw)); tile_h -= tile_h % 2
    names = ["A", "B", "C"]
    vw = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (tile_w * 3, tile_h))
    frames_dir = Path(source) / seq / "img1"
    for f in range(s, e + 1):
        img = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
        if img is None:
            continue
        tiles = []
        for name in names:
            cx, cy = variants[name]
            t = cv2.resize(_crop(img, cx[f - 1], cy[f - 1], cw, ch), (tile_w, tile_h))
            cv2.putText(t, name, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (40, 240, 40), 2)
            tiles.append(t)
        vw.write(np.hstack(tiles))
    vw.release()


def contact_sheet(seq, centers, cw, ch, source, out_path, n_tiles=12, cols=4, tile_w=480):
    cx, cy = centers
    idxs = np.linspace(0, len(cx) - 1, n_tiles).astype(int)
    tile_h = int(round(tile_w * ch / cw))
    rows = math.ceil(n_tiles / cols)
    sheet = np.zeros((rows * tile_h, cols * tile_w, 3), np.uint8)
    frames_dir = Path(source) / seq / "img1"
    for k, i in enumerate(idxs):
        img = cv2.imread(str(frames_dir / f"{i + 1:06d}.jpg"))
        if img is None:
            continue
        t = cv2.resize(_crop(img, cx[i], cy[i], cw, ch), (tile_w, tile_h))
        cv2.putText(t, f"f{i + 1}", (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (40, 240, 40), 2)
        r, c = divmod(k, cols)
        sheet[r * tile_h:(r + 1) * tile_h, c * tile_w:(c + 1) * tile_w] = t
    cv2.imwrite(str(out_path), sheet)


def abc_frames(seq, variants, cw, ch, source, out_path, frames, tile_w=560):
    """Grid: rows = chosen frames, cols = A/B/C. The committable A/B/C comparison still."""
    names = ["A", "B", "C"]
    tile_h = int(round(tile_w * ch / cw))
    sheet = np.zeros((len(frames) * tile_h, len(names) * tile_w, 3), np.uint8)
    frames_dir = Path(source) / seq / "img1"
    for r, f in enumerate(frames):
        img = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
        if img is None:
            continue
        for c, name in enumerate(names):
            cx, cy = variants[name]
            t = cv2.resize(_crop(img, cx[f - 1], cy[f - 1], cw, ch), (tile_w, tile_h))
            cv2.putText(t, f"{name}  f{f}", (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (40, 240, 40), 2)
            sheet[r * tile_h:(r + 1) * tile_h, c * tile_w:(c + 1) * tile_w] = t
    cv2.imwrite(str(out_path), sheet)


def plot_paths(variants, meta, out_path, seq):
    n = len(meta["bx"]); fr = np.arange(1, n + 1)
    fig, axs = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    cols = {"A": "tab:blue", "B": "tab:green", "C": "tab:red"}
    for ax, raw, key, lbl in [(axs[0], meta["bx"], 0, "x"), (axs[1], meta["by"], 1, "y")]:
        ax.plot(fr, raw, color="0.75", lw=0.8, label="raw ball")
        for name, col in cols.items():
            ax.plot(fr, variants[name][key], color=col, lw=1.4, label=f"{name}")
        ax.set_ylabel(f"crop-center {lbl} (px)"); ax.grid(alpha=0.3)
    axs[0].legend(loc="upper right", ncol=4); axs[1].set_xlabel("frame")
    axs[0].set_title(f"{seq}: crop-center path (raw ball vs A/B/C) -- lower wiggle = smoother")
    fig.tight_layout(); fig.savefig(out_path, dpi=110); plt.close(fig)


def plot_speed(variants, out_path, seq):
    fig, ax = plt.subplots(figsize=(14, 5))
    for name, col in [("RAW", "0.6"), ("A", "tab:blue"), ("B", "tab:green"), ("C", "tab:red")]:
        cx, cy = variants[name]
        v = np.hypot(np.diff(cx), np.diff(cy))
        ax.plot(np.arange(1, len(v) + 1), v, color=col, lw=1.1, label=f"{name} (mean {v.mean():.2f})")
    ax.set_ylabel("crop-center speed (px/frame)"); ax.set_xlabel("frame")
    ax.set_title(f"{seq}: pan speed -- spikes = whip-pans"); ax.grid(alpha=0.3); ax.legend()
    fig.tight_layout(); fig.savefig(out_path, dpi=110); plt.close(fig)


# ======================= main =======================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="?", default=None, help="single seq (omit -> default set)")
    ap.add_argument("--ball-dir", default="outputs/ball_track")
    ap.add_argument("--track-dir", default="outputs/track_results/sn_soccana_botsort_gmc")
    ap.add_argument("--source", default="datasets/soccernet_tracking")
    ap.add_argument("--gt-zip", default="datasets/soccernet_gsr/test.zip")
    ap.add_argument("--out", default="outputs/follow_cam")
    ap.add_argument("--fps", type=int, default=25)
    # crop / output
    ap.add_argument("--zoom", type=float, default=2.5, help="crop_w = frame_w / zoom")
    ap.add_argument("--out-w", type=int, default=1280)
    ap.add_argument("--out-h", type=int, default=720)
    # smoothing
    ap.add_argument("--cutoff", type=float, default=0.8, help="bidir low-pass cutoff (Hz)")
    ap.add_argument("--order", type=int, default=2, help="Butterworth order (filtfilt doubles it)")
    # blend weights (aerial-suppressed: B/C stay stabilized; A is the ball-faithful variant)
    ap.add_argument("--w-det", type=float, default=0.92)
    ap.add_argument("--w-pred", type=float, default=0.65)
    ap.add_argument("--w-aerial", type=float, default=0.30)
    ap.add_argument("--pred-decay", type=float, default=8.0, help="predict-streak weight decay (frames)")
    ap.add_argument("--w-smooth", type=int, default=7, help="MA window on w_ball (frames)")
    # part C
    ap.add_argument("--vmax", type=float, default=30.0, help="max pan speed (px/frame)")
    ap.add_argument("--a-accel", type=float, default=3.0, help="accel-in cap (px/frame^2)")
    ap.add_argument("--a-decel", type=float, default=1.5, help="decel-out cap (px/frame^2)")
    ap.add_argument("--deadzone", type=float, default=6.0, help="soft dead-zone (px)")
    # rendering
    ap.add_argument("--render", dest="render", action="store_true", default=True)
    ap.add_argument("--no-render", dest="render", action="store_false")
    ap.add_argument("--variants", default="C", help="which variants to render as video, e.g. A,B,C")
    ap.add_argument("--segment", default=None, help="montage segment 'start-end' (default auto)")
    args = ap.parse_args()

    seqs = [args.seq] if args.seq else SEQS_DEFAULT
    overall = {}
    for seq in seqs:
        print(f"\n=== {seq} ===")
        out_seq = Path(args.out) / seq
        out_seq.mkdir(parents=True, exist_ok=True)

        recs = load_ball(Path(args.ball_dir), seq)
        players = load_players(Path(args.track_dir) / f"{seq}.txt")
        n = len(recs)
        # frame size from a real frame
        img0 = cv2.imread(str(Path(args.source) / seq / "img1" / "000001.jpg"))
        H, W = img0.shape[:2]

        variants, meta = build_variants(recs, players, args, W, H)
        print(f"  frames={n}  frame={W}x{H}  crop={meta['cw']}x{meta['ch']} (zoom {args.zoom})")
        st = {s: meta["status"].count(s) for s in ("detected", "predicted", "lost")}
        print(f"  ball status: {st}  mean w_ball={meta['w'].mean():.2f}")

        gt_ball = None
        if Path(args.gt_zip).exists():
            try:
                gt_ball = {f: (v[0], v[1]) for f, v in load_ball_gt(Path(args.gt_zip), seq).items()}
            except Exception as ex:
                print(f"  (GT ball load skipped: {ex})")

        metrics = {name: compute_metrics(variants[name], meta, gt_ball) for name in ("RAW", "A", "B", "C")}
        print("  metric           RAW      A        B        C")
        def row(lbl, key, fmt="{:.3f}"):
            vals = "  ".join(
                (fmt.format(metrics[v][key]) if metrics[v][key] is not None else "  --  ").rjust(7)
                for v in ("RAW", "A", "B", "C"))
            print(f"  {lbl:<15} {vals}")
        row("jerk(px)", "mean_jerk_px", "{:.4f}")
        row("accel(px)", "mean_accel_px", "{:.3f}")
        row("ball_safezone", "ball_in_safe_zone")
        row("gt_ball_in_crop", "gt_ball_in_crop")
        row("action_in_frame", "action_in_frame")
        row("clamp_frac", "clamp_fraction")

        # perceptual artifacts (always -- these are how we 'watch' it)
        plot_paths(variants, meta, out_seq / "path_plot.png", seq)
        plot_speed(variants, out_seq / "speed_plot.png", seq)
        contact_sheet(seq, variants["C"], meta["cw"], meta["ch"], args.source, out_seq / "contact_sheet_C.png")
        # pick 4 spread frames for the A/B/C grid
        abc_fr = [int(x) for x in np.linspace(int(n * 0.15), int(n * 0.85), 4)]
        abc_frames(seq, variants, meta["cw"], meta["ch"], args.source, out_seq / "abc_frames.png", abc_fr)
        print(f"  wrote path_plot / speed_plot / contact_sheet_C / abc_frames (frames {abc_fr})")

        # persist ALL THREE crop paths -> feeds highlights / event reels later.
        # (A = ball-faithful incl. shots/high balls; B/C = stabilized. Downstream picks.)
        (out_seq / "follow_cam.json").write_text(json.dumps({
            "seq": seq, "frame_w": W, "frame_h": H, "crop_w": meta["cw"], "crop_h": meta["ch"],
            "fps": args.fps,
            "variants": {name: [{"frame": i + 1, "cx": float(variants[name][0][i]),
                                 "cy": float(variants[name][1][i])} for i in range(n)]
                         for name in ("A", "B", "C")},
        }))
        (out_seq / "metrics.json").write_text(json.dumps(metrics, indent=2))
        overall[seq] = metrics

        if args.render:
            for name in [v.strip() for v in args.variants.split(",") if v.strip()]:
                w = render_video(seq, variants[name], meta["cw"], meta["ch"], args.source,
                                 out_seq / f"follow_{name}.mp4", args.out_w, args.out_h,
                                 fps=args.fps, label=f"{seq}  follow-cam {name}")
                print(f"  rendered follow_{name}.mp4 ({w} frames)")
            seg = ([int(x) for x in args.segment.split("-")] if args.segment
                   else [int(n * 0.30), int(n * 0.30) + min(250, int(n * 0.4))])
            render_montage(seq, variants, meta["cw"], meta["ch"], args.source,
                           out_seq / "abc_montage.mp4", seg)
            print(f"  rendered abc_montage.mp4 (frames {seg[0]}-{seg[1]})")

    # combined
    if len(overall) > 1:
        print(f"\n=== combined ({len(overall)} seqs) ===")
        for key in ("mean_jerk_px", "ball_in_safe_zone", "gt_ball_in_crop", "action_in_frame"):
            for v in ("RAW", "A", "B", "C"):
                vals = [overall[s][v][key] for s in overall if overall[s][v][key] is not None]
                if vals:
                    print(f"  {key:<18} {v}: mean={np.mean(vals):.4f}")


if __name__ == "__main__":
    main()
