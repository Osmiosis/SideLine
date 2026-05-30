# Inclusive Player Highlights - basketball (output #2, SportsMOT proxy for DPS)

**Parity with football (Day-27).** Same mechanism -- per-player reels, human tag-per-clip,
presence fallback -- but involvement was RE-DERIVED for the half-court (see below).

**Why a fixed radius fails in basketball:** football involvement = nearest player within ~2.5 m.
On a half-court all players cluster near the ball; a fixed radius marks ~1.5 players/frame and
74% of all players involved -> no discrimination. The chosen `gap` definition (nearest AND clearly
closer than the 2nd-nearest) concentrates 96% of involvement on the top-3 ball-handlers, so
involvement means ball-handler -- and the presence fallback (heavier here than football) covers
everyone else.

**Identity = human tag-per-clip** (identical house kits -> auto-ID impossible, Day-26).

**Coverage = involvement clips + RENDERED presence clips** (basketball renders presence, not just
defines it -- it's the majority of coverage here).

## Clippable deliverable (cleaned C-feed available: c001, c007)

| seq | substantial | covered | via involvement | via presence | clips/player (min/med/max) |
|-----|-------------|---------|-----------------|--------------|----------------------------|
| c001 | 8 | 8 (100.0%) | 4 | 4 | 1/1/5 |
| c007 | 7 | 7 (100.0%) | 2 | 5 | 1/1/1 |

**Total (C-feed seqs): 15/15 substantial players get footage (100.0%)** -- involvement for ball-handlers, presence clips for the rest.

## Involvement measured, clipping pending (no cleaned C-feed: c003, c005, c008)

The Day-15/16 follow-cam head-FP cleaning produced a player-stabilized C-feed only for c001/c007.
These seqs have involvement MEASURED (Part A) but no cleaned feed to clip from:

| seq | substantial | would-be via involvement |
|-----|-------------|--------------------------|
| c003 | 11 | 5 |
| c005 | 11 | 3 |
| c008 | 10 | 3 |

## Honest caveats
- involvement leans on the plausibility-level basketball ball track (Day-19, noisier than
  football's RMSE-validated) -> more presence reliance, by design.
- nearest-player proxy, NOT exact per-touch; lost-ball frames excluded (confident ball only).
- height-normalized radius re-tuned for basketball; re-tune at the DPS camera mount.
- house-kit ID-switch means one player may span several track ids -> tag-per-clip re-unites them.
- SportsMOT proxy validates METHOD; real target = DPS.
