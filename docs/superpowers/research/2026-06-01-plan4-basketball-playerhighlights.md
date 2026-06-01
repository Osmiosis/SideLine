# Basketball Player Highlights — Backend Chain Map
*Researched 2026-06-01 from actual scripts; no guessing.*

---

## Per-script reference

### 1. `detect_involvement_bb.py`

**Purpose:** Per-player involvement detection (Part A). Emits involvement ranges per track id.

**CLI args + defaults:**
```
positional:  seq          (optional; default = all 5 SEQS_DEFAULT)
--mode       radius|nearest|gap   default="gap"
--compare    flag; runs all 3 modes, prints table, no canonical write
--tracker-dir  default="outputs/track_results/bb_ftdet_botsort_gmc"
--ball-dir     default="outputs/ball_track_bb"
--team-file    default="outputs/team_assign_bb/track_teams_bb.json"
--out          default="outputs/involvement_bb"
```

**Hardcoded coupling:**
```python
SEQS_DEFAULT = ["v_00HRwkvvjtQ_c001", "v_00HRwkvvjtQ_c003", "v_00HRwkvvjtQ_c005",
                "v_00HRwkvvjtQ_c007", "v_00HRwkvvjtQ_c008"]
```
All path args are CLI-overridable. No GT dependency. No frames needed (frame-free).

**Inputs read:**
- `{tracker_dir}/{seq}.txt` — player MOT tracks (top-left xywh format)
- `{ball_dir}/{seq}/trajectory.json` — ball pixel trajectory + status field
- `{team_file}` — `track_teams_bb.json`, shape `{seq: {tid: {role: "TeamA"|"TeamB"|...}}}`

**Hard deps:** all three above must exist. No optional/skippable deps.

**Outputs written:**
- `{out}/{seq}/involvement.json` — `{"stats": {...}, "tracks": [{track_id, role, moments: [{start, end, start_sec, end_sec, dur_frames, strength, ...}]}]}`
- `{out}/{seq}/distribution.png`
- `{out}/summary.json`
- `{out}/_compare.json` (only with `--compare`)

**Basketball-specific tunables (hardcoded constants — re-tune at DPS mount):**
```python
PLAYER_HEIGHT_M = 1.9
ON_BALL_RADIUS_M = 1.8    # tighter than football's 2.5
GAP_FACTOR = 1.6          # gap mode: 2nd-nearest must be >=1.6x nearest's distance
MERGE_GAP_FRAMES = 12
MIN_RANGE_FRAMES = 5
MIN_TRACK_FRAMES = 25
OUTFIELD_ROLES = {"TeamA", "TeamB"}
```

**Model files needed:** none (pure geometry).

---

### 2. `clip_player_highlights_bb.py`

**Purpose:** Cut per-involvement-range clips from C-feed frames (Part B). Emits taggable clips + manifest.

**CLI args + defaults:**
```
positional:  seq          (optional; default = all 5 SEQS_DEFAULT)
--involvement-dir  default="outputs/involvement_bb"
--follow-dir       default="outputs/follow_cam_bb"
--source           default="datasets/sportsmot_basketball"   ← SportsMOT coupling
--out              default="outputs/player_highlights_bb"
--clip-w           type=int, default=None (native C crop width = 640)
--clip-h           type=int, default=None (native C crop height = 360)
--no-clips         flag; manifest only, no mp4 rendering
```

**Hardcoded coupling:**
```python
SEQS_DEFAULT = [...]  # same 5 seqs
```
`--source` points to `datasets/sportsmot_basketball` — must be overridden for a job dir.

**Inputs read:**
- `{involvement_dir}/{seq}/involvement.json` — Part A output
- `{follow_dir}/{seq}/follow_cam.json` — C-feed crop centres; if absent, seq is **skipped entirely**
- `{source}/{seq}/img1/*.jpg` — source frames; if absent, manifest is written but clips are not rendered

**Hard dep:** `follow_cam.json` must exist (C-feed requirement — only c001 and c007 have it in SportsMOT).
Skippable: frames absence only skips render, manifest still written.

**Outputs written:**
- `{out}/{seq}/clips/t{tid:03d}_m{idx:02d}_{start_sec:.0f}s.mp4` — per-clip video (gitignored)
- `{out}/{seq}/clips_manifest.json` — JSON with `clips` array

**clip_id format:** filename stem of the mp4, e.g. `t007_m02_14s.mp4`. This is also the key in `clip_tags.json`.

**Per-clip manifest record (the taggable unit):**
```json
{
  "seq": "v_00HRwkvvjtQ_c001",
  "track_id": 7,
  "role": "TeamA",
  "moment_idx": 2,
  "start_frame": 301,
  "end_frame": 420,
  "involve_start_sec": 14.0,
  "involve_end_sec": 17.2,
  "strength": 0.84,
  "mean_closeness": 0.71,
  "dur_frames": 38,
  "clip": "outputs/player_highlights_bb/v_00HRwkvvjtQ_c001/clips/t007_m02_14s.mp4",
  "rendered": true,
  "kind": "involvement"
}
```

**PAD constants (hardcoded):**
```python
PAD_PRE = 50   # -2.0 s lead-in
PAD_POST = 25  # +1.0 s follow-through
```

**Model files needed:** none. Imports `follow_cam._crop` (geometry only).

---

### 3. `tag_clips_bb.py`

**Purpose:** Interactive Tkinter GUI for human operator to tag each clip with a player name (Part C). Produces `clip_tags.json` consumed by assemble step.

**CLI args + defaults:**
```
positional:  seq          (required)
--roster     default=None  (text file, one name per line; optional)
--clips-dir  default="outputs/player_highlights_bb"
--source     default="datasets/sportsmot_basketball"
--follow-dir default="outputs/follow_cam_bb"
```

**Inputs read:**
- `{clips_dir}/{seq}/clips_manifest.json` — both involvement and presence clips
- `{source}/{seq}/img1/{frame}.jpg` — key-frame preview
- `{follow_dir}/{seq}/follow_cam.json` — C crop for preview thumbnail
- `{clips_dir}/{seq}/clip_tags.json` — existing tags (for resume)

**Output written:**
- `{clips_dir}/{seq}/clip_tags.json`

**tags.json shape:**
```json
{
  "t007_m02_14s.mp4": "Alice",
  "t007_m00_03s.mp4": "Alice",
  "p012_presence.mp4": "Bob",
  "t003_m01_08s.mp4": "__skip__",
  "__track_last__7": "Alice"
}
```
Keys are mp4 **basenames** (not full paths). `__track_last__<tid>` keys are internal state (skipped by assemble via `k.startswith("__")` filter). `__skip__` value excludes a clip from reels.

**The tagger is interactive (Tkinter GUI).** The backend cannot run it headlessly. The backend must either:
1. Serve the clips via API, accept tag submissions from the operator web UI, then write `clip_tags.json` in the same shape; or
2. Provide a minimal JSON-write endpoint that produces the same file structure.

No code change needed in downstream scripts — `assemble_player_reels_bb.py` reads `clip_tags.json` directly by path.

**Model files needed:** none.

---

### 4. `assemble_player_reels_bb.py`

**Purpose:** Presence fallback + per-player reel assembly + inclusivity verification (Parts C+D).

**CLI args + defaults:**
```
positional:  seq          (optional; default = all 5 SEQS_DEFAULT)
--involvement-dir  default="outputs/involvement_bb"
--clips-dir        default="outputs/player_highlights_bb"
--tracker-dir      default="outputs/track_results/bb_ftdet_botsort_gmc"
--team-file        default="outputs/team_assign_bb/track_teams_bb.json"
--follow-dir       default="outputs/follow_cam_bb"
--source           default="datasets/sportsmot_basketball"   ← SportsMOT coupling
--out              default="outputs/deliverables/player_highlights_basketball"
--no-render        flag; report only (no presence clips or reels rendered)
```

**How it reads tags:**
```python
tags_path = Path(args.clips_dir, seq, "clip_tags.json")
tags = json.loads(tags_path.read_text()) if tags_path.exists() else {}
tags = {k: v for k, v in tags.items() if not k.startswith("__")}
```
Then:
```python
name = tags.get(Path(rec["clip"]).name)   # lookup by mp4 basename
```
If `clip_tags.json` absent → all clips grouped by `track_{tid:03d}` (draft mode, no names).
If name == `"__skip__"` → clip excluded from reel.
If name is None → falls through to `track_{tid:03d}` grouping.

**Inputs read:**
- `{involvement_dir}/{seq}/involvement.json` — Part A
- `{clips_dir}/{seq}/clips_manifest.json` — Part B manifest (involvement clips)
- `{tracker_dir}/{seq}.txt` — MOT tracks (for presence stretch computation)
- `{team_file}` — roles
- `{follow_dir}/{seq}/follow_cam.json` — C crop centres for presence clip + reel render
- `{source}/{seq}/img1/*.jpg` — frames for rendering

**Outputs written:**
- `{clips_dir}/{seq}/clips/p{tid:03d}_presence.mp4` — presence clips (gitignored)
- `{clips_dir}/{seq}/clips_manifest.json` — updated (involvement + presence entries combined)
- `{clips_dir}/{seq}/inclusivity_report.json`
- `{clips_dir}/{seq}/reels/{name}.mp4` — per-player reels (one per tagged name)
- `{out}/inclusivity.md`, `{out}/inclusivity_summary.json`, `{out}/sample_reel.mp4`
- `{out}/distribution_{seq[-4:]}.png`

**Model files needed:** none. Imports `follow_cam._crop`, `detect_involvement_bb` constants.

---

### 5. `follow_cam_basketball.py`

**Purpose:** Generates `follow_cam.json` (A/B/C crop-centre paths). Run ONCE during foundation; not re-run per job unless C-feed is missing.

**Relevant to backend:** only as a prerequisite. The backend needs `outputs/follow_cam_bb/<seq>/follow_cam.json` to exist before the highlights chain runs.

**CLI args (summary):**
```
positional:  seq          (optional; default = c001, c007)
--ball-dir   default="outputs/ball_track_bb"
--track-dir  default="outputs/track_results/bb_ftdet_botsort_gmc"
--source     default="datasets/sportsmot_basketball"
--out        default="outputs/follow_cam_bb"
--no-render  flag (skip mp4, metrics+json only)
```

**Output that matters downstream:** `{out}/{seq}/follow_cam.json` with shape:
```json
{
  "seq": "...", "frame_w": 1280, "frame_h": 720,
  "crop_w": 640, "crop_h": 360, "fps": 25,
  "variants": {
    "A": [{"frame": 1, "cx": 612.3, "cy": 360.1}, ...],
    "B": [...],
    "C": [{"frame": 1, "cx": 640.0, "cy": 360.0}, ...]
  },
  "a_feed_source": [{"frame": 1, "src": "ball", "holder_id": -1}, ...]
}
```

---

## Chain: player_highlights (two-part, with tagging pause)

Ordered backend commands targeting a job dir (`JOB`). All path overrides shown.

### Prerequisites (foundation — already run by backend)
```
# produces:
#   {JOB}/tracks/players/{seq}.txt             (MOT player tracks)
#   {JOB}/ball_track/{seq}/trajectory.json
#   {JOB}/team_assign/track_teams_emb.json     (roles per track)
#   {JOB}/frames/{seq}/img1/%06d.jpg + seqinfo.ini
#   {JOB}/homography.json
#
# ALSO NEEDED before highlights (not in stated foundation):
#   {JOB}/follow_cam/{seq}/follow_cam.json     (C-feed crop centres)
#
# If not present, run:
python scripts/follow_cam_basketball.py {seq} \
  --ball-dir {JOB}/ball_track \
  --track-dir {JOB}/tracks/players \
  --source {JOB}/frames \
  --out {JOB}/follow_cam \
  --no-render
```

### PART 1 — Emit taggable clips

**Step 1: Detect involvement**
```
python scripts/detect_involvement_bb.py {seq} \
  --mode gap \
  --tracker-dir {JOB}/tracks/players \
  --ball-dir    {JOB}/ball_track \
  --team-file   {JOB}/team_assign/track_teams_emb.json \
  --out         {JOB}/involvement
```
Emits: `{JOB}/involvement/{seq}/involvement.json`

**Step 2: Cut involvement clips**
```
python scripts/clip_player_highlights_bb.py {seq} \
  --involvement-dir {JOB}/involvement \
  --follow-dir      {JOB}/follow_cam \
  --source          {JOB}/frames \
  --out             {JOB}/player_highlights
```
Emits: `{JOB}/player_highlights/{seq}/clips/t{tid:03d}_m{idx:02d}_{sec:.0f}s.mp4`
       `{JOB}/player_highlights/{seq}/clips_manifest.json`

**Step 3: Generate presence clips (no-involvement players)**

Run `assemble_player_reels_bb.py` with `--no-render` first to get the presence manifest entries,
OR run it fully — presence clips render here. The backend may run the full assemble in two phases
(render presence now, assemble reels after tagging), but the script is designed as one pass.
For the tagging pause architecture, run assemble once with presence rendered, reels deferred:
```
python scripts/assemble_player_reels_bb.py {seq} \
  --involvement-dir {JOB}/involvement \
  --clips-dir       {JOB}/player_highlights \
  --tracker-dir     {JOB}/tracks/players \
  --team-file       {JOB}/team_assign/track_teams_emb.json \
  --follow-dir      {JOB}/follow_cam \
  --source          {JOB}/frames \
  --out             {JOB}/deliverables/player_highlights
```
*Note: presence clips are rendered unconditionally when C-feed + frames are present. Reels are also assembled here. If tags don't exist yet, reels are named `track_NNN` (draft). The backend can run this script TWICE: once before tagging (draft reels), once after tagging (named reels).*

---

### *** PAUSE — HUMAN TAGGING ***

The operator tags clips via `GET /tagging-clips` (see below).
Backend writes tags to: `{JOB}/player_highlights/{seq}/clip_tags.json`
Shape: `{"t007_m02_14s.mp4": "PlayerName", "p012_presence.mp4": "PlayerName", ...}`

---

### PART 2 — Assemble named per-player reels

**Step 4: Re-run assemble with tags in place**
```
python scripts/assemble_player_reels_bb.py {seq} \
  --involvement-dir {JOB}/involvement \
  --clips-dir       {JOB}/player_highlights \
  --tracker-dir     {JOB}/tracks/players \
  --team-file       {JOB}/team_assign/track_teams_emb.json \
  --follow-dir      {JOB}/follow_cam \
  --source          {JOB}/frames \
  --out             {JOB}/deliverables/player_highlights
```
Emits: `{JOB}/player_highlights/{seq}/reels/{PlayerName}.mp4` per tagged player
       `{JOB}/player_highlights/{seq}/inclusivity_report.json`
       `{JOB}/deliverables/player_highlights/sample_reel.mp4`

---

## What the operator tags (clip_id + tags.json shape)

**One tag per clip.** Each clip = one continuously-visible track fragment = unambiguously one person even in identical-kit teams.

**clip_id:** the mp4 **basename**, e.g. `t007_m02_14s.mp4` or `p012_presence.mp4`.

**tags.json shape** written to `{JOB}/player_highlights/{seq}/clip_tags.json`:
```json
{
  "t007_m02_14s.mp4": "Alice",
  "t007_m00_03s.mp4": "Alice",
  "p012_presence.mp4": "Bob",
  "t003_m01_08s.mp4": "__skip__"
}
```
- Key: mp4 basename only (not full path).
- Value: player name string, or `"__skip__"` to exclude from all reels.
- The `__track_last__<tid>` internal-state keys from `tag_clips_bb.py` are filtered out by assemble (`k.startswith("__")` check) — do NOT write them from the backend API.
- If a clip has no tag entry → grouped under `track_{tid:03d}` draft name.

**Backend implementation:** write the JSON file directly (no code change needed in assemble). The backend's `POST /tagging-clips/{seq}` endpoint accumulates operator submissions and writes this file.

---

## /tagging-clips: what to expose

For `GET /tagging-clips?job_id=X&seq=Y`:

Read `{JOB}/player_highlights/{seq}/clips_manifest.json`, return per-clip entries with:

| Field | Source in manifest | Notes |
|---|---|---|
| `clip_id` | `Path(rec["clip"]).name` — mp4 basename | key for tags.json |
| `playable_url` | served path to `rec["clip"]` | the rendered mp4 |
| `track_id` | `rec["track_id"]` | for bulk-by-track UX |
| `kind` | `rec["kind"]` — `"involvement"` or `"presence"` | |
| `start_sec` | `rec["involve_start_sec"]` | clip content start |
| `end_sec` | `rec["involve_end_sec"]` | clip content end |
| `strength` | `rec["strength"]` | 0.0 for presence clips |
| `seq` | `rec["seq"]` | |
| `rendered` | `rec["rendered"]` | false = mp4 absent, show placeholder |
| `existing_tag` | from `clip_tags.json` if present | for resume UX |

**Served file:** `rec["clip"]` field in manifest is a relative path like `outputs/player_highlights_bb/{seq}/clips/t007_m02_14s.mp4`. With job-dir override it becomes `{JOB}/player_highlights/{seq}/clips/t007_m02_14s.mp4`. Serve this mp4 directly.

---

## Couplings to break

| Coupling | Location | Fix |
|---|---|---|
| `SEQS_DEFAULT` hardcoded in all 3 `_bb` scripts | lines 49-50, 36-37, 48 (imports from detect_involvement_bb) | Pass positional `seq` arg — already supported. Backend always passes a single seq. |
| `--source` points to `datasets/sportsmot_basketball` | clip_player_highlights_bb, assemble_player_reels_bb, follow_cam_basketball | Override with `--source {JOB}/frames`. |
| `--tracker-dir` points to `outputs/track_results/bb_ftdet_botsort_gmc` | all 3 scripts | Override with `--tracker-dir {JOB}/tracks/players`. |
| `--ball-dir` points to `outputs/ball_track_bb` | detect_involvement_bb, follow_cam_basketball | Override with `--ball-dir {JOB}/ball_track`. |
| `--team-file` points to `outputs/team_assign_bb/track_teams_bb.json` | detect_involvement_bb, assemble_player_reels_bb | Override with `--team-file {JOB}/team_assign/track_teams_emb.json`. Note filename differs: foundation emits `track_teams_emb.json`, scripts default to `track_teams_bb.json` — must pass explicitly. |
| `--follow-dir` points to `outputs/follow_cam_bb` | clip_player_highlights_bb, assemble_player_reels_bb, tag_clips_bb | Override with `--follow-dir {JOB}/follow_cam`. |
| `--involvement-dir` points to `outputs/involvement_bb` | clip_player_highlights_bb, assemble_player_reels_bb | Override with `--involvement-dir {JOB}/involvement`. |
| `--clips-dir` points to `outputs/player_highlights_bb` | assemble_player_reels_bb | Override with `--clips-dir {JOB}/player_highlights`. |
| `--out` in assemble points to `outputs/deliverables/player_highlights_basketball` | assemble_player_reels_bb | Override with `--out {JOB}/deliverables/player_highlights`. |
| `tag_clips_bb.py` is interactive Tkinter GUI | entire script | Do NOT run from backend. Backend writes `clip_tags.json` directly. |

---

## Hard blockers vs skippable

### Hard blockers (chain cannot proceed without these)

1. **`follow_cam.json` must exist** per seq before `clip_player_highlights_bb.py` runs. In SportsMOT only c001 and c007 have it — the backend must run `follow_cam_basketball.py` during foundation if not already present.

2. **`team_assign/track_teams_emb.json`** must exist and contain the target seq as a key. Foundation produces this. Filename mismatch with script default (`track_teams_bb.json`) — always pass `--team-file` explicitly.

3. **`involvement.json`** must exist before clip_player_highlights_bb or assemble runs. Sequencing constraint.

4. **`clips_manifest.json`** must exist before assemble runs (assemble reads it for involvement clips before appending presence).

5. **Frames must be present** for any rendering. If absent, manifests are written but no mp4s are rendered — tagging UI has no playable clips.

6. **`clip_tags.json`** must be written by backend before the assemble-for-named-reels step. If absent, reels are rendered with draft `track_NNN` names (not a crash, but not the desired output).

### Skippable / degraded-mode

- Frames absent → manifest-only mode (clip rendered=false). Tagging can still proceed on key-frame thumbnails if backend extracts them separately.
- `--no-clips` flag → manifest only, no mp4s cut.
- `--no-render` flag on assemble → inclusivity report only, no presence clips or reels.
- `--compare` flag on detect_involvement_bb → diagnostic only, no canonical involvement.json written.

---

## Basketball-specific differences from football

| Aspect | Football | Basketball |
|---|---|---|
| Involvement definition | `nearest` (Day-27) — single closest within ~2.5 m radius | `gap` mode — nearest AND 2nd-nearest ≥1.6× farther; pure nearest smears across all 10 players in half-court crowd |
| ON_BALL_RADIUS_M | 2.5 | 1.8 (tighter; half-court congested) |
| Presence clip rendering | Presence stretches DEFINED only, not rendered | Presence clips RENDERED (majority of coverage is presence, not involvement) |
| Involve/presence split | ~29% involve / 71% presence | ~36% involve / 64% presence (Day-28 measured) |
| C-feed seqs available | football seqs (football follow_cam) | Only c001 + c007 (head-FP cleaning done Day-15/16); c003/c005/c008 skipped |
| Track directory | `outputs/track_results/<football_seq>.txt` | `outputs/track_results/bb_ftdet_botsort_gmc/<seq>.txt` — different subdir |
| Team file | `outputs/team_assign/track_teams.json` | `outputs/team_assign_bb/track_teams_bb.json` (default) or `track_teams_emb.json` (foundation output) |
| Ball trajectory source | `outputs/ball_track/<seq>/trajectory.json` | `outputs/ball_track_bb/<seq>/trajectory.json` |
| Follow-cam output | `outputs/follow_cam_bb/<seq>/` | same — shared |
| Frame resolution | 1920×1080 | 1280×720 |
| C-feed crop size | larger | 640×360 (zoom=2.0 from 1280×720) |
| Identity fragmentation | severe at full match (5106 IDs, Day-29/31) | not tested at full match; tag-per-clip is the identity solution regardless |
| PLAYER_HEIGHT_M | 1.75 (estimated) | 1.9 |

### Identity fragmentation + presence-fallback / inclusivity (Day-28)

The `gap` involvement definition concentrates ball-handling on a few tracks. Most on-court players get zero involvement clips. `assemble_player_reels_bb.py` implements the **presence fallback**:

- For every "substantial" track (≥25 frames = ~1s on court) with zero involvement clips, find the longest contiguous visible stretch in the MOT tracks.
- Cap to ~5s (125 frames), render one `p{tid:03d}_presence.mp4` from the C-feed.
- This guarantees every on-court player gets at least one clip → 100% inclusivity by construction.

The operator tags **both** involvement clips and presence clips the same way (same `clip_tags.json`). A player who only has a presence clip still lands in a named reel after tagging.

**Tag volume (Day-31 full-match finding):** at full-match scale, tagging is prohibitive (2,224 clips/half = 3–12h operator time). The backend should note this to operators and consider bulk-by-track shortcutting (`b` key in the original GUI, or a "name all clips for track X" API call).

---

## Minimal backend command set (job-dir targeted, all couplings broken)

```bash
SEQ="<seq>"
JOB="<job_dir>"

# 0. Prerequisite: follow_cam (if not already run in foundation)
python scripts/follow_cam_basketball.py $SEQ \
  --ball-dir   $JOB/ball_track \
  --track-dir  $JOB/tracks/players \
  --source     $JOB/frames \
  --out        $JOB/follow_cam \
  --no-render

# 1. Involvement
python scripts/detect_involvement_bb.py $SEQ \
  --mode gap \
  --tracker-dir $JOB/tracks/players \
  --ball-dir    $JOB/ball_track \
  --team-file   $JOB/team_assign/track_teams_emb.json \
  --out         $JOB/involvement

# 2. Cut involvement clips
python scripts/clip_player_highlights_bb.py $SEQ \
  --involvement-dir $JOB/involvement \
  --follow-dir      $JOB/follow_cam \
  --source          $JOB/frames \
  --out             $JOB/player_highlights

# 3. Render presence clips + draft reels (pre-tagging)
python scripts/assemble_player_reels_bb.py $SEQ \
  --involvement-dir $JOB/involvement \
  --clips-dir       $JOB/player_highlights \
  --tracker-dir     $JOB/tracks/players \
  --team-file       $JOB/team_assign/track_teams_emb.json \
  --follow-dir      $JOB/follow_cam \
  --source          $JOB/frames \
  --out             $JOB/deliverables/player_highlights

# *** PAUSE: operator tags via API → backend writes:
# {JOB}/player_highlights/{seq}/clip_tags.json
# shape: {"t007_m02_14s.mp4": "Alice", "p012_presence.mp4": "Bob", ...}

# 4. Re-assemble named per-player reels (post-tagging)
python scripts/assemble_player_reels_bb.py $SEQ \
  --involvement-dir $JOB/involvement \
  --clips-dir       $JOB/player_highlights \
  --tracker-dir     $JOB/tracks/players \
  --team-file       $JOB/team_assign/track_teams_emb.json \
  --follow-dir      $JOB/follow_cam \
  --source          $JOB/frames \
  --out             $JOB/deliverables/player_highlights
```

**Deliverable reels:** `{JOB}/player_highlights/{seq}/reels/{PlayerName}.mp4`
