# Does a multi-agent Claude Code harness beat a single agent? A measured answer.

## 1. The question, and the answer

On a fixed, stratified 40-instance subset of SWE-bench Verified, running Claude Sonnet 5 at
medium effort in identical containers, does a six-agent Claude Code harness fix more issues than
a single `claude -p` invocation with the same rules, model, budget, and environment? And can an
automated improver, reading only train-split failures, produce a variant that does?

No, on both counts. The single agent (C0) resolved 0.783 of instances (95% CI 0.658 to 0.900);
the seeded multi-agent harness (C1) resolved 0.750 (95% CI 0.625 to 0.875). The gap runs the
wrong way and sits inside noise: zero instances moved from always-fail to always-pass, two
always-pass instances stopped being always-pass, Wilcoxon p = 0.2568, sign test p = 1.0. Cost per
solved instance was $1.00 for C0 and $1.73 for C1: the structure cost about 1.7x per solve and
bought nothing. The improver proposed six real hypotheses; zero were accepted. One reached the
k=3 confirmation and was rejected there, having solved the same tasks as the seed at 1.3x the
cost while regressing a held-out instance.

I am Noy Fisher; I designed and ran this study, using Claude Code as the tool to build the
driver, the stats module, and the improver loop. The point of the repository is that the answer
is checkable: every number below comes from a committed file, cited next to its table.

## 2. What was built

**Per-run driver** (`bench/run.py`). One run is one (condition, instance, repeat). It exports
`harness/` at a pinned sha, starts an Epoch arm64 SWE-bench image, and enforces leakage guards
before the agent starts: only `problem_statement` enters the container, git history is scrubbed
to one commit, and `.claude/` and `.mcp.json` are removed, all asserted. One credential env var
enters, and the manifest records only its type. Diff hunks touching test-patch files are
stripped; any other test-path edit is flagged. Every run has a dollar budget and a wall-clock
alarm, and a killed run produces a manifest rather than a gap. `--bare` is never used: it
silently skips custom agents and subscription auth.

**Grading** (`bench/grade.py`). `swebench` 5.0.2 builds the official `TestSpec`, the image
reference is swapped for Epoch's arm64 image, and the runner's steps are replayed with the docker
CLI and scored by `get_eval_report`. Every candidate's gold patch was graded here first: 60 of 60
resolved (`bench/gold-results.json`).

**Batch runner** (`bench/batch.py`). Repeat-major order, so an interruption never leaves a
half-complete comparison; resume by counted run, so re-invoking a batch never burns usage twice;
one sha per batch; image preflight; rate-limit pauses that back off and re-queue.

**Stats** (`bench/stats.py`). The bootstrap resamples *instances*, not runs, because k repeats of
one instance are not k independent observations. Each instance gets a class per condition:
`solid_pass` (k/k), `flaky`, `solid_fail` (0/k). Comparisons are paired on shared instances:
transition table, `flips_up`, `regressions`, Wilcoxon signed-rank on pass-count differences, an
exact sign test on discordant majority pairs.

**Dossiers** (`bench/dossier.py`). One file per failing train instance: the problem statement,
the agent's JSON summary, what it actually ran, the patch, and which hidden tests still fail.
They are the improver's only input and never enter a run container.

**Improver loop** (`improver/loop.py`). The loop owns git and every decision; the agent only
edits files under `harness/`. Each iteration: propose on a fresh branch, mechanically validate
(only `harness/` touched, valid `HYPOTHESIS.json`, a real file changed, no hidden test name or
instance id leaked into container-bound files, `claude agents` still loads the harness), k=1
train screen, k=1 held-out screen, k=3 confirmation, archive.

Pre-registered before any baseline run (`docs/protocol.md`, frozen v1, 2026-09-04): N = 40 split
24 train / 16 held-out, k = 3, `claude-sonnet-5` at medium effort, $4.00 budget and 2400 s wall
per run, 3 workers, 10,000 bootstrap resamples at seed 0. Accept rule: reject at the train
screen unless there is a `flips_up` and no regression; reject on any held-out regression; accept
at k=3 only if held-out `regressions == 0` and train `flips_up >= 2`. The k=1 screens are
filters, not tests; only the confirmation applies the rule, and the one inferential test is the
final C0 versus C1 comparison.

## 3. Results

Per condition, k = 3 on all 40 instances (source: `results/report.md`, generated from
`results/runs.jsonl`):

| condition | pass rate (95% CI) | solid_pass / flaky / solid_fail | cost per solve | mean cost per run | mean wall (s) | mean turns |
|---|---|---|---:|---:|---:|---:|
| C0 single agent | 0.783 [0.658, 0.900] | 30 / 3 / 7 | $1.00 | $0.79 | 211.7 | 35.3 |
| C1 seeded harness | 0.750 [0.625, 0.875] | 28 / 3 / 9 | $1.73 | $1.30 | 367.0 | 34.1 |

Neither baseline had any infrastructure failure (`results/all-stats.json`).

C0 to C1, 40 paired instances (source: `results/report.md`, `results/all-stats.json`):

| C0 \ C1 | solid_pass | flaky | solid_fail |
|---|---:|---:|---:|
| solid_pass | 28 | 1 | 1 |
| flaky | 0 | 2 | 1 |
| solid_fail | 0 | 0 | 7 |

`flips_up` = 0, `regressions` = 2, discordant majority pairs = 2 (one each way), Wilcoxon
statistic 2.0, p = 0.2568 with `n_nonzero` = 4, sign test p = 1.0. The overlapping CIs are not
the evidence; the paired result is, and it is null.

Improver candidates, one row per hypothesis (sources: `improver/state/archive.json`,
`results/all-stats.json`; spend excludes the proposal session):

| # | condition | change | category | screen result | spend | verdict |
|---|---|---|---|---|---:|---|
| 1 | cand-1c1a458 | backend-dev greps the whole test tree for callers of the changed function and runs up to 3 more test files | prompt_rule | train k=1: 0 flips, 1 reg | $33.15 | rejected, train screen |
| 2 | cand-6e9817c | backend-dev "traces one level deeper" (base class, input provider, domain definition) before choosing a fix site | prompt_rule | train k=1: 0 flips, 1 reg | $31.79 | rejected, train screen |
| 3 | cand-5777b17 | lead: XS tier removed from the router, specialist workflow never skipped, planner always spawned | workflow | k=1 train 1 flip / 0 reg; k=1 held-out 1 flip / 0 reg; k=3 train 0 flips / 1 reg; k=3 held-out 1 flip / 1 reg | $205.42 | rejected, k=3 confirmation |
| 4 | cand-b64eadc | lead + planner: XS tier kept, planner added to its routing, hierarchy-tracing rule | workflow | train k=1 as recorded 1 flip / 2 reg; after a usage-wall timeout was superseded, 1 flip / 1 real reg | $27.79 | rejected, train screen |
| 5 | cand-4c62dca, re-screened as cand-c57396f | lead: six agents collapsed to three (Lead, backend-dev, code-reviewer), router and planner/tester/critic removed | workflow | first screen invalid (6 of 24 runs were usage-wall timeouts); re-screen 0 flips, 0 reg, mean $1.11 per run | $22.86 + $26.67 | rejected, train screen |
| 6 | cand-053964c | lead + swe-fix: router removed, Lead owns localization and reproduction, fix and QA always delegated | workflow | train k=1: 0 flips, 0 reg, mean $1.26 per run | $30.23 | rejected, train screen |

Candidate 3 is the only one measured at full k=3 on all 40 instances: 0.767 [0.642, 0.883], cost
per solve $2.23, mean wall 531.8 s (`results/report.md`).

Spend accounting (sources: `results/runs.jsonl`, `results/all-stats.json`,
`improver/state/archive.json`):

| item | value |
|---|---:|
| manifest lines / superseded at $0 / loaded / counted toward k | 515 / 10 / 505 / 495 |
| total run cost at API list price | $628.24 |
| C0 / C1 / candidates | $94.24 / $156.08 / $377.91 |
| improver proposals (6 successful, 2 aborted at $0) | $13.91 |
| pre-protocol spike (`results/spike-runs.jsonl`) | $5.10, 7 runs |

Every counted run ran on a Max 20x subscription; no API key was ever created
(`docs/decisions.md`). Per-run cost figures are the CLI's client-side `total_cost_usd` estimate
at API list price: not what the study actually cost, and useful only as a relative measure
between conditions.

## 4. What the improver found

Four of the six hypotheses added process: broader tests, root-layer localization, forced
delegation, and the last two combined. All four were rejected. The one that reached confirmation
(candidate 3, forced delegation) looked promising at k=1, with one train flip, one held-out flip,
and no regressions in either screen. At k=3 it solved the same instances as the seed, regressed
`scikit-learn__scikit-learn-26194` on train and `matplotlib__matplotlib-20859` on held-out, and
cost $2.23 per solve against the seed's $1.73, about 1.3x. The k=1 screens did what the protocol
says they do, filter; only the confirmation could decide.

After four consecutive rejections the loop wedged itself and wrote an item to
`improver/state/owner-decisions.md`. I revised `.claude/commands/improve.md` to forbid another
additive rule and steer toward subtraction, budget reallocation, or handoff quality, then ran two
more iterations and wrote up regardless. Both subtractive variants (candidates 5 and 6) matched
the seed's train classes at a lower mean cost per run, $1.11 and $1.26 against C1's $1.30, and
flipped nothing. Zero flips is a rejection under the pre-registered rule, and the loop closed.

Five train instances were never resolved by any run of any condition: `django__django-15732`,
`django__django-16667`, `sphinx-doc__sphinx-7985`, `sympy__sympy-20428`, `sympy__sympy-22080`.
A sixth, `pylint-dev__pylint-8898`, is `solid_fail` under C1 but was solved once by C0 and once
each in two candidate screens. `docs/taxonomy.md` reads the train dossiers for why. The recurring
modes: example-locked reproduction, where the repro transcribes the issue's snippet and covers
only the literal case; wrong-layer fixes, where the patch lands where the traceback surfaces
rather than where the broken invariant lives; confidence miscalibration, 0.90 to 0.95 reported on
patches whose hidden tests all fail; and router collapse, where the Lead classifies nearly
everything XS and does the work itself, so 10 of the 19 failing C1 train runs spawned no
specialist. On the six instances failing under both conditions, C1 ran roughly twice the shell
commands and 1.8x the reads of C0, and bought zero flips (`docs/taxonomy.md`, section 4).

## 5. What went wrong, and what it cost

**Docker VM freeze.** The first candidate screen produced sessions ending at turn 1 with
"Unknown skill: swe-fix" and zero cost. Detected by re-testing the same export in a healthy
container: the Docker Desktop VM had logged nothing for an hour and was returning API 500s. Fix
in code: `run.py` classifies any one-turn zero-cost session as `error`, which is infrastructure
and can never count as an agent failure. The manifest was superseded and the candidate
re-screened.

**Usage wall.** Iteration 5's train screen contained six zero-cost, zero-turn timeouts: the CLI
sat waiting on an exhausted 5-hour window until the wall clock fired. They were first counted as
failures, one of them as a regression against candidate 4. Fix in code: `run.py` classifies a
timeout with no result event and no spend as `paused`, which the batch re-queues and the stats
module excludes from k. The nine affected runs were superseded as `paused`, candidate 4's record
was annotated (one flip and one real regression, so its rejection stands), and candidate 5's
screen was declared invalid and re-run. The improver session hit the same wall on iteration 6;
`loop.py` now pauses 30 minutes and retries on rate-limit text.

**Expired host login.** The first real improver iteration failed at turn 1 with a 401: the host
CLI's OAuth access token had expired, and a plain `claude -p` then hung on re-auth. Fix in code:
`loop.py` injects the credentials-file token into the improver session, the same credential the
containers use. The aborted iteration cost $0 and counted nothing.

**Leak-check false positive.** The first proposal was rejected at validation because its
`HYPOTHESIS.json` rationale quoted a hidden test name. That file never enters a container:
`run.py` strips it from the export. Fix in code: the leak check is scoped to container-bound
files, with `HYPOTHESIS.json` exempt from the instance-id check (`expected_flips` must name train
ids); every other harness file is still checked. `--reuse-candidate` re-screens an existing
candidate after an infra stop without paying for a new proposal.

No invalid run remained counted. The audit trail is the `supersedes` field in
`results/runs.jsonl` (10 lines, zero cost) and the dated entries in `docs/decisions.md`.

A fifth incident, a credential printed into a local log, is **not recorded anywhere in this
repository**, so I will not assert it. What the repo does show is the handling: one credential
env var per run, manifests storing only the type (`subscription` or `api_key`) and never the
value, `bench/smoke_auth.py` replacing the value with `<redacted>` in both captured streams, and
`.gitignore` excluding `*.log` and Claude Code's config-dir state. A scan of the tracked tree for
credential-shaped strings returns nothing.

## 6. Limitations

N = 40 gives a 95% CI roughly 24 points wide, so this study detects only large effects. The
protocol's stats review notes that the instance bootstrap absorbs between-instance spread, making
measured coverage 97 to 99% and the interval conservative for a fixed-instance claim.

One model, one effort level. Everything ran on `claude-sonnet-5` at medium effort with all six
agents on `model: inherit`, which isolates structure from model tier but says nothing about an
Opus orchestrator. The protocol defines a C1o sensitivity variant; it was **not measured**.

Environment tilt. Epoch publishes arm64 images for 420 of 500 Verified instances, unevenly:
xarray 0 of 22, matplotlib 7 of 34, scikit-learn 7 of 32. The subset leans pure-Python, and the
`>4 hours` stratum, 3 instances dataset-wide, gets zero seats.

Screening statistics are not evidence. The k=1 screens compare one candidate run against the
base condition's k=3 classes and can only reject. Per-iteration p-values are uncorrected for
multiple looks.

The improver reads only the train split, and `docs/taxonomy.md` reads only train dossiers, so
every claim about the harness's failure profile rests on six instances and nineteen runs, with
mode assignments made by one reader rather than a coded rubric with a second annotator.

Finally, the protocol frames the claim as being about *these* 40 instances, not SWE-bench
Verified or SWE-bench-like tasks in general. Benchmark saturation and training-data contamination
are not addressed in the protocol and were **not measured** here.

## 7. What I would do next

Phase B, opening pull requests against real repositories, would use the single-agent
configuration, the measured better and cheaper of the two. It cannot start until egress is
restricted in the run container: v1 left egress open because the SWE-bench repos are pinned
commits of well-known projects, and `docs/decisions.md` tracks that as an open item for arbitrary
repositories.

Three measurements would sharpen the answer: a linux/amd64 sensitivity run, since x86_64 images
exist for all 500 instances and would remove the coverage tilt; the C1o variant with an Opus lead
and Sonnet specialists, to separate "multi-agent does not help" from "multi-agent does not help
when the orchestrator is the same tier as the workers"; and a larger N, since 40 instances leave
an interval wide enough to hide any effect smaller than the one this study can find.
