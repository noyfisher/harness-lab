"""Batch runner: schedule many (condition, instance, repeat) runs of bench/run.py with guards.

One batch = one condition, one harness sha, one split, k repeats.  The scheduling rules come
from docs/protocol.md; the counting rules come from bench/stats.py (a run only counts toward k
if the agent had its chance).

Non-negotiables encoded here:
  * **repeat-major order** -- every instance gets repeat 0 before any instance gets repeat 1,
    so an interruption (pause, guard trip, Ctrl-C) never leaves a half-complete comparison.
  * **resume by counted run** -- a (condition, instance, repeat) that already has a counted
    manifest (after `supersedes`) is skipped, so re-invoking the same command is safe and
    never burns usage twice.
  * **one harness sha per batch** -- `--harness-sha` is resolved to a full sha once, at batch
    start, and that same sha is handed to every job, so a mid-batch commit cannot change what
    is being measured.
  * **preflight before anything runs** -- every agent image is asserted to exist up front, so
    a batch either starts whole or does not start.
  * **guards over usage** -- rate-limit pauses back off and re-queue; a run of infrastructure
    failures stops the batch instead of burning the owner's subscription on a broken setup.

Exit codes: 0 done, 1 preflight/arguments, 2 infra guard tripped, 3 pause budget exhausted,
130 interrupted (running jobs were allowed to finish and the summary was written).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import subprocess
import sys
import threading
import time
from collections import Counter, deque
from pathlib import Path

from bench import run, stats

# Module-level paths: overridable (tests monkeypatch these so nothing touches results/runs.jsonl).
ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "runs.jsonl"
DRYRUNS = ROOT / "results" / "dryruns.jsonl"
BATCH_DIR = ROOT / "results" / "batches"
SUBSET = ROOT / "bench" / "subset.json"
AGENT_IMAGE = "harness-lab/agent.arm64.{instance}"
AGENT_IMAGE_LIVE = "harness-lab/agent.amd64.{instance}"  # SWE-bench-Live runs under amd64 emulation

EXIT_OK = 0
EXIT_PREFLIGHT = 1
EXIT_INFRA = 2
EXIT_PAUSE = 3
EXIT_INTERRUPT = 130

#: run.py argparse fields a job namespace must mirror, with the values a batch always fixes.
FIXED_JOB_FIELDS = {"grade_timeout": 1800, "network": "bridge", "no_grade": False, "keep_tmp": False}
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


# --- small seams (monkeypatched in tests; nothing else in this module shells out) ------------


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _git_rev_parse(ref: str) -> str:
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", ref], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def docker_available() -> bool:
    return subprocess.run(["docker", "ps"], capture_output=True, text=True).returncode == 0


def agent_image(instance_id: str, bench: str = "verified") -> str:
    return (AGENT_IMAGE_LIVE if bench == "live" else AGENT_IMAGE).format(instance=instance_id)


def image_exists(instance_id: str, attempts: int = 3, bench: str = "verified") -> bool:
    """True if the agent image is present. Docker Desktop under load can fail a single inspect
    transiently (seen once on an image that both baselines had used), so a miss is retried before
    the preflight declares the image missing; only a persistent miss fails the batch."""
    for i in range(attempts):
        r = subprocess.run(["docker", "image", "inspect", agent_image(instance_id, bench)],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return True
        if "No such image" in (r.stderr or "") and i == attempts - 1:
            return False
        time.sleep(2 * (i + 1))
    return False


# --- 1. work list ---------------------------------------------------------------------------


def work_list(condition: str, instances, k: int) -> list[tuple[str, str, int]]:
    """Repeat-major: all instances at repeat 0, then all at repeat 1, ...  Instances sorted."""
    ordered = sorted(set(instances))
    return [(condition, iid, r) for r in range(k) for iid in ordered]


def load_split(subset_path, split: str) -> list[str]:
    """Instance ids for `train`, `heldout`, or `all` (their union) from subset.json."""
    data = json.loads(Path(subset_path).read_text())
    train = list(data.get("train") or [])
    heldout = list(data.get("heldout") or [])
    if split == "train":
        ids = train
    elif split == "heldout":
        ids = heldout
    elif split == "all":
        ids = train + heldout
    else:
        raise ValueError(f"unknown split {split!r}")
    return sorted(set(ids))


# --- 2. resume ------------------------------------------------------------------------------


def completed_keys(path) -> set[tuple[str, str, int]]:
    """{(condition, instance_id, repeat)} that already have a *counted* run, after supersedes."""
    p = Path(path)
    if not p.exists():
        return set()
    keys: set[tuple[str, str, int]] = set()
    for rec in stats.load_runs(p):
        if not stats.counted(rec):
            continue
        try:
            repeat = int(rec.get("repeat"))
        except (TypeError, ValueError):
            continue
        keys.add((rec.get("condition"), rec.get("instance_id"), repeat))
    return keys


# --- 3. preflight ---------------------------------------------------------------------------


def preflight(instances, bench: str = "verified") -> tuple[bool, str]:
    """Docker reachable and every agent image present.  Nothing runs until this passes."""
    if not docker_available():
        return False, "[batch] preflight FAILED: docker daemon not reachable (open Docker Desktop)"
    # verified keeps the one-argument call so test doubles that mimic the old signature still work
    missing = [iid for iid in sorted(set(instances))
               if not (image_exists(iid) if bench == "verified" else image_exists(iid, bench=bench))]
    if missing:
        lines = [f"[batch] preflight FAILED: {len(missing)} agent image(s) missing; nothing was run."]
        lines += [f"    {agent_image(iid, bench)}" for iid in missing]
        lines.append(f"    build with: bench/docker/build.sh {' '.join(missing)}")
        return False, "\n".join(lines)
    return True, f"[batch] preflight ok: docker up, {len(set(instances))} agent image(s) present"


# --- 4. jobs --------------------------------------------------------------------------------


def make_ns(a, condition: str, instance: str, repeat: int, sha: str) -> argparse.Namespace:
    """A namespace mirroring run.py's argparse fields (see FIXED_JOB_FIELDS for batch-fixed ones)."""
    return argparse.Namespace(
        instance=instance, condition=condition, harness_sha=sha, repeat=repeat,
        model=a.model, effort=a.effort, budget_usd=a.budget_usd, timeout=a.timeout,
        dry=a.dry, bench=getattr(a, "bench", "verified"), **FIXED_JOB_FIELDS,
    )


def _failed_manifest(item, exc, wall_s: float) -> dict:
    condition, instance, repeat = item
    return {
        "run_id": f"{condition}-{instance}-r{repeat}-batchfail",
        "condition": condition, "instance_id": instance, "repeat": repeat,
        "outcome": "error", "resolved": None, "total_cost_usd": None, "wall_s": round(wall_s, 1),
        "notes": f"batch: {type(exc).__name__}: {exc}"[:500],
    }


def _log_line(m: dict) -> str:
    resolved = m.get("resolved")
    cost = m.get("total_cost_usd")
    return "\t".join([
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        str(m.get("condition")), str(m.get("instance_id")), f"r{m.get('repeat')}",
        str(m.get("outcome")),
        f"resolved={'-' if resolved is None else resolved}",
        f"cost={0.0 if cost is None else float(cost):.4f}",
        f"wall={float(m.get('wall_s') or 0.0):.1f}s",
        f"run_id={m.get('run_id')}",
    ])


# --- 5. the scheduler -----------------------------------------------------------------------


def run_batch(a, sha: str, items, log_path: Path) -> dict:
    """Run `items` with a worker pool, pause/resume on rate limits, and an infra circuit breaker."""
    pending = deque(items)
    inflight: dict[cf.Future, tuple[str, str, int]] = {}
    retried: set[tuple[str, str, int]] = set()   # each item gets exactly one infra retry
    counts: Counter = Counter()
    manifests: list[dict] = []
    log_lock = threading.Lock()
    t_batch = time.time()

    state = {
        "consecutive_infra": 0, "consecutive_pauses": 0, "max_consecutive_pauses": 0,
        "paused": False, "paused_total_s": 0.0, "requeued": 0, "done": 0,
        "cost": 0.0, "jobs_wall_s": 0.0, "stop_code": None, "interrupted": False,
    }

    def job(item):
        condition, instance, repeat = item
        t0 = time.time()
        try:
            return run.run_one(make_ns(a, condition, instance, repeat, sha))
        except (Exception, SystemExit) as exc:   # a job never takes the batch down with it
            return _failed_manifest(item, exc, time.time() - t0)

    def record(item, m, allow_requeue: bool) -> None:
        outcome = m.get("outcome") or "error"
        m.setdefault("condition", item[0])
        m.setdefault("instance_id", item[1])
        m.setdefault("repeat", item[2])
        state["done"] += 1
        counts[outcome] += 1
        state["cost"] += float(m.get("total_cost_usd") or 0.0)
        state["jobs_wall_s"] += float(m.get("wall_s") or 0.0)
        manifests.append(m)
        with log_lock:
            with open(log_path, "a") as fh:
                fh.write(_log_line(m) + "\n")
        planned = state["done"] + len(pending) + len(inflight)
        print(f"[{state['done']:3d}/{planned}] {item[0]} {item[1]} r{item[2]} -> {outcome} "
              f"resolved={m.get('resolved')} cost=${float(m.get('total_cost_usd') or 0.0):.2f} "
              f"wall={float(m.get('wall_s') or 0.0):.0f}s", flush=True)
        if not allow_requeue:
            return
        if outcome == "paused":
            state["paused"] = True
            state["consecutive_pauses"] += 1
            state["max_consecutive_pauses"] = max(state["max_consecutive_pauses"], state["consecutive_pauses"])
            pending.appendleft(item)          # first thing retried when the pause lifts
            state["requeued"] += 1
        elif outcome in ("error", "parse_error"):
            state["consecutive_infra"] += 1
            if item not in retried:
                retried.add(item)
                pending.append(item)          # one retry, at the back: transients get time
                state["requeued"] += 1
            if state["consecutive_infra"] >= a.max_infra_errors:
                print(f"[batch] STOP: {state['consecutive_infra']} consecutive infra failures "
                      f"(--max-infra-errors {a.max_infra_errors}); something systemic is wrong.", flush=True)
                state["stop_code"] = EXIT_INFRA
        else:
            state["consecutive_infra"] = 0
            state["consecutive_pauses"] = 0

    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        try:
            while (pending or inflight) and state["stop_code"] is None:
                while pending and not state["paused"] and len(inflight) < a.workers:
                    item = pending.popleft()
                    inflight[ex.submit(job, item)] = item
                if not inflight:
                    if not state["paused"]:
                        break
                    pause_s = a.pause_minutes * 60.0
                    if state["paused_total_s"] + pause_s > a.max_pause_hours * 3600.0:
                        print(f"[batch] STOP: pause budget exhausted "
                              f"({state['paused_total_s'] / 3600.0:.2f}h paused, cap {a.max_pause_hours}h).",
                              flush=True)
                        state["stop_code"] = EXIT_PAUSE
                        break
                    print(f"[batch] rate limited; pausing {a.pause_minutes} min "
                          f"({state['paused_total_s'] / 60.0:.0f} min paused so far, "
                          f"{state['consecutive_pauses']} consecutive)", flush=True)
                    _sleep(pause_s)
                    state["paused_total_s"] += pause_s
                    state["paused"] = False
                    continue
                done, _ = cf.wait(list(inflight), return_when=cf.FIRST_COMPLETED)
                for fut in done:
                    record(inflight.pop(fut), fut.result(), allow_requeue=True)
        except KeyboardInterrupt:
            state["interrupted"] = True
            state["stop_code"] = EXIT_INTERRUPT
            print(f"\n[batch] interrupted: starting no new jobs, waiting for "
                  f"{len(inflight)} running job(s) to finish (Ctrl-C again to stop waiting).", flush=True)
        # drain: whatever is still running finishes and is recorded (never re-queued)
        try:
            while inflight:
                done, _ = cf.wait(list(inflight), return_when=cf.FIRST_COMPLETED)
                for fut in done:
                    record(inflight.pop(fut), fut.result(), allow_requeue=False)
        except KeyboardInterrupt:
            print("[batch] second interrupt: abandoning the wait; containers may still be running.", flush=True)

    resolved = sum(1 for m in manifests if stats.counted(m) and stats.is_pass(m))
    return {
        "exit_code": state["stop_code"] or EXIT_OK,
        "completed": state["done"], "requeued": state["requeued"], "unrun": len(pending),
        "outcomes": dict(counts), "resolved": resolved,
        "counted": sum(1 for m in manifests if stats.counted(m)),
        "infra_failures": sum(counts[o] for o in ("error", "parse_error", "paused")),
        "total_cost_usd": round(state["cost"], 4),
        "jobs_wall_s": round(state["jobs_wall_s"], 1),
        "batch_wall_s": round(time.time() - t_batch, 1),
        "paused_minutes": round(state["paused_total_s"] / 60.0, 1),
        "max_consecutive_pauses": state["max_consecutive_pauses"],
        "interrupted": state["interrupted"],
        "manifests": manifests,
    }


# --- 6. reporting ---------------------------------------------------------------------------


def print_summary(batch_id: str, cfg: dict, res: dict) -> None:
    counts = res["outcomes"]
    width = max([len(k) for k in counts] + [7])
    print(f"\n== batch {batch_id} ==")
    print(f"  condition      {cfg['condition']}   harness_sha {(cfg['harness_sha'] or '-')[:12]}"
          f"   model {cfg['model']}/{cfg['effort']}{'   [DRY]' if cfg['dry'] else ''}")
    print(f"  split          {cfg['split']}  ({len(cfg['instances'])} instance(s), k={cfg['k']}, "
          f"workers={cfg['workers']})")
    print(f"  jobs           {res['completed']} completed, {cfg['skipped_resume']} skipped (resume), "
          f"{res['requeued']} re-queued, {res['unrun']} never started")
    print("  outcomes:")
    for outcome, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"    {outcome:<{width}} {n:4d}")
    print(f"  resolved       {res['resolved']} / {res['counted']} counted run(s)")
    print(f"  infra failures {res['infra_failures']} (paused/error/parse_error; not counted toward k)")
    print(f"  total cost     ${res['total_cost_usd']:.4f}  (client-side estimate at API list price)")
    print(f"  total wall     batch {res['batch_wall_s']:.1f}s, jobs {res['jobs_wall_s']:.1f}s summed")
    if res["paused_minutes"]:
        print(f"  paused         {res['paused_minutes']:.1f} min total, "
              f"{res['max_consecutive_pauses']} consecutive at worst")
    print(f"  record         {cfg['record_path']}")
    print(f"  exit           {res['exit_code']}")


# --- 7. CLI ---------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m bench.batch", description=__doc__.split("\n")[0])
    ap.add_argument("--bench", choices=["verified", "live"], default="verified",
                    help="verified (Epoch arm64, results/runs.jsonl) or live (SWE-bench-Live amd64, results/live/runs.jsonl)")
    ap.add_argument("--condition", required=True, help="C0, C1, C2.., or cand-<sha7>")
    ap.add_argument("--subset", default=None, help="subset.json (default bench/subset.json)")
    ap.add_argument("--split", default="all", choices=("all", "train", "heldout"))
    ap.add_argument("--k", type=int, default=3, help="repeats per instance")
    ap.add_argument("--workers", type=int, default=3, help="concurrent runs (protocol cap: 3)")
    ap.add_argument("--harness-sha", default="HEAD", help="resolved to a full sha once, at batch start")
    ap.add_argument("--instances", default=None, help="comma-separated ids; overrides the subset entirely")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--budget-usd", type=float, default=4.0)  # protocol v1
    ap.add_argument("--timeout", type=int, default=2400, help="agent wall clock seconds per run")
    ap.add_argument("--dry", action="store_true", help="dry runs; reads/writes results/dryruns.jsonl")
    ap.add_argument("--max-infra-errors", type=int, default=5,
                    help="consecutive error/parse_error runs that stop the batch")
    ap.add_argument("--pause-minutes", type=float, default=30.0, help="backoff after a rate-limit pause")
    ap.add_argument("--max-pause-hours", type=float, default=6.0, help="total paused wall time budget")
    ap.add_argument("--batch-id", default=None, help="default <condition>-<utc timestamp>")
    return ap


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    if a.workers < 1:
        print("[batch] --workers must be >= 1")
        return EXIT_PREFLIGHT
    if a.k < 0:
        print("[batch] --k must be >= 0")
        return EXIT_PREFLIGHT
    batch_id = a.batch_id or f"{a.condition}-{time.strftime('%Y%m%dT%H%M%S')}"
    if not _ID_RE.match(batch_id):
        print(f"[batch] bad --batch-id {batch_id!r}: use [A-Za-z0-9._-]")
        return EXIT_PREFLIGHT

    # --- instances ---
    subset_path = a.subset or SUBSET
    if a.instances:
        instances = sorted({s.strip() for s in a.instances.split(",") if s.strip()})
        split_label = "instances"
        subset_used = None
    else:
        try:
            instances = load_split(subset_path, a.split)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"[batch] cannot read split {a.split!r} from {subset_path}: {exc}\n"
                  f"        build it with bench/select.py, or pass --instances a,b,c")
            return EXIT_PREFLIGHT
        split_label = a.split
        subset_used = str(subset_path)
    if not instances:
        print(f"[batch] no instances selected (split {split_label!r})")
        return EXIT_PREFLIGHT

    # --- one sha for the whole batch ---
    sha = _git_rev_parse(a.harness_sha)
    if not sha:
        print(f"[batch] cannot resolve --harness-sha {a.harness_sha!r}; commit harness/ first")
        return EXIT_PREFLIGHT

    # --- work list (repeat-major) + resume ---
    items = work_list(a.condition, instances, a.k)
    if getattr(a, "bench", "verified") == "live":
        results_path = ROOT / "results" / "live" / ("dryruns.jsonl" if a.dry else "runs.jsonl")
    else:
        results_path = DRYRUNS if a.dry else RUNS
    done_keys = completed_keys(results_path)
    todo = [it for it in items if it not in done_keys]
    skipped = len(items) - len(todo)
    print(f"[batch] {batch_id}: {len(items)} job(s) planned "
          f"({len(instances)} instance(s) x k={a.k}, repeat-major)")
    print(f"[batch] resume: {skipped} already have a counted run in {results_path}; {len(todo)} to run")

    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    log_path = BATCH_DIR / f"{batch_id}.log"
    record_path = BATCH_DIR / f"{batch_id}.json"
    cfg = {
        "batch_id": batch_id, "bench": getattr(a, "bench", "verified"), "condition": a.condition, "harness_sha": sha,
        "harness_sha_ref": a.harness_sha, "split": split_label, "subset": subset_used,
        "k": a.k, "instances": instances, "model": a.model, "effort": a.effort,
        "budget_usd": a.budget_usd, "timeout": a.timeout, "grade_timeout": FIXED_JOB_FIELDS["grade_timeout"],
        "network": FIXED_JOB_FIELDS["network"], "workers": a.workers, "dry": a.dry,
        "max_infra_errors": a.max_infra_errors, "pause_minutes": a.pause_minutes,
        "max_pause_hours": a.max_pause_hours, "results_file": str(results_path),
        "planned_jobs": len(items), "skipped_resume": skipped,
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "ended": None,
        "argv": list(argv) if argv is not None else sys.argv[1:],
        "record_path": str(record_path), "log_path": str(log_path),
    }
    record_path.write_text(json.dumps(cfg, indent=1) + "\n")   # written up front: a crash still has a record

    if not todo:
        print("[batch] nothing to run; every planned job already has a counted run.")
        res = {"exit_code": EXIT_OK, "completed": 0, "requeued": 0, "unrun": 0, "outcomes": {},
               "resolved": 0, "counted": 0, "infra_failures": 0, "total_cost_usd": 0.0,
               "jobs_wall_s": 0.0, "batch_wall_s": 0.0, "paused_minutes": 0.0,
               "max_consecutive_pauses": 0, "interrupted": False, "manifests": []}
    else:
        ok, msg = preflight([iid for _, iid, _ in todo], getattr(a, "bench", "verified"))
        print(msg)
        if not ok:
            cfg["ended"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            cfg["result"] = {"exit_code": EXIT_PREFLIGHT, "note": "preflight failed; nothing ran"}
            record_path.write_text(json.dumps(cfg, indent=1) + "\n")
            return EXIT_PREFLIGHT
        res = run_batch(a, sha, todo, log_path)

    cfg["ended"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    cfg["result"] = {k: v for k, v in res.items() if k != "manifests"}
    cfg["run_ids"] = [m.get("run_id") for m in res["manifests"]]
    record_path.write_text(json.dumps(cfg, indent=1) + "\n")
    print_summary(batch_id, cfg, res)
    return res["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
