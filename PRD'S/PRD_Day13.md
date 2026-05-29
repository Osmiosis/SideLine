# PRD — Day 13: Follow-Cam (virtual camera, pro techniques) — Football
**Project:** AI Sports Recording & Analytics System
**Goal:** Generate a smooth, broadcast-style follow-cam by virtually cropping the wide frame around a blended ball+player-action target, using the documented professional techniques: bidirectional lookahead smoothing (we're offline), ball+player-density blend target, asymmetric pan limits, constant-velocity-preferring trajectory. Evaluate by EYE (perceptual deliverable — no ground-truth crop). Football, SoccerNet.
**Estimated time:** 3–4 hours
**Environment:** Windows 11, RTX 4060, Python 3.11, existing `.venv`, repo; Day-12 pixel-space ball trajectory; Day-9 player tracks; SoccerNet seqs

---

## Context + the techniques (read first — these are documented pro methods, not guesses)

VEO/Pixellot-class systems generate follow-cam by digitally cropping a wide recording (exactly our dual-phone-wide → digital-crop architecture). Key documented techniques we're using:

1. **Crop target = ball + player-density BLEND, not raw ball.** Serious systems compute "actionness" from a ball detector AND a player occupancy/saliency map — because naive ball-centering whips the camera on long kicks and chases false-positive balls. The crop should aim at a weighted blend of (ball position) and (player centroid/density), so when the ball is uncertain/aerial/missing, the player mass keeps the camera on the action.

2. **Bidirectional lookahead smoothing (the key smoothness trick).** Because we POST-PROCESS (not live), we have the whole future trajectory. Pro systems run "a virtual camera on a delay" so future ball positions are known and the path can be planned smooth (Pixellot uses a ~5s buffer). We can smooth the crop-center path BIDIRECTIONALLY (forward+backward filter, zero phase lag) — far smoother than causal real-time tracking. This is the single biggest "looks professional" factor.

3. **Asymmetric pan limits.** Analysis of real camera operators: acceleration easing INTO a motion can be higher than deceleration easing OUT. Encode asymmetric accel/decel caps on crop-center velocity for human feel.

4. **Constant-velocity-preferring trajectory.** Smooth pro trajectories prefer holding still or constant-velocity segments, transitioning smoothly — not nervously micro-adjusting. Heavy smoothing + a dead-zone (don't move the crop for small target movements) achieves this.

**Evaluation is PERCEPTUAL.** No ground-truth "correct crop" exists. We judge by WATCHING against named failure modes (jitter, whip-pan, ball-near-edge, swing-to-nowhere). Compute light proxies (ball-in-safe-zone %, crop-center jerk) as supporting evidence only — the eye is the arbiter.

**Scope: FOOTBALL, SoccerNet.** Basketball follow-cam later (different aspect/pace). This produces the tracked-view that feeds player highlights + event reels later.

---

## Build order (sequence matters — see each layer work before adding the next)

## PART A — Smoothed crop around the ball (baseline) (~50 min)
1. Use the Day-12 pixel-space ball trajectory (detected+predicted, per-frame). This is the raw crop-center signal.
2. Define the crop: a fixed-size window (start ~1/2.5 of frame width, 16:9) centered on the target, clamped to stay within frame bounds (no cropping outside the image).
3. **Bidirectional smooth** the crop-center path: forward-backward low-pass (e.g. scipy filtfilt) or a bidirectional Kalman smoother — zero phase lag, heavy smoothing. Tune cutoff so the path is visibly smooth.
4. Render the cropped video. WATCH IT.

**STOP. Report: baseline smoothed crop — watchable? where does it fail (whip on long balls? drift when ball predicted/missing? ball hugging edge)?**

## PART B — Blend target: ball + player density (~50 min)
1. Per frame compute player centroid (and optionally density/occupancy weighting) from Day-9 player tracks in PIXEL space.
2. Crop target = weighted blend: `target = w_ball * ball_pos + (1-w_ball) * player_centroid`, where w_ball DOWN-weights when ball is low-confidence/predicted/aerial-flagged (from Day-12 flags) and UP-weights when ball is confidently detected. So confident ball → follow ball; uncertain ball → follow player mass.
3. Re-smooth (bidirectional) the blended target path. Render. WATCH IT.

**STOP. Report: does the blend fix the baseline's failures (no more swings-to-nowhere on missing ball, calmer on long kicks)? new issues?**

## PART C — Asymmetric pan limits + constant-velocity polish (~40 min)
1. Cap crop-center velocity/acceleration with ASYMMETRIC limits (accel-in allowed faster than decel-out). Prevents whip-pans while keeping responsive starts.
2. Add a small DEAD-ZONE: if the target moves less than a few px from current crop center, don't move (kills micro-jitter, encourages constant-position segments).
3. Optionally bias toward constant-velocity: where the target moves steadily, let the crop glide at constant velocity rather than reic. Render. WATCH IT.

**STOP. Report: does it now feel like a human operator (smooth holds, gentle eased pans)? compare A vs B vs C side by side.**

## PART D — Light proxy metrics + eval (~30 min)
Supporting evidence only (eye is the arbiter):
1. **Ball-in-safe-zone %:** fraction of frames where the (detected) ball falls within a central safe-zone of the crop (not hugging edges). Higher = better framing.
2. **Crop-center jerk:** mean magnitude of 2nd/3rd derivative of crop-center path — lower = smoother. Compare A vs B vs C to show smoothing worked.
3. **Action-in-frame:** fraction of player detections inside the crop (are we keeping the play, not just the ball?).
Report these as A/B/C comparison, but lead with the perceptual verdict.

## PART E — Render finals, log, commit (~30 min)
1. Render 1-2 full sample sequences with the final (C) follow-cam. Keep a side-by-side or A/B/C montage if cheap.
2. notes.md `## Day 13`: the documented techniques used (blend target, bidirectional lookahead smoothing, asymmetric pans — cite that these are the VEO/Pixellot/research approach, not invented), build-order results, the perceptual verdict per stage, the proxy metrics (jerk reduction A→C, ball-in-safe-zone %), honest failure modes that remain, and:
   - What feeds onward: this tracked-view IS the input to player highlights + event reels.
   - Deployment note: crop ratios/pan limits are camera-distance dependent; school footage needs re-tuning. Still SoccerNet-validated-only.
3. gitignore checks (NDA, big videos); commit scripts + notes + a short sample clip if size allows (else a few frames):
   `git commit -m "Day 13: follow-cam virtual camera (blend target + bidirectional lookahead smoothing + asymmetric pans, VEO/Pixellot-style); perceptual eval"`; push.

---

## End-of-day report (developer → planning chat)
1. ✅/❌ per Part
2. Baseline (A) — watchable? main failure modes?
3. Did the blend target (B) fix swings-to-nowhere / long-kick whips?
4. Did asymmetric limits + dead-zone (C) make it feel human?
5. Proxy metrics: jerk reduction A→C, ball-in-safe-zone %, action-in-frame %
6. PERCEPTUAL VERDICT: is the final follow-cam watchable / broadcast-ish? remaining failure modes?
7. Errors hit (even if fixed)
8. Time taken

---

## Do NOT today
- Do NOT naively center on raw ball position — blend with player density (documented pro fix for whip-pans / missing-ball swings).
- Do NOT use causal/real-time smoothing — we're offline, use BIDIRECTIONAL lookahead smoothing (the key pro smoothness technique; zero phase lag).
- Do NOT over-engineer proxy metrics — this is perceptual; watch it, metrics are supporting only.
- Do NOT crop outside frame bounds — clamp the window.
- Do NOT do basketball follow-cam (later) or build highlights/reels yet (this tracked-view feeds them next).
- Do NOT commit SoccerNet raw data (NDA) or huge video files — short sample or frames only.
