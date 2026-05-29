# PRD — Day 20: First Coach Deliverable — Analytics PDF + Tactical Video (Football)
**Project:** AI Sports Recording & Analytics System
**Goal:** Assemble the validated football foundation into the first STAKEHOLDER-FACING deliverable: (1) a coach analytics PDF (one-glance tactical summary), then (2) a wide tactical "analyst-view" video with tracking + team colors drawn on. Deliberately NOT a dashboard — coaches want glance-and-share artifacts. Football, SoccerNet.
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; ALL validated football outputs (Day-10 heatmaps+distance, Day-11 team assignment, Day-12 possession), follow-cam/wide footage, player+ball tracks

---

## Context (read first)

The foundation is COMPLETE for both sports (detection → tracking → team assignment → ball tracking → follow-cam; basketball ball track finally cleared Day-19). This session PIVOTS from foundation to DELIVERABLES — the things the school proposal actually promised coaches.

**Format decision (already made):** coach output = a short VIDEO + a PDF, NOT a dashboard — coaches aren't technical operators; they want something to glance at and share (fits the WhatsApp-shareable angle from the original plan). This session: PDF FIRST (lower-risk assembly), then the tactical video, in one session.

**Nature of this work (different from Days 1-19):** this is mostly ASSEMBLY + PRESENTATION of already-validated outputs, not new CV capability. So the rigor shifts: the numbers are mostly already trust-gated (heatmaps/distance/possession validated against GSR). The new risk is (a) presenting derived-but-not-separately-validated metrics honestly, and (b) making it genuinely coach-useful, not just technically correct.

**Scope: FOOTBALL only** (richest validated data; basketball analytics need a court homography not yet built). PDF + video.

---

## The metrics: VALIDATED trio + DERIVED additions (mark the distinction)

**VALIDATED (trust-gated vs GSR in prior sessions) — present as validated:**
- Team-split positional heatmaps (Day-10/11)
- Distance covered, team-level (Day-10, validated to 0.2m)
- Possession % (Day-12 — note: possession was plausibility-validated, not GT-validated; mark accordingly)

**DERIVED (geometric summaries of validated positions — solid but not separately validated; mark as 'derived analytics'):**
- **Formation map / average positions:** each player's mean pitch position over the clip → de-facto formation. (One of the most-requested coach visuals.)
- **Territory / field tilt:** % of play (ball + player mass) in each pitch third. Intuitive cousin of possession.
- **Team shape / compactness:** avg spread (e.g. stdev of player positions, convex-hull area) per team; defensive-line height. "Were we too stretched?"
- **Intensity zones:** split the already-computed distance into walking/jogging/running/sprinting bands using ESTABLISHED sports-science speed thresholds (e.g. football: walk <2 m/s, jog 2-4, run 4-5.5, high-speed 5.5-7, sprint >7 m/s — use standard bands, cite them, don't invent). Gives "high-intensity distance," the metric sports scientists actually use.

**DEFERRED (note in PDF as "coming soon", do NOT fake): ** pass statistics (needs pass-detection validation — experimental), per-player individual stat lines (needs ReID to fix AssA~0.5 ID-switch noise; per-player totals not yet trustworthy). State these are planned, honestly explain why not yet.

---

## PART A — Compute the derived metrics (~50 min)
From existing player+ball pitch-position data (reuse Day-10/11/12 outputs; do NOT re-run detection/tracking):
1. Formation map: per-track mean pitch position, team-colored, on a pitch diagram.
2. Territory: bin ball+player positions into pitch thirds, % per third per team.
3. Team shape: per-team positional spread (stdev / convex-hull area) over time; report avg + a compactness time-series if cheap.
4. Intensity zones: from per-player velocity (already computed for distance), bucket distance into standard speed bands; report team high-intensity distance.
5. **Sanity-check each** against plausibility (formation looks like a formation; territory sums to 100%; intensity bands sum to total distance; compactness in sane meters). These are derived from validated data so they inherit its trust, but a quick plausibility pass catches bugs.

**STOP. Report: derived metrics computed + plausibility-checked? any that look off?**

---

## PART B — Build the coach PDF (~60 min)
Use the PDF skill. One-glance tactical one-pager (or 2 pages max), coach-readable, shareable:
1. Header: match/clip ID, date, "AI Match Analysis" + a one-line "what this is".
2. **Validated section** (label it): team-split heatmaps, team distance, possession %.
3. **Derived analytics section** (label it clearly as derived): formation map, territory/field-tilt, team shape/compactness, intensity zones.
4. **Coming-soon footer** (honest): "Planned: pass networks, per-player stat lines (pending further validation)."
5. Design: clean, visual, minimal jargon — a coach glances at this on a phone. Big visuals (heatmap, formation), small honest stat tables. NOT a wall of numbers.
6. Keep the validated/derived distinction visible but not alarming — a small label, not a disclaimer that undermines confidence.

**STOP. Report: PDF generated? does it read as coach-useful (glanceable, visual) vs a technical dump? screenshot.**

---

## PART C — Build the tactical "analyst-view" video (~70 min)
The wide tactical view with tracking + team colors drawn on:
1. On the WIDE footage (not the follow-cam crop — this is the analyst/coach tactical view), overlay per frame: player boxes/markers colored by assigned team (Day-11), the ball (Day-12 track, detected/predicted styled), optionally player IDs and a light possession indicator.
2. Keep overlays clean and readable — team colors, ball highlighted, not a cluttered debug view. This is a COACH artifact, not a debug render.
3. Optionally a lower-third with live possession % or current third. Keep minimal.
4. Render 1-2 sample sequences. WATCH: is it a clear tactical view a coach could learn from (who's where, team shape, ball location), not a noisy overlay?

**STOP. Report: tactical video rendered? clean and coach-readable? screenshot/clip.**

---

## PART D — Package, log, commit (~30 min)
1. Put the PDF + sample video together as `outputs/deliverables/coach_package_football/` — the first assembled coach deliverable.
2. notes.md `## Day 20`: the pivot to deliverables, the validated-vs-derived metric split (and WHY each is which), the deferred metrics + honest reasons (passes need validation, per-player needs ReID), PDF + video results, and:
   - This is the first stakeholder-facing artifact — what it proves (foundation → usable output).
   - Honest caveats: SoccerNet footage (deployment on DPS MIS pending); derived metrics inherit validated-position trust but aren't separately GT-checked; per-player deferred.
   - What's next (event/gameplay highlights via A-feed; player highlights via C-feed; basketball analytics need court homography).
3. gitignore checks (NDA/video size); commit scripts + notes + the deliverable package (PDF + a short sample clip if size allows):
   `git commit -m "Day 20: first coach deliverable — analytics PDF + tactical video (football); validated trio + derived analytics; passes/per-player deferred"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Derived metrics computed + plausibility-checked? any off?
3. PDF: coach-useful (glanceable/visual) or a technical dump? screenshot
4. Tactical video: clean + coach-readable? screenshot/clip
5. Is the validated-vs-derived distinction clear but not confidence-undermining?
6. Does the assembled package feel like a real deliverable a coach would use?
7. Errors hit (even if fixed)
8. Time taken

---

## Do NOT today
- Do NOT present derived metrics as validated — mark the distinction (honesty; they inherit validated-position trust but aren't separately GT-checked).
- Do NOT fake pass stats or per-player stat lines — note them as deferred with honest reasons (pass-detection unvalidated; per-player needs ReID for AssA~0.5 ID-switch noise).
- Do NOT invent intensity-zone speed thresholds — use established sports-science bands, cite them.
- Do NOT make a dashboard — PDF + video, glance-and-share (the decided format).
- Do NOT make the video a debug render — clean coach-readable overlays, not the diagnostic view.
- Do NOT re-run detection/tracking — assemble from validated Day-10/11/12 outputs.
- Do NOT do basketball (needs court homography) or highlights (next sessions).
- Do NOT commit SoccerNet raw data (NDA) or oversized video.
