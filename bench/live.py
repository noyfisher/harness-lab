"""SWE-bench-Live support: dataset fetch, image availability, and grading.

SWE-bench-Live (``SWE-bench-Live/SWE-bench-Live`` on the Hub) is the "living"
successor to SWE-bench Verified: frozen ``lite`` (300) and ``verified`` (500)
splits plus a ``full`` split that grows monthly.  Three things differ from the
Verified rig and this module owns all three:

1. **Images.**  Docker Hub ``starryzhang/sweb.eval.x86_64.<instance_id>`` with
   ``__`` rewritten to ``_1776_`` and the whole name lowercased (the upstream
   harness's own ``get_default_image_name``; see
   ``spikes/swe-bench-live/SWE-bench-Live/evaluation/evaluation.py``).  They are
   **single-arch amd64**, so everything here runs under emulation on Apple
   Silicon with ``DOCKER_DEFAULT_PLATFORM=linux/amd64``.

2. **Grading.**  Each instance carries its own ``test_cmds`` and ``log_parser``,
   so there is no single eval script to replay the way ``bench/grade.py`` does
   for Verified.  We delegate to the upstream harness (``evaluation.evaluation``)
   running in its own Python 3.12 venv, and translate its ``report.json`` into
   the exact dict shape ``bench.grade.grade`` returns, so ``bench/run.py`` can
   swap graders without any other change.

   Two upstream quirks are load-bearing:

   * ``--patch_dir`` points at a **JSON object keyed by instance_id**, not a
     JSONL file and not a JSON list.  ``main()`` does
     ``preds[instance["instance_id"]]["model_patch"]`` after a plain
     ``json.load``, so a list would raise ``AttributeError: 'list' object has no
     attribute 'keys'``.  See :func:`write_predictions`.
   * The harness must be invoked with ``cwd`` = the SWE-bench-Live repo root.
     ``evaluation.py`` does ``sys.path.insert(0, os.getcwd() + "/launch")`` at
     import time and RepoLaunch bind-mounts ``$CWD/tmp`` into every container.

3. **Pre-pulling.**  RepoLaunch's ``pull_image`` calls ``docker.images.pull``
   with no platform; on this Mac that has been observed to raise ImageNotFound
   for an image that ``docker pull --platform linux/amd64`` fetches happily (the
   haystack case in ``spikes/swe-bench-live/NOTES.md``).  Its first step is a
   local ``images.get``, so :func:`ensure_image` pre-pulling makes that path
   unreachable.  Always pre-pull before grading.

HOST-ONLY ARTEFACT.  ``bench/live-instances.json`` carries the hidden grading
fields (``patch``, ``test_patch``, ``FAIL_TO_PASS``, ``PASS_TO_PASS``) and is
gitignored.  Never mount it into an agent container.
"""

from __future__ import annotations

import argparse
import ast
import collections
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "bench"

DATASET = "SWE-bench-Live/SWE-bench-Live"
SPLIT = "lite"
IMAGE_NS = "starryzhang"
INSTANCES = BENCH_DIR / "live-instances.json"
LIVE_REPO = ROOT / "spikes" / "swe-bench-live" / "SWE-bench-Live"
LIVE_PY = ROOT / "spikes" / "swe-bench-live" / ".venv" / "bin" / "python"
GRADE_DIR = ROOT / "results" / "live" / "grading"

HF_CACHE = BENCH_DIR / ".cache" / "hf"
REGISTRY_CACHE = BENCH_DIR / ".cache" / "registry-live.json"
GOLD_RESULTS = BENCH_DIR / "live-gold-results.json"

# Fields copied out of the HF row.  `test_cmds`/`log_parser` are Live-specific:
# the harness runs the instance's own command and parses with its own parser.
FIELDS = (
    "repo",
    "instance_id",
    "base_commit",
    "patch",
    "test_patch",
    "problem_statement",
    "created_at",
    "FAIL_TO_PASS",
    "PASS_TO_PASS",
    "test_cmds",
    "log_parser",
    "difficulty",
)
# Copied when the split actually has them (schema drifts between splits).
OPTIONAL_FIELDS = ("version", "hints_text", "rebuild_cmds", "print_cmds", "docker_image", "parser")
LIST_FIELDS = ("FAIL_TO_PASS", "PASS_TO_PASS")


# --------------------------------------------------------------------------- #
# naming
# --------------------------------------------------------------------------- #
def image_ref(instance_id: str) -> str:
    """Docker Hub reference for an instance's evaluation image (verified naming)."""
    return f"{IMAGE_NS}/sweb.eval.x86_64.{instance_id.replace('__', '_1776_').lower()}"


def repo_name(instance_id: str) -> str:
    """Registry repository path -- identical to :func:`image_ref` on Docker Hub."""
    return image_ref(instance_id)


# --------------------------------------------------------------------------- #
# parsing helpers (the Hub rows store several fields as repr-ish strings)
# --------------------------------------------------------------------------- #
def parse_list(value) -> list:
    """Normalise FAIL_TO_PASS / PASS_TO_PASS to a real list.

    They arrive as Python-literal-ish strings (``"['a', 'b']"`` -- single quotes,
    so ``json.loads`` alone fails).  ``ast.literal_eval`` handles that; JSON is
    the fallback for the rows that happen to be valid JSON but not valid Python
    (``true``/``null``).
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if not isinstance(value, str):
        raise ValueError(f"unexpected type {type(value).__name__} for a list field")
    text = value.strip()
    if not text:
        return []
    for loader in (ast.literal_eval, json.loads):
        try:
            parsed = loader(text)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, (list, tuple)):
            return list(parsed)
        return [parsed]
    raise ValueError(f"could not parse as a list: {text[:120]!r}")


def parse_difficulty(value) -> dict:
    """Normalise ``difficulty`` to ``{'files': int, 'hunks': int, 'lines': int}``.

    Stored as ``"{'files': 2, 'hunks': 7, 'lines': 26}"`` -- again Python repr,
    not JSON.  Anything unparseable becomes ``{}`` so selection can bucket it as
    ``unknown`` rather than crashing the whole fetch.
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str):
        return {}
    text = value.strip()
    if not text:
        return {}
    for loader in (ast.literal_eval, json.loads):
        try:
            parsed = loader(text)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def to_iso(value) -> str:
    """``created_at`` is a datetime object in this dataset (a string elsewhere)."""
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


# --------------------------------------------------------------------------- #
# fetch
# --------------------------------------------------------------------------- #
def _configure_hf_cache() -> None:
    HF_CACHE.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(HF_CACHE))
    os.environ.setdefault("HF_DATASETS_CACHE", str(HF_CACHE / "datasets"))


def to_records(ds) -> list[dict]:
    available = set(getattr(ds, "column_names", []) or [])
    missing = [f for f in FIELDS if available and f not in available]
    if missing:
        print(f"[live] WARNING: split lacks fields {missing}; filling with defaults")
    extras = [f for f in OPTIONAL_FIELDS if f in available]

    records = []
    for row in ds:
        rec = {}
        for field in FIELDS:
            value = row.get(field)
            if field in LIST_FIELDS:
                rec[field] = parse_list(value)
            elif field == "difficulty":
                rec[field] = parse_difficulty(value)
            elif field == "created_at":
                rec[field] = to_iso(value)
            elif field == "test_cmds":
                rec[field] = list(value) if isinstance(value, (list, tuple)) else ([] if value in (None, "") else [value])
            else:
                rec[field] = "" if value is None else value
        for field in extras:
            rec[field] = row.get(field)
        records.append(rec)
    records.sort(key=lambda r: r["instance_id"])
    return records


def print_stats(records: list[dict]) -> None:
    print(f"\n[live] total instances: {len(records)}")
    repos = collections.Counter(r["repo"] for r in records)
    print(f"\n[live] top 12 repos by count (of {len(repos)} repos):")
    for name, count in repos.most_common(12):
        print(f"  {name:36} {count:4d}  ({100 * count / len(records):5.1f}%)")

    dates = sorted(d for d in (r["created_at"] for r in records) if d)
    if dates:
        print(f"\n[live] created_at range: {dates[0]} .. {dates[-1]}")
    months = collections.Counter(d[:7] for d in dates)
    if months:
        print(f"[live] months covered: {len(months)} ({min(months)} .. {max(months)})")

    lines = [r["difficulty"].get("lines") for r in records if isinstance(r.get("difficulty"), dict)]
    have = [n for n in lines if isinstance(n, int)]
    print(f"[live] difficulty parsed for {len(have)}/{len(records)} instances")
    if have:
        have.sort()
        print(f"  patch lines: min {have[0]}  median {have[len(have) // 2]}  max {have[-1]}")

    empty = sum(1 for r in records if not r["FAIL_TO_PASS"])
    if empty:
        print(f"\n[live] WARNING: {empty} instances have an empty FAIL_TO_PASS")


def fetch(out: Path | str = INSTANCES, split: str = SPLIT, dataset: str = DATASET) -> int:
    """Materialise the split as a JSON list sorted by instance_id.  Returns the count."""
    from datasets import load_dataset

    _configure_hf_cache()
    print(f"[live] loading {dataset} split={split} ...", flush=True)
    ds = load_dataset(dataset, split=split, cache_dir=str(HF_CACHE / "datasets"))
    records = to_records(ds)

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, indent=1, sort_keys=True) + "\n")
    print(f"\n[live] source: {dataset} (split={split})")
    print(f"[live] wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
    print_stats(records)
    print(
        "\n[live] REMINDER: this file is HOST-ONLY and gitignored. It contains the hidden\n"
        "       fields (patch, test_patch, FAIL_TO_PASS, PASS_TO_PASS). Never mount it\n"
        "       into an agent container."
    )
    return len(records)


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def load_instances(path: Path | str = INSTANCES) -> list[dict]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `python -m bench.live fetch` first")
    records = json.loads(path.read_text())
    return sorted(records, key=lambda r: r["instance_id"])


def load_instance(instance_id: str, path: Path | str = INSTANCES) -> dict:
    for rec in load_instances(path):
        if rec["instance_id"] == instance_id:
            return rec
    raise KeyError(
        f"instance {instance_id!r} not in {path} (split={SPLIT}); "
        f"check the id or re-run `python -m bench.live fetch`"
    )


# --------------------------------------------------------------------------- #
# registry (Docker Hub v2, stdlib only)
# --------------------------------------------------------------------------- #
AUTH_HOST = "auth.docker.io"
REGISTRY_HOST = "registry-1.docker.io"
HUB_API = "https://hub.docker.com/v2/namespaces/{ns}/repositories/{repo}/tags/{tag}"
TAG = "latest"
TIMEOUT = 20
ATTEMPTS = 2  # one try plus one retry

MANIFEST_ACCEPT = ", ".join(
    [
        "application/vnd.docker.distribution.manifest.v2+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.oci.image.index.v1+json",
    ]
)

_cache_lock = threading.Lock()


def _get(url: str, headers: dict[str, str]) -> tuple[int, bytes | None]:
    """(status, body).  HTTP errors come back as statuses; transport failures as 0."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:  # pragma: no cover - body is best effort
            body = None
        return exc.code, body
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, None


def _anon_token(name: str) -> str | None:
    url = f"https://{AUTH_HOST}/token?service=registry.docker.io&scope=repository:{name}:pull"
    status, body = _get(url, {"Accept": "application/json"})
    if status != 200 or not body:
        return None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    return payload.get("token") or payload.get("access_token")


def _probe_registry(instance_id: str) -> bool | None:
    """Registry v2 pull probe.  True/False are definitive; None means 'unknown'.

    Docker Hub hands anonymous callers a token for repositories that do not
    exist, so the verdict comes from the manifest GET: 200 is a hit, 401/403/404
    is a miss (Hub reports "missing" as 401 UNAUTHORIZED, verified by probe).

    This is the authoritative "can I pull this anonymously" check, but it is
    **rate limited to 100 manifest requests per hour per IP** (verified: the
    429 response carries ``ratelimit-limit: 100;w=3600``).  A 300-instance sweep
    blows through that in one go, so :func:`_probe` only reaches here when the
    cheap Hub API probe is inconclusive.
    """
    name = repo_name(instance_id)
    token = _anon_token(name)
    if token is None:
        return None  # token endpoint unreachable: unknown, never cached
    headers = {"Authorization": f"Bearer {token}", "Accept": MANIFEST_ACCEPT}
    status, _ = _get(f"https://{REGISTRY_HOST}/v2/{name}/manifests/{TAG}", headers)
    if status == 200:
        return True
    if status in (401, 403, 404):
        return False
    return None  # 429 (rate limited) and 5xx land here: unknown, never cached


def _probe_hub(instance_id: str) -> bool | None:
    """Docker Hub web API probe: cheap, and on a far looser rate limit.

    ``GET /v2/namespaces/<ns>/repositories/<repo>/tags/latest`` returns 200 with
    the tag's manifest metadata (including ``architecture``) or 404 ``object not
    found``.  Verified against a known-present and a known-absent repository.
    """
    ns, _, repo = repo_name(instance_id).partition("/")
    status, _ = _get(HUB_API.format(ns=ns, repo=repo, tag=TAG), {"Accept": "application/json"})
    if status == 200:
        return True
    if status == 404:
        return False
    return None


def _probe(instance_id: str) -> bool | None:
    """One attempt.  True/False are definitive; None means 'unknown, retry'."""
    result = _probe_hub(instance_id)
    if result is not None:
        return result
    return _probe_registry(instance_id)


def _resolve(instance_id: str) -> bool | None:
    for _ in range(ATTEMPTS):
        result = _probe(instance_id)
        if result is not None:
            return result
    return None


def _load_cache() -> dict[str, bool]:
    if not REGISTRY_CACHE.exists():
        return {}
    try:
        data = json.loads(REGISTRY_CACHE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: bool(v) for k, v in data.items() if isinstance(v, bool)}


def _save_cache(cache: dict[str, bool]) -> None:
    REGISTRY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY_CACHE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(dict(sorted(cache.items())), indent=1) + "\n")
    tmp.replace(REGISTRY_CACHE)


def image_exists(instance_id: str, use_cache: bool = True) -> bool:
    """True if the Live evaluation image for ``instance_id`` is pullable."""
    if use_cache:
        with _cache_lock:
            cached = _load_cache().get(instance_id)
        if cached is not None:
            return cached
    result = _resolve(instance_id)
    if result is None:
        return False  # unknown (network trouble): never cached, never claimed
    if use_cache:
        with _cache_lock:
            cache = _load_cache()
            cache[instance_id] = result
            _save_cache(cache)
    return result


def check_many(
    instance_ids,
    workers: int = 8,
    use_cache: bool = True,
    progress: bool = False,
) -> dict[str, bool]:
    """Concurrently check many ids.  ``{instance_id: exists}``, order preserved.

    Only definitive results are persisted, so a transient outage cannot poison a
    later selection.
    """
    ids = list(dict.fromkeys(instance_ids))
    cache = _load_cache() if use_cache else {}
    results: dict[str, bool] = {}
    todo = []
    for iid in ids:
        if use_cache and iid in cache:
            results[iid] = cache[iid]
        else:
            todo.append(iid)

    if todo:
        if progress:
            print(
                f"[live] {len(results)} cached, probing {len(todo)} images with {workers} workers ...",
                flush=True,
            )
        fresh: dict[str, bool] = {}
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            for iid, ok in zip(todo, pool.map(_resolve, todo)):
                results[iid] = bool(ok)
                if ok is not None:
                    fresh[iid] = ok
        if use_cache and fresh:
            with _cache_lock:
                merged = _load_cache()
                merged.update(fresh)
                _save_cache(merged)
    return {iid: results[iid] for iid in ids}


def split_negatives(results: dict[str, bool]) -> tuple[list[str], list[str]]:
    """Split the False verdicts into (definitely missing, inconclusive).

    Relies on the cache invariant: only definitive results are ever persisted,
    so a False that is *not* in the cache was an unknown (rate limit, outage)
    downgraded to False by :func:`check_many`, not a real absence.
    """
    cache = _load_cache()
    missing, unknown = [], []
    for iid, ok in results.items():
        if ok:
            continue
        (missing if cache.get(iid) is False else unknown).append(iid)
    return sorted(missing), sorted(unknown)


# --------------------------------------------------------------------------- #
# docker
# --------------------------------------------------------------------------- #
def _sh(cmd: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def ensure_image(instance_id: str, pull: bool = True) -> bool:
    """Make the Live image present locally.  Pre-pulling is mandatory before grading.

    RepoLaunch's own ``pull_image`` does ``images.get`` then a platform-less
    ``images.pull``; the pull has been observed to report ImageNotFound on this
    Mac for an image that exists.  A successful ``images.get`` short-circuits
    that, so we always pull here with an explicit ``--platform linux/amd64``.
    """
    ref = image_ref(instance_id)
    if _sh(["docker", "image", "inspect", ref]).returncode == 0:
        return True
    if not pull:
        return False
    r = _sh(["docker", "pull", "--platform", "linux/amd64", ref], timeout=1800)
    return r.returncode == 0


# --------------------------------------------------------------------------- #
# grading (delegate to the upstream harness)
# --------------------------------------------------------------------------- #
def write_predictions(preds_path: Path, rows: list[dict]) -> Path:
    """Write the harness's predictions file.

    UPSTREAM FORMAT, verified in ``evaluation/evaluation.py::main``::

        preds = json.load(f)                                 # plain json.load
        ... instance["instance_id"] in preds.keys() ...      # a dict, not a list
        instance["pred_patch"] = preds[iid]["model_patch"]

    So the file is a **JSON object keyed by instance_id** whose values carry
    ``model_patch``.  A JSONL file or a JSON list both crash it.  The extra
    ``instance_id`` / ``model_name_or_path`` keys are ignored by the harness but
    kept so the file is also a valid SWE-bench predictions record.
    """
    payload = {row["instance_id"]: row for row in rows}
    preds_path.parent.mkdir(parents=True, exist_ok=True)
    preds_path.write_text(json.dumps(payload, indent=1) + "\n")
    return preds_path


def _harness_env() -> dict[str, str]:
    env = dict(os.environ)
    env["DOCKER_DEFAULT_PLATFORM"] = "linux/amd64"
    # Share the rig's HF cache so the harness does not re-download the split.
    env.setdefault("HF_HOME", str(HF_CACHE))
    env.setdefault("HF_DATASETS_CACHE", str(HF_CACHE / "datasets"))
    return env


def _harness_cmd(instance_ids: list[str], patch_dir: str, output_dir: Path, workers: int) -> list[str]:
    return [
        str(LIVE_PY),
        "-m",
        "evaluation.evaluation",
        "--dataset",
        DATASET,
        "--split",
        SPLIT,
        "--instance_ids",
        *instance_ids,
        "--platform",
        "linux",
        "--patch_dir",
        patch_dir,
        "--output_dir",
        str(output_dir),
        "--workers",
        str(workers),
        "--overwrite",
        "1",
    ]


def _read_report(output_dir: Path, instance_id: str) -> dict | None:
    path = output_dir / instance_id / "report.json"
    if not path.exists():
        return None
    try:
        report = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return report if isinstance(report, dict) else None


def _tally(section) -> tuple[int, int]:
    if not isinstance(section, dict):
        return 0, 0
    ok = len(section.get("success") or [])
    bad = len(section.get("failure") or [])
    return ok, ok + bad


def grade_live(
    instance_id: str,
    model_patch: str | None,
    run_id: str,
    timeout: int = 1800,
    pull: bool = True,
    model_name: str = "harness-lab",
) -> dict:
    """Grade one patch with the SWE-bench-Live harness.

    Returns the same dict shape as :func:`bench.grade.grade` so ``bench/run.py``
    can use either grader interchangeably::

        patch_is_None, patch_exists, patch_successfully_applied, resolved,
        infra_failure, infra_failure_reason, instance_id, run_id, wall_s,
        f2p "x/y", p2p "x/y"

    Artefacts land in ``results/live/grading/<run_id>/``: ``preds.json``,
    ``harness.log`` (merged stdout+stderr), ``results.json``, and per-instance
    ``<instance_id>/{report.json,status.json,post_patch_log.txt}``.
    """
    started = time.time()
    out_dir = GRADE_DIR / run_id
    patch_text = model_patch or ""
    result = {
        "patch_is_None": model_patch is None,
        "patch_exists": bool(patch_text.strip()),
        "patch_successfully_applied": False,
        "resolved": False,
        "infra_failure": False,
        "infra_failure_reason": None,
        "instance_id": instance_id,
        "run_id": run_id,
        "wall_s": 0.0,
        "f2p": "0/0",
        "p2p": "0/0",
    }

    # Empty patch: never invoke the harness.  Upstream would skip the instance
    # ("Empty patch...") and write no report, which we would then have to call
    # an infra failure -- which it is not.
    if not result["patch_exists"]:
        result["wall_s"] = round(time.time() - started, 1)
        return result

    out_dir.mkdir(parents=True, exist_ok=True)
    preds_path = out_dir / "preds.json"
    write_predictions(
        preds_path,
        [{"instance_id": instance_id, "model_name_or_path": model_name, "model_patch": patch_text}],
    )
    log_path = out_dir / "harness.log"

    try:
        if not ensure_image(instance_id, pull=pull):
            raise RuntimeError(f"image not available: {image_ref(instance_id)}")
        cmd = _harness_cmd([instance_id], str(preds_path), out_dir, workers=1)
        with open(log_path, "wb") as fh:
            fh.write(f"$ {' '.join(cmd)}\n\n".encode())
            fh.flush()
            proc = subprocess.run(
                cmd, cwd=str(LIVE_REPO), env=_harness_env(),
                stdout=fh, stderr=subprocess.STDOUT, timeout=timeout,
            )
        if proc.returncode != 0:
            raise RuntimeError(f"harness exited {proc.returncode} (see {log_path})")
    except subprocess.TimeoutExpired:
        result["infra_failure"] = True
        result["infra_failure_reason"] = f"harness timeout after {timeout}s"
    except Exception as exc:  # infra failure: record, never raise past the batch
        result["infra_failure"] = True
        result["infra_failure_reason"] = f"{type(exc).__name__}: {exc}"

    report = _read_report(out_dir, instance_id)
    if report is None:
        result["infra_failure"] = True
        result["infra_failure_reason"] = result["infra_failure_reason"] or (
            f"no report.json at {out_dir / instance_id / 'report.json'}"
        )
    else:
        f2p_ok, f2p_total = _tally(report.get("FAIL_TO_PASS"))
        p2p_ok, p2p_total = _tally(report.get("PASS_TO_PASS"))
        result["resolved"] = bool(report.get("resolved"))
        result["f2p"] = f"{f2p_ok}/{f2p_total}"
        result["p2p"] = f"{p2p_ok}/{p2p_total}"
        # The Live harness has NO separate patch-apply flag: `container.apply_patch`
        # is best-effort and its outcome never reaches report.json.  The closest
        # honest proxy is "the test command ran and produced parseable results",
        # i.e. at least one F2P/P2P test was classified.  A patch that failed to
        # apply usually leaves F2P failing (0 successes) but still tallied, so
        # this flag is weaker than the Verified one -- read it as "the harness
        # got far enough to score tests", not as "git apply succeeded".
        result["patch_successfully_applied"] = (f2p_total + p2p_total) > 0
        if result["resolved"]:
            result["infra_failure"] = False
            result["infra_failure_reason"] = None

    result["wall_s"] = round(time.time() - started, 1)
    return result


def gold_validate(
    instance_ids,
    out_json: Path | str,
    workers: int = 2,
    timeout: int = 1800,
    run_id: str | None = None,
    pull: bool = True,
) -> dict[str, bool]:
    """Run the gold patch for many instances in ONE harness invocation.

    Environment validation, exactly as for Verified: an instance whose own gold
    patch does not resolve has environment-bound tests and must be excluded from
    the subset.  Merges ``{instance_id: resolved}`` into ``out_json`` (same merge
    semantics as ``bench/grade.py --out``) and returns the full mapping for the
    ids requested.  An instance with no report counts as False and is listed.
    """
    ids = sorted(dict.fromkeys(instance_ids))
    if not ids:
        return {}
    run_id = run_id or "gold-" + time.strftime("%Y%m%dT%H%M%S")
    out_dir = GRADE_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "harness.log"

    # Pre-pull first, 2 at a time: RepoLaunch's own pull is unreliable here, and
    # serialising the pulls keeps the emulated daemon from thrashing.
    print(f"[live] pre-pulling {len(ids)} images (2 at a time) ...", flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pulled = dict(zip(ids, pool.map(lambda i: ensure_image(i, pull=pull), ids)))
    missing = [i for i, ok in pulled.items() if not ok]
    if missing:
        print(f"[live] WARNING: {len(missing)} images could not be pulled: {', '.join(missing[:10])}")

    cmd = _harness_cmd(ids, "gold", out_dir, workers=workers)
    print(f"[live] gold harness: {len(ids)} instances, {workers} workers -> {log_path}", flush=True)
    started = time.time()
    try:
        with open(log_path, "wb") as fh:
            fh.write(f"$ {' '.join(cmd)}\n\n".encode())
            fh.flush()
            subprocess.run(
                cmd, cwd=str(LIVE_REPO), env=_harness_env(),
                stdout=fh, stderr=subprocess.STDOUT, timeout=timeout,
            )
    except subprocess.TimeoutExpired:
        print(f"[live] WARNING: gold harness timed out after {timeout}s; scoring whatever landed")

    results: dict[str, bool] = {}
    no_report: list[str] = []
    for iid in ids:
        report = _read_report(out_dir, iid)
        if report is None:
            no_report.append(iid)
            results[iid] = False
        else:
            results[iid] = bool(report.get("resolved"))

    passing = sum(results.values())
    print(f"\n[live] gold: {passing}/{len(ids)} resolved in {time.time() - started:.0f}s")
    if no_report:
        print(f"[live] no report ({len(no_report)}): {', '.join(no_report)}")
    failed = [i for i, ok in results.items() if not ok and i not in no_report]
    if failed:
        print(f"[live] gold failed ({len(failed)}): {', '.join(failed)}")

    outp = Path(out_json)
    outp.parent.mkdir(parents=True, exist_ok=True)
    merged = {}
    if outp.exists():
        try:
            merged = json.loads(outp.read_text())
        except json.JSONDecodeError:
            merged = {}
    merged.update({k: bool(v) for k, v in results.items()})
    outp.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
    print(f"[live] merged {len(results)} results into {outp}")
    return results


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _ids_from(value: str) -> list[str]:
    path = Path(value)
    if path.exists():
        text = path.read_text()
        if text.lstrip().startswith("["):
            data = json.loads(text)
            return [d["instance_id"] if isinstance(d, dict) else str(d) for d in data]
        if text.lstrip().startswith("{"):
            data = json.loads(text)
            for key in ("candidates", "train", "instance_ids"):
                if key in data:
                    return list(data[key])
            return sorted(data)
        return [line.strip() for line in text.splitlines() if line.strip()]
    return [s.strip() for s in value.split(",") if s.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bench.live", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("fetch", help="download the split to bench/live-instances.json")
    p.add_argument("--out", default=str(INSTANCES))
    p.add_argument("--split", default=SPLIT)

    p = sub.add_parser("check", help="check Docker Hub image availability")
    p.add_argument("--ids", help="comma-separated ids, or a file of ids")
    p.add_argument("--all", action="store_true", help="every instance in live-instances.json")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--no-cache", action="store_true")

    p = sub.add_parser("pull", help="docker pull the evaluation images")
    p.add_argument("--ids", required=True)
    p.add_argument("--workers", type=int, default=2)

    p = sub.add_parser("gold", help="gold-patch environment validation")
    p.add_argument("--ids-file", required=True)
    p.add_argument("--out", default=str(GOLD_RESULTS))
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--run-id", default=None)

    p = sub.add_parser("grade", help="grade one patch")
    p.add_argument("--instance", required=True)
    p.add_argument("--patch", required=True, help="path to a diff, or 'gold'")
    p.add_argument("--run-id", default=None)
    p.add_argument("--timeout", type=int, default=1800)

    p = sub.add_parser("image-ref", help="print the Docker Hub image reference for an id")
    p.add_argument("instance_id")

    args = ap.parse_args(argv)

    if args.cmd == "fetch":
        fetch(out=args.out, split=args.split)
        return 0

    if args.cmd == "image-ref":
        print(image_ref(args.instance_id))
        return 0

    if args.cmd == "check":
        if args.all:
            instances = load_instances()
            ids = [i["instance_id"] for i in instances]
        elif args.ids:
            instances = None
            ids = _ids_from(args.ids)
        else:
            ap.error("check needs --ids or --all")
        results = check_many(ids, workers=args.workers, use_cache=not args.no_cache, progress=True)
        have = sum(results.values())
        print(f"\n[live] {have}/{len(ids)} instances have an image")
        if args.all:
            by_repo: dict[str, list[int]] = {}
            for inst in instances:
                row = by_repo.setdefault(inst["repo"], [0, 0])
                row[0] += 1 if results.get(inst["instance_id"]) else 0
                row[1] += 1
            print(f"\n{'repo':36} {'have':>5} {'total':>6}  pct")
            for repo, (got, total) in sorted(by_repo.items(), key=lambda kv: (-kv[1][1], kv[0])):
                print(f"{repo:36} {got:5d} {total:6d}  {100 * got / total:5.1f}%")
        missing, unknown = split_negatives(results)
        if missing:
            print(f"\nmissing ({len(missing)}): {', '.join(missing[:20])}")
            if len(missing) > 20:
                print(f"  ... and {len(missing) - 20} more")
        if unknown:
            print(f"\ninconclusive ({len(unknown)}): {', '.join(unknown[:20])}")
            if len(unknown) > 20:
                print(f"  ... and {len(unknown) - 20} more")
            print("  these were NOT cached; re-run to retry (Docker Hub's anonymous")
            print("  registry limit is 100 manifest pulls/hour/IP)")
        return 0

    if args.cmd == "pull":
        ids = _ids_from(args.ids)
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            results = dict(zip(ids, pool.map(ensure_image, ids)))
        for iid, ok in results.items():
            print(f"{'ok  ' if ok else 'FAIL'} {iid}  {image_ref(iid)}")
        print(f"\n[live] pulled {sum(results.values())}/{len(ids)}")
        return 0 if all(results.values()) else 1

    if args.cmd == "gold":
        ids = _ids_from(args.ids_file)
        gold_validate(ids, args.out, workers=args.workers, timeout=args.timeout, run_id=args.run_id)
        return 0

    if args.cmd == "grade":
        if args.patch == "gold":
            patch = load_instance(args.instance)["patch"]
        else:
            patch = Path(args.patch).read_text()
        run_id = args.run_id or "grade-" + time.strftime("%Y%m%dT%H%M%S")
        report = grade_live(args.instance, patch, run_id, timeout=args.timeout)
        print(json.dumps(report, indent=1))
        return 0

    ap.error(f"unknown command {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
