# PRD — Day 32: Formation-Invariant Dead-Ball Identity Anchor (PROBE) — ZXY-validated — Football
**Project:** AI Sports Recording & Analytics System — for DPS MIS Doha
**Goal:** PROBE one appearance-free lever against full-match identity drift: re-anchor track IDs at dead-balls by registering consecutive settled-position sets to each other (formation-INVARIANT point-set registration — no assumed formation). Measure whether it reduces the ZXY-grounded identity error (IDs-per-player) vs the Day-30 baseline. Measure-first: build, measure the lift, honest keep-or-drop — NOT a commitment. Football, Alfheim full-match.
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; Day-29 stitched half + MOT + fixed H + ZXY GT; Day-30 `alfheim_identity_metric.py` (the ZXY-grounded IDF1/purity/IDs-per-GT metric — REUSE as the scorer) + Day-30 re-linked tracks (the −18% safe baseline)

---

## PROJECT GOAL CONTEXT (DPS-aware — read first)
Deployable system for DPS MIS Doha. Full-match testing (Day-29/30/31) found: foundation scales, analytics team-level-OK, events blocked (wide-cam ball recall 30%), player-highlights blocked at scale (2,224 clips, fragmentation-driven). Identity fragmentation (Day-30: 191 IDs/player) is the root blocker for per-player outputs; Day-30 proved local motion re-linking + appearance can't fix it (structural occlusion hopping + identical kits). This PROBES a DIFFERENT, untried, appearance-free lever from the research roadmap: dead-ball formation anchoring.

**Honest scope of the claim (set expectations):** a dead-ball anchor re-pins identity only AT dead-balls (kickoff, post-goal, maybe throw-ins/stoppages) — which are SPARSE. So it can BOUND drift (periodic reset) but CANNOT prevent the fragmentation that accumulates BETWEEN anchors. Realistic best case = a MODEST reduction in effective fragmentation, NOT "identity solved." Frame the result against that, not against 22.

**Why formation-INVARIANT not template:** DPS house/school matches won't hold pro formations (4-3-3 etc.), so DON'T map to a tactical template. Instead register the CURRENT settled position-set to the PREVIOUS dead-ball's set (Coherent Point Drift / ICP between consecutive snapshots) — re-associates the same ~22 identities across the gap without assuming any formation. This is the version that transfers to DPS.

**Why this is worth probing despite degraded Alfheim input:** if it helps even modestly on Alfheim's WORST-CASE single wide cam (tiny noisy detections), that's a LOWER BOUND on the DPS benefit (DPS dual-cam/closer/higher-res = cleaner tracklets, anchoring works better). A positive here → real DPS-deployment lever. Negative → anchoring's bounded-reset nature isn't enough, documented cheaply.

---

## PART A — Detect dead-ball / settled moments (~50 min)
No event labels, so detect settled moments from motion:
1. Find frames where overall player motion is LOW + players are SPREAD (not clustered) — the signature of a settled/dead-ball formation (kickoff lineup, post-goal reset, settled restart). Use the re-linked tracks' pitch positions (via fixed H).
2. Identify a set of "anchor frames" across the half (expect a handful — kickoffs of each half, post-goal, settled restarts). Report how many found + roughly where.
3. Honest check: are these actually settled-formation moments (cross-check a couple against the video/ZXY spread), or just low-motion noise? A bad anchor moment corrupts the re-association.

**STOP. Report: how many anchor moments detected over the half? do they look like genuine settled formations? (too few = the lever has little to work with — itself a finding)**

---

## PART B — Formation-invariant re-anchor via point-set registration (~70 min)
1. At each anchor frame, take the set of player pitch-positions (the ~22 in view).
2. Between CONSECUTIVE anchor frames, run point-set registration (ICP or Coherent Point Drift) to find the best correspondence between the two position-sets — i.e. which player at anchor N is which at anchor N+1 — using ONLY geometry (relative spatial configuration), NO appearance, NO assumed template.
3. Use that correspondence to RE-UNIFY track IDs: IDs that drifted/fragmented between the anchors but map to the same registered position get merged under one identity. (This is the "reset" — re-pinning the ~22 identities at each anchor.)
4. Over-merge guard (the Day-30 lesson): verify against ZXY that re-anchored merges join the SAME GT player, not different ones. Registration ambiguity (two players near-swapped between anchors) is the risk — flag it.

**STOP. Report: registration ran between anchors? IDs re-unified? over-merge checked vs ZXY (joining same GT player)?**

---

## PART C — Measure the lift vs ZXY (the probe verdict) (~40 min)
Reuse the Day-30 `alfheim_identity_metric.py` scorer:
1. Compute the ZXY-grounded identity metrics on the formation-anchored tracks: IDs-per-GT-player, purity, IDF1, ID-switches.
2. **The before/after table vs the Day-30 baseline:**
   | Metric | Day-30 (re-linked baseline) | Day-32 (+formation anchor) | Δ |
   |---|---|---|---|
   | IDs-per-GT-player (median) | 191 | ? | ? |
   | purity | 0.116 | ? | ? |
   | IDF1 | (Day-30 value) | ? | ? |
   | over-merge (2-GT-spanning tracks) | ~202 | ? | ? |
3. **Verdict:** did formation anchoring MEANINGFULLY reduce IDs-per-player without over-merging? (Realistic: a modest drop, given anchors are sparse.) Keep-or-drop, honestly.

**STOP. Report the before/after table + the honest keep/drop verdict.**

---

## PART D — Log + decision + commit (~30 min)
notes.md `## Day 32`: the probe (formation-invariant dead-ball anchor), anchor-moment count, the registration approach, the ZXY before/after table, over-merge check, and the verdict:
- KEEP (meaningful lift, no over-merge) → a real appearance-free DPS-deployment lever; note it'll likely help MORE on DPS's cleaner dual-cam input (lower bound demonstrated here).
- DROP (negligible / over-merges) → anchoring's sparse-reset nature insufficient on this footage; documented, the global min-cost-flow stitcher remains the bigger untried option (but needs cleaner tracklets — defer to DPS footage).
- Honest synthesis: where identity now stands — the per-player outputs remain blocked at full-match scale pending either better input (DPS dual-cam) or the heavier global stitcher; this probe tested the cheapest lever first.
- Caveats: ZXY home-team-only metric; sparse anchors bound but don't eliminate drift; Alfheim worst-case input (DPS expected better); still a proxy.
gitignore (Alfheim local); commit scripts + notes + the probe result:
`git commit -m "Day 32: formation-invariant dead-ball identity anchor PROBE; ZXY-measured lift vs Day-30; keep/drop verdict"`; (push per your workflow).

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Anchor moments detected over the half — how many, genuine settled formations?
3. Registration + ID re-unification ran?
4. Over-merge checked vs ZXY (same GT player)?
5. Before/after table: IDs-per-player / purity / IDF1 vs Day-30
6. VERDICT: meaningful lift or negligible? keep or drop?
7. Errors + time

---

## Do NOT today
- Do NOT assume a tactical formation template — formation-INVARIANT (register consecutive sets) so it transfers to DPS school games.
- Do NOT expect "identity solved" — anchors are sparse, this BOUNDS drift, modest lift is the realistic best case; judge against that.
- Do NOT use appearance — geometry/position registration only (identical kits).
- Do NOT over-merge — registration can mis-pair near-swapped players; verify merges vs ZXY join the SAME player (the Day-30 guard).
- Do NOT judge by raw ID count — the ZXY-grounded metric is the verdict (reuse Day-30's scorer).
- Do NOT build the global min-cost-flow stitcher today — that's the heavier lever needing cleaner tracklets; this probes the cheap one first.
- Do NOT re-run detection/tracking — reuse Day-29 MOT + Day-30 re-linked tracks.
- Do NOT commit Alfheim data.
