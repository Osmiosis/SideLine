# PRD — Day 19: Lighter Ball-vs-Head Methods (break the TrackNet tunnel-vision) — Basketball
**Project:** AI Sports Recording & Analytics System
**Goal:** Before committing to data-hungry TrackNet, evaluate LIGHTER methods that target the actual failure (detector confuses HEADS with the ball) and need far less labeling: (1) a ball-vs-not-ball crop classifier, (2) appearance-embedding/ReID rejection. Pick by fit-to-effort. Labeling falls out of the chosen method (likely: bulk-sort auto-cropped candidates, not draw boxes). Basketball, SportsMOT.
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; basketball ball detector, Day-9 player tracks, Day-16/17 FP diagnostics, follow_cam_basketball.py

---

## Context (read first)

Basketball ball track latches onto HEADS (confirmed by WATCHING — Day-17's 0.4% metric was wrong, heads still grab the camera on the rendered clips). Day-17 PROVED heads aren't size- or geometry-separable from the ball (area ratio ~1.0). The discriminating signal is APPEARANCE and/or MOTION.

Day-18 found TrackNet (the motion-learning fix) is blocked: no off-the-shelf consecutive-frame basketball ball GT (WASB frames academic-gated 135GB; DeepSport has frames XOR ball-GT, never both). TrackNet needs the scarce data.

**The tunnel-vision realization:** the four FP sessions (15-18) assumed the fix was either spatial-geometry (failed) or full temporal-learning (TrackNet, data-gated). The MIDDLE ground was skipped: APPEARANCE-based rejection. A head and a ball look different in appearance space even at identical size/shape — and learning that needs SINGLE labeled crops, not consecutive-frame trajectories. This sidesteps the entire TrackNet data wall.

**This session evaluates the lighter middle-ground methods.** TrackNet stays the documented fallback if these fail.

**Scope: BASKETBALL ball-FP rejection.** Reuse existing detector + tracks; no football; integration into follow-cam only as the eval.

---

## The candidate methods (evaluate by fit-to-effort)

1. **Ball-vs-not-ball crop classifier (lead candidate).** The detector proposes ball candidates; a small CNN (or even a logistic/SVM on lightweight features) classifies each crop as ball vs head/junk, rejecting heads. Trained on SINGLE labeled crops — NO consecutive frames. Labeling = sort auto-cropped candidates into ball/not-ball folders (clicking thumbnails, not drawing). Directly targets the head failure. Cheapest to label.

2. **Appearance-embedding / ReID rejection (Day-9 deferred arm).** Embed each candidate crop (a pretrained lightweight backbone, or the detector's own features); separate ball-appearance from head-appearance by threshold/clustering. Can bootstrap the "ball" anchor from HIGH-CONFIDENCE detections → potentially near-ZERO manual labels. Lightest labeling; slightly less reliable than a trained classifier.

3. **TrackNet — documented fallback only.** If 1 and 2 both fail to separate heads from the ball, TrackNet is justified, and the data cost is known (WASB academic email, async; or sparse-keyframe self-labeling).

---

## PART A — Build the candidate-crop dataset (fast labeling) (~50 min)
1. Run the basketball ball detector over the SportsMOT basketball clips; collect ALL ball-candidate detections (including the FPs — heads, banners, real balls), saving each as a small crop + its frame/box metadata.
2. **Fast labeling = bulk-sort, not draw:** auto-arrange candidate crops into a contact-sheet / folder-sort UI (or just two folders). User clicks each into {ball, not-ball(head/junk)}. Target a few hundred each — enough for a binary classifier. Seed with the Day-17 head-zone flags + confident detections to pre-sort and cut manual work.
   - This is the "fast, not soul-crushing" labeling: reviewing thumbnails, ~hundreds in ~30-40 min.
3. Hold out a test split for honest eval.

**STOP. Report: how many ball / not-ball crops labeled? labeling time? was the sort-based flow fast enough?**

---

## PART B — Method 1: ball-vs-not-ball crop classifier (~60 min)
1. Train a small classifier on the labeled crops (lightweight CNN, or features + simple classifier — keep it small for the 4060 and to avoid overfitting a few-hundred-sample set).
2. **Trust gate:** evaluate on the held-out crops — precision/recall for rejecting heads, and CRITICALLY the false-rejection rate on REAL balls (rejecting real balls would break tracking, the Day-17 failure mode). Report a confusion matrix.
3. Integrate as a FILTER on the ball-detection step: detector proposes → classifier vetoes heads/junk → survivors feed the existing Kalman.

**STOP. Report: classifier head-rejection precision/recall? real-ball false-rejection rate? (the must-not-break number)**

---

## PART C — Method 2: appearance-embedding rejection (~40 min)
1. Embed candidate crops with a lightweight pretrained backbone (or detector features). Anchor "ball" appearance from high-confidence detections; score candidates by distance to the ball anchor vs head examples.
2. Evaluate the SAME held-out set: head-rejection vs real-ball false-rejection. Compare to Method 1.
3. Note labeling cost: did this need fewer labels than Method 1 (bootstrap from confident dets)?

**STOP. Report: embedding-method head-rejection + real-ball false-rejection vs Method 1; labeling-cost difference.**

---

## PART D — Pick the winner, integrate, RE-WATCH (~40 min)
1. Choose the method with the best head-rejection AT the lowest real-ball false-rejection (fit-to-effort: if the classifier and embedding tie, prefer the one that needed less labeling / is simpler).
2. Regenerate the basketball ball track with the winning FP-filter in front of the Kalman; rebuild the A-feed.
3. **RE-WATCH (the real verdict, not the metric — Day-15/17 lesson):** on the rendered A-feed clips, do heads STILL grab the camera? Does the camera stay on the real ball when visible? Did dribble/pass/shot tracking survive?
4. Report against the same bar as Day-17: head-FP-latch low AND visually clean AND liked behavior intact.

**STOP. Report: winner method; RE-WATCH verdict (heads gone on VIDEO?); real-ball tracking intact?**

---

## PART E — Log + decision + commit (~30 min)
notes.md `## Day 19`: the tunnel-vision reframe (appearance middle-ground skipped for 4 sessions), labeling approach + cost, both methods' numbers (head-rejection vs real-ball false-rejection), the winner, the RE-WATCH verdict, and THE DECISION:
- **WORKS** (heads gone on video, real ball intact) → basketball ball track FINALLY done via the lightweight appearance fix; both sports at parity; TrackNet NOT needed (data wall sidestepped); → highlights/deliverables next.
- **PARTIAL/FAIL** → honest: appearance alone insufficient; TrackNet is the real path (send the WASB academic email now, async) OR accept basketball A-feed limitation + ship clean deliverables (football highlights, basketball C-feed) meanwhile.
Commit classifier/embedding scripts + notes (NOT the crop dataset if license-encumbered):
`git commit -m "Day 19: lightweight ball-vs-head appearance FP rejection (classifier/embedding); [works/partial]; TrackNet tunnel-vision broken"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Labeling: ball/not-ball crop counts + time + was the sort-flow fast enough?
3. Method 1 (classifier): head-rejection P/R + real-ball false-rejection rate
4. Method 2 (embedding): same + labeling-cost difference
5. Winner + why
6. RE-WATCH verdict: heads gone ON VIDEO? real-ball tracking survived?
7. DECISION: basketball ball track done, or TrackNet/defer?
8. Errors + time

---

## Do NOT today
- Do NOT jump to TrackNet — it's the fallback; the lighter appearance methods (single-crop labels, no consecutive-frame data) are tested first.
- Do NOT trust classifier metrics over the RE-WATCH — heads "gone" means gone ON THE VIDEO (Day-15/17 lesson: a good number with a bad video is a FAIL).
- Do NOT accept a head-rejection gain that raises real-ball false-rejection — breaking real-ball tracking is the Day-17 failure mode; the must-not-break number.
- Do NOT draw bounding boxes for labeling — sort auto-cropped candidates into folders (fast, sustainable).
- Do NOT over-train a giant model on a few hundred crops — keep it small, watch for overfit.
- Do NOT do football / highlights / C-feed this session.
- Do NOT commit license-encumbered crop data.
