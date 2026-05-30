# PRD — Day 26: ReID for Player Identity — Measure the Stability Lift (gate for output #2)
**Project:** AI Sports Recording & Analytics System — for DPS MIS Doha
**Goal:** Stand up appearance-ReID on top of the tracker and MEASURE how much it improves player identity-stability (HOTA/AssA/IDF1/ID-switches) vs the Day-9 tuned baseline — the gate that decides whether per-player highlight reels (output #2) are viable. Measure-first; build reels only if the lift justifies it. Football, SoccerNet.
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; TrackEval harness (Day-6), Day-9 tuned tracker (BoT-SORT+GMC, the production config), cached detections (Day-9), SoccerNet GSR subset + GT tracklets

---

## PROJECT GOAL CONTEXT (DPS-aware — read first)
Deployable system for DPS MIS Doha: fixed dual-phone capture → ONE pipeline → THREE outputs: (1) coach analytics [DONE both sports], (2) **per-player highlights [THIS \u2014 last unstarted output]**, (3) event reels [DONE both sports]. Proxies build/validate the METHOD; real target = DPS.

**DPS identity reality (user-confirmed):** DPS teams do NOT reliably wear numbered jerseys → jersey-number OCR is OUT. The deployment identity path is **MANUAL TAG-ONCE**: a human clicks each player once at match start, ReID maintains that identity across the match. So this session is about pure ReID identity-STABILITY (keeping the same player labeled consistently), NOT number-reading. Tag-once + stable ReID = named reels at DPS.

**Why measure-first:** a per-player reel is only trustworthy if identity is stable across the match. Current tracking is AssA~0.50 (Day-8/9) — players ID-switch on occlusion. A reel built on that could stitch DIFFERENT players' moments under one identity — worse than wrong analytics because it's personal and obviously wrong to the player. ReID (the deferred Day-9 BoT-SORT appearance arm) is the fix. This session MEASURES the lift; reels get built next ONLY if the lift makes identity trustworthy.

---

## The decision gate (what this session is FOR)
Run the Day-9 tuned tracker WITH ReID vs WITHOUT (the existing baseline), same TrackEval harness, same SoccerNet seqs. The numbers that matter for reels:
- **AssA** (association accuracy — the direct identity-stability measure)
- **IDF1** (identity consistency)
- **ID-switches** (raw churn — how often a player's identity flips)
- HOTA (overall)
**Verdict rule:** if ReID lifts AssA/IDF1 substantially (e.g. AssA 0.50 → 0.75+, ID-switches down hard), per-player reels are VIABLE → build them next. If the lift is marginal (AssA → ~0.6), reels are NOT yet trustworthy → document, and reels wait for a better identity solution (or DPS-footage tuning / tag-once-assisted correction).

---

## PART 0 — Confirm baseline + ReID availability (~30 min)
1. Reproduce the Day-9 tuned-tracker baseline on the SoccerNet subset via the cached pipeline (the Day-9 trust gate: cached-default must reproduce the known HOTA ~0.598 / AssA ~0.50). If it doesn't reproduce, fix before measuring.
2. Confirm the ReID path: BoT-SORT supports an appearance arm (with_reid=True) + a ReID weight/model. Check what's available (Ultralytics BoT-SORT ReID, or a lightweight ReID backbone). Note the model + whether it runs on the 4060.

**STOP. Report: Day-9 baseline reproduced (trust gate)? ReID arm available + which model?**

---

## PART A — Run tracker WITH ReID (~70 min)
1. Enable BoT-SORT appearance ReID (with_reid=True) on top of the Day-9 production config (keep GMC, the tuned thresholds — change ONLY the ReID arm, so the measured delta is purely ReID).
2. Run on the SoccerNet subset. NOTE: ReID extracts appearance features per detection (GPU step) → heavier than the cached-detection sweep; process seq-by-seq, watch for the TDR/OOM issues from earlier days. (Can't fully use the detection cache since ReID needs the crops — but reuse cached DETECTIONS for boxes, extract appearance on those boxes.)
3. Output tracker results in MOTChallenge format → TrackEval.

**STOP. Report: ReID run completed? any GPU/perf issues? results produced?**

---

## PART B — Measure the lift via TrackEval (~40 min)
1. TrackEval both configs vs GT tracklets. Report the comparison:
   | Metric | Day-9 (no ReID) | Day-26 (+ReID) | Δ |
   |---|---|---|---|
   | HOTA | ~0.598 | ? | ? |
   | AssA | ~0.50 | ? | ? |
   | IDF1 | ? | ? | ? |
   | ID-switches | ? | ? | ? |
2. **The reel-viability read:** is AssA/IDF1 up substantially and ID-switches down hard? Per-player identity now trustworthy enough to hand a player their reel?
3. Honesty: GT-validated here (SoccerNet has tracklets) — so this is a REAL measurement, the trust gate intact. (Contrast basketball later, which has no tracklet GT → plausibility.)

**STOP. Report the comparison table + the reel-viability verdict.**

---

## PART C — If viable: prototype tag-once identity (~40 min, conditional)
**If the ReID lift makes identity trustworthy:**
1. Prototype the DPS identity path: simulate "tag-once" — assign a name/label to each GT track at frame 1, let ReID-tracking propagate it, measure how long identities survive correctly (i.e. how often a tagged player keeps their tag across the clip).
2. This previews the DPS workflow (human tags once → reel follows the right person) and quantifies tag-survival, the real-world reel-reliability number.

**If NOT viable:** skip; document that reels need a stronger identity solution before building (options: stronger ReID model, DPS-footage tuning, or tag-once WITH periodic human re-correction).

**STOP. Report: tag-survival rate (if viable) OR the honest not-yet verdict + options.**

---

## PART D — Log + decision + commit (~30 min)
notes.md `## Day 26`: the measure-first rationale, the with/without-ReID TrackEval comparison, the reel-viability verdict, tag-once prototype result (if run), and:
- DECISION: per-player reels viable now (→ build next session) or not (→ what's needed first).
- DPS identity path = manual tag-once (no reliable jersey numbers); this measured pure ReID stability that tag-once depends on.
- The deferred-since-Day-9 ReID arm is now measured — close that open loop.
- DPS caveats: ReID appearance features may be less discriminative on similar-kit DPS teams (same similar-kit risk as team assignment); GT-validated on SoccerNet, DPS-pending.
- Note: ReID also helps per-player ANALYTICS (the Day-10 per-player distance that was caveated for ID-switches) — a bonus beyond reels.
gitignore (ReID weights, results); commit scripts + notes:
`git commit -m "Day 26: ReID identity-stability measurement (BoT-SORT appearance arm) vs Day-9 baseline; reel-viability gate for output #2"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Day-9 baseline reproduced (trust gate)? ReID model used?
3. GPU/perf issues with the ReID arm?
4. The comparison table: HOTA/AssA/IDF1/ID-switches, no-ReID vs +ReID
5. REEL-VIABILITY VERDICT: is identity stable enough to build per-player reels?
6. Tag-once prototype: tag-survival rate (if viable)?
7. Errors + time

---

## Do NOT today
- Do NOT build the full reel pipeline yet — MEASURE first; reels only if the lift justifies (the gate).
- Do NOT change anything but the ReID arm — keep the Day-9 config fixed so the measured delta is purely ReID.
- Do NOT trust the comparison until the Day-9 baseline reproduces via the cached pipeline (the trust gate).
- Do NOT plan for jersey-number OCR — DPS has no reliable numbers; identity = manual tag-once.
- Do NOT do basketball (no tracklet GT → plausibility, comes after) or build reels this session.
- Do NOT commit ReID weights / oversized results.
