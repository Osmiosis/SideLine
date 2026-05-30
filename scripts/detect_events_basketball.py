"""Day 25: BASKETBALL event detection + interest ranking (output #3 parity).

Basketball half of the event-highlight output. Reuses the Day-24 football architecture
(motion features -> high-recall detectors -> clip from A-feed -> curation package) and ALL its
hard-won lessons, basketball-tuned. The Day-24 lessons matter MORE here (occlusion-heavy ball):
  - LOST BALL = DEAD/UNKNOWN, never interpolated into fake velocity (speed zeroed where missing).
  - SHOT = ball-launch-into-gap, anchored to the LAUNCH (last detected frame before the ball
    vanishes), not the late speed/arrival peak -> the clip shows the shooter, not the aftermath.
  - teleport guards, peak-proximity clustering, generous pre-roll.

Basketball-different:
  - Shot-DENSE -> high-recall CAPTURE + INTEREST RANKING (made-basket/fast-break/block top,
    routine attempts bottom) so the StuCo editor skims ranked, isn't drowned.
  - 'likely made basket' is more detectable than football's goal: ball reaches a KNOWN hoop zone
    (from Day-21 court homography) + play reverses. Still plausibility-level, never "confirmed score".
  - vocab: shot_attempt, likely_made_basket, fast_break, steal_proxy, block_proxy. Honest tiers.

Honest tiers:
  Tier 1 (kinematic):  shot_attempt, fast_break
  Tier 2 (proxy):      likely_made_basket (NOT a confirmed score), block_proxy, steal_proxy
  Tier 3 (NOT built):  fouls (referee judgment -> AUDIO lever, same as football), travels/etc.

Reuses (no re-detection/tracking):
  outputs/ball_track_bb/<seq>/trajectory.json                 Day-19 ball (pixel, head-FP-cleaned)
  outputs/track_results/bball_ftdet_bytetrack/<seq>.txt       Day-9 players (MOT)
  outputs/team_assign_bb/track_teams_emb.json                 Day-23 teams (embeddings)
  outputs/deliverables/<seq>/court/homography.json            Day-21 court (pixel<->court meters)
  scripts/detect_events.py helpers (_runs, smooth, interp_nan, majority_smooth)

Outputs (outputs/events_bb/<seq>/):
  features.json   per-frame motion features (Part A)
  events.json     RANKED candidate moments (start,end,type,confidence,interest) (Part B)
  features_plot.png  ball court-speed + dist-to-hoop + possession (plausibility)

Usage:
  python scripts/detect_events_basketball.py v_00HRwkvvjtQ_c007
"""
import argparse, json, sys
from collections import defaultdict, Counter
from pathlib import Path
import numpy as np
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
from detect_events import _runs, smooth, interp_nan, majority_smooth  # reuse Day-24 helpers

SEQS_DEFAULT = ["v_00HRwkvvjtQ_c007"]   # only c007 has a saved court homography (hoop calibration)
FPS = 25

# ---- basketball geometry / guards (ALL camera-scale + court-marking dependent -> RE-TUNE at DPS) ----
COURT_HALF_X = 14.325         # m; NCAA half-length (baseline at x=+/-14.325), hoop axis
HOOP_X = 12.75                # m; hoop 1.575 m off the baseline, centered on width (y=0)
HOOPS_COURT = {"right": (HOOP_X, 0.0), "left": (-HOOP_X, 0.0)}
BALL_TELEPORT_MPS = 25.0      # m/s; basketball ball rarely > ~15-20; above = homography-noise teleport
NEAR_HOOP_M       = 1.8       # m; ball within this of hoop center = "at the rim" (shot/make zone)
SHOT_APPROACH_M   = 4.0       # m; flight must close at least this much toward the hoop
POSSESS_MAX_M     = 3.0       # m; nearest on-court player within this of ball -> possession (Day-20/21)
CONVERGE_M        = 4.0       # m; players within this of ball counted (block/contest)
MADE_REVERSE_FR   = 50        # frames (~2s) after rim to look for play-reversal/possession-flip
FASTBREAK_SPD     = 6.0       # m/s sustained ball court-speed
FASTBREAK_MINLEN  = 16        # frames
FASTBREAK_MIN_DX  = 8.0       # m net court-x travel
CLIP_PAD_PRE      = 100       # frames (-4s) pre-roll (peak-anchored; show the shooter)
CLIP_PAD_POST     = 50        # frames (+2s)
RUN_MAX_GAP       = 6
MOMENT_GAP        = 40        # frames; peak-proximity clustering
MAX_CLIP_LEN      = 275       # frames (11s) cap

# interest weight per type (the ranking backbone): exciting plays float to the top
INTEREST = {"likely_made_basket": 1.00, "fast_break": 0.82, "block_proxy": 0.74,
            "steal_proxy": 0.60, "shot_attempt": 0.50}


# ======================= loaders =======================
def _json_default(o):
    if isinstance(o, np.integer): return int(o)
    if isinstance(o, np.floating): return float(o)
    if isinstance(o, np.bool_): return bool(o)
    if isinstance(o, np.ndarray): return o.tolist()
    raise TypeError(f"not serializable: {type(o)}")


def load_ball(seq, root="outputs/ball_track_bb"):
    return json.loads((Path(root) / seq / "trajectory.json").read_text())


def load_homography(seq):
    H = json.loads(Path(f"outputs/deliverables/{seq}/court/homography.json").read_text())
    return np.array(H["H_court_from_img"], float), np.array(H["H_img_from_court"], float), H


def to_court(xy_pixel, H_court_from_img):
    return cv2.perspectiveTransform(np.array([[xy_pixel]], float), H_court_from_img).ravel()


def load_players_court(track_path, H_court_from_img):
    """MOT -> {frame: [(tid, court_x, court_y, px, py), ...]}. Feet (bbox bottom-center) projected."""
    by_frame = defaultdict(list)
    for line in Path(track_path).read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(",")
        f = int(p[0]); tid = int(p[1]); x = float(p[2]); y = float(p[3]); w = float(p[4]); h = float(p[5])
        fx, fy = x + w / 2, y + h
        c = to_court((fx, fy), H_court_from_img)
        by_frame[f].append((tid, float(c[0]), float(c[1]), fx, fy))
    return by_frame


def load_teams(seq, path="outputs/team_assign_bb/track_teams_emb.json"):
    d = json.loads(Path(path).read_text()).get(seq, {})
    return {int(t): v.get("role") for t, v in d.items()}


def in_frame_hoops(H_img_from_court, W, H):
    """Which hoops project inside the frame -> usable for this clip."""
    use = {}
    for name, c in HOOPS_COURT.items():
        px = cv2.perspectiveTransform(np.array([[c]], float), H_img_from_court).ravel()
        if 0 <= px[0] <= W and 0 <= px[1] <= H:
            use[name] = {"court": c, "pixel": (float(px[0]), float(px[1]))}
    return use


# ======================= PART A: features =======================
def guard_court_teleports(cx, cy, fps, cap_mps):
    px = cx.copy(); py = cy.copy(); n = len(px); tele = np.zeros(n, bool)
    cap_m = cap_mps / fps; last = None
    for i in range(n):
        if not np.isfinite(px[i]):
            continue
        if last is not None:
            step = np.hypot(px[i] - px[last], py[i] - py[last]) / max(1, i - last)
            if step > cap_m:
                tele[i] = True; px[i] = np.nan; py[i] = np.nan; continue
        last = i
    return interp_nan(px), interp_nan(py), tele


def compute_features(recs, players, teams, hoops, H_court_from_img, n, fps, smooth_win=5):
    bx = np.full(n, np.nan); by = np.full(n, np.nan); detected = np.zeros(n, bool)
    cx = np.full(n, np.nan); cy = np.full(n, np.nan)
    for i, r in enumerate(recs):
        if r.get("x") is not None:
            bx[i] = r["x"]; by[i] = r["y"]; detected[i] = (r.get("status") == "detected")
            c = to_court((r["x"], r["y"]), H_court_from_img); cx[i] = c[0]; cy[i] = c[1]
    valid = np.isfinite(cx)

    # ball court kinematics, lost = DEAD (no fabricated velocity across gaps)
    cxc, cyc, tele = guard_court_teleports(cx, cy, fps, BALL_TELEPORT_MPS)
    vmx = np.gradient(cxc) * fps; vmy = np.gradient(cyc) * fps
    spd = smooth(np.hypot(vmx, vmy), smooth_win)
    spd[~valid] = 0.0; vmx[~valid] = 0.0; vmy[~valid] = 0.0
    acc = np.gradient(spd) * fps

    # ball-relative-to-hoop (for in-frame hoops) + nearest-hoop distance + heading toward it
    dist_hoop = {}; head_hoop = {}
    for name, h in hoops.items():
        hx, hy = h["court"]
        dgx = hx - cxc; dgy = hy - cyc
        dist = np.hypot(dgx, dgy)
        g = np.stack([dgx, dgy], 1); gn = np.linalg.norm(g, axis=1, keepdims=True)
        g = np.divide(g, gn, out=np.zeros_like(g), where=gn > 1e-6)
        v = np.stack([vmx, vmy], 1); vn = np.linalg.norm(v, axis=1, keepdims=True)
        v = np.divide(v, vn, out=np.zeros_like(v), where=vn > 1e-6)
        dist_hoop[name] = dist; head_hoop[name] = np.sum(v * g, axis=1)
    near_dist = np.min(np.stack(list(dist_hoop.values()), 1), axis=1) if hoops else np.full(n, np.nan)

    # possession (Day-23 teams + nearest on-court player within POSSESS_MAX_M, court meters)
    poss = np.zeros(n, int); nA = np.zeros(n, int); nB = np.zeros(n, int)
    for i in range(n):
        if not valid[i]:
            continue
        best = None; bestd = POSSESS_MAX_M
        for (tid, pcx, pcy, _, _) in players.get(i + 1, []):
            role = teams.get(tid)
            d = np.hypot(pcx - cxc[i], pcy - cyc[i])
            if d <= CONVERGE_M:
                if role == "TeamA": nA[i] += 1
                elif role == "TeamB": nB[i] += 1
            if role in ("TeamA", "TeamB") and d < bestd:
                bestd = d; best = role
        poss[i] = 1 if best == "TeamA" else (2 if best == "TeamB" else 0)
    poss_s = majority_smooth(poss, win=int(fps * 0.6))
    flips = np.zeros(n, bool); last = 0
    for i in range(n):
        if poss_s[i] in (1, 2):
            if last in (1, 2) and poss_s[i] != last:
                flips[i] = True
            last = poss_s[i]

    # player streaming (mean court-x velocity of players) for fast-break direction
    stream = np.full(n, np.nan)
    prev = {}
    for i in range(n):
        cur = {tid: pcx for (tid, pcx, pcy, _, _) in players.get(i + 1, [])}
        vs = [(cur[t] - prev[t]) * fps for t in cur if t in prev]
        if vs:
            stream[i] = float(np.mean(vs))
        prev = cur
    stream = smooth(interp_nan(stream), smooth_win)

    return {
        "n": n, "fps": fps, "hoops": {k: v for k, v in hoops.items()},
        "ball_detected": detected.tolist(), "ball_valid": valid.tolist(), "ball_teleport": tele.tolist(),
        "court_x": cxc.tolist(), "court_y": cyc.tolist(),
        "court_speed_mps": spd.tolist(), "court_accel_mps2": acc.tolist(),
        "court_vx": vmx.tolist(),
        "dist_hoop": {k: v.tolist() for k, v in dist_hoop.items()},
        "head_hoop": {k: v.tolist() for k, v in head_hoop.items()},
        "near_hoop_dist": near_dist.tolist(),
        "possession": poss_s.tolist(), "possession_flip": flips.tolist(),
        "n_teamA_near": nA.tolist(), "n_teamB_near": nB.tolist(),
        "player_stream_vx": stream.tolist(),
    }


# ======================= PART B: detectors + ranking =======================
def detect_shot_flights(F):
    """Launch-anchored shot: a lost-ball stretch that departs a possessed spot and APPROACHES a
    hoop, ending near the rim. Anchor = launch (last detected before the gap = the release)."""
    det = np.array(F["ball_detected"], bool); n = F["n"]
    out = []
    for hoop, dist in F["dist_hoop"].items():
        dg = np.array(dist)
        for s, e in _runs(~det, min_len=10, max_gap=2):
            pre = s - 1
            while pre >= 0 and not det[pre]:
                pre -= 1
            post = e + 1
            while post < n and not det[post]:
                post += 1
            if pre < 0 or post >= n:
                continue
            d_pre, d_post = dg[pre], dg[post]
            reach = min(dg[s:e + 1].min(), d_post)   # closest approach across the flight
            if (d_pre - reach) >= SHOT_APPROACH_M and reach <= NEAR_HOOP_M + 1.5:
                conf = float(np.clip(0.5 + 0.4 * (d_pre - reach) / 8.0, 0.35, 0.95))
                out.append({"type": "shot_attempt", "start": pre, "end": post, "peak": pre,
                            "confidence": round(conf, 2), "hoop": hoop, "via": "flight",
                            "reach_m": round(float(reach), 1)})
    return out


def detect_shots_detected(F):
    """Shot while ball stays detected: moving toward a hoop, getting near the rim."""
    spd = np.array(F["court_speed_mps"]); det = np.array(F["ball_detected"], bool)
    out = []
    for hoop in F["dist_hoop"]:
        dg = np.array(F["dist_hoop"][hoop]); hd = np.array(F["head_hoop"][hoop])
        mask = det & (hd > 0.3) & (dg < SHOT_APPROACH_M + NEAR_HOOP_M) & (spd > 3.0)
        for s, e in _runs(mask, min_len=3, max_gap=RUN_MAX_GAP):
            pk = s + int(np.argmax(spd[s:e + 1]))
            conf = float(np.clip(0.4 + 0.3 * (dg[s] - dg[e]) / 6.0, 0.3, 0.85))
            out.append({"type": "shot_attempt", "start": s, "end": e, "peak": s,
                        "confidence": round(conf, 2), "hoop": hoop, "via": "detected"})
    return out


def detect_made_baskets(F, shots):
    """Ball reaches the rim zone, then play REVERSES (possession flip OR ball heads back out)
    within MADE_REVERSE_FR. Honest 'likely made' (no height/net) -> never a confirmed score."""
    n = F["n"]; det = np.array(F["ball_detected"], bool); poss = np.array(F["possession"], int)
    out = []
    for hoop in F["dist_hoop"]:
        dg = np.array(F["dist_hoop"][hoop]); hd = np.array(F["head_hoop"][hoop])
        for s, e in _runs(dg < NEAR_HOOP_M, min_len=1, max_gap=4):
            rim = s + int(np.argmin(dg[s:e + 1]))
            hi = min(n, e + MADE_REVERSE_FR)
            # reversal: ball later heads AWAY from this hoop, or possession flips after the rim
            away = bool((np.array(F["head_hoop"][hoop])[e:hi] < -0.2).any())
            flip = bool(np.array(F["possession_flip"])[e:hi].any())
            poss_change = poss[min(n - 1, hi - 1)] != 0 and poss[s] != 0 and poss[min(n - 1, hi - 1)] != poss[s]
            if away or flip or poss_change:
                conf = float(np.clip(0.4 + 0.2 * away + 0.2 * (flip or poss_change), 0.3, 0.7))
                anchor = next((sh["peak"] for sh in shots if sh["start"] <= rim <= sh["end"] + 5), rim)
                out.append({"type": "likely_made_basket", "start": min(anchor, s), "end": min(n - 1, hi),
                            "peak": anchor, "confidence": round(conf, 2), "hoop": hoop,
                            "evidence": ("ball-out " if away else "") + ("poss-reversal" if (flip or poss_change) else "")})
    return out


def detect_blocks(F, shots):
    """Shot toward rim that gets near (<NEAR+1) then sharply reverses away WITHOUT a made signature."""
    n = F["n"]; out = []
    for hoop in F["dist_hoop"]:
        dg = np.array(F["dist_hoop"][hoop]); hd = np.array(F["head_hoop"][hoop])
        det = np.array(F["ball_detected"], bool)
        for s, e in _runs(det & (dg < NEAR_HOOP_M + 1.0) & (hd > 0.2), min_len=2, max_gap=4):
            hi = min(n, e + 15)
            sharp_away = bool((hd[e:hi] < -0.4).any()) and (dg[min(n - 1, hi - 1)] - dg[e] > 1.5)
            if sharp_away:
                out.append({"type": "block_proxy", "start": s, "end": min(n - 1, hi), "peak": s,
                            "confidence": 0.45, "hoop": hoop})
    return out


def detect_fast_breaks(F):
    spd = np.array(F["court_speed_mps"]); cx = np.array(F["court_x"]); stream = np.array(F["player_stream_vx"])
    out = []
    for s, e in _runs(spd > FASTBREAK_SPD, min_len=FASTBREAK_MINLEN, max_gap=RUN_MAX_GAP):
        dx = abs(cx[e] - cx[s])
        streaming = abs(np.nanmean(stream[s:e + 1])) > 2.0  # players moving one way
        if dx < FASTBREAK_MIN_DX or not streaming:
            continue
        conf = float(np.clip(0.45 + 0.35 * dx / 20.0, 0.3, 0.9))
        out.append({"type": "fast_break", "start": s, "end": e,
                    "peak": s + int(np.argmax(spd[s:e + 1])), "confidence": round(conf, 2)})
    return out


def detect_steals(F, dedupe=15):
    """Open-court possession flip (ball NOT near a hoop = midcourt turnover)."""
    flips = np.array(F["possession_flip"], bool); near = np.array(F["near_hoop_dist"])
    nA = np.array(F["n_teamA_near"]); nB = np.array(F["n_teamB_near"]); n = F["n"]
    out = []; last = -10 ** 9
    for i in np.where(flips)[0]:
        if i - last < dedupe:
            continue
        if not np.isfinite(near[i]) or near[i] < 5.0:   # near a hoop -> not an open-court steal
            continue
        last = i
        out.append({"type": "steal_proxy", "start": max(0, i - 10), "end": min(n - 1, i + 10),
                    "peak": int(i), "confidence": 0.4})
    return out


def cluster_rank(events, n, pre, post, gap=MOMENT_GAP, max_len=MAX_CLIP_LEN):
    """Peak-proximity clustering (Day-24) -> moments; each scored by INTEREST for ranking."""
    if not events:
        return []
    evs = sorted(events, key=lambda e: e["peak"])
    clusters = [[evs[0]]]
    for ev in evs[1:]:
        if ev["peak"] - clusters[-1][-1]["peak"] <= gap:
            clusters[-1].append(ev)
        else:
            clusters.append([ev])
    out = []
    for cl in clusters:
        best = max(cl, key=lambda e: INTEREST.get(e["type"], 0) + 0.25 * e["confidence"])
        pk = best["peak"]
        s = max(0, min(min(e["start"] for e in cl), pk - pre))
        e_ = min(n - 1, max(e["end"] for e in cl) + post)
        if e_ - s > max_len:
            s = max(0, pk - max_len // 2); e_ = min(n - 1, pk + max_len // 2)
        types = sorted(set(e["type"] for e in cl))
        interest = round(max(INTEREST.get(e["type"], 0) + 0.25 * e["confidence"] for e in cl), 3)
        out.append({"start": s, "end": e_, "events": cl, "types": types,
                    "top_type": best["type"], "confidence": round(max(e["confidence"] for e in cl), 2),
                    "interest": interest, "peak": pk,
                    "start_sec": round(s / FPS, 2), "end_sec": round(e_ / FPS, 2)})
    out.sort(key=lambda m: -m["interest"])    # RANK best-first
    for rk, m in enumerate(out, 1):
        m["rank"] = rk
    return out


def detect_events(F):
    shots = detect_shot_flights(F) + detect_shots_detected(F)
    made = detect_made_baskets(F, shots)
    blocks = detect_blocks(F, shots)
    breaks = detect_fast_breaks(F)
    steals = detect_steals(F)
    raw = shots + made + blocks + breaks + steals
    ranked = cluster_rank(raw, F["n"], CLIP_PAD_PRE, CLIP_PAD_POST)
    return raw, ranked


# ======================= plot =======================
def plot_features(F, out_path, seq):
    n = F["n"]; fr = np.arange(1, n + 1)
    fig, axs = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    axs[0].plot(fr, F["court_speed_mps"], lw=1.0, color="tab:blue"); axs[0].set_ylabel("ball court\nspeed (m/s)"); axs[0].grid(alpha=.3)
    for name, d in F["dist_hoop"].items():
        axs[1].plot(fr, d, lw=1.0, label=f"dist {name} hoop")
    axs[1].axhline(NEAR_HOOP_M, color="r", ls="--", lw=1, label=f"rim zone {NEAR_HOOP_M}m")
    axs[1].set_ylabel("dist to hoop (m)"); axs[1].legend(loc="upper right"); axs[1].grid(alpha=.3)
    axs[2].plot(fr, F["possession"], lw=1.2, color="0.4", drawstyle="steps-post")
    axs[2].set_yticks([0, 1, 2]); axs[2].set_yticklabels(["none", "TeamA", "TeamB"])
    axs[2].set_ylabel("possession"); axs[2].set_xlabel("frame"); axs[2].grid(alpha=.3)
    axs[0].set_title(f"{seq}: basketball motion features")
    fig.tight_layout(); fig.savefig(out_path, dpi=110); plt.close(fig)


# ======================= main =======================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="?", default=None)
    ap.add_argument("--ball-dir", default="outputs/ball_track_bb")
    ap.add_argument("--track-dir", default="outputs/track_results/bball_ftdet_bytetrack")
    ap.add_argument("--follow-dir", default="outputs/follow_cam_bb")
    ap.add_argument("--out", default="outputs/events_bb")
    args = ap.parse_args()

    seqs = [args.seq] if args.seq else SEQS_DEFAULT
    for seq in seqs:
        print(f"\n=== {seq} ===")
        out_seq = Path(args.out) / seq; out_seq.mkdir(parents=True, exist_ok=True)
        recs = load_ball(seq, args.ball_dir); n = len(recs)
        H_ci, H_ic, Hmeta = load_homography(seq)
        fc = json.loads((Path(args.follow_dir) / seq / "follow_cam.json").read_text())
        W, Hh = fc["frame_w"], fc["frame_h"]
        hoops = in_frame_hoops(H_ic, W, Hh)
        players = load_players_court(Path(args.track_dir) / f"{seq}.txt", H_ci)
        teams = load_teams(seq)
        print(f"  frames={n} hoops in-frame={list(hoops)} (homography holdout {Hmeta.get('holdout_mean_err_m')}m) "
              f"teams={Counter(teams.values())}")

        F = compute_features(recs, players, teams, hoops, H_ci, n, FPS)
        valid = np.array(F["ball_valid"]); sp = np.array(F["court_speed_mps"])
        print(f"  ball valid {int(valid.sum())}/{n} | court speed max={sp.max():.1f} mean={sp.mean():.1f} m/s "
              f"| teleports {int(np.sum(F['ball_teleport']))} | poss flips {int(np.sum(F['possession_flip']))}")
        for name, d in F["dist_hoop"].items():
            print(f"  min ball-dist {name} hoop = {np.min(d):.1f} m")

        raw, ranked = detect_events(F)
        print(f"  candidates (raw): " + ", ".join(f"{k}={v}" for k, v in sorted(Counter(e['type'] for e in raw).items()))
              + f"  | ranked moments={len(ranked)}")
        print("  top-5 ranked moments:")
        for m in ranked[:5]:
            print(f"    #{m['rank']} interest={m['interest']} {m['top_type']:18s} "
                  f"[{m['start_sec']:.1f}-{m['end_sec']:.1f}s] conf={m['confidence']} types={m['types']}")

        (out_seq / "features.json").write_text(json.dumps(F))
        (out_seq / "events.json").write_text(json.dumps({
            "seq": seq, "n": n, "fps": FPS, "hoops": hoops, "ranked_moments": ranked, "raw_events": raw,
            "interest_weights": INTEREST,
            "thresholds": {"NEAR_HOOP_M": NEAR_HOOP_M, "SHOT_APPROACH_M": SHOT_APPROACH_M,
                           "POSSESS_MAX_M": POSSESS_MAX_M, "FASTBREAK_SPD": FASTBREAK_SPD,
                           "BALL_TELEPORT_MPS": BALL_TELEPORT_MPS,
                           "note": "camera-scale + court-marking dependent; RE-TUNE at DPS"},
        }, indent=2, default=_json_default))
        plot_features(F, out_seq / "features_plot.png", seq)
        print(f"  wrote features.json + events.json + features_plot.png")


if __name__ == "__main__":
    main()
