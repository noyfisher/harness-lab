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

## Gold validation on arm64 (amd64 emulation)

(pending)

## What would change in the rig

- `bench/run.py`: an `--image` source switch (Epoch arm64 vs Live amd64 with `--platform
  linux/amd64`), and a task loader that reads the HF row instead of a swe-bench-tasks dir.
- `bench/grade.py`: delegate to the Live harness in its own venv via subprocess (predictions
  JSON in, `report.json` out), or reimplement `test_cmds` + `log_parser` with swebench 5.x
  parsers. Delegation is the faithful choice for leaderboard comparability.
- Agent image: `FROM starryzhang/...` + node + pinned CLI, built with `--platform linux/amd64`.
