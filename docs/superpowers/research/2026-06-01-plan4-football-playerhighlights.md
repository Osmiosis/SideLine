# Football Player-Highlights Chain (output #2) — Backend Integration Map
*Researched 2026-06-01 from actual script source. No guessing.*

---

## Per-script reference

### `detect_involvement.py` — Part A: involvement detection

**CLI args (argparse):**
```
positional: seq          (optional; omit = all 5 SEQS_DEFAULT)
--tracker-dir            default: outputs/track_results/sn_soccana_botsort_gmc
--ball-dir               default: outputs/ball_track
--team-file              default: outputs/team_assign/track_teams.json
--out                    default: outputs/involvement
```

**Inputs read:**
| Path | Format | Notes |
|------|--------|-------|
| `{tracker_dir}/{seq}.txt` | MOT (CSV, top-left xywh) | player tracks |
| `{ball_dir}/{seq}/trajectory.json` | JSON list of `{frame, x, y, status, ...}` | ball trajectory |
| `{team_file}` | JSON `{seq: {track_id: {role: "TeamA"|"TeamB"|...}}}` | team assignment |

**SoccerNet/GT coupling:** NONE for inputs. The `SEQS_DEFAULT = ["SNGS-116","SNGS-117","SNGS-118","SNGS-119","SNGS-120"]` list is hardcoded at line 39 — the only SoccerNet remnant. No frames needed. No GT zip.

**Outputs written:**
| Path | Format |
|------|--------|
| `{out}/{seq}/involvement.json` | `{"stats": {...}, "tracks": [{track_id, role, moments:[{start,end,start_sec,end_sec,dur_frames,n_ball_frames,mean_closeness,strength},...]},...]}` |
| `{out}/{seq}/distribution.png` | histogram (matplotlib) |
| `{out}/summary.json` | cross-seq rollup |

**No frames, no GPU — pure JSON math.**

**Upstream deps:** tracker output, ball cache, team_assign output.

---

### `clip_player_highlights.py` — Part B: cut involvement clips

**CLI args (argparse):**
```
positional: seq          (optional)
--involvement-dir        default: outputs/involvement
--follow-dir             default: outputs/follow_cam
--source                 default: datasets/soccernet_tracking
--out                    default: outputs/player_highlights
--clip-w                 default: 854
--clip-h                 default: 480
--no-clips               flag; disables mp4 render (manifest-only mode)
```

**Inputs read:**
| Path | Format | Coupling |
|------|--------|---------|
| `{involvement_dir}/{seq}/involvement.json` | Part A output | clean |
| `{follow_dir}/{seq}/follow_cam.json` | `{variants: {C: [{frame, cx, cy}]}, crop_w, crop_h}` | clean |
| `{source}/{seq}/img1/*.jpg` | wide source frames | **SoccerNet path hardcoded** (line 128: `Path(args.source, seq, "img1")`); uses `test/` prefix was removed per Day-30 correction |

**SoccerNet coupling:** `--source` defaults to `datasets/soccernet_tracking`. For backend, override with `--source <job_dir>/frames`. The frame path is `<source>/<seq>/img1/%06d.jpg` — so job dir must contain `frames/<seq>/img1/` and `--source` should point to `<job_dir>/frames`.

**Frame-gated:** script checks `fd.is_dir() and any(fd.glob("*.jpg"))`. If absent, writes `clips_manifest.json` only (`rendered: false` per clip), skips mp4. **Manifest is always written.**

**Clip ID format:**
```python
clip_name = f"t{tid:03d}_m{idx:02d}_{m['start_sec']:.0f}s.mp4"
# e.g. t007_m00_42s.mp4 , t023_m03_187s.mp4
```
The clip_id used downstream is the **basename** of this filename (e.g. `t007_m00_42s.mp4`).

**Outputs written:**
| Path | Format |
|------|--------|
| `{out}/{seq}/clips/{clip_name}.mp4` | H.264 mp4, 854×480, 25fps, player-stabilized C-feed crop |
| `{out}/{seq}/clips_manifest.json` | `{"seq","n_clips","rendered","clips":[{seq,track_id,role,moment_idx,start_frame,end_frame,involve_start_sec,involve_end_sec,strength,mean_closeness,dur_frames,clip:"outputs/player_highlights/{seq}/clips/{clip_name}",rendered:bool,kind:"involvement"},...]}` |

**Upstream deps:** Part A (involvement.json), follow_cam output (follow_cam.json), source frames.

**Imports:** `follow_cam._crop` — the pixel-crop function. No model inference.

---

### `tag_clips.py` — Part C: human identity tagging (Tkinter GUI — NOT the backend path)

**CLI args (argparse):**
```
positional: seq          (REQUIRED)
--roster                 text file, one player name per line (optional)
--clips-dir              default: outputs/player_highlights
--source                 default: datasets/soccernet_tracking
--follow-dir             default: outputs/follow_cam
```

**What it does:** Tkinter GUI. Shows each clip's key-frame (mid-involvement C-feed crop). Operator types/picks a name; `b` = apply name to whole track (bulk); `s` = skip (`__skip__`). Saves after each action.

**Tags file written:**
```
{clips_dir}/{seq}/clip_tags.json
```
Shape:
```json
{
  "t007_m00_42s.mp4": "Alice",
  "t007_m01_98s.mp4": "Alice",
  "t023_m03_187s.mp4": "__skip__",
  "__track_last__7": "Alice"
}
```
Keys prefixed `__` are internal state (last-used name per track). Real tags: `{clip_basename: player_name_or___skip__}`.

**This script is the LOCAL operator tool — the backend replaces it with a REST API tagging step.** The `assemble_player_reels.py` reads from `clip_tags.json` at the same path — the backend only needs to write a conforming `clip_tags.json`.

**Upstream deps:** clips_manifest.json, source frames (optional for preview).

---

### `assemble_player_reels.py` — Part D: per-player reels + inclusivity

**CLI args (argparse):**
```
positional: seq          (optional)
--involvement-dir        default: outputs/involvement
--clips-dir              default: outputs/player_highlights
--tracker-dir            default: outputs/track_results/sn_soccana_botsort_gmc
--team-file              default: outputs/team_assign/track_teams.json
--follow-dir             default: outputs/follow_cam
--source                 default: datasets/soccernet_tracking
--out                    default: outputs/deliverables/player_highlights_football
--no-render              flag; inclusivity report only, no mp4 render
--render-seqs            comma-list of seqs to render (default: first seq only)
```

**Inputs read:**
| Path | Format | Notes |
|------|--------|-------|
| `{involvement_dir}/{seq}/involvement.json` | Part A | for inclusivity |
| `{clips_dir}/{seq}/clips_manifest.json` | Part B | clip records |
| `{clips_dir}/{seq}/clip_tags.json` | `{clip_basename: name}` | **THE TAGGING INPUT** — optional; if absent, falls back to `track_{tid:03d}` draft names |
| `{tracker_dir}/{seq}.txt` | MOT | for presence-fallback stretches |
| `{team_file}` | JSON | role lookup |
| `{follow_dir}/{seq}/follow_cam.json` | C-feed crop centers | render only |
| `{source}/{seq}/img1/*.jpg` | frames | render only |

**Tags consumption (line 119–129):**
```python
tags_path = Path(args.clips_dir, seq, "clip_tags.json")
tags = json.loads(tags_path.read_text()) if tags_path.exists() else {}
tags = {k: v for k, v in tags.items() if not k.startswith("__")}
# then: name = tags.get(Path(rec["clip"]).name)  <- keys by clip BASENAME
```
Tags dict is keyed by **clip filename basename** (e.g. `t007_m00_42s.mp4`), value is player name string or `"__skip__"`.

**Presence-fallback:** any substantial outfield track with zero involvement clips gets a fallback range (longest contiguous visible stretch) — ensures 100% coverage. Reported in inclusivity_report.json but the actual fallback clip is NOT automatically rendered by this script for untagged tracks (only reported).

**Outputs written:**
| Path | Format |
|------|--------|
| `{clips_dir}/{seq}/inclusivity_report.json` | per-seq coverage JSON |
| `{out}/inclusivity.md` | human-readable rollup |
| `{out}/inclusivity_summary.json` | committable summary |
| `{clips_dir}/{seq}/reels/{name}.mp4` | per-player reel, 854×480 (gitignored) |
| `{out}/sample_reel.mp4` | best player's reel at 640×360 |

**Upstream deps:** Part A + B + C (tags), tracker, team_assign, follow_cam, source frames.

**Imports:** `follow_cam._crop`, `detect_involvement.load_tracks` + constants.

---

## Chain: player_highlights (two-part, with tagging pause)

```
FOUNDATION (already run by backend)
  decode → track_alfheim → ball-cache → analyze_ball → analyze_pitch → team_assign
  Produces: tracks/<seq>.txt, ball_track/<seq>/trajectory.json,
            team_assign/track_teams.json, frames/<seq>/img1/%06d.jpg,
            follow_cam/<seq>/follow_cam.json   ← REQUIRED (must run follow_cam.py first)

PART 1 — "generate taggable clips"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 1: detect_involvement.py
  python scripts/detect_involvement.py <seq> \
    --tracker-dir <job_dir>/tracks \
    --ball-dir    <job_dir>/ball_track \
    --team-file   <job_dir>/team_assign/track_teams.json \
    --out         <job_dir>/involvement
  Output: <job_dir>/involvement/<seq>/involvement.json

Step 2: clip_player_highlights.py
  python scripts/clip_player_highlights.py <seq> \
    --involvement-dir <job_dir>/involvement \
    --follow-dir      <job_dir>/follow_cam \
    --source          <job_dir>/frames \
    --out             <job_dir>/player_highlights
  Output: <job_dir>/player_highlights/<seq>/clips_manifest.json
          <job_dir>/player_highlights/<seq>/clips/t{tid}_m{idx}_{sec}s.mp4

  ← GET /tagging-clips reads clips_manifest.json + serves mp4 files

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  *** PAUSE: OPERATOR TAGGING VIA OPERATOR APP ***
  POST /tag-clips  { "tags": {"t007_m00_42s.mp4": "Alice", ...} }
  Backend writes: <job_dir>/player_highlights/<seq>/clip_tags.json
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PART 2 — "assemble per-player reels" (after tags submitted)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 3: assemble_player_reels.py
  python scripts/assemble_player_reels.py <seq> \
    --involvement-dir <job_dir>/involvement \
    --clips-dir       <job_dir>/player_highlights \
    --tracker-dir     <job_dir>/tracks \
    --team-file       <job_dir>/team_assign/track_teams.json \
    --follow-dir      <job_dir>/follow_cam \
    --source          <job_dir>/frames \
    --out             <job_dir>/deliverables/player_highlights \
    --render-seqs     <seq>
  Output: <job_dir>/player_highlights/<seq>/reels/<player_name>.mp4
          <job_dir>/player_highlights/<seq>/inclusivity_report.json
```

**follow_cam.py dependency:** `clip_player_highlights.py` and `assemble_player_reels.py` both read `follow_cam/<seq>/follow_cam.json`. This must be run as part of the foundation before Part 1:
```
  python scripts/follow_cam.py <seq> \
    --ball-dir   <job_dir>/ball_track \
    --track-dir  <job_dir>/tracks \
    --source     <job_dir>/frames \
    --out        <job_dir>/follow_cam \
    --no-render
```
Note: `follow_cam.py` also reads `--gt-zip datasets/soccernet_gsr/test.zip` but only for an optional GT metric — silently skips if absent (line 460: `try/except`). **Not a hard blocker.**

---

## What the operator tags (clip_id + tags.json shape)

**Unit of tagging:** one clip = one involvement moment for one track. The clip shows a few seconds of a single continuously-visible player. The operator assigns ONE name per clip (or bulk-names all clips for the same track_id in one keypress).

**clip_id = clip filename basename:**
```
t{tid:03d}_m{idx:02d}_{start_sec:.0f}s.mp4
```
Examples: `t007_m00_42s.mp4`, `t023_m03_187s.mp4`

**tags.json written to:**
```
<job_dir>/player_highlights/<seq>/clip_tags.json
```

**Shape (what assemble_player_reels.py reads — line 119–121):**
```json
{
  "t007_m00_42s.mp4": "Alice",
  "t007_m01_98s.mp4": "Alice",
  "t023_m03_187s.mp4": "Bob",
  "t031_m00_210s.mp4": "__skip__"
}
```
- Keys: clip filename basenames (no path, no directory prefix)
- Values: player name string, OR `"__skip__"` to exclude clip
- Keys starting with `__` are stripped by assemble_player_reels.py (line 121) — safe to omit from API output
- Untagged clips fall back to `track_{tid:03d}` draft name (not skipped)

**Minimal edit to read from a backend-written tags.json:** none needed. `assemble_player_reels.py` already reads from `{clips_dir}/{seq}/clip_tags.json` — the backend just writes that file before invoking Step 3.

---

## /tagging-clips: what to expose

`GET /tagging-clips?job_id=X&seq=Y` should return, per clip:

```json
{
  "clips": [
    {
      "clip_id": "t007_m00_42s.mp4",
      "track_id": 7,
      "seq": "SNGS-118",
      "involve_start_sec": 42.0,
      "involve_end_sec": 45.2,
      "strength": 1.24,
      "start_frame": 1001,
      "end_frame": 1125,
      "mp4_url": "/clips/<job_id>/<seq>/t007_m00_42s.mp4",
      "role": "TeamA"
    },
    ...
  ]
}
```

**Source of truth:** `clips_manifest.json` already contains all these fields per clip record. The backend serves the mp4 at:
```
<job_dir>/player_highlights/<seq>/clips/<clip_name>
```

**Preview frame alternative:** `tag_clips.py` uses the mid-involvement frame as a key-frame preview: `frame = (start_frame + end_frame) // 2`, then C-feed crop. Backend could serve this as a thumbnail instead of / in addition to the full mp4.

---

## Couplings to break

| Coupling | Location | Fix |
|----------|----------|-----|
| Hardcoded `SEQS_DEFAULT` | `detect_involvement.py:39`, `clip_player_highlights.py:123`, `assemble_player_reels.py:223` | Always pass `<seq>` positional arg |
| `--tracker-dir` defaults to SoccerNet botsort path | all scripts | Pass `--tracker-dir <job_dir>/tracks` |
| `--source` defaults to `datasets/soccernet_tracking` | `clip_player_highlights.py`, `assemble_player_reels.py`, `follow_cam.py` | Pass `--source <job_dir>/frames` |
| `--team-file` defaults to SoccerNet outputs path | `detect_involvement.py`, `assemble_player_reels.py` | Pass `--team-file <job_dir>/team_assign/track_teams.json` |
| `--follow-dir` defaults to `outputs/follow_cam` | `clip_player_highlights.py`, `assemble_player_reels.py` | Pass `--follow-dir <job_dir>/follow_cam` |
| `--gt-zip` in `follow_cam.py` | `follow_cam.py:410` | Not needed; silently skipped if absent |
| `follow_cam.py` reads first frame to get W/H (`img0 = cv2.imread(...)`) | `follow_cam.py:447` | Hard dep on frames existing at run time |
| `tag_clips.py` is Tkinter GUI — not usable in backend | `tag_clips.py` entire script | Backend replaces with REST API + writes `clip_tags.json` directly |

---

## Hard blockers vs skippable

### Hard blockers
1. **`follow_cam.py` must run before Part B/D** — both `clip_player_highlights.py` and `assemble_player_reels.py` read `follow_cam/<seq>/follow_cam.json`. If absent, they crash at `load_centers()` / line 132.
2. **Source frames must exist for mp4 rendering** — `clip_player_highlights.py` and `assemble_player_reels.py` are frame-gated. Manifest is always written, but clips are hollow (`rendered: false`) without frames. For a real backend deployment, frames must be present at `<job_dir>/frames/<seq>/img1/`.
3. **`team_assign/track_teams.json` must contain the seq key** — `detect_involvement.py` calls `.get(seq, {})` (line 85) so missing seq → empty role dict → all tracks excluded as non-outfield. Silent failure, no coverage.

### Skippable / non-blocking
- `--gt-zip` in `follow_cam.py` — caught with try/except, skipped gracefully.
- `--no-clips` flag — clip_player_highlights.py writes manifest without frames; downstream scripts handle `rendered: false`.
- `tag_clips.py` entirely — the backend bypasses it and writes `clip_tags.json` directly.
- `--no-render` in `assemble_player_reels.py` — inclusivity report always written; reels are optional.
- `distribution.png` matplotlib render in `detect_involvement.py` — fails only if matplotlib absent; does not affect JSON outputs.

---

## Identity-fragmentation reality (Day-26/30/31)

- At SoccerNet 5-seq scale (each ~750 frames / 30s): ~**189 substantial outfield tracks** across 5 seqs, averaging ~38/seq. With Day-27 tag-per-clip + presence-fallback: **100% coverage**.
- At full-match scale (Alfheim 47min, Day-31): tracker produced **5,106 raw IDs** → de-frag to ~4,186 → still **2,224 clips per half** requiring **3–12 hours of human tagging**. This is the known upstream blocker for production full-match deployment.
- The backend should surface the clip count before the operator starts tagging so they can decide whether to proceed.
- Presence-fallback is implemented in `assemble_player_reels.py` (`verify_inclusivity`) and reported in `inclusivity_report.json`, but fallback clips for zero-involvement tracks are **reported only, not rendered**, unless involvement clips exist. Backend may need to extend this.
