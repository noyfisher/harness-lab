# Measurement protocol v2: SWE-bench-Live, Opus tier (pre-registered)

Status: **FROZEN v2, 2026-09-13**, before the first counted run. Changes after freezing go in
`decisions.md` with a date and reason.

## Why a second study

SWE-bench Verified was retired by OpenAI in February 2026 (flawed tests, contamination;
`docs/background.md`). Phase A's answer on Verified was that a multi-agent harness does not beat
a single agent at either model tier. SWE-bench-Live's frozen `lite` split is built from issues
dated after January 2024 with monthly refresh, so it is contamination-resistant by construction,
and the best published single-agent configurations score far lower on it than on Verified. If a
multi-agent structure can show an effect anywhere, it is on a substrate with headroom. The rig,
guards, statistics, and trace archive carry over unchanged; only the image source and grader
change (`spikes/swe-bench-live/NOTES.md`).

## Claim being measured

Whether the seed multi-agent harness with an Opus 5 Lead and Sonnet 5 specialists (C1o, tag
`harness-c1o`) fixes more SWE-bench-Live lite issues than a plain single agent on Opus 5 (C0o)
with the same rules, budget, wall clock, and container. Opus tier only: those are the two
strongest configurations measured in phase A, and the tier question was already settled there
(C0o vs C1o on Verified: 0 flips, 1 regression, p = 0.28). The claim is about these instances.

## Pinned versions

| component | value |
|---|---|
| dataset | `SWE-bench-Live/SWE-bench-Live`, split `lite` (300, frozen) via Hugging Face `datasets`; `bench/live-instances.json` is host-only |
| images | `starryzhang/sweb.eval.x86_64.<id>` (amd64-only), run with `--platform linux/amd64` under Docker Desktop's emulation (measured 1.9x on CPU work) |
| grader | `microsoft/SWE-bench-Live` main (commit 9a27349) with its `launch` submodule, Python 3.12, isolated venv `spikes/swe-bench-live/.venv`; invoked per run by `bench/live.py`; the driver pre-pulls images because the harness's own registry check has given false negatives |
| agent image | Live base + Node 22.20.0 x64 + Claude Code 2.1.76 (`bench/docker/Dockerfile.live`) |
| model / effort | `claude-opus-5` / `medium` for the top-level session; C1o specialists pinned to `claude-sonnet-5` |
| stats | `bench/stats.py` unchanged; results under `results/live/` |

## Subset

- Candidates: `bench/select_live.py --candidates 60 --seed 20260912` from image-available lite
  instances, stratified by a size bucket derived from the gold patch's changed lines (small <= 15,
  medium 16 to 60, large > 60), at most 6 per repo.
- Gold validation: every candidate's gold patch graded on this machine under emulation; any that
  does not resolve is excluded and listed in `bench/live-gold-results.json`. The spike measured 5
  of 6 resolving; the miss was environment-bound notebook tests.
- Final subset: `bench/select_live.py --n 40 --seed 20260912 --gold-results ...`, 24 train / 16
  held-out stratified by bucket, committed as `bench/live-subset.json`. **N = 40, k = 3.**

## Conditions

| id | config dir | prompt | model |
|---|---|---|---|
| C0o | `bench/c0-config` | `bench/c0-prompt.md` | claude-opus-5 |
| C1o | `harness/` at tag `harness-c1o` | `/swe-fix` | claude-opus-5 Lead, claude-sonnet-5 specialists |

Same rules, done-condition, JSON summary contract, budget, timeout, and image in both.

## Per-run guards

Identical to v1: only `problem_statement` enters the container; git history scrubbed to one
commit; `.claude/` and `.mcp.json` removed; one credential env var; test-patch hunks stripped
and other test edits flagged; never `--bare`. Wall clock **3600 s** (raised from 2400 because emulation slows the agent's own test runs;
the spike's longest run was 842 s). Budget **$4.00** per run. **2 workers**
(Opus runs draw on the scoped weekly cap that the owner's own sessions share). Batches overnight.

## Metrics and inference

As v1: mean pass@1 over k with an instance bootstrap; solid_pass / flaky / solid_fail classes;
paired transition table, flips_up, regressions, Wilcoxon signed-rank and exact sign test. The
one inferential test is the pre-registered paired comparison C0o vs C1o at full k on all 40.
Absolute rates are reported next to the SWE-bench-Live leaderboard's single-agent baselines for
context only; they are not comparable (different scaffolds, budgets, and a 40-instance sample).

## Compute rule

Spike: 4 runs (2 instances x C0o, C1o) on the subscription with `/usage` before and after.
Projected ~240 counted runs. Proceed on the subscription if the projected weekly usage of the
heaviest week stays under 50% of both the weekly cap and the scoped cap; otherwise wait for a
reset or use the $600-capped API key for overflow. Outcome: **subscription; C0o batch before the
2026-09-14T21:00Z reset, C1o batch after it** (weekly cap was at 52% with dev usage included).

## Limitations stated up front

Emulation adds wall time, not correctness risk, but the agent's own test loops run slower, so
the timeout is not comparable with v1. The lite split leans toward repositories that RepoLaunch
could build automatically. Forty instances give a confidence interval about 24 points wide.
Trajectories are archived so a leaderboard submission is possible; none is planned unless the
subset is expanded to the full lite split.

## Spike log

Usage before (2026-09-13T06:37Z): session 1%, weekly_all 52%, weekly_scoped 31%; both weekly
caps reset 2026-09-14T21:00Z. Weekly cap estimate from the two preceding readings: ~$1,100 to
$1,200 list-equivalent per point-hundred (~$10 to $12 per point). Benchmark runs already this
week: C1o and C0o on Verified, ~$254. Decision under the compute rule: spike and the C0o batch
before the reset; the C1o batch after it.

Spike results (2026-09-13, `results/live/spike-runs.jsonl`, not counted): beeware__briefcase-2075
resolved under both conditions; deepset-ai__haystack-8525 unresolved under both (0 of 2 hidden
tests). C0o: $0.87 and $1.00, wall 419 s and 563 s. C1o: $1.25 and $1.94, wall 480 s and 842 s.
Projection: C0o batch ~$115 and ~8 h at 2 workers; C1o batch ~$190 and ~11 h. Spike total $5.06.
Usage after the spike (2026-09-13T07:06Z): session 9% (+8 points for ~$24 list-equivalent
including the orchestration session), weekly_all 54% (+2), weekly_scoped 33% (+2). Consistent
with ~$12 per weekly point; the C0o batch (~$115) is projected to end the week near 64%, leaving
the owner headroom until the reset. The C1o batch is scheduled for 2026-09-14T21:10Z.
