# PRD — Day 18: TrackNet Data Scouting (cheap pre-step, NOT the build)
**Project:** AI Sports Recording & Analytics System
**Goal:** Determine which consecutive-frame basketball ball-position dataset is ACTUALLY accessible and usable as TrackNet training data — before committing to the full TrackNet build. Pure scouting: acquire/inspect/verify, do NOT train anything. The output is a go/no-go + a chosen source, which then shapes the real TrackNet PRD.
**Estimated time:** 1.5–2.5 hours (short by design — this is a gate, not a build)
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo

---

## Context (read first)

Three spatial patches (Day 15 wobble, 16 corner-FP, 17 head-FP) failed to stop the basketball ball track latching onto heads — confirmed by WATCHING the rendered clips (the Day-17 notes claimed PASS on a 0.4% metric, but the user watched the new clips and heads STILL grab the camera; eyes overrule the metric, same as Day 15). Day-17 also PROVED heads aren't size-separable from the ball (area 1.07×) — so the discriminating signal is TEMPORAL (motion), which is TrackNet's domain. TrackNet is now the EVIDENCED next step.

BUT TrackNet needs CONSECUTIVE-FRAME ball-position training data for basketball, which is scarce/gated. This session ONLY answers: which source is real and usable? No training. Writing the full TrackNet PRD waits until this returns a verified source.

**Skepticism rule:** these are LEADS, not confirmed assets. A dataset described well in a chat/paper is not a downloaded, parsed, sanity-checked dataset. Do not declare a source "usable" until frames + per-frame ball coords are actually on disk and a sample renders correctly. (We've been burned by "should work": the 72-frame set, the OwnCloud 401.)

---

## Candidate sources (check in PRIORITY ORDER; stop when one clean source is confirmed sufficient)

1. **WASB-SBDT (`nttcom/WASB-SBDT`)** — purpose-built for TrackNet-style heatmap regression, claims continuous basketball annotations across 5 sports. HIGHEST PRIORITY (format already matches TrackNet). Check: repo accessible? basketball split downloadable (not gated)? annotation format = per-frame ball (x,y)? license?

2. **DeepSportRadar Ballistic / `deepsport` / Kaggle `gabrielvanzandycke/ballistic-raw-sequences`** — continuous raw basketball sequences, ball annotated across consecutive frames with 3D positions projectable to 2D pixels. Already parked from earlier (gated, pickle format) — re-check the KAGGLE ballistic-raw-sequences specifically, which may be the ungated path. Check: Kaggle set accessible? consecutive frames? 2D pixel coords derivable?

3. **SportsTrack (2024, Han et al.)** — UNVERIFIED lead; claims hand-annotated basketball with occlusion. Check existence/accessibility; treat with skepticism (may be misnamed/unavailable).

4. **TrackID3x3 (2025, Yamada et al.)** — UNVERIFIED lead; 3x3 basketball, continuous frames, primarily player/pose. Check existence/accessibility; lowest priority (3x3 ≠ our 5v5 use case, and player-focused not ball).

---

## PART A — Scout the sources (~60–90 min)
For each candidate in priority order, until one CLEAN sufficient source is confirmed:
1. Web-search + locate the actual repo/dataset page. Note: real? accessible without paywall/NDA/credential gate?
2. If accessible, attempt to actually acquire a SMALL sample (a few sequences, not the whole thing). Note download mechanism + any friction.
3. Inspect format: are there CONSECUTIVE frames with PER-FRAME ball positions (pixel x,y or projectable to it)? This is the make-or-break property — disjoint single-frame boxes are useless for TrackNet.
4. Note: license/usage terms (can it go in the project? must it stay off the public repo?), size, basketball-specific availability (not just "multi-sport" in the abstract).

Stop scouting once you have ONE confirmed source with consecutive-frame ball positions in a TrackNet-convertible format. (Don't exhaustively acquire all four — find the cleanest usable one.)

**STOP. Report per source checked: real? accessible? consecutive-frame ball coords? format? license? → which is the WINNER (or none).**

---

## PART B — Verify the winner is genuinely usable (~30–45 min)
For the chosen source only:
1. Acquire a small but real sample (e.g. a few hundred consecutive frames with ball annotations).
2. **Sanity-render:** draw the annotated ball position on ~20-30 consecutive frames as a short clip/strip. WATCH: does the annotation actually sit ON the ball, frame to frame, continuously? (This is the trust gate for the data — bad labels make TrackNet pointless.)
3. Confirm convertibility to TrackNet's expected input (consecutive frames → per-frame 2D Gaussian heatmap at ball center). Note any conversion needed.
4. Estimate scale: how many usable consecutive-frame basketball samples total? (Enough to train? hundreds-of-frames is thin; thousands is workable.)

**STOP. Report: winner verified? annotations sit on the ball (sanity-render)? convertible to heatmap format? how many usable frames? GO or NO-GO for the TrackNet build?**

---

## PART C — Log + decide (~20 min)
Append `## Day 18` to notes.md: the FAIL reconciliation (Day-17's 0.4% metric vs the user's eyes — heads still latch on the new clips; spatial approach ceiling reached, signal is temporal), each source's scouting result (real/accessible/format/license), the chosen winner + its verification (sanity-render result, usable frame count, convertibility), and the GO/NO-GO:
- **GO** → next session is the full TrackNet build (training + baseline, integration deferred). Note the chosen source + format so the build PRD can be written precisely.
- **NO-GO** (no accessible source with consecutive ball coords) → the honest fork: hand-label N frames (state the realistic cost), OR accept head-FP as a documented basketball limitation and proceed to deliverables that ARE clean (football highlights on the RMSE-validated football ball track; basketball C-feed which works). Recommend based on what scouting found.
Commit scouting scripts + notes (NO datasets):
`git commit -m "Day 18: TrackNet data scouting — [winner source] verified / [or NO-GO]; reconciled Day-17 FAIL"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Per source: real? accessible? consecutive-frame ball coords? format? license?
3. WINNER source (or none)
4. Sanity-render: do the winner's annotations sit on the ball frame-to-frame?
5. Usable basketball consecutive-frame count (enough to train?)
6. Convertible to TrackNet heatmap format? conversion needed?
7. GO / NO-GO for the TrackNet build — and if NO-GO, hand-label vs defer recommendation
8. Errors hit
9. Time taken

---

## Do NOT today
- Do NOT train anything — this is scouting only. The TrackNet build is the NEXT session, written around whatever this finds.
- Do NOT declare a source usable from its description — acquire a real sample + sanity-render the annotations on the ball first (the data trust gate).
- Do NOT acquire all four exhaustively — find ONE clean usable source and stop.
- Do NOT trust the unverified leads (SportsTrack, TrackID3x3) without confirming they exist + are accessible.
- Do NOT commit datasets (license/size); scripts + notes only.
- Do NOT spend >~2.5h — if no clean source appears, that itself is the answer (→ NO-GO fork), don't grind.
