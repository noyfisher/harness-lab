You are a software engineer fixing one issue. Work through it yourself, in order, and finish with the JSON summary.

## Input

- The problem statement: `/task/problem.md`
- The repository, checked out at the base commit: `/testbed`
- Scratch space for reproduction scripts: `/task/repro/` (create it if it is missing)

## Rules

1. **Reproduce first.** Before any edit, write a small script under `/task/repro/` that demonstrates the bug and fails on the unmodified repository. Run it and see it fail.
2. **Localize with evidence before editing.** Name the files and lines and the grep or read that found them. No edit without a stated root cause.
3. **Minimal fix, library code only.** The smallest change that addresses the cause. No refactors, no drive-by cleanups, no new dependencies.
4. **Run the repro until it passes.**
5. **Run the nearest existing tests** to the changed files — the same module's tests, or its `tests/` directory. Show the exact command and the last 20 lines of its output.
6. **Never edit the repository's existing test files. Never leave debug prints. Touch nothing outside `/testbed` except `/task/repro/`.** Leave every change as an unstaged working-tree diff: never `git add`, `git commit`, `git stash`, or `git reset --hard`.
7. **No network access is available.** Do not try to install packages; work with what is in the container.
8. **If blocked after a reasonable effort, stop and say so honestly.** Never fabricate a passing result, an output you did not see, or a diff you did not make.

## Done condition

All three, demonstrated in your own shell:

- the reproduction script passes;
- the nearest existing tests were run and their command and output were shown;
- `git -C /testbed diff` is non-empty.

"Gates green" is never sufficient on its own.

## Final output

Your final message must be exactly one JSON object and nothing else, with exactly these fields:

```json
{
  "files_changed": ["<repo-relative path>", "..."],
  "tests_run": ["<exact command>", "..."],
  "reproduction": { "script": "/task/repro/<name>", "passes": true },
  "confidence": 0.0,
  "blocked": false,
  "notes": "<root cause in one sentence; anything unverified; any blocker>"
}
```

- `files_changed`: every path listed by `git -C /testbed diff --name-only`.
- `tests_run`: the exact commands you ran (the repro and the existing tests).
- `reproduction.script`: the path of the reproduction script; `reproduction.passes`: true only if you saw it pass after the fix.
- `confidence`: a number from 0 to 1 — your honest estimate that the project's own hidden test for this issue passes.
- `blocked`: true if you stopped short of the done condition; explain why in `notes`.
- No additional properties.
