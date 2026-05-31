# Football CV Pipeline — Backend Integration Map
**Date:** 2026-05-31  
**Purpose:** Exact chain from raw mp4 → coach_analytics + event_highlights for backend wrapping.

---

## Per-script reference

### track_alfheim.py

**CLI args:**
```
--video      (required) path to mp4 or frame folder; passed directly to model.track(source=)
--out        (required) output MOT .txt path
--model      default="models/soccana.pt"
--imgsz      default=1280
--tracker    default="botsort.yaml"
--classes    default="0"  (0=player; pass "0,1" to also track ball)
--vid-stride default=1
--device     default="0"
--flush-every default=2000
```

**Inputs:** mp4 video file directly (passed to `model.track(source=args.video, stream=True)`). Does NOT need a frame folder. No SoccerNet coupling.

**Outputs:**
- `<out>.txt` — MOT format: `frame,tid,x,y,w,h,conf,-1,-1,-1` (top-left xywh, 1-indexed frames)
- `<out>.stats.json` — runtime/VRAM/fps/unique-ID stats

**Upstream deps:** None (first stage). Needs `models/soccana.pt`.

**GT coupling:** NONE. Runs purely on the video.

**Backend job dir adaptation:** Pure CLI — pass `--video jobs/<id>/video.mp4 --out jobs/<id>/outputs/tracks/players.txt`. No code change needed.

---

### build_det_cache.py

**CLI args:**
```
--detector   (required) YOLO .pt path
--source     (required) dataset root containing seq dirs with seqinfo.ini + img1/
--out        (required) cache output dir
--class-name default="player"
--imgsz      default=1280
--conf       default=0.25
--only       optional list of seq names
```

**Inputs:** Frame folder structure: `<source>/<seq>/img1/<frame:06d>.jpg` + `seqinfo.ini`.  
**HARD REQUIRES `seqinfo.ini`** to know frame count/imDir/imExt.

**Outputs:** `<out>/<seq>.txt` — one line per detection: `frame,x,y,w,h,conf` (top-left, 1-indexed)

**GT coupling:** NONE (no GT data read). But REQUIRES `seqinfo.ini` in each seq directory.

**Note:** This is the SoccerNet-era frame-folder-only pipeline. `track_alfheim.py` is the replacement that tracks directly from an mp4 and does NOT need this cache. The football chain uses `track_alfheim.py`, not `build_det_cache.py` + `track_botsort_from_cache.py`.

---

### track_botsort_from_cache.py

**CLI args:**
```
--cache   (required) dir of cached detection .txt files
--source  (required) dataset root (needs seqinfo.ini + img1/ for GMC frames)
--out     (required) output MOT dir
--param   repeatable key=value tracker overrides
```

**Inputs:** Detection cache `.txt` + frame JPGs (for GMC optical-flow). Needs `seqinfo.ini`.

**Outputs:** `<out>/<seq>.txt` — MOT format identical to track_alfheim output.

**GT coupling:** NONE. But needs frame folder + seqinfo.ini.

**Note:** SoccerNet-era path. Not needed for new video → use `track_alfheim.py` directly.

---

### analyze_ball.py

**CLI args:**
```
seq          positional, optional (omit → run all 5 SEQS_DEFAULT)
--cache-dir  default="outputs/det_cache/sn_ball"
--zip        default="datasets/soccernet_gsr/test.zip"   ← GT ZIP
--source     default="datasets/soccernet_tracking"       ← for seqinfo.ini + img1/
--out        default="outputs/ball_track"
--vel-gate   default=80.0 px/frame
--max-gap    default=15
--init-conf  default=0.35
--aerial-thresh default=25.0
--tol-px     default=50.0
```

**Inputs:**
1. Ball detection cache: `<cache-dir>/<seq>.txt` (frame,x,y,w,h,conf top-left)
2. `seqinfo.ini` at `<source>/<seq>/seqinfo.ini` — **needed for n_frames** (line 333-334)
3. GT zip `datasets/soccernet_gsr/test.zip` — used for (a) GT validation metrics AND (b) **`derive_per_frame_H()` to get pitch projection H** (line 354-356)
4. Frame JPGs for sample render: `<source>/<seq>/img1/<frame:06d>.jpg`

**Outputs:** `<out>/<seq>/trajectory.json`, `validation.json`, `sample_frame.png`

**GT couplings:**
- `load_gt()` + `derive_per_frame_H()` (line 354-355): GT zip required to derive the per-frame homography H used to project ball to pitch metres. **DELIVERABLE-CRITICAL** — pitch_x_m/pitch_y_m fields in trajectory.json feed coach_deliverable + detect_events.
- `load_ball_gt()` + `validate()` (lines 339-363): validation-only RMSE metrics. **Skippable** for production.
- `seqinfo.ini` n_frames read (line 333-334): **required** unless n_frames is inferred from cache length.

**Backend blocker:** Needs replacement H source (homography.json from mark_court.py) instead of `derive_per_frame_H()`. See GT/SoccerNet couplings section.

---

### analyze_pitch.py

**CLI args:**
```
seq          (required) positional, e.g. SNGS-116
--zip        default="datasets/soccernet_gsr/test.zip"   ← GT ZIP
--tracker    default="outputs/track_results/sn_soccana_botsort_gmc"
--out        default="outputs/deliverables"
--smooth-win default=5
--top-n-players default=4
```

**Inputs:**
1. Tracker MOT: `<tracker>/<seq>.txt`
2. GT zip — **fully required** for `load_gt()` → `derive_per_frame_H()`. This IS the deliverable computation, not just validation.

**Outputs:** `<out>/<seq>/positions.json`, `distances.json`, `validation.json`, `heatmap_team.png`, `heatmap_player<ID>.png`

**GT coupling (DELIVERABLE-CRITICAL):**  
- `derive_per_frame_H()` called at line 227. All pitch projections and distance calculations depend on H derived from GT. Cannot skip.  
- GT-distance comparison (line 254-263): validation-only, skippable.

**Backend blocker:** Must replace GT-derived H with homography.json from mark_court.py. See GT/SoccerNet couplings section.

**Also exports** helper functions `load_gt`, `derive_per_frame_H`, `project_tracker`, `render_heatmap`, `PITCH_X_HALF`, `PITCH_Y_HALF` — imported by team_assign, analyze_ball, follow_cam, compute_possession.

---

### compute_possession.py

**CLI args:**
```
seq              positional, optional
--zip            default="datasets/soccernet_gsr/test.zip"  ← GT ZIP
--source         default="datasets/soccernet_tracking"
--tracker-dir    default="outputs/track_results/sn_soccana_botsort_gmc"
--ball-track-dir default="outputs/ball_track"
--team-assign-dir default="outputs/team_assign"
```

**Inputs:**
1. Ball trajectory JSON: `<ball-track-dir>/<seq>/trajectory.json`
2. Tracker MOT: `<tracker-dir>/<seq>.txt`
3. GT zip → `derive_per_frame_H()` for projecting player feet to pitch (line 84-85)
4. `track_teams.json` from team_assign

**Outputs:** `<ball-track-dir>/<seq>/possession.json`, `possession_timeline.png`

**GT coupling:** `derive_per_frame_H()` called at line 84-85. Needed to project player feet to pitch metres for proximity-to-ball calculation. **DELIVERABLE-CRITICAL**.

---

### team_assign.py

**CLI args:**
```
--k              default=2
--feature-mode   default="ab"
--non-outfield-abs-threshold default=20.0
--non-outfield-percentile  optional
--tracker-dir    default="outputs/track_results/sn_soccana_botsort_gmc"
--zip            default="datasets/soccernet_gsr/test.zip"  ← GT ZIP
--data-root      default="datasets/soccernet_tracking"
--out            default="outputs/team_assign"
--sample-seq     default="SNGS-118"
--sample-frame   default=100
```

**Inputs:**
1. Tracker MOT files: `<tracker-dir>/<SNGS-XXX>.txt` for all 5 hardcoded SEQS
2. Frame JPGs: `<data-root>/<seq>/img1/<frame:06d>.jpg` — **reads actual frame pixels** for torso crop colors
3. GT zip: used for (a) `gt_by_frame()` IoU-matching for validation AND (b) `render_team_heatmaps()` which calls `derive_per_frame_H()`

**CRITICAL HARD COUPLING:** `SEQS = ["SNGS-116", "SNGS-117", "SNGS-118", "SNGS-119", "SNGS-120"]` is **hardcoded at line 36** — the script always processes exactly these 5 sequences. No CLI arg to change them.

**Outputs:**
- `track_teams.json` — `{seq: {tid: {role, majority_cluster, ...}}}` — key downstream input
- `cluster_summary.json`, `torso_features.npz`, `validation.json`, sample renders

**GT couplings:**
- Validation (Part D, line 514): calls `validate()` with GT zip — validation only, **skippable**.
- `render_team_heatmaps()` (line 508-510): calls `derive_per_frame_H()` — render only, **skippable**.
- Core torso-color clustering (Parts A/B/C): reads frame pixels from `img1/` + tracker MOT, NO GT needed.

**Backend blocker (major):** Hardcoded SEQS list and `--data-root` pointing at SoccerNet `img1/` folders. Needs code edit to accept a single-seq mode with a custom frames dir. Minimal fix: add `--seqs` arg + `--frames-dir` to override, or run with custom `--data-root` pointing to `jobs/<id>/frames` where the seq folder is named appropriately.

---

### coach_deliverable.py

**CLI args:**
```
seq              positional, default="SNGS-118"
--deliverables   default="outputs/deliverables"   ← positions.json + distances.json + validation.json
--ball-dir       default="outputs/ball_track"     ← trajectory.json + possession.json
--team-assign    default="outputs/team_assign/track_teams.json"
--track-dir      default="outputs/track_results/sn_soccana_botsort_gmc"  ← MOT .txt
--frames         default="datasets/soccernet_tracking"   ← frame JPGs for tactical video
--no-video
--video-secs     optional
--contact-only
--full-video
--sample-secs    default=10
--sample-scale   default=0.5
```

**Inputs (all from prior stages):**
1. `<deliverables>/<seq>/positions.json` — from analyze_pitch
2. `<deliverables>/<seq>/distances.json` — from analyze_pitch
3. `<deliverables>/<seq>/validation.json` — from analyze_pitch (contains GT-error metadata + distance totals)
4. `<team-assign>` (track_teams.json) — from team_assign
5. `<ball-dir>/<seq>/possession.json` — from compute_possession
6. `<ball-dir>/<seq>/trajectory.json` — from analyze_ball
7. `<track-dir>/<seq>.txt` — MOT player tracks
8. `<frames>/<seq>/img1/<frame:06d>.jpg` — source frames for tactical overlay video

**Outputs:** `<deliverables>/<seq>/coach/metrics.json`, `fig_heatmap_A/B.png`, `fig_formation.png`, `fig_territory.png`, `fig_compactness.png`, `fig_intensity.png`, `coach_analysis.pdf`, `tactical_sample.mp4`, `tactical_contact_sheet.png`

**GT coupling:**
- `validation.json` is consumed at line 365 for `team_distance_vs_gt_pct` and `homography_median_err_m`. These are inserted INTO the PDF as accuracy metadata. They will simply be None/missing if validation.json lacks those fields. **Skippable** — the analytics still render; only the "checked vs ground truth" footnote in the PDF will be absent.
- Frames are read from `<frames>/<seq>/img1/` — **requires numbered JPG frame folder**.

**Backend adaptation:** All pure CLI args — point `--deliverables`, `--ball-dir`, `--team-assign`, `--track-dir`, `--frames` at job dirs. No code change needed.

---

### detect_events.py

**CLI args:**
```
seq              positional, optional
--ball-dir       default="outputs/ball_track"
--track-dir      default="outputs/track_results/sn_soccana_botsort_gmc"
--team-json      default="outputs/team_assign/track_teams.json"
--zip            default="datasets/soccernet_gsr/test.zip"  ← GT ZIP
--out            default="outputs/events"
--ball-teleport-mps default=40.0
```

**Inputs:**
1. Ball trajectory: `<ball-dir>/<seq>/trajectory.json`
2. Player MOT: `<track-dir>/<seq>.txt`
3. Team assignments: `<team-json>` (track_teams.json)
4. GT zip: `load_action_label()` at line 89-101 — reads `info.action_class`, `action_position`, `clip_start`, `frame_rate` for the labeled event frame

**Outputs:** `<out>/<seq>/features.json`, `events.json`, `features_plot.png`

**GT coupling:**
- `load_action_label()` (line 559): reads clip-level action label from GSR zip. Used only for plausibility printout and `features_plot.png` magenta marker + `events.json.label` field. **Skippable** — the event detection itself (shots, transitions, tackles, stoppages) runs purely on motion features. Set `--zip` to a non-existent path; `load_action_label()` catches the exception and returns `{action_class: None, approx_frame: None}`.

**Backend adaptation:** All CLI args. Pass `--zip ""` or a dummy path to skip label. No code change for the core pipeline.

---

### follow_cam.py

**CLI args:**
```
seq              positional, optional
--ball-dir       default="outputs/ball_track"
--track-dir      default="outputs/track_results/sn_soccana_botsort_gmc"
--source         default="datasets/soccernet_tracking"   ← img1/ frame JPGs
--gt-zip         default="datasets/soccernet_gsr/test.zip"  ← GT ZIP (optional)
--out            default="outputs/follow_cam"
--fps            default=25
--zoom           default=2.5
--out-w          default=1280
--out-h          default=720
... (smoothing + pan-limit args)
--render / --no-render
```

**Inputs:**
1. Ball trajectory: `<ball-dir>/<seq>/trajectory.json`
2. Player MOT: `<track-dir>/<seq>.txt`
3. Frame JPGs: `<source>/<seq>/img1/<frame:06d>.jpg` — reads `000001.jpg` for frame dimensions (line 447), then renders contact sheet / video

**Outputs:** `<out>/<seq>/follow_cam.json` (A/B/C crop-center paths), `metrics.json`, `path_plot.png`, `speed_plot.png`, `contact_sheet_C.png`, `abc_frames.png`, optionally `follow_C.mp4`, `abc_montage.mp4`

**GT coupling:**
- `--gt-zip`: calls `load_ball_gt()` to load pixel GT ball positions for a "GT-ball-in-crop" metric. Used ONLY for the metrics table. Wrapped in try/except (line 456-460). **Fully skippable** — pass `--gt-zip ""` or any missing path.

**Backend adaptation:** Pure CLI. Point `--source jobs/<id>/frames --ball-dir jobs/<id>/outputs/ball_track --track-dir jobs/<id>/outputs/tracks`.

---

### clip_highlights.py

**CLI args:**
```
seq              positional, optional
--events-dir     default="outputs/events"
--follow-dir     default="outputs/follow_cam"
--source         default="datasets/soccernet_tracking"   ← img1/ frame JPGs
--out            default="outputs/deliverables/event_highlights_football"
--clip-w         default=854
--clip-h         default=480
--no-clips
--reel-top       default=8
```

**Inputs:**
1. Events JSON: `<events-dir>/<seq>/events.json`
2. Follow-cam JSON: `<follow-dir>/<seq>/follow_cam.json` — A-variant crop centers
3. Frame JPGs: `<source>/<seq>/img1/<frame:06d>.jpg`

**Outputs:** Per-moment clips at `<events-dir>/<seq>/clips/`, `<out>/index.json`, `index.md`, `contact_<seq>.jpg`, `auto_draft_reel.mp4`, `sample_highlight.mp4`

**GT coupling:** NONE. Reads `events.json["label"]` for `covers_gsr_label` field in index — this is just metadata annotation in the index, not needed for clipping.

**Backend adaptation:** Pure CLI. All paths configurable.

---

### mark_court.py

**CLI args:**
```
seq              (required) positional — sequence/job name
--frame          default=540  — which frame to use for calibration
--frames-root    default="datasets/sportsmot_basketball"
--model          default="ncaa" choices=["ncaa","fiba"]  (basketball court models)
--out            default="outputs/deliverables"
```

**NOTE:** This is a **basketball calibration tool** (GUI app for clicking court landmarks). It produces `homography.json` for basketball. For football, there is no equivalent `mark_pitch.py`.

**homography.json shape (from line 226-235):**
```json
{
  "seq": "...", "frame": 540, "model": "ncaa",
  "H_img_from_court": [[...3x3 matrix as nested list...]],
  "H_court_from_img": [[...3x3 matrix as nested list...]],
  "points": [{"name": "...", "img": [x, y], "court": [x, y]}, ...],
  "method": "MANUAL marking (human-clicked)",
  "n_clicked": N, "n_used": N,
  "pruned_outliers": [...],
  "holdout_mean_err_m": float,
  "holdout_errs": [...],
  "landmark_recon_err_m": [...],
  "landmark_recon_mean_m": float
}
```

**For football:** The 4 user-provided calibration points must produce an equivalent homography.json with `H_img_from_court` (= H from pixel → pitch metres, or its inverse). The key matrix consumed by downstream scripts is passed to `cv2.perspectiveTransform()` to map pixel coords to pitch metres.

---

## Chain: coach_analytics

Ordered stages + exact backend commands (job dir = `jobs/<id>/`):

```
STAGE 1 — decode (backend pre-step)
  ffmpeg -i jobs/<id>/video.mp4 -q:v 2 jobs/<id>/frames/<jobid>/img1/%06d.jpg
  # creates 6-digit JPG frame folder expected by all downstream scripts
  # Also write jobs/<id>/frames/<jobid>/seqinfo.ini with seqLength + frameRate

STAGE 2 — player tracking (track_alfheim.py)
  python scripts/track_alfheim.py \
    --video jobs/<id>/video.mp4 \
    --out jobs/<id>/outputs/tracks/players.txt \
    --model models/soccana.pt \
    --classes 0
  # output: MOT .txt (players, 1-indexed frames, top-left xywh)

STAGE 3 — ball detection cache (build_det_cache.py)  [NEEDED for analyze_ball]
  python scripts/build_det_cache.py \
    --detector models/soccana.pt \
    --source jobs/<id>/frames \
    --out jobs/<id>/outputs/det_cache/ball \
    --class-name ball \
    --only <jobid>
  # requires <jobid>/img1/ + seqinfo.ini frame folder layout
  # output: jobs/<id>/outputs/det_cache/ball/<jobid>.txt

STAGE 4 — ball Kalman + pitch projection (analyze_ball.py)  [REQUIRES H FIX]
  python scripts/analyze_ball.py <jobid> \
    --cache-dir jobs/<id>/outputs/det_cache/ball \
    --source jobs/<id>/frames \
    --out jobs/<id>/outputs/ball_track
  # *** GT COUPLING TO BREAK: replace derive_per_frame_H(load_gt(zip)) with
  #     load H from jobs/<id>/homography.json ***

STAGE 5 — player pitch projection + distances (analyze_pitch.py)  [REQUIRES H FIX]
  python scripts/analyze_pitch.py <jobid> \
    --tracker jobs/<id>/outputs/tracks \
    --out jobs/<id>/outputs/deliverables
  # *** GT COUPLING TO BREAK: same H replacement ***

STAGE 6 — team assignment (team_assign.py)  [REQUIRES CODE EDIT]
  python scripts/team_assign.py \
    --tracker-dir jobs/<id>/outputs/tracks \
    --data-root jobs/<id>/frames \
    --out jobs/<id>/outputs/team_assign \
    --sample-seq <jobid>
  # *** HARDCODED SEQS = [...] MUST BE REPLACED with --seqs <jobid> arg ***
  # *** Validation (--zip) should be skipped/mocked ***

STAGE 7 — possession (compute_possession.py)  [REQUIRES H FIX]
  python scripts/compute_possession.py <jobid> \
    --source jobs/<id>/frames \
    --tracker-dir jobs/<id>/outputs/tracks \
    --ball-track-dir jobs/<id>/outputs/ball_track \
    --team-assign-dir jobs/<id>/outputs/team_assign
  # *** GT COUPLING: derive_per_frame_H must be replaced with homography.json H ***

STAGE 8 — coach deliverable (coach_deliverable.py)
  python scripts/coach_deliverable.py <jobid> \
    --deliverables jobs/<id>/outputs/deliverables \
    --ball-dir jobs/<id>/outputs/ball_track \
    --team-assign jobs/<id>/outputs/team_assign/track_teams.json \
    --track-dir jobs/<id>/outputs/tracks \
    --frames jobs/<id>/frames \
    --no-video   # or --contact-only for fast version
  # output: PDF + metrics.json + heatmaps in outputs/deliverables/<jobid>/coach/
```

**Deliverables produced:**
- `jobs/<id>/outputs/deliverables/<jobid>/coach/coach_analysis.pdf`
- `jobs/<id>/outputs/deliverables/<jobid>/coach/metrics.json`
- `jobs/<id>/outputs/deliverables/<jobid>/coach/tactical_contact_sheet.png`
- `jobs/<id>/outputs/deliverables/<jobid>/coach/tactical_sample.mp4` (if video enabled)

---

## Chain: event_highlights

Shares stages 1–6 with coach_analytics. From stage 6 onwards:

```
STAGE 6 — team assignment (same as above)

STAGE 9 — event detection (detect_events.py)
  python scripts/detect_events.py <jobid> \
    --ball-dir jobs/<id>/outputs/ball_track \
    --track-dir jobs/<id>/outputs/tracks \
    --team-json jobs/<id>/outputs/team_assign/track_teams.json \
    --zip ""     # skip GT label (catches exception gracefully) \
    --out jobs/<id>/outputs/events
  # output: events/<jobid>/features.json + events.json

STAGE 10 — follow-cam (follow_cam.py)
  python scripts/follow_cam.py <jobid> \
    --ball-dir jobs/<id>/outputs/ball_track \
    --track-dir jobs/<id>/outputs/tracks \
    --source jobs/<id>/frames \
    --gt-zip ""  # skip GT metric \
    --out jobs/<id>/outputs/follow_cam \
    --no-render  # skip mp4, just produce follow_cam.json
  # output: follow_cam/<jobid>/follow_cam.json

STAGE 11 — clip highlights (clip_highlights.py)
  python scripts/clip_highlights.py <jobid> \
    --events-dir jobs/<id>/outputs/events \
    --follow-dir jobs/<id>/outputs/follow_cam \
    --source jobs/<id>/frames \
    --out jobs/<id>/outputs/event_highlights
  # output: per-moment clips + index.json + contact sheets + auto_draft_reel.mp4
```

**Deliverables produced:**
- `jobs/<id>/outputs/event_highlights/index.json`
- `jobs/<id>/outputs/event_highlights/index.md`
- `jobs/<id>/outputs/event_highlights/contact_<jobid>.jpg`
- `jobs/<id>/outputs/event_highlights/auto_draft_reel.mp4`
- `jobs/<id>/outputs/event_highlights/sample_highlight.mp4`
- `jobs/<id>/outputs/events/<jobid>/clips/*.mp4`

---

## Shared foundation

Stages 1–6 are shared by both deliverables:

| Stage | Script | Shared output |
|-------|--------|---------------|
| 1 | ffmpeg decode | `frames/<jobid>/img1/%06d.jpg` + `seqinfo.ini` |
| 2 | track_alfheim.py | `tracks/players.txt` (MOT) |
| 3 | build_det_cache.py | `det_cache/ball/<jobid>.txt` |
| 4 | analyze_ball.py | `ball_track/<jobid>/trajectory.json` + `possession.json` |
| 5 | analyze_pitch.py | `deliverables/<jobid>/positions.json` + `distances.json` |
| 6 | team_assign.py | `team_assign/track_teams.json` |

Coach chain adds: compute_possession → coach_deliverable  
Highlights chain adds: detect_events → follow_cam → clip_highlights

---

## GT/SoccerNet couplings to break

### 1. analyze_ball.py — H from GT (DELIVERABLE-CRITICAL)

**Lines 354-356:**
```python
gt_pts = load_gt(Path(args.zip), seq)
H_by_frame, _ = derive_per_frame_H(gt_pts)
records = project_trajectory(records, H_by_frame, ...)
```
This derives a per-frame homography from GT correspondences. The resulting `pitch_x_m` / `pitch_y_m` fields in `trajectory.json` feed every downstream analytics step.

**Fix:** Add `--homography` arg. When provided, load a single static H from `homography.json["H_court_from_img"]` (3×3 matrix) and use it for all frames instead of the per-frame GT H. The pitch projection call is already factored into `project_trajectory(records, H_by_frame)` — replace `H_by_frame` with `{f: H_static for f in range(1, n+1)}`.

### 2. analyze_pitch.py — H from GT (DELIVERABLE-CRITICAL)

**Lines 221-227:**
```python
gt_pts = load_gt(Path(args.zip), args.seq)
track = load_tracker(...)
H_by_frame, holdout = derive_per_frame_H(gt_pts)
```
All `positions.json` pitch coords and `distances.json` depend on this H.

**Fix:** Same as above — add `--homography` arg; load static H; replace `H_by_frame` dict.

### 3. compute_possession.py — H from GT (DELIVERABLE-CRITICAL)

**Lines 83-85:**
```python
gt_pts = load_gt(Path(args.zip), seq)
H_by_frame, _ = derive_per_frame_H(gt_pts)
```
Used to project player feet to pitch for nearest-player-to-ball proximity.

**Fix:** Same static H pattern.

### 4. team_assign.py — hardcoded SEQS (MAJOR CODE EDIT)

**Line 36:** `SEQS = ["SNGS-116", ..., "SNGS-120"]` — hardcoded, no CLI override.

**Downstream at line 498:** `frames_dirs = {seq: data_root / seq / "img1" for seq in SEQS}` — builds frame paths per SoccerNet seq.

**Fix:** Change `SEQS` to be driven by a `--seqs` CLI arg. Single-job usage: `--seqs <jobid>`. The torso clustering and team assignment logic itself is purely appearance-based and has no GT dependency in its core (parts A/B/C).

**Also:** `render_team_heatmaps()` calls `derive_per_frame_H()` — wrap in try/except or skip when no zip.

### 5. analyze_ball.py — seqinfo.ini for n_frames

**Lines 332-334:**
```python
cp.read(Path(args.source) / seq / "seqinfo.ini")
n_frames = int(cp["Sequence"]["seqLength"])
```
**Fix:** Either (a) generate `seqinfo.ini` during the decode stage (trivial — just write `seqLength=<frame_count>`), or (b) add `--n-frames` CLI arg as fallback when seqinfo.ini is absent. Option (a) is simpler.

### 6. build_det_cache.py — seqinfo.ini required

Reads `seqinfo.ini` for frame count and image dir. **Fix:** Generate `seqinfo.ini` in the decode stage (same as above).

### 7. team_assign.py validation — GSR zip (SKIPPABLE)

Lines 514, 508-510: calls `validate()` and `render_team_heatmaps()` using the GSR zip. These only produce `validation.json` and heatmap renders.  
**Fix:** Mock the zip path or catch exceptions; the core `track_teams.json` output is unaffected.

### 8. detect_events.py — action label from zip (SKIPPABLE)

`load_action_label()` is wrapped in try/except (lines 89-101) and returns `{action_class: None, approx_frame: None}` on failure. Pass `--zip ""` — no code change needed.

### 9. follow_cam.py — GT ball for metrics (SKIPPABLE)

`load_ball_gt()` call wrapped in try/except (lines 456-460). Pass `--gt-zip ""`. No change needed.

---

## Hard blockers vs skippable-validation

### Hard blockers (pipeline breaks without fix)

| Script | Blocker | Impact |
|--------|---------|--------|
| `analyze_ball.py` | GT H for pitch projection | `pitch_x_m/y_m` in trajectory.json = all None; detect_events + coach analytics lose all pitch-space metrics |
| `analyze_pitch.py` | GT H for pitch projection | `positions.json` = empty; coach PDF has no heatmaps, distances, formation |
| `compute_possession.py` | GT H for player pitch coords | `possession.json` fails; coach PDF loses possession stats |
| `team_assign.py` | Hardcoded SEQS list | Script crashes on unknown seq name; `track_teams.json` not produced; all team-dependent analytics fail |
| `analyze_ball.py` | `seqinfo.ini` needed for n_frames | Script crashes if ini absent |
| `build_det_cache.py` | `seqinfo.ini` + `img1/` folder | Script cannot run without frame folder |

### Skippable / validation-only couplings

| Script | Coupling | What breaks if skipped |
|--------|----------|------------------------|
| `team_assign.py` | `validate()` + `render_team_heatmaps()` with GT zip | Only `validation.json` accuracy metrics + heatmap renders; `track_teams.json` unaffected |
| `detect_events.py` | `load_action_label()` | Plausibility printout + `label.action_class` in events.json; event detection unaffected |
| `follow_cam.py` | `load_ball_gt()` | `gt_ball_in_crop` metric in metrics.json; crop paths unaffected |
| `analyze_pitch.py` | GT-distance comparison | `smoothed_vs_gt_pct` in validation.json; analytics unaffected |
| `coach_deliverable.py` | `validation.json` gt fields | PDF footnotes "checked vs GT +X%" become None; PDF still renders |

---

## Decode stage needs

### Frame folder layout required

All downstream scripts (team_assign, analyze_ball, analyze_pitch, follow_cam, coach_deliverable, clip_highlights, build_det_cache, track_botsort_from_cache) expect:

```
<root>/<seq>/img1/<frame:06d>.jpg
```

- `<root>` = the `--source` / `--data-root` / `--frames` argument
- `<seq>` = the sequence name (job ID for the backend)
- `img1/` = literal subdirectory name (hardcoded in build_det_cache `parse_seqinfo` fallback)
- `<frame:06d>.jpg` = 6-digit zero-padded 1-indexed frame number, e.g. `000001.jpg`, `000002.jpg`

**Evidence:** `f"{f:06d}.jpg"` pattern used in team_assign line 95, analyze_ball line 275, follow_cam line 309, clip_highlights line 68, track_botsort_from_cache line 48, coach_deliverable line 500.

### seqinfo.ini required for

`build_det_cache.py` (`parse_seqinfo`) and `analyze_ball.py` (n_frames). Minimal required content:

```ini
[Sequence]
name=<jobid>
seqLength=<total_frame_count>
frameRate=25
imDir=img1
imExt=.jpg
imWidth=1920
imHeight=1080
```

### ffmpeg decode command

```bash
ffmpeg -i input.mp4 -q:v 2 -start_number 1 frames/<jobid>/img1/%06d.jpg
```

Frame count for seqinfo.ini can be obtained via:
```bash
ffprobe -v quiet -select_streams v:0 -count_packets -show_entries stream=nb_read_packets -of csv=p=0 input.mp4
```

### Homography from 4 calibration points

The backend receives 4 pixel points + their known pitch metre coordinates (FIFA centre-origin: pitch spans ±52.5m x, ±34.0m y). Use:

```python
import cv2, numpy as np
src = np.array(pixel_points, dtype=np.float32)   # shape (4,2), pixel coords
dst = np.array(pitch_points, dtype=np.float32)   # shape (4,2), metres
H_ci, _ = cv2.findHomography(src, dst)           # H_court_from_img
H_ic, _ = cv2.findHomography(dst, src)           # H_img_from_court
```

Write `homography.json` with the same schema as `mark_court.py` output. Downstream scripts need `H_ci` (pixel → metres) for `cv2.perspectiveTransform()`.

The scripts call: `cv2.perspectiveTransform(np.array([[[px, py]]], dtype=np.float32), H)` where H = `H_court_from_img` (pixel to metres).
