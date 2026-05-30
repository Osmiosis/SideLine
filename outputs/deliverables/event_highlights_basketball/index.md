# Basketball Event Highlight Candidates - RANKED (output #3 parity)

**Output #3, basketball half** (Student Council reel). HIGH-RECALL + **INTEREST-RANKED**:
basketball is shot-dense, so the set is sorted best-first (made-baskets/blocks top, routine
attempts bottom) -- the editor skims top-down and isn't drowned. Motion-only; AUDIO (whistle/
crowd) is the documented next lever for fouls + made-basket confirmation.

Honest labels: `likely_made_basket` (NOT a confirmed score - no net/height, plausibility-level
ball track), `block_proxy` / `steal_proxy` (proxies), `shot_attempt`, `fast_break`. Hoop zone
from the Day-21 manual court homography -> a DPS court-marking setup dependency. Thresholds
camera-scale-dependent -> RE-TUNE at the DPS mount. **The USER is the perceptual arbiter.**

| rank | interest | type(s) | conf | t (s) | clip |
|------|----------|---------|------|-------|------|
| 1 | 1.15 | block_proxy, likely_made_basket, shot_attempt | 0.6 | 0.0-6.8 | `01_likely_made_basket.mp4` |
| 2 | 1.15 | likely_made_basket, shot_attempt, steal_proxy | 0.6 | 4.4-13.2 | `02_likely_made_basket.mp4` |
| 3 | 0.853 | block_proxy, shot_attempt | 0.48 | 22.6-28.2 | `03_block_proxy.mp4` |
| 4 | 0.7 | steal_proxy | 0.4 | 14.0-20.4 | `04_steal_proxy.mp4` |
| 5 | 0.7 | shot_attempt, steal_proxy | 0.78 | 19.3-28.2 | `05_steal_proxy.mp4` |
