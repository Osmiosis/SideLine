# PRD — Day 8: Football Player Tracking — Baseline (SoccerNet + SportsMOT cross-check)
**Project:** AI Sports Recording & Analytics System
**Goal:** Bring football player tracking to the same measured rigor as basketball. Re-run the proven Day-6 TrackEval harness on football: GT-fed ceiling + soccana-fed real baseline, on SoccerNet-Tracking (primary) and SportsMOT-football (cross-check). Localize the football bottleneck (detection vs association). NO tuning.
**Estimated time:** 3–4 hours (mostly reruns of proven code; data acquisition is the variable)
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo, soccana detector (`models/football.pt`), TrackEval harness + scripts from Day 6 (`track_mot_run.py`, `eval_track.py`)

---

## Context (read first)

Basketball tracking is now measured and improved: Day 6 baselined it (ceiling HOTA 74.05, real 26.62, bottleneck = detection), Day 7 fixed detection (HOTA → 48.50, MOTA -113 → +91, residual gap now association-side). Football tracking has NEVER been measured properly — Day 2's 371-unique-IDs was the misleading proxy on the wrong detector.

This session brings football to parity: a trustworthy HOTA/IDF1 baseline with the bottleneck localized, exactly as Day 6 did for basketball. SoccerNet NDA access is now granted (password received).

**Key difference from basketball:** football detection is ALREADY strong (soccana person AP 0.903, and soccana is trained to detect players/refs sensibly, unlike COCO's grab-everyone person class). So football's real-vs-ceiling gap may be SMALLER and more association-driven from the start — it might skip the detector-fix step basketball needed. The measurement will tell us. Don't assume; measure.

**Scope: FOOTBALL, PLAYERS only, MEASUREMENT only.** Ball tracking (Kalman) and tuning are later. This is a baseline session like Day 6, not an improvement session like Day 7.

---

## NDA constraint (SoccerNet)
SoccerNet-Tracking is under the NDA you signed. It must NEVER touch the public repo — not the data, not committed anywhere public. `.gitignore` already excludes `datasets/`; confirm it holds. The password/credentials go in a local config OUTSIDE the repo (e.g. `~/.soccernet/`), never committed. Scripts and result numbers (HOTA etc.) are fine to share; the raw data is not.

---

## The metrics (same as Day 6)
HOTA (primary), MOTA, IDF1, ID-switches, plus DetA/AssA breakdown (the diagnostic that localizes detection-vs-association). Report all.

### Expected calibration
- SoccerNet-Tracking published ceiling: top methods ~85 HOTA; vanilla ByteTrack well below.
- SportsMOT football: paper found football "relatively easier" than basketball (basketball was hardest at ~60.8 best-method HOTA; football higher).
- So expect football baselines to look BETTER than basketball's did — both because football is easier to track AND because soccana detection is already strong. A higher starting HOTA than basketball's 26.62 is expected and good.

---

## PART A — Acquire football tracking data (~50 min)
**Priority order if time is short: get SoccerNet working first (primary); SportsMOT-football is the cross-check.**

1. **SoccerNet-Tracking:** download via the SoccerNet pip package / their tooling using the granted credentials (password). Pull the TEST or CHALLENGE split with GT tracklets. Use a SUBSET (~5 sequences, 30s each) for runtime — note sequence IDs. Save to `datasets/soccernet_tracking/` (gitignored). Confirm GT format: per-frame, per-object tracklet id + bbox, players.
2. **SportsMOT-football:** you already have SportsMOT on disk from basketball. Locate the FOOTBALL sequences. Pick ~5. These are the cross-check. Save/point to `datasets/sportsmot_football/`.
3. Confirm both have player tracklet GT in the format TrackEval expects (MOTChallenge).

**STOP. Report: SoccerNet acquired (how many seqs, any credential friction)? SportsMOT-football located? GT formats confirmed?**

---

## PART B — Sanity-check GT + harness on BOTH datasets (~30 min)
The harness is proven, but the LABELS are new — verify the trust gate holds on each dataset's format.
1. Visualize GT tracklets (~2 seqs per dataset) with IDs drawn → `outputs/fb_track_gt_sample_*.mp4`. Confirm IDs stay glued to correct players.
2. **TrackEval GT-as-output gate** on each dataset: feed GT in as tracker output → HOTA~1.0, IDF1~1.0, IDsw=0. MUST pass per dataset before trusting that dataset's numbers. (SoccerNet and SportsMOT may have subtly different GT conventions — e.g. coordinate origin, class filtering — so check BOTH, don't assume basketball's pass covers it.)
3. Empty-output degenerate check.

**STOP. Report sanity-gate results per dataset.**

---

## PART C — SoccerNet baselines: ceiling + real (~50 min)
On the SoccerNet subset:
1. **Ceiling:** GT detection boxes (IDs stripped) → default ByteTrack → TrackEval vs GT tracklets. Record HOTA/DetA/AssA/MOTA/IDF1/IDsw.
2. **Real:** soccana (`models/football.pt`) @1280, person class, → default ByteTrack → TrackEval. Record same. Also log unique-ID proxy.
Output → `outputs/track_results/soccernet_{gtdet,soccana}_bytetrack/`.

**STOP. Report SoccerNet ceiling + real metrics.**

---

## PART D — SportsMOT-football cross-check (~40 min)
Repeat Part C on the SportsMOT-football subset (ceiling + real). This is the cross-check: does soccana+ByteTrack behave consistently across two different football footage styles (SoccerNet tactical-cam vs SportsMOT broadcast)?

The comparison that matters:
| Dataset    | Setup            | HOTA | DetA | AssA | MOTA | IDF1 | IDsw |
|------------|------------------|------|------|------|------|------|------|
| SoccerNet  | GT + ByteTrack   |      |      |      |      |      |      |
| SoccerNet  | soccana+ByteTrack|      |      |      |      |      |      |
| SportsMOT  | GT + ByteTrack   |      |      |      |      |      |      |
| SportsMOT  | soccana+ByteTrack|      |      |      |      |      |      |

Key reads:
- Football real HOTA vs basketball's 48.50 (post-fix) and 26.62 (pre-fix) — where does football start?
- Is football's ceiling-vs-real gap detection-driven (DetA gap) or association-driven (AssA gap)? (Hypothesis: more association-driven than basketball, since soccana detection is already strong.)
- Does soccana behave consistently across SoccerNet vs SportsMOT, or does footage style swing it? (Tells us deployment-footage sensitivity.)

---

## PART E — Log, interpret, commit (~30 min)
Append `## Day 8` to notes.md: setup (datasets, seqs, NDA note), sanity gates per dataset, the 4-row baseline table, and interpretation:
- Football real HOTA vs basketball (parity check across sports).
- Detection-vs-association diagnosis for football (DetA gap vs AssA gap) — does football need a detector fix (like basketball did) or go straight to tracker tuning?
- SoccerNet-vs-SportsMOT consistency for soccana — footage-style sensitivity.
- unique-ID proxy vs real IDF1 (re-confirm the proxy lesson on football).
- What the next session targets (likely shared tracker-tuning for BOTH sports, since basketball already needs it).
Then: confirm datasets/track_results/weights/videos gitignored AND SoccerNet data is NOT staged (NDA); commit scripts + notes:
`git commit -m "Day 8: football player tracking baseline (SoccerNet + SportsMOT cross-check); ceiling vs soccana-fed; bottleneck localized"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. SoccerNet acquired? seqs? credential friction? SportsMOT-football located?
3. TrackEval GT-as-output gate: passed on BOTH datasets?
4. The 4-row baseline table (ceiling + real, both datasets)
5. Football real HOTA vs basketball's 48.50 — parity read
6. Football bottleneck: detection-driven or association-driven? (DetA vs AssA gap)
7. soccana consistency across SoccerNet vs SportsMOT?
8. Errors hit (even if fixed)
9. Time taken

---

## Do NOT today
- Do NOT tune the tracker — baseline only (Day-6-style). Tuning is the next session (likely shared across both sports).
- Do NOT hand-roll HOTA/IDF1 — reuse the Day-6 TrackEval harness.
- Do NOT trust any number until GT-as-output gate passes ON THAT dataset (check both — different GT conventions).
- Do NOT do the ball (Kalman, separate) or basketball (already baselined+fixed).
- Do NOT commit SoccerNet data (NDA) or any datasets/track_results/weights/videos. Double-check git status for SoccerNet leakage specifically.
- If short on time: SoccerNet real baseline is the priority; SportsMOT cross-check can slip to next session.
