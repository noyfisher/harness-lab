# SWE-bench-Live spike (started 2026-09-12)

Question: can this rig run SWE-bench-Live's frozen `lite` split on Apple Silicon, and at what cost?

## Verified facts

- Dataset `SWE-bench-Live/SWE-bench-Live` (Python): splits `test` 1000, `lite` 300 (frozen),
  `verified` 500 (frozen), `full` 1888 (grows by ~50 issues a month). Fields carry everything the
  driver and grader need: `problem_statement`, `base_commit`, `patch`, `test_patch`,
  `FAIL_TO_PASS`, `PASS_TO_PASS`, plus `test_cmds` and `log_parser` (the task's own test command
  and parser), `difficulty` as `{files, hunks, lines}`, and `created_at` (2024-10 onward in lite).
- Images: Docker Hub `starryzhang/sweb.eval.x86_64.<instance_id with "__" -> "_1776_", lowercased>:latest`.
  Six random lite instances across six repos all exist. Single-arch **amd64 only**.
- Emulation: Docker Desktop on this M-series Mac runs amd64 containers at roughly 1.9x the
  native arm64 time on a pure-CPU Python loop (0.93 s vs 1.79 s), i.e. Rosetta-class, not QEMU.
- Image shape (faker-2190): 485 MB, pull 30 s, `/testbed` at the base commit, plain
  `/usr/local/bin/python` 3.10 (no conda), **3,956 commits of git history** (scrub required, as
  with the Verified images).
- Harness: `microsoft/SWE-bench-Live` main, `python -m evaluation.evaluation --dataset ... --split
  lite --instance_ids ... --platform linux --patch_dir gold|<preds.json> --output_dir ... --workers
  N --overwrite 1`. It applies the patch, runs the instance's `test_cmds`, parses with its
  `log_parser`, and writes `results.json` plus per-instance `report.json` with `resolved`.
  Requires the `launch` git submodule (RepoLaunch) and **Python >= 3.12**; installed in an
  isolated venv (`spikes/swe-bench-live/.venv`, Homebrew python@3.12) so the study's pinned
  swebench 5.0.2 is untouched. The old python-only branch used `swebench.harness.run_evaluation
  --namespace starryzhang` instead; both grade the same way.
- Leaderboard rule: the agent may see only `problem_statement` and the image; submissions must
  include rollout trajectories. This matches the study's existing guards and trace archive.

## Gold validation on arm64 (amd64 emulation), 2026-09-12

Six lite instances, six repos, harness run with `DOCKER_DEFAULT_PLATFORM=linux/amd64`, 2 workers.
Whole run 14 minutes including five image pulls (1.7 to 3.7 GB each).

| instance | gold | notes |
|---|---|---|
| yt-dlp__yt-dlp-11425 | resolved | first report 2 min after start, pull included |
| pydata__xarray-9974 | resolved | |
| mikedh__trimesh-2354 | resolved | |
| joke2k__faker-2190 | resolved | |
| matplotlib__matplotlib-29007 | NOT resolved | F2P 2/2 pass; P2P fails `test_backend_inline.py::test_ipynb` and `test_backend_nbagg.py::test_ipynb` (notebook-kernel tests; environment, not the patch). Excluded by the gold filter, as in the Verified study. |
| deepset-ai__haystack-8981 | error, then rerun | the harness's own registry check said "not found" although `docker pull` succeeds and Hub lists tags `latest`, `0430`; rerun after a manual pull (result below) |

Reading: the Live harness works end to end on this Mac under emulation. Gold grading time is
minutes per instance, dominated by the test suite, not the emulation. The gold filter will drop
instances with environment-bound tests exactly as it did for Verified (60/60 there; expect a
lower keep rate here, so draw 90 to 100 candidates for a 40 to 60 subset).

Haystack rerun: resolved=True (F2P 5 pass / 0 fail; P2P 0 fail). Gold tally: 5 of 6 resolved; the one true exclusion is matplotlib's notebook-bound tests.

## What would change in the rig

- `bench/run.py`: an `--image` source switch (Epoch arm64 vs Live amd64 with `--platform
  linux/amd64`), and a task loader that reads the HF row instead of a swe-bench-tasks dir.
- `bench/grade.py`: delegate to the Live harness in its own venv via subprocess (predictions
  JSON in, `report.json` out), or reimplement `test_cmds` + `log_parser` with swebench 5.x
  parsers. Delegation is the faithful choice for leaderboard comparability.
- Agent image: `FROM starryzhang/...` + node + pinned CLI, built with `--platform linux/amd64`.

## Gold validation of the 60 candidates (waves of 10, 2026-09-13)

Wave 1: 5 of 10 resolved. All four aws-cloudformation/cfn-lint candidates fail on PASS_TO_PASS
integration tests (`test_quickstart_templates*`) that appear to depend on external template
downloads, plus two unit tests; their FAIL_TO_PASS tests pass. One checkov candidate produced no
report. Both are environment-bound and excluded by the gold filter. A second-stage candidate list
(`bench/live-candidates-extra.json`, 32 ids = seeded 90-draw minus the 60-draw) is prepared in
case the keep rate stays near one half.

Final: 46 of 60 candidates resolve (77%), six waves of ten, 242 minutes, host free never below
243 GB thanks to per-wave cleanup. Failures by repo: aws-cloudformation 0/4, matplotlib 0/3,
keras 0/2, and singletons in checkov, flexget, smolagents, kedro, qtile. The second-stage list
was not needed. `bench/live-gold-results.json` is the exclusion record.
