"""Day 21 (Parts C-D): TEAM-AGNOSTIC basketball coach deliverable -- analytics PDF + tactical video.

Applies the Day-21 court homography (scripts/basketball_court.py) to the existing basketball player
tracks (Day-9) + ball track (Day-19) to compute analytics in COURT-METERS, then assembles a coach
PDF + tactical video adapted from the Day-20 football pipeline.

HONESTY (read first -- this is ONE COMPONENT BEHIND football, by design):
  - The homography is PLAUSIBILITY-validated, NOT GT-validated (no court-meter GT exists; cf.
    football's 0.2 m GSR validation). Same honesty level as the Day-19 basketball ball track.
    So the "validated" band in this PDF is THINNER and explicitly marked plausibility-level.
  - There is NO basketball TEAM ASSIGNMENT yet (football got it in Day-11). So everything here is
    TEAM-AGNOSTIC: all-players heatmap, total distance, court territory, intensity, avg positions.
    Team-split heatmaps + possession are DEFERRED to a future basketball-team-assignment session.
  - SportsMOT footage PANS constantly -> a single homography only holds for a short stable window
    (~4 s, c007 f493-591). This is a METHOD DEMO on that window. The deployment fixed camera removes
    this limit (mark once, holds the match). Numbers are illustrative, not a full-game report.

Intensity speed bands: basketball lacks football's single standardized GPS band set. Adapted from
basketball time-motion analysis (McInnes et al. 1995 J Sports Sci; Stojanovic et al. 2018 Sports
Med) -- basketball high-speed efforts are SHORT bursts on a small court, so the high-intensity
threshold is lower than football's. Bands (m/s): stand/walk <1.4, jog 1.4-3, run 3-4.5,
high-intensity 4.5-6, sprint >6. Teleport guard: per-step >9 m/s (above basketball peak ~8.5 m/s)
treated as ID-switch artefact (Day-20 guard, basketball-tuned). Cited + caveated, not invented.

Usage:
  python scripts/coach_deliverable_basketball.py v_00HRwkvvjtQ_c007 --win 493 591
"""
import argparse, json
from collections import defaultdict
from pathlib import Path
import sys
import numpy as np
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Arc

sys.path.insert(0, str(Path(__file__).parent))
import basketball_court as bc

FPS = 25
SMOOTH_WIN = 5
SPEED_BANDS = [("Stand/walk", 0.0, 1.4), ("Jog", 1.4, 3.0), ("Run", 3.0, 4.5),
               ("High-intensity", 4.5, 6.0), ("Sprint", 6.0, 99.0)]
SPEED_ARTEFACT = 9.0    # m/s; above basketball peak (~8.5) -> ID-switch teleport
HIGH_THRESH = 4.5
PLAYER_BGR = (40, 200, 40)   # team-agnostic fallback (when no team labels)
BALL_BGR = (0, 215, 255)
# Day-22 team colours. Mapping is by jersey colour (set in bball_team_assign): TeamA = Wichita
# white, TeamB = Kentucky blue (the user's labeling convention: white = A, blue = B). Drawn in
# high-contrast amber/blue for readability (white wouldn't show); legend names the jerseys.
TEAM_BGR = {"TeamA": (40, 170, 245), "TeamB": (235, 140, 30), "Referee": (0, 215, 255),
            "Excluded": (150, 150, 150)}
TEAM_RGB = {"TeamA": (0.96, 0.55, 0.0), "TeamB": (0.12, 0.45, 0.85)}
TEAM_LABEL = {"TeamA": "Team A (white)", "TeamB": "Team B (blue)"}
POSSESSION_MAX_M = 3.0       # nearest on-court player within this -> in possession (Day-12 method)


def load_team_map(path, seq):
    """{tid(int): role}. Returns None if no team assignment yet (team-agnostic fallback)."""
    p = Path(path)
    if not p.exists():
        return None
    tt = json.loads(p.read_text()).get(seq, {})
    return {int(t): v["role"] for t, v in tt.items()} if tt else None


def smooth_xy(xy, win=SMOOTH_WIN):
    if len(xy) < 2:
        return xy.copy()
    k = max(1, win // 2)
    pad = np.pad(xy, ((k, k), (0, 0)), mode="edge")
    ker = np.ones(win) / win
    return np.stack([np.convolve(pad[:, 0], ker, "valid"),
                     np.convolve(pad[:, 1], ker, "valid")], axis=1)[:len(xy)]


def load_tracks(track_path, win):
    """{tid: [(frame, feet_x_px, feet_y_px)]} within window; also {frame:[(tid,x,y,w,h)]}."""
    by_tid = defaultdict(list); by_frame = defaultdict(list)
    for line in Path(track_path).read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(",")
        f = int(p[0])
        if not (win[0] <= f <= win[1]):
            continue
        tid = int(p[1]); x, y, w, h = float(p[2]), float(p[3]), float(p[4]), float(p[5])
        by_tid[tid].append((f, x + w / 2, y + h)); by_frame[f].append((tid, x, y, w, h))
    return by_tid, by_frame


def project_tracks(by_tid, H_ci, m):
    """{tid: court_xy (N,2)} smoothed, in-bounds-clipped to the court."""
    out = {}
    for tid, rows in by_tid.items():
        rows = sorted(rows)
        feet = [(r[1], r[2]) for r in rows]
        court = bc.apply_H(H_ci, feet)
        # keep only points within a small margin of court (drop wild projections)
        ok = (np.abs(court[:, 0]) <= m["hx"] + 2) & (np.abs(court[:, 1]) <= m["hy"] + 2)
        if ok.sum() >= 2:
            out[tid] = smooth_xy(court[ok])
    return out


def inbounds_fraction(by_tid, H_ci, m):
    """Fraction of ALL raw projected player feet (over the window) that land inside the court
    (+1.5 m margin). Computed here so it works regardless of how the court was calibrated."""
    feet = [(r[1], r[2]) for rows in by_tid.values() for r in rows]
    if not feet:
        return None
    c = bc.apply_H(H_ci, feet)
    return float(np.mean((np.abs(c[:, 0]) <= m["hx"] + 1.5) & (np.abs(c[:, 1]) <= m["hy"] + 1.5)))


def calib_quality(hj, val):
    """Source-agnostic calibration readout: prefer the manual-marking landmark reconstruction error
    (metres); fall back to the (retired) auto-register pixel residual; else 'n/a'."""
    if hj.get("landmark_recon_mean_m") is not None:
        return {"method": hj.get("method", val.get("method", "manual")),
                "label": "landmark recon", "value": f"{hj['landmark_recon_mean_m']:.1f} m"}
    reg = (val or {}).get("register") or (hj or {}).get("register")
    if reg and reg.get("cost") is not None:
        return {"method": "auto-register (retired)", "label": "align resid", "value": f"{reg['cost']:.0f} px"}
    return {"method": val.get("method", "unknown"), "label": "calib", "value": "n/a"}


def ball_court_points(traj, win, H_ci, m):
    pts = []
    for r in traj:
        f = r.get("frame")
        if f is None or not (win[0] <= f <= win[1]):
            continue
        if r.get("x") is not None:
            c = bc.apply_H(H_ci, [(r["x"], r["y"])])[0]
            if abs(c[0]) <= m["hx"] + 2 and abs(c[1]) <= m["hy"] + 2:
                pts.append((float(c[0]), float(c[1])))
    return pts


# ---------------- metrics ----------------
def total_distance(proj):
    tot = 0.0; artefact = 0.0
    for xy in proj.values():
        if len(xy) < 2:
            continue
        step = np.linalg.norm(np.diff(xy, axis=0), axis=1); spd = step * FPS
        tot += step[spd <= SPEED_ARTEFACT].sum(); artefact += step[spd > SPEED_ARTEFACT].sum()
    return round(tot, 1), round(artefact, 1)


def intensity(proj):
    band_m = {b[0]: 0.0 for b in SPEED_BANDS}; artefact = 0.0
    for xy in proj.values():
        if len(xy) < 2:
            continue
        step = np.linalg.norm(np.diff(xy, axis=0), axis=1); spd = step * FPS
        for d, v in zip(step, spd):
            if v > SPEED_ARTEFACT:
                artefact += d; continue
            for nm, lo, hi in SPEED_BANDS:
                if lo <= v < hi:
                    band_m[nm] += d; break
    high = band_m["High-intensity"] + band_m["Sprint"]
    return {k: round(v, 1) for k, v in band_m.items()}, round(high, 1), round(artefact, 1)


def territory(proj, ball_pts, m):
    xs = [p[0] for xy in proj.values() for p in xy] + [b[0] for b in ball_pts]
    xs = np.clip(np.array(xs), -m["hx"], m["hx"])
    edges = [-m["hx"], -m["hx"] / 3, m["hx"] / 3, m["hx"]]
    counts = np.histogram(xs, bins=edges)[0].astype(float)
    pct = 100 * counts / counts.sum() if counts.sum() else counts
    return dict(zip(["Left third", "Middle third", "Right third"], pct.round(1).tolist()))


def avg_positions(proj, min_frames=40):
    return [(tid, float(xy[:, 0].mean()), float(xy[:, 1].mean()), len(xy))
            for tid, xy in proj.items() if len(xy) >= min_frames]


def max_speed(proj):
    mx = 0.0
    for xy in proj.values():
        if len(xy) < 2:
            continue
        spd = np.linalg.norm(np.diff(xy, axis=0), axis=1) * FPS
        spd = spd[spd <= SPEED_ARTEFACT]
        if len(spd):
            mx = max(mx, float(spd.max()))
    return round(mx, 1)


# ---------------- court figure helpers ----------------
def _court_ax(ax, m):
    hx, hy, lhw, ftx, bx = m["hx"], m["hy"], m["lhw"], m["ftx"], m["bx"]
    ax.set_facecolor("#caa472")
    ax.add_patch(Rectangle((-hx, -hy), 2 * hx, 2 * hy, fill=False, ec="white", lw=2))
    ax.plot([0, 0], [-hy, hy], color="white", lw=1.5)
    ax.add_patch(Circle((0, 0), m["ft_r"], fill=False, ec="white", lw=1.5))
    for s in (1, -1):
        ax.add_patch(Rectangle((s * hx - s * m["lane_len"], -lhw), s * m["lane_len"], 2 * lhw,
                               fill=False, ec="white", lw=1.5))
        ax.add_patch(Circle((s * ftx, 0), m["ft_r"], fill=False, ec="white", lw=1.5))
        ax.add_patch(Arc((s * bx, 0), 2 * m["arc_r"], 2 * m["arc_r"],
                         theta1=90 if s > 0 else -90, theta2=270 if s > 0 else 90, color="white", lw=1.5))
        ax.add_patch(Circle((s * bx, 0), 0.23, fill=False, ec="#d35400", lw=1.6))
    ax.set_xlim(-hx - 1, hx + 1); ax.set_ylim(hy + 1, -hy - 1); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])


def fig_heatmap(proj, m, out, title):
    pts = np.array([p for xy in proj.values() for p in xy]) if proj else np.empty((0, 2))
    fig, ax = plt.subplots(figsize=(8.0, 4.6), dpi=130)
    _court_ax(ax, m)
    if len(pts):
        ax.hist2d(pts[:, 0], pts[:, 1], bins=[36, 20], range=[[-m["hx"], m["hx"]], [-m["hy"], m["hy"]]],
                  cmap="hot", alpha=0.62)
    ax.set_title(title, fontsize=10)
    fig.tight_layout(); fig.savefig(out, facecolor="#caa472", bbox_inches="tight"); plt.close(fig)


def fig_positions(avg, m, out, title):
    fig, ax = plt.subplots(figsize=(8.0, 4.6), dpi=130)
    _court_ax(ax, m)
    if avg:
        ax.scatter([a[1] for a in avg], [a[2] for a in avg], s=240, c="#1565c0",
                   edgecolors="white", linewidths=1.3, zorder=5)
        for tid, x, y, _ in avg:
            ax.text(x, y, str(tid), ha="center", va="center", fontsize=7, color="white", zorder=6)
    ax.set_title(title, fontsize=10)
    fig.tight_layout(); fig.savefig(out, facecolor="#caa472", bbox_inches="tight"); plt.close(fig)


def fig_territory(terr, out, title):
    fig, ax = plt.subplots(figsize=(7.0, 3.2), dpi=130)
    names = list(terr.keys()); vals = list(terr.values())
    b = ax.bar(names, vals, color=["#90a4ae", "#42a5f5", "#90a4ae"], edgecolor="black")
    for bb, v in zip(b, vals):
        ax.text(bb.get_x() + bb.get_width() / 2, v + 1, f"{v:.0f}%", ha="center", fontweight="bold")
    ax.set_ylim(0, max(vals) + 12); ax.set_ylabel("% of play (players+ball)")
    ax.set_title(title, fontsize=10); ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(out, bbox_inches="tight"); plt.close(fig)


def fig_intensity(bands, out, title):
    fig, ax = plt.subplots(figsize=(7.0, 3.3), dpi=130)
    names = [b[0] for b in SPEED_BANDS]; vals = [bands[n] for n in names]
    ax.bar(names, vals, color="#26a69a", edgecolor="black")
    ax.set_ylabel("distance (m)")
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([f"{b}\n{lo:g}-{hi:g}" if hi < 90 else f"{b}\n>{lo:g}" for b, lo, hi in SPEED_BANDS],
                       fontsize=8)
    ax.set_title(title, fontsize=10); ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(out, bbox_inches="tight"); plt.close(fig)


def fig_team_heatmaps(proj, team_map, m, out, seq, win):
    """Two side-by-side court density panels, one per team (the Day-22 deferred panel)."""
    fig, axs = plt.subplots(1, 2, figsize=(9.4, 2.9), dpi=130)
    for ax, team in zip(axs, ("TeamA", "TeamB")):
        _court_ax(ax, m)
        pts = np.array([p for tid, xy in proj.items()
                        if team_map.get(tid) == team for p in xy]) if proj else np.empty((0, 2))
        if len(pts):
            ax.hist2d(pts[:, 0], pts[:, 1], bins=[30, 17],
                      range=[[-m["hx"], m["hx"]], [-m["hy"], m["hy"]]], cmap="hot", alpha=0.62)
        ax.set_title(f"{TEAM_LABEL[team]}  (n={len(pts)})", fontsize=9)
    fig.suptitle(f"Team-split positional density  -  {seq} f{win[0]}-{win[1]}", fontsize=10)
    fig.tight_layout(); fig.savefig(out, facecolor="#caa472", bbox_inches="tight"); plt.close(fig)


def compute_possession(by_frame, traj, win, H_ci, m, team_map):
    """Day-12 nearest-player-to-ball possession, by team, in court-metres. Each frame with a ball
    and an on-court player within POSSESSION_MAX_M is credited to that player's team."""
    poss = {r["frame"]: r for r in traj}
    counts = {"TeamA": 0, "TeamB": 0}; per_frame = []; n_no_ball = 0; n_far = 0
    for f in range(win[0], win[1] + 1):
        r = poss.get(f)
        if not r or r.get("x") is None:
            n_no_ball += 1; continue
        bc_xy = bc.apply_H(H_ci, [(r["x"], r["y"])])[0]
        best_team, best_d = None, 1e9
        for (tid, x, y, w, h) in by_frame.get(f, []):
            team = team_map.get(tid)
            if team not in ("TeamA", "TeamB"):
                continue
            pc = bc.apply_H(H_ci, [(x + w / 2, y + h)])[0]
            if abs(pc[0]) > m["hx"] + 1.5 or abs(pc[1]) > m["hy"] + 1.5:
                continue
            d = float(np.hypot(pc[0] - bc_xy[0], pc[1] - bc_xy[1]))
            if d < best_d:
                best_d, best_team = d, team
        if best_team is None or best_d > POSSESSION_MAX_M:
            n_far += 1; continue
        counts[best_team] += 1; per_frame.append([f, best_team])
    total = counts["TeamA"] + counts["TeamB"]
    pa = 100 * counts["TeamA"] / total if total else 0.0
    return {"teamA_pct": round(pa, 1), "teamB_pct": round(100 - pa, 1) if total else 0.0,
            "n_counted": total, "n_total": win[1] - win[0] + 1,
            "excluded": {"no_ball": n_no_ball, "no_close_player": n_far}, "per_frame": per_frame}


# ---------------- PDF ----------------
def build_pdf(seq, win, metrics, val, outdir, pdf_path):
    fig = plt.figure(figsize=(8.27, 11.69), dpi=150); fig.patch.set_facecolor("white")
    gs = fig.add_gridspec(100, 100, left=0.05, right=0.95, top=0.97, bottom=0.03)

    def img(sl, png):
        ax = fig.add_subplot(sl); ax.axis("off"); ax.imshow(plt.imread(str(png)))

    teamed = bool(val.get("team_map"))
    poss = val.get("possession")
    tacc = val.get("team_acc")
    team_val_txt = (f"hand-label-validated ({tacc*100:.0f}% team accuracy)" if tacc is not None
                    else "torso-colour clustering — accuracy validation PENDING hand-labels")
    hax = fig.add_subplot(gs[0:6, :]); hax.axis("off"); hax.set_xlim(0, 1); hax.set_ylim(0, 1)
    hax.text(0.0, 0.82, "AI Match Analysis - Basketball", fontsize=20, fontweight="bold", color="#b35900")
    hax.text(1.0, 0.86, f"~{(win[1]-win[0]+1)/FPS:.0f} s method demo", fontsize=10, color="#888", ha="right")
    hax.text(0.0, 0.42, f"Clip {seq}  f{win[0]}-{win[1]}  ·  basketball  ·  2026-05-29", fontsize=10, color="#444")
    hax.text(0.0, 0.10, ("Automated court-metre analytics via a basketball court homography + team assignment."
                         if teamed else "Automated court-metre analytics via a basketball court homography (team-agnostic)."),
             fontsize=8.5, color="#888", style="italic")
    hax.axhline(0.0, color="#b35900", lw=2)

    lab = fig.add_subplot(gs[7:10, :]); lab.axis("off")
    lab.add_patch(Rectangle((0, 0), 1, 1, color="#8d6e63"))
    lab.text(0.01, 0.5, "  PLAUSIBILITY-VALIDATED  -  homography hand-marked (no court GT, cf. football 0.2 m); "
             + ("teams hand-label-validated" if tacc is not None else "team validation pending"),
             color="white", fontsize=7.6, fontweight="bold", va="center")

    img(gs[11:33, 0:60], outdir / "fig_heatmap.png")
    sax = fig.add_subplot(gs[11:33, 62:100]); sax.axis("off"); sax.set_xlim(0, 1); sax.set_ylim(0, 1)
    cal = val.get("calib", {"method": "manual", "label": "calib", "value": "n/a"})
    sax.text(0.0, 0.94, "Court calibration", fontsize=10.5, fontweight="bold")
    sax.text(0.0, 0.84, f"in-bounds: {100*val['in_bounds_frac']:.0f}%   ({cal['label']} {cal['value']})", fontsize=8.5, color="#33691e")
    sax.text(0.0, 0.66, "Total distance (all)", fontsize=10.5, fontweight="bold")
    sax.text(0.0, 0.54, f"{metrics['total_distance_m']:.0f} m", fontsize=15, color="#b35900", fontweight="bold")
    sax.text(0.0, 0.45, f"{metrics['n_tracks']} tracks · max {metrics['max_speed_ms']:.1f} m/s", fontsize=7.5, color="#888")
    if teamed and poss:
        sax.text(0.0, 0.30, "Possession", fontsize=10.5, fontweight="bold")
        sax.text(0.0, 0.18, f"A {poss['teamA_pct']:.0f}%   B {poss['teamB_pct']:.0f}%", fontsize=14,
                 color="#b35900", fontweight="bold")
        sax.text(0.0, 0.08, f"(nearest-player; {poss['n_counted']}/{poss['n_total']} frames)", fontsize=7.0, color="#888")

    # team analytics band (Day-22: the previously-deferred panels)
    if teamed:
        lab1 = fig.add_subplot(gs[35:38, :]); lab1.axis("off")
        lab1.add_patch(Rectangle((0, 0), 1, 1, color="#2e7d32"))
        lab1.text(0.01, 0.5, f"  TEAM ANALYTICS  -  team assignment {team_val_txt}  ·  A = white jerseys, B = blue",
                  color="white", fontsize=7.4, fontweight="bold", va="center")
        img(gs[39:60, 0:100], outdir / "fig_team_heatmaps.png")
        derived_top = 62
    else:
        derived_top = 35

    lab2 = fig.add_subplot(gs[derived_top:derived_top + 3, :]); lab2.axis("off")
    lab2.add_patch(Rectangle((0, 0), 1, 1, color="#1565c0"))
    lab2.text(0.01, 0.5, "  DERIVED ANALYTICS  -  geometric summaries of the calibrated court positions",
              color="white", fontsize=8.5, fontweight="bold", va="center")
    dt = derived_top + 4
    img(gs[dt:dt + 18, 0:50], outdir / "fig_positions.png")
    img(gs[dt:dt + 11, 50:100], outdir / "fig_territory.png")
    img(gs[dt + 11:dt + 23, 50:100], outdir / "fig_intensity.png")

    fax = fig.add_subplot(gs[88:100, :]); fax.axis("off"); fax.set_xlim(0, 1); fax.set_ylim(0, 1)
    fax.axhline(0.98, color="#bbb", lw=1)
    fax.text(0.0, 0.84, "Coming soon", fontsize=9, fontweight="bold", color="#555")
    fax.text(0.0, 0.60, "Pass networks and per-player stat lines (per-player needs ReID for ID-switch noise).",
             fontsize=7.6, color="#777")
    fax.text(0.0, 0.30, "Honest status", fontsize=9, fontweight="bold", color="#555")
    fax.text(0.0, 0.06, f"Homography hand-marked (0.2 m landmark recon); team assignment {team_val_txt}. "
             f"~{(win[1]-win[0]+1)/FPS:.0f}s single-homography demo on panning broadcast; fixed deployment camera removes that limit.",
             fontsize=7.0, color="#777")
    fax.text(1.0, 0.0, "Generated by AI Sports Analytics  -  method demo on SportsMOT footage",
             fontsize=6.5, color="#aaa", ha="right")
    fig.savefig(pdf_path, format="pdf", facecolor="white")
    fig.savefig(str(pdf_path).replace(".pdf", "_preview.png"), facecolor="white", dpi=150)
    plt.close(fig)


# ---------------- tactical video ----------------
def render_video(seq, win, by_frame, traj, frames_dir, out_mp4, scale=0.75, contact=True,
                 outdir=None, team_map=None):
    img0 = cv2.imread(str(frames_dir / f"{win[0]:06d}.jpg")); H, W = img0.shape[:2]
    poss_x = {r["frame"]: r for r in traj}
    teamed = bool(team_map)

    def pcolor(tid):
        if not teamed:
            return PLAYER_BGR
        return TEAM_BGR.get(team_map.get(tid), (150, 150, 150))

    def draw(img, f):
        for (tid, x, y, w, h) in by_frame.get(f, []):
            x, y, w, h = int(x), int(y), int(w), int(h); col = pcolor(tid)
            cv2.rectangle(img, (x, y), (x + w, y + h), col, 2)
            cv2.ellipse(img, (x + w // 2, y + h), (16, 6), 0, 0, 360, col, 2)
            cv2.putText(img, str(tid), (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2, cv2.LINE_AA)
        r = poss_x.get(f)
        if r and r.get("x") is not None:
            bx, by = int(r["x"]), int(r["y"]); det = r.get("status") == "detected"
            cv2.circle(img, (bx, by), 8, BALL_BGR, -1 if det else 2)
            cv2.circle(img, (bx, by), 13, (0, 0, 0), 1)
            if not det:
                cv2.putText(img, "pred", (bx + 14, by), cv2.FONT_HERSHEY_SIMPLEX, 0.45, BALL_BGR, 1, cv2.LINE_AA)
        ov = img.copy(); cv2.rectangle(ov, (0, H - 44), (W, H), (0, 0, 0), -1)
        cv2.addWeighted(ov, 0.45, img, 0.55, 0, img)
        title = f"{seq}  tactical view  f{f}" if teamed else f"{seq}  tactical view (team-agnostic)  f{f}"
        cv2.putText(img, title, (14, H - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
        if teamed:
            cv2.putText(img, "Team A", (14, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, TEAM_BGR["TeamA"], 2, cv2.LINE_AA)
            cv2.putText(img, "Team B", (14, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.6, TEAM_BGR["TeamB"], 2, cv2.LINE_AA)
            cv2.putText(img, "ball", (14, 76), cv2.FONT_HERSHEY_SIMPLEX, 0.6, BALL_BGR, 2, cv2.LINE_AA)
        else:
            cv2.putText(img, "players", (14, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, PLAYER_BGR, 2, cv2.LINE_AA)
            cv2.putText(img, "ball", (14, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.6, BALL_BGR, 2, cv2.LINE_AA)
        return img

    if contact and outdir:
        idxs = np.linspace(win[0], win[1], 6).astype(int); tw = 640; th = int(640 * H / W); tiles = []
        for f in idxs:
            im = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
            if im is None:
                continue
            t = cv2.resize(draw(im, f), (tw, th), interpolation=cv2.INTER_AREA)
            cv2.putText(t, f"f{f}", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (40, 240, 40), 2)
            tiles.append(t)
        rows = [np.hstack(tiles[i:i + 2]) for i in range(0, len(tiles), 2)]
        cv2.imwrite(str(outdir / "tactical_contact_sheet.png"), np.vstack(rows))

    ow, oh = int(W * scale) - int(W * scale) % 2, int(H * scale) - int(H * scale) % 2
    vw = cv2.VideoWriter(str(out_mp4), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (ow, oh)); n = 0
    for f in range(win[0], win[1] + 1):
        im = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
        if im is None:
            continue
        vw.write(cv2.resize(draw(im, f), (ow, oh), interpolation=cv2.INTER_AREA)); n += 1
    vw.release()
    return n, (ow, oh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq")
    ap.add_argument("--win", type=int, nargs=2, default=[493, 591])
    ap.add_argument("--deliverables", default="outputs/deliverables")
    ap.add_argument("--track", default="outputs/track_results/bball_ftdet_bytetrack")
    ap.add_argument("--ball", default="outputs/ball_track_bb")
    ap.add_argument("--frames-root", default="datasets/sportsmot_basketball")
    ap.add_argument("--team-assign", default="outputs/team_assign_bb/track_teams_emb.json")
    ap.add_argument("--no-video", action="store_true")
    args = ap.parse_args()
    seq, win = args.seq, tuple(args.win)

    court_dir = Path(args.deliverables) / seq / "court"
    hj = json.loads((court_dir / "homography.json").read_text())
    val = json.loads((court_dir / "validation.json").read_text())
    H_ci = np.array(hj["H_court_from_img"], np.float32)
    m = bc.court_model(hj.get("model", "ncaa"))
    outdir = Path(args.deliverables) / seq / "coach"
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"=== Day-21 basketball coach deliverable: {seq} f{win[0]}-{win[1]} ===")

    by_tid, by_frame = load_tracks(Path(args.track) / f"{seq}.txt", win)
    traj = json.loads((Path(args.ball) / seq / "trajectory.json").read_text())
    proj = project_tracks(by_tid, H_ci, m)
    ball_pts = ball_court_points(traj, win, H_ci, m)
    inb = inbounds_fraction(by_tid, H_ci, m)
    calib = calib_quality(hj, val)
    team_map = load_team_map(args.team_assign, seq)
    possession = compute_possession(by_frame, traj, win, H_ci, m, team_map) if team_map else None
    # validation file mirrors the team-assign file name (track_teams_*.json -> validation_*.json)
    valbb_path = Path(args.team_assign).with_name(Path(args.team_assign).name.replace("track_teams", "validation"))
    team_acc = None
    if valbb_path.exists():
        vj = json.loads(valbb_path.read_text())
        team_acc = vj.get("team_accuracy_post_alignment")          # Day-22 colour format
        if team_acc is None and vj.get("winner_region"):           # Day-23 embedding format
            team_acc = (vj.get(vj["winner_region"]) or {}).get("overall")
    if team_map:
        from collections import Counter as _C
        print(f"  TEAM-AWARE: {dict(_C(team_map.get(t) for t in proj))}  | "
              f"possession A {possession['teamA_pct']}/B {possession['teamB_pct']} "
              f"(counted {possession['n_counted']}/{possession['n_total']})")

    tot, tot_art = total_distance(proj)
    bands, high_m, band_art = intensity(proj)
    terr = territory(proj, ball_pts, m)
    avg = avg_positions(proj)
    mxs = max_speed(proj)
    metrics = {"seq": seq, "window": list(win), "n_tracks": len(proj),
               "total_distance_m": tot, "distance_artefact_m": tot_art,
               "intensity_bands_m": bands, "high_intensity_m": high_m, "intensity_artefact_m": band_art,
               "territory_pct": terr, "max_speed_ms": mxs,
               "avg_positions": [{"tid": a[0], "x": round(a[1], 2), "y": round(a[2], 2), "n": a[3]} for a in avg],
               "ball_court_points": len(ball_pts)}

    # plausibility checks
    band_sum = round(sum(bands.values()) + band_art, 1)
    print("\n-- PART C: analytics + plausibility --")
    print(f"  tracks projected: {len(proj)}  ball court-points: {len(ball_pts)}")
    print(f"  total distance: {tot} m (+artefact {tot_art} m)  max speed {mxs} m/s (guard {SPEED_ARTEFACT})")
    print(f"  intensity bands(m): {bands}  high-intensity={high_m}  artefact={band_art}")
    print(f"     bands+artefact={band_sum} vs total+artefact={round(tot+tot_art,1)}  (should match)")
    print(f"  territory: {terr}  sum={round(sum(terr.values()),1)}")
    print(f"  avg-position tracks (>=40 frames): {len(avg)}")
    print(f"  in-bounds (window): {100*inb:.0f}%  | calibration: {calib['method']} "
          f"({calib['label']} {calib['value']})")
    metrics["calibration"] = calib
    metrics["plausibility"] = {"territory_sum": round(sum(terr.values()), 1),
                               "bands_plus_artefact_m": band_sum, "total_plus_artefact_m": round(tot + tot_art, 1),
                               "max_speed_ms": mxs, "in_bounds_frac": inb}

    fig_heatmap(proj, m, outdir / "fig_heatmap.png", f"All-players court density  -  {seq} f{win[0]}-{win[1]}")
    fig_positions(avg, m, outdir / "fig_positions.png", f"Average positions (team-agnostic)  -  {seq}")
    fig_territory(terr, outdir / "fig_territory.png", f"Court territory / tilt  -  {seq}")
    fig_intensity(bands, outdir / "fig_intensity.png", f"Intensity zones (basketball bands, m/s)  -  {seq}")
    if team_map:
        fig_team_heatmaps(proj, team_map, m, outdir / "fig_team_heatmaps.png", seq, win)
        metrics["possession"] = possession
        metrics["team_counts"] = {t: sum(1 for x in proj if team_map.get(x) == t) for t in ("TeamA", "TeamB")}
    (outdir / "metrics_basketball.json").write_text(json.dumps(metrics, indent=2))

    pdf = outdir / "coach_analysis_basketball.pdf"
    build_pdf(seq, win, metrics, {"in_bounds_frac": inb, "calib": calib, "team_map": team_map,
                                  "possession": possession, "team_acc": team_acc}, outdir, pdf)
    print(f"\n-- PART D: PDF -> {pdf} (+ _preview.png)")

    if not args.no_video:
        frames_dir = Path(args.frames_root) / seq / "img1"
        out_mp4 = outdir / "tactical_sample_basketball.mp4"
        n, (W, H) = render_video(seq, win, by_frame, traj, frames_dir, out_mp4, outdir=outdir,
                                 team_map=team_map)
        print(f"-- tactical video {W}x{H}, {n} frames -> {out_mp4}")
        print(f"   contact sheet -> {outdir / 'tactical_contact_sheet.png'}")
    print(f"\nDONE -> {outdir}")


if __name__ == "__main__":
    main()
