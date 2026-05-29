"""Day 21: basketball COURT HOMOGRAPHY (pixel -> court-meters) + plausibility validation.

Football got real-meter analytics from the Day-10 homography (GSR shipped bbox_pitch -> GT-
validated to 0.2 m). Basketball has NO court-meter ground truth (SportsMOT = pixel boxes only;
Day-18 confirmed basketball court/ball-coord GT is a dead-end hunt). So this homography is
PLAUSIBILITY-validated, NOT GT-validated -- the same honesty level as the Day-19 basketball ball
track. Labelled so everywhere.

DEPLOYMENT REFRAME (user-flagged): the school court's line state is UNKNOWN -- it may be faded /
missing / multi-sport-overlaid / non-regulation / outdoor. So the method must NOT assume clean
regulation markings. Design = AUTO-detect (try first) with a MANUAL one-time point-marking
FALLBACK. The deployment camera is FIXED (no zoom/cuts) -> mark once, holds the whole match. That
makes the real deployment EASIER than this SportsMOT broadcast (which pans constantly, so a single
homography only holds for a short stable window -- here ~4 s on c007 f493-591).

MANUAL is the REQUIRED path. Calibrate with scripts/mark_court.py (a GUI app: click court points,
live overlay, save). The automatic attempts here are kept FOR THE RECORD ONLY:
  - --auto: blackhat + HoughLinesP finds court-line candidates + a blue center-logo blob but CANNOT
    reliably LABEL which line is which on broadcast (logos/text/crowd/occlusion) -> defers to manual.
  - --register: camera-pose chamfer registration. UNRELIABLE -- its projected-court overlay can be
    VISUALLY VERY WRONG while still passing the players-in-bounds metric (an in-bounds score is
    satisfiable by a misaligned pose). Do NOT trust it; it is retained only to document the attempt.
This file still also supports --mark / --points (the inline marking + reproducible-points path used
before the standalone GUI app); mark_court.py is the friendlier, recommended tool.

Court model: NCAA men's (this clip is the 2014 NCAA tournament) 94 x 50 ft = 28.65 x 15.24 m.
FIBA (28 x 15 m) constants are also provided (--model fiba) for the school deployment if needed.

Outputs (outputs/deliverables/<seq>/court/):
  homography.json     H (img<->court), the marked points, held-out reconstruction error
  overlay.png         the court model projected back onto the frame (alignment = the eye test)
  court_diagram.png   top-down court with the frame's player feet projected into court-meters
  validation.json     plausibility gate: held-out reconstruction err, in-bounds %, speed sanity

Usage:
  python scripts/basketball_court.py v_00HRwkvvjtQ_c007 --frame 540 --auto
  python scripts/basketball_court.py v_00HRwkvvjtQ_c007 --frame 540 --mark        # click points
  python scripts/basketball_court.py v_00HRwkvvjtQ_c007 --frame 540 --points pts.json
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
import cv2

# ============================ court models (meters, origin = center court) ============================
def court_model(name="ncaa"):
    if name == "fiba":
        L, Wd = 28.0, 15.0; lane_w, lane_len = 4.9, 5.8; ft_r = 1.8; arc_r = 6.75
        basket = 1.575; corner3 = 6.6
    else:  # ncaa men's (2013-14)
        L, Wd = 28.65, 15.24; lane_w, lane_len = 3.6576, 5.7912; ft_r = 1.829; arc_r = 6.325
        basket = 1.575; corner3 = 6.02
    hx, hy = L / 2, Wd / 2
    bx = hx - basket               # right basket center x (left = -bx)
    ftx = hx - lane_len            # right free-throw line x
    return dict(name=name, L=L, Wd=Wd, hx=hx, hy=hy, lane_w=lane_w, lane_len=lane_len,
                ft_r=ft_r, arc_r=arc_r, basket=basket, bx=bx, ftx=ftx, corner3=corner3,
                lhw=lane_w / 2)

# Named landmark world coords (meters) -- the manual-marking vocabulary. Right half (+x) shown in
# c007 f540; mirror for left half. Corners are the most deployment-robust.
def landmarks(m):
    hx, hy, lhw, ftx, bx = m["hx"], m["hy"], m["lhw"], m["ftx"], m["bx"]
    return {
        "center":            (0.0, 0.0),
        "center_far":        (0.0, -hy),
        "center_near":       (0.0,  hy),
        "r_baseline_far":    ( hx, -hy),
        "r_baseline_near":   ( hx,  hy),
        "r_lane_base_far":   ( hx, -lhw),
        "r_lane_base_near":  ( hx,  lhw),
        "r_lane_ft_far":     (ftx, -lhw),
        "r_lane_ft_near":    (ftx,  lhw),
        "r_ft_center":       (ftx, 0.0),
        "r_arc_top":         (bx - m["arc_r"], 0.0),
        "r_basket":          (bx, 0.0),
        # left-half mirrors (for full-court frames)
        "l_baseline_far":    (-hx, -hy),
        "l_baseline_near":   (-hx,  hy),
        "l_ft_center":       (-ftx, 0.0),
        "l_basket":          (-bx, 0.0),
    }

# ============================ court polylines for the overlay / diagram ============================
def court_polylines(m, n_arc=40):
    hx, hy, lhw, ftx, bx = m["hx"], m["hy"], m["lhw"], m["ftx"], m["bx"]
    P = []
    P.append([(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy), (-hx, -hy)])      # boundary
    P.append([(0, -hy), (0, hy)])                                          # center line
    th = np.linspace(0, 2 * np.pi, n_arc)
    P.append([(m["ft_r"] * np.cos(t), m["ft_r"] * np.sin(t)) for t in th])  # center circle
    for s in (1, -1):                                                       # both ends
        bxx = s * bx; basex = s * hx; ftxx = s * ftx
        P.append([(basex, -lhw), (ftxx, -lhw), (ftxx, lhw), (basex, lhw)])  # lane
        P.append([(ftxx + m["ft_r"] * np.cos(t) * (-s), m["ft_r"] * np.sin(t))
                  for t in th])                                            # ft circle
        # 3pt arc: sweep angles facing center
        a = np.linspace(-np.pi / 2, np.pi / 2, n_arc) if s > 0 else np.linspace(np.pi / 2, 3 * np.pi / 2, n_arc)
        P.append([(bxx + m["arc_r"] * np.cos(t) * (-s) if False else bxx - s * m["arc_r"] * np.cos(t2),
                   m["arc_r"] * np.sin(t2)) for t2 in a])
    return P

# ============================ homography ============================
def solve_H(img_pts, court_pts):
    src = np.array(court_pts, np.float32); dst = np.array(img_pts, np.float32)
    H_img_from_court, _ = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    H_court_from_img = np.linalg.inv(H_img_from_court)
    return H_img_from_court, H_court_from_img

def apply_H(H, pts):
    pts = np.array(pts, np.float32).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, H).reshape(-1, 2)

def holdout_reconstruction(img_pts, court_pts, names, seed=0):
    """Leave-one-out: fit H on all-but-one marked points, project the held-out IMAGE point to
    court-m, compare to its KNOWN court coord. The closest thing to a trust gate without GT."""
    errs = []
    n = len(img_pts)
    if n < 5:
        return None, []
    for i in range(n):
        idx = [j for j in range(n) if j != i]
        Hi_ic, _ = cv2.findHomography(np.array([court_pts[j] for j in idx], np.float32),
                                      np.array([img_pts[j] for j in idx], np.float32), cv2.RANSAC, 5.0)
        if Hi_ic is None:
            continue
        Hi_ci = np.linalg.inv(Hi_ic)
        pred = apply_H(Hi_ci, [img_pts[i]])[0]
        e = float(np.hypot(pred[0] - court_pts[i][0], pred[1] - court_pts[i][1]))
        errs.append((names[i], round(e, 3)))
    vals = [e for _, e in errs]
    return (float(np.mean(vals)) if vals else None), errs

# ============================ line-snapping refinement (rough init -> precise) ============================
def court_edge_map(frame, player_boxes=None):
    """Thin dark court lines on bright wood, restricted to the court band, with player regions
    masked out (so we snap to LINES, not player silhouettes)."""
    H, W = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    bh = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)))
    _, e = cv2.threshold(bh, 22, 255, cv2.THRESH_BINARY)
    e[:int(H * 0.18)] = 0; e[int(H * 0.86):] = 0
    if player_boxes:
        for (x, y, w, h) in player_boxes:
            x0 = max(0, int(x - 4)); y0 = max(0, int(y - 4))
            e[y0:int(y + h + 8), x0:int(x + w + 8)] = 0   # erase player region
    return e

def _dense_polylines(m, step_m=0.4):
    """Court polylines resampled densely in court-meters, with per-point tangent for normals."""
    out = []
    for poly in court_polylines(m, n_arc=80):
        P = np.array(poly, float)
        for i in range(len(P) - 1):
            a, b = P[i], P[i + 1]
            d = np.hypot(*(b - a))
            k = max(1, int(d / step_m))
            for t in np.linspace(0, 1, k, endpoint=False):
                out.append(a + t * (b - a))
    return np.array(out)

def refine_homography(frame, H_ic, court_pts0, img_pts0, m, player_boxes=None,
                      iters=8, search0=22):
    """ICP-style: project dense court-line points, snap each to the nearest court-edge pixel along
    its normal, refit H. Robust (drops far snaps), shrinking search window. Returns refined H + the
    anchor points kept (so the user marks are still respected as soft anchors)."""
    e = court_edge_map(frame, player_boxes)
    ys, xs = np.where(e > 0)
    edge_pts = np.stack([xs, ys], 1).astype(np.float32)
    if len(edge_pts) < 50:
        return H_ic, np.linalg.inv(H_ic), {"refined": False, "reason": "too few court edges"}
    dense = _dense_polylines(m)
    H = H_ic.copy()
    anchors_court = list(court_pts0); anchors_img = list(img_pts0)  # keep user marks as anchors
    hist = []
    for it in range(iters):
        search = max(4, int(search0 * (1 - it / iters)))
        proj = apply_H(H, dense)                                   # court-line pts -> image
        # tangents from neighbours -> normals
        d = np.gradient(proj, axis=0)
        nrm = np.stack([-d[:, 1], d[:, 0]], 1)
        nrm /= (np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-6)
        src, dst = list(anchors_court), list(anchors_img)
        for i, p in enumerate(proj):
            if not (0 <= p[0] < frame.shape[1] and 0 <= p[1] < frame.shape[0]):
                continue
            dd = edge_pts - p
            close = dd[(np.abs(dd[:, 0]) < search) & (np.abs(dd[:, 1]) < search)]
            if len(close) == 0:
                continue
            # nearest edge pixel, projected onto the normal (line-to-line, ignore tangential slip)
            j = np.argmin(np.hypot(close[:, 0], close[:, 1]))
            off = close[j]
            normal_off = float(off @ nrm[i]) * nrm[i]
            found = p + normal_off
            if np.hypot(*normal_off) <= search:
                src.append(tuple(dense[i])); dst.append((float(found[0]), float(found[1])))
        if len(dst) < 8:
            break
        Hn, mask = cv2.findHomography(np.array(src, np.float32), np.array(dst, np.float32),
                                      cv2.RANSAC, 3.0)
        if Hn is None:
            break
        H = Hn; hist.append(int(mask.sum()) if mask is not None else 0)
    return H, np.linalg.inv(H), {"refined": True, "inlier_hist": hist, "n_edge_px": int(len(edge_pts))}

# ============================ camera-pose chamfer registration (robust auto-calibration) ============================
def _lookat(cam, target, up=(0, 0, 1.0)):
    cam = np.asarray(cam, float); target = np.asarray(target, float); up = np.asarray(up, float)
    fwd = target - cam; fwd /= np.linalg.norm(fwd)
    r = np.cross(fwd, up); r /= np.linalg.norm(r)
    u = np.cross(r, fwd)
    Rwc = np.stack([r, -u, fwd], 0)
    rvec, _ = cv2.Rodrigues(Rwc)
    return rvec.ravel(), (-Rwc @ cam)

def register_pose(frame, m, player_boxes=None, player_feet=None):
    """Auto court calibration by CAMERA-POSE chamfer matching: optimise a real camera (focal +
    look-at extrinsics) projecting the 3D court plane to minimise (a) distance between projected
    court lines and the player-masked court-edge map, AND (b) a penalty for projecting the known
    on-court players OUT of bounds. A real camera can't collapse the court (unlike a free 8-DOF
    homography fit), and the player-in-bounds prior rules out the low-chamfer-but-wrong solutions
    that pure edge matching falls into. Multi-start over plausible broadcast cameras."""
    from scipy.optimize import minimize
    H, W = frame.shape[:2]
    edge = court_edge_map(frame, player_boxes)
    dt = cv2.distanceTransform(cv2.bitwise_not(edge), cv2.DIST_L2, 3)
    dense = _dense_polylines(m, step_m=0.5)
    dense3 = np.hstack([dense, np.zeros((len(dense), 1))]).astype(np.float64)
    feet = np.array(player_feet, np.float32) if player_feet else None
    hx, hy = m["hx"], m["hy"]

    def Hic_of(p):
        f, cx, cy, cz, tx, ty = p
        K = np.array([[f, 0, W / 2], [0, f, H / 2], [0, 0, 1]], np.float64)
        rvec, tvec = _lookat([cx, cy, cz], [tx, ty, 0])
        Rm, _ = cv2.Rodrigues(rvec)
        Hic = K @ np.column_stack([Rm[:, 0], Rm[:, 1], tvec])
        return Hic / Hic[2, 2], K, rvec, tvec

    def cost(p):
        f, cx, cy, cz, tx, ty = p
        if f < 400 or f > 3500 or cz < 6 or cz > 18 or cy > -6:
            return 1e6
        try:
            Hic, *_ = Hic_of(p); Hci = np.linalg.inv(Hic)
            proj = apply_H(Hic, dense)
        except Exception:
            return 1e6
        x, y = proj[:, 0], proj[:, 1]; inb = (x >= 0) & (x < W) & (y >= 0) & (y < H)
        if inb.sum() < len(proj) * 0.45:
            return 1e6 + (len(proj) - inb.sum())
        xs = np.clip(x[inb], 0, W - 1).astype(int); ys = np.clip(y[inb], 0, H - 1).astype(int)
        c = dt[ys, xs].mean() + (1 - inb.mean()) * 25
        if feet is not None and len(feet):                       # players-on-court prior
            pc = apply_H(Hci, feet)
            oob = np.mean((np.abs(pc[:, 0]) > hx + 1.0) | (np.abs(pc[:, 1]) > hy + 1.0))
            c += oob * 40
        return c

    best = None
    for f0 in (800, 1300, 1900):
        for cz0 in (8, 11, 14):
            for cy0 in (-14, -20):
                for tx0 in (-7, 7):
                    s = [f0, 0, cy0, cz0, tx0, 0]
                    r = minimize(cost, s, method="Nelder-Mead",
                                 options={"maxiter": 3000, "xatol": 1e-2, "fatol": 1e-3})
                    if best is None or r.fun < best.fun:
                        best = r
    Hic, K, rvec, tvec = Hic_of(best.x)
    return Hic, np.linalg.inv(Hic), {"method": "pose-chamfer+inbounds",
                                     "cost": round(float(best.fun), 2),
                                     "cam": np.round(best.x, 2).tolist()}

# ============================ rendering ============================
def draw_overlay(frame, H_ic, m, marked=None, out_path=None):
    vis = frame.copy()
    for poly in court_polylines(m):
        pix = apply_H(H_ic, poly).astype(np.int32)
        cv2.polylines(vis, [pix], False, (0, 255, 255), 2, cv2.LINE_AA)
    if marked:
        for (px, py), nm in marked:
            cv2.circle(vis, (int(px), int(py)), 6, (0, 0, 255), -1)
            cv2.putText(vis, nm, (int(px) + 6, int(py) - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (0, 255, 0), 1, cv2.LINE_AA)
    if out_path:
        cv2.imwrite(str(out_path), vis)
    return vis

def draw_court_diagram(m, player_xy=None, ball_xy=None, heat=None, out_path=None, title=""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Circle, Arc
    hx, hy, lhw, ftx, bx = m["hx"], m["hy"], m["lhw"], m["ftx"], m["bx"]
    fig, ax = plt.subplots(figsize=(8.6, 4.9), dpi=130)
    ax.set_facecolor("#caa472")
    ax.add_patch(Rectangle((-hx, -hy), 2 * hx, 2 * hy, fill=False, ec="white", lw=2))
    ax.plot([0, 0], [-hy, hy], color="white", lw=1.5)
    ax.add_patch(Circle((0, 0), m["ft_r"], fill=False, ec="white", lw=1.5))
    for s in (1, -1):
        ax.add_patch(Rectangle((s * hx - s * m["lane_len"], -lhw), s * m["lane_len"], 2 * lhw,
                               fill=False, ec="white", lw=1.5))
        ax.add_patch(Circle((s * ftx, 0), m["ft_r"], fill=False, ec="white", lw=1.5))
        ax.add_patch(Arc((s * bx, 0), 2 * m["arc_r"], 2 * m["arc_r"],
                         theta1=90 if s > 0 else -90, theta2=270 if s > 0 else 90,
                         color="white", lw=1.5))
        ax.add_patch(Circle((s * bx, 0), 0.23, fill=False, ec="#d35400", lw=1.5))
    if heat is not None and len(heat):
        ax.hist2d(heat[:, 0], heat[:, 1], bins=[40, 22],
                  range=[[-hx, hx], [-hy, hy]], cmap="hot", alpha=0.65)
    if player_xy is not None and len(player_xy):
        ax.scatter(player_xy[:, 0], player_xy[:, 1], s=60, c="#1565c0", edgecolors="white",
                   linewidths=1, zorder=5)
    if ball_xy is not None and len(ball_xy):
        ax.scatter(ball_xy[:, 0], ball_xy[:, 1], s=30, c="#ff9800", edgecolors="black",
                   linewidths=0.6, zorder=6)
    ax.set_xlim(-hx - 1, hx + 1); ax.set_ylim(hy + 1, -hy - 1); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([]); ax.set_title(title, fontsize=11)
    fig.tight_layout()
    if out_path:
        fig.savefig(out_path, facecolor="#caa472", bbox_inches="tight")
    plt.close(fig)

# ============================ auto-detect (best-effort; expected to defer to manual) ============================
def auto_detect(frame):
    """Return candidate court-line segments + blue center-logo blob. Honest: finds candidates but
    cannot reliably label them on broadcast footage -> recommends manual marking."""
    H, W = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    bh = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)))
    _, th = cv2.threshold(bh, 28, 255, cv2.THRESH_BINARY)
    th[:int(H * 0.20)] = 0; th[int(H * 0.90):] = 0
    lines = cv2.HoughLinesP(th, 1, np.pi / 180, 70, minLineLength=70, maxLineGap=25)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    blue = cv2.inRange(hsv, (95, 80, 40), (130, 255, 255))
    blue[:int(H * 0.20)] = 0
    cnts, _ = cv2.findContours(blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blobs = sorted([cv2.boundingRect(c) + (cv2.contourArea(c),) for c in cnts if cv2.contourArea(c) > 1500],
                   key=lambda b: -b[-1])[:5]
    return {"n_line_candidates": 0 if lines is None else len(lines),
            "n_blue_blobs": len(blobs), "blobs": blobs,
            "verdict": "candidates found; cannot reliably auto-LABEL on broadcast (logos/text/"
                       "crowd/occlusion) -> use --mark manual fallback (the deployment path)"}

# ============================ marking tool ============================
def mark_interactive(frame, lm, out_pts):
    """Click a court point, then type its landmark name in the console prompt. q to finish."""
    clicks = []
    disp = frame.copy()
    win = "mark court points (click; then name in console; ESC=done)"
    def on(ev, x, y, *_):
        if ev == cv2.EVENT_LBUTTONDOWN:
            clicks.append((x, y))
            cv2.circle(disp, (x, y), 5, (0, 0, 255), -1); cv2.imshow(win, disp)
    cv2.namedWindow(win, cv2.WINDOW_NORMAL); cv2.imshow(win, disp); cv2.setMouseCallback(win, on)
    print("Landmark names:\n  " + "\n  ".join(lm.keys()))
    named = []
    while True:
        if cv2.waitKey(20) == 27:
            break
        if len(clicks) > len(named):
            nm = input(f"name for click {clicks[-1]}: ").strip()
            if nm in lm:
                named.append({"name": nm, "img": list(clicks[-1]), "court": list(lm[nm])})
            else:
                print("  unknown landmark, ignored"); clicks.pop()
    cv2.destroyAllWindows()
    Path(out_pts).write_text(json.dumps(named, indent=2))
    print(f"saved {len(named)} points -> {out_pts}")
    return named

# ============================ main ============================
def load_players_frame(track_path, frame):
    feet, boxes = [], []
    for line in Path(track_path).read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(",")
        if int(p[0]) != frame:
            continue
        x, y, w, h = float(p[2]), float(p[3]), float(p[4]), float(p[5])
        feet.append((x + w / 2, y + h)); boxes.append((x, y, w, h))
    return feet, boxes

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq")
    ap.add_argument("--frame", type=int, default=540)
    ap.add_argument("--frames-root", default="datasets/sportsmot_basketball")
    ap.add_argument("--track", default="outputs/track_results/bball_ftdet_bytetrack")
    ap.add_argument("--out", default="outputs/deliverables")
    ap.add_argument("--model", default="ncaa", choices=["ncaa", "fiba"])
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--register", action="store_true",
                    help="automatic camera-pose chamfer registration (no manual marks needed)")
    ap.add_argument("--mark", action="store_true")
    ap.add_argument("--refine", action="store_true",
                    help="auto-refine the rough init by snapping court lines to detected edges")
    ap.add_argument("--points", default=None, help="JSON list of {name,img:[x,y]} (reproducible)")
    args = ap.parse_args()

    m = court_model(args.model)
    lm = landmarks(m)
    out_dir = Path(args.out) / args.seq / "court"
    out_dir.mkdir(parents=True, exist_ok=True)
    frame_path = Path(args.frames_root) / args.seq / "img1" / f"{args.frame:06d}.jpg"
    frame = cv2.imread(str(frame_path))
    if frame is None:
        sys.exit(f"frame not found: {frame_path}")
    print(f"=== basketball court homography: {args.seq} f{args.frame} ({args.model}) ===")

    if args.auto:
        print("AUTO-detect:", json.dumps(auto_detect(frame)["verdict"]))

    feet, boxes = load_players_frame(Path(args.track) / f"{args.seq}.txt", args.frame)
    pts_file = out_dir / "points.json"
    named = []
    refine_info = {"refined": False}
    reg_info = {}
    mean_err, errs, direct, direct_mean = None, [], [], None
    img_pts = court_pts = names = []

    if args.register:
        print("  WARNING: --register (auto camera-pose chamfer) proved UNRELIABLE -- its overlay can "
              "be VISUALLY VERY WRONG while still passing the in-bounds metric. Use the MANUAL app "
              "(scripts/mark_court.py) for any real calibration. --register kept for the record only.")
        H_ic, H_ci, reg_info = register_pose(frame, m, player_boxes=boxes, player_feet=feet)
        print(f"  AUTO-REGISTER (camera-pose chamfer): {reg_info}")
        if args.refine:
            H_ic, H_ci, refine_info = refine_homography(frame, H_ic, [], [], m, player_boxes=boxes)
            print(f"  REFINE polish: {refine_info}")
    else:
        if args.mark:
            named = mark_interactive(frame, lm, pts_file)
        elif args.points:
            named = json.loads(Path(args.points).read_text())
        elif pts_file.exists():
            named = json.loads(pts_file.read_text())
        else:
            sys.exit("no points: run with --register, --mark, or --points <file>")
        img_pts = [tuple(p["img"]) for p in named]
        court_pts = [tuple(lm[p["name"]]) for p in named]
        names = [p["name"] for p in named]
        H_ic, H_ci = solve_H(img_pts, court_pts)
        if args.refine:
            H_ic, H_ci, refine_info = refine_homography(frame, H_ic, court_pts, img_pts, m,
                                                        player_boxes=boxes)
            print(f"  REFINE (line-snapping): {refine_info}")
        mean_err, errs = holdout_reconstruction(img_pts, court_pts, names)
        proj = apply_H(H_ci, img_pts)
        direct = [(names[i], round(float(np.hypot(proj[i][0] - court_pts[i][0],
                                                  proj[i][1] - court_pts[i][1])), 3))
                  for i in range(len(names))]
        direct_mean = float(np.mean([e for _, e in direct]))
        print(f"  marked points: {len(named)}")
        print(f"  reconstruction err on landmarks (current H): mean {direct_mean:.3f} m")
        for nm, e in direct:
            print(f"    {nm:<20} {e} m")
        if mean_err:
            print(f"  leave-one-out reconstruction (init marks only): mean {mean_err:.3f} m")

    draw_overlay(frame, H_ic, m, marked=list(zip(img_pts, names)), out_path=out_dir / "overlay.png")
    player_court = apply_H(H_ci, feet) if feet else np.empty((0, 2))
    inb = np.mean((np.abs(player_court[:, 0]) <= m["hx"] + 1.5) &
                  (np.abs(player_court[:, 1]) <= m["hy"] + 1.5)) if len(player_court) else None
    draw_court_diagram(m, player_xy=player_court, out_path=out_dir / "court_diagram.png",
                       title=f"{args.seq} f{args.frame}: players projected to court-m "
                             f"(in-bounds {100*inb:.0f}%)" if inb is not None else "")
    print(f"  players this frame: {len(feet)}  in-bounds: {100*inb:.0f}%" if inb is not None else "  no players")

    (out_dir / "homography.json").write_text(json.dumps({
        "seq": args.seq, "frame": args.frame, "model": args.model,
        "H_img_from_court": H_ic.tolist(), "H_court_from_img": H_ci.tolist(),
        "points": named, "holdout_mean_err_m": mean_err, "holdout_errs": errs,
        "refine": refine_info, "register": reg_info,
        "landmark_recon_err_m": direct, "landmark_recon_mean_m": direct_mean,
    }, indent=2))
    (out_dir / "validation.json").write_text(json.dumps({
        "method": "auto-register (pose-chamfer)" if args.register else "manual marks",
        "register": reg_info, "landmark_recon_mean_m": direct_mean, "holdout_mean_err_m": mean_err,
        "refined": refine_info.get("refined"), "in_bounds_frac": inb,
        "trust_level": "PLAUSIBILITY-validated (no court-meter GT; cf. football 0.2m GT). "
                       "Same honesty level as the Day-19 basketball ball track.",
    }, indent=2))
    print(f"  -> {out_dir}")

if __name__ == "__main__":
    main()
