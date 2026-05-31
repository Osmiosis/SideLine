# PRD ADDENDUM — Day 31: Ball-Track Probe-Then-Branch (supersedes Part B approach; adjusts Part C)
**Read alongside PRD_Day31_fullmatch_deliverables.md.** This addendum handles the blocker found at session start: **Alfheim is players-only (no ball track)** — Day-29 was player-tracking only. Event detection (Part B) needs a ball track; player involvement (Part C) partly does. Rather than blindly run a 1hr ball pass that may produce an unusable track on wide fixed-cam footage, PROBE first, then branch.

---

## The core discipline (why probe-first)
The soccana ball detector was validated on SoccerNet BROADCAST footage (ball relatively large). Alfheim is a WIDE FIXED ELEVATED single camera → the ball is TINY (few pixels, on grass, at distance). Ball recall may be POOR. If it is, a full 47-min pass (~1hr compute) produces a gappy track, and any event-density number built on it measures the DETECTOR'S FAILURE, not real event density — the metric-vs-reality trap. So: measure ball recall CHEAPLY before trusting any event number built on it. (Same "trust-gate before trusting numbers" discipline as the whole project.)

**Part C (player tagging volume) is the PRIORITY and is delivered FULLY regardless** — it has the presence fallback that needs NO ball, so it degrades gracefully.

---

## PART B-probe — Ball-recall probe on a short window (~30 min) [REPLACES blind Part B]
1. Run soccana ball detection on a SHORT Alfheim window (~3-5 min) only. Adapt `analyze_ball` to the fixed homography if needed for the probe (minimal).
2. **WATCH/measure the result** (perceptual + rough recall): what fraction of frames get a plausible ball detection? Is the track usable (continuous-ish) or full of holes? Spot-check a few detections sit on the actual ball (not lines/heads/noise — the wide-cam version of the head-FP risk).
3. **DECISION GATE:**
   - **Recall DECENT** (track usable) → the full 47-min pass is justified → proceed to PART B-full.
   - **Recall POOR** (gappy/unusable) → STOP the ball work. Write Part B up as **evidence-backed blocked**: report the MEASURED recall, conclude event detection isn't viable on wide fixed-cam without a ball-detection improvement, and note this is a REAL DPS FINDING (DPS wide capture would hit the same wall → ball detection on wide fixed cameras is a known gap needing work, e.g. a wide-cam-tuned ball detector or higher-res capture). No full pass.

**STOP. Report: ball recall on the probe window? usable or poor? GATE decision: full pass or evidence-backed blocked?**

---

## PART B-full — Full ball pass + event density (~60 min) [ONLY IF probe recall decent]
1. Run ball detection over the full half; adapt analyze_ball to the fixed H; build the ball track.
2. Run the Day-24 event pipeline (high-recall + ranking, lost-ball discipline, launch-anchor) → the real Part B numbers from the original PRD: candidate count over 45min per type, ranked-usability, top-candidate sanity check.

**STOP. Report the original Part B numbers (now with a real ball track) + caveat the wide-cam ball recall.**

---

## PART C — Player tagging volume — BALL-RESILIENT (the priority) (~70 min)
Deliver FULLY regardless of the Part B gate:
1. **Involvement** (nearest-player-to-ball) needs a ball signal. Use whatever ball track the probe/full-pass produced. **If ball recall is poor**, involvement clips will be sparse/unreliable → that's fine, LEAN ON PRESENCE.
2. **Presence fallback** needs NO ball — every substantial track gets its longest visible stretch. This carries the tagging-volume number even with no usable ball.
3. **THE NUMBER (priority deliverable):** total clips for a full match (involvement-where-available + presence), estimated human tagging time (clips × sec/tag), viable-or-prohibitive verdict. Report the involve/presence split (expect presence-heavy if ball recall poor — note it honestly).
4. Inclusivity at full scale + the fragmentation reality (191 IDs/player → pre-tag = track-level; tagging reconstitutes players; quantify the effort).

**STOP. Report: full-match clip count, tagging-time estimate, viable/prohibitive, involve/presence split (+ whether ball recall forced presence-heavy).**

---

## Logging note (folds into Part D)
notes.md `## Day 31`: ADD — the missing-ball-track blocker + the probe-then-branch handling; the MEASURED ball recall on wide fixed-cam (a real DPS finding either way); Part B result (real numbers OR evidence-backed blocked); Part C tagging-volume delivered fully + whether ball recall forced presence-reliance. The wide-cam ball-recall finding is DPS-relevant: it tells you whether your DPS wide capture will need a wide-tuned ball detector.

---

## Do NOT (addendum)
- Do NOT run the full 47-min ball pass before the probe says recall is decent (avoid the 1hr-for-an-unusable-track trap).
- Do NOT report an event-density number built on a gappy ball track as if it's real — if recall is poor, the honest output is "blocked + measured recall", not a fake density.
- Do NOT let a poor ball track block Part C — presence fallback carries it; the tagging-volume number is the priority and is ball-optional.
- Do NOT over-invest adapting analyze_ball for the probe — minimal adaptation; full adaptation only if the full pass is greenlit.
