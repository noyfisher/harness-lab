# Week 1 spike log

## Usage before (Noy's `/usage`, 2026-09-04T05:39:33Z)

| window | used | resets |
|---|---|---|
| session (5-hour) | 14% | 2026-09-04T09:09:59Z |
| weekly_all | 30% | 2026-09-07T20:59:59Z |
| weekly_scoped | 40% | 2026-09-07T20:59:59Z |

Note: the planning and build session that produced this repo consumed roughly $44.58 at
list-price equivalent on Fable before the spike; that is development usage, not counted runs.

## Spike batches

- `spike-C0`: C0 on django__django-11099, pytest-dev__pytest-5262, sympy__sympy-13031, k=1
- `spike-C1`: C1 (harness-seed = 9ec1540) on the same three, k=1
- model claude-sonnet-5, effort medium, budget $3.00/run, wall 2400 s, workers 3

## Usage after (Noy's `/usage`, 2026-09-04T05:56:40Z)

| window | before | after | delta |
|---|---|---|---|
| session (5-hour) | 14% | 17% | +3 points |
| weekly_all | 30% | 30% | < 0.5 points (integer resolution) |
| weekly_scoped | 40% | 40% | 0 (Sonnet runs do not touch the scoped cap) |

Between readings: spike $5.10 (Sonnet 5, counted runs) + orchestration session $2.82 (Fable,
dev usage) = ~$7.9 list-equivalent.

## Arithmetic

- 5-hour window: ~$7.9 per 3 points => ~$2.6 per point => one window ~= $260 list-equivalent
  (readings are integer-rounded; plausible range $225-$315).
- Weekly cap: < 0.5 points for ~$7.9 => one point >= ~$16 => full cap >= ~$1,600 list-equivalent.
  This is a lower bound only; the weekly reading did not move.
- Study projection (N=40, k=3): C0 120 runs x ~$0.8 = ~$96; C1 120 x ~$1.8 = ~$216;
  4 candidate screens on train (96 runs) ~$173; 2 held-out screens (32 runs) ~$58;
  final confirmation 120 runs ~$216. Total ~490 runs, ~$760 list-equivalent over ~4 weeks.
- Heaviest week (both baselines, ~$312) vs weekly cap >= $1,600 => <= 20% of weekly capacity,
  under the 50% rule with margin even if the estimate is off by 2x.
- A 5-hour window (~$260) is exhausted by ~140 baseline-C1 runs' worth of usage; a 120-run C1
  batch at 3 workers (~$80/hour) hits the wall after ~3 hours and resumes after the reset.
  Batches run overnight; the batch runner's pause/resume handles the wall.

## Decision

**Subscription only. No API key is created.** Re-check after the C0 baseline batch: if that
batch (~$96) moves the weekly reading by more than 6 points, the weekly-cap estimate is wrong
and the rule is re-evaluated before C1.

## Results (all runs resolved; model ids = claude-sonnet-5 only)

| cond | instance | turns | cost (list) | agent s | wall s |
|---|---|---:|---:|---:|---:|
| C0 | django__django-11099 | 19 | $0.30 | 55 | 66.9 |
| C0 | pytest-dev__pytest-5262 | 20 | $0.31 | 66 | 107.5 |
| C0 | sympy__sympy-13031 | 37 | $0.75 | 236 | 240.6 |
| C0 | sympy__sympy-13031 | 37 | $0.72 | 193 | 195.8 |
| C1 | django__django-11099 | 19 | $0.64 | 147 | 157.9 |
| C1 | pytest-dev__pytest-5262 | 19 | $0.73 | 173 | 186.6 |
| C1 | sympy__sympy-13031 | 45 | $1.66 | 397 | 404.6 |

- C0: 4 runs, mean cost $0.52, mean wall 153 s, total $2.07
- C1: 3 runs, mean cost $1.01, mean wall 250 s, total $3.03
- spike total at list price: $5.10 across 7 runs (one C0 sympy duplicate from an infra retry)
- grading infra failures on sympy were caused by the gold job not having pulled that image yet; fixed (grade pulls) and regraded without re-running the agent
