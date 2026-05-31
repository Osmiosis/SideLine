# PRD — Day 31: Finish the Full-Match Scale Test — Events + Player Highlights at 45min (Football)
**Project:** AI Sports Recording & Analytics System — for DPS MIS Doha
**Goal:** Complete the full-match scale test deferred from Day-29: decouple the event-detection and player-highlight scripts from their SoccerNet-sequence coupling, run them on the Alfheim stitched full half, and get the TWO missing scale numbers — (1) event-candidate density over 45 min (does high-recall+ranking stay usable or flood?), (2) player-highlight TAGGING VOLUME over a full match (the deployment-viability number). Football, Alfheim full-match.
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; Day-29 stitched `first_half.mp4` + its MOT tracking output + fixed homography (1.78m) + Day-30 re-linked tracks (the safe −18% pre-pass); Day-24 `detect_events.py`/`clip_highlights.py`, Day-27 `detect_involvement.py`/`clip_player_highlights.py`/`assemble_player_reels.py` (SoccerNet-coupled — decouple them)

---

## PROJECT GOAL CONTEXT (DPS-aware — read first)
Deployable system for DPS MIS Doha (fixed dual-phone capture → ONE pipeline → 3 outputs). All 3 outputs exist for both sports on 30s clips. The Day-29 full-match test (Alfheim fixed single-cam, best DPS proxy yet) ran the FOUNDATION + analytics at full scale but DEFERRED events + player-highlights (their scripts were SoccerNet-sequence-coupled). This finishes that — getting all 3 deliverables tested at full-match scale = the honest completion of "all deliverables on a full game."

**Two findings from Day-29/30 that frame this:**
- Identity fragments structurally (Day-30: 191 IDs/player, appearance-free re-linking can't fix it → human tag-per-clip is MEASURED-necessary). So player highlights here RUN ON the fragmented/re-linked tracks via the tag-per-clip clipping design — the test is the TAGGING VOLUME this produces.
- Analytics magnitude is homography/single-cam-limited, NOT identity-limited (Day-30) — not this session's concern.

**The deliverable = the two scale NUMBERS, not polished reels:**
1. Event-candidate density over 45 min — is the ranked output usable for a StuCo curator, or a flood?
2. Player-highlight tagging volume — how many clips would a human tag for a full match? Minutes or hours? (Deployment-viability: if a full match = 3hrs of tagging, that changes the DPS workflow pitch.)

---

## PART A — Decouple the scripts from SoccerNet coupling (~50 min)
The event + player-highlight scripts assume SoccerNet-sequence structure (paths, frame indexing, clip naming). Decouple so they run on the Alfheim full half:
1. Identify the SoccerNet-specific assumptions (hardcoded seq paths, frame-rate assumptions — Alfheim is 30fps not 25, the Day-29 catch; sequence-length assumptions; GT-label coupling).
2. Refactor to take a generic input: a video + its MOT tracking output + homography + framerate, no SoccerNet structure. (This decoupling ALSO advances operator-app readiness — the app needs these to run on arbitrary footage, not hardcoded SoccerNet.)
3. Smoke-test on a short Alfheim window first (confirm they run decoupled before the full half).

**STOP. Report: scripts decoupled? smoke-test on a short Alfheim window works? what SoccerNet assumptions had to be removed?**

---

## PART B — Event detection at full-match scale (~60 min)
Run the Day-24 event pipeline (high-recall + interest ranking) on the full Alfheim half:
1. Use the fixed homography (goal regions in pitch coords) + the ball track + the Day-30 re-linked tracks. Lost-ball discipline + launch-anchor (Day-24 lessons) intact.
2. **THE SCALE NUMBER:** how many candidates over 45 min, per type (shot/transition/likely-goal/stoppage)? Is the RANKED top usable for a curator, or does the volume break the design?
3. Sanity-watch a sample of top-ranked candidates (do they land on real events? — perceptual, USER judges if possible, else spot-check).
4. Note: Alfheim is a real full match → real event density, unlike the pre-clipped 30s SoccerNet windows. This is the ranking design's true test.

**STOP. Report: candidate count over 45min per type? is ranked output usable at full-match scale or a flood? do top candidates look like real events?**

---

## PART C — Player highlights at full-match scale — THE TAGGING VOLUME (~70 min)
Run the Day-27 involvement+presence pipeline on the full half:
1. Involvement (nearest-player-to-ball, confident-ball only) + presence fallback over 45 min, on the re-linked tracks.
2. **THE SCALE NUMBER:** how many clips does this generate for a full match? Given Day-30's fragmentation (~2,100 substantial tracks, NOT 22 players), how many distinct clips would a human need to tag? Estimate the human tagging TIME (clips × seconds-per-tag).
3. **This is the deployment-viability finding:** is full-match tagging viable (e.g. <30-60 min of human effort) or prohibitive (hours)? If prohibitive, note what would reduce it (the Day-30 re-linking pre-pass helps; clip-level dedup; only-tag-involvement-not-presence; etc.).
4. Inclusivity at full scale: does the involve+presence design still cover players, or does fragmentation make "per-player" meaningless at full match? (Honest: with 191 IDs/player, a "player reel" pre-tagging is really a "track reel" — the human tagging is what reconstitutes real players. Quantify how much tagging that takes.)

**STOP. Report: clip count for a full match? estimated human tagging time? viable or prohibitive? does inclusivity survive fragmentation?**

---

## PART D — Log the completed scale test + commit (~40 min)
notes.md `## Day 31`: the decoupling, and the COMPLETED full-match scale picture (all 3 deliverables now tested at 45min):
- Event density + ranking usability at full-match scale (the number).
- Player tagging volume + viability (the number) — the key DPS-workflow finding.
- Honest synthesis: with all 3 deliverables now full-match-tested, what's DPS-deployable vs what needs work? (Analytics: team-level yes / per-player no, homography-limited. Events: ranked candidates usable? Player: tagging-viable?)
- The decoupling advanced operator-app readiness (scripts now run on arbitrary footage).
- Honest caveats: Alfheim proxy (fixed single-cam, real full match, but not DPS); fragmentation means pre-tag reels are track-level; DPS kit/court/lighting still pending real footage.
gitignore (Alfheim data local); commit scripts + notes + the scale-findings package:
`git commit -m "Day 31: full-match scale test completed — events + player highlights at 45min; decoupled from SoccerNet; event-density + tagging-volume numbers"`; (push per your workflow).

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Scripts decoupled from SoccerNet? what assumptions removed?
3. EVENT DENSITY: candidates over 45min per type — ranked output usable or flood?
4. Do top-ranked events look real?
5. PLAYER TAGGING VOLUME: clips for a full match? estimated human tag-time? viable or prohibitive?
6. Does inclusivity survive full-match fragmentation?
7. Synthesis: all-3-deliverables-at-full-scale — what's DPS-deployable, what needs work?
8. Errors + time

---

## Do NOT today
- Do NOT re-run detection/tracking — reuse the Day-29 MOT + Day-30 re-linked tracks.
- Do NOT re-break the 30fps assumption when decoupling — Alfheim is 30fps (the Day-29 catch).
- Do NOT chase polished named reels — the deliverable is the SCALE NUMBERS (event density + tagging volume), honestly reported.
- Do NOT hide a bad tagging-volume result — if a full match is hours of tagging, that's a CRITICAL DPS finding worth knowing; report it + what would reduce it.
- Do NOT claim per-player reels are clean pre-tagging — fragmentation means they're track-level until the human tags (quantify the tagging).
- Do NOT attempt to fix fragmentation again (Day-30 settled it's structural) or the analytics magnitude (homography lever, separate).
- Do NOT do basketball or commit Alfheim data.
