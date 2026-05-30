# PRD — Day 30: Attack Track Fragmentation (appearance-free re-linking) — ZXY-validated — Football
**Project:** AI Sports Recording & Analytics System — for DPS MIS Doha
**Goal:** Reduce the 232× track fragmentation the Day-29 full-match test exposed (5,106 IDs for ~22 players, median track life 1.3s) using APPEARANCE-FREE methods only (motion/position re-linking + track-buffer tuning — right for identical DPS house kits). Measure-first: diagnose WHY tracks break + build a REAL identity-stability metric against ZXY ground truth, then fix the biggest cause and measure the lift. Football, Alfheim full-match (Day-29 stitched half + ZXY GT).
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; Day-29 stitched `first_half.mp4` + MOT tracking output + ZXY GT CSVs + `track_alfheim.py` / `alfheim_trust_gate.py` / `alfheim_scale_findings.py`

---

## PROJECT GOAL CONTEXT (DPS-aware — read first)
Deployable system for DPS MIS Doha (fixed dual-phone capture → ONE pipeline → 3 outputs). All 3 outputs exist for both sports; the Day-29 full-match scale-test on FIXED-camera footage (best DPS proxy yet) found the real DPS blocker: **identity stability over 45 min** — raw tracking fragments 232×. Memory + fixed-homography already held. This session attacks fragmentation.

**The reframe (critical — sets the realistic target):** the deployable per-player identity path is ALREADY decided = human tag-per-clip, because identical house kits (Rose=red/Lily=yellow, no numbers/names) make AUTO-identity fundamentally impossible (Day-26 ReID proved it: AssA +0.004). So this session is NOT "make auto-identity perfect" (unreachable). It's: **reduce fragmentation enough that (a) the human tagging burden is viable, and (b) team/aggregate analytics become trustworthy** — WITHOUT appearance (which fails on identical kits).

**Honest ceiling (frame the result this way):** appearance-free re-linking can plausibly cut 5,106 → a few hundred (most fragments are the same players, motion-rejoinable). It will NOT reach ~22 — when two identical-kit players cross/occlude, NO appearance-free method always recovers who's who (and appearance won't help on house kits). So "few hundred clean long tracks" = SUCCESS; "didn't reach 22" = EXPECTED, not failure.

---

## PART A — Build a REAL identity metric vs ZXY (measure-first foundation) (~60 min)
Raw ID count (5,106) is a proxy; build a GROUND-TRUTH identity-stability metric:
1. Align tracker output to ZXY GT in space+time (Day-29 established the ZXY-refined homography + the 30fps time-sync — REUSE it; the framerate sync was a Day-29 catch, don't re-break it).
2. For each frame, match tracked players to ZXY players (Hungarian on pitch-position distance). Compute identity-stability metrics: **IDF1 / AssA-style** (how consistently one tracked ID maps to one ZXY player), ID-switches vs GT, and fragmentation (tracked IDs per GT player). This is the REAL metric — improvement gets measured against THIS, not raw ID count.
3. Caveat: ZXY = home team only (~11 players), positions @ ~16Hz; so the metric is home-team identity stability. Honest, still a real GT metric.

**STOP. Report: ZXY-grounded identity metric built? baseline IDF1/AssA + IDs-per-GT-player (the real fragmentation number vs the raw 5,106)?**

---

## PART B — Diagnose WHY tracks break (before fixing) (~50 min)
Don't fix blind — find the dominant break cause:
1. For a sample of track terminations, classify WHY a track dies + a new one spawns: (a) OCCLUSION (players cross/overlap), (b) DETECTION FLICKER (detector misses a frame → track drops), (c) FAST MOTION (association gate too tight), (d) EDGE (player leaves/re-enters view), (e) stride-2 sampling gaps.
2. Quantify the mix: what % of breaks is each cause? (The fix differs per cause — buffer/re-link for occlusion+flicker, association tuning for fast motion.)
3. Cross-check with ZXY: at break moments, were two players actually close (occlusion) per the GT positions?

**STOP. Report: break-cause breakdown? dominant cause(s)? (this picks the fix)**

---

## PART C — Appearance-free fixes, measured each (~70 min)
Apply the fixes matched to the dominant cause(s), APPEARANCE-FREE only, measure each vs the Part-A metric:
1. **Track-buffer tuning:** increase how long a lost track is kept alive for re-association (a briefly-occluded/flickering player keeps their ID instead of spawning new). The key knob; cheap to sweep. (Re-tune for Alfheim 30fps/stride-2, not the SoccerNet-30s Day-9 values.)
2. **Offline gap re-linking (the big lever):** post-hoc, stitch a terminated track to a new track that appears nearby shortly after with consistent position/velocity (motion continuity, NO appearance). Offline = can do bidirectional/global linking a live tracker can't. Tune the gap/distance/velocity-consistency thresholds.
3. **Detection-flicker smoothing (if Part B says flicker):** bridge 1-2 frame detection gaps so tracks don't drop on a single missed detection.
4. Measure each fix's effect on IDF1/AssA + IDs-per-GT-player. Keep what helps; watch for OVER-linking (stitching two DIFFERENT players into one track — the failure mode; check against ZXY that re-links join the SAME GT player).

**STOP. Report: each fix's effect on the ZXY identity metric? fragmentation reduced from 5,106 → ? over-linking checked against GT?**

---

## PART D — Re-validate analytics + log + commit (~40 min)
1. With reduced fragmentation, RE-RUN the Day-29 analytics trust gate: does the intensity/distance magnitude move closer to ZXY GT now that identity is more stable? (Day-29 was ~2× inflated, partly from ID-fragmentation — does fixing identity help?)
2. notes.md `## Day 30`: the ZXY identity metric (baseline + after), the break-cause diagnosis, each appearance-free fix + its measured lift, the fragmentation reduction (5,106 → ?), the honest ceiling note (didn't/can't reach 22, and WHY — identical kits), whether analytics magnitude improved, and:
   - DPS read: how much does this lower the human tag-per-clip burden? are team/aggregate analytics GT-trustworthy now?
   - Appearance-free was the right call for identical kits (no appearance dependency anywhere).
   - Honest caveats: ZXY = home-team-only metric; still a proxy; over-link risk monitored.
3. gitignore (Alfheim data stays local); commit scripts + notes + metric outputs:
   `git commit -m "Day 30: appearance-free track de-fragmentation (buffer + offline re-linking); ZXY-validated identity metric; 5106 IDs -> N"`; (push per your workflow).

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. ZXY identity metric built? baseline IDF1/AssA + IDs-per-GT-player?
3. Break-cause breakdown — dominant cause?
4. Each appearance-free fix's effect on the metric
5. Fragmentation: 5,106 → ? (and the honest "not 22 because identical-kit crossings" framing)
6. Over-linking checked against GT (no merging different players)?
7. Did reduced fragmentation improve the analytics magnitude vs ZXY?
8. DPS read: tagging burden lowered? aggregate analytics trustworthy now?
9. Errors + time

---

## Do NOT today
- Do NOT use appearance/ReID for re-linking — identical house kits make it fail (Day-23/26); appearance-free motion/position only.
- Do NOT chase "22 IDs" — identical-kit crossings are unrecoverable appearance-free; "few hundred clean tracks for the tag-per-clip layer" is success.
- Do NOT fix before diagnosing (Part B) — the fix depends on the dominant break cause.
- Do NOT over-link — stitching two DIFFERENT players into one ID corrupts identity worse; verify re-links join the SAME ZXY player.
- Do NOT re-break the Day-29 30fps ZXY time-sync — reuse it.
- Do NOT measure success by raw ID count alone — the ZXY-grounded IDF1/AssA is the real metric.
- Do NOT re-run detection from scratch if the Day-29 MOT output is reusable (re-link post-hoc on it); re-track only if buffer-tuning requires it.
- Do NOT commit Alfheim data (license/size).
