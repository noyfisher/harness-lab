# Run manifest schema (`results/runs.jsonl`, one JSON object per line, append-only)

Every counted run produces exactly one line. Never edit lines; append corrections as new
lines with `supersedes: <run_id>`.

| field | type | meaning |
|---|---|---|
| run_id | str | unique, `<condition>-<instance_id>-r<repeat>-<utc timestamp>` |
| ts | str | ISO-8601 UTC start time |
| condition | str | `C0` (plain claude -p), `C1` (seeded harness), `C2`.. (accepted variants), `cand-<sha7>` (candidate screen) |
| harness_sha | str or null | git SHA of `harness/` under test; null for C0 |
| cli_version | str | `claude --version` inside the container |
| model | str | model alias passed to `--model` |
| effort | str | `--effort` value |
| credential | str | `subscription` or `api_key` (which env var authenticated the run) |
| instance_id | str | SWE-bench Verified instance id |
| repeat | int | 0-based repeat index |
| outcome | str | `resolved`, `unresolved`, `no_diff`, `parse_error`, `timeout`, `budget`, `paused`, `error` |
| resolved | bool or null | grading verdict; null when not graded (no_diff, paused, error) |
| touched_tests | bool | model diff modified a test path outside `test_patch` files |
| stripped_test_hunks | int | hunks removed because they touched `test_patch` files |
| num_turns | int or null | from the `-p` JSON result |
| total_cost_usd | float or null | from the `-p` JSON result (tokens at API list price, client-side estimate) |
| input_tokens | int or null | |
| output_tokens | int or null | |
| cache_read_tokens | int or null | |
| cache_write_tokens | int or null | |
| duration_ms | int or null | agent session duration from the JSON result |
| wall_s | float | driver-measured wall clock incl. container start |
| patch_path | str or null | `results/patches/<run_id>.diff` |
| trace_path | str or null | `results/traces/<run_id>.jsonl.gz` |
| grade_run_id | str or null | swebench grading run_id (fresh per evaluation) |
| summary | object or null | the agent's final `--json-schema` summary, if any |
| notes | str | free text (error message, pause reason) |
| supersedes | str or null | run_id this line corrects |

Aggregation rules (`bench/stats.py`):
- A run counts toward k only if `outcome` is `resolved` or `unresolved` or `no_diff` or `budget`
  or `timeout` (the agent had its chance). `paused`, `error`, `parse_error` do not count and are
  re-run; they are reported separately as infrastructure failures.
- `resolved == true` is a pass; everything else that counts is a fail.
- Per condition and instance: passes / k. Class: solid_pass (k/k), flaky, solid_fail (0/k).
