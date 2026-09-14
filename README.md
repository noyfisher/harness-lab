# harness-lab

A measurement rig that asks one question and answers it with numbers: does a multi-agent Claude
Code harness fix more SWE-bench Verified issues than a single `claude -p` invocation with the
same model, rules, budget, and container? It runs a pre-registered protocol on a fixed,
stratified 40-instance subset at 3 repeats per instance, then runs an automated improver loop
that proposes harness edits, screens them, and keeps only variants that clear a frozen accept
rule.

## Headline

All rows: `claude-sonnet-5` at medium effort, k = 3, 40 instances, bootstrap over instances
(10,000 resamples, seed 0). Source: `results/report.md`, generated from `results/runs.jsonl`.

| condition | what it is | pass rate (95% CI) | solid_pass / flaky / solid_fail | cost per solve |
|---|---|---|---:|---:|
| C0 | single agent, rules only, Sonnet 5 | 0.783 [0.658, 0.900] | 30 / 3 / 7 | $1.00 |
| C1 | seeded six-agent harness, Sonnet 5 | 0.750 [0.625, 0.875] | 28 / 3 / 9 | $1.73 |
| cand-5777b17 | best improver candidate (forced delegation) | 0.767 [0.642, 0.883] | 29 / 3 / 8 | $2.23 |
| C0o | single agent, Opus 5 (post-hoc extension) | 0.875 [0.775, 0.975] | 35 / 0 / 5 | $0.62 |
| C1o | six-agent harness, Opus 5 Lead (post-hoc extension) | 0.900 [0.808, 0.975] | 34 / 3 / 3 | $1.75 |

Paired C0 to C1 on all 40 instances: 0 flips up, 2 regressions, Wilcoxon p = 0.2568, sign test
p = 1.0. Six improver hypotheses were proposed and zero were accepted
(`improver/state/archive.json`). Paired C0o to C1o: 0 flips up, 1 regression, p = 0.276; the
Opus-lead harness solves nothing the Opus single agent does not, at 2.8x the cost per solve
(`docs/c1o.md`).

### Second study: SWE-bench-Live, Opus tier (protocol v2)

Same rig on 40 instances of SWE-bench-Live's frozen lite split (issues filed after the model
cutoffs), amd64 images under emulation, k = 3, `docs/protocol-v2.md` frozen before the first
counted run. Source: `results/live/report.md`, generated from `results/live/runs.jsonl`; page
at [noyfisher.github.io/harness-lab/live/](https://noyfisher.github.io/harness-lab/live/).

| condition | what it is | pass rate (95% CI) | solid_pass / flaky / solid_fail | cost per solve |
|---|---|---|---:|---:|
| C0o | single agent, Opus 5 | 0.492 [0.350, 0.633] | 16 / 7 / 17 | $1.77 |
| C1o | six-agent harness, Opus 5 Lead | 0.508 [0.367, 0.650] | 18 / 6 / 16 | $4.28 |

Paired C0o to C1o on all 40: 0 flips up, 0 regressions, Wilcoxon p = 0.414, sign test p = 1.0.
The one discordant majority pair favours the single agent. Same answer as Verified, on tasks the
models could not have seen: the structure adds cost (2.4x per solve), not solves
(`docs/writeup.md` section 3c).

## How it works

1. `bench/select.py` draws a stratified subset from the arm64-available instances, splits it
   60/40 train/held-out, and freezes it as `bench/subset.json`.
2. `bench/run.py` runs one (condition, instance, repeat) in a container: exports `harness/` at a
   pinned sha, scrubs git history, keeps hidden fields out, caps dollars and wall clock.
3. `bench/grade.py` grades the patch with the `swebench` 5.0.2 test spec and grading functions
   inside Epoch's arm64 image, replaying the official runner's steps.
4. `bench/batch.py` schedules batches repeat-major, resumes by counted run, and pauses on the
   subscription usage wall instead of burning it.
5. `bench/stats.py` classifies each instance as solid_pass / flaky / solid_fail, bootstraps over
   instances, and runs the paired tests; `bench/site.py` renders the static results page.
6. `improver/loop.py` proposes a harness variant, validates it mechanically (including a leak
   check), screens at k=1 on train and held-out, confirms at k=3, and archives the outcome.

## Quickstart

Requires Docker Desktop with arm64 images available and Python 3.11+.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python -m bench.fetch                        # dataset -> bench/instances.json
.venv/bin/python -m bench.select --candidates 60       # -> bench/candidates.json
.venv/bin/python -c "import json;print('\n'.join(json.load(open('bench/candidates.json'))['candidates']))" \
    > /tmp/candidates.txt
.venv/bin/python -m bench.grade --instances /tmp/candidates.txt --gold \
    --out bench/gold-results.json                      # validate the environment
.venv/bin/python -m bench.select --n 40 --gold-results bench/gold-results.json

bench/docker/build.sh django__django-11099             # agent image, one per instance
.venv/bin/python -m bench.run --instance django__django-11099 --condition C0 --dry

.venv/bin/python -m bench.batch --condition C0 --split all --k 3 --workers 3 \
    --batch-id C0-baseline
.venv/bin/python -m bench.stats --runs results/runs.jsonl --json results/all-stats.json \
    > results/report.md
.venv/bin/python -m bench.site --runs results/runs.jsonl --out results/site

.venv/bin/python -m improver.loop --once               # one improver iteration
```

`--dry` exercises the whole pipeline without invoking `claude`, and writes to
`results/dryruns.jsonl` so it can never contaminate counted runs.

## Credentials

Put exactly one credential in `~/.harness-lab/credentials.env`:

```
CLAUDE_CODE_OAUTH_TOKEN=...   # from `claude setup-token`
# or
ANTHROPIC_API_KEY=...
```

Exactly one must be present; the driver refuses to start otherwise, forwards only that one
variable into the container, and records only its type (`subscription` or `api_key`) in the run
manifest, never its value. The file lives outside the repository and is never committed.
Override the path with `HARNESS_LAB_CREDENTIALS`. This study ran entirely on a Max 20x
subscription; no API key was created.

## Where to read more

- `docs/protocol.md`: the pre-registered protocol, frozen before the first baseline run, with
  pinned versions, per-run guards, metrics, the improver accept rule, and the caveats.
- `docs/writeup.md`: the full study, including what went wrong operationally and what it cost.
- `docs/taxonomy.md`: the failure taxonomy read off the train-split dossiers.
- `docs/decisions.md`: the dated decision log, including every incident and its code fix.
- `results/site/index.html`: the generated results page, regenerated and diffed in CI so it can
  never drift from the manifest. Live copy: https://noyfisher.github.io/harness-lab/

## Honesty statement

The harness did not beat the baseline. The single agent resolved more instances at lower cost
per solve, no instance moved from always-fail to always-pass under the multi-agent harness, and
none of the six improver hypotheses cleared the accept rule that was frozen before any of them
were written. Cost figures are the CLI's client-side estimate at API list price, not what the
study actually cost, and the 40-instance subset gives a confidence interval wide enough to hide
any small effect. All of that is in the repository: the raw manifests, the batch records, the
rejected candidates with their hypotheses, and the runs that were invalidated by infrastructure
failures along with the code changes that stopped them from being counted. The repository is the
evidence either way.
