"""Day 22 Parts B-D: basketball TEAM ASSIGNMENT (torso-color clustering, court-position aided),
validated against a hand-labeled set.

Adapts the proven Day-11 football method (torso a/b-chroma KMeans + per-tracklet majority vote +
distance-outlier for non-team), basketball-tuned, with TWO basketball-specific changes:
  - NEW court-position filter (Part B): the Day-21 homography projects each detection's feet to
    court-metres, so off-court people (bench/refs near the sideline) can be flagged by POSITION --
    a lever football Day-11 lacked. (Only the c007 stable window has a homography, so the filter is
    applied there; color + distance handle the other clips.)
  - validated against HAND-LABELS (Part D), not GT (SportsMOT has no team labels). The hand-labels
    ARE the reference -> note label-noise; this is hand-label-validated, NOT GT-validated.

DEPLOYMENT REASONING (why torso-COLOR, not a luminance shortcut): the real target is DPS MIS Doha,
whose house/school teams won't follow the NCAA home-light/away-dark broadcast convention (similar PE
kits, bibs, house colours). Torso-colour clustering transfers to whatever DPS wears; a luminance
shortcut would overfit this proxy and break at deployment. (Same deployment-first logic as Day-21's
court-marking robustness.)

Assign BLIND (clustering never sees the hand-labels -- using them to assign would inflate accuracy;
the Day-11 lesson), then validate with label-permutation (cluster IDs are arbitrary; try both A/B
mappings, take the better -- the Hungarian-alignment lesson).

Outputs (outputs/team_assign_bb/):
  track_teams_bb.json   {seq: {tid: {role: TeamA/TeamB/Referee, cluster, votes, on_court_frac, ...}}}
  cluster_summary_bb.json
  sample_torsos.png     per-cluster torso swatches (spot-check the 2 teams)
  validation_bb.json    (only if hand_labels.json exists) team accuracy + ref/bench exclusion

Usage:
  python scripts/bball_team_assign.py                 # cluster + assign (+ validate if labels exist)
  python scripts/bball_team_assign.py --validate-only # re-run validation after labeling
"""
import argparse, json, sys
from collections import defaultdict, Counter
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent))
import team_assign as ta            # crop_torso, mean_lab, mean_bgr, kmeans_lab
import basketball_court as bc       # court model + apply_H

SEQS = ["v_00HRwkvvjtQ_c001", "v_00HRwkvvjtQ_c003", "v_00HRwkvvjtQ_c005",
        "v_00HRwkvvjtQ_c007", "v_00HRwkvvjtQ_c008"]
COURT_SEQ = "v_00HRwkvvjtQ_c007"    # the only clip with a Day-21 homography (stable window)


def extract_features(seq, track_path, frames_dir, step=2):
    """Per-detection torso records: (frame, tid, a, b, B,G,R, x,y,w,h). Subsamples frames (step)."""
    by_frame = defaultdict(list)
    for line in Path(track_path).read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(",")
        by_frame[int(p[0])].append((int(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5])))
    recs = []
    for f in sorted(by_frame)[::step]:
        img = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
        if img is None:
            continue
        for (tid, x, y, w, h) in by_frame[f]:
            patch = ta.crop_torso(img, x, y, w, h)
            if patch is None or patch.shape[0] * patch.shape[1] < ta.MIN_TORSO_AREA:
                continue
            lab = ta.mean_lab(patch); bgr = ta.mean_bgr(patch)
            if lab is None:
                continue
            recs.append((f, tid, lab[1], lab[2], bgr[0], bgr[1], bgr[2], x, y, w, h))
    return recs


def court_on_frac(recs, H_ci, m):
    """{tid: fraction of its detections projecting ON-court (+1.5 m margin)}. Off-court => bench/ref."""
    by_tid = defaultdict(list)
    for r in recs:
        feet = (r[7] + r[9] / 2, r[8] + r[10])   # bottom-mid
        c = bc.apply_H(H_ci, [feet])[0]
        on = abs(c[0]) <= m["hx"] + 1.5 and abs(c[1]) <= m["hy"] + 1.5
        by_tid[r[1]].append(on)
    return {tid: float(np.mean(v)) for tid, v in by_tid.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", default="outputs/track_results/bball_ftdet_bytetrack")
    ap.add_argument("--frames-root", default="datasets/sportsmot_basketball")
    ap.add_argument("--court", default="outputs/deliverables/v_00HRwkvvjtQ_c007/court/homography.json")
    ap.add_argument("--out", default="outputs/team_assign_bb")
    ap.add_argument("--step", type=int, default=2)
    ap.add_argument("--off-court-thresh", type=float, default=0.5,
                    help="track on-court fraction below this (in c007) -> Excluded (bench/ref)")
    ap.add_argument("--ref-dist-pct", type=float, default=92.0,
                    help="per-track mean a/b dist-to-team above this percentile -> Referee (color outlier)")
    ap.add_argument("--validate-only", action="store_true")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    if args.validate_only:
        validate(out)            # uses existing track_teams_bb.json + hand_labels.json
        return

    # ---- feature extraction across clips ----
    print("=== Part C: torso a/b features across clips ===")
    recs_by_seq = {}
    for seq in SEQS:
        recs = extract_features(seq, Path(args.track) / f"{seq}.txt",
                                Path(args.frames_root) / seq / "img1", step=args.step)
        recs_by_seq[seq] = recs
        print(f"  {seq}: {len(recs)} torso features")
    all_recs = [(seq, r) for seq in SEQS for r in recs_by_seq[seq]]
    feats_ab = np.array([[r[2], r[3]] for _, r in all_recs], np.float32)
    feats_bgr = np.array([[r[4], r[5], r[6]] for _, r in all_recs], np.float32)

    # ---- cluster (a/b chroma, k=2) BLIND ----
    labels, centers = ta.kmeans_lab(feats_ab, k=2)
    centers_bgr = np.array([feats_bgr[labels == c].mean(0) for c in range(2)])
    sizes = [int((labels == c).sum()) for c in range(2)]
    # Map clusters -> teams by COLOUR (robust to KMeans cluster numbering): the higher-b (more
    # neutral/white) cluster = TeamA (white jerseys), the lower-b (blue) cluster = TeamB. This
    # matches the user's labeling convention (white = A, blue = B) without depending on cluster IDs.
    white_cluster = int(np.argmax(centers[:, 1]))   # b channel: higher = whiter/neutral
    cluster_team = {white_cluster: "TeamA", 1 - white_cluster: "TeamB"}
    print(f"\n=== Part C: KMeans k=2 on a/b (blind) ===")
    for c in range(2):
        print(f"  cluster {c} [{cluster_team[c]}]: n={sizes[c]}  mean a/b={centers[c].round(1).tolist()}  BGR={centers_bgr[c].astype(int).tolist()}")

    # split labels back per seq, per detection
    det_cluster = {}; det_dist = {}
    off = 0
    for seq in SEQS:
        n = len(recs_by_seq[seq])
        det_cluster[seq] = labels[off:off + n]
        d = np.linalg.norm(feats_ab[off:off + n][:, None, :] - centers[None, :, :], axis=2).min(1)
        det_dist[seq] = d
        off += n

    # ---- Part B: court-position filter on c007 ----
    print("\n=== Part B: court-position filter (c007, Day-21 homography) ===")
    hj = json.loads(Path(args.court).read_text())
    H_ci = np.array(hj["H_court_from_img"], np.float32)
    m = bc.court_model(hj.get("model", "ncaa"))
    on_frac = court_on_frac(recs_by_seq[COURT_SEQ], H_ci, m)
    n_off = sum(1 for v in on_frac.values() if v < args.off_court_thresh)
    print(f"  c007 tracks: {len(on_frac)}  | off-court (<{args.off_court_thresh} on-court) -> Excluded: {n_off}")

    # ---- per-tracklet vote + role assignment ----
    # referee colour-outlier threshold (per-track mean dist), global
    track_meandist = []
    for seq in SEQS:
        bt = defaultdict(list)
        for r, dist in zip(recs_by_seq[seq], det_dist[seq]):
            bt[r[1]].append(dist)
        for tid, ds in bt.items():
            track_meandist.append(np.mean(ds))
    ref_thr = float(np.percentile(track_meandist, args.ref_dist_pct)) if track_meandist else 1e9

    track_teams = {}
    for seq in SEQS:
        bt_clusters = defaultdict(list); bt_dist = defaultdict(list); bt_n = Counter()
        for r, c, dist in zip(recs_by_seq[seq], det_cluster[seq], det_dist[seq]):
            bt_clusters[r[1]].append(int(c)); bt_dist[r[1]].append(float(dist)); bt_n[r[1]] += 1
        seq_out = {}
        for tid, votes in bt_clusters.items():
            cnt = Counter(votes); maj = cnt.most_common(1)[0][0]
            md = float(np.mean(bt_dist[tid]))
            ocf = on_frac.get(tid) if seq == COURT_SEQ else None
            if ocf is not None and ocf < args.off_court_thresh:
                role = "Excluded"            # off-court (bench/ref) by position
            elif md >= ref_thr:
                role = "Referee"             # colour outlier
            else:
                role = cluster_team[maj]     # white-cluster -> TeamA, blue -> TeamB
            seq_out[str(tid)] = {"role": role, "cluster": maj, "n_dets": bt_n[tid],
                                 "vote_purity": round(max(cnt.values()) / bt_n[tid], 3),
                                 "mean_dist_to_team": round(md, 2),
                                 "on_court_frac": round(ocf, 2) if ocf is not None else None,
                                 "votes": dict(cnt)}
        track_teams[seq] = seq_out
        roles = Counter(v["role"] for v in seq_out.values())
        print(f"  {seq}: {len(seq_out)} tracks -> {dict(roles)}")

    (out / "cluster_summary_bb.json").write_text(json.dumps({
        "k": 2, "sizes": sizes, "centers_ab": centers.tolist(), "centers_bgr": centers_bgr.tolist(),
        "ref_dist_threshold": ref_thr, "off_court_thresh": args.off_court_thresh,
        "note": "cluster 0/1 are arbitrary; A/B aligned at validation"}, indent=2))
    (out / "track_teams_bb.json").write_text(json.dumps(track_teams, indent=2))
    render_sample_torsos(all_recs, labels, centers_bgr, Path(args.frames_root), out / "sample_torsos.png")
    print(f"  -> track_teams_bb.json + cluster_summary_bb.json + sample_torsos.png")

    # ---- Part D: validate against hand-labels ----
    validate(out, track_teams)


def render_sample_torsos(all_recs, labels, centers_bgr, frames_root, out_path, n=8):
    import random
    rng = random.Random(0)
    by_c = defaultdict(list)
    for i, c in enumerate(labels):
        by_c[int(c)].append(i)
    cw, ch = 60, 90
    canvas = np.full((2 * (ch + 4), (n + 1) * (cw + 4), 3), 255, np.uint8)
    for c in range(2):
        sw = np.full((ch, cw, 3), centers_bgr[c], np.uint8)
        cv2.putText(sw, f"#{c}", (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        canvas[c * (ch + 4):c * (ch + 4) + ch, 0:cw] = sw
        for col, gi in enumerate(rng.sample(by_c[c], min(n, len(by_c[c])))):
            seq, r = all_recs[gi]
            img = cv2.imread(str(Path(frames_root) / seq / "img1" / f"{r[0]:06d}.jpg"))
            if img is None:
                continue
            patch = ta.crop_torso(img, r[7], r[8], r[9], r[10])
            if patch is None or patch.size == 0:
                continue
            patch = cv2.resize(patch, (cw, ch))
            x1 = (col + 1) * (cw + 4)
            canvas[c * (ch + 4):c * (ch + 4) + ch, x1:x1 + cw] = patch
    cv2.imwrite(str(out_path), canvas)


def validate(out, track_teams=None):
    lab_path = out / "hand_labels.json"
    crops_path = out / "crops.npz"
    if not lab_path.exists() or not crops_path.exists():
        print("\n=== Part D: validation SKIPPED (no hand_labels.json yet -- run label_crops.py) ===")
        return
    if track_teams is None:
        track_teams = json.loads((out / "track_teams_bb.json").read_text())
    labels = json.loads(lab_path.read_text())
    manifest = json.loads(str(np.load(crops_path, allow_pickle=True)["manifest"]))

    # crop -> assigned role (via its track's per-tracklet assignment)
    pairs = []   # (hand_label, assigned_role)
    for idx, hand in labels.items():
        mf = manifest[int(idx)]
        tv = track_teams.get(mf["seq"], {}).get(str(mf["tid"]))
        if tv is None:
            continue
        pairs.append((hand, tv["role"]))

    team_pairs = [(h, a) for (h, a) in pairs if h in ("A", "B") and a in ("TeamA", "TeamB")]
    # permutation-align (cluster IDs arbitrary): try both A->TeamA/B
    def acc(mp):
        return np.mean([mp[h] == a for h, a in team_pairs]) if team_pairs else 0.0
    a1 = acc({"A": "TeamA", "B": "TeamB"}); a2 = acc({"A": "TeamB", "B": "TeamA"})
    team_acc = max(a1, a2)
    best_mp = {"A": "TeamA", "B": "TeamB"} if a1 >= a2 else {"A": "TeamB", "B": "TeamA"}
    per_class = {}
    for hl in ("A", "B"):
        cp = [a for h, a in team_pairs if h == hl]
        per_class[hl] = round(np.mean([a == best_mp[hl] for a in cp]), 4) if cp else None

    # how many A/B crops got excluded (Referee/Excluded) instead of a team -> coverage loss
    ab_total = sum(1 for h, _ in pairs if h in ("A", "B"))
    ab_excluded = sum(1 for h, a in pairs if h in ("A", "B") and a in ("Referee", "Excluded"))
    # ref/bench exclusion recall: of ref+bench crops, fraction assigned non-team
    rb = [(h, a) for h, a in pairs if h in ("ref", "bench")]
    rb_excluded = sum(1 for h, a in rb if a in ("Referee", "Excluded"))

    res = {
        "n_labeled": len(labels), "n_matched_to_track": len(pairs),
        "team_accuracy_post_alignment": round(team_acc, 4),
        "acc_A_TeamA": round(a1, 4), "acc_A_TeamB": round(a2, 4),
        "best_alignment": best_mp, "per_class_accuracy": per_class,
        "n_team_pairs_scored": len(team_pairs),
        "team_crops_excluded_frac": round(ab_excluded / ab_total, 4) if ab_total else None,
        "ref_bench_exclusion_recall": round(rb_excluded / len(rb), 4) if rb else None,
        "n_ref_bench": len(rb),
        "label_counts": dict(Counter(labels.values())),
        "note": "hand-label-validated (labels ARE the reference; possible label noise). "
                "Random 2-team floor = 50%; football Day-11 GT-validated 88-92%.",
    }
    (out / "validation_bb.json").write_text(json.dumps(res, indent=2))
    print("\n=== Part D: validation vs hand-labels ===")
    print(f"  labeled: {res['n_labeled']}  matched-to-track: {res['n_matched_to_track']}  "
          f"team-pairs scored: {res['n_team_pairs_scored']}")
    print(f"  TEAM ACCURACY (post-alignment): {team_acc:.3f}  (A->TeamA {a1:.3f} / A->TeamB {a2:.3f})")
    print(f"    per-class: A={per_class['A']}  B={per_class['B']}  (best map {best_mp})")
    print(f"  team crops wrongly excluded: {res['team_crops_excluded_frac']}")
    print(f"  ref/bench exclusion recall: {res['ref_bench_exclusion_recall']}  (n={len(rb)})")
    print(f"  label counts: {res['label_counts']}")


if __name__ == "__main__":
    main()
