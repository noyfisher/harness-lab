# Benchmark environment

This is a benchmark environment: **no user, no network, no deploys.** Nobody will answer a question, so never ask one — choose the safe default, state it, and proceed. The task is always the same shape: fix the one issue described in `/task/problem.md` in the repository at `/testbed`, and prove it.

## Standing rules

1. **Reproduce first.** Before any edit, a small script under `/task/repro/` demonstrates the bug and fails on the unmodified repository. Run it and see it fail.
2. **Localize with evidence before editing.** Files and lines are named together with the grep or read that found them. No edit without a stated root cause.
3. **Minimal fix, library code only.** The smallest change that addresses the cause. No refactors, no drive-by cleanups, no new dependencies.
4. **Run the repro until it passes.**
5. **Run the nearest existing tests** to the changed files — the same module's tests, or its `tests/` directory — and show the exact command and the last 20 lines of its output.
6. **Never edit the repository's existing test files. Never leave debug prints. Touch nothing outside `/testbed` except `/task/repro/`.** Every change stays an unstaged working-tree diff: never `git add`, `git commit`, `git stash`, or `git reset --hard`.
7. **No network access.** Do not try to install packages; work with what is in the container.
8. **If blocked after a reasonable effort, stop and say so honestly.** Never fabricate a passing result, an output you did not see, or a diff you did not make.

## Done condition

All three, demonstrated in your own shell: the reproduction script passes; the nearest existing tests were run and their output shown; `git -C /testbed diff` is non-empty. "Gates green" is never sufficient on its own.
