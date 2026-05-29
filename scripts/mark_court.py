"""Day 21 (revised): MANUAL court-marking GUI app -- the REQUIRED basketball calibration path.

Why manual is now the required path: the Day-21 automatic camera-pose chamfer registration produced
a homography whose projected-court overlay was VISUALLY VERY WRONG even though its players-in-bounds
metric passed (an in-bounds score is satisfiable by a misaligned pose, so it misled the auto fit).
On broadcast footage with court logos/text/crowd/player occlusion there is no reliable automatic
signal. So calibration is done by a HUMAN clicking known court points -- which is also the realistic
deployment workflow: the school's fixed camera is marked ONCE and the homography holds the match.

This app shows one frame + a labelled reference court, walks you through clicking each visible court
landmark, and draws the projected court back onto the frame LIVE so you can SEE the alignment and
re-mark until it sits on the real lines. Saves a homography.json compatible with
coach_deliverable_basketball.py (re-run that after marking to get court-metre analytics).

Controls (focus the "mark court" window):
  left-click : place the CURRENT target landmark's pixel point, then advance to the next
  k          : skip the current landmark (not visible / not on this court)
  u          : undo the last placed point
  r          : reset all points
  s          : save homography.json + points.json (needs >= 4 points)
  q / ESC    : quit

You only need >= 4 well-spread points; corners are the most robust (present on nearly any court,
even faded/multi-sport/outdoor). More points + good spread = a better fit. Watch the yellow overlay:
when the projected lines sit on the painted lines, you're done.

Usage:
  python scripts/mark_court.py v_00HRwkvvjtQ_c007 --frame 540
  python scripts/mark_court.py <seq> --frame <N> --model fiba      # FIBA 28x15 court
  python scripts/mark_court.py <seq> --frame <N> --frames-root datasets/<your_footage>
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent))
import basketball_court as bc

# Marking order: most-robust first (corners), then lane/FT, then arcs/centre. Skip any not visible.
MARK_ORDER = [
    "r_baseline_far", "r_baseline_near", "r_lane_base_far", "r_lane_base_near",
    "r_lane_ft_far", "r_lane_ft_near", "r_ft_center", "r_arc_top", "r_basket",
    "center", "center_far", "center_near",
    "l_baseline_far", "l_baseline_near", "l_ft_center", "l_basket",
]

HELP = {
    "r_baseline_far":   "RIGHT baseline x FAR sideline corner (court corner near the basket, top side)",
    "r_baseline_near":  "RIGHT baseline x NEAR sideline corner (court corner near the basket, bottom)",
    "r_lane_base_far":  "RIGHT lane (key) corner on the BASELINE, FAR side",
    "r_lane_base_near": "RIGHT lane (key) corner on the BASELINE, NEAR side",
    "r_lane_ft_far":    "RIGHT lane corner at the FREE-THROW line, FAR side",
    "r_lane_ft_near":   "RIGHT lane corner at the FREE-THROW line, NEAR side",
    "r_ft_center":      "RIGHT free-throw line MIDPOINT (centre of the FT circle)",
    "r_arc_top":        "RIGHT 3-point arc TOP (straight out from the basket)",
    "r_basket":         "RIGHT basket / rim centre (on the floor under the hoop)",
    "center":           "CENTRE of the court (middle of the centre circle)",
    "center_far":       "CENTRE line x FAR sideline (top)",
    "center_near":      "CENTRE line x NEAR sideline (bottom)",
    "l_baseline_far":   "LEFT baseline x FAR sideline corner",
    "l_baseline_near":  "LEFT baseline x NEAR sideline corner",
    "l_ft_center":      "LEFT free-throw line midpoint",
    "l_basket":         "LEFT basket / rim centre",
}


def reference_diagram(m, lm, highlight, out_path):
    """Top-down court with every landmark plotted + named; current target ringed."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Circle, Arc
    hx, hy, lhw, ftx, bx = m["hx"], m["hy"], m["lhw"], m["ftx"], m["bx"]
    fig, ax = plt.subplots(figsize=(7.6, 4.4), dpi=120)
    ax.set_facecolor("#caa472")
    ax.add_patch(Rectangle((-hx, -hy), 2 * hx, 2 * hy, fill=False, ec="white", lw=2))
    ax.plot([0, 0], [-hy, hy], color="white", lw=1.4)
    ax.add_patch(Circle((0, 0), m["ft_r"], fill=False, ec="white", lw=1.4))
    for s in (1, -1):
        ax.add_patch(Rectangle((s * hx - s * m["lane_len"], -lhw), s * m["lane_len"], 2 * lhw,
                               fill=False, ec="white", lw=1.4))
        ax.add_patch(Circle((s * ftx, 0), m["ft_r"], fill=False, ec="white", lw=1.4))
        ax.add_patch(Arc((s * bx, 0), 2 * m["arc_r"], 2 * m["arc_r"],
                         theta1=90 if s > 0 else -90, theta2=270 if s > 0 else 90, color="white", lw=1.4))
    for nm, (x, y) in lm.items():
        cur = nm == highlight
        ax.scatter([x], [y], s=120 if cur else 30, c="#ffeb3b" if cur else "#1565c0",
                   edgecolors="red" if cur else "white", linewidths=2 if cur else 0.6, zorder=5)
        if cur:
            ax.annotate(nm, (x, y), color="red", fontsize=9, fontweight="bold",
                        xytext=(4, 4), textcoords="offset points")
    ax.set_xlim(-hx - 1, hx + 1); ax.set_ylim(hy + 1, -hy - 1); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"TARGET: {highlight}", fontsize=11, color="red")
    fig.tight_layout(); fig.savefig(out_path, facecolor="#caa472", bbox_inches="tight"); plt.close(fig)
    return cv2.imread(str(out_path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq")
    ap.add_argument("--frame", type=int, default=540)
    ap.add_argument("--frames-root", default="datasets/sportsmot_basketball")
    ap.add_argument("--model", default="ncaa", choices=["ncaa", "fiba"])
    ap.add_argument("--out", default="outputs/deliverables")
    args = ap.parse_args()

    m = bc.court_model(args.model); lm = bc.landmarks(m)
    frame_path = Path(args.frames_root) / args.seq / "img1" / f"{args.frame:06d}.jpg"
    frame = cv2.imread(str(frame_path))
    if frame is None:
        sys.exit(f"frame not found: {frame_path}")
    out_dir = Path(args.out) / args.seq / "court"; out_dir.mkdir(parents=True, exist_ok=True)

    order = [n for n in MARK_ORDER if n in lm]
    placed = []          # list of {"name","img":[x,y]}
    idx = 0              # pointer into `order` (skips advance it too)
    WIN = "mark court (click target; k=skip u=undo r=reset s=save q=quit)"
    REF = "reference court (target ringed in red)"

    def cur_target():
        while idx < len(order) and any(p["name"] == order[idx] for p in placed):
            return None
        return order[idx] if idx < len(order) else None

    def current_H():
        if len(placed) < 4:
            return None
        img_pts = [tuple(p["img"]) for p in placed]
        court_pts = [tuple(lm[p["name"]]) for p in placed]
        H_ic, _ = bc.solve_H(img_pts, court_pts)
        return H_ic

    def redraw():
        vis = frame.copy()
        H_ic = current_H()
        if H_ic is not None:
            for poly in bc.court_polylines(m):
                pix = bc.apply_H(H_ic, poly).astype(np.int32)
                cv2.polylines(vis, [pix], False, (0, 255, 255), 2, cv2.LINE_AA)
        for p in placed:
            x, y = p["img"]
            cv2.circle(vis, (int(x), int(y)), 6, (0, 0, 255), -1)
            cv2.putText(vis, p["name"], (int(x) + 6, int(y) - 6), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, (0, 255, 0), 1, cv2.LINE_AA)
        tgt = order[idx] if idx < len(order) else None
        msg = f"CLICK: {tgt}" if tgt else "all landmarks done"
        cv2.rectangle(vis, (0, 0), (frame.shape[1], 56), (0, 0, 0), -1)
        cv2.putText(vis, msg, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
        if tgt:
            cv2.putText(vis, HELP.get(tgt, ""), (10, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (200, 200, 200), 1, cv2.LINE_AA)
        cv2.putText(vis, f"points: {len(placed)} (need >=4)  s=save", (frame.shape[1] - 300, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
        cv2.imshow(WIN, vis)
        if tgt:
            cv2.imshow(REF, reference_diagram(m, lm, tgt, out_dir / "_ref.png"))

    def on_mouse(ev, x, y, *_):
        nonlocal idx
        if ev == cv2.EVENT_LBUTTONDOWN and idx < len(order):
            placed.append({"name": order[idx], "img": [int(x), int(y)]})
            idx += 1
            redraw()

    cv2.namedWindow(WIN, cv2.WINDOW_AUTOSIZE)   # AUTOSIZE => clicks are native image pixels
    cv2.namedWindow(REF, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(WIN, on_mouse)
    print(__doc__)
    redraw()
    while True:
        key = cv2.waitKey(20) & 0xFF
        if key in (ord("q"), 27):
            break
        elif key == ord("k") and idx < len(order):
            idx += 1; redraw()
        elif key == ord("u") and placed:
            placed.pop(); idx = max(0, idx - 1); redraw()
        elif key == ord("r"):
            placed.clear(); idx = 0; redraw()
        elif key == ord("s"):
            if len(placed) < 4:
                print("need >= 4 points to solve a homography"); continue
            save(args, m, lm, placed, out_dir, frame)
            print("saved. keep refining (re-mark) or q to quit.")
    cv2.destroyAllWindows()


def prune_outliers(placed, lm, thresh_m=2.0, min_keep=4):
    """Iteratively drop clicks whose court-space reconstruction error exceeds thresh_m -- catches
    misclicks and points marked for landmarks that aren't actually visible in the frame. Returns
    (kept, dropped). Keeps at least min_keep best points."""
    keep = list(placed)
    dropped = []
    while len(keep) > min_keep:
        img = [tuple(p["img"]) for p in keep]; court = [tuple(lm[p["name"]]) for p in keep]
        H_ic, H_ci = bc.solve_H(img, court)
        proj = bc.apply_H(H_ci, img)
        errs = [float(np.hypot(proj[i][0] - court[i][0], proj[i][1] - court[i][1])) for i in range(len(keep))]
        worst = int(np.argmax(errs))
        if errs[worst] <= thresh_m:
            break
        dropped.append((keep[worst]["name"], round(errs[worst], 2)))
        keep.pop(worst)
    return keep, dropped


def save(args, m, lm, placed_all, out_dir, frame):
    placed, dropped = prune_outliers(placed_all, lm)
    if dropped:
        print(f"  pruned {len(dropped)} outlier click(s) (likely misclick / landmark not visible): "
              + ", ".join(f"{n} ({e}m)" for n, e in dropped))
    img_pts = [tuple(p["img"]) for p in placed]
    court_pts = [tuple(lm[p["name"]]) for p in placed]
    names = [p["name"] for p in placed]
    H_ic, H_ci = bc.solve_H(img_pts, court_pts)
    mean_err, errs = bc.holdout_reconstruction(img_pts, court_pts, names)
    proj = bc.apply_H(H_ci, img_pts)
    direct = [(names[i], round(float(np.hypot(proj[i][0] - court_pts[i][0],
                                              proj[i][1] - court_pts[i][1])), 3))
              for i in range(len(names))]
    direct_mean = float(np.mean([e for _, e in direct]))
    bc.draw_overlay(frame, H_ic, m, marked=list(zip(img_pts, names)), out_path=out_dir / "overlay.png")
    (out_dir / "points.json").write_text(json.dumps(placed, indent=2))
    (out_dir / "homography.json").write_text(json.dumps({
        "seq": args.seq, "frame": args.frame, "model": args.model,
        "H_img_from_court": H_ic.tolist(), "H_court_from_img": H_ci.tolist(),
        "points": [{"name": p["name"], "img": p["img"], "court": list(lm[p["name"]])} for p in placed],
        "method": "MANUAL marking (human-clicked)",
        "n_clicked": len(placed_all), "n_used": len(placed),
        "pruned_outliers": [{"name": n, "err_m": e} for n, e in dropped],
        "holdout_mean_err_m": mean_err, "holdout_errs": errs,
        "landmark_recon_err_m": direct, "landmark_recon_mean_m": direct_mean,
    }, indent=2))
    (out_dir / "validation.json").write_text(json.dumps({
        "method": "MANUAL marking (human-clicked)",
        "landmark_recon_mean_m": direct_mean, "holdout_mean_err_m": mean_err,
        "trust_level": "PLAUSIBILITY-validated (no court-metre GT; cf. football 0.2m GT). "
                       "Same honesty level as the Day-19 basketball ball track.",
    }, indent=2))
    print(f"  {len(placed)} pts | landmark recon mean {direct_mean:.2f} m"
          f"{f' | leave-one-out {mean_err:.2f} m' if mean_err else ''} -> {out_dir}/homography.json")
    print(f"  overlay -> {out_dir}/overlay.png  (check the yellow lines sit on the real court)")


if __name__ == "__main__":
    main()
