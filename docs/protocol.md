# Measurement protocol (pre-registered)

Status: DRAFT, Week 1. Fields marked TBD are filled from spike measurements before any
baseline run and then frozen. Changes after freezing go in `decisions.md` with a date and reason.

## Claim being measured

Whether a multi-agent Claude Code harness (`harness/`) fixes more SWE-bench Verified issues
than a single-agent `claude -p` invocation with the same model, effort, budget, prompt rules,
and environment, and whether an improver loop that edits the harness produces gains that hold
on instances it never saw. The claim is about **these instances** (a fixed, stratified subset),
not about SWE-bench-like tasks in general; the bootstrap interval is conservative for that
reading (see Caveats).

## Pinned versions

| component | value |
|---|---|
| Claude Code CLI | 2.1.76, `DISABLE_AUTOUPDATER=1`, installed in the agent image via npm |
| swebench | 5.0.2 (import check: `swebench.harness.utils.make_test_spec`, `swebench.types.TestSpec`, `swebench.harness.grading.get_logs_eval/get_eval_report` all resolve) |
| task definitions | `SWE-bench/swe-bench-tasks` shallow clone (task dirs carry eval.sh, test.patch, gold.patch) |
| images | `ghcr.io/epoch-research/swe-bench.eval.arm64.<instance_id>:latest` (only tag published; digest recorded per run) |
| agent image | Epoch base + Node 22.20.0 + pinned CLI (`bench/docker/Dockerfile`) |
| model / effort | `sonnet` / `medium` for every agent under test in every condition |
| improver model | Opus or Fable, high effort; never used inside a counted run |

## Environment limitation (stated, not hidden)

Epoch publishes arm64 images for 420 of 500 Verified instances. Coverage is not uniform:
xarray has 0 of 22, matplotlib 7 of 34, scikit-learn 7 of 32; django, sympy, sphinx, pytest,
pylint, requests are essentially complete. The subset is therefore tilted toward pure-Python
repositories. The `>4 hours` difficulty stratum has only 3 instances in the dataset and
receives 0 seats at any subset size we can afford. Both are limitations of this study, not of
the harness. A linux/amd64 sensitivity run is possible later (all 500 x86_64 images exist).

## Subset

- Candidates: `bench/select.py --candidates 60 --seed 20260903` (arm64-available, stratified
  by `difficulty`, at most 8 per repo).
- Gold validation: every candidate's gold patch is graded on this machine; any that does not
  resolve is excluded and listed in `bench/gold-results.json`.
- Final subset: `bench/select.py --n N --seed 20260903 --gold-results bench/gold-results.json`,
  split 60/40 train/held-out, stratified by difficulty. Committed as `bench/subset.json`.
- **N = TBD** (working assumption 30-40), **k = TBD** (working assumption 3), set from the
  spike's per-run cost, wall time, and usage-window consumption. Note: N, not N*k, sets the
  headline CI width; k sharpens per-instance classification (the flip signal).

## Conditions

| id | config dir | prompt | purpose |
|---|---|---|---|
| C0 | `bench/c0-config` (rules only, no agents, no commands) | `bench/c0-prompt.md` | single-agent baseline |
| C1 | `harness/` at the seed commit | `/swe-fix` | seeded multi-agent harness, all agents on sonnet |
| C2..Cn | `harness/` at each accepted improver commit | `/swe-fix` | accepted variants |
| cand-<sha7> | candidate commit | `/swe-fix` | improver screens (not headline results) |
| C1o (optional) | C1 with lead on opus | `/swe-fix` | sensitivity: does an Opus orchestrator matter |

C0 and C1 differ only in the presence of the multi-agent structure: same rules, same
done-condition, same JSON summary contract, same model, effort, budget, timeout, image.

## Per-run guards

- Hidden fields never enter the container; only `problem_statement` is written to `/task/problem.md`.
- Git history scrubbed to one commit; `.claude/` and `.mcp.json` removed; both asserted before the agent starts.
- One credential env var per run; manifest records `subscription` or `api_key`.
- Wall clock: **TBD** s (assumption 2400). Budget: **TBD** USD per run (assumption 3.00), enforced by the CLI.
- Model diff hunks touching `test_patch` files are stripped; any other test-path edit is flagged `touched_tests`.
- Never `--bare`. The driver asserts it.

## Metrics

- Primary: mean pass@1 over k repeats per instance, averaged over instances; bootstrap 95% CI
  resampling instances (10,000 draws, seed 0).
- Classification per instance and condition: solid_pass (k/k), flaky, solid_fail (0/k).
- Paired comparison between conditions on shared instances: transition table of classes,
  `flips_up` (solid_fail -> solid_pass), `regressions` (solid_pass -> not solid_pass),
  Wilcoxon signed-rank on per-instance pass-count differences (ties discarded; `n_nonzero`
  reported), exact sign test on discordant majority pairs.
- Cost: `total_cost_usd` from the CLI result (tokens at API list price, client-side estimate;
  not a subscription cost), tokens, `num_turns`, wall time; cost per solved instance.
- Infrastructure failures (`paused`, `error`, `parse_error`) are reported alongside every
  headline number and re-run; they do not count toward k.

## Improver accept rule (frozen before the first iteration)

1. Candidate must pass the harness-load smoke check (`claude agents` lists the expected agents).
2. Train screen at k=1: reject if zero `flips_up` among train solid_fail instances OR any train
   solid_pass regresses.
3. Held-out at k=1: reject on any regression.
4. Confirmation at k=3 on both splits: accept only if held-out `regressions == 0` and train
   `flips_up >= 2`; the paired tests are reported but are screening statistics, not evidence.
5. The **only inferential test** in this study is the pre-registered final comparison of C0,
   C1, and the last accepted variant at full k on both splits. Per-iteration p-values are
   not corrected for multiple looks and are labeled as such.

## Compute decision rule (auth)

Spike: 6 runs (3 instances x C0, C1) on the Max 20x subscription. Record `/usage` 5-hour and
weekly percentages before and after. Project the total run count against weekly capacity.
If the heaviest benchmark week uses <= 50% of weekly capacity, the study runs on the
subscription and no API key is created. Otherwise a Console API key capped at $600/month
covers only the overflow of counted runs. Outcome: **TBD**.

## Caveats (from the stats review; stated so nobody over-reads the numbers)

1. The instance bootstrap absorbs between-instance spread, so measured coverage is ~97-99%,
   wider than nominal for a fixed-instance claim. We state the fixed-instance claim.
2. Overlapping per-condition CIs do not imply no paired difference; conditions share
   instances. Read the paired tests.
3. Wilcoxon on 0..k pass counts is coarse at k=3 (many ties); the sign test is the
   assumption-light cross-check. Both are reported.
4. Repeats are paired by index across conditions; if k ever differs for an instance the
   module flags `k_mismatch_instances` and that instance is excluded from the paired test.
5. `cost_per_solve` includes failed runs in the numerator by design.
6. Infra failures are not missing at random (`paused` clusters by time of day); the infra
   table accompanies every headline number.
7. Any run whose credential type differs from the rest of its condition is flagged; costs are
   not compared across credential types.
