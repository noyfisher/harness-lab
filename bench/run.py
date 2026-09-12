"""Run one (condition, instance, repeat) of the benchmark: agent in a container -> patch -> grade -> manifest.

Conditions:
  C0   plain single-agent `claude -p` with bench/c0-config as the config dir and bench/c0-prompt.md
  C1+  the harness/ checkout at --harness-sha (default HEAD) mounted as the config dir, prompt `/swe-fix`
  cand-<sha7> candidate screens use the same path as C1 with an explicit sha

Hard rules enforced here (see docs/decisions.md):
  * never `--bare` (it skips custom agents/commands and does not read subscription tokens)
  * hidden fields (test_patch, patch, FAIL_TO_PASS, PASS_TO_PASS, hints_text) never enter the container
  * git history is scrubbed to a single commit before the agent starts; .claude/ and .mcp.json removed
  * exactly one credential env var enters the container; the manifest records which
  * every run has a dollar budget and a wall-clock alarm; killed runs are manifests, not gaps
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from swebench.task.repo import load_task

from bench import grade as grader

ROOT = Path(__file__).resolve().parents[1]
HARNESS_DIR = ROOT / "harness"
C0_CONFIG = ROOT / "bench" / "c0-config"
C0_PROMPT = ROOT / "bench" / "c0-prompt.md"
RUNS = ROOT / "results" / "runs.jsonl"
PATCHES = ROOT / "results" / "patches"
TRACES = ROOT / "results" / "traces"
CRED_FILE = Path(os.environ.get("HARNESS_LAB_CREDENTIALS", Path.home() / ".harness-lab" / "credentials.env"))
PINNED_CLI = "2.1.76"
TEST_PATH_RE = re.compile(r"(^|/)(tests?|testing)(/|$)|(^|/)test_[^/]*\.py$|_tests?\.py$|(^|/)conftest\.py$")
PERMISSION_FLAG = "--dangerously-skip-permissions"  # only ever used inside a throwaway container


def sh(cmd, timeout=None, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)


def read_credentials() -> tuple[str, str]:
    """Return (env_var_name, value). Exactly one credential is allowed; the value is only forwarded."""
    env = {}
    if CRED_FILE.exists():
        for line in CRED_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    present = [k for k in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY") if env.get(k)]
    if len(present) != 1:
        raise SystemExit(
            f"exactly one credential required, found {present or 'none'}. Put CLAUDE_CODE_OAUTH_TOKEN=... "
            f"(from `claude setup-token`) or ANTHROPIC_API_KEY=... in {CRED_FILE}"
        )
    return present[0], env[present[0]]


def harness_export(sha: str) -> tuple[Path, str]:
    """Export harness/ at `sha` to a temp dir (clean tree, never the working copy)."""
    full = sh(["git", "-C", str(ROOT), "rev-parse", sha]).stdout.strip()
    if not full:
        raise SystemExit(f"cannot resolve harness sha {sha!r}; commit harness/ first")
    tmp = Path(tempfile.mkdtemp(prefix="hl-harness-"))
    r = subprocess.run(
        f"git -C {ROOT} archive {full} harness | tar -x -C {tmp}", shell=True, capture_output=True, text=True
    )
    if r.returncode != 0 or not (tmp / "harness").is_dir():
        raise SystemExit(f"git archive failed for {full}: {r.stderr}")
    # The improver's hypothesis names train instance ids; it is loop bookkeeping, not harness
    # behaviour, and must never enter the agent container.
    (tmp / "harness" / "HYPOTHESIS.json").unlink(missing_ok=True)
    return tmp / "harness", full


def split_diff(diff: str) -> list[tuple[str, str]]:
    """[(path, chunk)] for a unified diff; path is the b/ path."""
    out = []
    parts = re.split(r"(?m)^(?=diff --git )", diff)
    for part in parts:
        if not part.startswith("diff --git "):
            continue
        m = re.match(r"diff --git a/(.*?) b/(.*)", part.splitlines()[0])
        path = m.group(2) if m else ""
        out.append((path, part))
    return out


def filter_patch(model_diff: str, test_patch: str) -> tuple[str, int, bool]:
    """Drop hunks touching files in test_patch; flag other test paths. Returns (diff, stripped, touched_tests)."""
    protected = {p for p, _ in split_diff(test_patch)}
    kept, stripped, touched = [], 0, False
    for path, chunk in split_diff(model_diff):
        if path in protected:
            stripped += 1
            continue
        if TEST_PATH_RE.search(path):
            touched = True
        kept.append(chunk)
    return "".join(kept), stripped, touched


RATE_RE = re.compile(r"rate.?limit|usage limit|429|overloaded|limit reached", re.I)


def classify_result(result: dict | None, rc: int, timed_out: bool, stderr: str) -> tuple[str, str]:
    """Map the claude -p result to (outcome, note). Outcome is refined later by grading."""
    if timed_out:
        # A timeout with no result event and no spend means the session never got API progress
        # (usage wall, backoff loop). That is infrastructure, so the batch pauses and re-queues it.
        if result is None:
            return "paused", "wall-clock alarm with no API progress (usage wall?)"
        return "timeout", "wall-clock alarm"
    if result is None:
        text = (stderr or "")[-500:]
        if RATE_RE.search(text):
            return "paused", text
        return "parse_error", f"no result event (rc={rc}): {text}"
    subtype = str(result.get("subtype", ""))
    err_text = json.dumps(result)[:2000]
    if "budget" in subtype:
        return "budget", subtype
    # A session that ends after one turn at zero cost did no work (e.g. "Unknown skill" when a
    # degraded Docker VM failed to materialize the config dir). That is infrastructure, not a
    # counted failure of the agent.
    if (result.get("num_turns") or 0) <= 1 and not (result.get("total_cost_usd") or 0):
        return "error", f"zero-cost session: {str(result.get('result'))[:160]}"
    if result.get("is_error") or subtype.startswith("error"):
        if RATE_RE.search(err_text):
            return "paused", subtype
        return "error", subtype
    return "ok", subtype


SETUP_SCRIPT = r"""
set -euo pipefail
rm -rf /harness && mkdir -p /harness && cp -a /harness-src/. /harness/
cd /testbed
rm -rf .git .claude .mcp.json
git init -q && git config user.email bench@harness-lab && git config user.name harness-lab
git add -A >/dev/null 2>&1 && git commit -qm base >/dev/null
[ "$(git log --oneline | wc -l | tr -d ' ')" = "1" ] || { echo "SCRUB_FAILED"; exit 9; }
[ ! -e .claude ] && [ ! -e .mcp.json ] || { echo "GUARD_FAILED"; exit 9; }
claude --version
"""


def run_one(a) -> dict:
    t_start = time.time()
    run_id = f"{a.condition}-{a.instance}-r{a.repeat}-{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    bench = getattr(a, "bench", "verified")
    if bench == "live":
        # SWE-bench-Live: amd64-only images under emulation, results kept apart from the Verified study.
        from bench import live
        task = live.load_instance(a.instance)
        image = f"harness-lab/agent.amd64.{a.instance}"
        platform = "linux/amd64"
        base_ref = live.image_ref(a.instance)
        runs_path, patches_dir, traces_dir = (ROOT / "results" / "live" / "runs.jsonl",
                                              ROOT / "results" / "live" / "patches",
                                              ROOT / "results" / "live" / "traces")
    else:
        task = load_task(grader.TASKS_REPO / "tasks" / a.instance)
        image = f"harness-lab/agent.arm64.{a.instance}"
        platform = "linux/arm64"
        base_ref = grader.image_ref(a.instance)
        runs_path, patches_dir, traces_dir = RUNS, PATCHES, TRACES
    manifest = {
        "bench": bench,
        "run_id": run_id, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "condition": a.condition,
        "harness_sha": None, "cli_version": None, "model": a.model, "effort": a.effort, "credential": None,
        "instance_id": a.instance, "repeat": a.repeat, "outcome": None, "resolved": None,
        "touched_tests": False, "stripped_test_hunks": 0, "num_turns": None, "total_cost_usd": None,
        "input_tokens": None, "output_tokens": None, "cache_read_tokens": None, "cache_write_tokens": None,
        "duration_ms": None, "wall_s": None, "patch_path": None, "trace_path": None, "grade_run_id": None,
        "summary": None, "notes": "", "supersedes": None, "budget_usd": a.budget_usd, "network": a.network,
    }
    # --- preconditions ---
    if sh(["docker", "ps"]).returncode != 0:
        raise SystemExit("docker daemon not reachable (open Docker Desktop)")
    if sh(["docker", "image", "inspect", image]).returncode != 0:
        raise SystemExit(f"agent image missing: {image}. Build with bench/docker/build{'-live' if bench == 'live' else ''}.sh {a.instance}")
    dig = sh(["docker", "image", "inspect", "--format", "{{index .RepoDigests 0}}", base_ref]).stdout.strip()
    manifest["image_digest"] = dig or None  # only `latest` is published; the digest pins the environment
    cred_name, cred_value = ("DRY", "dry") if a.dry else read_credentials()
    manifest["credential"] = {"CLAUDE_CODE_OAUTH_TOKEN": "subscription", "ANTHROPIC_API_KEY": "api_key", "DRY": "dry"}[cred_name]

    # --- config dir + prompt ---
    tmp_root = Path(tempfile.mkdtemp(prefix="hl-run-"))
    if a.condition.startswith("C0"):  # C0 and model-tier variants such as C0o share the plain baseline config
        cfg_src = C0_CONFIG
        prompt = C0_PROMPT.read_text()
    else:
        cfg_src, manifest["harness_sha"] = harness_export(a.harness_sha)
        prompt = "/swe-fix"
    schema_path = cfg_src / "schemas" / "summary.schema.json"
    if not schema_path.exists():
        schema_path = HARNESS_DIR / "schemas" / "summary.schema.json"
    task_dir = tmp_root / "task"
    task_dir.mkdir()
    (task_dir / "problem.md").write_text(task["problem_statement"])  # the ONLY task data that enters
    (task_dir / "prompt.md").write_text(prompt)
    cname = "hl.run." + re.sub(r"[^A-Za-z0-9_.-]", "_", run_id)[:70]
    trace_path = TRACES / f"{run_id}.jsonl.gz"
    result_event = None
    stderr_tail = ""
    rc = -1
    timed_out = False
    try:
        # --- container ---
        env_args = ["-e", f"{cred_name}={cred_value}", "-e", "CLAUDE_CONFIG_DIR=/harness", "-e", "IS_SANDBOX=1",
                    "-e", "DISABLE_AUTOUPDATER=1", "-e", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1", "-e", "HOME=/root"]
        r = sh(["docker", "run", "-d", "--name", cname, "--platform", platform, "--network", a.network,
                "-v", f"{cfg_src}:/harness-src:ro", "-v", f"{task_dir}:/task", *env_args, image, "sleep", "infinity"], timeout=300)
        if r.returncode != 0:
            raise RuntimeError(f"docker run failed: {r.stderr.strip()}")

        # --- pre-agent setup inside: writable config copy, leakage scrub, guards ---
        r = sh(["docker", "exec", cname, "/bin/bash", "-c", SETUP_SCRIPT], timeout=900)
        if r.returncode != 0:
            raise RuntimeError(f"setup failed: {r.stdout[-300:]} {r.stderr[-300:]}")
        manifest["cli_version"] = r.stdout.strip().splitlines()[-1].split()[0]
        if manifest["cli_version"] != PINNED_CLI:
            raise RuntimeError(f"CLI in image is {manifest['cli_version']}, protocol pins {PINNED_CLI}")

        # --- the agent ---
        claude_cmd = [
            "claude", "-p", "--verbose", "--output-format", "stream-json",
            PERMISSION_FLAG, "--no-session-persistence",
            "--model", a.model, "--effort", a.effort, "--max-budget-usd", str(a.budget_usd),
        ]
        if schema_path.exists():
            claude_cmd += ["--json-schema", schema_path.read_text()]
        assert "--bare" not in claude_cmd  # non-negotiable 6
        if a.dry:
            inner = "echo '{\"type\":\"result\",\"subtype\":\"dry\",\"is_error\":false,\"total_cost_usd\":0,\"num_turns\":0,\"duration_ms\":0}'"
        else:
            quoted = " ".join("'" + c.replace("'", "'\"'\"'") + "'" for c in claude_cmd)
            inner = f'cd /testbed && {quoted} "$(cat /task/prompt.md)"'
        t0 = time.time()
        traces_dir.mkdir(parents=True, exist_ok=True)
        raw_trace = tmp_root / "trace.jsonl"
        with open(raw_trace, "wb") as out, open(tmp_root / "stderr.txt", "wb") as err:
            try:
                proc = subprocess.run(["docker", "exec", "-w", "/testbed", cname, "/bin/bash", "-lc", inner],
                                      stdout=out, stderr=err, timeout=a.timeout)
                rc = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
        stderr_tail = (tmp_root / "stderr.txt").read_text(errors="replace")[-2000:]
        for line in raw_trace.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "result":
                result_event = ev
        with gzip.open(trace_path, "wb") as gz:
            gz.write(raw_trace.read_bytes())
        manifest["trace_path"] = str(trace_path.relative_to(ROOT))
        manifest["duration_ms"] = int((time.time() - t0) * 1000)

        # --- result fields (defensive) ---
        if result_event:
            usage = result_event.get("usage") or {}
            manifest.update({
                "num_turns": result_event.get("num_turns"), "total_cost_usd": result_event.get("total_cost_usd"),
                "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
                "cache_read_tokens": usage.get("cache_read_input_tokens"), "cache_write_tokens": usage.get("cache_creation_input_tokens"),
                "summary": result_event.get("structured_output"),
                "model_ids": sorted((result_event.get("modelUsage") or {}).keys()),  # what actually ran
            })
            if result_event.get("duration_ms"):
                manifest["duration_ms"] = result_event["duration_ms"]
        outcome, note = classify_result(result_event, rc, timed_out, stderr_tail)
        manifest["notes"] = note

        # --- patch ---
        r = sh(["docker", "exec", "-w", "/testbed", cname, "/bin/bash", "-c",
                "git add -A -N . >/dev/null 2>&1; git -c core.fileMode=false diff"], timeout=300)
        raw_diff = r.stdout or ""
        diff, stripped, touched = filter_patch(raw_diff, task["test_patch"])
        manifest["stripped_test_hunks"], manifest["touched_tests"] = stripped, touched
        patches_dir.mkdir(parents=True, exist_ok=True)
        patch_path = patches_dir / f"{run_id}.diff"
        patch_path.write_text(diff)
        manifest["patch_path"] = str(patch_path.relative_to(ROOT))

        # --- grade ---
        if outcome in ("paused", "parse_error", "error"):
            manifest["outcome"] = outcome
        elif not diff.strip():
            manifest["outcome"] = "no_diff" if outcome == "ok" else outcome
        elif a.no_grade or a.dry:
            manifest["outcome"] = outcome if outcome != "ok" else "ungraded"
        else:
            grade_run = f"grade-{run_id}"
            if bench == "live":
                rep = live.grade_live(a.instance, diff, grade_run, timeout=a.grade_timeout)
            else:
                rep = grader.grade(a.instance, diff, grade_run, timeout=a.grade_timeout, pull=True)  # pull if the base image is missing
            manifest["grade_run_id"] = grade_run
            manifest["resolved"] = bool(rep.get("resolved"))
            if rep.get("infra_failure"):
                manifest["outcome"] = "error"
                manifest["notes"] += f" | grading infra failure: {rep.get('infra_failure_reason')}"
            elif outcome == "ok":
                manifest["outcome"] = "resolved" if manifest["resolved"] else "unresolved"
            else:  # timeout/budget with a diff: graded, outcome keeps the cause
                manifest["outcome"] = outcome
            manifest["notes"] += f" | f2p {rep.get('f2p')} p2p {rep.get('p2p')} applied={rep.get('patch_successfully_applied')}"
    except Exception as e:
        manifest["outcome"] = "error"
        manifest["notes"] = f"{type(e).__name__}: {e}"[:1000]
    finally:
        sh(["docker", "rm", "-f", cname])
        if not a.keep_tmp:
            shutil.rmtree(tmp_root, ignore_errors=True)
            if not a.condition.startswith("C0") and cfg_src.parent.name.startswith("hl-harness-"):
                shutil.rmtree(cfg_src.parent, ignore_errors=True)
    manifest["wall_s"] = round(time.time() - t_start, 1)
    target = runs_path.with_name("dryruns.jsonl") if a.dry else runs_path  # dry runs never touch the counted file
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a") as fh:
        fh.write(json.dumps(manifest) + "\n")
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--instance", required=True)
    ap.add_argument("--bench", choices=["verified", "live"], default="verified",
                    help="verified: Epoch arm64 images + swe-bench-tasks; live: SWE-bench-Live amd64 images, results under results/live/")
    ap.add_argument("--condition", required=True, help="C0, C1, C2.., or cand-<sha7>")
    ap.add_argument("--harness-sha", default="HEAD")
    ap.add_argument("--repeat", type=int, default=0)
    ap.add_argument("--model", default="claude-sonnet-5", help="explicit model id; the sonnet alias resolves to 4.6 in CLI 2.1.76")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--budget-usd", type=float, default=3.0)
    ap.add_argument("--timeout", type=int, default=2400, help="agent wall clock seconds")
    ap.add_argument("--grade-timeout", type=int, default=1800)
    ap.add_argument("--network", default="bridge", help="docker network for the agent container")
    ap.add_argument("--no-grade", action="store_true")
    ap.add_argument("--dry", action="store_true", help="exercise the plumbing without invoking claude")
    ap.add_argument("--keep-tmp", action="store_true")
    a = ap.parse_args(argv)
    m = run_one(a)
    print(json.dumps({k: m[k] for k in ("run_id", "condition", "instance_id", "repeat", "outcome", "resolved",
                                          "num_turns", "total_cost_usd", "wall_s", "credential", "harness_sha", "notes")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
