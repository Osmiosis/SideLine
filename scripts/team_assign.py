"""Day 11: per-track team assignment via torso-color clustering, validated vs GSR.

Pipeline:
  1) For each tracker detection (5 seqs, SNGS-116..120 from same game_id=7), crop the torso
     region (vert 20-55%, horiz central 50%), compute mean Lab color.
  2) Cluster all torso means with KMeans k>=4 (default 4).
  3) Identify the 2 largest clusters as Team A / Team B; remaining = non-outfield (GK + Ref).
  4) Per-tracklet majority vote -> single team label per (seq, tracker_id).
  5) Validate against GSR `attributes.team` (left/right) and `attributes.role`
     (player/goalkeeper/referee/other) by IoU-matching tracker boxes to GT.
  6) Hungarian-align cluster->team mapping; report outfield team accuracy + GK/ref detection.
  7) Render team-colored sample frame + team-split heatmap (for one seq).

Outputs:
  outputs/team_assign/torso_features.npz   (concatenated features across 5 seqs)
  outputs/team_assign/cluster_summary.json (cluster sizes, mean BGR per cluster, label map)
  outputs/team_assign/track_teams.json     {seq: {tid: {team, role, votes}}}
  outputs/team_assign/validation.json      (outfield accuracy, GK/ref P/R)
  outputs/team_assign/sample_torsos.png    (spot-check)
  outputs/team_assign/team_heatmap_A.png + team_heatmap_B.png  (one seq)
  outputs/team_assign/team_colored_frame.png

Usage:
  python scripts/team_assign.py [--k 4] [--sample-seq SNGS-118]
"""
import argparse, json, sys, zipfile
from collections import defaultdict, Counter
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent))
from analyze_pitch import (PITCH_X_HALF, PITCH_Y_HALF, load_gt, load_tracker,
                           derive_per_frame_H, project_tracker, render_heatmap)

SEQS = ["SNGS-116", "SNGS-117", "SNGS-118", "SNGS-119", "SNGS-120"]
TORSO_Y_FRAC = (0.20, 0.55)
TORSO_X_FRAC = (0.25, 0.75)
MIN_TORSO_AREA = 50  # px; below this, the patch is too small to be reliable

# -------- Torso feature extraction --------
def crop_torso(img: np.ndarray, x: float, y: float, w: float, h: float):
    H, W = img.shape[:2]
    x1 = int(round(x + TORSO_X_FRAC[0] * w))
    x2 = int(round(x + TORSO_X_FRAC[1] * w))
    y1 = int(round(y + TORSO_Y_FRAC[0] * h))
    y2 = int(round(y + TORSO_Y_FRAC[1] * h))
    x1 = max(0, x1); y1 = max(0, y1)
    x2 = min(W, x2); y2 = min(H, y2)
    if x2 <= x1 or y2 <= y1:
        return None
    return img[y1:y2, x1:x2]

def mean_lab(patch: np.ndarray):
    """Return (L, a, b) trimmed-mean over the patch. Trims top/bot 10% per channel."""
    if patch.size == 0:
        return None
    lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB).astype(np.float32)
    pix = lab.reshape(-1, 3)
    # Trim 10% extremes per channel
    lo = np.percentile(pix, 10, axis=0)
    hi = np.percentile(pix, 90, axis=0)
    mask = np.all((pix >= lo) & (pix <= hi), axis=1)
    inliers = pix[mask] if mask.any() else pix
    return inliers.mean(axis=0)  # (L, a, b)

def mean_bgr(patch: np.ndarray):
    if patch.size == 0: return None
    pix = patch.reshape(-1, 3).astype(np.float32)
    lo = np.percentile(pix, 10, axis=0)
    hi = np.percentile(pix, 90, axis=0)
    mask = np.all((pix >= lo) & (pix <= hi), axis=1)
    inliers = pix[mask] if mask.any() else pix
    return inliers.mean(axis=0)

def extract_features_seq(tracker_path: Path, frames_dir: Path):
    """Return per-detection records: list of (seq_idx, frame, tid, lab[3], bgr[3], bbox[4])."""
    track = load_tracker(tracker_path)  # (frame, tid, feet_x, feet_y) -- but we need bbox
    # Reload tracker output with bbox xywh
    rows = []
    for line in tracker_path.read_text().splitlines():
        if not line.strip(): continue
        p = line.split(",")
        f = int(p[0]); tid = int(p[1])
        x = float(p[2]); y = float(p[3]); w = float(p[4]); h = float(p[5])
        rows.append((f, tid, x, y, w, h))
    # Group by frame so we read each frame once
    by_frame = defaultdict(list)
    for r in rows:
        by_frame[r[0]].append(r)
    records = []
    skipped = 0
    for f in sorted(by_frame):
        img_path = frames_dir / f"{f:06d}.jpg"
        img = cv2.imread(str(img_path))
        if img is None: continue
        for (_, tid, x, y, w, h) in by_frame[f]:
            patch = crop_torso(img, x, y, w, h)
            if patch is None or patch.shape[0] * patch.shape[1] < MIN_TORSO_AREA:
                skipped += 1; continue
            lab = mean_lab(patch); bgr = mean_bgr(patch)
            if lab is None: skipped += 1; continue
            records.append((f, tid, lab[0], lab[1], lab[2], bgr[0], bgr[1], bgr[2], x, y, w, h))
    return records, skipped

# -------- Clustering + per-tracklet vote --------
def kmeans_lab(features: np.ndarray, k: int, seed: int = 42):
    """KMeans via cv2.kmeans on Lab features."""
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 1e-4)
    _, labels, centers = cv2.kmeans(features.astype(np.float32), k, None, crit, 10, cv2.KMEANS_PP_CENTERS)
    return labels.ravel(), centers

def per_tracklet_vote(records: list, det_clusters: np.ndarray, det_features: np.ndarray, centers: np.ndarray):
    """For each tracker_id:
       - majority team cluster (0 or 1) via vote across its frames
       - median distance to nearest team center (the GK/ref-outlier signal)
       - vote purity (max votes / total)
       Returns {tid: {...}}
    """
    by_tid_clusters = defaultdict(list)
    by_tid_dists = defaultdict(list)
    for r, c, f in zip(records, det_clusters, det_features):
        tid = r[1]
        by_tid_clusters[tid].append(int(c))
        # dist to nearest team center
        d = float(np.linalg.norm(f - centers, axis=1).min())
        by_tid_dists[tid].append(d)
    out = {}
    for tid, votes in by_tid_clusters.items():
        cnt = Counter(votes)
        majority = cnt.most_common(1)[0][0]
        ndets = len(votes)
        out[tid] = {
            "majority_cluster": majority,
            "n_dets": ndets,
            "votes": dict(cnt),
            "vote_purity": max(cnt.values()) / ndets,
            "median_dist_to_team": float(np.median(by_tid_dists[tid])),
            "mean_dist_to_team": float(np.mean(by_tid_dists[tid])),
        }
    return out

def flag_non_outfield(track_teams_by_seq: dict, abs_threshold: float = None,
                      percentile: float = None):
    """Flag tracks with HIGH mean-distance-to-team as non-outfield (Referee, in practice).
    Use ABSOLUTE distance threshold (preferred -- calibrated against GT chroma distances),
    OR percentile cutoff (fallback). GKs share team colors so they get assigned to their team,
    not flagged -- which is the correct behavior given color-alone cannot distinguish GK from
    their team's outfielders.

    Returns the threshold used (in a/b space).
    """
    if abs_threshold is None and percentile is None:
        raise ValueError("Provide abs_threshold or percentile")
    if abs_threshold is None:
        all_dists = []
        for tracks in track_teams_by_seq.values():
            for v in tracks.values():
                all_dists.extend([v["mean_dist_to_team"]] * v["n_dets"])
        abs_threshold = float(np.percentile(all_dists, 100 - percentile))
    for tracks in track_teams_by_seq.values():
        for v in tracks.values():
            if v["mean_dist_to_team"] >= abs_threshold:
                v["role"] = "NonOutfield"
            elif v["majority_cluster"] == 0:
                v["role"] = "TeamA"
            else:
                v["role"] = "TeamB"
    return abs_threshold

# -------- GSR validation --------
def iou(a, b):
    """xywh boxes."""
    ax1, ay1, aw, ah = a; ax2, ay2 = ax1+aw, ay1+ah
    bx1, by1, bw, bh = b; bx2, by2 = bx1+bw, by1+bh
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw = max(0, ix2-ix1); ih = max(0, iy2-iy1)
    inter = iw * ih
    if inter <= 0: return 0.0
    return inter / (aw*ah + bw*bh - inter)

def gt_by_frame(zip_path: Path, seq: str):
    """{frame: list of (gt_tid, bbox_xywh, team, role)}."""
    z = zipfile.ZipFile(zip_path)
    with z.open(f"{seq}/Labels-GameState.json") as f:
        data = json.load(f)
    img_to_frame = {img["image_id"]: int(Path(img["file_name"]).stem) for img in data["images"]}
    by_f = defaultdict(list)
    for a in data["annotations"]:
        if a.get("category_id") not in (1, 2, 3):
            continue  # players, goalkeepers, referees
        bi = a.get("bbox_image")
        if not bi: continue
        f = img_to_frame.get(a["image_id"])
        if f is None: continue
        attrs = a.get("attributes", {})
        by_f[f].append((a["track_id"],
                        (bi["x"], bi["y"], bi["w"], bi["h"]),
                        attrs.get("team"), attrs.get("role")))
    return by_f

def validate(records_by_seq: dict, zip_path: Path, track_teams_by_seq: dict,
             iou_thresh: float = 0.4):
    """Per-detection: IoU-match to GT; compute outfield team accuracy + GK/ref P/R.
    track_teams_by_seq[seq][tid] has 'role' in {'TeamA','TeamB','NonOutfield'}.
    """
    pairs = []  # (pred_role, gsr_team(left/right/None), gsr_role)
    n_no_match = 0
    for seq, records in records_by_seq.items():
        gtf = gt_by_frame(zip_path, seq)
        track_pred = track_teams_by_seq[seq]
        for (f, tid, *_lab_bgr, x, y, w, h) in records:
            tv = track_pred.get(tid)
            if tv is None or "role" not in tv: continue
            pred_role = tv["role"]
            candidates = gtf.get(f, [])
            best, best_iou = None, 0.0
            for c in candidates:
                i = iou((x, y, w, h), c[1])
                if i > best_iou:
                    best, best_iou = c, i
            if best is None or best_iou < iou_thresh:
                n_no_match += 1; continue
            pairs.append((pred_role, best[2], best[3]))

    # Outfield team accuracy: include players AND goalkeepers (both have a team label;
    # color-only cannot distinguish GK from teammates, but they DO belong to a team).
    outfield_pairs = [(p, t) for (p, t, r) in pairs if r in ("player", "goalkeeper") and t in ("left", "right")]

    def acc(mapping):
        ok = sum(1 for p, t in outfield_pairs if mapping.get(p) == t)
        return ok / len(outfield_pairs) if outfield_pairs else 0.0

    align_LR = {"TeamA": "left", "TeamB": "right"}
    align_RL = {"TeamA": "right", "TeamB": "left"}
    acc_LR = acc(align_LR); acc_RL = acc(align_RL)
    if acc_LR >= acc_RL:
        best_align, best_acc = align_LR, acc_LR
    else:
        best_align, best_acc = align_RL, acc_RL

    # Referee detection P/R vs GT role=='referee' (NOT GK -- GK shares team colors, see notes).
    pred_no = [p == "NonOutfield" for (p, _, _) in pairs]
    gt_ref = [r == "referee" for (_, _, r) in pairs]
    tp = sum(1 for p, g in zip(pred_no, gt_ref) if p and g)
    fp = sum(1 for p, g in zip(pred_no, gt_ref) if p and not g)
    fn = sum(1 for p, g in zip(pred_no, gt_ref) if not p and g)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2*prec*rec / (prec+rec) if (prec+rec) else 0.0

    # Breakdown: among NonOutfield predictions, what's the GT role distribution?
    breakdown = Counter()
    for (p, _, r) in pairs:
        if p == "NonOutfield":
            breakdown[r] += 1

    # GK-specific accuracy: when GT role=='goalkeeper', did we still get the team right?
    gk_pairs = [(p, t) for (p, t, r) in pairs if r == "goalkeeper" and t in ("left", "right")]
    gk_acc_LR = sum(1 for p, t in gk_pairs if align_LR.get(p) == t) / max(1, len(gk_pairs))
    gk_acc_RL = sum(1 for p, t in gk_pairs if align_RL.get(p) == t) / max(1, len(gk_pairs))
    gk_n_flagged_nonoutfield = sum(1 for p, t in gk_pairs if p == "NonOutfield")

    # Player-only accuracy
    pl_pairs = [(p, t) for (p, t, r) in pairs if r == "player" and t in ("left", "right")]
    pl_acc_LR = sum(1 for p, t in pl_pairs if align_LR.get(p) == t) / max(1, len(pl_pairs))
    pl_acc_RL = sum(1 for p, t in pl_pairs if align_RL.get(p) == t) / max(1, len(pl_pairs))

    return {
        "n_pairs": len(pairs),
        "n_no_match_iou_lt_thresh": n_no_match,
        "outfield_team_accuracy_all_GT_outfield": best_acc,  # players + GKs
        "player_only_team_accuracy": max(pl_acc_LR, pl_acc_RL),
        "goalkeeper_only_team_accuracy": max(gk_acc_LR, gk_acc_RL),
        "n_goalkeepers_flagged_NonOutfield": gk_n_flagged_nonoutfield,
        "n_goalkeepers_total": len(gk_pairs),
        "alignment": {"mapping": best_align, "acc_LR": acc_LR, "acc_RL": acc_RL},
        "referee_detection": {
            "precision": prec, "recall": rec, "f1": f1, "tp": tp, "fp": fp, "fn": fn,
            "pred_NonOutfield_role_breakdown": dict(breakdown),
        },
    }

# -------- Sample renders --------
def render_sample_torsos(records_by_seq: dict, det_clusters_by_seq: dict, frames_dirs: dict,
                         centers_bgr: np.ndarray, cluster_role: list, out_path: Path,
                         n_per_cluster: int = 6):
    """Render N torso patches per cluster as a grid; row = cluster, columns = samples."""
    import random
    rng = random.Random(42)
    k = len(cluster_role)
    # Index all records globally
    flat_records = []
    flat_clusters = []
    flat_seqs = []
    for seq, recs in records_by_seq.items():
        flat_records.extend(recs)
        flat_clusters.extend(det_clusters_by_seq[seq].tolist())
        flat_seqs.extend([seq] * len(recs))
    # Group by cluster
    by_cluster = defaultdict(list)
    for i, c in enumerate(flat_clusters):
        by_cluster[c].append(i)
    # Pick samples
    cell_h, cell_w = 80, 60
    canvas = np.full((k * (cell_h + 4), (n_per_cluster + 1) * (cell_w + 4), 3), 255, dtype=np.uint8)
    for row, cluster_id in enumerate(range(k)):
        # Left-most cell: a swatch of the cluster's mean color
        bgr = centers_bgr[cluster_id]
        swatch = np.full((cell_h, cell_w, 3), bgr, dtype=np.uint8)
        cv2.putText(swatch, f"#{cluster_id} {cluster_role[cluster_id]}", (3, 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        y0 = row * (cell_h + 4); x0 = 0
        canvas[y0:y0+cell_h, x0:x0+cell_w] = swatch
        # Sample patches
        idxs = by_cluster.get(cluster_id, [])
        if idxs:
            picked = rng.sample(idxs, min(n_per_cluster, len(idxs)))
        else:
            picked = []
        for col, gi in enumerate(picked):
            rec = flat_records[gi]; seq = flat_seqs[gi]
            f = rec[0]; x, y, w, h = rec[8], rec[9], rec[10], rec[11]
            img = cv2.imread(str(frames_dirs[seq] / f"{f:06d}.jpg"))
            if img is None: continue
            patch = crop_torso(img, x, y, w, h)
            if patch is None: continue
            patch = cv2.resize(patch, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
            x1 = (col + 1) * (cell_w + 4)
            canvas[y0:y0+cell_h, x1:x1+cell_w] = patch
    cv2.imwrite(str(out_path), canvas)

def render_team_colored_frame(sample_seq: str, frames_dir: Path, records_seq: list,
                              track_teams: dict, out_path: Path, frame_idx: int = 100):
    """Pick a frame; draw each detection's bbox colored by its tracker's track-role."""
    color_by_role = {
        "TeamA":       (60, 220, 60),    # green
        "TeamB":       (60, 60, 230),    # red
        "NonOutfield": (0, 200, 255),    # yellow
    }
    img = cv2.imread(str(frames_dir / f"{frame_idx:06d}.jpg"))
    if img is None: return
    for rec in records_seq:
        f, tid = rec[0], rec[1]
        if f != frame_idx: continue
        x, y, w, h = rec[8], rec[9], rec[10], rec[11]
        tv = track_teams.get(tid)
        if tv is None or "role" not in tv: continue
        role = tv["role"]
        c = color_by_role.get(role, (200, 200, 200))
        cv2.rectangle(img, (int(x), int(y)), (int(x+w), int(y+h)), c, 2)
        cv2.putText(img, f"{tid}:{role[:1]}", (int(x), int(y) - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 2)
    cv2.imwrite(str(out_path), img)

def render_team_heatmaps(sample_seq: str, zip_path: Path, records_seq: list,
                         track_teams: dict, out_dir: Path):
    """Two heatmaps (Team A, Team B) + one for NonOutfield, in pitch meters."""
    gt_pts = load_gt(zip_path, sample_seq)
    H_by_frame, _ = derive_per_frame_H(gt_pts)
    positions_by_role = {"TeamA": [], "TeamB": [], "NonOutfield": []}
    for rec in records_seq:
        f, tid = rec[0], rec[1]
        x, y, w, h = rec[8], rec[9], rec[10], rec[11]
        tv = track_teams.get(tid)
        if tv is None or "role" not in tv: continue
        role = tv["role"]
        if role not in positions_by_role: continue
        H = H_by_frame.get(f)
        if H is None: continue
        feet_x = x + w/2; feet_y = y + h
        pt = cv2.perspectiveTransform(np.array([[[feet_x, feet_y]]], dtype=np.float32), H).ravel()
        positions_by_role[role].append((float(pt[0]), float(pt[1])))
    for role in ("TeamA", "TeamB", "NonOutfield"):
        xy = np.array(positions_by_role[role], dtype=np.float32) if positions_by_role[role] else np.zeros((0, 2))
        render_heatmap(xy, out_dir / f"team_heatmap_{role}.png",
                       f"{sample_seq} - {role} density (n={len(xy)} pts)")

# -------- Main --------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=2,
                    help="2-stage: k=2 for teams, GK/ref via distance outlier")
    ap.add_argument("--feature-mode", choices=["lab", "ab"], default="ab",
                    help="lab = full Lab (lighting-sensitive); ab = a+b chroma only (default)")
    ap.add_argument("--non-outfield-percentile", type=float, default=None,
                    help="Tracks whose mean-distance-to-team is in the top N%% are flagged NonOutfield")
    ap.add_argument("--non-outfield-abs-threshold", type=float, default=20.0,
                    help="Absolute a/b distance threshold for NonOutfield (Referee). "
                         "Calibrated: GT player+GK p75 ~12, GT ref p25 ~36 -> 20 cleanly splits.")
    ap.add_argument("--tracker-dir", default="outputs/track_results/sn_soccana_botsort_gmc")
    ap.add_argument("--zip", default="datasets/soccernet_gsr/test.zip")
    ap.add_argument("--data-root", default="datasets/soccernet_tracking")
    ap.add_argument("--out", default="outputs/team_assign")
    ap.add_argument("--sample-seq", default="SNGS-118")
    ap.add_argument("--sample-frame", type=int, default=100)
    args = ap.parse_args()

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    tracker_dir = Path(args.tracker_dir)
    zip_path = Path(args.zip)
    data_root = Path(args.data_root)

    # Part A: extract torso features per seq
    print(f"=== Part A: torso feature extraction ===")
    records_by_seq = {}
    skipped_by_seq = {}
    for seq in SEQS:
        frames_dir = data_root / seq / "img1"
        recs, skipped = extract_features_seq(tracker_dir / f"{seq}.txt", frames_dir)
        records_by_seq[seq] = recs
        skipped_by_seq[seq] = skipped
        print(f"  {seq}: {len(recs)} torso features ({skipped} skipped tiny/missing)")

    # Pool features
    all_records = [r for seq in SEQS for r in records_by_seq[seq]]
    features_lab = np.array([(r[2], r[3], r[4]) for r in all_records], dtype=np.float32)
    features_bgr = np.array([(r[5], r[6], r[7]) for r in all_records], dtype=np.float32)

    # Choose clustering feature: lab (lighting-sensitive) vs ab (chroma only)
    if args.feature_mode == "ab":
        features_cluster = features_lab[:, 1:3]  # a, b only
    else:
        features_cluster = features_lab
    print(f"  total torso features: {len(features_lab)}  clustering on {args.feature_mode} ({features_cluster.shape[1]}-D)")

    # Part B: cluster
    print(f"\n=== Part B: KMeans k={args.k} (feature_mode={args.feature_mode}) ===")
    labels, centers_cluster = kmeans_lab(features_cluster, k=args.k)
    # For reporting + visualization, recover full Lab + BGR centers from cluster assignments
    centers_lab = np.zeros((args.k, 3), dtype=np.float32)
    centers_bgr = np.zeros((args.k, 3), dtype=np.float32)
    sizes = np.zeros(args.k, dtype=int)
    for c in range(args.k):
        mask = labels == c
        sizes[c] = int(mask.sum())
        if sizes[c] > 0:
            centers_bgr[c] = features_bgr[mask].mean(axis=0)
            centers_lab[c] = features_lab[mask].mean(axis=0)
    # Cluster #0 -> TeamA, Cluster #1 -> TeamB (placeholder; aligned to GSR left/right in validate)
    cluster_role = ["TeamA", "TeamB"] + ["Extra"] * (args.k - 2)
    for c in range(args.k):
        bgr = centers_bgr[c].astype(int).tolist()
        print(f"  cluster #{c} [{cluster_role[c]}]: size={sizes[c]}  mean Lab={centers_lab[c].round(1).tolist()}  mean BGR={bgr}")

    # Split labels back per seq
    det_clusters_by_seq = {}
    features_cluster_by_seq = {}
    offset = 0
    for seq in SEQS:
        n = len(records_by_seq[seq])
        det_clusters_by_seq[seq] = labels[offset:offset+n]
        features_cluster_by_seq[seq] = features_cluster[offset:offset+n]
        offset += n

    # Per-tracklet vote + distance-to-team
    track_teams_by_seq = {}
    for seq in SEQS:
        track_teams_by_seq[seq] = per_tracklet_vote(
            records_by_seq[seq], det_clusters_by_seq[seq],
            features_cluster_by_seq[seq], centers_cluster)

    # Two-stage: flag tracks with high distance as NonOutfield (Referees, in practice)
    thresh = flag_non_outfield(track_teams_by_seq,
                               abs_threshold=args.non_outfield_abs_threshold,
                               percentile=args.non_outfield_percentile)
    mode = "abs" if args.non_outfield_percentile is None else f"p={args.non_outfield_percentile}%"
    print(f"\n  Non-outfield (referee) distance threshold (a/b space): {thresh:.2f}  ({mode})")
    for seq in SEQS:
        roles = Counter(v["role"] for v in track_teams_by_seq[seq].values())
        n_tracks = len(track_teams_by_seq[seq])
        print(f"  {seq}: {n_tracks} tracks -> TeamA={roles['TeamA']}, TeamB={roles['TeamB']}, NonOutfield={roles['NonOutfield']}")

    # Save artifacts
    np.savez(out / "torso_features.npz", lab=features_lab, bgr=features_bgr, labels=labels)
    (out / "cluster_summary.json").write_text(json.dumps({
        "k": args.k, "sizes": sizes.tolist(),
        "centers_lab": centers_lab.tolist(), "centers_bgr": centers_bgr.tolist(),
        "cluster_role": cluster_role,
        "skipped_by_seq": skipped_by_seq,
    }, indent=2))
    (out / "track_teams.json").write_text(json.dumps({
        seq: {str(tid): {
            "majority_cluster": v["majority_cluster"],
            "role": v["role"],
            "n_dets": v["n_dets"],
            "vote_purity": v["vote_purity"],
            "median_dist_to_team": v["median_dist_to_team"],
            "mean_dist_to_team": v["mean_dist_to_team"],
            "votes": v["votes"],
        } for tid, v in track_teams_by_seq[seq].items()}
        for seq in SEQS
    }, indent=2))

    # Part C: sample renders
    print(f"\n=== Part C: sample renders ({args.sample_seq}) ===")
    frames_dirs = {seq: data_root / seq / "img1" for seq in SEQS}
    render_sample_torsos(records_by_seq, det_clusters_by_seq, frames_dirs,
                         centers_bgr, cluster_role, out / "sample_torsos.png")
    print(f"  -> sample_torsos.png")
    sample_recs = records_by_seq[args.sample_seq]
    render_team_colored_frame(args.sample_seq, frames_dirs[args.sample_seq],
                              sample_recs, track_teams_by_seq[args.sample_seq],
                              out / f"{args.sample_seq}_team_colored_f{args.sample_frame}.png",
                              frame_idx=args.sample_frame)
    print(f"  -> {args.sample_seq}_team_colored_f{args.sample_frame}.png")
    render_team_heatmaps(args.sample_seq, zip_path, sample_recs,
                         track_teams_by_seq[args.sample_seq], out)
    print(f"  -> team_heatmap_TeamA.png + team_heatmap_TeamB.png + team_heatmap_NonOutfield.png")

    # Part D: validate
    print(f"\n=== Part D: validate vs GSR ===")
    val = validate(records_by_seq, zip_path, track_teams_by_seq)
    print(f"  matched detections: {val['n_pairs']} (no-match: {val['n_no_match_iou_lt_thresh']})")
    print(f"  OUTFIELD TEAM ACCURACY (players + GKs): {val['outfield_team_accuracy_all_GT_outfield']:.3f}")
    print(f"    (acc_LR={val['alignment']['acc_LR']:.3f}  acc_RL={val['alignment']['acc_RL']:.3f})")
    print(f"  PLAYER-ONLY team accuracy: {val['player_only_team_accuracy']:.3f}")
    print(f"  GK-ONLY team accuracy: {val['goalkeeper_only_team_accuracy']:.3f}  "
          f"(GKs flagged non-outfield: {val['n_goalkeepers_flagged_NonOutfield']}/{val['n_goalkeepers_total']})")
    rd = val["referee_detection"]
    print(f"  REFEREE detection: P={rd['precision']:.3f}  R={rd['recall']:.3f}  F1={rd['f1']:.3f}  tp={rd['tp']} fp={rd['fp']} fn={rd['fn']}")
    print(f"    NonOutfield pred role breakdown: {rd['pred_NonOutfield_role_breakdown']}")
    (out / "validation.json").write_text(json.dumps(val, indent=2))

if __name__ == "__main__":
    main()
