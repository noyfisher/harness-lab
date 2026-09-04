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

## Usage after

(TBD)

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
