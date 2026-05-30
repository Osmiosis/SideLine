# Event Highlight Candidates - football (SoccerNet proxy for DPS)

**Output #3** (Student Council / school Instagram). HIGH-RECALL candidate set: a
human curates -> picks the keepers, discards false positives. Motion-only (audio is
the documented next lever for fouls + goal-confirmation).

Honest type labels: `likely_goal_candidate` (NOT a goal - no goal-line/net detection;
catches saves/near-misses too), `stoppage_review` (NOT a foul - motion can't judge that),
`tackle_proxy` (noisy), `shot`, `fast_transition`. Thresholds are camera-scale-dependent
-> RE-TUNE at the DPS mount.

**Label-anchored recall:** 5/5 GSR-labeled clip actions fall inside a candidate moment.

| seq | t (s) | type(s) | conf | covers GSR label | clip |
|-----|-------|---------|------|------------------|------|
| SNGS-116 | 4.6-16.6 | stoppage_review, tackle_proxy | 0.6 | YES (Corner) | `00_stoppage_review_5s.mp4` |
| SNGS-116 | 19.7-26.1 | tackle_proxy | 0.4 |  | `01_tackle_proxy_20s.mp4` |
| SNGS-116 | 22.0-28.4 | tackle_proxy | 0.5 |  | `02_tackle_proxy_22s.mp4` |
| SNGS-116 | 24.0-30.0 | tackle_proxy | 0.4 |  | `03_tackle_proxy_24s.mp4` |
| SNGS-117 | 3.2-9.6 | tackle_proxy | 0.4 |  | `00_tackle_proxy_3s.mp4` |
| SNGS-117 | 5.2-12.4 | stoppage_review | 0.36 |  | `01_stoppage_review_5s.mp4` |
| SNGS-117 | 8.4-14.8 | tackle_proxy | 0.5 |  | `02_tackle_proxy_8s.mp4` |
| SNGS-117 | 21.2-30.0 | fast_transition, likely_goal_candidate, shot, stoppage_review, tackle_proxy | 0.98 | YES (Offside) | `03_fast_transition_21s.mp4` |
| SNGS-118 | 0.0-7.4 | tackle_proxy | 0.4 |  | `00_tackle_proxy_0s.mp4` |
| SNGS-118 | 3.4-9.8 | tackle_proxy | 0.5 |  | `01_tackle_proxy_3s.mp4` |
| SNGS-118 | 5.8-12.4 | shot, tackle_proxy | 0.98 |  | `02_shot_6s.mp4` |
| SNGS-118 | 8.6-14.6 | shot, tackle_proxy | 0.89 |  | `03_shot_9s.mp4` |
| SNGS-118 | 9.8-21.8 | likely_goal_candidate, shot, tackle_proxy | 0.64 | YES (Shots off target) | `04_likely_goal_candidate_10s.mp4` |
| SNGS-118 | 15.3-24.7 | stoppage_review | 0.55 | YES (Shots off target) | `05_stoppage_review_15s.mp4` |
| SNGS-118 | 18.7-27.2 | likely_goal_candidate, shot | 0.81 |  | `06_likely_goal_candidate_19s.mp4` |
| SNGS-119 | 0.0-6.7 | likely_goal_candidate, shot | 0.76 | YES (Clearance) | `00_likely_goal_candidate_0s.mp4` |
| SNGS-119 | 0.1-8.6 | likely_goal_candidate, shot | 0.69 | YES (Clearance) | `01_likely_goal_candidate_0s.mp4` |
| SNGS-119 | 3.4-9.8 | tackle_proxy | 0.4 | YES (Clearance) | `02_tackle_proxy_3s.mp4` |
| SNGS-119 | 5.6-14.3 | likely_goal_candidate, shot, tackle_proxy | 0.8 | YES (Clearance) | `03_likely_goal_candidate_6s.mp4` |
| SNGS-119 | 7.2-15.7 | likely_goal_candidate, shot | 0.93 |  | `04_likely_goal_candidate_7s.mp4` |
| SNGS-119 | 10.8-19.7 | stoppage_review, tackle_proxy | 0.55 |  | `05_stoppage_review_11s.mp4` |
| SNGS-119 | 13.5-22.7 | stoppage_review, tackle_proxy | 0.4 |  | `06_stoppage_review_13s.mp4` |
| SNGS-119 | 19.7-28.5 | stoppage_review | 0.53 |  | `07_stoppage_review_20s.mp4` |
| SNGS-119 | 24.0-30.0 | fast_transition, tackle_proxy | 0.74 |  | `08_fast_transition_24s.mp4` |
| SNGS-120 | 0.0-8.3 | likely_goal_candidate, shot, stoppage_review, tackle_proxy | 0.68 |  | `00_likely_goal_candidate_0s.mp4` |
| SNGS-120 | 1.9-9.7 | stoppage_review | 0.43 |  | `01_stoppage_review_2s.mp4` |
| SNGS-120 | 6.4-14.5 | fast_transition, shot | 0.98 |  | `02_fast_transition_6s.mp4` |
| SNGS-120 | 10.3-18.5 | fast_transition, stoppage_review, tackle_proxy | 0.84 |  | `03_fast_transition_10s.mp4` |
| SNGS-120 | 13.5-21.4 | tackle_proxy | 0.5 |  | `04_tackle_proxy_13s.mp4` |
| SNGS-120 | 20.0-26.4 | tackle_proxy | 0.6 | YES (Foul) | `05_tackle_proxy_20s.mp4` |
| SNGS-120 | 25.1-30.0 | stoppage_review | 0.33 |  | `06_stoppage_review_25s.mp4` |
