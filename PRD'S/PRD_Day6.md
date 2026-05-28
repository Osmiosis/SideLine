# PRD — Day 6: Football Tracking — Measurement Harness + Honest Baseline
**Project:** AI Sports Recording & Analytics System
**Goal:** Stand up a rigorous multi-object-tracking evaluation pipeline (SoccerNet-Tracking + TrackEval, real HOTA/IDF1/MOTA) and establish a verified, sanity-checked baseline for PLAYER tracking — measured two ways: (1) tracker fed ground-truth detections (ceiling), (2) tracker fed our own detector (real deployable number). NO tuning this session.
**Estimated time:** 3–4 hours (realistically measurement + baseline only — this is correct, mirrors Day 3)
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo, soccana football detector

---

## Context (read first)

Day 2 surfaced severe tracking churn: 371 unique IDs for ~25 football players using vanilla ByteTrack on default settings. That run was also on the wrong (uisikdag) detector. Detection is now solved (soccana, ball AP 0.474, person AP 0.903). Tracking is the parked bottleneck — everything downstream (distance, heatmaps, possession, player highlights) needs stable per-player identity across frames.

The literature confirms this is genuinely hard: SoccerNet-Tracking authors state player/ball tracking in soccer is "far from solved" under fast motion/occlusion; vanilla ByteTrack/DeepSORT/FairMOT all struggle. Top published methods reach ~85 HOTA; vanilla ByteTrack sits well below. So the realistic goal is meaningful improvement later — but FIRST we need to measure honestly.

**This session = PLAYERS only, FOOTBALL only, MEASUREMENT only.** Ball tracking (needs Kalman) and tuning are explicitly future sessions. Basketball tracking is after football.

**Why measurement-first:** unique-ID-count is a misleading proxy (40 IDs could be good tracking OR a tracker lazily merging distinct players). Real tracking metrics (HOTA/IDF1/MOTA) against ground-truth tracklets are the honest measure — the tracking equivalent of the Day 3 detection harness.

---

## The metrics (what we're computing and why)

- **HOTA** (Higher Order Tracking Accuracy): the modern primary metric; balances detection accuracy (DetA) and association accuracy (AssA). SoccerNet's main metric.
- **MOTA** (Multi-Object Tracking Accuracy): older, detection-dominated; counts false positives, misses, ID switches.
- **IDF1**: identity-focused; how consistently a tracker keeps the SAME id on the SAME player. This is the one most relevant to our churn problem.
- **ID switches**: raw count of times a track changes identity. Directly measures churn.

We report all four. IDF1 + ID-switches are the churn-relevant headline; HOTA is the standard summary.

---

## Datasets & tools

- **SoccerNet-Tracking**: 200 sequences x 30s, fully annotated with bounding boxes + tracklet IDs, single tactical-view footage (matches our use case). Has a public test/challenge split. Access via the SoccerNet pip package / their GitHub (github.com/SoccerNet/sn-tracking). May require the SoccerNet download (NDA-style agreement form, free — the developer may need to register and accept terms; PAUSE and ask if so).
  - To keep runtime sane, use a SUBSET (e.g. 5–10 of the 30s sequences) for this baseline. Note which sequences.
- **TrackEval** (github.com/JonathonLuiten/TrackEval): the standard tool that computes HOTA/MOTA/IDF1 from MOTChallenge-format files. This is the vetted metric implementation — DO NOT hand-roll tracking metrics (far more error-prone than detection metrics).

---

## PART A — Acquire SoccerNet-Tracking subset + TrackEval (~50 min)

1. Install/clone TrackEval. Read its expected input format (MOTChallenge format: `gt/gt.txt` per sequence, and tracker output as `<seq>.txt`, both with rows: `frame,id,x,y,w,h,conf,-1,-1,-1`).
2. Acquire SoccerNet-Tracking. Prefer the official sn-tracking package. If it requires registering + accepting a data agreement, PAUSE and ask the developer to do that (don't automate credential/agreement acceptance).
3. Download a SUBSET — enough sequences for a meaningful number, few enough to run in this session (start with ~5 sequences from the test/challenge set; note their IDs). Save to `datasets/soccernet_tracking/`.
4. Confirm structure: each sequence has frames + a ground-truth file with per-frame, per-object id + bbox. Confirm the GT includes player tracklet IDs.

**STOP. Report: TrackEval installed? SoccerNet-Tracking subset acquired (how many sequences)? GT format confirmed?**

---

## PART B — Sanity-check the GT and the eval tool BEFORE trusting it (~30 min)

Same discipline as Day 3. A tracking harness that's silently wrong produces clean-looking fake HOTA.

1. **Visualize GT tracklets:** render ~3 sequences' ground-truth boxes WITH their tracklet IDs drawn, as a short video or frame strip → `outputs/track_gt_sample_*.mp4/png`. Developer confirms: do the GT IDs stay glued to the correct player across frames? (Confirms we're reading tracklet labels correctly.)
2. **TrackEval self-consistency check:** feed the GROUND TRUTH in as if it were the tracker's OUTPUT. TrackEval MUST report HOTA ~ 1.0 / 100, IDF1 ~ 1.0, ID-switches = 0, MOTA ~ 1.0. If a perfect tracker doesn't score perfectly, the format conversion or eval wiring is broken — FIX before proceeding.
3. **Degenerate check:** feed empty tracker output → metrics ~0, no crash.

**STOP. Report sanity-check results. GT-as-tracker-output must score ~perfect before any real number means anything.**

---

## PART C — Baseline #1: tracker fed GROUND-TRUTH detections (the ceiling) (~40 min)

This isolates pure tracking/association ability — how good is ByteTrack if detection were perfect?

1. Take the SoccerNet-Tracking GT detection BOXES (positions only, strip the identity IDs) and feed them frame-by-frame into ByteTrack (default `bytetrack.yaml`).
2. ByteTrack assigns its OWN ids. Write output in MOTChallenge format per sequence → `outputs/track_results/gtdet_bytetrack/`.
3. Run TrackEval on these vs the GT tracklets.
4. Record HOTA / MOTA / IDF1 / ID-switches. Restrict to the PERSON/player class.

This number is the tracking-association ceiling for vanilla ByteTrack on this footage.

**STOP. Report the GT-fed baseline metrics.**

---

## PART D — Baseline #2: tracker fed OUR DETECTOR (the real number) (~40 min)

This is the real deployable end-to-end system.

1. Run soccana (`models/football.pt`) at imgsz=1280 on the SoccerNet-Tracking subset frames, person class, feeding detections into ByteTrack (default config), persist across frames.
2. Write tracker output in MOTChallenge format → `outputs/track_results/soccana_bytetrack/`.
3. Run TrackEval vs GT tracklets. Record HOTA / MOTA / IDF1 / ID-switches (person class).
4. Also record the unique-ID-count proxy here, so we can later see how badly the proxy diverges from real IDF1 (ties back to the Day-2 371-ID number).

**The key comparison:**
| Setup                          | HOTA | MOTA | IDF1 | ID-switches |
|--------------------------------|------|------|------|-------------|
| GT detections + ByteTrack (ceiling) |   |   |   |   |
| soccana + ByteTrack (real)          |   |   |   |   |

- The GAP between ceiling and real tells us whether future effort belongs in the TRACKER (if ceiling is also poor) or the DETECTOR (if ceiling is good but real is poor).

---

## PART E — Log, interpret, commit (~30 min)

Append to `notes.md` a Day 6 section:
```
## Day 6 — [date] — Football player tracking: measurement harness + baseline

### Setup
- Eval: SoccerNet-Tracking, [N] sequences [list ids], TrackEval (HOTA/MOTA/IDF1/IDsw). Person/player class only.
- Tracker: ByteTrack default (bytetrack.yaml). Detector for Baseline #2: soccana @1280.

### Sanity checks
- GT tracklets visualized: IDs stay on correct players [y/n].
- TrackEval GT-as-output: HOTA=__ IDF1=__ IDsw=__ (must be ~perfect) [pass/fail].
- Empty output: ~0, no crash [pass/fail].

### Baselines (person/player class)
| Setup                              | HOTA | MOTA | IDF1 | ID-switches | unique-ID proxy |
|------------------------------------|------|------|------|-------------|-----------------|
| GT detections + ByteTrack (ceiling)|      |      |      |             | n/a             |
| soccana + ByteTrack (real)         |      |      |      |             |                 |

### Interpretation
- Ceiling vs real gap: ___ . Implies next effort belongs in [tracker / detector].
- IDF1 vs unique-ID-count proxy: how misleading was the Day-2 371-ID number? ___
- vs published SoccerNet ceiling (~85 HOTA top methods): where does vanilla ByteTrack land? ___

### Next session (tuning — NOT done today)
- Tune ByteTrack thresholds (track_high_thresh, track_low_thresh, match_thresh, new_track_thresh, track_buffer/max_age) for sports fast-motion.
- Consider BoT-SORT (appearance features) vs ByteTrack.
- Re-measure against this baseline.
```
Then: confirm `datasets/`, `outputs/track_results/`, `*.pt`, videos gitignored; commit scripts + notes:
`git commit -m "Day 6: football player tracking eval harness (TrackEval HOTA/IDF1/MOTA); GT-fed + detector-fed ByteTrack baselines"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. SoccerNet-Tracking acquired? how many sequences? any registration/agreement friction?
3. TrackEval GT-as-output sanity: HOTA/IDF1 ~ perfect? (the trust gate)
4. Baseline table: HOTA/MOTA/IDF1/IDsw for GT-fed AND soccana-fed
5. Ceiling-vs-real gap read: next effort → tracker or detector?
6. How misleading was the unique-ID proxy vs real IDF1?
7. Errors hit (even if fixed)
8. Time taken

---

## Do NOT today
- Do NOT tune the tracker — measurement + baseline only. Tuning is next session (rushing measurement is the one thing this project has taught us not to do).
- Do NOT hand-roll HOTA/MOTA/IDF1 — use TrackEval (vetted). Hand-rolled tracking metrics are very error-prone.
- Do NOT trust any tracking number until TrackEval scores GT-as-output ~perfect.
- Do NOT do the ball this session (needs Kalman, separate problem) — players only.
- Do NOT do basketball this session — football first.
- Do NOT commit datasets, track_results, weights, or videos.
