# PRD — Day 29: Full-Match Footage — Stitch Alfheim Single-Cam + Full-Match Scale-Stress-Test (Football)
**Project:** AI Sports Recording & Analytics System — for DPS MIS Doha
**Goal:** Acquire a FULL continuous football match from a FIXED single camera (Alfheim, Tromsø–Strømsgodset, single-camera-1) by stitching its many short H264 clips into continuous halves, VERIFY continuity first, then run ALL THREE deliverables end-to-end at full-match scale. This is the first full-match test — finding what BREAKS at 45-90min scale (ID accumulation, event density, runtime, tagging volume) is the GOAL. BONUS: Alfheim ships ZXY ground-truth (player positions + distance + speed-class) → first real TRUST GATE for the analytics deliverable.
**Estimated time:** 4–5 hours (download + stitch + full-match run; a big session — may split)
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; full football pipeline (Day-9 tracking, Day-10 homography, Day-11 teams, Day-12 ball, Day-13 follow-cam, Day-20 analytics, Day-24 events, Day-27 player highlights); ffmpeg
**Source:** https://datasets.simula.no/alfheim/ — match "2013-11-03: Tromsø IL - Strømsgodset", SINGLE CAMERA 1 (chosen because a single fixed camera matches the DPS phone rig — NOT the stitched panorama).

---

## PROJECT GOAL CONTEXT (DPS-aware — read first)
Deployable system for DPS MIS Doha: fixed dual-phone capture → ONE pipeline → THREE outputs (coach analytics, event reels, player highlights) — ALL THREE now exist for both sports, but ONLY validated on 30-second proxy clips. This session is the FULL-MATCH test on FIXED-CAMERA footage — the closest proxy yet to DPS deployment (fixed elevated single camera ≈ the DPS rig). Why single-cam-1 not panorama: single fixed camera with native lens = true DPS preview; panorama is 5-camera stitched (seams, not the deployment scenario).

**This is a SCALE-STRESS-TEST. Finding what breaks at full-match length IS the goal — not a failure.** Expect: ID-switch accumulation over 45min, event-candidate density, runtime/memory limits (RAM exhaustion hit once before — Day-26), tagging volume for player highlights.

---

## PART 0 — Acquire + VERIFY CONTINUITY (the gate — do NOT skip) (~60 min)
**The critical unknown: are the clips CONTIGUOUS (tile the whole half) or only clustered around events?** If contiguous → stitch gives a real continuous match. If gappy → stitching gives a broken highlight-stream (tracking teleports across gaps) = useless for a scale test. VERIFY BEFORE STITCHING.
1. From https://datasets.simula.no/alfheim/ locate the Tromsø–Strømsgodset (2013-11-03) SINGLE CAMERA 1 clips for 1st half and 2nd half. Note count + total size + license terms (free non-commercial research — confirm; keep OFF the public repo if redistribution-restricted).
2. Download a SMALL SAMPLE first (e.g. the first ~20 clips of 1st half). Inspect:
   - **Naming/ordering:** are they sequentially numbered/timestamped so chronological order is unambiguous?
   - **Continuity:** do consecutive clips' timestamps/durations tile back-to-back with NO gaps (clip N ends where clip N+1 begins)? Or are there time jumps (event-clustered)?
   - **Uniform codec/res/fps** across clips (enables lossless stream-copy concat)?
3. **DECISION GATE:**
   - CONTIGUOUS + uniform → proceed to full download + stitch.
   - GAPPY (event-clustered) → STOP. Report: the clips don't reconstruct a continuous match; full-match scale-test not possible from this source as-is. (Then we rethink — maybe panorama has a continuous file, or another source.)

**STOP. Report: clip count/size? sequentially ordered? CONTIGUOUS (tile the whole half) or gappy? codec uniform? GO/NO-GO for stitching.**

---

## PART A — Stitch into continuous halves (~40 min, if GO)
1. Download the full set of single-cam-1 clips for both halves.
2. Order them chronologically (by name/timestamp — verify the sort is correct, not lexicographic-broken e.g. clip2 vs clip10).
3. **ffmpeg concat, stream-copy** (lossless, fast) if codecs uniform: produce `first_half.mp4` and `second_half.mp4`. Re-encode only if necessary (note quality cost).
4. **VERIFY the stitch:** play/scan the joins — total duration ≈ 45min/half? Any black frames, freezes, or hard jumps at clip boundaries? Note: tiny single-frame seam-blips are expected and OK (tracking rides over them); big jumps are not. (Honesty note for later: seam-glitches are STITCH artifacts, not pipeline failures — don't misread them.)

**STOP. Report: halves stitched? durations sane (~45min each)? joins clean or glitchy? sample frame.**

---

## PART B — Run the FOUNDATION at full-match scale (~70 min)
Run the existing football pipeline on ONE full half first (1st half) — do NOT do both halves + all deliverables blind; prove one half works, then scale.
1. Detection + tracking (Day-9 config) over the full half. WATCH runtime + memory (process in chunks if needed; the RAM-exhaustion lesson from Day-26 — sequential, monitor). Note: how many total track IDs over 45min? (ID-accumulation = the key scale finding.)
2. Homography (Day-10): the Alfheim camera is FIXED → ONE homography should hold the whole half (unlike the broadcast proxies that needed per-segment). Mark it once (manual-marking method from Day-21, or Alfheim's known 105×68 pitch + ZXY calibration). Validate against ZXY pitch coords if mappable.
3. Team assignment (Day-11/23), ball tracking (Day-12).

**STOP. Report: full-half foundation ran? runtime + peak memory? total track-ID count (ID accumulation)? does ONE fixed homography hold the whole half? any drift/divergence over 45min?**

---

## PART C — Run ALL THREE deliverables at full-match scale (~80 min)
On the full 1st half:
1. **Coach analytics (Day-20):** full-match heatmaps, distance, possession, intensity zones, formation. These are now REAL match aggregates (not 30s toys). **TRUST GATE (the bonus):** validate distance + speed-class against Alfheim's ZXY ground-truth (it ships per-player distance + distance-in-speed-classes at 1Hz). FIRST real GT validation of the analytics deliverable — report your distance vs ZXY distance, your intensity bands vs ZXY speed classes.
2. **Event highlights (Day-24):** run high-recall + ranking over 45min. KEY SCALE TEST: how many candidates over a full half? Is the ranked output USABLE for a curator, or a flood? (This is where the ranking design gets its real trial.)
3. **Player highlights (Day-27):** involvement + presence over 45min. KEY SCALE TEST: tagging VOLUME — how many clips would a human tag for a full match? Minutes or hours? (Deployment-viability question.) Inclusivity over a full half.

**STOP. Report per deliverable: did it run at scale? Analytics: distance/speed vs ZXY GT (the trust gate numbers!). Events: candidate count + is ranking usable at scale? Player: tagging volume + inclusivity.**

---

## PART D — Log the scale findings + commit (~40 min)
notes.md `## Day 29`: the source (Alfheim single-cam-1, why single-cam not panorama = DPS rig match), continuity verification + stitch, and THE SCALE FINDINGS (the point of the session):
- ID accumulation over 45min (vs 30s clips).
- Runtime + memory at full-match scale (RTX 4060 feasibility → informs the operator-app compute question).
- ONE fixed homography holding a full half (the DPS fixed-camera advantage, finally demonstrated on real full-length footage).
- **Analytics TRUST GATE: distance/speed-class vs ZXY ground-truth** — the FIRST GT validation of the analytics deliverable (upgrade from plausibility). Report the error.
- Event candidate density + ranking usability at scale.
- Player-highlight tagging volume at scale (deployment-effort reality).
- What broke / what held; what this says about DPS-readiness.
- Honest caveats: Alfheim is STILL a proxy (Norwegian pro match, not DPS) but the BEST proxy yet (fixed single cam, full match, GT data); stitch-seam artifacts noted; DPS-specific (kit/court/lighting) still pending real DPS footage.
gitignore: Alfheim video + clips OFF the repo (license/size); commit scripts + notes + the GT-validation numbers + a sample full-match deliverable:
`git commit -m "Day 29: full-match scale-test on Alfheim fixed single-cam (stitched); all 3 deliverables at 45min scale; analytics GT-validated vs ZXY; scale findings"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Clips CONTIGUOUS or gappy? (the gate) — GO/NO-GO
3. Halves stitched cleanly? durations? join quality?
4. Foundation at scale: runtime, peak memory, total ID count, fixed-homography-holds?
5. Analytics TRUST GATE: your distance/speed vs ZXY ground-truth — how close?
6. Events: candidate count over 45min — ranking usable or flood?
7. Player highlights: tagging volume for a full match — viable?
8. What BROKE at scale (the findings)?
9. Errors + time

---

## Do NOT today
- Do NOT stitch before verifying continuity — gappy clips give a broken match (the Part-0 gate).
- Do NOT skip the ZXY trust gate on analytics — it's the first chance to GT-validate distance/speed (huge: plausibility → validated).
- Do NOT use the panorama — single-cam-1 matches the DPS rig (fixed single camera).
- Do NOT run both halves + all deliverables blind — prove 1st half end-to-end first, then scale.
- Do NOT misread stitch-seam glitches as pipeline failures — note them as artifacts.
- Do NOT ignore memory — full-match scale + the Day-26 RAM-exhaustion lesson; process in chunks, monitor.
- Do NOT claim DPS-validation — Alfheim is the BEST proxy yet (fixed cam, full match, GT) but still a proxy; DPS kit/court/lighting pending.
- Do NOT commit Alfheim video/clips (license + size) — keep off the public repo.
