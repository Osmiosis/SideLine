# Day 32 — Formation-Invariant Dead-Ball Identity Anchor (PROBE) — football, ZXY-validated

Probe of ONE untried appearance-free lever against full-match identity drift: re-anchor track IDs at
dead-balls by registering consecutive settled position-sets to each other (formation-INVARIANT point-set
registration — no assumed tactical template, so it transfers to DPS school games). **Measure-first, honest
keep-or-drop.** Scorer = the Day-30 ZXY-grounded identity metric (`alfheim_identity_metric.py`). Baseline =
Day-30 re-linked safe −18% tracks (4,186 IDs). Alfheim full half (47 min, fixed single cam = worst-case input).

**Verdict: DROP.** Negligible identity lift, and the lever fails from both ends (sparse genuine anchors;
spurious registration on loose anchors).

---

## PART A — anchor detection (+ a genuineness discriminator)

Detected settled moments from motion (no event labels, no ball): low median player speed + spatial spread +
enough in-view tracks, sustained. Two anchor sets:

| anchor set | criterion | # found | genuine dead-balls? |
|---|---|---|---|
| **settled** | low-motion (≤1.2 m/s) + spread + ≥6 in view | **60** | NO — mostly low-motion *in-play* (this match walks 56.5% of the time per ZXY), not dead-balls |
| **kickoff** | + centre circle (±10 m of centre spot) near-empty + players split across the halfway line, ≤0.6 m/s | **4** | YES — f11 (start-of-half kickoff) + ~3 centre restarts at 22 / 26 min |

The **kickoff filter** (detect the centre-circle-empty, half-split geometry of a real kickoff — no ball
needed) is the genuineness discriminator the generic detector lacked. It shows the honest Part-A answer:
**genuine centre-circle dead-balls are extremely sparse — ~4 in 47 min.** That alone bounds the lever: even
perfect re-pinning at 4 anchors can dent IDs-per-player by at most ~4 fragments out of 183.

---

## PART B — formation-invariant registration + ID re-unify

At each anchor, the in-view player pitch-positions (via the fixed H). Between consecutive anchors, **trimmed
rigid ICP** (rotation+translation, geometry only, NO appearance, NO template) recovers a correspondence;
corresponded track IDs are merged (union-find). **Over-merge guard** = direct ZXY check: for each merge
whose endpoints both match a home GT player, did it join the SAME player (good) or DIFFERENT (over-merge)?

| mode | anchors | merge pairs | IDs before→after | GT-check: same / DIFFERENT / undet |
|---|---|---|---|---|
| settled | 60 | 212 | 4,186 → 4,045 (−3.4%) | **2 / 5 / 205** |
| kickoff | 4 | 16 | 4,186 → 4,178 (−0.2%) | 0 / 0 / 16 |

**Settled registration is mostly WRONG:** of the 7 merges verifiable against GT, **5 joined different players,
only 2 the same** — point-set registration between two low-motion snapshots minutes apart (different players
in view, no preserved rigid configuration) recovers spurious correspondences. **Kickoff registration** makes
too few merges to verify (none of the 16 had both endpoints GT-matched — away-team / unmatched).

---

## PART C — lift vs ZXY (the verdict)

| Metric | Day-30 re-linked (baseline) | Day-32 settled (60 anchors) | Day-32 kickoff (4 genuine) |
|---|---|---|---|
| IDs-per-GT-player (median) | **183** | 179 (−2.2%) | **183** (flat) |
| IDs-per-GT-player (mean) | 165.0 | 158.4 | 164.6 |
| identity purity | **0.116** | 0.117 | 0.116 |
| IDF1 | **0.008** | 0.009 | 0.008 |
| id-switches vs GT | 2576 | 2554 | 2574 |
| over-merge (tracks spanning ≥2 GT, strict) | 437 | 409 | 435 |

**Purity and IDF1 are FLAT in both modes** — the only thing that determines the verdict (raw ID count is not
the metric; Day-30 lesson). The small IDs/GT drop in settled mode is consolidation of short/away tracks, not
identity recovery (purity didn't move). Over-merge didn't blow up (the merges are too few / consolidating),
but the *direction* of the verifiable settled merges (5 wrong : 2 right) shows the mechanism is unreliable.

---

## Verdict & synthesis — DROP

Formation-invariant dead-ball anchoring gives **no meaningful identity lift** on this footage, for two
complementary reasons:
1. **Genuine dead-balls are too sparse** (~4 centre-circle moments / half) → re-pinning at them moves
   IDs-per-player <1%. Anchoring *bounds* drift by periodic reset, but with so few resets there's almost
   nothing to bound.
2. **Loosening the anchor definition** to gather more (60) pulls in low-motion *in-play* moments that are
   NOT preserved formations, so the point-set registration between them is mostly spurious (more wrong than
   right vs GT) — no purity gain and an over-merge risk.

**Per the PRD's lower-bound logic:** it was hoped a positive on worst-case Alfheim would lower-bound the DPS
benefit. It is NOT positive, so no DPS lower bound is claimed. And the *sparsity* of dead-balls (~4/half) is
structural — cleaner DPS dual-cam tracklets would make registration more accurate but would NOT add more
dead-balls — so the sparse-reset ceiling likely transfers. The cheapest identity lever has now been tested
and shelved.

**Where identity stands:** per-player outputs remain blocked at full-match scale (Day-30/31). The remaining
untried lever is the heavier **global min-cost-flow stitcher**, but it needs cleaner tracklets than Alfheim's
single wide cam provides → **defer to real DPS dual-cam footage**. This probe correctly tested the cheap
lever first and documented its failure cheaply.

### Caveats
- ZXY = home-team-only metric (~11 players) → home-team identity stability; still a real GT.
- Sparse anchors bound but don't eliminate drift; Alfheim is worst-case single-cam input (DPS expected
  cleaner, but not denser in dead-balls); still a proxy (kit/court/lighting/optics differ from DPS).
- Over-merge verifiable only where both merge endpoints hit home GT; away-team merges unverifiable.
