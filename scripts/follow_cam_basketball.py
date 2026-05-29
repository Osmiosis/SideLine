"""Day 15: broadcast-style FOLLOW-CAM (virtual camera) for BASKETBALL, SportsMOT.

Basketball parity with the football Day-13 follow-cam (`scripts/follow_cam.py`). Same
VEO/Pixellot dual-wide -> digital-crop architecture, same FIXED braking-distance pan
limiter, same bidirectional lookahead smoothing. THREE DISTINCT feeds, mapped to the
user's two-feed deliverable strategy:

  A -- ball-faithful + POSSESSION-HANDOFF  (gameplay / event highlights)   <-- the new piece
  B -- ball+player confidence-weighted blend (intermediate, for comparison)
  C -- player-stabilized, heavily smoothed   (player highlights / celebrations)

THE HYPOTHESIS UNDER TEST (Day-15):
  Day-14 gave basketball a ball track that tracks well on dribbles/passes/shots but DROPS
  on held/occluded ball (hands hide it -> 14-30 frame no-detection runs). Rather than jump
  straight to TrackNet, we test the cheaper POSSESSION-HANDOFF: when the ball is held/lost,
  follow the player who LAST held it (a held ball IS at that player) until it reappears.
  If that makes held-ball moments watchable in the A-feed -> TrackNet is unneeded. If not ->
  TrackNet is justified WITH EVIDENCE (the pre-set escalation trigger).

A-feed possession-handoff target logic (per frame):
  1. ball status 'detected'                         -> target = ball; (re)bind holder = nearest
                                                        player to the ball (within bind_radius).
  2. ball status 'predicted' AND within short gap   -> target = (Kalman) ball pos.
  3. ball lost (or long predict) AND holder known
     AND holder track present this frame            -> target = LAST-HOLDER player pos (handoff).
  4. ball lost long / no holder / holder track gone  -> target = team centroid (trimmed mean).
  All resolved targets are then bidirectionally smoothed, asymmetric-rate-limited (the FIXED,
  non-oscillating braking-distance limiter) + dead-zoned, and clamped inside the frame.

Basketball-specific tuning vs football Day-13 (re-tuned by eye, NOT football constants):
  - 1280x720 source (football 1920x1080); tighter crop (zoom ~1.9) -- court is smaller.
  - Faster pace / quicker reversals -> higher pan-velocity cap (vmax up), slightly higher accel.
  - `shot_flag` (Day-14) plays the role football's `aerial_suspect` did: A chases the shot;
    B/C suppress it to stay grounded/stabilized (keeps the three variants distinct).

Evaluation is PERCEPTUAL (no GT crop, and basketball has NO per-frame ungated ball GT --
Day-14 was plausibility-validated). The eye is the arbiter: we render videos + montage +
contact sheet + path/speed plots. Proxy metrics (crop-center jerk, action-in-frame %,
edge-clamp %) are SUPPORTING evidence only. Watch the HELD-BALL moments specifically.

Inputs:
  outputs/ball_track_bb/<seq>/trajectory.json                 (Day 14: pixel ball + status + shot_flag)
  outputs/track_results/bb_ftdet_botsort_gmc/<seq>.txt        (Day 9: basketball player tracks, MOT)
  datasets/sportsmot_basketball/<seq>/img1/<frame>.jpg        (wide frames, 1280x720)

Outputs (outputs/follow_cam_bb/<seq>/, gitignored except committed sample frames):
  follow_cam.json     A/B/C crop-center paths (+ A-feed per-frame target source)
  metrics.json        RAW/A/B/C proxy metrics + A-feed handoff source breakdown
  path_plot.png       crop-center x,y vs frame (raw ball vs A/B/C)
  speed_plot.png      crop-center speed vs frame (whip-pans = spikes)
  handoff_plot.png    A-feed target source over time (ball / pred / holder / centroid)
  contact_sheet_A.png 12 A-feed crops across the clip
  abc_frames.png      A vs B vs C at a few moments
  follow_<variant>.mp4 / abc_montage.mp4   rendered crops (local; *.mp4 gitignored)

Usage:
  python scripts/follow_cam_basketball.py v_00HRwkvvjtQ_c001 --no-render   # fast: metrics+plots
  python scripts/follow_cam_basketball.py v_00HRwkvvjtQ_c001               # + render videos
  python scripts/follow_cam_basketball.py                                  # default seq pair
"""
import argparse, json, math, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
# reuse the football signal helpers VERBATIM (the FIXED limiter, bidir smoother, etc.)
from follow_cam import (
    interp_fill, moving_average, bidir_smooth, clamp_centers, asym_rate_limit,
    player_centroid, compute_w_ball, contact_sheet, render_video, render_montage,
    abc_frames, plot_speed,
)

SEQS_DEFAULT = ["v_00HRwkvvjtQ_c001", "v_00HRwkvvjtQ_c007"]
SRC_COLS = {"ball": (40, 240, 40), "pred": (40, 200, 240), "holder": (40, 120, 255),
            "centroid": (200, 80, 200)}


# ======================= loaders (basketball) =======================
def load_ball(ball_dir: Path, seq: str):
    return json.loads((Path(ball_dir) / seq / "trajectory.json").read_text())


def load_players_id(track_path: Path):
    """MOT output -> two views in PIXEL space (bbox centers):
       by_frame      {frame: [(cx, cy, w, h), ...]}        (for centroid; football-compatible)
       by_frame_id   {frame: [(id, cx, cy), ...]}          (for nearest-player holder binding)
       by_id         {id: {frame: (cx, cy)}}               (for per-holder lookup over time)"""
    by_frame = defaultdict(list)
    by_frame_id = defaultdict(list)
    by_id = defaultdict(dict)
    for line in Path(track_path).read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(",")
        f = int(p[0]); tid = int(p[1])
        x = float(p[2]); y = float(p[3]); w = float(p[4]); h = float(p[5])
        cx, cy = x + w / 2, y + h / 2
        by_frame[f].append((cx, cy, w, h))
        by_frame_id[f].append((tid, cx, cy))
        by_id[tid][f] = (cx, cy)
    return by_frame, by_frame_id, by_id


# ======================= ball arrays (basketball) =======================
def ball_arrays(recs):
    """Like football's, but basketball carries `shot_flag` instead of `aerial_suspect`.
    shot_flag is returned in the `shot` slot and used exactly where football used aerial."""
    n = len(recs)
    bx = np.full(n, np.nan); by = np.full(n, np.nan)
    shot = np.zeros(n, bool); conf = np.zeros(n); status = []
    for i, r in enumerate(recs):
        status.append(r["status"])
        shot[i] = bool(r.get("shot_flag"))
        if r.get("x") is not None:
            bx[i] = r["x"]; by[i] = r["y"]
        if r.get("picked_conf") is not None:
            conf[i] = r["picked_conf"]
    return bx, by, status, shot, conf


# ======================= A-feed: possession-handoff target =======================
def build_handoff_target(bx, by, status, by_frame_id, by_id, px, py,
                         short_pred_gap, holder_max_hold, bind_radius):
    """Resolve the A-feed target per frame via the possession-handoff cascade.

    Returns (tx, ty, src, holder_ids) where:
      tx,ty       resolved target path (may still hold NaN only if even centroid is NaN -> filled later)
      src         per-frame source label in {'ball','pred','holder','centroid'}
      holder_ids  per-frame bound holder track id (or -1)

    Holder semantics (PRD): last-holder = nearest player to the last CONFIDENT ball detection;
    PERSIST the holder id until the ball reappears (rebinds) or the holder track ends / a long
    no-confident-ball gap elapses (-> centroid). Predicted ball within `short_pred_gap` frames of
    the last detection is still trusted as 'on the ball'."""
    n = len(status)
    tx = np.full(n, np.nan); ty = np.full(n, np.nan)
    src = ["centroid"] * n
    holder_ids = np.full(n, -1, int)

    holder_id = None
    frames_since_conf = 10 ** 9  # frames since last 'detected'

    for i in range(n):
        f = i + 1
        s = status[i]
        if s == "detected" and np.isfinite(bx[i]):
            # (re)bind holder = nearest player to the confident ball, within bind_radius
            best_id, best_d = None, bind_radius
            for tid, cx, cy in by_frame_id.get(f, []):
                d = math.hypot(cx - bx[i], cy - by[i])
                if d <= best_d:
                    best_d = d; best_id = tid
            if best_id is not None:
                holder_id = best_id
            tx[i], ty[i] = bx[i], by[i]
            src[i] = "ball"; frames_since_conf = 0
        elif s == "predicted" and np.isfinite(bx[i]) and frames_since_conf < short_pred_gap:
            tx[i], ty[i] = bx[i], by[i]
            src[i] = "pred"; frames_since_conf += 1
        else:
            frames_since_conf += 1
            pos = by_id.get(holder_id, {}).get(f) if holder_id is not None else None
            if pos is not None and frames_since_conf <= holder_max_hold:
                tx[i], ty[i] = pos
                src[i] = "holder"
            else:
                tx[i], ty[i] = px[i], py[i]
                src[i] = "centroid"
        if holder_id is not None:
            holder_ids[i] = holder_id
    return interp_fill(tx), interp_fill(ty), src, holder_ids


# ======================= variant construction =======================
def build_variants(recs, by_frame, by_frame_id, by_id, args, W, H):
    n = len(recs)
    cw = int(round(W / args.zoom)); cw -= cw % 2
    ch = int(round(cw * H / W)); ch -= ch % 2  # match frame aspect (16:9 on 1280x720)

    bx, by, status, shot, conf = ball_arrays(recs)
    px, py, pcount = player_centroid(by_frame, n)

    # RAW: naive ball-center, gaps linearly filled (the thing we must NOT ship)
    rbx, rby = interp_fill(bx), interp_fill(by)

    # A: ball-faithful + possession-handoff -> smooth -> FIXED limiter -> clamp
    hx, hy, src, holder_ids = build_handoff_target(
        bx, by, status, by_frame_id, by_id, px, py,
        args.short_pred_gap, args.holder_max_hold, args.bind_radius)
    ax = bidir_smooth(hx, args.cutoff, args.fps, args.order)
    ay = bidir_smooth(hy, args.cutoff, args.fps, args.order)
    ax, ay = asym_rate_limit(ax, ay, args.vmax, args.a_accel, args.a_decel, args.deadzone)

    # B: confidence-weighted blend (Day-13), shot-suppressed so B stays grounded
    w = compute_w_ball(status, shot, conf, args.w_det, args.w_pred, args.w_aerial, args.pred_decay)
    w = np.clip(moving_average(w, args.w_smooth), 0.0, 1.0)
    blx, bly = px.copy(), py.copy()
    m = (w > 0) & np.isfinite(bx)
    blx[m] = w[m] * bx[m] + (1 - w[m]) * px[m]
    bly[m] = w[m] * by[m] + (1 - w[m]) * py[m]
    bxs = bidir_smooth(blx, args.cutoff, args.fps, args.order)
    bys = bidir_smooth(bly, args.cutoff, args.fps, args.order)
    bxs, bys = asym_rate_limit(bxs, bys, args.vmax, args.a_accel, args.a_decel, args.deadzone)

    # C: player-stabilized -- centroid-led, HEAVILY smoothed (lower cutoff). No ball, no handoff.
    cx0 = bidir_smooth(px, args.cutoff_c, args.fps, args.order)
    cy0 = bidir_smooth(py, args.cutoff_c, args.fps, args.order)
    cxc, cyc = asym_rate_limit(cx0, cy0, args.vmax, args.a_accel, args.a_decel, args.deadzone)

    variants = {
        "RAW": clamp_centers(rbx.copy(), rby.copy(), cw, ch, W, H),
        "A":   clamp_centers(ax, ay, cw, ch, W, H),
        "B":   clamp_centers(bxs, bys, cw, ch, W, H),
        "C":   clamp_centers(cxc, cyc, cw, ch, W, H),
    }
    meta = dict(cw=cw, ch=ch, W=W, H=H, bx=bx, by=by, status=status, aerial=shot,
                px=px, py=py, pcount=pcount, w=w, players=by_frame,
                a_src=src, holder_ids=holder_ids)
    return variants, meta


# ======================= metrics =======================
def _center_box_dist(px, py, c):
    """Distance from point to a player box given as center+size (cx,cy,w,h); 0 if inside."""
    cx, cy, w, h = c[0], c[1], c[2], c[3]
    dx = max(abs(px - cx) - w / 2, 0.0)
    dy = max(abs(py - cy) - h / 2, 0.0)
    return math.hypot(dx, dy)


def _in_head_zone_c(px, py, c, frac_h=0.18, frac_w=0.6):
    """Head-zone test for a player given as center+size (cx,cy,w,h): top frac_h, central frac_w."""
    cx, cy, w, h = c[0], c[1], c[2], c[3]
    y0 = cy - h / 2
    return (y0 <= py <= y0 + frac_h * h) and (abs(px - cx) <= frac_w * w / 2)


def a_feed_fp_latch(meta, prox_px=150.0, head_frac_h=0.18, head_frac_w=0.6):
    """PRIMARY-honesty metric: fraction of frames where the A-feed is centered on a 'ball' target
    that is FP-suspect -- either far from EVERY player box (Day-16 corner FP) OR in a player's HEAD
    zone (Day-17 head FP). A smooth camera pointed at a false ball scores HIGH here; this is the
    number jerk could not catch."""
    bx, by, src, players = meta["bx"], meta["by"], meta["a_src"], meta["players"]
    n = len(src); latched = no_player = head = 0; ball_frames = 0
    for i in range(n):
        if src[i] != "ball" or not np.isfinite(bx[i]):
            continue
        ball_frames += 1
        boxes = players.get(i + 1, [])
        if not boxes:
            continue
        is_noplayer = min(_center_box_dist(bx[i], by[i], c) for c in boxes) > prox_px
        is_head = any(_in_head_zone_c(bx[i], by[i], c, head_frac_h, head_frac_w) for c in boxes)
        if is_noplayer or is_head:
            latched += 1
            no_player += int(is_noplayer); head += int(is_head)
    return dict(fp_latch_rate=latched / n if n else None, fp_latched_frames=latched,
                fp_noplayer=no_player, fp_head=head,
                ball_target_frames=ball_frames, prox_px=prox_px)


def compute_metrics(centers, meta, safe_frac=0.7):
    cx, cy = centers
    cw, ch, W, H = meta["cw"], meta["ch"], meta["W"], meta["H"]
    bx, by, status = meta["bx"], meta["by"], meta["status"]
    n = len(cx)

    hw, hh = cw / 2 * safe_frac, ch / 2 * safe_frac
    det = [i for i in range(n) if status[i] == "detected" and np.isfinite(bx[i])]
    insz = sum(1 for i in det if abs(bx[i] - cx[i]) <= hw and abs(by[i] - cy[i]) <= hh)
    ball_safe = insz / len(det) if det else None

    P = np.stack([cx, cy], axis=1)
    acc = np.diff(P, n=2, axis=0); jerk = np.diff(P, n=3, axis=0)
    mean_acc = float(np.hypot(acc[:, 0], acc[:, 1]).mean())
    mean_jerk = float(np.hypot(jerk[:, 0], jerk[:, 1]).mean())

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

    hwf, hhf = cw / 2.0, ch / 2.0
    clamped = np.mean((cx <= hwf + 0.5) | (cx >= W - hwf - 0.5) |
                      (cy <= hhf + 0.5) | (cy >= H - hhf - 0.5))

    return dict(ball_in_safe_zone=ball_safe, mean_accel_px=mean_acc, mean_jerk_px=mean_jerk,
                action_in_frame=action, clamp_fraction=float(clamped), n_detected=len(det))


# ======================= visuals =======================
def plot_paths(variants, meta, out_path, seq):
    n = len(meta["bx"]); fr = np.arange(1, n + 1)
    fig, axs = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    cols = {"A": "tab:blue", "B": "tab:green", "C": "tab:red"}
    for ax, key, lbl in [(axs[0], 0, "x"), (axs[1], 1, "y")]:
        raw = meta["bx"] if key == 0 else meta["by"]
        ax.plot(fr, raw, color="0.75", lw=0.8, label="raw ball")
        for name, col in cols.items():
            ax.plot(fr, variants[name][key], color=col, lw=1.4, label=f"{name}")
        ax.set_ylabel(f"crop-center {lbl} (px)"); ax.grid(alpha=0.3)
    axs[0].legend(loc="upper right", ncol=4); axs[1].set_xlabel("frame")
    axs[0].set_title(f"{seq}: crop-center path (raw ball vs A/B/C) -- lower wiggle = smoother")
    fig.tight_layout(); fig.savefig(out_path, dpi=110); plt.close(fig)


def plot_handoff(meta, out_path, seq):
    """A-feed target source over time -- the held-ball-handoff story, at a glance."""
    n = len(meta["a_src"]); fr = np.arange(1, n + 1)
    order = ["ball", "pred", "holder", "centroid"]
    yof = {s: k for k, s in enumerate(order)}
    fig, ax = plt.subplots(figsize=(14, 3.2))
    for s in order:
        xs = [fr[i] for i in range(n) if meta["a_src"][i] == s]
        ys = [yof[s]] * len(xs)
        ax.scatter(xs, ys, s=8, color=np.array(SRC_COLS[s][::-1]) / 255.0,
                   label=f"{s} ({len(xs)})")
    ax.set_yticks(range(len(order))); ax.set_yticklabels(order)
    ax.set_xlabel("frame"); ax.set_ylim(-0.5, len(order) - 0.5); ax.grid(alpha=0.3, axis="x")
    ax.set_title(f"{seq}: A-feed target source per frame (held-ball -> 'holder' is the handoff)")
    ax.legend(loc="upper right", ncol=4, fontsize=8)
    fig.tight_layout(); fig.savefig(out_path, dpi=110); plt.close(fig)


# ======================= main =======================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="?", default=None)
    ap.add_argument("--ball-dir", default="outputs/ball_track_bb")
    ap.add_argument("--track-dir", default="outputs/track_results/bb_ftdet_botsort_gmc")
    ap.add_argument("--source", default="datasets/sportsmot_basketball")
    ap.add_argument("--out", default="outputs/follow_cam_bb")
    ap.add_argument("--fps", type=int, default=25)
    # crop / output -- BASKETBALL: tighter crop than football (court smaller)
    ap.add_argument("--zoom", type=float, default=2.0, help="crop_w = frame_w / zoom (2.0 -> clean 640x360 half-frame)")
    ap.add_argument("--out-w", type=int, default=1280)
    ap.add_argument("--out-h", type=int, default=720)
    # smoothing
    ap.add_argument("--cutoff", type=float, default=0.9, help="A/B bidir low-pass cutoff (Hz)")
    ap.add_argument("--cutoff-c", type=float, default=0.5, help="C heavier smoothing cutoff (Hz)")
    ap.add_argument("--order", type=int, default=2)
    # possession-handoff (A-feed)
    ap.add_argument("--short-pred-gap", type=int, default=8,
                    help="trust predicted ball this many frames past last detection (Day-14 gap)")
    ap.add_argument("--holder-max-hold", type=int, default=50,
                    help="follow last-holder up to this many frames of no-confident-ball, then centroid")
    ap.add_argument("--bind-radius", type=float, default=180.0,
                    help="max px from ball to bind a player as holder (else keep prior holder)")
    # blend weights (B) -- shot-suppressed so B/C stay grounded; A is the ball-faithful variant
    ap.add_argument("--w-det", type=float, default=0.92)
    ap.add_argument("--w-pred", type=float, default=0.60)
    ap.add_argument("--w-aerial", type=float, default=0.30, help="weight cap when shot_flag set")
    ap.add_argument("--pred-decay", type=float, default=6.0)
    ap.add_argument("--w-smooth", type=int, default=7)
    # FIXED braking-distance limiter -- BASKETBALL: faster pace -> higher caps than football
    ap.add_argument("--vmax", type=float, default=40.0, help="max pan speed (px/frame)")
    ap.add_argument("--a-accel", type=float, default=4.0, help="accel-in cap (px/frame^2)")
    ap.add_argument("--a-decel", type=float, default=2.0, help="decel-out cap (px/frame^2)")
    ap.add_argument("--deadzone", type=float, default=6.0, help="soft dead-zone (px)")
    ap.add_argument("--fp-prox", type=float, default=150.0,
                    help="A-feed FP-latch metric: ball-target farther than this from every player = FP-latched")
    # rendering
    ap.add_argument("--render", dest="render", action="store_true", default=True)
    ap.add_argument("--no-render", dest="render", action="store_false")
    ap.add_argument("--variants", default="A,C", help="which variants to render as video")
    ap.add_argument("--segment", default=None, help="montage segment 'start-end' (default auto)")
    args = ap.parse_args()

    seqs = [args.seq] if args.seq else SEQS_DEFAULT
    overall = {}
    for seq in seqs:
        print(f"\n=== {seq} ===")
        out_seq = Path(args.out) / seq
        out_seq.mkdir(parents=True, exist_ok=True)

        recs = load_ball(Path(args.ball_dir), seq)
        by_frame, by_frame_id, by_id = load_players_id(Path(args.track_dir) / f"{seq}.txt")
        n = len(recs)
        img0 = cv2.imread(str(Path(args.source) / seq / "img1" / "000001.jpg"))
        H, W = img0.shape[:2]

        variants, meta = build_variants(recs, by_frame, by_frame_id, by_id, args, W, H)
        print(f"  frames={n}  frame={W}x{H}  crop={meta['cw']}x{meta['ch']} (zoom {args.zoom})")
        st = {s: meta["status"].count(s) for s in ("detected", "predicted", "lost")}
        print(f"  ball status: {st}  mean w_ball={meta['w'].mean():.2f}  shots={int(meta['aerial'].sum())}")
        # A-feed handoff breakdown -- the hypothesis evidence
        from collections import Counter
        sc = Counter(meta["a_src"])
        print(f"  A-feed target source: ball={sc['ball']} pred={sc['pred']} "
              f"holder={sc['holder']} centroid={sc['centroid']}  "
              f"(handoff covers {sc['holder']} held/lost frames = {sc['holder']/n*100:.1f}%)")

        metrics = {name: compute_metrics(variants[name], meta) for name in ("RAW", "A", "B", "C")}
        metrics["A_handoff_source"] = dict(sc)
        # Day-16 PRIMARY A-feed metric: is the camera on the REAL ball? (caught the Day-15 wobble)
        fp_latch = a_feed_fp_latch(meta, args.fp_prox)
        metrics["A_fp_latch"] = fp_latch
        print("  metric           RAW      A        B        C")
        def row(lbl, key, fmt="{:.3f}"):
            vals = "  ".join(
                (fmt.format(metrics[v][key]) if metrics[v][key] is not None else "  --  ").rjust(7)
                for v in ("RAW", "A", "B", "C"))
            print(f"  {lbl:<15} {vals}")
        row("ball_safezone*", "ball_in_safe_zone")   # * PRIMARY: crop centered on the real ball
        print(f"  >> A-feed FP-latch rate (PRIMARY truth metric): {fp_latch['fp_latch_rate']*100:.1f}%  "
              f"({fp_latch['fp_latched_frames']} frames on a FP ball: no-player={fp_latch['fp_noplayer']} head={fp_latch['fp_head']})")
        row("action_in_frame", "action_in_frame")
        row("clamp_frac", "clamp_fraction")
        row("jerk(px) [2nd]", "mean_jerk_px", "{:.4f}")  # SECONDARY: smoothness only
        row("accel(px) [2nd]", "mean_accel_px", "{:.3f}")

        plot_paths(variants, meta, out_seq / "path_plot.png", seq)
        plot_speed(variants, out_seq / "speed_plot.png", seq)
        plot_handoff(meta, out_seq / "handoff_plot.png", seq)
        contact_sheet(seq, variants["A"], meta["cw"], meta["ch"], args.source, out_seq / "contact_sheet_A.png")
        abc_fr = [int(x) for x in np.linspace(int(n * 0.15), int(n * 0.85), 4)]
        abc_frames(seq, variants, meta["cw"], meta["ch"], args.source, out_seq / "abc_frames.png", abc_fr)
        print(f"  wrote path_plot / speed_plot / handoff_plot / contact_sheet_A / abc_frames (frames {abc_fr})")

        (out_seq / "follow_cam.json").write_text(json.dumps({
            "seq": seq, "frame_w": W, "frame_h": H, "crop_w": meta["cw"], "crop_h": meta["ch"],
            "fps": args.fps,
            "variants": {name: [{"frame": i + 1, "cx": float(variants[name][0][i]),
                                 "cy": float(variants[name][1][i])} for i in range(n)]
                         for name in ("A", "B", "C")},
            "a_feed_source": [{"frame": i + 1, "src": meta["a_src"][i],
                               "holder_id": int(meta["holder_ids"][i])} for i in range(n)],
        }))
        (out_seq / "metrics.json").write_text(json.dumps(metrics, indent=2))
        overall[seq] = metrics

        if args.render:
            for name in [v.strip() for v in args.variants.split(",") if v.strip()]:
                wn = render_video(seq, variants[name], meta["cw"], meta["ch"], args.source,
                                  out_seq / f"follow_{name}.mp4", args.out_w, args.out_h,
                                  fps=args.fps, label=f"{seq}  follow-cam {name}")
                print(f"  rendered follow_{name}.mp4 ({wn} frames)")
            seg = ([int(x) for x in args.segment.split("-")] if args.segment
                   else [int(n * 0.30), int(n * 0.30) + min(250, int(n * 0.4))])
            render_montage(seq, variants, meta["cw"], meta["ch"], args.source,
                           out_seq / "abc_montage.mp4", seg)
            print(f"  rendered abc_montage.mp4 (frames {seg[0]}-{seg[1]})")

    if len(overall) > 1:
        print(f"\n=== combined ({len(overall)} seqs) ===")
        for key in ("mean_jerk_px", "ball_in_safe_zone", "action_in_frame", "clamp_fraction"):
            for v in ("RAW", "A", "B", "C"):
                vals = [overall[s][v][key] for s in overall if overall[s][v][key] is not None]
                if vals:
                    print(f"  {key:<18} {v}: mean={np.mean(vals):.4f}")


if __name__ == "__main__":
    main()
