# PRD — Day 11: Team Assignment (jersey clustering, GK/ref handling, GSR-validated)
**Project:** AI Sports Recording & Analytics System
**Goal:** Assign each tracked player to a team (Team A / Team B / Goalkeeper / Referee) via torso-color clustering, aggregated per-tracklet, validated against SoccerNet GSR's ground-truth team+role labels. Unlocks possession, team heatmaps, pass maps, team shape. Football, SoccerNet.
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; Day-9 tracker outputs + Day-10 pitch pipeline; SoccerNet GSR subset with team/role labels on disk

---

## Context (read first)

Day 10 delivered validated heatmaps + distance. Team assignment is the next unlock — possession, team-based heatmaps, pass maps, team shape all need "which team is this player on." It's also a prerequisite for more deliverables than ball tracking or ReID are.

**The deceptive trap:** it's NOT a clean 2-cluster problem. On a pitch there are ~5 appearance groups: Team A outfield, Team B outfield, Team A GK, Team B GK, Referee(s). Naive k=2 clustering misassigns GKs and refs. We handle them explicitly.

**Trust gate (same philosophy as Day 10's bbox_pitch):** SoccerNet GSR ships team AND role labels (it's Game State Reconstruction). Validate team-assignment accuracy against these. Keeps the measure-against-truth discipline alive in a task that otherwise has no ground truth.

**Method decision:** color-based clustering FIRST (cheap, interpretable, no training, measurable), escalate to appearance-embeddings ONLY if color fails the accuracy bar. Same staged logic as the tracker tuning.

---

## Sport & data
- Football, SoccerNet GSR subset (SNGS-116..120, already on disk with tracker outputs from Day 9 and GSR team/role labels).
- Reuse Day-9 tracker tracks. Do NOT re-run detection/tracking.

---

## PART A — Extract torso-color features per detection (~40 min)
1. For each tracked detection (frame, id, bbox), sample the TORSO region: roughly the upper-middle of the bbox (e.g. vertical 20-55% from top, horizontal central 50%) — AVOID head/skin, shorts, socks, legs, and surrounding grass. The torso is where the jersey color lives.
2. Compute a color feature for the torso crop: a histogram in a perceptually-robust space (Lab or HSV — prefer Lab for lighting robustness), or the mean/dominant torso color. Keep it simple and inspectable first.
3. Handle bad crops: skip detections where the torso region is too small (distant players), heavily occluded, or low-confidence. Note how many are skipped.

**STOP. Report: torso features extracted? spot-check a few crops (render 5-6 torso patches) — do they actually capture jersey color, not grass/skin?**

---

## PART B — Cluster into teams + separate GK/ref (~60 min)
1. **Cluster torso features into k clusters with k > 2** (try k=4 and k=5) — NOT k=2. Rationale: 2 big clusters = the outfield teams; small outlier clusters = GKs and referees (distinct kit colors, few members).
2. **Identify the two TEAM clusters** as the two largest by membership. The remaining small clusters are GK/ref candidates.
3. **Classify GK vs ref among the small clusters** — by color and/or by count (usually 1-2 GKs per team, 1-3 refs). Use GSR's role labels in validation (Part D) to check this separation worked; don't peek at them for the assignment itself (that would be cheating — assign blind, validate after).
4. **Aggregate per-tracklet, not per-frame:** assign each TRACK a single team by majority vote across all its frames' cluster memberships. This is more stable than per-frame and leverages the tracking. A track that's split across teams in its votes is a sign of an ID switch (cross-reference Day-9 ID-switch findings).

**STOP. Report: cluster structure (sizes)? did 2 big + small outliers emerge as expected? per-track assignments produced?**

---

## PART C — Render team-colored output (~30 min)
1. Render a sample sequence (SNGS-118, the Day-10 sample) with each player's bbox/marker colored by assigned team (Team A, Team B, GK, Ref distinct colors).
2. Produce a team-split heatmap: two heatmaps (one per team) on the pitch — the first genuinely team-aware analytic, and a clear visual of whether assignment is sane (teams should occupy sensible, somewhat-separated regions, not be randomly intermixed).

**STOP. Report: team-colored video/frames look right on eyeball? team-split heatmaps sane?**

---

## PART D — Validate against GSR team+role labels (the trust gate) (~40 min)
1. For each tracked detection, get the GSR ground-truth team+role for the matching GT player (match tracker box to nearest GT box by IoU, as the tracking eval does).
2. **Team accuracy with label-permutation handling:** your "cluster 0/1" labels are arbitrary vs GSR's "team A/B". Try BOTH mappings (cluster0→A or cluster0→B), take the better — standard clustering eval (optimal label alignment, like Hungarian matching). Report accuracy = fraction of player-frames assigned to the correct team after alignment.
3. **Report separately:**
   - Outfield team accuracy (the main number)
   - GK/ref detection: did the small-cluster approach correctly flag GKs and refs (precision/recall vs GSR role labels)?
4. **Sanity floor:** random 2-team assignment = 50% accuracy. A useful system should be well above (target 85%+ on distinct kits). If it's near 50%, color clustering failed — that's the signal to escalate to appearance-embeddings (next session).

**STOP. Report: outfield team accuracy (post-alignment)? GK/ref detection accuracy? above the 85% bar or does it need embeddings?**

---

## PART E — Log, interpret, commit (~30 min)
Append `## Day 11` to notes.md: torso-sampling approach, cluster structure, per-tracklet aggregation, the team-colored + team-split-heatmap outputs, and the VALIDATION (outfield team accuracy post-alignment, GK/ref detection accuracy). Plus:
- Verdict: is color clustering good enough, or is the embedding escalation needed?
- What this unlocks (possession = which team's players are near the ball; team shape; pass maps).
- Honest limitation: validated on SoccerNet distinct kits; DPS MIS kits may be more similar (school teams, bibs) — note that similar-kit robustness is the deployment risk, and embeddings would help there.
- Tie-in: tracks with split team-votes flag ID switches — cross-ref Day-9; ReID would help both team-assignment stability AND per-player distance (Day-10 caveat).
Then: confirm outputs/datasets (SoccerNet NDA)/weights/videos gitignored; commit scripts + notes + sample team visuals (if non-identifiable):
`git commit -m "Day 11: team assignment via torso-color clustering (GK/ref handled), per-tracklet, GSR-validated; team-split heatmaps"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Torso crops capture jersey color (not grass/skin)?
3. Cluster structure — did 2 teams + GK/ref outliers emerge?
4. **Outfield team accuracy vs GSR (post-alignment) — above 85%?** (the trust gate)
5. GK/ref detection accuracy?
6. Team-colored video + team-split heatmaps look right?
7. Verdict: color good enough or escalate to embeddings?
8. Errors hit (even if fixed)
9. Time taken

---

## Do NOT today
- Do NOT cluster into k=2 — that misassigns GK/ref; use k>2 and identify the 2 big clusters as teams.
- Do NOT sample the whole bbox for color — torso region only (grass/skin/shorts corrupt it).
- Do NOT assign team per-frame — aggregate per-tracklet (majority vote); more stable, leverages tracking.
- Do NOT peek at GSR labels to MAKE the assignment — assign blind, validate after (using labels to assign = cheating, inflates accuracy).
- Do NOT forget label-permutation in validation — arbitrary cluster IDs vs GSR team IDs need optimal alignment or accuracy looks falsely ~50%.
- Do NOT escalate to embeddings unless color clustering fails the ~85% bar — measure first.
- Do NOT re-run detection/tracking; reuse Day-9 outputs.
- Do NOT commit SoccerNet raw data (NDA).
