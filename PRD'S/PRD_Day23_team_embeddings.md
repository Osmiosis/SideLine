# PRD — Day 23: Team Assignment via Appearance Embeddings (fix the white-attractor ceiling)
**Project:** AI Sports Recording & Analytics System — for DPS MIS Doha
**Goal:** Replace mean-color team clustering with FROZEN PRETRAINED APPEARANCE EMBEDDINGS to fix the structural white-attractor failure (Day-22: Blue 65%, ref-exclusion 16%, overall 79.6%). Cluster embeddings instead of a/b chroma. Validate on the SAME 717 Day-22 hand-labels — clean before/after. Success = Blue-team AND ref-exclusion specifically improve, not just the average. Basketball, SportsMOT (proxy for DPS).
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; Day-22 `bball_team_assign.py` + the 717 hand-labels (`hand_labels.json`) + crops + court-position filter + Day-9 tracks

---

## PROJECT GOAL CONTEXT (DPS-aware, read first)
Deployable system for DPS MIS Doha (fixed dual-phone capture → coach analytics + player highlights + event reels). Proxies (SportsMOT) build/validate the METHOD; real target is DPS kits/courts.

**Why a FROZEN pretrained embedding is the DPS-right choice:** it's a general-purpose appearance encoder with nothing fit to NCAA kits → transfers to DPS unchanged (no retraining, no overfit to the proxy). Same pattern that beat the Day-19 ball-vs-head problem. We validate on the proxy's hand-labels, but the method carries to DPS.

**Why embeddings, not color (the Day-22 finding):** mean a/b color collapses shadowed-blue + grey-ref + white-jersey all toward "neutral" → the white cluster became an ATTRACTOR absorbing every ambiguous crop (Blue 65%, refs 16%). This is STRUCTURAL, not a tuning bug — and DPS kits (often white/pale/bibs) likely make it WORSE. Embeddings separate on texture/pattern/structure, not mean chroma, so the attractor problem should dissolve.

**Scope note (important):** TODAY = team assignment via embeddings (Option A). The Day-9 ReID model (Option B) is a DIFFERENT tool for a DIFFERENT later job — PER-PLAYER identity for individual highlights (both sports). ReID maximizes INTER-individual distinctness (wrong for team-grouping, right for player-tracking-for-highlights). Note ReID as the player-highlights unlock; do NOT use it for team-grouping today.

---

## PART A — Embed the crops + cluster (~70 min)
1. Reuse the Day-22 player crops (the 780 generated + whatever the 717 labels cover). For each crop, take the TORSO region (same upper-central sampling — still avoid limbs/skin) OR the full player crop (test both: torso-only vs full-body embedding — full-body may capture more team signal like shorts/socks; report which clusters better).
2. Embed each crop with a FROZEN pretrained backbone (e.g. ResNet18/50 ImageNet penultimate features, or a CLIP image encoder — use what's available locally / pip-installable; keep it lightweight for the 4060). NO training, NO fine-tuning — frozen features only (the DPS-transfer property).
3. Optionally L2-normalize + reduce (PCA) before clustering to denoise.
4. **Cluster the embeddings into 2 teams** (KMeans k=2, or agglomerative). Per-(seq,tid) majority vote (the Day-22 stable aggregation). Keep the Day-22 court-position filter (off-court → excluded) as a SEPARATE pre-filter — it's orthogonal and helped.
5. Ref handling: refs should now be MORE separable (striped/grey texture differs from solid jerseys in embedding space) — test whether they fall into a distinct embedding region or need the court-position filter + an outlier step.

**STOP. Report: embeddings computed (which backbone, torso vs full-body)? 2 clean team clusters in embedding space? do refs separate better than color did?**

---

## PART B — Validate on the SAME 717 hand-labels (clean before/after) (~50 min)
1. Match embedding-cluster assignments to the 717 hand-labels. Permutation-align (Hungarian, as Day-22). 
2. **Report the SAME breakdown as Day-22 for direct comparison:**
   | Metric | Day-22 color | Day-23 embeddings |
   |---|---|---|
   | Overall team accuracy | 79.6% | ? |
   | Team A (white) | 98.3% | ? |
   | Team B (blue) | 65.2% | ? |
   | Ref/bench exclusion recall | 16% | ? |
3. **Success criteria (the specific failure, not the average):** Blue-team accuracy must materially improve (target → 85%+), AND ref-exclusion must improve. If overall goes up but Blue is still the attractor victim, embeddings did NOT fix the structural problem — report that honestly.
4. Also report torso-only vs full-body embedding if both tried.

**STOP. Report the before/after table. Did Blue + refs SPECIFICALLY improve? PASS/FAIL on the structural fix.**

---

## PART C — Regenerate the basketball deliverable + decide (~50 min)
**If PASS (Blue + refs improved):**
1. Regenerate the Day-21/22 basketball PDF + tactical video with the embedding-based teams: team-split heatmaps + possession now resting on the better assignment.
2. Re-check the possession number (Day-22's A81/B19 was on the 65%-accurate Blue — recompute on the improved teams; it may shift meaningfully, which itself shows why the fix mattered).

**If FAIL (embeddings didn't fix Blue/refs):**
1. Honest: frozen embeddings insufficient for this; document. Options to note: per-match calibration, a small fine-tune, or accept-and-defer-to-DPS-footage.
2. Don't regenerate on a still-broken assignment.

**STOP. Report: PASS → regenerated deliverable + updated possession; FAIL → honest documentation + options.**

---

## PART D — Log + commit (~30 min)
notes.md `## Day 23`: the structural diagnosis (white-attractor, color's ceiling), the embedding method (backbone, torso vs full-body), the before/after table vs Day-22's 79.6%/65%/16%, PASS/FAIL on the SPECIFIC failure, and:
- DPS-transfer reasoning: frozen embedder has nothing fit to NCAA → carries to DPS kits.
- The ReID-for-player-highlights note (Option B is the LATER per-player-identity tool, distinct from today's team-grouping).
- Honest level: hand-label-validated (717 labels are the reference; possible label noise), downstream possession/heatmaps still inherit tracking ID-switch noise.
- Per-match calibration likely still needed for DPS; similar-kit remains the deployment risk (but embeddings should degrade more gracefully than color).
gitignore checks (crops/labels regenerable, gitignored); commit scripts + notes + (if PASS) refreshed package:
`git commit -m "Day 23: team assignment via frozen appearance embeddings; [PASS Blue X% ref Y% vs color 65/16 / FAIL]; DPS-transferable method"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Backbone used; torso-only vs full-body — which clustered better?
3. Before/after table (overall, Team A, Team B, ref-exclusion) vs Day-22
4. PASS/FAIL on the SPECIFIC failure: did Blue (65%) and refs (16%) improve?
5. If PASS: regenerated deliverable + how much did possession shift?
6. If FAIL: honest read + options
7. Errors hit (even if fixed)
8. Time taken

---

## Do NOT today
- Do NOT fine-tune/train the embedder — frozen features only (the DPS-transfer property; training would overfit the NCAA proxy).
- Do NOT use a ReID model for team-grouping — ReID maximizes inter-individual distinctness (wrong for grouping). It's the LATER per-player-highlights tool.
- Do NOT judge success on overall accuracy alone — Blue-team + ref-exclusion are the structural failure; they must specifically improve.
- Do NOT use hand-labels to MAKE the clustering — cluster BLIND, validate after (the Day-11/22 lesson).
- Do NOT forget Hungarian permutation-alignment in validation.
- Do NOT regenerate the deliverable on a still-broken assignment (if FAIL).
- Do NOT claim GT-validation — hand-label-validated (717 labels = reference).
- Do NOT re-run detection/tracking — reuse Day-9 tracks + Day-22 crops/filter.
- Do NOT commit crops/labels (regenerable/user-data, gitignored).
