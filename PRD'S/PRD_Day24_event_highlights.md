# PRD — Day 24: Event Detection + Highlight Clipping (output #3) — Football
**Project:** AI Sports Recording & Analytics System — for DPS MIS Doha
**Goal:** Build the third DPS output: auto-detect candidate exciting moments from motion (shots, fast transitions, likely-goal candidates, tackle-proxy, play-stoppages) and clip them from the A-feed for a human-curated highlight reel. HIGH-RECALL (catch all, human discards). Validate shot-detection against SoccerNet event labels if they exist, else perceptual. Football, SoccerNet (proxy for DPS).
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; football ball track (Day-12, RMSE-validated), player tracks (Day-9), team assignment (Day-11), homography (Day-10), follow-cam A-feed (Day-13)

---

## PROJECT GOAL CONTEXT (DPS-aware — read first)
Deployable system for DPS MIS Doha: fixed dual-phone wide capture → ONE shared pipeline → THREE outputs: (1) coach analytics [DONE both sports], (2) per-player highlights [needs ReID, later], (3) **EVENT HIGHLIGHT REELS [THIS] for Student Council / school Instagram**. Proxies build/validate the METHOD; real target is DPS courts/teams/kits/lighting/camera. Every threshold here is camera-scale-dependent → will need re-tuning at DPS's actual mount; flag it.

**DPS use = Student Council posts a highlight reel.** A human curates before posting → HIGH RECALL is right (a missed goal is gone forever; a false positive is a 2s skip the editor discards). Tune for catch-everything, human-filters.

---

## Honest event tiers (what motion CAN and CANNOT do)

**Tier 1 — solid, motion-kinematic (your data directly encodes these):**
- **Shots:** ball acceleration spike + trajectory toward a goal region.
- **Fast transitions / counterattacks:** rapid sustained up-pitch ball movement.

**Tier 2 — detectable as honest PROXIES (caveat clearly):**
- **Likely-goal candidates:** shot toward goal → ball stops/disappears near goal area → play restarts. An INFERENCE (no goal-line/net detection), so it also catches near-misses/saves. Frame as "likely-goal candidate," NOT "goal detected."
- **Tackle-proxy:** two OPPOSING-team players (Day-11 teams) converge on the ball + possession flips. Noisy proxy.
- **Play-stoppage proxy:** ball goes dead + players cluster + motion halts. Correlates with fouls/throw-ins/injuries/subs → label "stoppage (review)", NEVER "foul." This is the motion-half of a future foul detector that AUDIO (whistle) completes.

**Tier 3 — NOT honestly detectable from motion (do NOT build/claim):**
- **Fouls** — a referee judgment, no kinematic signature separates foul from fair challenge. Deferred to the AUDIO session (whistle detection + the stoppage proxy = real foul candidates).
- **Skill moves** — research-level pose/ball-control; out of scope.

**Planned next lever (note, don't build today): AUDIO.** DPS phones record audio; a whistle detector (fouls/stoppages) + crowd-roar spikes (goal confirmation) are the honest path to fouls + goal-confirmation. Today is motion-only; audio is the documented next unlock.

---

## PART 0 — Check SoccerNet for event labels (validation path) (~20 min)
SoccerNet has an Action-Spotting lineage (goals/shots/etc. with timestamps). Check: do the SoccerNet clips we use (SN-GSR / the seqs on disk) have, or map to, event-timestamp labels (shots/goals)?
- YES → validate shot/goal-candidate detection against real event timestamps (precision/recall, the trust gate).
- NO → perceptual validation (watch the clipped moments; judge exciting/missed).

**STOP. Report: event labels available? → validation path.**

---

## PART A — Compute motion features for event detection (~50 min)
From existing tracks (reuse Day-9/10/12; do NOT re-run detection/tracking):
1. Ball kinematics: speed, acceleration, direction (pitch-space via Day-10 homography AND pixel-space; use the >10 m/s teleport guard from Day-20 so ID/track noise doesn't fake events).
2. Ball-toward-goal: distance/heading of ball relative to each goal region (define goal regions in pitch coords).
3. Possession state over time (Day-11 teams + nearest-player-to-ball, the Day-12 proxy) → detect possession FLIPS.
4. Player convergence: count opposing-team players near the ball (for tackle-proxy).
5. Motion-halt: frames where ball speed ~0 + players cluster (for stoppage proxy).

**STOP. Report: features computed + plausibility-checked (do speed/accel spikes line up with visually exciting moments on a quick check)?**

---

## PART B — Event detectors, HIGH-RECALL (~60 min)
Each detector emits candidate (start,end,type,confidence). Tune for recall (catch-all):
1. **Shot:** ball accel spike above threshold + heading toward goal region. Low threshold (recall).
2. **Fast transition:** sustained high ball up-pitch velocity over N frames.
3. **Likely-goal candidate:** shot toward goal + subsequent ball-near-goal-then-dead / restart signature. Mark candidate, low confidence by design.
4. **Tackle-proxy:** opposing players converge on ball + possession flip.
5. **Stoppage (review):** motion-halt + cluster. Labeled "stoppage", never "foul."
Each event → a clip window (event time ± padding, e.g. -3s/+2s). Merge overlapping windows.

**STOP. Report: how many candidates per type? does high-recall produce a sensible candidate count (not thousands, not zero)?**

---

## PART C — Clip from the A-feed + validate (~50 min)
1. For each candidate window, cut the clip from the A-feed (Day-13 ball-faithful follow-cam — the right feed for ball-centric events). Tag each clip with its type + confidence + timestamp.
2. **Validation (per Part-0 path):**
   - If SoccerNet event labels: precision/recall of shot/goal-candidate detection vs the real timestamps. Report recall especially (the high-recall goal). The trust-gate-adjacent number.
   - Perceptual (always): WATCH a sample of clipped moments. Are they actually exciting? Did it miss obvious ones (recall by eye)? Are false positives tolerable for a human curator?
3. Honest framing check: are types labeled accurately ("likely-goal candidate", "stoppage (review)" — not overclaimed)?

**STOP. Report: validation numbers (if labels) + perceptual verdict; are the clips genuinely a useful candidate set for a StuCo editor?**

---

## PART D — Package as a curation-ready output + log + commit (~40 min)
1. Produce a "highlight candidate" package: the clips + a simple index (timestamp, type, confidence) a human can skim and pick from — the StuCo curation workflow. Optionally auto-assemble a rough reel (concatenate top-confidence clips) as a demo, clearly marked "auto-draft, human-curate."
2. notes.md `## Day 24`: the event tiers (what's solid/proxy/deferred), the high-recall design + WHY (StuCo curation), validation (labels or perceptual), honest type labeling, the AUDIO-next-lever note (fouls/goal-confirmation), and DPS caveats (thresholds camera-scale-dependent → re-tune at DPS; proxy footage; human-in-the-loop curation is the intended workflow).
3. gitignore (clips/video size); commit scripts + notes + sample candidate clips/index:
   `git commit -m "Day 24: event detection + highlight clipping (output #3, football); high-recall candidate moments; honest tiers; audio noted as fouls/goal lever"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. SoccerNet event labels available? validation path?
3. Features computed + line up with exciting moments?
4. Candidate counts per type — sensible under high-recall?
5. Validation: shot/goal-candidate precision/recall (if labels) + perceptual verdict
6. Are clips a genuinely useful candidate set for a StuCo editor? honest type labels?
7. Errors hit (even if fixed)
8. Time taken

---

## Do NOT today
- Do NOT claim "goal detection" — it's "likely-goal candidate" (no goal-line/net detection).
- Do NOT claim "foul detection" — fouls aren't motion-detectable; build only a "stoppage (review)" proxy, defer real fouls to the audio session.
- Do NOT build skill-move detection — out of scope.
- Do NOT tune for precision over recall — StuCo curates; catch-all + human-filter is the design.
- Do NOT forget the >10 m/s teleport guard — ID/track noise will fake ball-accel events otherwise.
- Do NOT re-run detection/tracking — reuse Day-9/10/11/12.
- Do NOT do basketball (next) or player highlights (needs ReID, later).
- Do NOT commit oversized video.
