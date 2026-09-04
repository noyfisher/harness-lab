"""Download SWE-bench Verified and materialise it as bench/instances.json.

HOST-ONLY ARTEFACT.  instances.json carries the hidden grading fields
(``patch``, ``test_patch``, ``FAIL_TO_PASS``, ``PASS_TO_PASS``, ``hints_text``).
It is gitignored and must never be mounted into an agent container -- see
non-negotiable #1 in the plan.  Regenerate it with ``python -m bench.fetch``.

Hugging Face downloads are cached under ``bench/.cache/hf`` so nothing lands in
``~/.cache/huggingface``.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
HF_CACHE = BENCH_DIR / ".cache" / "hf"
OUT_PATH = BENCH_DIR / "instances.json"

# Both point at the same data; the SWE-bench org copy is canonical since the
# 2024 rename, princeton-nlp is the original upload and stays as a fallback.
DATASET_IDS = ("SWE-bench/SWE-bench_Verified", "princeton-nlp/SWE-bench_Verified")
SPLIT = "test"
EXPECTED_COUNT = 500

FIELDS = [
    "repo",
    "instance_id",
    "base_commit",
    "patch",
    "test_patch",
    "problem_statement",
    "hints_text",
    "created_at",
    "version",
    "FAIL_TO_PASS",
    "PASS_TO_PASS",
    "environment_setup_commit",
    "difficulty",
]
# Stored in the source dataset as strings holding a JSON list.
JSON_LIST_FIELDS = ("FAIL_TO_PASS", "PASS_TO_PASS")


def _configure_hf_cache() -> None:
    HF_CACHE.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(HF_CACHE))
    os.environ.setdefault("HF_DATASETS_CACHE", str(HF_CACHE / "datasets"))


def _parse_json_list(value):
    """Source stores these as a JSON string; normalise to a real list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"could not parse as a JSON list: {value[:120]!r}") from exc
        if not isinstance(parsed, list):
            raise ValueError(f"expected a JSON list, got {type(parsed).__name__}")
        return parsed
    raise ValueError(f"unexpected type {type(value).__name__}")


def load_split(dataset_ids=DATASET_IDS, split: str = SPLIT):
    """Load the dataset, trying each id in turn.  Returns (dataset, dataset_id)."""
    from datasets import load_dataset

    errors = []
    for dataset_id in dataset_ids:
        try:
            print(f"[fetch] loading {dataset_id} split={split} ...", flush=True)
            ds = load_dataset(dataset_id, split=split, cache_dir=str(HF_CACHE / "datasets"))
            return ds, dataset_id
        except Exception as exc:  # noqa: BLE001 - want the fallback on any failure
            print(f"[fetch] {dataset_id} failed: {type(exc).__name__}: {exc}", flush=True)
            errors.append((dataset_id, exc))
    raise RuntimeError(f"could not load any of {dataset_ids}: {errors}")


def to_records(ds) -> list[dict]:
    available = set(ds.column_names)
    missing = [f for f in FIELDS if f not in available]
    if missing:
        print(f"[fetch] WARNING: dataset lacks fields {missing}; filling with defaults")

    records = []
    for row in ds:
        rec = {}
        for field in FIELDS:
            value = row.get(field)
            if field in JSON_LIST_FIELDS:
                rec[field] = _parse_json_list(value)
            elif field == "difficulty":
                rec[field] = value if value else "unknown"
            else:
                rec[field] = "" if value is None else value
        records.append(rec)
    records.sort(key=lambda r: r["instance_id"])
    return records


def print_stats(records: list[dict]) -> None:
    print(f"\n[fetch] total instances: {len(records)}")
    if len(records) != EXPECTED_COUNT:
        print(f"[fetch] WARNING: expected {EXPECTED_COUNT} instances, got {len(records)}")

    diffs = collections.Counter(r["difficulty"] for r in records)
    print(f"\n[fetch] difficulty values ({len(diffs)} distinct):")
    for name, count in sorted(diffs.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {name:28} {count:4d}  ({100 * count / len(records):5.1f}%)")

    repos = collections.Counter(r["repo"] for r in records)
    print(f"\n[fetch] top 12 repos by count (of {len(repos)} repos):")
    for name, count in repos.most_common(12):
        print(f"  {name:32} {count:4d}  ({100 * count / len(records):5.1f}%)")

    empty_f2p = sum(1 for r in records if not r["FAIL_TO_PASS"])
    if empty_f2p:
        print(f"\n[fetch] WARNING: {empty_f2p} instances have an empty FAIL_TO_PASS")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(OUT_PATH))
    parser.add_argument("--split", default=SPLIT)
    args = parser.parse_args(argv)

    _configure_hf_cache()
    ds, dataset_id = load_split(split=args.split)
    records = to_records(ds)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, indent=1, sort_keys=True) + "\n")

    print(f"\n[fetch] source: {dataset_id} (split={args.split})")
    print(f"[fetch] hf cache: {HF_CACHE}")
    print(f"[fetch] wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
    print_stats(records)
    print(
        "\n[fetch] REMINDER: this file is HOST-ONLY and gitignored. It contains the\n"
        "        hidden fields (patch, test_patch, FAIL_TO_PASS, PASS_TO_PASS,\n"
        "        hints_text). Never mount it into an agent container."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
