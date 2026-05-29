# Your Side — Day 12 (Ball Tracking + Kalman, pixel-space / project-on-use)

The hardest piece left. Ball detected ~half the frames; Kalman predicts through the gaps. Decided architecture: Kalman in PIXEL space, project to pitch only where an analytic needs meters. Football, SoccerNet.

## Why this architecture (the thing you figured out)
Your three deliverables consume the ball differently: follow-cam crops in PIXELS, possession needs METERS, events need velocity. So smooth the trajectory where the noise and the main consumer live (pixels), and project to pitch only on-demand for possession/path-drawing. Bonus: this sidesteps the airborne-ball problem entirely (a ball in the air has a valid pixel position; only pitch projection breaks for aerial balls).

## The mental model
49% raw detection → Kalman fills gaps → continuous trajectory. Win metric: effective ball-availability after Kalman vs 49% before. The pixel trajectory feeds follow-cam; the projected-on-use pitch trajectory feeds possession.

## Three things to watch

### Part 0 gates validation — GSR ball GT and its form
- [ ] Claude Code checks: does GSR label the ball, and in pixel bbox or pitch coords? Pixel bbox = cleanest (validate the pixel trajectory directly, no homography in the validation path). Determines how you'll know it works.

### The FP velocity gate
- [ ] soccana has false-positive ball detections. The Kalman rejects any "detection" implying the ball jumped an implausible pixel distance in one frame. Watch the rendered track for snaps to weird locations — that's an FP that beat the gate.

### Aerial balls (now a flag, not a crisis)
- [ ] Because the Kalman is in pixel space, airborne balls are tracked fine in the image. The only place they err is when PROJECTED to pitch (a high ball projects to a wrong pitch spot). Part C flags aerial-suspect frames as lower-confidence. You're not solving ball height (that's research-level / future work) — just flagging it. Expect some aerial frames flagged; that's correct behavior.

## Judgment calls

### After Part D (validation)
- [ ] If GSR has ball GT: the headline is PREDICTED-frame RMSE (error during the gaps — proves gap-filling works; detected-frame RMSE is trivially low). And effective-recall lift: 49% → what?
- [ ] If no GT: does pixel-velocity look like real football (passes/shots, not teleportation)? 
- [ ] ALWAYS watch the render: does the predicted ball (color-coded) follow the real ball through detection gaps, or drift into empty space?

## What to log
The pixel-space/project-on-use architecture + WHY (deliverable-driven — this is good report material), GSR ball-GT form, detection rate + gaps, Kalman design, validation, effective-recall lift, aerial-flag fraction, and the deployment-pending caveat.

## Send me at end of day
1. ✅/❌ per Part
2. GSR ball GT? coordinate form?
3. Raw detection rate + gap distribution
4. Kalman design (state, velocity gate, loss N)
5. Validation: predicted-frame RMSE or plausibility; effective-recall lift (49% → ?)
6. Sanity gate (GT-as-detection → RMSE ~0) if GT
7. Aerial-suspect fraction; does the track follow the ball through gaps? (screenshot)
8. Errors + time

## Expectations
- Hardest piece — don't expect Day-10/11 cleanliness. A solid effective-recall lift (49% → 75%+) with believable trajectories = strong result.
- Pixel-space makes follow-cam essentially fall out for free (smooth pixel ball = crop center).
- Football first (ground-pass physics suits simple Kalman); basketball ball (dribbles/shots) is erratic, later.

## Don't
- ❌ Don't run the Kalman in pitch space — pixel space, project on use.
- ❌ Don't solve 3D ball height — flag aerial-suspect, future work.
- ❌ Don't let FP detections yank the track — velocity gate; watch for snaps.
- ❌ Don't predict through long gaps — stop/re-init after N.
- ❌ Don't do basketball ball or players today.
- ❌ Don't trust validation until the GT-as-detection sanity gate passes (if GT exists).
- ❌ Don't commit SoccerNet raw data.

## If you finish fast — build POSSESSION
You'll now have ball position (Kalman, projected to pitch) AND team assignment (Day 11). Build the possession proxy: per frame, which team's nearest player is closest to the ball → possession %. It's the deliverable that needed BOTH, and you'd finally have both. A team-possession % is a striking, coach-friendly number — and the first analytic combining two prior sessions' work. Then report.
