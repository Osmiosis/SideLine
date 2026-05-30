# PRD — Day 25: Basketball Event Detection + Highlight Clipping (output #3 parity)
**Project:** AI Sports Recording & Analytics System — for DPS MIS Doha
**Goal:** Bring output #3 (event highlights) to basketball parity. Reuse the Day-24 architecture, basketball-tuned: high-recall capture of shot attempts + notable plays, RANKED by interest (made-baskets/fast-breaks top, routine misses bottom) so the StuCo editor isn't flooded. Build 'likely made basket' detection (hoop location from Day-21 homography). Validate vs SportsMOT sparse labels if any + perceptual (USER judges the clips). Basketball, SportsMOT (proxy for DPS).
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; basketball ball track (Day-19, head-FP-cleaned), player tracks (Day-9), team assignment (Day-23 embeddings), homography (Day-21), basketball follow-cam A-feed (Day-15/16); Day-24 `detect_events.py` + `clip_highlights.py` to adapt

---

## PROJECT GOAL CONTEXT (DPS-aware — read first)
Deployable system for DPS MIS Doha: fixed dual-phone capture → ONE pipeline → THREE outputs: (1) coach analytics [DONE both sports], (2) per-player highlights [needs ReID, later], (3) **event highlight reels** [football DONE Day-24, THIS = basketball half]. For Student Council / school Instagram. Proxies build/validate the METHOD; real target is DPS courts/teams/kits/lighting/mount. Thresholds are camera-scale-dependent → re-tune at DPS. Human-in-the-loop curation is the intended workflow.

---

## What transfers from Day-24 (reuse) vs what's basketball-different (rethink)

**Reuse (architecture proven on football):** motion-features → high-recall detectors → clip from A-feed → curation package (index + contact sheets + auto-draft reel). The Day-24 hard-won lessons ALL carry and matter MORE here:
- **Lost-ball discipline:** a lost ball is DEAD/UNKNOWN, never interpolated into fake velocity (Day-24 had 3 bugs from this). Basketball ball is occlusion-heavy (held-ball, Day-14/15) → MORE gaps → this discipline is even more critical.
- **Shot = ball-launch-into-gap, not speed-peak:** Day-24's key fix — anchor a shot clip to the LAUNCH (last detected frame before the ball vanishes), not the late speed peak (which clips the aftermath). Basketball shots also launch the ball fast/aerial → same anchoring.
- **Teleport guards, peak-proximity clustering, pre-roll padding.**

**Basketball-different (rethink):**
1. **Shot-DENSE, not sparse.** A shot every ~20s → high-recall could yield 100+ candidates/match. So: high-recall CAPTURE + **interest RANKING** (made-baskets/fast-breaks/blocks top, routine midcourt misses bottom). The editor skims ranked, catches everything, isn't drowned. (User chose high-recall; ranking is how we keep it usable.)
2. **'Likely made basket' is MORE detectable than football's goal.** Ball descends through a KNOWN hoop zone (hoop location from Day-21 homography) + immediate possession/direction reversal to the other end. Strong signal → a good candidate (still not certainty; ball-track is plausibility-level). Powers the ranking (made > attempt).
3. **Different event vocabulary:** shot attempt, likely-made-basket, fast-break (rapid full-court ball movement + players streaming one direction), steal-proxy (possession flip in open court), block-proxy (shot attempt + ball trajectory reversal near rim). Tier them honestly like Day-24.
4. **Ball track plausibility-level + occlusion-heavy** → expect noisier events than football; lean on the lost-ball discipline + ranking to keep the top of the list clean.

---

## PART 0 — Hoop locations + SportsMOT event labels (~30 min)
1. **Hoop zones:** from the Day-21 court homography, define the two hoop locations in court coords (standard positions) → project to pixels. Needed for made-basket + block detection. (DPS note: at deployment, hoop positions come from the manual court-marking — a setup dependency football didn't have.)
2. **Labels:** does SportsMOT (or the clips on disk) carry ANY event/action labels? Likely NOT (SportsMOT is tracking-only). If none → perceptual-only validation (expected). If some → use as sparse recall anchors like Day-24.

**STOP. Report: hoop zones defined + projected sanely? any SportsMOT event labels (validation path)?**

---

## PART A — Basketball motion features (~50 min)
Reuse Day-24 feature pipeline on basketball tracks (Day-9 players / Day-19 ball / Day-23 teams / Day-21 homography). Compute:
1. Ball kinematics (pixel + court-meters via homography), with the lost-ball = DEAD discipline (no interpolation across gaps; speed zeroed/flagged where ball missing).
2. Ball-relative-to-hoop: distance + descent through each hoop zone.
3. Possession + flips (Day-23 teams + nearest-player); open-court flips (for steals).
4. Direction-reversal at the court level (for fast-breaks + made-basket confirmation).
5. Player streaming/convergence (fast-break = players one-direction; block = convergence at rim).
Plausibility-check features line up with visually active moments.

**STOP. Report: features computed + plausibility-checked? lost-ball handled (no fabricated velocity)?**

---

## PART B — Detectors (high-recall) + interest ranking (~70 min)
Detectors (each → candidate start/end/type/confidence), tuned high-recall:
1. **Shot attempt:** ball launch toward a hoop zone (launch = last detected before gap, the Day-24 anchor).
2. **Likely made basket:** ball descends through hoop zone + possession/direction reversal. Higher interest.
3. **Fast break:** sustained rapid full-court ball + players streaming one way. High interest.
4. **Steal-proxy:** open-court possession flip (not a normal halfcourt change). Medium.
5. **Block-proxy:** shot attempt + ball reversal near the rim. Medium-high.
Then **INTEREST RANKING:** score each candidate (made-basket > fast-break/block > shot attempt > routine) so the curation index is SORTED best-first. This is how high-recall stays usable on shot-dense basketball.

**STOP. Report: candidate counts per type? does ranking float the genuinely exciting plays to the top? total count sane for a curator (ranked, so volume is OK)?**

---

## PART C — Clip from A-feed + package (~40 min)
1. Clip each candidate from the basketball A-feed (Day-15/16 ball-faithful, head-FP-cleaned), launch-anchored for shots, pre-roll padded.
2. Build the curation package: **ranked** index (timestamp, type, confidence, interest-rank), contact sheets, marked auto-draft reel (top-N ranked).
3. Leave the PERCEPTUAL judging to the USER — surface the clips + contact sheets + index for the user to watch and verdict (do NOT self-declare quality; the user is the arbiter, as on every perceptual deliverable).

**STOP (for user): clips + contact sheets + ranked index ready for the user to watch.**

---

## PART D — Validate (user perceptual + any sparse labels) + log + commit (~40 min)
1. If any SportsMOT labels: report recall (did candidate windows cover labeled events?).
2. **USER perceptual verdict** (the primary precision judge): user watches the ranked clips — are the top-ranked ones genuinely exciting? Does ranking work (good stuff on top)? Are made-baskets correctly surfaced? Tolerable FPs for a curator? (Claude Code surfaces; user judges.)
3. notes.md `## Day 25`: basketball event tiers, the shot-dense→ranking design, made-basket detection (hoop from homography), reused Day-24 lessons (lost-ball, launch-anchor), validation (sparse + user-perceptual), AUDIO-next-lever (whistle/crowd for fouls + made-basket confirmation — same as football), DPS caveats (thresholds + hoop-marking setup dependency + plausibility-level ball).
4. gitignore (clips/video); commit scripts + notes + basketball event package:
   `git commit -m "Day 25: basketball event detection + ranked highlight clipping (output #3 parity); made-basket via hoop homography; high-recall+ranked"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Hoop zones defined OK? any SportsMOT event labels?
3. Features computed + lost-ball handled?
4. Candidate counts per type; does interest-ranking float exciting plays to the top?
5. USER perceptual verdict: top-ranked clips genuinely exciting? made-baskets surfaced? ranking usable? (user judges)
6. Recall vs any sparse labels
7. Is this a usable ranked candidate set for a StuCo editor on shot-dense basketball?
8. Errors + time

---

## Do NOT today
- Do NOT interpolate the lost ball into fake velocity — DEAD/unknown (the Day-24 3-bug root cause; worse on occlusion-heavy basketball).
- Do NOT anchor shot clips to the speed peak — anchor to the LAUNCH (last detected before gap), or you clip the aftermath (Day-24 lesson).
- Do NOT ship unranked high-recall on shot-dense basketball — RANK it, or the editor drowns.
- Do NOT call 'likely made basket' a confirmed score, or proxies (steal/block) certainties — honest labels.
- Do NOT self-declare perceptual quality — surface clips, USER judges (the arbiter on perceptual deliverables).
- Do NOT claim foul detection — same as football, that's the audio lever (note it).
- Do NOT re-run detection/tracking — reuse Day-9/19/21/23.
- Do NOT do player highlights (needs ReID) or football.
- Do NOT commit oversized video.
