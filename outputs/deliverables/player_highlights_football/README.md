# Inclusive Player Highlights — football (output #2)

AI Sports Recording & Analytics — DPS MIS Doha. SoccerNet is the **method proxy**; the real
target is DPS footage.

## What this is
Per-player highlight reels built to be **inclusive**: every player who was on court gets
footage — not just the stars. This is the deliberate contrast to event highlights (output #3),
which surface only exciting moments and so concentrate on scorers/playmakers. The school value
is "every child seen" (a parent wants *their* kid), and inclusive reels are a genuine
differentiator vs VEO/Pixellot's star/ball focus.

## How it works (no magic — reuses Days 9/12/13/24/25)
1. **Involvement detection** (`detect_involvement.py`) — per confident-ball frame, the nearest
   player track within an "on-ball" radius gets credited; merged into per-track involvement
   ranges. Pure math on cached tracks + ball trajectory (no frames, no GPU). Only genuinely
   *detected* ball frames count (lost-ball discipline — no fabricated involvement).
2. **Clip from the C-feed** (`clip_player_highlights.py`) — each range + padding (−2s/+1s) is
   cut from the Day-13 **C-feed** (player-stabilized — the right feed for player-subject
   footage; the ball-centric A-feed is for event highlights).
3. **Tag-per-clip identity** (`tag_clips.py`) — identical house kits (no numbers/names) make
   auto-identity impossible (Day-26 ReID: AssA +0.004). So the **user names each short clip**;
   each clip shows one continuously-visible person → unambiguous even in identical kits.
   Pre-grouped by track id for bulk-naming.
4. **Assemble + verify** (`assemble_player_reels.py`) — group clips by name, rank by
   involvement-strength, concat with a title card → one reel per player.

## Inclusivity — the goal check
**189/189 substantial outfield players across 5 sequences get footage (100%).**
- 55 via involvement clips (the near-ball players).
- 134 via **presence-clip fallback**: players who were on court but were never the nearest
  player to a *detected* ball (deep defenders / keeper / brief fragments) still get their
  longest visible stretch clipped, so nobody is left out. Involvement alone covers only 29% —
  the fallback is what makes the deliverable actually inclusive.

See [`inclusivity.md`](inclusivity.md) for the per-sequence table and
`outputs/player_highlights/<seq>/inclusivity_report.json` for per-player detail.

## Honest caveats
- Involvement is a **nearest-player proxy** (plausibility-level "near the ball", not exact
  per-touch).
- The on-ball radius is **bbox-height-normalized** (a homography substitute; pitch-meter
  calibration is available as a drop-in refinement) — re-tune at the DPS mount.
- `sample_reel.mp4` here is the most-involved player's reel (SNGS-118, downscaled). Full
  per-player **tagged** reels require the human Part-C tagging pass (`tag_clips.py`, a GUI);
  without tags, `assemble_player_reels.py` produces per-track *draft* reels (local, gitignored).

## Files
- `inclusivity.md` — per-sequence inclusivity rollup (the goal check).
- `outputs/involvement/<seq>/` — involvement.json + distribution.png.
- `outputs/player_highlights/<seq>/` — clips_manifest.json, inclusivity_report.json,
  clip_tags.json (after tagging); clips/ and reels/ video are local (gitignored).
