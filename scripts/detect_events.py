"""Day 24: EVENT DETECTION + highlight-candidate windows (output #3, football, SoccerNet).

THIRD DPS output: auto-surface candidate exciting moments from MOTION for a human
(Student Council) to curate into a highlight reel. Design = HIGH RECALL: catch
everything, the editor discards false positives (a missed goal is gone forever; a
false positive is a 2s skip). Motion-only today; AUDIO (whistle/crowd) is the
documented next lever for real fouls + goal-confirmation.

Honest event tiers (what motion CAN / CANNOT do):
  Tier 1 (solid kinematic):  shot, fast-transition
  Tier 2 (honest proxies):   likely-goal-candidate, tackle-proxy, stoppage(review)
  Tier 3 (NOT built):        fouls (referee judgment -> audio), skill-moves (out of scope)

This script does PART A (motion features) + PART B (high-recall detectors -> candidate
windows). Clipping from the A-feed + validation lives in clip_highlights.py (Part C/D).

Reuses (no re-detection / re-tracking):
  outputs/ball_track/<seq>/trajectory.json                 Day-12 ball (pixel + pitch + flags)
  outputs/track_results/sn_soccana_botsort_gmc/<seq>.txt   Day-9 player tracks (MOT, pixel)
  outputs/team_assign/track_teams.json                     Day-11 team per track_id
  datasets/soccernet_gsr/test.zip                          GSR Labels (clip-level action label)
  analyze_pitch.derive_per_frame_H / PITCH_X_HALF/Y_HALF   Day-10 pitch geometry

Teleport guards (so ID/track noise can't fake an accel event):
  PLAYER step speed > 10 m/s  -> tracking teleport, dropped       (Day-20 coach_deliverable)
  BALL  pitch step > BALL_TELEPORT_MPS (default 40 m/s) -> homography-noise teleport, interp'd.
    Note: the ball guard is DELIBERATELY higher than the player 10 m/s guard -- a real shot
    travels 25-30+ m/s, so a 10 m/s cap would erase the exact events we detect. Honest split.

Outputs (outputs/events/<seq>/):
  features.json     per-frame motion features + scalar meta (Part A)
  events.json       merged high-recall candidate windows (start,end,type,confidence) (Part B)
  features_plot.png ball pitch-speed/accel + possession + goal-distance (plausibility, by eye)

Usage:
  python scripts/detect_events.py SNGS-118          # one seq
  python scripts/detect_events.py                   # all 5 default seqs
"""
import argparse, json, sys, zipfile
from collections import defaultdict
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
from analyze_pitch import PITCH_X_HALF, PITCH_Y_HALF  # 52.5, 34.0 (FIFA half-dims, origin=center)

SEQS_DEFAULT = ["SNGS-116", "SNGS-117", "SNGS-118", "SNGS-119", "SNGS-120"]
FPS = 25

# ---- guards / geometry (ALL camera-scale-dependent -> RE-TUNE at DPS mount) ----
PLAYER_SPEED_ARTEFACT = 10.0   # m/s; Day-20 player teleport guard (sprint peak ~10 m/s)
BALL_TELEPORT_MPS      = 40.0  # m/s; ball pitch-step above this = homography-noise teleport
GOAL_X                 = PITCH_X_HALF          # goals at x = +/-52.5 m, y = 0
GOAL_HALF_W            = 9.0   # m; "near goal" |y| band (goal 7.32 wide; widen for recall)
GOAL_NEAR_DX           = 12.0  # m; ball within this of goal-line x => "near goal" zone
POSSESS_RADIUS_PX      = 170.0 # px; nearest-player-to-ball max range to assign possession
CONVERGE_RADIUS_PX     = 220.0 # px; players within this of ball counted for tackle-proxy


# ======================= loaders =======================
def load_ball(ball_dir, seq):
    return json.loads((Path(ball_dir) / seq / "trajectory.json").read_text())


def load_players(track_path):
    """MOT -> {frame: [(track_id, feet_x, feet_y, cx, cy), ...]} pixel space.
    feet = bbox bottom-center (ground contact, best for ball proximity)."""
    by_frame = defaultdict(list)
    for line in Path(track_path).read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(",")
        f = int(p[0]); tid = int(p[1])
        x = float(p[2]); y = float(p[3]); w = float(p[4]); h = float(p[5])
        by_frame[f].append((tid, x + w / 2, y + h, x + w / 2, y + h / 2))
    return by_frame


def load_teams(team_path, seq):
    """track_id(str) -> 'TeamA'|'TeamB'|other. Day-11 majority role."""
    data = json.loads(Path(team_path).read_text())
    seqd = data.get(seq, {})
    return {int(tid): info.get("role") for tid, info in seqd.items()}


def load_action_label(zip_path, seq):
    """GSR clip-level action: (action_class, approx_frame). The only event 'GT' available
    (1 labeled action per 750-frame clip; action_position->frame via clip_start/fps)."""
    try:
        z = zipfile.ZipFile(zip_path)
        info = json.loads(z.read(f"{seq}/Labels-GameState.json"))["info"]
        ap = int(info["action_position"]); cs = int(info["clip_start"])
        fr = int(info["frame_rate"])
        frame = int(round((ap - cs) / 1000.0 * fr))
        return {"action_class": info["action_class"], "approx_frame": frame,
                "seq_length": int(info["seq_length"])}
    except Exception as ex:
        return {"action_class": None, "approx_frame": None, "note": str(ex)}


# ======================= signal helpers =======================
def interp_nan(v):
    v = np.asarray(v, float).copy()
    idx = np.arange(len(v)); good = np.isfinite(v)
    if good.sum() == 0:
        return np.zeros_like(v)
    v[~good] = np.interp(idx[~good], idx[good], v[good])
    return v


def smooth(v, win):
    if win <= 1:
        return np.asarray(v, float).copy()
    k = win // 2
    pad = np.pad(np.asarray(v, float), (k, k), mode="edge")
    ker = np.ones(2 * k + 1) / (2 * k + 1)
    return np.convolve(pad, ker, mode="valid")[:len(v)]


# ======================= PART A: motion features =======================
def ball_series(recs, n):
    """Pixel x,y (NaN where lost) + pitch x,y (NaN where unprojected) + aerial flag."""
    bx = np.full(n, np.nan); by = np.full(n, np.nan)
    pxm = np.full(n, np.nan); pym = np.full(n, np.nan)
    aerial = np.zeros(n, bool); detected = np.zeros(n, bool)
    for i, r in enumerate(recs):
        if r.get("x") is not None:
            bx[i] = r["x"]; by[i] = r["y"]
        if r.get("pitch_x_m") is not None:
            pxm[i] = r["pitch_x_m"]; pym[i] = r["pitch_y_m"]
        aerial[i] = bool(r.get("aerial_suspect"))
        detected[i] = (r.get("status") == "detected")
    return bx, by, pxm, pym, aerial, detected


def guard_ball_teleports(pxm, pym, fps, cap_mps):
    """NaN-out pitch positions that imply a >cap_mps single-frame jump (homography noise),
    then interpolate. Returns cleaned (pxm, pym) and a teleport mask."""
    px = pxm.copy(); py = pym.copy()
    n = len(px); tele = np.zeros(n, bool)
    cap_m = cap_mps / fps
    last = None
    for i in range(n):
        if not np.isfinite(px[i]):
            continue
        if last is not None:
            step = np.hypot(px[i] - px[last], py[i] - py[last]) / max(1, i - last)
            if step > cap_m:
                tele[i] = True
                px[i] = np.nan; py[i] = np.nan
                continue
        last = i
    return interp_nan(px), interp_nan(py), tele


def compute_features(recs, players_by_frame, teams, n, fps,
                     ball_teleport_mps, smooth_win=5):
    bx, by, pxm, pym, aerial, detected = ball_series(recs, n)
    # validity masks BEFORE interpolation: speed must NOT be derived across missing frames
    # (linear interp over a lost gap fabricates a constant non-zero velocity -> fake events).
    valid_px = np.isfinite(bx); valid_pitch = np.isfinite(pxm)

    # ---- ball kinematics, pixel space (Day-12 Kalman already 80px/frame gated) ----
    bxf, byf = interp_nan(bx), interp_nan(by)
    vpx = np.gradient(bxf); vpy = np.gradient(byf)
    spd_px = np.hypot(vpx, vpy)                          # px/frame
    spd_px_s = smooth(spd_px, smooth_win)
    spd_px_s[~valid_px] = 0.0                            # lost ball -> no measured motion
    acc_px = np.abs(np.gradient(spd_px_s))              # px/frame^2 (speed change)

    # ---- ball kinematics, pitch space (perspective-invariant, teleport-guarded) ----
    pxc, pyc, tele = guard_ball_teleports(pxm, pym, fps, ball_teleport_mps)
    vmx = np.gradient(pxc) * fps; vmy = np.gradient(pyc) * fps   # m/s components
    spd_m = np.hypot(vmx, vmy)
    spd_m_s = smooth(spd_m, smooth_win)
    spd_m_s[~valid_pitch] = 0.0                          # lost/unprojected -> dead, not fake
    vmx[~valid_pitch] = 0.0; vmy[~valid_pitch] = 0.0     # heading undefined when ball missing
    acc_m = np.gradient(spd_m_s) * fps                  # m/s^2 (signed)

    # ---- ball-toward-goal: distance + heading toward each goal (+x and -x) ----
    # goal centers at (+/-GOAL_X, 0). heading = unit(vel) . unit(ball->goal).
    vunit = np.stack([vmx, vmy], 1)
    vnorm = np.linalg.norm(vunit, axis=1, keepdims=True)
    vunit = np.divide(vunit, vnorm, out=np.zeros_like(vunit), where=vnorm > 1e-6)
    dist_goal = {}; head_goal = {}
    for sgn, gx in (("pos", GOAL_X), ("neg", -GOAL_X)):
        dgx = gx - pxc; dgy = 0.0 - pyc
        dist = np.hypot(dgx, dgy)
        gunit = np.stack([dgx, dgy], 1)
        gn2 = np.linalg.norm(gunit, axis=1, keepdims=True)
        gunit = np.divide(gunit, gn2, out=np.zeros_like(gunit), where=gn2 > 1e-6)
        head = np.sum(vunit * gunit, axis=1)            # cos(angle), 1 = straight at goal
        dist_goal[sgn] = dist; head_goal[sgn] = head
    # ball inside a goal zone (near goal-line x + within widened goal band y)
    in_goal_zone = ((np.abs(pxc) > GOAL_X - GOAL_NEAR_DX) & (np.abs(pyc) < GOAL_HALF_W))

    # ---- possession (Day-11 teams + nearest-player-to-ball, Day-12 proxy) ----
    poss = np.full(n, 0, int)   # 0 none, 1 TeamA, 2 TeamB
    nA_near = np.zeros(n, int); nB_near = np.zeros(n, int)
    for i in range(n):
        f = i + 1
        if not np.isfinite(bx[i]):
            continue
        pl = players_by_frame.get(f, [])
        best = None; bestd = POSSESS_RADIUS_PX
        for (tid, fxx, fyy, cx, cy) in pl:
            role = teams.get(tid)
            d = np.hypot(fxx - bx[i], fyy - by[i])
            if d <= CONVERGE_RADIUS_PX:
                if role == "TeamA": nA_near[i] += 1
                elif role == "TeamB": nB_near[i] += 1
            if role in ("TeamA", "TeamB") and d < bestd:
                bestd = d; best = role
        if best == "TeamA": poss[i] = 1
        elif best == "TeamB": poss[i] = 2
    # smooth possession by majority over a window -> stable team, then flips
    poss_s = majority_smooth(poss, win=int(fps * 0.6))
    flips = np.zeros(n, bool)
    last_team = 0
    for i in range(n):
        if poss_s[i] in (1, 2):
            if last_team in (1, 2) and poss_s[i] != last_team:
                flips[i] = True
            last_team = poss_s[i]

    # ---- player spread (motion-halt / cluster signal for stoppage proxy) ----
    spread = np.full(n, np.nan)
    pcount = np.zeros(n, int)
    for i in range(n):
        pl = players_by_frame.get(i + 1, [])
        pcount[i] = len(pl)
        if len(pl) >= 3:
            pts = np.array([(c[3], c[4]) for c in pl], float)  # box centers
            cen = np.median(pts, axis=0)
            spread[i] = float(np.mean(np.hypot(pts[:, 0] - cen[0], pts[:, 1] - cen[1])))
    spread = interp_nan(spread); spread_s = smooth(spread, fps)

    return {
        "n": n, "fps": fps,
        "ball_detected": detected.tolist(), "aerial": aerial.tolist(),
        "ball_teleport": tele.tolist(),
        "px_speed": spd_px_s.tolist(), "px_accel": acc_px.tolist(),
        "pitch_x": pxc.tolist(), "pitch_y": pyc.tolist(),
        "pitch_speed_mps": spd_m_s.tolist(), "pitch_accel_mps2": acc_m.tolist(),
        "dist_goal_pos": dist_goal["pos"].tolist(), "dist_goal_neg": dist_goal["neg"].tolist(),
        "head_goal_pos": head_goal["pos"].tolist(), "head_goal_neg": head_goal["neg"].tolist(),
        "in_goal_zone": in_goal_zone.tolist(),
        "possession": poss_s.tolist(), "possession_flip": flips.tolist(),
        "n_teamA_near": nA_near.tolist(), "n_teamB_near": nB_near.tolist(),
        "player_spread": spread_s.tolist(), "player_count": pcount.tolist(),
    }


def majority_smooth(v, win):
    """Per-frame majority of v over +/- win//2, ignoring 0 (no-possession)."""
    v = np.asarray(v, int); n = len(v); out = v.copy(); k = win // 2
    for i in range(n):
        seg = v[max(0, i - k):min(n, i + k + 1)]
        seg = seg[seg != 0]
        if len(seg):
            vals, cnts = np.unique(seg, return_counts=True)
            out[i] = int(vals[np.argmax(cnts)])
        else:
            out[i] = 0
    return out


# ======================= plausibility plot =======================
def plot_features(feat, label, out_path, seq):
    n = feat["n"]; fr = np.arange(1, n + 1)
    fig, axs = plt.subplots(4, 1, figsize=(14, 11), sharex=True)
    axs[0].plot(fr, feat["pitch_speed_mps"], lw=1.2, color="tab:blue")
    axs[0].set_ylabel("ball pitch\nspeed (m/s)"); axs[0].grid(alpha=0.3)
    axs[1].plot(fr, np.abs(feat["pitch_accel_mps2"]), lw=1.0, color="tab:red")
    axs[1].set_ylabel("|ball accel|\n(m/s^2)"); axs[1].grid(alpha=0.3)
    axs[2].plot(fr, feat["dist_goal_pos"], lw=1.0, color="tab:green", label="dist +goal")
    axs[2].plot(fr, feat["dist_goal_neg"], lw=1.0, color="tab:olive", label="dist -goal")
    axs[2].set_ylabel("dist to goal (m)"); axs[2].legend(loc="upper right"); axs[2].grid(alpha=0.3)
    axs[3].plot(fr, feat["possession"], lw=1.2, color="0.4", drawstyle="steps-post")
    axs[3].set_yticks([0, 1, 2]); axs[3].set_yticklabels(["none", "TeamA", "TeamB"])
    axs[3].set_ylabel("possession"); axs[3].set_xlabel("frame"); axs[3].grid(alpha=0.3)
    if label.get("approx_frame") is not None:
        for ax in axs:
            ax.axvline(label["approx_frame"], color="magenta", ls="--", lw=1.3)
        axs[0].set_title(f"{seq}: motion features  (magenta = GSR label '{label['action_class']}'"
                         f" @f{label['approx_frame']})")
    else:
        axs[0].set_title(f"{seq}: motion features")
    fig.tight_layout(); fig.savefig(out_path, dpi=110); plt.close(fig)


def plausibility(feat, label):
    """Print quick sanity: do speed/accel peaks line up with the labeled action frame?"""
    sp = np.array(feat["pitch_speed_mps"]); ac = np.abs(np.array(feat["pitch_accel_mps2"]))
    af = label.get("approx_frame")
    print(f"    ball pitch speed: max={sp.max():.1f} mean={sp.mean():.1f} m/s | "
          f"|accel| max={ac.max():.1f} m/s^2")
    print(f"    teleports guarded: {int(np.sum(feat['ball_teleport']))} | "
          f"poss flips: {int(np.sum(feat['possession_flip']))} | "
          f"aerial frames: {int(np.sum(feat['aerial']))}")
    if af is not None and 1 <= af <= feat["n"]:
        lo, hi = max(0, af - 1 - 38), min(feat["n"], af - 1 + 38)  # +/-1.5s window
        loc_spd = sp[lo:hi].max(); loc_acc = ac[lo:hi].max()
        spd_rank = float((sp < loc_spd).mean())   # percentile of the local peak
        print(f"    @label '{label['action_class']}' f{af} (+/-1.5s): peak speed="
              f"{loc_spd:.1f} m/s (>{spd_rank*100:.0f}% of clip), peak |accel|={loc_acc:.1f}")


# ======================= PART B: high-recall detectors =======================
# All thresholds LOW (recall-biased) + camera-scale-dependent -> RE-TUNE at DPS.
SHOT_SPD       = 9.0    # m/s; ball pitch-speed floor for a "shot" (low for recall)
SHOT_HEAD      = 0.30   # cos; ball heading within ~72 deg of a goal direction
SHOT_RANGE     = 42.0   # m; ball within this of the goal it's heading at (attacking-ish)
TRANS_SPD      = 7.0    # m/s; sustained ball speed for a fast transition
TRANS_MINLEN   = 16     # frames (~0.64s) sustained
TRANS_MIN_DX   = 18.0   # m; net up-pitch ball displacement over the run
HALT_SPD       = 1.6    # m/s; ball ~dead
HALT_MINLEN    = 38     # frames (~1.5s) of dead ball
CLIP_PAD_PRE   = 100    # frames (-4.0s) pre-roll: capture the run-up + the STRIKE itself.
CLIP_PAD_POST  = 50     # frames (+2.0s)
# Pre-roll is anchored to the speed PEAK (the strike), not the detection-run start: during a
# real shot the ball is often lost (fast/aerial) so detection resumes a beat LATE -> without
# peak-anchored pre-roll the clip starts after the strike and shows only the aftermath.
RUN_MAX_GAP    = 6      # frames; bridge short gaps when grouping a detection run
MOMENT_GAP     = 40     # frames (~1.6s); event peaks farther apart start a new MOMENT.
MAX_CLIP_LEN   = 300    # frames (12s) cap; longer cluster -> center on best peak.
# NOTE: clustering by peak-PROXIMITY (not padded-window overlap) is the right merge on these
# 30s SoccerNet clips -- they are pre-curated action-dense windows, so plain overlap-merge
# collapses to the whole clip. On continuous DPS match footage (sparse events) either works;
# peak-clustering keeps distinct moments distinct in BOTH regimes. (proxy-data caveat)


def _runs(mask, min_len=1, max_gap=0):
    """Contiguous True runs of a bool array, bridging gaps <= max_gap. -> [(s,e)] 0-based incl."""
    mask = np.asarray(mask, bool); n = len(mask); runs = []; i = 0
    while i < n:
        if not mask[i]:
            i += 1; continue
        j = i
        gap = 0; last = i
        k = i
        while k < n:
            if mask[k]:
                last = k; gap = 0
            else:
                gap += 1
                if gap > max_gap:
                    break
            k += 1
        if last - i + 1 >= min_len:
            runs.append((i, last))
        i = max(last + 1, k)
    return runs


def detect_shots(F):
    sp = np.array(F["pitch_speed_mps"]); det = np.array(F["ball_detected"], bool)
    hp = np.array(F["head_goal_pos"]); hn = np.array(F["head_goal_neg"])
    dp = np.array(F["dist_goal_pos"]); dn = np.array(F["dist_goal_neg"])
    toward = ((hp > SHOT_HEAD) & (dp < SHOT_RANGE)) | ((hn > SHOT_HEAD) & (dn < SHOT_RANGE))
    mask = det & (sp > SHOT_SPD) & toward
    out = []
    for s, e in _runs(mask, min_len=2, max_gap=RUN_MAX_GAP):
        seg = sp[s:e + 1]; pk = s + int(np.argmax(seg))
        goal = "+" if (hp[pk] * (dp[pk] < SHOT_RANGE)) >= (hn[pk] * (dn[pk] < SHOT_RANGE)) else "-"
        conf = float(np.clip(0.45 + 0.5 * (sp[pk] - SHOT_SPD) / 16.0
                             + 0.2 * (max(hp[pk], hn[pk]) - SHOT_HEAD), 0.2, 0.98))
        out.append({"type": "shot", "start": s, "end": e, "peak": pk,
                    "confidence": round(conf, 2), "toward_goal": goal,
                    "peak_speed_mps": round(float(sp[pk]), 1)})
    return out


def detect_shot_flights(F, min_lost=12, min_approach_m=8.0, near_goal_m=26.0):
    """The STRIKE-anchored shot detector. A real shot launches the ball fast/aerial, so detection
    DROPS at the kick -> the ball is LOST for a stretch while it flies goalward, reappearing near
    goal. Speed-based detection only sees the ARRIVAL (too late to show the shooter). Here we find
    lost-ball stretches whose endpoints moved >=`min_approach_m` closer to a goal and end within
    `near_goal_m` of it, and anchor the event to the LAUNCH (last detected frame before the gap =
    the strike) so the clip shows the player shooting. Emits 'shot' (+ caller derives likely-goal)."""
    det = np.array(F["ball_detected"], bool); n = F["n"]
    dg = {"+": np.array(F["dist_goal_pos"]), "-": np.array(F["dist_goal_neg"])}
    out = []
    for s, e in _runs(~det, min_len=min_lost, max_gap=2):
        pre = s - 1
        while pre >= 0 and not det[pre]:
            pre -= 1
        post = e + 1
        while post < n and not det[post]:
            post += 1
        if pre < 0 or post >= n:
            continue
        for sgn in ("+", "-"):
            d_pre, d_post = dg[sgn][pre], dg[sgn][post]
            if (d_pre - d_post) >= min_approach_m and d_post <= near_goal_m:
                conf = float(np.clip(0.55 + 0.35 * (d_pre - d_post) / 40.0, 0.4, 0.95))
                out.append({"type": "shot", "start": pre, "end": post, "peak": pre,
                            "confidence": round(conf, 2), "toward_goal": sgn,
                            "via": "flight", "approach_m": round(float(d_pre - d_post), 1),
                            "arrive_dist_m": round(float(d_post), 1)})
                break
    return out


def detect_transitions(F):
    sp = np.array(F["pitch_speed_mps"]); px = np.array(F["pitch_x"])
    out = []
    for s, e in _runs(sp > TRANS_SPD, min_len=TRANS_MINLEN, max_gap=RUN_MAX_GAP):
        dx = abs(px[e] - px[s])
        if dx < TRANS_MIN_DX:
            continue
        conf = float(np.clip(0.4 + 0.4 * (dx / 50.0) + 0.2 * (sp[s:e + 1].mean() / 15.0), 0.2, 0.95))
        out.append({"type": "fast_transition", "start": s, "end": e,
                    "peak": s + int(np.argmax(sp[s:e + 1])),
                    "confidence": round(conf, 2), "updapitch_m": round(float(dx), 1)})
    return out


def detect_likely_goals(F, shots, lookahead=60):
    """Shot toward goal -> within `lookahead` frames the ball reaches that goal zone OR goes
    dead (lost / possession none). An INFERENCE (no goal-line/net): catches saves/near-misses
    too. Low confidence BY DESIGN. Labeled 'likely_goal_candidate', never 'goal'."""
    n = F["n"]
    inzone = np.array(F["in_goal_zone"], bool)
    det = np.array(F["ball_detected"], bool)
    poss = np.array(F["possession"], int)
    out = []
    for sh in shots:
        e = sh["end"]; hi = min(n, e + lookahead)
        win = slice(e, hi)
        reaches = bool(inzone[win].any())
        dead = bool(((~det[win]).mean() > 0.5) or ((poss[win] == 0).mean() > 0.5))
        if reaches or dead:
            conf = float(np.clip(0.25 + 0.15 * reaches + 0.1 * dead + 0.2 * sh["confidence"], 0.15, 0.6))
            out.append({"type": "likely_goal_candidate", "start": sh["start"],
                        "end": min(n - 1, hi), "peak": sh["peak"],
                        "confidence": round(conf, 2), "toward_goal": sh["toward_goal"],
                        "evidence": ("ball-in-goal-zone " if reaches else "") +
                                    ("ball-dead/restart" if dead else "")})
    return out


def detect_tackles(F, flank=10, dedupe=15):
    """Opposing players converge on ball + possession flips. Noisy proxy. Flips within
    `dedupe` frames are collapsed to one event (raw flip jitter else over-fires)."""
    flips = np.array(F["possession_flip"], bool)
    nA = np.array(F["n_teamA_near"]); nB = np.array(F["n_teamB_near"])
    n = F["n"]; out = []
    idxs = list(np.where(flips)[0]); last_emit = -10 ** 9
    for i in idxs:
        if i - last_emit < dedupe:
            continue
        lo, hi = max(0, i - flank), min(n, i + flank + 1)
        contested = (nA[lo:hi].max() >= 1) and (nB[lo:hi].max() >= 1)
        if not contested:
            continue
        last_emit = i
        conf = float(np.clip(0.3 + 0.1 * min(nA[lo:hi].max(), nB[lo:hi].max()), 0.25, 0.7))
        out.append({"type": "tackle_proxy", "start": int(lo), "end": int(hi - 1),
                    "peak": int(i), "confidence": round(conf, 2)})
    return out


def detect_stoppages(F):
    """Ball dead + players clustered/static. Correlates with fouls/throw-ins/injuries/subs.
    Labeled 'stoppage_review', NEVER 'foul' (motion can't separate foul from fair challenge)."""
    sp = np.array(F["pitch_speed_mps"]); spread = np.array(F["player_spread"])
    poss = np.array(F["possession"], int); det = np.array(F["ball_detected"], bool)
    med_spread = np.nanmedian(spread)
    # halt = ball genuinely slow OR ball lost (lost-ball interp gives a constant non-zero
    # speed, so the slow-test alone misses real dead-ball stretches -> OR in 'not detected').
    dead = (sp < HALT_SPD) | (~det)
    out = []
    for s, e in _runs(dead, min_len=HALT_MINLEN, max_gap=RUN_MAX_GAP):
        clustered = (np.nanmean(spread[s:e + 1]) < med_spread) or ((poss[s:e + 1] == 0).mean() > 0.6)
        if not clustered:
            continue
        conf = float(np.clip(0.25 + 0.1 * (e - s) / 50.0, 0.2, 0.55))
        out.append({"type": "stoppage_review", "start": s, "end": e,
                    "peak": s + (e - s) // 2, "confidence": round(conf, 2)})
    return out


def merge_windows(events, n, pre, post, gap=MOMENT_GAP, max_len=MAX_CLIP_LEN):
    """Cluster events into MOMENTS by peak proximity (gap), then pad each cluster to a clip
    window [min_peak-pre, max_peak+post], capped at max_len (center on best-conf peak if over).
    Keeps distinct moments distinct on action-dense pre-cut clips (see MOMENT_GAP note)."""
    if not events:
        return []
    evs = sorted(events, key=lambda e: e["peak"])
    clusters = [[evs[0]]]
    for ev in evs[1:]:
        if ev["peak"] - clusters[-1][-1]["peak"] <= gap:
            clusters[-1].append(ev)
        else:
            clusters.append([ev])
    merged = []
    for cl in clusters:
        best = max(cl, key=lambda e: e["confidence"]); pk = best["peak"]
        # window spans the cluster's event EXTENTS (so a long stoppage/transition clip actually
        # covers its dead/active region), padded; capped at max_len centered on the best peak.
        # start is anchored to guarantee `pre` frames BEFORE the speed peak (the strike) so the
        # clip shows the run-up + strike, not just the aftermath.
        s = max(0, min(min(e["start"] for e in cl), pk - pre))
        e_ = min(n - 1, max(e["end"] for e in cl) + post)
        if e_ - s > max_len:                      # cap: center on highest-confidence peak
            s = max(0, pk - max_len // 2); e_ = min(n - 1, pk + max_len // 2)
        merged.append({
            "start": s, "end": e_, "events": cl,
            "types": sorted(set(e["type"] for e in cl)),
            "confidence": round(max(e["confidence"] for e in cl), 2),
            "peak": pk, "start_sec": round(s / FPS, 2), "end_sec": round(e_ / FPS, 2),
        })
    return merged


def detect_events(F):
    flights = detect_shot_flights(F)            # strike-anchored shots (show the shooter)
    shots = detect_shots(F) + flights           # + speed-based ground shots
    trans = detect_transitions(F)
    goals = detect_likely_goals(F, shots)       # flights arriving near goal -> likely-goal too
    # a flight that ends near goal is itself a likely-goal candidate, anchored at the strike
    for fl in flights:
        if fl.get("arrive_dist_m", 99) <= GOAL_NEAR_DX + GOAL_HALF_W:
            goals.append({"type": "likely_goal_candidate", "start": fl["start"], "end": fl["end"],
                          "peak": fl["start"], "confidence": round(min(0.6, fl["confidence"]), 2),
                          "toward_goal": fl["toward_goal"], "evidence": "shot-flight->near-goal"})
    tackles = detect_tackles(F)
    stops = detect_stoppages(F)
    raw = shots + trans + goals + tackles + stops
    merged = merge_windows(raw, F["n"], CLIP_PAD_PRE, CLIP_PAD_POST)
    return raw, merged


# ======================= main =======================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="?", default=None)
    ap.add_argument("--ball-dir", default="outputs/ball_track")
    ap.add_argument("--track-dir", default="outputs/track_results/sn_soccana_botsort_gmc")
    ap.add_argument("--team-json", default="outputs/team_assign/track_teams.json")
    ap.add_argument("--zip", default="datasets/soccernet_gsr/test.zip")
    ap.add_argument("--out", default="outputs/events")
    ap.add_argument("--ball-teleport-mps", type=float, default=BALL_TELEPORT_MPS)
    args = ap.parse_args()

    seqs = [args.seq] if args.seq else SEQS_DEFAULT
    for seq in seqs:
        print(f"\n=== {seq} ===")
        out_seq = Path(args.out) / seq
        out_seq.mkdir(parents=True, exist_ok=True)

        recs = load_ball(Path(args.ball_dir), seq)
        n = len(recs)
        players = load_players(Path(args.track_dir) / f"{seq}.txt")
        teams = load_teams(Path(args.team_json), seq)
        label = load_action_label(Path(args.zip), seq)
        print(f"  frames={n}  players_tracks={len(teams)}  "
              f"GSR label='{label.get('action_class')}' @f{label.get('approx_frame')}")

        feat = compute_features(recs, players, teams, n, FPS, args.ball_teleport_mps)
        plausibility(feat, label)

        feat_out = dict(feat); feat_out["label"] = label
        (out_seq / "features.json").write_text(json.dumps(feat_out))
        plot_features(feat, label, out_seq / "features_plot.png", seq)

        # ---- PART B: high-recall detectors ----
        raw, merged = detect_events(feat)
        from collections import Counter
        by_type = Counter(e["type"] for e in raw)
        print(f"  candidates (raw): " + ", ".join(f"{k}={v}" for k, v in sorted(by_type.items()))
              + f"  | merged windows={len(merged)}")
        # does a candidate cover the GSR-labeled action frame?
        af = label.get("approx_frame")
        if af is not None:
            hit = any(m["start"] <= af - 1 <= m["end"] for m in merged)
            covtypes = sorted({t for m in merged if m["start"] <= af - 1 <= m["end"] for t in m["types"]})
            print(f"  GSR label '{label['action_class']}' @f{af} covered by a window: "
                  f"{hit}" + (f" via {covtypes}" if hit else ""))
        (out_seq / "events.json").write_text(json.dumps({
            "seq": seq, "n": n, "fps": FPS, "label": label,
            "merged_windows": merged, "raw_events": raw,
            "thresholds": {"SHOT_SPD": SHOT_SPD, "SHOT_HEAD": SHOT_HEAD, "SHOT_RANGE": SHOT_RANGE,
                           "TRANS_SPD": TRANS_SPD, "HALT_SPD": HALT_SPD,
                           "BALL_TELEPORT_MPS": args.ball_teleport_mps,
                           "note": "camera-scale-dependent; RE-TUNE at DPS mount"},
        }, indent=2))
        print(f"  wrote features.json + features_plot.png + events.json")


if __name__ == "__main__":
    main()
