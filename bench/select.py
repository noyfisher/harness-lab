"""Pick the benchmark subset: image-available, gold-passing, difficulty-stratified.

Selection pipeline (each stage's surviving count is recorded in the output under
``filters`` so the subset is auditable):

1. load ``bench/instances.json`` (from ``bench/fetch.py``);
2. keep instances whose Epoch AI eval image exists for ``--arch``;
3. if ``--gold-results`` is given, keep only instances the gold patch passed;
4. stratify by ``difficulty`` using the largest-remainder method so the subset
   mirrors the dataset's proportions as closely as integer rounding allows;
5. cap any single repo at ``--max-per-repo`` (SWE-bench Verified is 46% django);
6. draw with a seeded ``numpy.random.Generator``;
7. split 60/40 train/held-out, stratified by difficulty, seeded.

Determinism: every candidate pool is sorted by ``instance_id`` before sampling and
each stratum gets its own generator derived from ``(seed, crc32(difficulty))``, so
the same seed and the same inputs produce byte-identical JSON.

Usage::

    python -m bench.select --n 40 --seed 20260903
    python -m bench.select --candidates 60 --seed 20260903
    python -m bench.select --n 40 --seed 20260903 --gold-results results/gold.json
"""

from __future__ import annotations

import argparse
import collections
import json
import zlib
from pathlib import Path

import numpy as np

from . import registry

BENCH_DIR = Path(__file__).resolve().parent
INSTANCES_PATH = BENCH_DIR / "instances.json"
SUBSET_PATH = BENCH_DIR / "subset.json"
CANDIDATES_PATH = BENCH_DIR / "candidates.json"

TRAIN_FRACTION = 0.6
DEFAULT_SEED = 20260903


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def load_instances(path=INSTANCES_PATH) -> list[dict]:
    records = json.loads(Path(path).read_text())
    return sorted(records, key=lambda r: r["instance_id"])


def _rng(seed: int, *tags) -> np.random.Generator:
    """Generator keyed by seed plus stable tags (crc32, not salted hash())."""
    key = [int(seed)]
    for tag in tags:
        key.append(zlib.crc32(str(tag).encode()) if isinstance(tag, str) else int(tag))
    return np.random.default_rng(key)


def largest_remainder(counts: dict[str, int], total: int) -> dict[str, int]:
    """Apportion ``total`` across strata in proportion to ``counts``.

    Hamilton / largest-remainder: floor the exact quotas, then hand the leftover
    seats to the largest fractional remainders.  Ties break on stratum name so
    the result is deterministic.  Never allocates more than a stratum has.
    """
    pool = sum(counts.values())
    if pool <= 0 or total <= 0:
        return {k: 0 for k in counts}
    total = min(total, pool)

    exact = {k: total * v / pool for k, v in counts.items()}
    alloc = {k: min(int(v), counts[k]) for k, v in exact.items()}
    remaining = total - sum(alloc.values())

    order = sorted(counts, key=lambda k: (-(exact[k] - int(exact[k])), k))
    while remaining > 0:
        progressed = False
        for name in order:
            if remaining == 0:
                break
            if alloc[name] < counts[name]:
                alloc[name] += 1
                remaining -= 1
                progressed = True
        if not progressed:  # every stratum exhausted
            break
    return alloc


def _draw_stratum(pool: list[dict], quota: int, cap: int, repo_counts, rng) -> list[dict]:
    """Take up to ``quota`` from ``pool`` honouring the global per-repo cap."""
    if quota <= 0 or not pool:
        return []
    order = rng.permutation(len(pool))
    picked = []
    for idx in order:
        if len(picked) >= quota:
            break
        inst = pool[int(idx)]
        if cap is not None and repo_counts[inst["repo"]] >= cap:
            continue
        picked.append(inst)
        repo_counts[inst["repo"]] += 1
    return picked


def stratified_sample(
    instances: list[dict],
    n: int,
    seed: int,
    max_per_repo: int | None = None,
    strat_key: str = "difficulty",
) -> list[dict]:
    """Draw ``n`` instances, difficulty-stratified and repo-capped, deterministically.

    If the repo cap starves a stratum, the unfilled seats are redistributed to the
    other strata (largest pool first) so the subset still reaches ``n`` when the
    caps mathematically allow it.  Returned list is sorted by instance_id.
    """
    instances = sorted(instances, key=lambda r: r["instance_id"])
    if n <= 0 or not instances:
        return []

    by_strat: dict[str, list[dict]] = collections.defaultdict(list)
    for inst in instances:
        by_strat[inst.get(strat_key, "unknown")].append(inst)

    counts = {k: len(v) for k, v in by_strat.items()}
    quotas = largest_remainder(counts, n)

    repo_counts: collections.Counter = collections.Counter()
    picked: dict[str, list[dict]] = {}
    taken: set[str] = set()
    for name in sorted(by_strat):
        got = _draw_stratum(by_strat[name], quotas[name], max_per_repo, repo_counts, _rng(seed, name))
        picked[name] = got
        taken.update(i["instance_id"] for i in got)

    # Redistribute seats the repo cap made unfillable.
    shortfall = n - sum(len(v) for v in picked.values())
    while shortfall > 0:
        remaining = {
            name: [i for i in by_strat[name] if i["instance_id"] not in taken]
            for name in sorted(by_strat)
        }
        eligible = {
            name: [i for i in pool if max_per_repo is None or repo_counts[i["repo"]] < max_per_repo]
            for name, pool in remaining.items()
        }
        if not any(eligible.values()):
            break
        # Fill from the largest eligible pool first, preserving proportions as
        # well as the caps permit.
        extra = largest_remainder({k: len(v) for k, v in eligible.items()}, shortfall)
        progressed = False
        for name in sorted(eligible):
            got = _draw_stratum(
                eligible[name], extra[name], max_per_repo, repo_counts, _rng(seed, name, len(taken))
            )
            if got:
                progressed = True
                picked[name].extend(got)
                taken.update(i["instance_id"] for i in got)
        if not progressed:
            break
        shortfall = n - sum(len(v) for v in picked.values())

    selected = [inst for name in sorted(picked) for inst in picked[name]]
    return sorted(selected, key=lambda r: r["instance_id"])


def split_train_heldout(
    selected: list[dict],
    seed: int,
    train_fraction: float = TRAIN_FRACTION,
    strat_key: str = "difficulty",
) -> tuple[list[str], list[str]]:
    """Stratified, seeded 60/40 split.  Returns (train_ids, heldout_ids), sorted."""
    selected = sorted(selected, key=lambda r: r["instance_id"])
    by_strat: dict[str, list[dict]] = collections.defaultdict(list)
    for inst in selected:
        by_strat[inst.get(strat_key, "unknown")].append(inst)

    counts = {k: len(v) for k, v in by_strat.items()}
    train_total = int(round(train_fraction * len(selected)))
    train_quotas = largest_remainder(counts, train_total)

    train, heldout = [], []
    for name in sorted(by_strat):
        pool = by_strat[name]
        order = _rng(seed, name, "split").permutation(len(pool))
        want = train_quotas[name]
        for rank, idx in enumerate(order):
            iid = pool[int(idx)]["instance_id"]
            (train if rank < want else heldout).append(iid)
    return sorted(train), sorted(heldout)


def _counter(instances, key) -> dict[str, int]:
    return dict(sorted(collections.Counter(i[key] for i in instances).items()))


# --------------------------------------------------------------------------- #
# pipeline
# --------------------------------------------------------------------------- #
def filter_available(instances, arch, workers=16, check=None, verbose=True):
    """Keep instances with an Epoch eval image; print availability per repo."""
    check = check or registry.check_many
    ids = sorted(i["instance_id"] for i in instances)
    results = check(ids, arch, workers)
    kept = [i for i in instances if results.get(i["instance_id"])]

    if verbose:
        print(f"[select] {arch} images available: {len(kept)}/{len(instances)}")
        by_repo: dict[str, list[int]] = {}
        for inst in instances:
            row = by_repo.setdefault(inst["repo"], [0, 0])
            row[0] += 1 if results.get(inst["instance_id"]) else 0
            row[1] += 1
        print(f"  {'repo':32} {'have':>5} {'total':>6}   pct")
        for repo, (got, total) in sorted(by_repo.items(), key=lambda kv: (-kv[1][1], kv[0])):
            print(f"  {repo:32} {got:5d} {total:6d}  {100 * got / total:5.1f}%")
    return kept


def filter_gold(instances, gold_path, verbose=True):
    gold = json.loads(Path(gold_path).read_text())
    kept = [i for i in instances if gold.get(i["instance_id"]) is True]
    if verbose:
        print(f"[select] gold-passing: {len(kept)}/{len(instances)} (from {gold_path})")
    return kept


def build(
    instances,
    n,
    seed,
    arch="arm64",
    max_per_repo=8,
    gold_results=None,
    workers=16,
    check=None,
    split=True,
    verbose=True,
):
    """Run the full pipeline and return the output dict (also used by tests)."""
    filters = {"loaded": len(instances)}

    available = filter_available(instances, arch, workers, check=check, verbose=verbose)
    filters["image_available"] = len(available)

    if gold_results:
        available = filter_gold(available, gold_results, verbose=verbose)
    filters["gold_passing"] = len(available)
    filters["gold_results"] = str(gold_results) if gold_results else None

    selected = stratified_sample(available, n, seed, max_per_repo)
    filters["selected"] = len(selected)
    filters["max_per_repo"] = max_per_repo

    out = {
        "seed": seed,
        "n": len(selected),
        "requested_n": n,
        "arch": arch,
        "filters": filters,
        "strata": _counter(selected, "difficulty"),
        "repos": _counter(selected, "repo"),
    }
    if split:
        train, heldout = split_train_heldout(selected, seed)
        out["train"] = train
        out["heldout"] = heldout
        out["train_strata"] = _counter([i for i in selected if i["instance_id"] in set(train)], "difficulty")
        out["heldout_strata"] = _counter([i for i in selected if i["instance_id"] in set(heldout)], "difficulty")
    else:
        out["candidates"] = [i["instance_id"] for i in selected]
    return out


def _report(out, label):
    print(f"\n[select] {label}: {out['n']} instances (requested {out['requested_n']})")
    print("  by difficulty:")
    for name, count in sorted(out["strata"].items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"    {name:28} {count:3d}  ({100 * count / out['n']:5.1f}%)")
    print("  by repo:")
    for name, count in sorted(out["repos"].items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"    {name:32} {count:3d}")
    if "train" in out:
        print(f"  train {len(out['train'])} / heldout {len(out['heldout'])}")
        print(f"    train strata:   {out['train_strata']}")
        print(f"    heldout strata: {out['heldout_strata']}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--arch", default="arm64")
    parser.add_argument("--gold-results", default=None, help="JSON {instance_id: bool} from grading")
    parser.add_argument(
        "--candidates",
        type=int,
        default=None,
        metavar="K",
        help="emit K gold-validation candidates to bench/candidates.json instead of a subset",
    )
    parser.add_argument("--max-per-repo", type=int, default=8)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--instances", default=str(INSTANCES_PATH))
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    instances = load_instances(args.instances)
    print(f"[select] loaded {len(instances)} instances from {args.instances}")

    candidate_mode = args.candidates is not None
    n = args.candidates if candidate_mode else args.n
    out_path = Path(args.out) if args.out else (CANDIDATES_PATH if candidate_mode else SUBSET_PATH)

    out = build(
        instances,
        n=n,
        seed=args.seed,
        arch=args.arch,
        max_per_repo=args.max_per_repo,
        gold_results=args.gold_results,
        workers=args.workers,
        split=not candidate_mode,
    )
    out["mode"] = "candidates" if candidate_mode else "subset"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    _report(out, "candidates" if candidate_mode else "subset")
    print(f"\n[select] wrote {out_path}")
    if candidate_mode:
        print("[select] next: grade these with the gold patch, then re-run with --gold-results")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
