# PRD — Day 27: Inclusive Player Highlights (output #2) — involvement clips + tag-per-clip — Football
**Project:** AI Sports Recording & Analytics System — for DPS MIS Doha
**Goal:** Build output #2 (per-player highlights) as an INCLUSIVE deliverable: detect every player's involvement moments (nearest-player-to-ball), clip them from the C-feed, let the user NAME each short clip (tag-per-clip — sidesteps identical-house-kit identity), assemble per-player reels, and VERIFY every player who was on court gets footage. Football, SoccerNet (proxy for DPS).
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; player tracks (Day-9), ball track (Day-12 RMSE-validated), C-feed player-stabilized follow-cam (Day-13), Day-24/25 clipping machinery to reuse

---

## PROJECT GOAL CONTEXT (DPS-aware — read first)
Deployable system for DPS MIS Doha: fixed dual-phone capture → ONE pipeline → THREE outputs: (1) coach analytics [DONE both sports], (2) **per-player highlights [THIS]**, (3) event reels [DONE both sports]. Proxies build/validate METHOD; real target = DPS.

**Two DPS realities that SHAPE this deliverable:**
1. **INCLUSIVITY is the point.** Event highlights (output #3) only surface exciting moments → concentrate on stars (scorers/playmakers); quiet players get little/nothing. Player highlights must be INCLUSIVE — every player gets footage, not just stars. This is a school-specific value (every kid seen; parents want THEIR child) and a genuine differentiator vs VEO/Pixellot (which are star/ball-focused). Foreground it.
2. **Identical house kits make auto-identity IMPOSSIBLE.** DPS houses wear uniform kits — Rose=full red, Lily=full yellow, NO numbers, NO names. Within a team every player is visually identical → appearance ReID is not just weak (Day-23/26 ceiling) but FUNDAMENTALLY impossible (no appearance signal to separate teammates). So identity = HUMAN tag-per-clip. The system can't name them; the user does. Confirmed by the Day-26 ReID measurement failure (AssA +0.004, useless) — this is the settled, evidenced pivot.

---

## The mechanism (settled — concrete, no magic)
1. **Involvement detection = math on existing data:** per frame, nearest player to the ball within a threshold (~2m, reuse Day-12 possession-proxy logic) → per-track lists of involvement frame-ranges. Quiet defender who cleared 3 balls → 3 involvement ranges; playmaker → many. Naturally scales with involvement = inclusive by construction.
2. **Clip = reuse Day-24/25 clipping:** each involvement range + padding (-2s/+1s) → ffmpeg cut from the C-FEED (player-stabilized, the right feed for player-subject clips). Same clipping machinery as event highlights, different timestamps.
3. **Identity = tag-per-clip:** clips come grouped by track ID, but IDs drift/switch (house-kit problem). So the user NAMES each short clip ("who is this?"). Each clip is short (~seconds) → one continuous visible person → unambiguous even in identical kits. User names the clip, not the match-long identity.
4. **Assemble:** group clips by user-assigned name → concatenate → per-player reel.

---

## PART A — Involvement detection (~50 min)
1. Per frame, compute nearest player to the ball (Day-12 logic), distance threshold (~2m in pitch-meters via homography; tune). Use the lost-ball discipline (Day-24): when the ball is lost/predicted, don't fabricate involvement — only count confident-ball frames.
2. Per player TRACK, collect involvement frame-ranges (merge ranges within a small gap; min duration so 2-frame blips don't become clips).
3. Output: per-track involvement timeline. Report distribution: how many involvement moments per track? (Sanity: a few star tracks with many, a long tail with few — that long tail is the inclusivity target.)

**STOP. Report: involvement moments detected per track? does the distribution show stars AND quiet players (the inclusivity signal)?**

---

## PART B — Clip from the C-feed (~40 min)
1. For each involvement range, cut from the C-feed (Day-13 player-stabilized) with padding. Reuse Day-24/25 ffmpeg clipping.
2. Tag each clip with its source track ID + timestamp + involvement-strength (e.g. how close/how long on ball) for later ranking within a player's reel.
3. Note: clips are C-feed (player-centered) NOT A-feed — player highlights are about the PERSON, the C-feed keeps them framed. (The A/C split from Day-13 paying off.)

**STOP. Report: clips generated? do they actually center the involved player (C-feed working for this)?**

---

## PART C — Tag-per-clip identity tool (~50 min)
1. Build a simple tagging app (like the Day-19 sorter / Day-22 labeler that worked): show each involvement clip (or its key frame + short preview), user clicks a NAME (or "skip/not-a-real-involvement"). Roster is user-entered (e.g. the DPS team list).
2. Each clip is short → the player is visually unambiguous within it even in identical kits (the whole reason tag-per-clip beats auto-ReID here).
3. Optional speed-up: pre-group by track ID so consecutive clips from one un-switched track can be bulk-named — but the user can re-tag any that the track got wrong (ID switch). Keep it forgiving.
4. Save clip→name mapping.

**STOP. Report: tagging tool works? how long to tag a match's worth of clips? was it manageable?**

---

## PART D — Assemble per-player reels + VERIFY INCLUSIVITY (~40 min)
1. Group clips by assigned name → concatenate (optionally ranked by involvement-strength, best first) → one reel per player. Add a simple title card per reel (player name).
2. **VERIFY INCLUSIVITY EXPLICITLY (the goal check):** list every player who appeared on court (every substantial track) and confirm each gets a reel with at least some footage. Flag any player with zero/near-zero clips — are they genuinely uninvolved, or did involvement detection miss them? (A player with real court time but no reel = the inclusivity goal failing, investigate.)
3. Report: how many players got reels? min/median/max clips per player? anyone left out, and why?

**STOP. Report: per-player reels assembled? INCLUSIVITY verified — does everyone who played get footage? anyone missed + why?**

---

## PART E — Log + commit (~30 min)
notes.md `## Day 27`: the inclusivity reframe (event highlights miss quiet players → player highlights must include everyone; the VEO differentiator), the identical-house-kit reality (auto-identity impossible → tag-per-clip, evidenced by Day-26 ReID failure), the mechanism (involvement math → C-feed clip → tag → assemble), inclusivity verification result, and:
- DPS workflow: user enters roster + tags clips; identical kits handled by short-clip human naming (not auto-ID).
- Honest caveats: involvement = nearest-player proxy (plausibility-level, catches near-ball not exact-touch — fine for inclusive reels); SoccerNet footage, DPS-pending; tagging is manual effort (quantify it).
- Differentiator note for the report/proposal: inclusive every-player reels vs VEO's star/ball focus.
gitignore (clips/video); commit scripts + notes + sample per-player reels:
`git commit -m "Day 27: inclusive player highlights (output #2, football) — involvement clips from C-feed + tag-per-clip identity; inclusivity verified"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Involvement per track — distribution show stars AND quiet players?
3. Clips center the involved player (C-feed working)?
4. Tagging tool manageable? time to tag a match?
5. Per-player reels assembled?
6. INCLUSIVITY VERIFIED: does everyone who played get footage? anyone missed + why?
7. Errors + time

---

## Do NOT today
- Do NOT attempt auto-player-identity / ReID — identical house kits make it impossible (Day-26 evidenced); identity = human tag-per-clip.
- Do NOT build star-only reels — inclusivity is the GOAL; verify every player gets footage.
- Do NOT use the A-feed for player clips — C-feed (player-stabilized) is the right feed for player-subject footage.
- Do NOT fabricate involvement on lost-ball frames — confident-ball only (Day-24 lost-ball discipline).
- Do NOT claim exact per-touch attribution — it's nearest-player involvement (plausibility-level), honestly framed.
- Do NOT do basketball (next) or re-run detection/tracking (reuse Day-9/12/13).
- Do NOT commit oversized video.
