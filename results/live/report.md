# Harness benchmark report

243 runs loaded, 240 counted toward k. Conditions: C0o, C1o.
Bootstrap: 10000 resamples of *instances*, seed 0.

## Per-condition summary

| condition | instances | k (min/max) | pass rate (95% CI) | solid_pass | flaky | solid_fail | resolved runs | cost per solve | mean wall (s) |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| C0o | 40 | 3/3 | 0.492 [0.350, 0.633] | 16 | 7 | 17 | 59 | $1.77 | 853.4 |
| C1o | 40 | 3/3 | 0.508 [0.367, 0.650] | 18 | 6 | 16 | 61 | $4.28 | 1028.0 |

## Paired comparisons

### C0o -> C1o

Instances in both conditions: 40 (0 only in C0o, 0 only in C1o); paired: 40.

- flips_up (solid_fail in C0o -> solid_pass in C1o): **0**
- regressions (solid_pass in C0o -> not solid_pass in C1o): **0**
- discordant majority pairs: 1 (C1o better: 0, C0o better: 1); concordant: 19 pass / 20 fail
- Wilcoxon signed-rank on per-instance pass counts: statistic=7.0, p=0.4142
- sign test on discordant majority pairs: p=1.0000

Transition table (rows = C0o, cols = C1o):

| C0o \ C1o | solid_pass | flaky | solid_fail |
|---|---:|---:|---:|
| solid_pass | 16 | 0 | 0 |
| flaky | 2 | 4 | 1 |
| solid_fail | 0 | 2 | 15 |

## Infrastructure failures (not counted toward k)

| condition | outcome | runs |
|---|---|---:|
| C0o | error | 3 |

