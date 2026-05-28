# PRD — Day 6 (Pivot): Basketball Player Tracking — Measurement Harness + Honest Baseline
**Project:** AI Sports Recording & Analytics System
**Goal:** Stand up a rigorous multi-object-tracking eval pipeline (SportsMOT basketball + TrackEval, real HOTA/IDF1/MOTA) and establish a verified, sanity-checked baseline for BASKETBALL PLAYER tracking — measured two ways: (1) tracker fed ground-truth detections (ceiling), (2) tracker fed our fine-tuned basketball detector (real deployable number). NO tuning this session.
**Estimated time:** 3–4 hours (realistically measurement + baseline only — correct, mirrors Day 3)
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo, fine-tuned basketball detector (`models/basketball_ft.pt`)

---

## Context (read first)

Pivoted to basketball tracking because SoccerNet (football tracking) access is pending an NDA approval. SportsMOT needs no SoccerNet and covers basketball with real tracklet labels — so we lose no rigor.

Detection status: basketball fine-tuned detector (Day 5) hits ball AP 0.618 OOD, person AP ~0.84. Tracking is unmeasured — Day 2's basketball run showed 268-325 unique IDs (churn) but that was the broken boris-gans detector AND the misleading unique-ID proxy.

**This session = BASKETBALL, PLAYERS only, MEASUREMENT only.** Ball tracking (needs Kalman) and tuning are future sessions.

**Why measurement-first:** unique-ID count is a misleading proxy (low count could mean good tracking OR a tracker merging distinct players). Real metrics (HOTA/IDF1/MOTA) vs ground-truth tracklets are the honest measure — the tracking analogue of the Day 3 detection harness.

**Note:** the harness built today is sport-agnostic. It will be reused for football tracking (SportsMOT football sequences, or SoccerNet when access lands) with near-zero new code.

---

## The metrics
- **HOTA**: primary modern metric; balances detection (DetA) + association (AssA). SportsMOT's main metric.
- **MOTA**: detection-dominated; FPs, misses, ID switches.
- **IDF1**: identity consistency — keeping the SAME id on the SAME player. Most relevant to churn.
- **ID switches**: raw churn count.
Report all four. IDF1 + ID-switches are the churn headline; HOTA is the standard summary.

### Expected-results calibration (from SportsMOT paper — so we're not surprised)
- Basketball is the HARDEST of the 3 sports: best-method HOTA ~60.8, and much lower under pure appearance/motion association.
- SOTA refinement methods reach ~81 HOTA on SportsMOT overall.
- Vanilla ByteTrack will land WELL BELOW these. That's expected and reproduces the paper's finding that basketball association is hard — not a failure.

---

## Datasets & tools
- **SportsMOT** (github.com/MCG-NJU/SportsMOT): 240 clips (basketball/football/volleyball), MOT-format tracklet annotations, 720P/25FPS, sourced from NBA/NCAA/Olympics YouTube. Players-on-court only (excludes spectators/refs/coaches). Likely open (no NDA) — verify. Use the BASKETBALL sequences only today; a SUBSET (~5 sequences) for runtime.
- **TrackEval** (github.com/JonathonLuiten/TrackEval): standard HOTA/MOTA/IDF1 computation from MOTChallenge-format files. Vetted — DO NOT hand-roll tracking metrics.

---

## PART A — Acquire SportsMOT basketball subset + TrackEval (~50 min)
1. Install/clone TrackEval. Read its MOTChallenge input format (gt/gt.txt per seq; tracker output `<seq>.txt`; rows `frame,id,x,y,w,h,conf,-1,-1,-1`).
2. Acquire SportsMOT from the MCG-NJU GitHub (follow their download link — Papers-with-Code / OneDrive / Codalab as they specify). If any registration/agreement is required, PAUSE and ask the developer. Verify whether it's open or gated.
3. Extract the BASKETBALL sequences. Pick a SUBSET (~5 sequences) for this session; note their IDs. Save to `datasets/sportsmot_basketball/`.
4. Confirm structure: each sequence has frames + a GT file with per-frame, per-object tracklet id + bbox (players only).

**STOP. Report: TrackEval installed? SportsMOT basketball subset acquired (how many seqs)? Open or gated? GT format confirmed?**

---

## PART B — Sanity-check GT + eval tool BEFORE trusting it (~30 min)
Same discipline as Day 3 / the football tracking plan.
1. **Visualize GT tracklets:** render ~3 sequences' GT boxes WITH tracklet IDs → `outputs/bball_track_gt_sample_*.mp4`. Developer confirms IDs stay glued to the correct player across frames.
2. **TrackEval self-consistency:** feed GT in AS the tracker output. MUST report HOTA~1.0/100, IDF1~1.0, ID-switches=0, MOTA~1.0. If not perfect, format conversion/wiring is broken — FIX before proceeding.
3. **Degenerate check:** empty tracker output → ~0, no crash.

**STOP. Report sanity-check results. GT-as-output must score ~perfect before any real number means anything.**

---

## PART C — Baseline #1: tracker fed GROUND-TRUTH detections (ceiling) (~40 min)
Isolates pure association ability — how good is ByteTrack if detection were perfect?
1. Take SportsMOT GT detection BOXES (strip identity IDs), feed frame-by-frame into ByteTrack (default `bytetrack.yaml`).
2. ByteTrack assigns its own ids. Write MOTChallenge-format output per seq → `outputs/track_results/bball_gtdet_bytetrack/`.
3. Run TrackEval vs GT tracklets. Record HOTA/MOTA/IDF1/ID-switches (player class).

**STOP. Report GT-fed baseline metrics.**

---

## PART D — Baseline #2: tracker fed OUR DETECTOR (real number) (~40 min)
The real deployable end-to-end system.
1. Run the fine-tuned basketball detector for PLAYERS. NOTE: `models/basketball_ft.pt` is BALL-only (trained on YOLOBball ball class). For PLAYERS use COCO yolov8m person class (Day 5 measured OOD person AP ~0.84) OR whichever model detects basketball players best. Confirm `model.names` and map person/player by NAME. (Do the housekeeping: `cp models/basketball_ft.pt models/basketball.pt` is about the BALL detector; players come from the person detector — keep these straight.)
2. Run the player detector at imgsz=1280 on the SportsMOT basketball subset frames, feed detections into ByteTrack (default), persist across frames.
3. Write MOTChallenge output → `outputs/track_results/bball_detector_bytetrack/`.
4. Run TrackEval vs GT tracklets. Record HOTA/MOTA/IDF1/ID-switches. ALSO record the unique-ID-count proxy to compare against real IDF1 (ties back to Day 2's 268-325 number).

**Key comparison:**
| Setup                              | HOTA | MOTA | IDF1 | ID-switches |
|------------------------------------|------|------|------|-------------|
| GT detections + ByteTrack (ceiling)|      |      |      |             |
| our detector + ByteTrack (real)    |      |      |      |             |
- The GAP localizes the bottleneck: if ceiling is also poor → tracker is the problem; if ceiling good but real poor → detector misses cause churn.

---

## PART E — Log, interpret, commit (~30 min)
Append to `notes.md` a Day 6 section:
```
## Day 6 — [date] — Basketball player tracking: measurement harness + baseline (SportsMOT)

### Setup
- Eval: SportsMOT basketball, [N] seqs [ids], TrackEval (HOTA/MOTA/IDF1/IDsw). Player class only.
- Tracker: ByteTrack default. Player detector for Baseline #2: [which model] @1280.
- (SoccerNet football tracking still pending NDA; SportsMOT used for basketball today. Harness is reusable for football later.)

### Sanity checks
- GT tracklets visualized: IDs stay on correct players [y/n].
- TrackEval GT-as-output: HOTA=__ IDF1=__ IDsw=__ (must be ~perfect) [pass/fail].
- Empty output: ~0, no crash [pass/fail].

### Baselines (player class)
| Setup                              | HOTA | MOTA | IDF1 | ID-switches | unique-ID proxy |
|------------------------------------|------|------|------|-------------|-----------------|
| GT detections + ByteTrack (ceiling)|      |      |      |             | n/a             |
| our detector + ByteTrack (real)    |      |      |      |             |                 |

### Interpretation
- Ceiling vs real gap: ___ → next effort belongs in [tracker / detector].
- IDF1 vs unique-ID proxy: how misleading was the Day-2 268-325 number? ___
- vs SportsMOT published basketball ceiling (~60.8 HOTA best, ~81 SOTA overall): where does vanilla ByteTrack land? ___
- Reproduced the paper's finding that basketball is the hardest sport to track? ___

### Next sessions (NOT today)
- Tune ByteTrack thresholds for sports fast-motion; try BoT-SORT (appearance) vs ByteTrack; re-measure vs this baseline.
- Football tracking: reuse this harness on SportsMOT football seqs / SoccerNet when access lands.
- Ball tracking: separate session, Kalman-based.
```
Then: confirm `datasets/`, `outputs/track_results/`, weights, videos gitignored; commit scripts + notes:
`git commit -m "Day 6: basketball player tracking eval harness (SportsMOT + TrackEval HOTA/IDF1); GT-fed + detector-fed ByteTrack baselines"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. SportsMOT acquired? how many basketball seqs? open or gated?
3. TrackEval GT-as-output sanity: ~perfect? (trust gate)
4. Baseline table: HOTA/MOTA/IDF1/IDsw, GT-fed AND detector-fed
5. Ceiling-vs-real gap: next effort → tracker or detector?
6. How misleading was the unique-ID proxy vs real IDF1?
7. Where does vanilla ByteTrack land vs SportsMOT's ~60.8 basketball ceiling?
8. Errors hit (even if fixed)
9. Time taken

---

## Do NOT today
- Do NOT tune the tracker — measurement + baseline only. Tuning is a deliberate next session.
- Do NOT hand-roll HOTA/MOTA/IDF1 — use TrackEval (vetted; tracking metrics are very error-prone by hand).
- Do NOT trust any tracking number until TrackEval scores GT-as-output ~perfect.
- Do NOT do the ball this session (needs Kalman, separate problem) — players only.
- Do NOT do football this session — basketball pivot today; football harness-reuse later.
- Do NOT commit datasets, track_results, weights, or videos.
