"""Existence checks against Epoch AI's public SWE-bench evaluation image registry.

Registry facts (verified 2026-09-03 by direct HTTP probe, no docker required):

* Repository name scheme::

      ghcr.io/epoch-research/swe-bench.eval.<arch>.<instance_id>

  with ``<arch>`` in ``{arm64, x86_64}``.  Both were confirmed present for
  ``django__django-11099``.

* **Tag scheme: ``latest`` is the only tag.**  ``GET /v2/<name>/tags/list`` for
  ``epoch-research/swe-bench.eval.arm64.django__django-11099`` returns exactly
  ``{"name": "...", "tags": ["latest"]}``.  There are no per-commit or per-version
  tags, so ``image_ref()`` pins ``:latest`` and callers that need immutability
  should resolve and record the manifest digest at grading time.

* Anonymous pulls work.  Flow is the standard Docker registry v2 dance:
  ``GET https://ghcr.io/token?scope=repository:<name>:pull`` returns a bearer
  token, which is then sent to ``GET https://ghcr.io/v2/<name>/manifests/latest``
  with Accept headers for the docker v2 manifest, the OCI manifest and the OCI
  index.  A hit is HTTP 200.

* **A missing repository fails at the token endpoint with HTTP 403 ``DENIED``,
  not 404.**  ghcr.io does not distinguish "no such repository" from "not
  permitted" for anonymous callers, so 403 and 404 are both treated as "image
  does not exist".  Any other status (or a transport error) is treated as
  *unknown*: it yields ``False`` for this run but is deliberately **not** written
  to the on-disk cache, so a transient outage cannot poison future selections.

stdlib only (urllib) so the benchmark tooling has no ``requests`` dependency.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
CACHE_DIR = BENCH_DIR / ".cache"

REGISTRY_HOST = "ghcr.io"
NAMESPACE = "epoch-research"
IMAGE_PREFIX = "swe-bench.eval"
TAG = "latest"

TIMEOUT = 15
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


def repo_name(instance_id: str, arch: str = "arm64") -> str:
    """Registry repository path (no host, no tag)."""
    return f"{NAMESPACE}/{IMAGE_PREFIX}.{arch}.{instance_id}"


def image_ref(instance_id: str, arch: str = "arm64") -> str:
    """Fully qualified image reference, e.g. ``ghcr.io/epoch-research/...:latest``.

    The tag is omitted from the returned string because ``latest`` is the only
    tag published; docker resolves the bare name to ``:latest`` identically.
    """
    return f"{REGISTRY_HOST}/{repo_name(instance_id, arch)}"


def cache_path(arch: str = "arm64") -> Path:
    return CACHE_DIR / f"registry-{arch}.json"


def _load_cache(arch: str) -> dict[str, bool]:
    path = cache_path(arch)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: bool(v) for k, v in data.items() if isinstance(v, bool)}


def _save_cache(arch: str, cache: dict[str, bool]) -> None:
    path = cache_path(arch)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(dict(sorted(cache.items())), indent=1) + "\n")
    tmp.replace(path)


def _get(url: str, headers: dict[str, str]) -> tuple[int, bytes | None]:
    """Return (status, body).  HTTP error statuses come back as statuses, not
    exceptions; transport failures come back as status 0."""
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


def _anon_token(name: str) -> tuple[str | None, int]:
    url = f"https://{REGISTRY_HOST}/token?scope=repository:{name}:pull&service={REGISTRY_HOST}"
    status, body = _get(url, {"Accept": "application/json"})
    if status != 200 or not body:
        return None, status
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None, status
    token = payload.get("token") or payload.get("access_token")
    return (token, status) if token else (None, status)


def _probe(instance_id: str, arch: str) -> bool | None:
    """One attempt.  True/False are definitive; None means 'unknown, retry'."""
    name = repo_name(instance_id, arch)
    token, status = _anon_token(name)
    if token is None:
        # 403 DENIED is how ghcr reports "no such repository" to anonymous callers.
        if status in (401, 403, 404):
            return False
        return None
    status, _ = _get(
        f"https://{REGISTRY_HOST}/v2/{name}/manifests/{TAG}",
        {"Authorization": f"Bearer {token}", "Accept": MANIFEST_ACCEPT},
    )
    if status == 200:
        return True
    if status in (401, 403, 404):
        return False
    return None


def list_tags(instance_id: str, arch: str = "arm64") -> list[str]:
    """Tags published for an instance's image (empty if inaccessible)."""
    name = repo_name(instance_id, arch)
    token, _ = _anon_token(name)
    if token is None:
        return []
    status, body = _get(
        f"https://{REGISTRY_HOST}/v2/{name}/tags/list",
        {"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if status != 200 or not body:
        return []
    try:
        return list(json.loads(body).get("tags") or [])
    except json.JSONDecodeError:
        return []


def image_exists(instance_id: str, arch: str = "arm64", use_cache: bool = True) -> bool:
    """True if the Epoch eval image for ``instance_id`` on ``arch`` is pullable.

    15s timeout per HTTP call, one retry on an inconclusive result.  Results are
    memoised on disk (see :func:`cache_path`) so repeated selections are instant.
    """
    if use_cache:
        with _cache_lock:
            cached = _load_cache(arch).get(instance_id)
        if cached is not None:
            return cached

    result: bool | None = None
    for _ in range(ATTEMPTS):
        result = _probe(instance_id, arch)
        if result is not None:
            break
    if result is None:
        # Unknown (network trouble): do not persist, do not claim availability.
        return False

    if use_cache:
        with _cache_lock:
            cache = _load_cache(arch)
            cache[instance_id] = result
            _save_cache(arch, cache)
    return result


def check_many(
    instance_ids,
    arch: str = "arm64",
    workers: int = 16,
    use_cache: bool = True,
    progress: bool = False,
) -> dict[str, bool]:
    """Concurrently check many instance ids.  Returns ``{instance_id: exists}``.

    Cache hits never touch the network; only definitive results are cached, and
    the cache file is written once at the end rather than per-check.
    """
    ids = list(dict.fromkeys(instance_ids))  # de-dupe, preserve order
    cache = _load_cache(arch) if use_cache else {}
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
                f"[registry] {len(results)} cached, probing {len(todo)} "
                f"{arch} images with {workers} workers...",
                flush=True,
            )
        fresh: dict[str, bool] = {}
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            for iid, ok in zip(todo, pool.map(lambda i: _resolve(i, arch), todo)):
                results[iid] = bool(ok)
                if ok is not None:
                    fresh[iid] = ok
        if use_cache and fresh:
            with _cache_lock:
                merged = _load_cache(arch)
                merged.update(fresh)
                _save_cache(arch, merged)

    return {iid: results[iid] for iid in ids}


def _resolve(instance_id: str, arch: str) -> bool | None:
    for _ in range(ATTEMPTS):
        result = _probe(instance_id, arch)
        if result is not None:
            return result
    return None


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Check Epoch AI SWE-bench eval images.")
    parser.add_argument("--arch", default="arm64")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument(
        "--instances",
        default=str(BENCH_DIR / "instances.json"),
        help="instances.json produced by bench/fetch.py",
    )
    parser.add_argument("--tags-for", help="list published tags for one instance id and exit")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    if args.tags_for:
        print(f"{args.tags_for} ({args.arch}) tags: {list_tags(args.tags_for, args.arch)}")
        return

    instances = json.loads(Path(args.instances).read_text())
    ids = sorted(inst["instance_id"] for inst in instances)
    results = check_many(ids, args.arch, args.workers, use_cache=not args.no_cache, progress=True)

    have = sum(results.values())
    print(f"\n{args.arch}: {have}/{len(ids)} instances have an image")

    by_repo: dict[str, list[int]] = {}
    for inst in instances:
        got = 1 if results.get(inst["instance_id"]) else 0
        row = by_repo.setdefault(inst["repo"], [0, 0])
        row[0] += got
        row[1] += 1
    print(f"\n{'repo':32} {'have':>5} {'total':>6}  pct")
    for repo, (got, total) in sorted(by_repo.items(), key=lambda kv: (-kv[1][1], kv[0])):
        print(f"{repo:32} {got:5d} {total:6d}  {100 * got / total:5.1f}%")

    missing = sorted(i for i, ok in results.items() if not ok)
    if missing:
        print(f"\nmissing ({len(missing)}): {', '.join(missing[:20])}")
        if len(missing) > 20:
            print(f"  ... and {len(missing) - 20} more")


if __name__ == "__main__":
    _main()
