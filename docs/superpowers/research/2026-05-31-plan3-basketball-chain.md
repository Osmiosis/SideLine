# Basketball CV Pipeline Map — Plan 3 Backend Integration
**Date:** 2026-05-31  
**Purpose:** Exact pipeline map for wrapping existing scripts to serve `coach_analytics` and `event_highlights` from a raw mp4 + marked calibration points.

---

## 1. Script Inventory

### `track_basketball.py`
**CLI:** `python scripts/track_basketball.py <input_mp4>`  
Positional `sys.argv[1]` only — no argparse. INPUT defaults to `clips/basketball.mp4`.  
OUTPUT hardcoded to `outputs/annotated_videos/{stem}_tracked.mp4`.

**Inputs:** Raw mp4 directly via `cv2.VideoCapture`. **No frame folder needed. No seqinfo.ini.**  
**Outputs:** Annotated mp4 only. **Does NOT write MOT .txt tracks.** This is a visualiser, not a pipeline tracker.

**Dataset coupling:** None. Takes any mp4.

**Model:** `models/basketball.pt` — exists. Uses `model.track()` with ByteTrack. Writes annotated video, not usable track files.

**Verdict:** This script is a demo/visualiser. The pipeline tracker is `build_det_cache.py` + `track_from_cache.py` (see §5). The backend needs to use those two instead.

---

### `build_det_cache.py`
**CLI:**
```
python scripts/build_det_cache.py \
  --detector models/basketball_player.pt \
  --source <frames_root>         # dir containing seq dirs with seqinfo.ini + img1/
  --out <cache_dir>              # writes <seq>.txt per seq
  --class-name player            # filter class
  --imgsz 1280
  --conf 0.25
  --only <seq_name>              # optional: process one seq only
```
**Inputs:** Frames in `<source>/<seq>/img1/000001.jpg` format + `<source>/<seq>/seqinfo.ini`.  
**Dataset coupling:** Requires numbered JPG frames in `img1/` and a `seqinfo.ini`. **The backend MUST decode the mp4 to frames and write a seqinfo.ini before calling this.**  
**Outputs:** `<out>/<seq>.txt` — cache format `frame,x,y,w,h,conf` (1-indexed frames).  
**Models needed:** `models/basketball_player.pt` — exists.

---

### `track_from_cache.py`
**CLI:**
```
python scripts/track_from_cache.py \
  --cache <cache_dir>     # built by build_det_cache
  --source <frames_root>  # same dir; needs seqinfo.ini for frame dims + fps
  --out <track_out_dir>   # writes <seq>.txt in MOT format: frame,tid,x,y,w,h,...
```
**Inputs:** Detection cache `.txt` + `seqinfo.ini` for dimensions/fps.  
**Dataset coupling:** Needs `seqinfo.ini`. Same decode requirement as build_det_cache.  
**Outputs:** MOT `.txt` tracks: `frame,tid,x,y,w,h,...` per row.  
**Models needed:** None (pure ByteTrack, no GPU).

---

### `basketball_court.py` (library + main)
**CLI (main):**
```
python scripts/basketball_court.py <seq> \
  --frame 540 \
  --frames-root datasets/sportsmot_basketball \
  --track outputs/track_results/bball_ftdet_bytetrack \
  --out outputs/deliverables \
  --model ncaa|fiba \
  --mark | --points pts.json | --register
```
**Inputs:** A single frame from `<frames-root>/<seq>/img1/<frame:06d>.jpg` + optional track `.txt` for player feet overlay. Interactive marking requires a display.  
**Dataset coupling:** `--frames-root` defaults to SportsMOT but is a pure CLI arg — override to job dir.  
**Outputs:** `<out>/<seq>/court/homography.json` — shape:
```json
{
  "seq": "...", "frame": 540, "model": "ncaa",
  "H_img_from_court": [[...3x3...]],
  "H_court_from_img": [[...3x3...]],
  "points": [{"name": "r_baseline_far", "img": [x,y], "court": [cx,cy]}, ...],
  "holdout_mean_err_m": 0.21,
  "landmark_recon_mean_m": 0.18
}
```
Also writes `overlay.png`, `court_diagram.png`, `validation.json`.  
**Models needed:** None.

**Deployment note:** Auto-detect/register are documented as unreliable. `--mark` requires a display (GUI). For backend, the operator uses `mark_court.py` interactively ONCE to produce `homography.json`, which is uploaded to the job. OR the backend calls `basketball_court.py --points <pts.json>` if the frontend collected points.

---

### `mark_court.py`
**CLI:**
```
python scripts/mark_court.py <seq> \
  --frame 540 \
  --frames-root datasets/sportsmot_basketball \
  --model ncaa|fiba \
  --out outputs/deliverables
```
**Inputs:** Single frame from `<frames-root>/<seq>/img1/<frame:06d>.jpg`. Requires display (OpenCV GUI).  
**Dataset coupling:** `--frames-root` is a pure arg — override to job frames dir.  
**Outputs:** `<out>/<seq>/court/homography.json` + `points.json` + `overlay.png` + `validation.json`. Same JSON shape as `basketball_court.py` output.  
**Usage in backend:** Operator runs this locally/interactively on a sample frame; resulting `homography.json` is uploaded or copied into `jobs/<id>/outputs/<seq>/court/homography.json`. Not called programmatically by the worker.

---

### `bball_team_assign.py`
**CLI:**
```
python scripts/bball_team_assign.py \
  --track outputs/track_results/bball_ftdet_bytetrack \
  --frames-root datasets/sportsmot_basketball \
  --court outputs/deliverables/v_00HRwkvvjtQ_c007/court/homography.json \
  --out outputs/team_assign_bb \
  --step 2 \
  --off-court-thresh 0.5 \
  --ref-dist-pct 92.0 \
  --validate-only
```
**Inputs:**  
- `<track>/<seq>.txt` — MOT tracks (one per seq in `SEQS` hardcoded list)  
- `<frames-root>/<seq>/img1/<frame:06d>.jpg` — reads actual frame images for torso crops  
- `<court>` — homography.json for court-position filter (only applied to COURT_SEQ)

**Dataset coupling — HARD:** `SEQS` is hardcoded to 5 SportsMOT sequence names at module level (line 43). The court-position filter is also hardcoded to `COURT_SEQ = "v_00HRwkvvjtQ_c007"`. For deployment, the list must be changed to the single job seq name.  
**Required change:** Pass `--only` seq or refactor: add `--seq` arg, or patch `SEQS = [args.seq]` in main. **This is a code edit, not just CLI args.**

**Outputs:** `<out>/track_teams_bb.json` — shape:
```json
{
  "<seq>": {
    "<tid>": {"role": "TeamA|TeamB|Referee|Excluded", "cluster": 0, "n_dets": 45, ...}
  }
}
```
Also `cluster_summary_bb.json`, `sample_torsos.png`, optional `validation_bb.json`.  
**Models needed:** None (KMeans on torso LAB color, pure numpy).  
**GT/validation dependency:** `validation_bb.json` requires `hand_labels.json` + `crops.npz` — these only exist for SportsMOT. Validation is skipped gracefully if absent (prints "SKIPPED"). **Not a blocker.**

---

### `bball_team_embed.py`
**CLI:**
```
python scripts/bball_team_embed.py \
  --track outputs/track_results/bball_ftdet_bytetrack \
  --frames-root datasets/sportsmot_basketball \
  --court outputs/deliverables/v_00HRwkvvjtQ_c007/court/homography.json \
  --out outputs/team_assign_bb \
  --step 2 --pca 50 \
  --region both|torso|full
```
**Inputs:** Same as `bball_team_assign.py` — MOT tracks + frame images + homography.json.  
**Dataset coupling:** Same `SEQS` hardcoded list (line 38) + `COURT_SEQ` hardcoded. Same code edit required.  
**Outputs:** `<out>/track_teams_emb.json` — same shape as `track_teams_bb.json` but from embedding-based clustering. Also `validation_emb.json`.  
**Models needed:** Frozen ImageNet ResNet18 (downloaded by torchvision on first run — no `.pt` file in `models/`).  
**Validation dependency:** Also requires `hand_labels.json` + `crops.npz` — skipped gracefully if absent. **Not a blocker.**

**Which to use:** `bball_team_embed.py` is Day-23 (newer, better accuracy). `coach_deliverable_basketball.py` reads whichever file is specified via `--team-assign` (defaults to `track_teams_emb.json`). Use embed version.

---

### `analyze_ball_basketball.py`
**CLI:**
```
python scripts/analyze_ball_basketball.py [seq] \
  --cache-dir outputs/det_cache/bb_ball \
  --source datasets/sportsmot_basketball \
  --out outputs/ball_track_bb \
  --vel-gate 100.0 --max-gap 8 --init-conf 0.35 \
  --require-player \
  --track-dir outputs/track_results/bb_ftdet_botsort_gmc \
  --reinit-prox 150.0 --ingate-prox 300.0 --reacq-frames 2 \
  --motion-consistency \
  --appearance-filter outputs/ball_head/filter.pt \
  --render-video
```
**Inputs:**  
- Ball detection cache: `<cache-dir>/<seq>.txt` — same `frame,x,y,w,h,conf` format, ball class  
- `<source>/<seq>/seqinfo.ini` — needs frame count + dimensions  
- Player tracks: `<track-dir>/<seq>.txt` (for proximity prior, optional but recommended)  
- `<appearance-filter>` — `outputs/ball_head/filter.pt` (optional ball-vs-head classifier)

**Dataset coupling:** `--source` for seqinfo.ini only; `--cache-dir` and `--track-dir` are fully overridable. `SEQS_DEFAULT` is a module-level list but only used when `seq` positional arg is omitted. Pass `seq` positionally to process one.  
**Outputs:** `<out>/<seq>/trajectory.json` — per-frame `{frame, status, x, y, vx, vy, n_dets, picked_conf, shot_flag}`. Also `validation.json`, `sample_frame.png`.  
**Models needed:** `models/basketball.pt` (ball detection) for the cache build step; `outputs/ball_head/filter.pt` for appearance filter (optional). Ball model = `basketball.pt` or `basketball_ft.pt` — must verify which was used to build `outputs/det_cache/bb_ball`.

**Seqinfo.ini requirement:** Reads `seqinfo.ini` via `seq_info()` for frame count + dimensions. This is a **hard requirement** — the decode stage must write this file.

---

### `follow_cam_basketball.py`
**CLI:**
```
python scripts/follow_cam_basketball.py [seq] \
  --ball-dir outputs/ball_track_bb \
  --track-dir outputs/track_results/bb_ftdet_botsort_gmc \
  --source datasets/sportsmot_basketball \
  --out outputs/follow_cam_bb \
  --fps 25 --zoom 2.0 \
  --no-render
```
**Inputs:**  
- `<ball-dir>/<seq>/trajectory.json` — ball track from analyze_ball_basketball  
- `<track-dir>/<seq>.txt` — MOT player tracks  
- `<source>/<seq>/img1/000001.jpg` — reads first frame for W/H dimensions  
- Frame images for rendering (if `--render`)

**Dataset coupling:** `--source` used only to read frame 000001.jpg for dimensions + render frames. Override to job frames dir.  
**Outputs:** `<out>/<seq>/follow_cam.json` — crop-center paths for variants A/B/C, frame_w, frame_h, crop_w, crop_h, fps. Also `metrics.json`, plots, optional mp4s.  
**Key field used by downstream:** `follow_cam.json` → `frame_w`, `frame_h`, `crop_w`, `crop_h`, and `variants.A` array.  
**Models needed:** None.

---

### `detect_events_basketball.py`
**CLI:**
```
python scripts/detect_events_basketball.py [seq] \
  --ball-dir outputs/ball_track_bb \
  --track-dir outputs/track_results/bball_ftdet_bytetrack \
  --follow-dir outputs/follow_cam_bb \
  --out outputs/events_bb
```
**Inputs:**  
- `<ball-dir>/<seq>/trajectory.json` — ball track  
- `<track-dir>/<seq>.txt` — player MOT tracks  
- `<follow-dir>/<seq>/follow_cam.json` — for frame_w/frame_h dimensions  
- Homography: hardcoded path `outputs/deliverables/{seq}/court/homography.json` — **no CLI arg to override**  
- Team assignment: hardcoded path `outputs/team_assign_bb/track_teams_emb.json` — **no CLI arg to override**

**Dataset coupling — HARD (two hardcoded paths):**  
```python
def load_homography(seq):
    H = json.loads(Path(f"outputs/deliverables/{seq}/court/homography.json").read_text())
```
```python
def load_teams(seq, path="outputs/team_assign_bb/track_teams_emb.json"):
```
These are relative to CWD. The backend must either: (a) symlink/copy files to match these paths, OR (b) patch these defaults by adding `--homography` and `--teams` CLI args. **Recommend adding args — minimal edit.**  
`SEQS_DEFAULT` hardcoded to `["v_00HRwkvvjtQ_c007"]` but overridden by positional arg.  
**Outputs:** `<out>/<seq>/events.json` (ranked_moments, raw_events) + `features.json` + `features_plot.png`.  
**Models needed:** None.

---

### `clip_highlights_basketball.py`
**CLI:**
```
python scripts/clip_highlights_basketball.py [seq] \
  --events-dir outputs/events_bb \
  --follow-dir outputs/follow_cam_bb \
  --source datasets/sportsmot_basketball \
  --out outputs/deliverables/event_highlights_basketball \
  --ball-dir outputs/ball_track_bb \
  --crop ball|follow_A \
  --clip-w 854 --clip-h 480 \
  --reel-top 8 \
  --no-clips
```
**Inputs:**  
- `<events-dir>/<seq>/events.json` — ranked moments  
- `<follow-dir>/<seq>/follow_cam.json` — crop_w/crop_h  
- `<ball-dir>/<seq>/trajectory.json` — for `--crop ball` mode  
- `<source>/<seq>/img1/<frame:06d>.jpg` — source frames for rendering

**Dataset coupling:** `--source` for frame images. Override to job frames dir.  
**Outputs:**  
- `<out>/index.json` + `index.md` — ranked curation list  
- `<out>/contact_<seq>.jpg` — visual contact sheet  
- `<out>/sample_highlight.mp4` — #1 ranked clip  
- `<events-dir>/<seq>/clips/<rank>_<type>.mp4` — individual clips  
- `<out>/auto_draft_reel.mp4` — top-N concat reel  
**Models needed:** None.

---

### `coach_deliverable_basketball.py`
**CLI:**
```
python scripts/coach_deliverable_basketball.py <seq> \
  --win <start> <end> \
  --deliverables outputs/deliverables \
  --track outputs/track_results/bball_ftdet_bytetrack \
  --ball outputs/ball_track_bb \
  --frames-root datasets/sportsmot_basketball \
  --team-assign outputs/team_assign_bb/track_teams_emb.json \
  --no-video
```
**Inputs:**  
- `<deliverables>/<seq>/court/homography.json` — must exist  
- `<track>/<seq>.txt` — MOT player tracks  
- `<ball>/<seq>/trajectory.json` — ball trajectory  
- `<frames-root>/<seq>/img1/<frame:06d>.jpg` — for tactical video rendering  
- `<team-assign>` — `track_teams_emb.json` or `track_teams_bb.json`

**Dataset coupling:** `--frames-root` defaults to SportsMOT but is a pure CLI arg. `--win` defaults to `493 591` (the SportsMOT stable window) — **must override for arbitrary video** (e.g., `--win 1 <total_frames>`). All other defaults are overridable via CLI.  
**Outputs:**  
- `<deliverables>/<seq>/coach/coach_analysis_basketball.pdf` + `_preview.png`  
- `<deliverables>/<seq>/coach/metrics_basketball.json`  
- `<deliverables>/<seq>/coach/tactical_sample_basketball.mp4` (unless `--no-video`)  
- `<deliverables>/<seq>/coach/tactical_contact_sheet.png`  
- `<deliverables>/<seq>/coach/fig_heatmap.png`, `fig_positions.png`, `fig_territory.png`, `fig_intensity.png`, `fig_team_heatmaps.png`
**Models needed:** None.

---

## 2. Two Ordered Chains

### Shared Foundation (common to both deliverables)

```
Stage 0 — DECODE (NEW — not in any existing script)
  Input:  jobs/<id>/upload.mp4
  Output: jobs/<id>/frames/<seq>/img1/000001.jpg ... NNNNNN.jpg
          jobs/<id>/frames/<seq>/seqinfo.ini
  Tool:   ffmpeg -i upload.mp4 -q:v 2 frames/<seq>/img1/%06d.jpg
  seqinfo.ini fields required: name, seqLength, imWidth, imHeight, imDir=img1, imExt=.jpg, frameRate

Stage 1 — DETECT PLAYERS (build_det_cache.py)
  Input:  jobs/<id>/frames/   (frames dir as --source)
  Command:
    python scripts/build_det_cache.py \
      --detector models/basketball_player.pt \
      --source jobs/<id>/frames \
      --out jobs/<id>/det_cache/players \
      --class-name player --imgsz 1280 --conf 0.25 \
      --only <seq>

Stage 2 — TRACK PLAYERS (track_from_cache.py)
  Input:  jobs/<id>/det_cache/players/<seq>.txt + seqinfo.ini
  Command:
    python scripts/track_from_cache.py \
      --cache jobs/<id>/det_cache/players \
      --source jobs/<id>/frames \
      --out jobs/<id>/tracks/players
  Output: jobs/<id>/tracks/players/<seq>.txt  (MOT format)

Stage 3 — DETECT BALL (build_det_cache.py, ball class)
  Input:  jobs/<id>/frames/
  Command:
    python scripts/build_det_cache.py \
      --detector models/basketball_ft.pt \
      --source jobs/<id>/frames \
      --out jobs/<id>/det_cache/ball \
      --class-name ball --imgsz 1280 --conf 0.25 \
      --only <seq>
  Note: confirm which model (basketball.pt vs basketball_ft.pt) was used for the existing
        outputs/det_cache/bb_ball cache; both exist in models/.

Stage 4 — TRACK BALL (analyze_ball_basketball.py)
  Input:  jobs/<id>/det_cache/ball/<seq>.txt + player tracks + seqinfo.ini
  Command:
    python scripts/analyze_ball_basketball.py <seq> \
      --cache-dir jobs/<id>/det_cache/ball \
      --source jobs/<id>/frames \
      --out jobs/<id>/ball_track \
      --track-dir jobs/<id>/tracks/players \
      --require-player --motion-consistency
  Output: jobs/<id>/ball_track/<seq>/trajectory.json

Stage 5 — TEAM ASSIGN (bball_team_embed.py, with SEQS patch)
  Input:  player tracks + frames + homography.json
  Requires code edit: replace hardcoded SEQS list with single-seq from arg
  Command:
    python scripts/bball_team_embed.py \
      --track jobs/<id>/tracks/players \
      --frames-root jobs/<id>/frames \
      --court jobs/<id>/homography.json \
      --out jobs/<id>/team_assign
  Output: jobs/<id>/team_assign/track_teams_emb.json

Stage 6 — FOLLOW CAM (follow_cam_basketball.py)
  Input:  ball_track trajectory.json + player tracks + first frame for W/H
  Command:
    python scripts/follow_cam_basketball.py <seq> \
      --ball-dir jobs/<id>/ball_track \
      --track-dir jobs/<id>/tracks/players \
      --source jobs/<id>/frames \
      --out jobs/<id>/follow_cam \
      --no-render
  Output: jobs/<id>/follow_cam/<seq>/follow_cam.json
```

**Homography prerequisite (parallel/pre-job):**  
Operator runs `mark_court.py` interactively on a sample frame, uploading the resulting `homography.json` as part of job setup. This is NOT a pipeline stage — it is a one-time calibration artifact per camera installation.

---

### Chain A: `coach_analytics`

Stages 0–6 above, then:

```
Stage 7A — COACH DELIVERABLE (coach_deliverable_basketball.py)
  Input:  player tracks + ball trajectory + homography.json + team assign
  Command:
    python scripts/coach_deliverable_basketball.py <seq> \
      --win 1 <total_frames> \
      --deliverables jobs/<id>/outputs/deliverables \
      --track jobs/<id>/tracks/players \
      --ball jobs/<id>/ball_track \
      --frames-root jobs/<id>/frames \
      --team-assign jobs/<id>/team_assign/track_teams_emb.json
  Outputs:
    jobs/<id>/outputs/deliverables/<seq>/coach/coach_analysis_basketball.pdf
    jobs/<id>/outputs/deliverables/<seq>/coach/tactical_sample_basketball.mp4
    jobs/<id>/outputs/deliverables/<seq>/coach/metrics_basketball.json
    jobs/<id>/outputs/deliverables/<seq>/coach/fig_*.png
```

---

### Chain B: `event_highlights`

Stages 0–6 above, then:

```
Stage 7B — DETECT EVENTS (detect_events_basketball.py)
  Requires minor code edit: add --homography and --teams CLI args (currently hardcoded paths)
  Command:
    python scripts/detect_events_basketball.py <seq> \
      --ball-dir jobs/<id>/ball_track \
      --track-dir jobs/<id>/tracks/players \
      --follow-dir jobs/<id>/follow_cam \
      --out jobs/<id>/events \
      --homography jobs/<id>/homography.json \
      --teams jobs/<id>/team_assign/track_teams_emb.json
  Output: jobs/<id>/events/<seq>/events.json (ranked_moments)

Stage 8B — CLIP HIGHLIGHTS (clip_highlights_basketball.py)
  Input:  events.json + follow_cam.json + ball trajectory + source frames
  Command:
    python scripts/clip_highlights_basketball.py <seq> \
      --events-dir jobs/<id>/events \
      --follow-dir jobs/<id>/follow_cam \
      --source jobs/<id>/frames \
      --ball-dir jobs/<id>/ball_track \
      --out jobs/<id>/outputs/event_highlights \
      --crop ball
  Outputs:
    jobs/<id>/outputs/event_highlights/index.json
    jobs/<id>/outputs/event_highlights/sample_highlight.mp4
    jobs/<id>/outputs/event_highlights/auto_draft_reel.mp4
    jobs/<id>/events/<seq>/clips/*.mp4
```

---

## 3. Dataset Couplings to Break

| Script | Coupling | Type | Fix |
|--------|----------|------|-----|
| `build_det_cache.py` | Needs `seqinfo.ini` in frames dir | Hard | Decode stage writes it |
| `track_from_cache.py` | Needs `seqinfo.ini` for frame dims | Hard | Decode stage writes it |
| `analyze_ball_basketball.py` | Needs `seqinfo.ini` via `seq_info()` | Hard | Decode stage writes it |
| `bball_team_assign.py` | `SEQS` list hardcoded (line 43), `COURT_SEQ` hardcoded (line 45) | Hard | Add `--seq` arg + `SEQS = [args.seq]` in main |
| `bball_team_embed.py` | Same `SEQS` + `COURT_SEQ` hardcoded (lines 38, 40) | Hard | Same fix |
| `detect_events_basketball.py` | `load_homography()` uses hardcoded `outputs/deliverables/{seq}/court/homography.json` (line 91); `load_teams()` hardcoded to `outputs/team_assign_bb/track_teams_emb.json` (line 113) | Hard | Add `--homography` + `--teams` CLI args |
| `coach_deliverable_basketball.py` | `--win` defaults to `493 591` (SportsMOT stable window) | Soft | Pass `--win 1 <total_frames>` |
| `follow_cam_basketball.py` | `--source` used for frame dims (reads `000001.jpg`) | Soft | Override `--source` to job frames dir |
| `clip_highlights_basketball.py` | `--source` for frame reads | Soft | Override `--source` to job frames dir |
| `bball_team_assign/embed.py` | Reads frame images from `<frames-root>/<seq>/img1/` | Soft | Override `--frames-root` to job frames dir |

---

## 4. Hard Blockers vs Skippable Validation

### Hard Blockers (block production use)

1. **Decode stage missing.** No existing script decodes mp4 → numbered JPG frames + `seqinfo.ini`. All downstream scripts (build_det_cache, track_from_cache, analyze_ball_basketball) require this. Must add ffmpeg decode step in the backend worker.

2. **`SEQS` hardcoded in bball_team_assign.py and bball_team_embed.py.** Both scripts iterate over a hardcoded list of 5 SportsMOT sequence names and will fail/produce wrong output on a job seq. Requires adding `--seq` arg and patching `SEQS = [args.seq]` in `main()` — ~3 lines each.

3. **Homography paths hardcoded in detect_events_basketball.py.** `load_homography()` and `load_teams()` use CWD-relative hardcoded paths. Must add `--homography` and `--teams` args. ~4 lines each.

4. **Ball detection cache must be built before analyze_ball_basketball.** No single script runs detection + Kalman in one pass (unlike `track_basketball.py`). The worker must call `build_det_cache.py` for ball class separately.

5. **Two separate track dirs used by different scripts.** `follow_cam_basketball.py` and `analyze_ball_basketball.py` default to `bb_ftdet_botsort_gmc`, while `bball_team_embed.py`, `detect_events_basketball.py`, and `coach_deliverable_basketball.py` default to `bball_ftdet_bytetrack`. Backend must either use one consistent dir or pass correct `--track-dir` to each script.

### Skippable Validation (only needed for SportsMOT benchmarking)

- `validation_bb.json` / `validation_emb.json` — require `hand_labels.json` + `crops.npz`. Code skips gracefully with a print message if absent. **Not a blocker.**
- `analyze_ball_basketball.py --gt` — optional ball GT for RMSE. Falls back to plausibility-only. **Not a blocker.**
- `basketball_court.py` holdout reconstruction error — informational only, does not gate the pipeline.

---

## 5. Model Files

| Stage | Model file | Exists? | Notes |
|-------|-----------|---------|-------|
| Player detection | `models/basketball_player.pt` | Yes | Used in build_det_cache for players |
| Ball detection | `models/basketball_ft.pt` | Yes | Fine-tuned ball detector; also `basketball_446.pt`, `basketball_borisgans.pt` |
| Ball appearance filter | `outputs/ball_head/filter.pt` | Unknown — not in models/ | Optional; skip if absent |
| Team assignment | Torchvision ResNet18 (auto-downloaded) | N/A | No local .pt needed |
| Player tracking (ByteTrack) | YAML config only | N/A | No model weights |

All models in `models/`: `basketball.pt`, `basketball_446.pt`, `basketball_borisgans.pt`, `basketball_ft.pt`, `basketball_player.pt`. Confirm which ball model matches the existing `outputs/det_cache/bb_ball` cache by checking build logs.

---

## 6. Basketball-Specific Differences from Football

| Aspect | Basketball | Football | Backend impact |
|--------|-----------|----------|----------------|
| Tracking script | `track_basketball.py` is a demo only; use `build_det_cache + track_from_cache` | Football also uses cache pipeline | Use cache pipeline for both |
| Team assignment | Torso-color KMeans OR frozen ResNet18 embeddings; validated on hand-labels not GT | Football GT-validated | Use `bball_team_embed.py` (Day-23 winner) |
| Court homography | Manual GUI mark once per camera (`mark_court.py`); fixed camera = mark once, holds match | Same manual mark | Operator marks once at DPS install; `homography.json` is an upload artifact |
| Court model | NCAA (default) or FIBA (`--model fiba`); use FIBA for DPS school court | Football pitch standard | Pass `--model fiba` for DPS |
| `--win` arg | `coach_deliverable_basketball.py` requires frame window; default is 4s SportsMOT clip | Football has no window restriction | Pass `--win 1 <total_frames>` |
| Half-court involvement | Basketball has half-court play; `detect_involvement_bb.py` uses fixed-radius marks instead of full-pitch threshold | Full pitch for football | Relevant for player_highlights (output #2), not coach_analytics or event_highlights |
| Ball tracking | Separate ball det cache (ball class); Kalman with player-proximity FP rejection + head-zone rejection | Same architecture | Two separate `build_det_cache` calls (player + ball) |
| `follow_cam_basketball.py` | Two-track systems: `bb_ftdet_botsort_gmc` (ball tracking) vs `bball_ftdet_bytetrack` (team/events) | One track system | Backend must route correct track dir to each script |
| SEQS coupling | Hardcoded in team_assign scripts | Football equivalents use seq arg | Code patch required |
| Event detection | Requires homography (hoop zone) + team assignment (possession); `SEQS_DEFAULT` only c007 | Football event detection is more standalone | Both homography + teams are prerequisites for events |

---

## 7. Minimal Job Dir Layout

```
jobs/<id>/
  upload.mp4                          # uploaded by operator
  homography.json                     # uploaded by operator (from mark_court.py run)
  frames/<seq>/
    seqinfo.ini                       # written by decode stage
    img1/
      000001.jpg ... NNNNNN.jpg       # written by decode stage
  det_cache/
    players/<seq>.txt                 # build_det_cache (player model)
    ball/<seq>.txt                    # build_det_cache (ball model)
  tracks/
    players/<seq>.txt                 # track_from_cache (ByteTrack)
  ball_track/<seq>/
    trajectory.json                   # analyze_ball_basketball
  team_assign/
    track_teams_emb.json              # bball_team_embed
  follow_cam/<seq>/
    follow_cam.json                   # follow_cam_basketball
  events/<seq>/                       # detect_events_basketball
    events.json
    clips/                            # clip_highlights_basketball
  outputs/
    deliverables/<seq>/
      court/
        homography.json               # symlink or copy of uploaded homography
      coach/                          # coach_deliverable_basketball outputs
    event_highlights/                 # clip_highlights_basketball outputs
```

The `<seq>` name can be any string (e.g., `job_<id>`) — scripts use it as a directory key, not for hardcoded lookups, except in the two team_assign scripts which need the SEQS patch.
