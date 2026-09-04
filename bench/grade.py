"""Grade a model patch for one SWE-bench Verified instance inside Epoch AI's arm64 image.

Why this exists instead of `swebench.harness.run_evaluation`: that runner resolves images by
name from the task's `image` field (official x86_64 images). We run on Apple Silicon and use
Epoch's `ghcr.io/epoch-research/swe-bench.eval.arm64.<instance_id>` images, so we build the
same TestSpec (`swebench.harness.utils.make_test_spec`) from the swe-bench-tasks task dir,
swap the image reference, and replay the official runner's steps with the docker CLI:
start container -> copy patch -> apply with the official GIT_APPLY_CMDS chain -> copy eval.sh
-> run with timeout -> score the log with `swebench.harness.grading.get_eval_report`.

stdout and stderr are merged in order (stderr=STDOUT) because the eval script's start/end
markers are emitted by `set -x` on stderr while test output may go to either stream; the log
parser slices between the markers, so stream interleaving must match the official runner.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from swebench.harness.constants import APPLY_PATCH_FAIL, APPLY_PATCH_PASS, TESTS_TIMEOUT
from swebench.harness.grading import get_eval_report
from swebench.harness.run_evaluation import (  # these names are module-level there whatever their origin
    CONTAINER_PATCH_FILE,
    CONTAINER_USER,
    CONTAINER_WORKDIR,
    GIT_APPLY_CMDS,
)
from swebench.harness.utils import make_test_spec
from swebench.task.repo import load_task

ROOT = Path(__file__).resolve().parents[1]
TASKS_REPO = ROOT / "bench" / ".cache" / "swe-bench-tasks"
GRADE_DIR = ROOT / "results" / "grading"


def image_ref(instance_id: str, arch: str = "arm64") -> str:
    return f"ghcr.io/epoch-research/swe-bench.eval.{arch}.{instance_id}"


def load_instance(instance_id: str) -> dict:
    task_dir = TASKS_REPO / "tasks" / instance_id
    if not task_dir.is_dir():
        raise FileNotFoundError(f"no task dir for {instance_id} under {TASKS_REPO}")
    return load_task(task_dir)


def build_spec(instance: dict, arch: str = "arm64"):
    inst = dict(instance)
    inst["image"] = image_ref(inst["instance_id"], arch)
    return make_test_spec(inst)


def _sh(cmd: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _dexec(cname: str, script: str, timeout: float | None = 600) -> subprocess.CompletedProcess:
    return _sh(
        ["docker", "exec", "-w", CONTAINER_WORKDIR, "-u", CONTAINER_USER, cname, "/bin/bash", "-c", script],
        timeout=timeout,
    )


def ensure_image(image: str, pull: bool = True) -> bool:
    if _sh(["docker", "image", "inspect", image]).returncode == 0:
        return True
    if not pull:
        return False
    r = _sh(["docker", "pull", "-q", image], timeout=1800)
    return r.returncode == 0


def grade(
    instance_id: str,
    model_patch: str | None,
    run_id: str,
    arch: str = "arm64",
    timeout: int = 1800,
    keep: bool = False,
    model_name: str = "harness-lab",
    pull: bool = True,
) -> dict:
    """Return the per-instance report dict (resolved, patch_successfully_applied, ...)."""
    instance = load_instance(instance_id)
    spec = build_spec(instance, arch)
    log_dir = GRADE_DIR / run_id / instance_id
    log_dir.mkdir(parents=True, exist_ok=True)
    patch_file = log_dir / "patch.diff"
    patch_file.write_text(model_patch or "")
    eval_file = log_dir / "eval.sh"
    eval_file.write_text(spec.eval_script)
    test_output_path = log_dir / "test_output.txt"
    pred = {"instance_id": instance_id, "model_name_or_path": model_name, "model_patch": model_patch}
    cname = "hl." + re.sub(r"[^A-Za-z0-9_.-]", "_", f"{run_id}.{instance_id}")[:80]
    log: list[str] = []
    started = time.time()
    try:
        if not ensure_image(spec.image, pull=pull):
            raise RuntimeError(f"image not available: {spec.image}")
        r = _sh(["docker", "run", "-d", "--name", cname, "--platform", f"linux/{arch}", spec.image, "sleep", "infinity"], timeout=300)
        if r.returncode != 0:
            raise RuntimeError(f"docker run failed: {r.stderr.strip()}")
        log.append(f"container {cname} started from {spec.image}")
        _sh(["docker", "cp", str(patch_file), f"{cname}:{CONTAINER_PATCH_FILE}"])
        applied = False
        last = ""
        for attempt, cmd in enumerate(GIT_APPLY_CMDS):
            if attempt:
                _dexec(cname, "git checkout -- . ; git clean -fd")
            r = _dexec(cname, f"{cmd} {CONTAINER_PATCH_FILE}")
            last = (r.stdout or "") + (r.stderr or "")
            if r.returncode == 0:
                applied = True
                log.append(f"{APPLY_PATCH_PASS}:\n{last}")
                break
            log.append(f"Failed to apply patch to container: {cmd}\n{last}")
        if not applied:
            r = _dexec(cname, f"git apply --check --reverse {CONTAINER_PATCH_FILE}")
            if r.returncode == 0:
                applied = True
                log.append(f"{APPLY_PATCH_PASS}: verified already applied")
        if not applied:
            log.append(f"{APPLY_PATCH_FAIL}:\n{last}")
            test_output_path.write_text(f"{APPLY_PATCH_FAIL}:\n{last}\n")
        else:
            _sh(["docker", "cp", str(eval_file), f"{cname}:/eval.sh"])
            t0 = time.time()
            timed_out = False
            with open(test_output_path, "wb") as fh:
                try:
                    subprocess.run(
                        ["docker", "exec", cname, "/bin/bash", "/eval.sh"],
                        stdout=fh, stderr=subprocess.STDOUT, timeout=timeout,
                    )
                except subprocess.TimeoutExpired:
                    timed_out = True
            if timed_out:
                with open(test_output_path, "a") as fh:
                    fh.write(f"\n\n{TESTS_TIMEOUT}\nTimeout error: {timeout} seconds exceeded.\n")
            log.append(f"Test runtime: {time.time() - t0:.1f}s timed_out={timed_out}")
        report = get_eval_report(spec, pred, str(test_output_path), include_tests_status=True)
    except Exception as e:  # infra failure: record, never raise past the batch
        log.append(f"ERROR: {type(e).__name__}: {e}")
        report = {instance_id: {"patch_is_None": model_patch is None, "patch_exists": bool(model_patch),
                                "patch_successfully_applied": False, "resolved": False,
                                "infra_failure": True, "infra_failure_reason": f"{type(e).__name__}: {e}"}}
    finally:
        if not keep:
            _sh(["docker", "rm", "-f", cname])
        log.append(f"total {time.time() - started:.1f}s")
        (log_dir / "run_instance.log").write_text("\n".join(log) + "\n")
    (log_dir / "report.json").write_text(json.dumps(report, indent=2))
    out = dict(report[instance_id])
    out["instance_id"] = instance_id
    out["run_id"] = run_id
    out["wall_s"] = round(time.time() - started, 1)
    ts = out.get("tests_status") or {}
    f2p = ts.get("FAIL_TO_PASS", {})
    p2p = ts.get("PASS_TO_PASS", {})
    out["f2p"] = f"{len(f2p.get('success', []))}/{len(f2p.get('success', [])) + len(f2p.get('failure', []))}"
    out["p2p"] = f"{len(p2p.get('success', []))}/{len(p2p.get('success', [])) + len(p2p.get('failure', []))}"
    out.pop("tests_status", None)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--instance", help="single instance id")
    ap.add_argument("--instances", help="comma-separated ids or a JSON/text file with one id per line")
    ap.add_argument("--patch", help="path to a model patch (diff) for --instance")
    ap.add_argument("--gold", action="store_true", help="grade the dataset's gold patch (environment validation)")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--arch", default="arm64")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--keep", action="store_true", help="keep the container for inspection")
    ap.add_argument("--no-pull", action="store_true")
    ap.add_argument("--out", help="JSON file to merge {instance_id: resolved} results into")
    args = ap.parse_args(argv)

    if args.instance:
        ids = [args.instance]
    elif args.instances:
        p = Path(args.instances)
        if p.exists():
            txt = p.read_text()
            ids = json.loads(txt) if txt.lstrip().startswith("[") else [l.strip() for l in txt.splitlines() if l.strip()]
            if ids and isinstance(ids[0], dict):
                ids = [d["instance_id"] for d in ids]
        else:
            ids = [s.strip() for s in args.instances.split(",") if s.strip()]
    else:
        ap.error("--instance or --instances required")

    run_id = args.run_id or ("gold-" if args.gold else "grade-") + time.strftime("%Y%m%dT%H%M%S")

    def patch_for(iid: str) -> str | None:
        if args.gold:
            return load_instance(iid)["patch"]
        if args.patch:
            return Path(args.patch).read_text()
        raise SystemExit("need --gold or --patch")

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(grade, iid, patch_for(iid), run_id, args.arch, args.timeout, args.keep,
                          "gold" if args.gold else "harness-lab", not args.no_pull): iid for iid in ids}
        for fut in as_completed(futs):
            res = fut.result()
            results.append(res)
            print(json.dumps(res), flush=True)

    if args.out:
        outp = Path(args.out)
        merged = json.loads(outp.read_text()) if outp.exists() else {}
        for res in results:
            merged[res["instance_id"]] = bool(res.get("resolved"))
        outp.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
        print(f"merged {len(results)} results into {outp}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
