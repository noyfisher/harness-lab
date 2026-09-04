"""Unit tests for bench/select.py.  Synthetic data only -- no network, no dataset."""

from __future__ import annotations

import collections
import json

import pytest

from bench import select

# Rough shape of SWE-bench Verified: four difficulty bands, one dominant repo.
DIFFICULTIES = ["<15 min fix", "15 min - 1 hour", "1-4 hours", ">4 hours"]
DIFF_WEIGHTS = [78, 104, 16, 2]  # 200 instances total
REPOS = ["django/django", "sympy/sympy", "sphinx-doc/sphinx", "pytest-dev/pytest", "psf/requests"]
REPO_WEIGHTS = [100, 40, 30, 20, 10]


def make_instances(n_per_diff=DIFF_WEIGHTS, repo_weights=REPO_WEIGHTS) -> list[dict]:
    """Deterministic synthetic instance list with a skewed repo distribution."""
    repo_slots = []
    for repo, weight in zip(REPOS, repo_weights):
        repo_slots.extend([repo] * weight)

    instances = []
    slot = 0
    for difficulty, count in zip(DIFFICULTIES, n_per_diff):
        for i in range(count):
            repo = repo_slots[slot % len(repo_slots)]
            slot += 1
            instances.append(
                {
                    "instance_id": f"{repo.split('/')[1]}-{slot:04d}",
                    "repo": repo,
                    "difficulty": difficulty,
                    "base_commit": f"c{slot:040d}",
                }
            )
    return instances


def fake_check(available_ids):
    """Stand-in for registry.check_many restricted to ``available_ids``."""
    allowed = set(available_ids)

    def _check(instance_ids, arch="arm64", workers=16):
        return {iid: iid in allowed for iid in instance_ids}

    return _check


def counts(instances, key="difficulty"):
    return collections.Counter(i[key] for i in instances)


# --------------------------------------------------------------------------- #
# largest_remainder
# --------------------------------------------------------------------------- #
def test_largest_remainder_sums_to_total():
    alloc = select.largest_remainder({"a": 78, "b": 104, "c": 16, "d": 2}, 40)
    assert sum(alloc.values()) == 40


def test_largest_remainder_never_exceeds_pool():
    alloc = select.largest_remainder({"a": 3, "b": 100}, 50)
    assert alloc["a"] <= 3
    assert sum(alloc.values()) == 50


def test_largest_remainder_caps_at_available():
    alloc = select.largest_remainder({"a": 5, "b": 5}, 100)
    assert alloc == {"a": 5, "b": 5}


# --------------------------------------------------------------------------- #
# stratification
# --------------------------------------------------------------------------- #
def test_stratification_matches_proportions_without_cap():
    instances = make_instances()
    n = 40
    picked = select.stratified_sample(instances, n=n, seed=1234, max_per_repo=None)
    assert len(picked) == n

    expected = select.largest_remainder(dict(counts(instances)), n)
    assert dict(counts(picked)) == {k: v for k, v in expected.items() if v}


def test_stratification_proportions_are_close_to_source():
    instances = make_instances()
    n = 50
    picked = select.stratified_sample(instances, n=n, seed=7, max_per_repo=None)
    src = counts(instances)
    got = counts(picked)
    for difficulty in src:
        want = n * src[difficulty] / len(instances)
        # largest-remainder rounding can only be off by less than one seat
        assert abs(got[difficulty] - want) < 1.0


def test_sample_returns_real_instances_without_duplicates():
    instances = make_instances()
    picked = select.stratified_sample(instances, n=40, seed=99, max_per_repo=8)
    ids = [i["instance_id"] for i in picked]
    assert len(set(ids)) == len(ids)
    assert set(ids) <= {i["instance_id"] for i in instances}


def test_sample_is_sorted_by_instance_id():
    picked = select.stratified_sample(make_instances(), n=30, seed=5, max_per_repo=8)
    assert [i["instance_id"] for i in picked] == sorted(i["instance_id"] for i in picked)


def test_sample_handles_n_larger_than_pool():
    instances = make_instances()
    picked = select.stratified_sample(instances, n=1000, seed=3, max_per_repo=None)
    assert len(picked) == len(instances)


# --------------------------------------------------------------------------- #
# repo cap
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cap", [2, 5, 8])
def test_repo_cap_is_enforced(cap):
    instances = make_instances()
    picked = select.stratified_sample(instances, n=40, seed=20260903, max_per_repo=cap)
    per_repo = counts(picked, "repo")
    assert max(per_repo.values()) <= cap, per_repo


def test_repo_cap_still_fills_n_when_arithmetic_allows():
    instances = make_instances()
    cap = 8
    # 5 repos * 8 = 40 seats available, so n=40 must be reachable.
    picked = select.stratified_sample(instances, n=40, seed=42, max_per_repo=cap)
    assert len(picked) == 40
    assert max(counts(picked, "repo").values()) <= cap


def test_repo_cap_limits_total_when_impossible():
    instances = make_instances()
    cap = 3
    picked = select.stratified_sample(instances, n=100, seed=42, max_per_repo=cap)
    # 5 repos * 3 = 15 seats maximum
    assert len(picked) == 15
    assert max(counts(picked, "repo").values()) <= cap


def test_dominant_repo_is_actually_reduced():
    instances = make_instances()
    uncapped = select.stratified_sample(instances, n=40, seed=11, max_per_repo=None)
    capped = select.stratified_sample(instances, n=40, seed=11, max_per_repo=8)
    assert counts(uncapped, "repo")["django/django"] > 8
    assert counts(capped, "repo")["django/django"] == 8


# --------------------------------------------------------------------------- #
# determinism
# --------------------------------------------------------------------------- #
def test_sampling_is_deterministic_for_same_seed():
    instances = make_instances()
    a = select.stratified_sample(instances, n=40, seed=20260903, max_per_repo=8)
    b = select.stratified_sample(instances, n=40, seed=20260903, max_per_repo=8)
    assert [i["instance_id"] for i in a] == [i["instance_id"] for i in b]


def test_sampling_is_insensitive_to_input_order():
    instances = make_instances()
    shuffled = list(reversed(instances))
    a = select.stratified_sample(instances, n=40, seed=20260903, max_per_repo=8)
    b = select.stratified_sample(shuffled, n=40, seed=20260903, max_per_repo=8)
    assert [i["instance_id"] for i in a] == [i["instance_id"] for i in b]


def test_different_seeds_give_different_subsets():
    instances = make_instances()
    a = select.stratified_sample(instances, n=40, seed=1, max_per_repo=8)
    b = select.stratified_sample(instances, n=40, seed=2, max_per_repo=8)
    assert [i["instance_id"] for i in a] != [i["instance_id"] for i in b]


def test_build_output_is_byte_identical_across_calls(monkeypatch):
    instances = make_instances()
    monkeypatch.setattr(select.registry, "check_many", fake_check(i["instance_id"] for i in instances))

    first = select.build(instances, n=40, seed=20260903, max_per_repo=8, verbose=False)
    second = select.build(instances, n=40, seed=20260903, max_per_repo=8, verbose=False)
    assert json.dumps(first, sort_keys=True, indent=1) == json.dumps(second, sort_keys=True, indent=1)


# --------------------------------------------------------------------------- #
# train / held-out split
# --------------------------------------------------------------------------- #
def test_split_is_disjoint_and_covers_the_subset():
    picked = select.stratified_sample(make_instances(), n=40, seed=20260903, max_per_repo=8)
    train, heldout = select.split_train_heldout(picked, seed=20260903)
    assert set(train) & set(heldout) == set()
    assert set(train) | set(heldout) == {i["instance_id"] for i in picked}
    assert len(train) + len(heldout) == len(picked)


def test_split_is_sixty_forty():
    picked = select.stratified_sample(make_instances(), n=40, seed=20260903, max_per_repo=8)
    train, heldout = select.split_train_heldout(picked, seed=20260903)
    assert len(train) == 24
    assert len(heldout) == 16


def test_split_is_stratified_by_difficulty():
    picked = select.stratified_sample(make_instances(), n=40, seed=20260903, max_per_repo=8)
    train, heldout = select.split_train_heldout(picked, seed=20260903)
    by_id = {i["instance_id"]: i for i in picked}

    subset_counts = counts(picked)
    train_counts = counts([by_id[i] for i in train])
    expected = select.largest_remainder(dict(subset_counts), len(train))
    assert dict(train_counts) == {k: v for k, v in expected.items() if v}

    heldout_counts = counts([by_id[i] for i in heldout])
    for difficulty, total in subset_counts.items():
        assert train_counts[difficulty] + heldout_counts[difficulty] == total


def test_split_is_deterministic():
    picked = select.stratified_sample(make_instances(), n=40, seed=20260903, max_per_repo=8)
    a = select.split_train_heldout(picked, seed=20260903)
    b = select.split_train_heldout(picked, seed=20260903)
    assert a == b
    assert a[0] == sorted(a[0]) and a[1] == sorted(a[1])


# --------------------------------------------------------------------------- #
# pipeline / filters (registry mocked)
# --------------------------------------------------------------------------- #
def test_image_filter_drops_unavailable(monkeypatch):
    instances = make_instances()
    available = [i["instance_id"] for i in instances[::2]]
    monkeypatch.setattr(select.registry, "check_many", fake_check(available))

    out = select.build(instances, n=20, seed=1, max_per_repo=8, verbose=False)
    assert out["filters"]["loaded"] == len(instances)
    assert out["filters"]["image_available"] == len(available)
    assert set(out["train"]) | set(out["heldout"]) <= set(available)


def test_gold_results_filter(tmp_path, monkeypatch):
    instances = make_instances()
    monkeypatch.setattr(select.registry, "check_many", fake_check(i["instance_id"] for i in instances))

    gold_pass = {i["instance_id"]: True for i in instances[:60]}
    gold_pass.update({i["instance_id"]: False for i in instances[60:]})
    gold_path = tmp_path / "gold.json"
    gold_path.write_text(json.dumps(gold_pass))

    out = select.build(
        instances, n=20, seed=1, max_per_repo=8, gold_results=str(gold_path), verbose=False
    )
    assert out["filters"]["gold_passing"] == 60
    passing = {k for k, v in gold_pass.items() if v}
    assert set(out["train"]) | set(out["heldout"]) <= passing


def test_candidate_mode_emits_flat_list(monkeypatch):
    instances = make_instances()
    monkeypatch.setattr(select.registry, "check_many", fake_check(i["instance_id"] for i in instances))

    out = select.build(instances, n=60, seed=20260903, max_per_repo=None, split=False, verbose=False)
    assert "candidates" in out
    assert "train" not in out
    assert len(out["candidates"]) == 60
    assert out["candidates"] == sorted(out["candidates"])


def test_filters_record_every_stage(monkeypatch):
    instances = make_instances()
    monkeypatch.setattr(select.registry, "check_many", fake_check(i["instance_id"] for i in instances))
    out = select.build(instances, n=40, seed=1, max_per_repo=8, verbose=False)
    for stage in ("loaded", "image_available", "gold_passing", "selected", "max_per_repo"):
        assert stage in out["filters"]
    assert out["strata"] and out["repos"]
    assert sum(out["repos"].values()) == out["n"]
