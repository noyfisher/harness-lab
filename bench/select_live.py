"""Pick the SWE-bench-Live benchmark subset: image-available, gold-passing, size-stratified.

Same pipeline and the same determinism guarantees as ``bench/select.py`` -- it
reuses that module's ``largest_remainder`` / ``stratified_sample`` /
``split_train_heldout`` so both benchmarks draw their subsets with identical
machinery -- with one difference: **the stratification key**.

SWE-bench Verified ships a human "difficulty" label (``<15 min fix`` ...).
SWE-bench-Live does not.  It ships ``difficulty`` as a *patch-size* dict,
``{'files': n, 'hunks': n, 'lines': n}``, so the stratum here is a bucket over
the gold patch's changed-line count:

====== ==================
bucket gold patch lines
====== ==================
small  <= 15
medium 16 .. 60
large  > 60
====== ==================

(Plus ``unknown`` for rows whose ``difficulty`` did not parse.)  Patch size is a
proxy for difficulty, not a measurement of it; the bucket definition is written
into the output so a reader can see exactly what the strata mean.

Pipeline:

1. load ``bench/live-instances.json`` (from ``python -m bench.live fetch``);
2. keep instances whose Docker Hub image exists (``bench.live.check_many``);
3. if ``--gold-results`` is given, keep only instances the gold patch resolved;
4. stratify by bucket with the largest-remainder method (preserves the split's
   proportions as closely as integer rounding allows);
5. cap any single repo at ``--max-per-repo``;
6. draw with a seeded ``numpy.random.Generator``;
7. split 60/40 train/held-out, stratified by bucket, seeded.

Usage::

    python -m bench.select_live --candidates 90 --seed 20260912
    python -m bench.select_live --n 40 --seed 20260912 --gold-results bench/live-gold-results.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import live
from .select import _counter, split_train_heldout, stratified_sample

BENCH_DIR = Path(__file__).resolve().parent
SUBSET_PATH = BENCH_DIR / "live-subset.json"
CANDIDATES_PATH = BENCH_DIR / "live-candidates.json"

DEFAULT_SEED = 20260912
DEFAULT_MAX_PER_REPO = 6
STRAT_KEY = "bucket"

# (name, inclusive lower bound, inclusive upper bound or None for open-ended)
BUCKETS = (("small", 0, 15), ("medium", 16, 60), ("large", 61, None))
BUCKET_DEF = {
    "key": "difficulty.lines (gold patch changed lines)",
    "small": "<= 15",
    "medium": "16-60",
    "large": "> 60",
    "unknown": "difficulty missing or unparseable",
}


def bucket_for(instance: dict) -> str:
    """Difficulty bucket for one instance, from ``difficulty['lines']``."""
    difficulty = instance.get("difficulty")
    lines = difficulty.get("lines") if isinstance(difficulty, dict) else None
    if not isinstance(lines, int) or isinstance(lines, bool) or lines < 0:
        return "unknown"
    for name, low, high in BUCKETS:
        if lines >= low and (high is None or lines <= high):
            return name
    return "unknown"


def annotate(instances: list[dict]) -> list[dict]:
    """Return shallow copies carrying the ``bucket`` stratum key."""
    out = []
    for inst in instances:
        rec = dict(inst)
        rec[STRAT_KEY] = bucket_for(inst)
        out.append(rec)
    return out


def filter_available(instances, workers=8, check=None, verbose=True):
    """Keep instances whose Live image exists; print availability per repo."""
    check = check or live.check_many
    ids = sorted(i["instance_id"] for i in instances)
    results = check(ids, workers)
    kept = [i for i in instances if results.get(i["instance_id"])]
    if verbose:
        print(f"[select-live] images available: {len(kept)}/{len(instances)}")
        by_repo: dict[str, list[int]] = {}
        for inst in instances:
            row = by_repo.setdefault(inst["repo"], [0, 0])
            row[0] += 1 if results.get(inst["instance_id"]) else 0
            row[1] += 1
        shown = sorted(by_repo.items(), key=lambda kv: (-kv[1][1], kv[0]))[:15]
        print(f"  {'repo':36} {'have':>5} {'total':>6}   pct")
        for repo, (got, total) in shown:
            print(f"  {repo:36} {got:5d} {total:6d}  {100 * got / total:5.1f}%")
        if len(by_repo) > len(shown):
            print(f"  ... and {len(by_repo) - len(shown)} more repos")
    return kept


def filter_gold(instances, gold_path, verbose=True):
    gold = json.loads(Path(gold_path).read_text())
    kept = [i for i in instances if gold.get(i["instance_id"]) is True]
    if verbose:
        print(f"[select-live] gold-passing: {len(kept)}/{len(instances)} (from {gold_path})")
    return kept


def build(
    instances,
    n,
    seed,
    max_per_repo=DEFAULT_MAX_PER_REPO,
    gold_results=None,
    workers=8,
    check=None,
    split=True,
    verbose=True,
):
    """Run the full pipeline and return the output dict (also used by tests)."""
    instances = annotate(instances)
    filters = {"loaded": len(instances)}

    available = filter_available(instances, workers, check=check, verbose=verbose)
    filters["image_available"] = len(available)

    if gold_results:
        available = filter_gold(available, gold_results, verbose=verbose)
    filters["gold_passing"] = len(available)
    filters["gold_results"] = str(gold_results) if gold_results else None

    selected = stratified_sample(available, n, seed, max_per_repo, strat_key=STRAT_KEY)
    filters["selected"] = len(selected)
    filters["max_per_repo"] = max_per_repo

    out = {
        "bench": "live",
        "dataset": live.DATASET,
        "split": live.SPLIT,
        "arch": "x86_64",
        "seed": seed,
        "n": len(selected),
        "requested_n": n,
        "buckets": BUCKET_DEF,
        "filters": filters,
        "strata": _counter(selected, STRAT_KEY),
        "pool_strata": _counter(instances, STRAT_KEY),
        "repos": _counter(selected, "repo"),
    }
    if split:
        train, heldout = split_train_heldout(selected, seed, strat_key=STRAT_KEY)
        train_set, heldout_set = set(train), set(heldout)
        out["train"] = train
        out["heldout"] = heldout
        out["train_strata"] = _counter([i for i in selected if i["instance_id"] in train_set], STRAT_KEY)
        out["heldout_strata"] = _counter([i for i in selected if i["instance_id"] in heldout_set], STRAT_KEY)
    else:
        out["candidates"] = [i["instance_id"] for i in selected]
    return out


def _report(out, label):
    n = max(out["n"], 1)
    print(f"\n[select-live] {label}: {out['n']} instances (requested {out['requested_n']})")
    print("  by bucket (subset / whole split):")
    pool = out.get("pool_strata", {})
    pool_total = max(sum(pool.values()), 1)
    for name, count in sorted(out["strata"].items(), key=lambda kv: (-kv[1], kv[0])):
        share = 100 * count / n
        pool_share = 100 * pool.get(name, 0) / pool_total
        print(f"    {name:10} {count:3d}  ({share:5.1f}%   split {pool_share:5.1f}%)")
    print("  by repo:")
    for name, count in sorted(out["repos"].items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"    {name:36} {count:3d}")
    if "train" in out:
        print(f"  train {len(out['train'])} / heldout {len(out['heldout'])}")
        print(f"    train strata:   {out['train_strata']}")
        print(f"    heldout strata: {out['heldout_strata']}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--candidates",
        type=int,
        default=None,
        metavar="K",
        help="emit K gold-validation candidates to bench/live-candidates.json instead of a subset",
    )
    parser.add_argument("--max-per-repo", type=int, default=DEFAULT_MAX_PER_REPO)
    parser.add_argument("--gold-results", default=None, help="JSON {instance_id: bool} from `bench.live gold`")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--instances", default=str(live.INSTANCES))
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    instances = live.load_instances(args.instances)
    print(f"[select-live] loaded {len(instances)} instances from {args.instances}")

    candidate_mode = args.candidates is not None
    n = args.candidates if candidate_mode else args.n
    out_path = Path(args.out) if args.out else (CANDIDATES_PATH if candidate_mode else SUBSET_PATH)

    out = build(
        instances,
        n=n,
        seed=args.seed,
        max_per_repo=args.max_per_repo,
        gold_results=args.gold_results,
        workers=args.workers,
        split=not candidate_mode,
    )
    out["mode"] = "candidates" if candidate_mode else "subset"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    _report(out, "candidates" if candidate_mode else "subset")
    print(f"\n[select-live] wrote {out_path}")
    if candidate_mode:
        print("[select-live] next: `python -m bench.live gold --ids-file " f"{out_path}` then re-run with --gold-results")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
