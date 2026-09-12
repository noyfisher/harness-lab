# C1o sensitivity run log

Variant: tag `harness-c1o` (d7bc81f), Lead on `claude-opus-5`, specialists on `claude-sonnet-5`.
Question: does the multi-agent structure fail because the orchestrator is the same tier as the
workers? Same subset, k=3, $4.00 budget, 2400 s wall, 2 workers.

## Usage before (Noy's `/usage`, 2026-09-11T18:52:52Z)

| window | used | resets |
|---|---|---|
| session (5-hour) | 8% | 2026-09-11T23:00:00Z |
| weekly_all | 21% | 2026-09-14T21:00:00Z |
| weekly_scoped (Opus/Fable) | 18% | 2026-09-14T20:59:59Z |

## Usage after C1o (Noy's `/usage`, 2026-09-12T09:40:21Z)

| window | before | after | delta |
|---|---|---|---|
| session (5-hour) | 8% | 0% | reset in between |
| weekly_all | 21% | 40% | +19 points (C1o $188.59 + orchestration sessions ~$20 + owner's own use) |
| weekly_scoped (Opus/Fable) | 18% | 20% | +2 points for ~$83 of Opus-5 run cost inside C1o |

Implication: the scoped cap is far less sensitive to Opus-5 run spend than feared; the weekly_all
cap is the binding one, at roughly $11 per point this week.

## C0o: single agent on claude-opus-5 (post-hoc extension, started 2026-09-12)

Same `bench/c0-config`, same prompt, same $4.00 budget, 2400 s wall, k=3 on all 40, 2 workers,
`--model claude-opus-5`. Purpose: separate "Opus 5 is the better model" from "an Opus orchestrator
makes the team work". Decision rule for the writeup: if C0o's paired comparison with C1o shows no
advantage for C1o, the C1o gain is model tier; if C1o beats C0o with flips and no regressions, the
structure earns its cost only when the orchestrator outranks the workers.

## Results (2026-09-12, batch `C1o-sensitivity`, 120 runs, 0 infra failures, $188.59 list)

| condition | pass rate (95% CI) | solid_pass / flaky / solid_fail | cost per solve | mean cost per run | mean wall |
|---|---|---|---:|---:|---:|
| C0 single agent, Sonnet 5 | 0.783 [0.658, 0.900] | 30 / 3 / 7 | $1.00 | $0.79 | 212 s |
| C1 seed harness, all Sonnet 5 | 0.750 [0.625, 0.875] | 28 / 3 / 9 | $1.73 | $1.30 | 367 s |
| C1o seed harness, Lead on Opus 5 | 0.900 [0.808, 0.975] | 34 / 3 / 3 | $1.75 | $1.57 | 532 s |

Paired C1 -> C1o: flips_up 5, regressions 0, Wilcoxon p = 0.018, sign test p = 0.070.
Paired C0 -> C1o: flips_up 3, regressions 0, Wilcoxon p = 0.03881295437592857.
Cost split inside C1o (from trace result events): mean $1.57 per run = $0.69 Opus (the Lead) + $0.89 Sonnet (specialists); the Lead is 44% of spend. No budget hits (max $3.97), no timeouts.
C1o's remaining solid_fail: sympy__sympy-19783, sympy__sympy-20428, sympy__sympy-22080. It solved four of the five instances no earlier condition ever solved.

**Confound to resolve before any claim:** C1o mixes a stronger model into the harness, so the effect could be "Opus is better" rather than "an Opus orchestrator helps". The de-confounding run is C0o: the plain single agent on claude-opus-5 with the same rules, budget, and environment. Not pre-registered; added post hoc and labeled as such.
