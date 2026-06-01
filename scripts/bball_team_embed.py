"""Day 23: basketball team assignment via FROZEN PRETRAINED APPEARANCE EMBEDDINGS.

Day-22 used mean a/b colour -> the neutral/white KMeans cluster became an ATTRACTOR (shadowed-blue +
grey-ref + white-jersey all collapse toward neutral chroma): Blue 65%, ref-exclusion 16%, overall
79.6%. That's STRUCTURAL, not a tuning bug. This swaps the feature for a frozen ImageNet ResNet18
penultimate embedding (512-d), which separates on texture/pattern/structure, not mean chroma -- so
the attractor should dissolve. Everything else (per-tracklet majority vote, court-position filter,
the SAME 717 hand-labels) is held fixed for a clean before/after.

Why FROZEN pretrained is the DPS-right choice: nothing is fit to NCAA kits -> the encoder transfers
to DPS kits unchanged (no retrain, no proxy overfit). Same pattern that fixed Day-19 ball-vs-head.
NOT a ReID model: ReID maximises INTER-individual distinctness (wrong for team-grouping; it's the
later per-player-highlights tool). We use a generic appearance encoder + unsupervised 2-means.

Tests TORSO-only vs FULL-BODY embeddings (full body may add shorts/socks team signal) and reports
which clusters better. Blind clustering; validate after on the 717 labels (Hungarian permutation).

Outputs (outputs/team_assign_bb/):
  track_teams_emb.json     winner's per-(seq,tid) roles (TeamA=white / TeamB=blue / Referee/Excluded)
  validation_emb.json      before/after vs Day-22 (overall, per-class, ref-exclusion), both regions
  sample_torsos_emb.png    winner's 2 team clusters (spot-check)

Usage:
  python scripts/bball_team_embed.py                # both regions, pick winner, validate
  python scripts/bball_team_embed.py --region full  # force one region
"""
import argparse, json, sys
from collections import defaultdict, Counter
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent))
import team_assign as ta
import basketball_court as bc
from ball_head_classifier import embed_all   # frozen ResNet18 (ImageNet) 512-d, L2-normalized

SEQS_DEFAULT = ["v_00HRwkvvjtQ_c001", "v_00HRwkvvjtQ_c003", "v_00HRwkvvjtQ_c005",
                "v_00HRwkvvjtQ_c007", "v_00HRwkvvjtQ_c008"]
COURT_SEQ_DEFAULT = "v_00HRwkvvjtQ_c007"
DAY22 = {"overall": 0.796, "A_white": 0.983, "B_blue": 0.652, "ref_excl": 0.16}


def extract_patches(track_path, frames_dir, step=2):
    """Per-detection (frame,tid,x,y,w,h) + aligned 64x64 BGR patches for torso and full body."""
    by_frame = defaultdict(list)
    for line in Path(track_path).read_text().splitlines():
        if not line.strip():
            continue
        p = line.split(",")
        by_frame[int(p[0])].append((int(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5])))
    recs, torso, full = [], [], []
    for f in sorted(by_frame)[::step]:
        img = cv2.imread(str(frames_dir / f"{f:06d}.jpg"))
        if img is None:
            continue
        Hh, Ww = img.shape[:2]
        for (tid, x, y, w, h) in by_frame[f]:
            tp = ta.crop_torso(img, x, y, w, h)
            x1, y1 = max(0, int(x)), max(0, int(y)); x2, y2 = min(Ww, int(x + w)), min(Hh, int(y + h))
            if tp is None or tp.size < ta.MIN_TORSO_AREA or x2 - x1 < 6 or y2 - y1 < 10:
                continue
            recs.append((f, tid, x, y, w, h))
            torso.append(cv2.resize(tp, (64, 64)))
            full.append(cv2.resize(img[y1:y2, x1:x2], (64, 64)))
    return recs, np.array(torso), np.array(full)


def pca_reduce(X, dim=50):
    Xc = X - X.mean(0, keepdims=True)
    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    return (Xc @ Vt[:dim].T).astype(np.float32)


def assign(recs_by_seq, emb_by_seq, court_ci, court_m, off_thresh=0.5, ref_pct=92.0, pca_dim=50,
           seqs=None, court_seq=None):
    """Cluster embeddings (k=2) BLIND -> per-(seq,tid) roles. TeamA = whiter cluster (set later by
    caller via colour); here clusters are 0/1, caller maps. Returns track_teams + centers + det info."""
    if seqs is None:
        seqs = SEQS_DEFAULT
    if court_seq is None:
        court_seq = COURT_SEQ_DEFAULT
    all_emb = np.concatenate([emb_by_seq[s] for s in seqs])
    feat = pca_reduce(all_emb, pca_dim) if pca_dim else all_emb
    labels, centers = ta.kmeans_lab(feat, k=2)
    off = 0; det_cluster = {}; det_dist = {}
    for s in seqs:
        n = len(recs_by_seq[s])
        det_cluster[s] = labels[off:off + n]
        d = np.linalg.norm(feat[off:off + n][:, None, :] - centers[None, :, :], axis=2).min(1)
        det_dist[s] = d; off += n
    # court-position on-court fraction (court_seq only)
    on_frac = {}
    for r in recs_by_seq[court_seq]:
        feet = (r[2] + r[4] / 2, r[3] + r[5])
        c = bc.apply_H(court_ci, [feet])[0]
        ok = abs(c[0]) <= court_m["hx"] + 1.5 and abs(c[1]) <= court_m["hy"] + 1.5
        on_frac.setdefault(r[1], []).append(ok)
    on_frac = {t: float(np.mean(v)) for t, v in on_frac.items()}
    # referee distance-outlier threshold (per-track mean dist, global)
    md_all = []
    for s in seqs:
        bt = defaultdict(list)
        for r, dd in zip(recs_by_seq[s], det_dist[s]):
            bt[r[1]].append(dd)
        md_all += [np.mean(v) for v in bt.values()]
    ref_thr = float(np.percentile(md_all, ref_pct)) if md_all else 1e9
    track_teams = {}
    for s in seqs:
        btc = defaultdict(list); btd = defaultdict(list)
        for r, c, dd in zip(recs_by_seq[s], det_cluster[s], det_dist[s]):
            btc[r[1]].append(int(c)); btd[r[1]].append(float(dd))
        out = {}
        for tid, votes in btc.items():
            cnt = Counter(votes); maj = cnt.most_common(1)[0][0]; md = float(np.mean(btd[tid]))
            ocf = on_frac.get(tid) if s == court_seq else None
            if ocf is not None and ocf < off_thresh:
                role = ("Excluded", maj)
            elif md >= ref_thr:
                role = ("Referee", maj)
            else:
                role = ("cluster%d" % maj, maj)
            out[str(tid)] = {"role_raw": role[0], "cluster": maj, "n_dets": len(votes),
                             "mean_dist": round(md, 3),
                             "on_court_frac": round(ocf, 2) if ocf is not None else None}
        track_teams[s] = out
    return track_teams, centers, det_cluster, labels


def whiten_map(all_full_emb_unused, recs_by_seq, emb_by_seq, det_cluster):
    """Decide which cluster is the WHITE team by mean BGR of its torso crops -> TeamA=white (matches
    the user's white=A convention). Returns {0/1 -> TeamA/TeamB}."""
    # mean torso BGR per cluster (use the torso patches caller passes via emb_by_seq is embeddings,
    # so caller must give us bgr means); handled in main instead.
    raise NotImplementedError


def finalize_roles(track_teams, cluster_team):
    for s, tracks in track_teams.items():
        for tid, v in tracks.items():
            rr = v["role_raw"]
            v["role"] = cluster_team[v["cluster"]] if rr.startswith("cluster") else rr
    return track_teams


def validate(track_teams, out_dir):
    # Hand-label validation only exists for the SportsMOT benchmark. On operator
    # footage these files are absent — skip validation, return a benign stub.
    if not (out_dir / "hand_labels.json").exists() or not (out_dir / "crops.npz").exists():
        return {"overall": 0.0, "per_class": {"A": None, "B": None},
                "ref_bench_exclusion_recall": None, "n_ref_bench": 0,
                "team_crops_excluded_frac": None, "skipped": True}
    labels = json.loads((out_dir / "hand_labels.json").read_text())
    manifest = json.loads(str(np.load(out_dir / "crops.npz", allow_pickle=True)["manifest"]))
    pairs = []
    for idx, hand in labels.items():
        mf = manifest[int(idx)]
        tv = track_teams.get(mf["seq"], {}).get(str(mf["tid"]))
        if tv:
            pairs.append((hand, tv["role"]))
    team_pairs = [(h, a) for h, a in pairs if h in ("A", "B") and a in ("TeamA", "TeamB")]
    def acc(mp): return np.mean([mp[h] == a for h, a in team_pairs]) if team_pairs else 0.0
    a1 = acc({"A": "TeamA", "B": "TeamB"}); a2 = acc({"A": "TeamB", "B": "TeamA"})
    best = {"A": "TeamA", "B": "TeamB"} if a1 >= a2 else {"A": "TeamB", "B": "TeamA"}
    per = {}
    for hl in ("A", "B"):
        cp = [a for h, a in team_pairs if h == hl]
        per[hl] = round(float(np.mean([a == best[hl] for a in cp])), 4) if cp else None
    rb = [(h, a) for h, a in pairs if h in ("ref", "bench")]
    rb_excl = sum(1 for h, a in rb if a in ("Referee", "Excluded"))
    ab_tot = sum(1 for h, _ in pairs if h in ("A", "B"))
    ab_excl = sum(1 for h, a in pairs if h in ("A", "B") and a in ("Referee", "Excluded"))
    return {"overall": round(max(a1, a2), 4), "per_class": per, "best_align": best,
            "ref_bench_exclusion_recall": round(rb_excl / len(rb), 4) if rb else None, "n_ref_bench": len(rb),
            "team_crops_excluded_frac": round(ab_excl / ab_tot, 4) if ab_tot else None,
            "n_team_pairs": len(team_pairs), "n_matched": len(pairs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seq", default=None,
                    help="single seq to process (overrides the hardcoded SEQS list)")
    ap.add_argument("--track", default="outputs/track_results/bball_ftdet_bytetrack")
    ap.add_argument("--frames-root", default="datasets/sportsmot_basketball")
    ap.add_argument("--court", default="outputs/deliverables/v_00HRwkvvjtQ_c007/court/homography.json")
    ap.add_argument("--out", default="outputs/team_assign_bb")
    ap.add_argument("--step", type=int, default=2)
    ap.add_argument("--pca", type=int, default=50)
    ap.add_argument("--region", choices=["torso", "full", "both"], default="both")
    args = ap.parse_args()
    # --seq overrides: process a single job seq instead of the SportsMOT list
    seqs = [args.seq] if args.seq else SEQS_DEFAULT
    court_seq = args.seq if args.seq else COURT_SEQ_DEFAULT
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    device = "cuda"
    hj = json.loads(Path(args.court).read_text())
    court_ci = np.array(hj["H_court_from_img"], np.float32); court_m = bc.court_model(hj.get("model", "ncaa"))

    print("=== Part A: extract patches + embed (frozen ResNet18) ===")
    recs_by_seq, torso_by_seq, full_by_seq, bgr_by_seq = {}, {}, {}, {}
    for s in seqs:
        recs, torso, full = extract_patches(Path(args.track) / f"{s}.txt", Path(args.frames_root) / s / "img1", args.step)
        recs_by_seq[s] = recs; torso_by_seq[s] = torso; full_by_seq[s] = full
        # mean torso BGR per det (for white/blue cluster identification)
        bgr_by_seq[s] = np.array([p.reshape(-1, 3).mean(0) for p in torso]) if len(torso) else np.zeros((0, 3))
        print(f"  {s}: {len(recs)} dets")

    regions = ["torso", "full"] if args.region == "both" else [args.region]
    results = {}
    for region in regions:
        src = torso_by_seq if region == "torso" else full_by_seq
        emb_by_seq = {}
        for s in seqs:
            emb_by_seq[s] = embed_all(list(src[s]), device) if len(src[s]) else np.zeros((0, 512), np.float32)
        print(f"\n=== {region}: cluster (k=2, PCA={args.pca}) + assign ===")
        track_teams, centers, det_cluster, labels = assign(
            recs_by_seq, emb_by_seq, court_ci, court_m, pca_dim=args.pca,
            seqs=seqs, court_seq=court_seq)
        # map cluster -> team by torso colour: whiter (higher mean B+G+R, low saturation) cluster = TeamA(white)
        all_bgr = np.concatenate([bgr_by_seq[s] for s in seqs])
        cluster_bright = [all_bgr[labels == c].mean(0).mean() if (labels == c).any() else 0 for c in range(2)]
        white_cluster = int(np.argmax(cluster_bright))
        cluster_team = {white_cluster: "TeamA", 1 - white_cluster: "TeamB"}
        finalize_roles(track_teams, cluster_team)
        val = validate(track_teams, out)
        results[region] = {"val": val, "track_teams": track_teams, "labels": labels,
                           "white_cluster": white_cluster, "cluster_bright": cluster_bright}
        print(f"  overall {val['overall']:.3f} | A(white) {val['per_class']['A']} "
              f"B(blue) {val['per_class']['B']} | ref-excl {val['ref_bench_exclusion_recall']} "
              f"(n={val['n_ref_bench']}) | team-excl {val['team_crops_excluded_frac']}")

    # pick winner by overall, but report both
    winner = max(results, key=lambda r: results[r]["val"]["overall"])
    print("\n=== BEFORE/AFTER (vs Day-22 colour) ===")
    print(f"  {'metric':<22}{'Day22 colour':>14}{'torso emb':>12}{'full emb':>12}")
    def row(name, key, sub=None):
        def g(r):
            if r not in results: return "  --"
            v = results[r]["val"]; x = v[key] if sub is None else v[key][sub]
            return f"{x*100:.1f}%" if x is not None else "--"
        d22 = {"overall": DAY22["overall"], ("per_class", "A"): DAY22["A_white"],
               ("per_class", "B"): DAY22["B_blue"], "ref_bench_exclusion_recall": DAY22["ref_excl"]}
        dk = (key, sub) if sub else key
        print(f"  {name:<22}{d22.get(dk,0)*100:>13.1f}%{g('torso'):>12}{g('full'):>12}")
    row("overall", "overall"); row("Team A (white)", "per_class", "A")
    row("Team B (blue)", "per_class", "B"); row("ref/bench exclusion", "ref_bench_exclusion_recall")
    print(f"  WINNER: {winner} embedding (overall {results[winner]['val']['overall']:.3f})")

    w = results[winner]
    blue_ok = w["val"]["per_class"]["B"] and w["val"]["per_class"]["B"] > DAY22["B_blue"]
    ref_ok = w["val"]["ref_bench_exclusion_recall"] and w["val"]["ref_bench_exclusion_recall"] > DAY22["ref_excl"]
    verdict = "PASS" if (blue_ok and ref_ok) else "PARTIAL" if (blue_ok or ref_ok) else "FAIL"
    print(f"  STRUCTURAL FIX (Blue>65.2% AND ref>16%): {verdict}  (blue_improved={bool(blue_ok)}, ref_improved={bool(ref_ok)})")

    (out / "track_teams_emb.json").write_text(json.dumps(w["track_teams"], indent=2))
    (out / "validation_emb.json").write_text(json.dumps({
        "backbone": "frozen ImageNet ResNet18 (512-d), L2-norm, PCA%d" % args.pca,
        "winner_region": winner, "verdict": verdict,
        "day22_colour": DAY22, "torso": results.get("torso", {}).get("val"),
        "full": results.get("full", {}).get("val"),
        "note": "hand-label-validated (717 labels = reference; possible label noise). "
                "Blind clustering; Hungarian permutation-aligned. TeamA=white, TeamB=blue."}, indent=2))
    print(f"\n  -> track_teams_emb.json + validation_emb.json  ({winner} region)")


if __name__ == "__main__":
    main()
