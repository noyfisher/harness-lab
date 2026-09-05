# Harness benchmark report

505 runs loaded, 495 counted toward k. Conditions: C0, C1, cand-053964c, cand-1c1a458, cand-4c62dca, cand-5777b17, cand-6e9817c, cand-b64eadc, cand-c57396f, cand-f852723.
Bootstrap: 10000 resamples of *instances*, seed 0.

## Per-condition summary

| condition | instances | k (min/max) | pass rate (95% CI) | solid_pass | flaky | solid_fail | resolved runs | cost per solve | mean wall (s) |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| C0 | 40 | 3/3 | 0.783 [0.658, 0.900] | 30 | 3 | 7 | 94 | $1.00 | 211.7 |
| C1 | 40 | 3/3 | 0.750 [0.625, 0.875] | 28 | 3 | 9 | 90 | $1.73 | 367.0 |
| cand-053964c | 24 | 1/1 | 0.750 [0.583, 0.917] | 18 | 0 | 6 | 18 | $1.68 | 394.0 |
| cand-1c1a458 | 24 | 1/1 | 0.708 [0.500, 0.875] | 17 | 0 | 7 | 17 | $1.95 | 416.3 |
| cand-4c62dca | 18 | 1/1 | 0.833 [0.667, 1.000] | 15 | 0 | 3 | 15 | $1.52 | 425.8 |
| cand-5777b17 | 40 | 3/3 | 0.767 [0.642, 0.883] | 29 | 3 | 8 | 92 | $2.23 | 531.8 |
| cand-6e9817c | 24 | 1/1 | 0.708 [0.500, 0.875] | 17 | 0 | 7 | 17 | $1.87 | 426.6 |
| cand-b64eadc | 21 | 1/1 | 0.714 [0.524, 0.905] | 15 | 0 | 6 | 15 | $1.85 | 662.5 |
| cand-c57396f | 24 | 1/1 | 0.750 [0.583, 0.917] | 18 | 0 | 6 | 18 | $1.48 | 379.4 |
| cand-f852723 | 0 | n/a | n/a [n/a, n/a] | 0 | 0 | 0 | 0 | n/a | n/a |

## Paired comparisons

### C0 -> C1

Instances in both conditions: 40 (0 only in C0, 0 only in C1); paired: 40.

- flips_up (solid_fail in C0 -> solid_pass in C1): **0**
- regressions (solid_pass in C0 -> not solid_pass in C1): **2**
- discordant majority pairs: 2 (C1 better: 1, C0 better: 1); concordant: 30 pass / 8 fail
- Wilcoxon signed-rank on per-instance pass counts: statistic=2.0, p=0.2568
- sign test on discordant majority pairs: p=1.0000

Transition table (rows = C0, cols = C1):

| C0 \ C1 | solid_pass | flaky | solid_fail |
|---|---:|---:|---:|
| solid_pass | 28 | 1 | 1 |
| flaky | 0 | 2 | 1 |
| solid_fail | 0 | 0 | 7 |

### C1 -> cand-053964c

Instances in both conditions: 24 (16 only in C1, 0 only in cand-053964c); paired: 0 (24 excluded for k mismatch).

- flips_up (solid_fail in C1 -> solid_pass in cand-053964c): **0**
- regressions (solid_pass in C1 -> not solid_pass in cand-053964c): **0**
- discordant majority pairs: 0 (cand-053964c better: 0, C1 better: 0); concordant: 0 pass / 0 fail
- Wilcoxon signed-rank on per-instance pass counts: statistic=n/a, p=n/a (all shared instances excluded for k mismatch)
- sign test on discordant majority pairs: p=1.0000 (no discordant majority pairs)
- warning: k differs between conditions for 24 instance(s), excluded from the transition table and both paired tests (protocol caveat 4): astropy__astropy-14309, astropy__astropy-14995, django__django-15128, django__django-15732, django__django-16667 and more

Transition table (rows = C1, cols = cand-053964c):

| C1 \ cand-053964c | solid_pass | flaky | solid_fail |
|---|---:|---:|---:|
| solid_pass | 0 | 0 | 0 |
| flaky | 0 | 0 | 0 |
| solid_fail | 0 | 0 | 0 |

### cand-053964c -> cand-1c1a458

Instances in both conditions: 24 (0 only in cand-053964c, 0 only in cand-1c1a458); paired: 24.

- flips_up (solid_fail in cand-053964c -> solid_pass in cand-1c1a458): **0**
- regressions (solid_pass in cand-053964c -> not solid_pass in cand-1c1a458): **1**
- discordant majority pairs: 1 (cand-1c1a458 better: 0, cand-053964c better: 1); concordant: 17 pass / 6 fail
- Wilcoxon signed-rank on per-instance pass counts: statistic=0.0, p=0.3173
- sign test on discordant majority pairs: p=1.0000

Transition table (rows = cand-053964c, cols = cand-1c1a458):

| cand-053964c \ cand-1c1a458 | solid_pass | flaky | solid_fail |
|---|---:|---:|---:|
| solid_pass | 17 | 0 | 1 |
| flaky | 0 | 0 | 0 |
| solid_fail | 0 | 0 | 6 |

### cand-1c1a458 -> cand-4c62dca

Instances in both conditions: 18 (6 only in cand-1c1a458, 0 only in cand-4c62dca); paired: 18.

- flips_up (solid_fail in cand-1c1a458 -> solid_pass in cand-4c62dca): **1**
- regressions (solid_pass in cand-1c1a458 -> not solid_pass in cand-4c62dca): **0**
- discordant majority pairs: 1 (cand-4c62dca better: 1, cand-1c1a458 better: 0); concordant: 14 pass / 3 fail
- Wilcoxon signed-rank on per-instance pass counts: statistic=0.0, p=0.3173
- sign test on discordant majority pairs: p=1.0000

Transition table (rows = cand-1c1a458, cols = cand-4c62dca):

| cand-1c1a458 \ cand-4c62dca | solid_pass | flaky | solid_fail |
|---|---:|---:|---:|
| solid_pass | 14 | 0 | 0 |
| flaky | 0 | 0 | 0 |
| solid_fail | 1 | 0 | 3 |

### cand-4c62dca -> cand-5777b17

Instances in both conditions: 18 (0 only in cand-4c62dca, 22 only in cand-5777b17); paired: 0 (18 excluded for k mismatch).

- flips_up (solid_fail in cand-4c62dca -> solid_pass in cand-5777b17): **0**
- regressions (solid_pass in cand-4c62dca -> not solid_pass in cand-5777b17): **0**
- discordant majority pairs: 0 (cand-5777b17 better: 0, cand-4c62dca better: 0); concordant: 0 pass / 0 fail
- Wilcoxon signed-rank on per-instance pass counts: statistic=n/a, p=n/a (all shared instances excluded for k mismatch)
- sign test on discordant majority pairs: p=1.0000 (no discordant majority pairs)
- warning: k differs between conditions for 18 instance(s), excluded from the transition table and both paired tests (protocol caveat 4): astropy__astropy-14309, astropy__astropy-14995, django__django-15128, django__django-15732, django__django-16667 and more

Transition table (rows = cand-4c62dca, cols = cand-5777b17):

| cand-4c62dca \ cand-5777b17 | solid_pass | flaky | solid_fail |
|---|---:|---:|---:|
| solid_pass | 0 | 0 | 0 |
| flaky | 0 | 0 | 0 |
| solid_fail | 0 | 0 | 0 |

### cand-5777b17 -> cand-6e9817c

Instances in both conditions: 24 (16 only in cand-5777b17, 0 only in cand-6e9817c); paired: 0 (24 excluded for k mismatch).

- flips_up (solid_fail in cand-5777b17 -> solid_pass in cand-6e9817c): **0**
- regressions (solid_pass in cand-5777b17 -> not solid_pass in cand-6e9817c): **0**
- discordant majority pairs: 0 (cand-6e9817c better: 0, cand-5777b17 better: 0); concordant: 0 pass / 0 fail
- Wilcoxon signed-rank on per-instance pass counts: statistic=n/a, p=n/a (all shared instances excluded for k mismatch)
- sign test on discordant majority pairs: p=1.0000 (no discordant majority pairs)
- warning: k differs between conditions for 24 instance(s), excluded from the transition table and both paired tests (protocol caveat 4): astropy__astropy-14309, astropy__astropy-14995, django__django-15128, django__django-15732, django__django-16667 and more

Transition table (rows = cand-5777b17, cols = cand-6e9817c):

| cand-5777b17 \ cand-6e9817c | solid_pass | flaky | solid_fail |
|---|---:|---:|---:|
| solid_pass | 0 | 0 | 0 |
| flaky | 0 | 0 | 0 |
| solid_fail | 0 | 0 | 0 |

### cand-6e9817c -> cand-b64eadc

Instances in both conditions: 21 (3 only in cand-6e9817c, 0 only in cand-b64eadc); paired: 21.

- flips_up (solid_fail in cand-6e9817c -> solid_pass in cand-b64eadc): **1**
- regressions (solid_pass in cand-6e9817c -> not solid_pass in cand-b64eadc): **1**
- discordant majority pairs: 2 (cand-b64eadc better: 1, cand-6e9817c better: 1); concordant: 14 pass / 5 fail
- Wilcoxon signed-rank on per-instance pass counts: statistic=1.5, p=1.0000
- sign test on discordant majority pairs: p=1.0000

Transition table (rows = cand-6e9817c, cols = cand-b64eadc):

| cand-6e9817c \ cand-b64eadc | solid_pass | flaky | solid_fail |
|---|---:|---:|---:|
| solid_pass | 14 | 0 | 1 |
| flaky | 0 | 0 | 0 |
| solid_fail | 1 | 0 | 5 |

### cand-b64eadc -> cand-c57396f

Instances in both conditions: 21 (0 only in cand-b64eadc, 3 only in cand-c57396f); paired: 21.

- flips_up (solid_fail in cand-b64eadc -> solid_pass in cand-c57396f): **1**
- regressions (solid_pass in cand-b64eadc -> not solid_pass in cand-c57396f): **1**
- discordant majority pairs: 2 (cand-c57396f better: 1, cand-b64eadc better: 1); concordant: 14 pass / 5 fail
- Wilcoxon signed-rank on per-instance pass counts: statistic=1.5, p=1.0000
- sign test on discordant majority pairs: p=1.0000

Transition table (rows = cand-b64eadc, cols = cand-c57396f):

| cand-b64eadc \ cand-c57396f | solid_pass | flaky | solid_fail |
|---|---:|---:|---:|
| solid_pass | 14 | 0 | 1 |
| flaky | 0 | 0 | 0 |
| solid_fail | 1 | 0 | 5 |

### cand-c57396f -> cand-f852723

Instances in both conditions: 0 (24 only in cand-c57396f, 0 only in cand-f852723); paired: 0.

- flips_up (solid_fail in cand-c57396f -> solid_pass in cand-f852723): **0**
- regressions (solid_pass in cand-c57396f -> not solid_pass in cand-f852723): **0**
- discordant majority pairs: 0 (cand-f852723 better: 0, cand-c57396f better: 0); concordant: 0 pass / 0 fail
- Wilcoxon signed-rank on per-instance pass counts: statistic=n/a, p=n/a (no instances present in both conditions)
- sign test on discordant majority pairs: p=1.0000 (no discordant majority pairs)

Transition table (rows = cand-c57396f, cols = cand-f852723):

| cand-c57396f \ cand-f852723 | solid_pass | flaky | solid_fail |
|---|---:|---:|---:|
| solid_pass | 0 | 0 | 0 |
| flaky | 0 | 0 | 0 |
| solid_fail | 0 | 0 | 0 |

## Infrastructure failures (not counted toward k)

| condition | outcome | runs |
|---|---|---:|
| cand-4c62dca | paused | 6 |
| cand-b64eadc | paused | 3 |
| cand-f852723 | error | 1 |

