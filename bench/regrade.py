"""Re-grade an existing run's patch without re-running the agent, appending a superseding manifest.

Use after a grading infrastructure failure (image not pulled yet, docker hiccup). The agent's
work, cost, and trace are preserved; only the grading verdict and outcome change. The new
manifest line carries `supersedes: <old run_id>` so stats.load_runs replaces the old line.

    python -m bench.regrade --run-id <run_id> [--timeout 1800]
    python -m bench.regrade --infra-failures      # every run whose notes mention a grading infra failure
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid

from bench import grade as grader
from bench.run import ROOT, RUNS


def load_manifests() -> list[dict]:
    if not RUNS.exists():
        return []
    return [json.loads(l) for l in RUNS.read_text().splitlines() if l.strip()]


def regrade(m: dict, timeout: int) -> dict:
    patch_path = ROOT / m["patch_path"]
    diff = patch_path.read_text()
    new = dict(m)
    new["run_id"] = f"{m['run_id']}-rg{uuid.uuid4().hex[:4]}"
    new["supersedes"] = m["run_id"]
    new["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    base_note = (m.get("notes") or "").split(" | grading infra failure")[0]
    if not diff.strip():
        new["outcome"], new["resolved"], new["grade_run_id"] = "no_diff", None, None
        new["notes"] = base_note + " | regraded: empty patch"
        return new
    grade_run = f"grade-{new['run_id']}"
    rep = grader.grade(m["instance_id"], diff, grade_run, timeout=timeout, pull=True)
    new["grade_run_id"] = grade_run
    new["resolved"] = bool(rep.get("resolved"))
    if rep.get("infra_failure"):
        new["outcome"] = "error"
        new["notes"] = base_note + f" | regrade infra failure: {rep.get('infra_failure_reason')}"
    else:
        agent_outcome = "ok" if (m.get("outcome") not in ("timeout", "budget")) else m["outcome"]
        new["outcome"] = ("resolved" if new["resolved"] else "unresolved") if agent_outcome == "ok" else agent_outcome
        new["notes"] = base_note + f" | regraded: f2p {rep.get('f2p')} p2p {rep.get('p2p')} applied={rep.get('patch_successfully_applied')}"
    return new


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run-id")
    ap.add_argument("--infra-failures", action="store_true")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args(argv)
    ms = load_manifests()
    superseded = {m["supersedes"] for m in ms if m.get("supersedes")}
    if a.run_id:
        targets = [m for m in ms if m["run_id"] == a.run_id]
    elif a.infra_failures:
        targets = [m for m in ms if "grading infra failure" in (m.get("notes") or "") and m["run_id"] not in superseded]
    else:
        ap.error("--run-id or --infra-failures required")
    if not targets:
        print("nothing to regrade", file=sys.stderr)
        return 0
    with open(RUNS, "a") as fh:
        for m in targets:
            new = regrade(m, a.timeout)
            fh.write(json.dumps(new) + "\n")
            print(json.dumps({k: new[k] for k in ("run_id", "supersedes", "condition", "instance_id", "outcome", "resolved", "notes")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
