# PRD — Day 15: Basketball Follow-Cam (A/B/C + possession-handoff) — parity with football Day-13
**Project:** AI Sports Recording & Analytics System
**Goal:** Build basketball follow-cam (the Day-13 equivalent), bringing basketball to full follow-cam parity. Reuse the A/B/C virtual-camera architecture, basketball-tuned, and add the possession-handoff fallback to the A-feed so it survives held-ball occlusion. Test whether the handoff removes the need for TrackNet. Perceptual eval, with close scrutiny of the held-ball moments. Basketball, SportsMOT.
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; Day-14 basketball ball track (`outputs/ball_track_bb/<seq>/trajectory.json`); Day-9 basketball player tracks; Day-13 follow-cam code (`scripts/follow_cam.py`) to adapt

---

## Context (read first)

Football reached follow-cam (Day 13) with A/B/C virtual-camera variants and the user's two-feed deliverable strategy:
- **A (ball-faithful)** → gameplay/event highlights (shots, aerial passes — ball is the story)
- **C (player-stabilized)** → player highlights + celebrations (person is the story)
Kept as DISTINCT feeds; downstream deliverable picks which it consumes. Same strategy applies to basketball.

Day 14 gave basketball a ball track (pixel Kalman, plausibility-validated). User's video review found it tracks well on dribbles/passes/shots but DROPS on held/occluded ball (hands hide it). Rather than escalate to TrackNet immediately, we test the user's cheaper idea: **possession-handoff** — when the ball is held/lost, follow the player who last held it (a held ball IS at that player). This reuses the Day-12/14 possession logic (nearest player to last confident ball). If the handoff makes held-ball moments watchable in the A-feed → TrackNet unneeded. If not → TrackNet justified with evidence (the pre-set escalation trigger).

**Scope: BASKETBALL follow-cam.** Builds the tracked-views that feed basketball highlights/reels later.

---

## The variant + handoff design (how it maps to deliverables)

- **A — ball-faithful + possession-handoff (the key new piece):** target follows the ball when confidently detected; when the ball is held/lost, fall back to the LAST-POSSESSING player (nearest player to the last confident ball detection) until the ball reappears; only after a long no-holder gap fall back to team centroid. This is the gameplay/event-highlight feed, now robust through occlusion. THE hypothesis under test.
- **B — ball+player blend (intermediate, for comparison):** the Day-13 confidence-weighted blend.
- **C — player-stabilized:** player-centroid-led, heavily smoothed — the player-highlight/celebration feed. Largely unaffected by ball dropouts by design (doesn't need the handoff).
- Keep all three as DISTINCT outputs (don't merge), mapped to deliverables as in football.

---

## Basketball-specific tuning (vs football Day-13)
- **Tighter crop, faster pace:** basketball court is smaller and play reverses fast → crop ratio and pan limits need re-tuning (likely tighter crop, higher allowed pan velocity). Start from Day-13 constants, adjust by eye.
- **Aspect:** SportsMOT basketball is 1280×720; pick a sensible 16:9 (or tighter) crop window.
- **Bidirectional lookahead smoothing:** same as football (offline advantage, zero phase lag) — the dominant smoothness factor. Keep it.
- **Asymmetric pan limits + dead-zone:** same braking-distance velocity cap as the fixed Day-13 limiter (the one that fixed the oscillation). Reuse the FIXED version, not the buggy first one.

---

## PART A — A-feed: ball-faithful + possession-handoff (~70 min)
1. Load Day-14 ball track (per-frame pixel pos + status {detected|predicted|lost} + shot_flag) and Day-9 player tracks.
2. **Possession-handoff target logic:**
   - ball status detected (or short-gap predicted) → target = ball pos.
   - ball lost AND a recent last-holder known → target = that player's track position. Last-holder = nearest player to the last CONFIDENT ball detection (reuse possession proximity logic); persist the holder ID until the ball reappears or the holder track ends.
   - ball lost long / no holder → target = team centroid (trimmed mean, as Day-13).
3. Bidirectional-smooth the resulting target path; asymmetric-limit + dead-zone (the FIXED braking-distance limiter); clamp to frame.
4. Render the A-feed. WATCH the held-ball moments specifically.

**STOP. Report: does the A-feed track ball on dribbles/passes/shots AND stay sensibly on the holder during held-ball dropouts (not swing to nowhere)? Is the handoff visible/clean?**

---

## PART B — B-feed: ball+player blend (~30 min)
Reuse Day-13's confidence-weighted blend (`target = w·ball + (1-w)·player_centroid`), basketball-tuned. Render. (Comparison variant.)

**STOP. Report: B watchable? how it differs from A.**

---

## PART C — C-feed: player-stabilized (~30 min)
Player-centroid-led, heavily smoothed (the celebration/player-highlight feed). Render.

**STOP. Report: C stable/watchable for player-highlight use?**

---

## PART D — Perceptual eval + the TrackNet decision (~40 min)
1. A/B/C montage + the Day-13 proxy metrics (crop-center jerk, action-in-frame %, edge-clamp %) as SUPPORTING evidence.
2. **Watch with specific scrutiny on held-ball moments in the A-feed** (the hypothesis): does the possession-handoff make them watchable?
3. **THE DECISION:** does the A-feed (with handoff) work well enough to feed gameplay highlights?
   - YES → TrackNet NOT needed; basketball follow-cam done; both sports at parity.
   - NO (handoff insufficient, still loses the play through occlusion) → TrackNet is now justified WITH EVIDENCE; document exactly what failed (which occlusion cases the handoff couldn't save) as the spec for a TrackNet session.

**STOP. Report the perceptual verdict + the TrackNet decision (needed or not, with evidence).**

---

## PART E — Render finals, log, commit (~30 min)
1. Render 1-2 full sample seqs of the A-feed (with handoff) and C-feed.
2. notes.md `## Day 15`: basketball A/B/C + handoff design, basketball-specific tuning vs football + why, the held-ball-handoff result (the hypothesis outcome), perceptual verdict per feed, proxy metrics, THE TrackNet decision (needed/not + evidence), and:
   - Parity status: basketball now has A + C feeds → maps to gameplay highlights (A) + player highlights (C), same as football.
   - Honest caveats: still SoccerNet/SportsMOT footage; plausibility-validated ball upstream (Day-14); crop constants camera-distance dependent (school re-tune).
3. gitignore checks (datasets/weights/videos); commit scripts + notes + sample frames/short clip:
   `git commit -m "Day 15: basketball follow-cam (A/B/C + possession-handoff); held-ball occlusion fix; TrackNet decision"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. A-feed: tracks ball on dribbles/passes/shots? handoff clean on held-ball dropouts?
3. B and C feeds watchable? C good for player-highlight use?
4. Proxy metrics (jerk, action-in-frame, edge-clamp) A/B/C
5. HELD-BALL HANDOFF VERDICT: did it solve the dropout the user saw?
6. TRACKNET DECISION: needed or not? if needed, what exactly did the handoff fail to save?
7. Parity check: basketball A+C feeds ready for highlights, like football?
8. Errors hit (even if fixed)
9. Time taken

---

## Do NOT today
- Do NOT merge A and C into one hybrid — keep distinct feeds (A→gameplay highlights, C→player highlights), per the deliverable strategy.
- Do NOT apply the possession-handoff to C (it's player-stabilized already; handoff is an A-feed fix).
- Do NOT reuse the buggy Day-13 oscillating limiter — use the FIXED braking-distance version.
- Do NOT jump to TrackNet before testing the handoff — that's the whole point of this session (test cheap fix first).
- Do NOT reuse football's crop ratio / pan limits blindly — basketball is tighter/faster, re-tune by eye.
- Do NOT do football or build highlights/reels yet (these feeds feed them next).
- Do NOT commit datasets/weights/videos.