# Inclusive Player Highlights - football (output #2, SoccerNet proxy for DPS)

**The inclusivity goal:** event highlights (output #3) surface only exciting moments
-> stars get footage, quiet kids get nothing. Player highlights must include EVERYONE
(the DPS value: every child seen; parents want THEIR kid -- a genuine differentiator
vs VEO/Pixellot's star/ball focus).

**Identity = human tag-per-clip**, NOT auto-ReID: identical house kits (no numbers/names)
make auto-identity impossible (Day-26 ReID: AssA +0.004). Each short clip = one visible
person -> the user names it unambiguously.

**Coverage = involvement clips + presence-clip fallback** for on-court players who were
never near a confident ball (deep defenders / GK / brief fragments), so nobody is left out.

| seq | substantial players | covered | via involvement | via presence-fallback | clips/player (min/med/max) |
|-----|--------------------|---------|-----------------|----------------------|----------------------------|
| SNGS-116 | 50 | 50 (100.0%) | 7 | 43 | 0/0/2 |
| SNGS-117 | 36 | 36 (100.0%) | 11 | 25 | 0/0/2 |
| SNGS-118 | 31 | 31 (100.0%) | 11 | 20 | 0/0/3 |
| SNGS-119 | 24 | 24 (100.0%) | 9 | 15 | 0/0/3 |
| SNGS-120 | 48 | 48 (100.0%) | 17 | 31 | 0/0/3 |

**Total: 189/189 substantial outfield players get footage (100.0%)** -- involvement clips for near-ball players, presence clips for the rest.

Honest caveats: involvement = nearest-player proxy (plausibility-level near-ball, NOT
exact per-touch); SoccerNet footage (DPS-pending); house-kit ID-switch means one player
may span several track ids -> tag-per-clip re-unites them under one name; tagging is
manual effort (one name per short clip, bulk-named per un-switched track).
