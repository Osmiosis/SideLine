# Day 13 — Follow-Cam (virtual camera), Football / SoccerNet

Broadcast-style follow-cam by digitally cropping a fixed 16:9 window (768×432, a 2.5×
zoom) out of the wide 1920×1080 frame and steering its center to follow the action.
Documented VEO / Pixellot-class techniques (not invented here):

1. **Blend target** = `w·ball + (1−w)·player-centroid`; `w` down-weights when the ball is
   predicted / aerial-suspect / lost (Day-12 flags) → confident ball follows the ball,
   uncertain ball follows the player mass.
2. **Bidirectional lookahead smoothing** — offline forward-backward Butterworth (scipy
   `filtfilt`, zero phase lag, 0.8 Hz). The single biggest "looks professional" factor.
3. **Asymmetric pan limits** — velocity capped by braking-distance (can always decelerate
   to rest → never overshoots/oscillates); accel-in may exceed decel-out (gentle landing).
4. **Dead-zone** — holds the crop for sub-6px target moves → locked-off segments.

**Evaluation is PERCEPTUAL** (no ground-truth crop exists). The metrics below are
supporting evidence only; the arbiter is watching `follow_C.mp4` / `abc_montage.mp4`
(rendered locally — `*.mp4` is gitignored) and the committed frame grids + plots.

Variants: **RAW** = naive ball-center (ship-NONE) · **A** = smoothed ball-only ·
**B** = smoothed blend · **C** = B + asymmetric limits + dead-zone (the **final**).

---

## Proxy metrics (RAW / A / B / C)

Lower jerk = smoother. Higher ball-in-safe-zone / action-in-frame = better framing.
Lower clamp-fraction = the crop is not jammed against the frame edge (ball-near-edge).

### SNGS-118 — "Shots off target" (ball detected 498 / predicted 97 / lost 155; mean w=0.64)
| metric | RAW | A | B | C (final) |
|---|---:|---:|---:|---:|
| crop-center jerk (px) | 3.186 | 0.127 | **0.107** | 0.361 |
| ball-in-safe-zone | 1.000 | 1.000 | 1.000 | 0.998 |
| true-ball-in-crop (GT) | 1.000 | 1.000 | 0.852 | 0.859 |
| action-in-frame | 0.261 | 0.261 | 0.412 | **0.411** |
| frame-edge clamp | 0.136 | 0.137 | **0.000** | **0.000** |

### SNGS-120 — "Foul" (detected 404 / predicted 158 / lost 188; mean w=0.54)
| metric | RAW | A | B | C (final) |
|---|---:|---:|---:|---:|
| crop-center jerk (px) | 5.059 | 0.317 | **0.321** | 0.472 |
| ball-in-safe-zone | 0.983 | 0.983 | 0.901 | 0.869 |
| true-ball-in-crop (GT) | 0.983 | 0.981 | 0.778 | 0.784 |
| action-in-frame | 0.273 | 0.275 | 0.359 | **0.360** |
| frame-edge clamp | 0.359 | 0.364 | **0.091** | **0.091** |

### SNGS-116 — "Corner" (stress case: detected 143 / predicted 94 / lost 513; mean w=0.18)
| metric | RAW | A | B | C (final) |
|---|---:|---:|---:|---:|
| crop-center jerk (px) | 1.941 | 0.261 | **0.203** | 0.678 |
| ball-in-safe-zone | 0.993 | 0.986 | 0.909 | 0.790 |
| true-ball-in-crop (GT) | 0.714 | 0.710 | 0.467 | 0.464 |
| action-in-frame | 0.399 | 0.397 | 0.539 | **0.540** |
| frame-edge clamp | 0.264 | 0.271 | **0.007** | **0.003** |

---

## Perceptual verdict (the arbiter — from actually WATCHING)

**No single winner — a genuine tradeoff, so all three variants are kept:**

- **A (ball-only) is the best at following the actual BALL — shots and high passes included.**
  It tracks the ball up into the air (confirmed on watching the A|B|C montage). For a
  follow-cam whose first job is "follow the ball," that faithfulness is the key property. Its
  costs are real but situational: on a **sustained** ball-loss it swings to nowhere
  (`SNGS-118_abc_frames.png` row 3: A films the crowd / ad-boards; `SNGS-118_path_plot.png`:
  A's y collapses to ~220), and it jams the crop to the frame edge 13–36% of frames.
- **B / C are smoother and more stable** — edge-clamp → 0–9%, action-in-frame +50–58%, calm
  through ball-loss, locked holds (C). BUT they down-weight the aerial ball (anti-whip), so
  they stay **ground-focused on shots / high passes** — they do NOT follow the ball into the
  air. Better for steady framing of ground play, worse for the aerial action.
- **Bidirectional smoothing is what makes all three watchable** — jerk 3–5 px → 0.1–0.3 px
  (~15–25×), every whip-pan spike removed (`SNGS-118_speed_plot.png`: RAW 90–125 px/frame →
  gone). This part of the pro thesis fully holds.
- **C adds whip-safety + locked holds** over B; on these already-smoothed paths the effect is
  marginal (B is mathematically smoothest — a discrete rate-limiter scores slightly higher on
  3rd-derivative jerk, but the pans are smooth, no sawtooth). Value: robustness on whip-prone
  footage.

**Net:** A's ball-faithfulness (shots + high passes) is the priority for a highlights/event
feed; B/C's stabilization is the better base for steady tactical framing. A production blend
(A's ball-following + B's lost-ball fallback + a wider set-piece crop) is the natural next
step — left for later; the three variants are kept as-is.

## Honest remaining failure modes
- **True-ball-in-crop drops to ~85% (118/120) and ~46% (116 corner).** When the ball is
  genuinely lost/aerial, the camera correctly follows the player mass, so the (high,
  undetected) ball can sit outside the tight 2.5× crop. Correct behavior, but the metric
  reflects it. A wider crop (lower zoom) for set-pieces would recover most of this.
- When play hugs the far touchline the crop frames ad-boards above the players (no vertical
  bias yet). A small upward target offset (frame players low) is a known broadcast fix.
- SoccerNet-validated only; crop ratio + pan limits are camera-distance dependent and need
  re-tuning for school footage.

**What feeds onward:** `outputs/follow_cam/<seq>/follow_cam.json` (all three A/B/C crop-center
paths) is the tracked-view input to player highlights + event reels next — downstream picks A
(ball-faithful) or B/C (stabilized).
