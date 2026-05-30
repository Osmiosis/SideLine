# PRD — Day 28: Inclusive Basketball Player Highlights (output #2 parity) — radius reconsidered
**Project:** AI Sports Recording & Analytics System — for DPS MIS Doha
**Goal:** Bring output #2 (inclusive player highlights) to basketball parity, reusing the Day-27 mechanism BUT re-deriving "involvement" for basketball's crowded half-court (a fixed proximity radius marks everyone involved → meaningless). Test the involvement definition empirically BEFORE clipping, then C-feed clips + tag-per-clip + explicit 100% inclusivity verification. Basketball, SportsMOT (proxy for DPS).
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; basketball player tracks (Day-9), ball track (Day-19 head-FP-cleaned, plausibility-level), basketball C-feed (Day-15/16), Day-27 `detect_involvement.py` / `clip_player_highlights.py` / `tag_clips.py` / `assemble_player_reels.py` to adapt

---

## PROJECT GOAL CONTEXT (DPS-aware — read first)
Deployable system for DPS MIS Doha: fixed dual-phone capture → ONE pipeline → THREE outputs: (1) coach analytics [DONE both sports], (2) **player highlights [football DONE Day-27, THIS = basketball half]**, (3) event reels [DONE both sports]. Proxies validate METHOD; real target = DPS.

**Inclusivity is the point** (every player gets footage, not just stars — school value + VEO differentiator). **Identical house kits** (Rose=red/Lily=yellow, no numbers/names) → auto-identity impossible (Day-26 proved it) → human tag-per-clip. Both carry from Day-27.

---

## THE basketball-specific problem: involvement radius doesn't transfer
Day-27 football involvement = "nearest player within ~2m of the ball." Works on a big spread pitch. **Basketball is a half-court game in a tiny space — all 10 players can be within a few meters of the ball at once.** A fixed radius → marks nearly everyone involved every frame → involvement becomes MEANINGLESS (no discrimination between ball-handler and a player standing in the corner).

So basketball needs a DIFFERENT involvement definition, not just a smaller radius. Candidates:
1. **Strict nearest-only:** only the SINGLE closest player to the ball is "involved" (not everyone-within-X). In a crowd exactly one is closest = usually the ball-handler. Cleanest fix.
2. **Relative-gap:** involved = closest AND meaningfully closer than 2nd-closest (the ball is clearly THEIRS, not contested-equidistant). Filters ambiguous crowd frames.
3. **Possession-based:** closest AND ball moving with them (dribble/hold). Tighter but leans on the plausibility-level ball track (noisier).

Lean: **strict-nearest + relative-gap.** Expect basketball to lean MORE on the presence fallback than football (involvement is concentrated on ball-handlers) — honest and expected, NOT a failure. Smaller teams (~5/side) make full inclusivity easier anyway.

---

## PART 0 — Confirm inputs (~20 min)
1. Confirm the basketball C-feed used is the cleaned version (post head-FP work, Day-16/19) — the player-stabilized feed (C), NOT the ball-faithful A-feed. (C is right for player-subject clips and is the more robust basketball feed.)
2. Confirm ball track (Day-19) + player tracks (Day-9) on disk for the eval clips.

**STOP. Report: C-feed (cleaned) confirmed? ball + player tracks available?**

---

## PART A — Re-derive + EMPIRICALLY TEST involvement (measure before clipping) (~60 min)
Do NOT just shrink the radius and clip. TEST definitions first:
1. Run involvement detection with 2-3 definitions: (a) strict-nearest-only, (b) strict-nearest + relative-gap (closest must be clearly closer than 2nd), optionally (c) a tight fixed radius for comparison.
2. For each, report the DISTRIBUTION: involvement moments per track. The GOOD signal = a few players with clear ball-handler moments + discrimination (NOT "all 10 always involved"). The BAD signal (fixed radius) = everyone involved every frame.
3. Pick the definition that DISCRIMINATES (ball-handler vs bystander), basketball-radius tuned (height-normalized like Day-27, re-tuned for basketball scale). Use the lost-ball discipline — only confident-ball frames count.

**STOP. Report: distribution per definition? which discriminates properly? chosen definition + why? (this is the measure-before-clip gate)**

---

## PART B — Clip from the C-feed (~40 min)
Reuse Day-27 clipping on the chosen involvement ranges: each range + padding cut from the basketball C-feed. Tag clips with track id + timestamp + involvement-strength.

**STOP. Report: involvement clips generated? do they center the ball-handler (C-feed working for basketball)?**

---

## PART C — Presence fallback + tag-per-clip (~50 min)
1. **Presence fallback (the inclusivity guarantee, from Day-27):** any substantial on-court track with zero involvement gets its longest contiguous visible stretch clipped from the C-feed. (Expect MORE presence clips than football — basketball involvement is concentrated.)
2. **Tag-per-clip:** reuse the Day-27 tagging tool (Tkinter, roster, bulk-name per track, re-tag on ID-switch). Identical kits → human names short clips.

**STOP. Report: presence fallback working? involve-vs-presence ratio (expect more presence than football)? tagging tool works for basketball?**

---

## PART D — Assemble + VERIFY INCLUSIVITY (~40 min)
1. Group clips by name → per-player reel (rank involvement-strength, title card).
2. **VERIFY INCLUSIVITY EXPLICITLY:** every substantial on-court player gets a reel with footage (involve + presence → target 100% by construction, like football). List coverage; flag anyone missed + why.
3. Report: players covered, involve/presence split, min/median/max clips per player.

**STOP. Report: per-player reels assembled? INCLUSIVITY verified 100%? involve/presence split?**

---

## PART E — Log + commit (~30 min)
notes.md `## Day 28`: the radius-doesn't-transfer problem + the re-derived involvement definition (with the distribution evidence for WHY), basketball involve/presence split (vs football's 29%/71%), inclusivity verification, and:
- DPS workflow same as football (roster + tag-per-clip; identical kits handled by human naming).
- Honest caveats: involvement leans on plausibility-level basketball ball track (noisier than football's RMSE-validated → more presence reliance); height-norm radius re-tune at DPS mount; SportsMOT proxy, DPS-pending.
- Status: output #2 now at parity (both sports); inclusive every-player reels both sports.
gitignore checks (clips/video; double-check no dataset leakage after the Day-27 .gitignore scare); commit scripts + notes + basketball package:
`git commit -m "Day 28: inclusive basketball player highlights (output #2 parity) — re-derived involvement for half-court + presence fallback; inclusivity verified"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. C-feed (cleaned) + tracks confirmed?
3. Involvement definitions tested — which discriminates (not everyone-always-involved)? chosen + why?
4. Clips center the ball-handler (C-feed)?
5. Involve/presence split (vs football 29/71)?
6. INCLUSIVITY verified 100%? anyone missed + why?
7. Errors + time

---

## Do NOT today
- Do NOT reuse football's involvement radius — half-court makes a fixed radius mark everyone involved; re-derive + TEST the definition before clipping (the measure-before-clip gate).
- Do NOT clip before confirming the involvement definition discriminates (ball-handler vs bystander).
- Do NOT use the A-feed — C-feed (player-stabilized) for player clips.
- Do NOT skip the presence fallback — it's the inclusivity guarantee (expect heavier basketball reliance).
- Do NOT attempt auto-identity — identical kits → human tag-per-clip (Day-26 evidenced).
- Do NOT claim exact per-touch — nearest-player involvement, plausibility-level (noisier on basketball's ball track).
- Do NOT fabricate involvement on lost-ball frames — confident-ball only.
- Do NOT re-run detection/tracking — reuse Day-9/19.
- Do NOT commit oversized video or (NDA/scare) any dataset content — verify git status.
