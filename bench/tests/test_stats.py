"""Synthetic-data tests for bench.stats.

Everything is generated with fixed seeds; the whole module is designed to run in
well under 20 seconds (the bootstrap-coverage test uses n_boot=500).
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from bench import stats


# --- generators ------------------------------------------------------------


def _instance_ids(n: int) -> list[str]:
    return [f"inst{i:03d}" for i in range(n)]


def _run(
    condition: str,
    instance_id: str,
    repeat: int,
    outcome: str,
    *,
    resolved: bool | None = None,
    cost: float | None = 1.25,
    wall_s: float | None = 300.0,
    num_turns: int | None = 12,
    supersedes: str | None = None,
    run_id: str | None = None,
    notes: str = "",
) -> dict:
    """One manifest-shaped line (see docs/manifest-schema.md)."""
    return {
        "run_id": run_id
        or f"{condition}-{instance_id}-r{repeat}-2026-09-03T00:00:{repeat:02d}Z",
        "ts": f"2026-09-03T00:00:{repeat:02d}Z",
        "condition": condition,
        "harness_sha": None if condition == "C0" else "abc1234",
        "cli_version": "2.1.76",
        "model": "sonnet",
        "effort": "high",
        "credential": "subscription",
        "instance_id": instance_id,
        "repeat": repeat,
        "outcome": outcome,
        "resolved": resolved,
        "touched_tests": False,
        "stripped_test_hunks": 0,
        "num_turns": num_turns,
        "total_cost_usd": cost,
        "input_tokens": 1000,
        "output_tokens": 500,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "duration_ms": 300000,
        "wall_s": wall_s,
        "patch_path": None,
        "trace_path": None,
        "grade_run_id": None,
        "summary": None,
        "notes": notes,
        "supersedes": supersedes,
    }


def make_runs(
    n_instances: int,
    k: int,
    p_by_instance: dict[str, float] | None = None,
    condition: str = "C0",
    seed: int = 0,
) -> list[dict]:
    """Manifest-shaped runs with outcome resolved/unresolved ~ Bernoulli(p_i)."""
    if p_by_instance is None:
        ids = _instance_ids(n_instances)
        p_by_instance = {iid: 0.5 for iid in ids}
    else:
        ids = sorted(p_by_instance)
        assert len(ids) == n_instances, "n_instances must match p_by_instance"
    rng = np.random.default_rng(seed)
    runs: list[dict] = []
    for iid in ids:
        p = float(p_by_instance[iid])
        draws = rng.random(k) < p
        for repeat, ok in enumerate(draws):
            runs.append(
                _run(
                    condition,
                    iid,
                    repeat,
                    "resolved" if ok else "unresolved",
                    resolved=bool(ok),
                )
            )
    return runs


def make_fixed_runs(
    spec: dict[str, int], k: int, condition: str, cost: float | None = 1.25
) -> list[dict]:
    """Deterministic runs: ``spec`` maps instance_id -> number of passes."""
    runs: list[dict] = []
    for iid, passes in sorted(spec.items()):
        assert 0 <= passes <= k
        for repeat in range(k):
            ok = repeat < passes
            runs.append(
                _run(
                    condition,
                    iid,
                    repeat,
                    "resolved" if ok else "unresolved",
                    resolved=ok,
                    cost=cost,
                )
            )
    return runs


def inject_infra_runs(
    instance_ids,
    condition: str,
    outcome: str = "paused",
    n_per_instance: int = 1,
    start_repeat: int = 90,
) -> list[dict]:
    """Non-counted runs (paused / error / parse_error) to add to a manifest."""
    out: list[dict] = []
    for iid in instance_ids:
        for j in range(n_per_instance):
            out.append(
                _run(
                    condition,
                    iid,
                    start_repeat + j,
                    outcome,
                    resolved=None,
                    cost=None,
                    wall_s=5.0,
                    num_turns=None,
                    notes="usage window",
                )
            )
    return out


# --- counted / loading -----------------------------------------------------


def test_counted_follows_schema_rules():
    for outcome in ("resolved", "unresolved", "no_diff", "budget", "timeout"):
        assert stats.counted(_run("C0", "i", 0, outcome)) is True
    for outcome in ("paused", "error", "parse_error"):
        assert stats.counted(_run("C0", "i", 0, outcome)) is False
    assert stats.counted({"outcome": "something_new"}) is False
    assert stats.counted({}) is False


def test_is_pass_prefers_grading_verdict():
    assert stats.is_pass(_run("C0", "i", 0, "resolved", resolved=True))
    assert not stats.is_pass(_run("C0", "i", 0, "unresolved", resolved=False))
    # ungraded but outcome says resolved -> still a pass
    assert stats.is_pass(_run("C0", "i", 0, "resolved", resolved=None))
    assert not stats.is_pass(_run("C0", "i", 0, "no_diff", resolved=None))


def test_load_runs_supersedes_and_malformed(tmp_path, capsys):
    a = _run("C0", "i1", 0, "error", resolved=None, run_id="A")
    b = _run("C0", "i1", 0, "unresolved", resolved=False, run_id="B",
             supersedes="A")
    c = _run("C0", "i1", 0, "resolved", resolved=True, run_id="C",
             supersedes="B")
    d = _run("C0", "i2", 0, "resolved", resolved=True, run_id="D")
    orphan = _run("C0", "i3", 0, "resolved", resolved=True, run_id="E",
                  supersedes="does-not-exist")

    path = tmp_path / "runs.jsonl"
    lines = [
        json.dumps(a),
        "{not json at all",
        json.dumps(b),
        "[1, 2, 3]",
        json.dumps({"run_id": "X", "condition": "C0"}),  # missing fields
        json.dumps(c),
        "",
        json.dumps(d),
        json.dumps(orphan),
        json.dumps(d),  # duplicate run_id, no supersedes
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    runs = stats.load_runs(path)
    ids = [r["run_id"] for r in runs]
    assert ids == ["C", "D", "E"], ids
    # chain collapsed: superseded runs are gone, position preserved
    assert runs[0]["outcome"] == "resolved"

    err = capsys.readouterr().err
    assert "unparseable" in err
    assert "not a JSON object" in err
    assert "missing/invalid" in err
    assert "unknown run_id" in err
    assert "duplicate run_id" in err

    # the superseding correction is what feeds aggregation
    assert stats.per_instance(runs, "C0") == {
        "i1": (1, 1),
        "i2": (1, 1),
        "i3": (1, 1),
    }


# --- classification --------------------------------------------------------


def test_classify_boundaries():
    assert stats.classify(0, 3) == "solid_fail"
    assert stats.classify(3, 3) == "solid_pass"
    assert stats.classify(1, 3) == "flaky"
    assert stats.classify(2, 3) == "flaky"
    # k = 1: every instance is solid one way or the other
    assert stats.classify(0, 1) == "solid_fail"
    assert stats.classify(1, 1) == "solid_pass"
    with pytest.raises(ValueError):
        stats.classify(0, 0)
    with pytest.raises(ValueError):
        stats.classify(4, 3)


def test_classes_and_class_counts():
    pi = {"a": (3, 3), "b": (0, 3), "c": (1, 3), "d": (2, 3)}
    assert stats.classes(pi) == {
        "a": "solid_pass",
        "b": "solid_fail",
        "c": "flaky",
        "d": "flaky",
    }
    assert stats.class_counts(pi) == {
        "solid_pass": 1,
        "flaky": 2,
        "solid_fail": 1,
    }


# --- pass rate -------------------------------------------------------------


def test_pass_rate_is_mean_of_per_instance_rates():
    spec = {"a": 3, "b": 0, "c": 1, "d": 2}
    runs = make_fixed_runs(spec, k=3, condition="C1")
    pi = stats.per_instance(runs, "C1")
    assert pi == {"a": (3, 3), "b": (0, 3), "c": (1, 3), "d": (2, 3)}
    expected = (3 / 3 + 0 / 3 + 1 / 3 + 2 / 3) / 4
    assert stats.pass_rate(pi) == pytest.approx(expected)
    # not the same as pooling runs when k is unequal
    uneven = {"a": (1, 1), "b": (1, 4)}
    assert stats.pass_rate(uneven) == pytest.approx((1.0 + 0.25) / 2)
    assert math.isnan(stats.pass_rate({}))


# --- bootstrap -------------------------------------------------------------


def test_bootstrap_ci_is_deterministic_and_ordered():
    runs = make_runs(20, 3, None, "C0", seed=7)
    pi = stats.per_instance(runs, "C0")
    first = stats.bootstrap_ci(pi, n_boot=500, seed=3)
    second = stats.bootstrap_ci(pi, n_boot=500, seed=3)
    assert first == second
    lo, hi = first
    assert 0.0 <= lo <= stats.pass_rate(pi) <= hi <= 1.0


def test_bootstrap_ci_coverage():
    """95% instance-bootstrap CI covers mean(p_i) in >= 88% of datasets."""
    rng = np.random.default_rng(20260903)
    n_instances, k, n_datasets = 40, 3, 200
    hits = 0
    for d in range(n_datasets):
        p = rng.beta(2.0, 2.0, size=n_instances)
        truth = float(p.mean())
        p_by = {
            iid: float(p[i]) for i, iid in enumerate(_instance_ids(n_instances))
        }
        runs = make_runs(
            n_instances, k, p_by, "C0", seed=int(rng.integers(0, 2**31 - 1))
        )
        pi = stats.per_instance(runs, "C0")
        assert len(pi) == n_instances
        lo, hi = stats.bootstrap_ci(pi, n_boot=500, seed=d, alpha=0.05)
        if lo <= truth <= hi:
            hits += 1
    coverage = hits / n_datasets
    assert coverage >= 0.88, f"bootstrap coverage was only {coverage:.3f}"


# --- paired comparison -----------------------------------------------------


def _paired_fixture(n_instances: int = 20, k: int = 3, n_flip: int = 8):
    ids = _instance_ids(n_instances)
    spec_a: dict[str, int] = {}
    for i, iid in enumerate(ids):
        if i < n_flip:
            spec_a[iid] = 0            # solid_fail, the flip candidates
        elif i < n_flip + 8:
            spec_a[iid] = k            # solid_pass
        else:
            spec_a[iid] = 1            # flaky
    spec_b = dict(spec_a)
    for iid in ids[:n_flip]:
        spec_b[iid] = k                # solid_fail -> solid_pass
    return spec_a, spec_b, ids


def test_paired_compare_direction_and_transition_table():
    n_instances, k, n_flip = 20, 3, 8
    spec_a, spec_b, _ = _paired_fixture(n_instances, k, n_flip)
    runs = make_fixed_runs(spec_a, k, "C0") + make_fixed_runs(spec_b, k, "C1")

    cmp_ = stats.paired_compare(runs, "C0", "C1")
    assert cmp_["n_instances"] == n_instances
    assert cmp_["flips_up"] == 8
    assert cmp_["regressions"] == 0
    assert cmp_["wilcoxon"]["p_value"] < 0.05
    assert cmp_["wilcoxon"]["statistic"] is not None
    assert cmp_["transition_table"]["total"] == n_instances
    matrix = cmp_["transition_table"]["matrix"]
    assert sum(sum(row) for row in matrix) == n_instances
    rows = cmp_["transition_table"]["rows"]
    assert rows["solid_fail"]["solid_pass"] == 8
    assert rows["solid_pass"]["solid_pass"] == 8
    assert rows["flaky"]["flaky"] == 4
    # discordant majority pairs all favour B
    assert cmp_["discordant"]["b_only"] == 8
    assert cmp_["discordant"]["a_only"] == 0
    assert cmp_["sign_test"]["p_value"] < 0.05
    # JSON-serializable
    json.dumps(cmp_)


def test_paired_compare_reversed_direction_counts_regressions():
    n_instances, k, n_flip = 20, 3, 8
    spec_a, spec_b, _ = _paired_fixture(n_instances, k, n_flip)
    runs = make_fixed_runs(spec_a, k, "C0") + make_fixed_runs(spec_b, k, "C1")
    back = stats.paired_compare(runs, "C1", "C0")
    assert back["flips_up"] == 0
    assert back["regressions"] == 8
    assert back["discordant"]["a_only"] == 8
    assert back["discordant"]["b_only"] == 0


def test_paired_compare_zero_differences_does_not_raise():
    spec = {iid: (i % 4) for i, iid in enumerate(_instance_ids(12))}
    runs = make_fixed_runs(spec, 3, "C0") + make_fixed_runs(spec, 3, "C1")
    cmp_ = stats.paired_compare(runs, "C0", "C1")
    assert cmp_["wilcoxon"]["p_value"] == 1.0
    assert cmp_["wilcoxon"]["statistic"] is None
    assert cmp_["wilcoxon"]["note"]
    assert cmp_["flips_up"] == 0
    assert cmp_["regressions"] == 0
    assert cmp_["sign_test"]["p_value"] == 1.0
    assert cmp_["transition_table"]["total"] == 12
    json.dumps(cmp_)


def test_paired_compare_restricted_to_common_instances():
    runs = make_fixed_runs({"a": 3, "b": 0}, 3, "C0")
    runs += make_fixed_runs({"b": 3, "c": 3}, 3, "C1")
    cmp_ = stats.paired_compare(runs, "C0", "C1")
    assert cmp_["n_instances"] == 1
    assert [i["instance_id"] for i in cmp_["instances"]] == ["b"]
    assert cmp_["n_only_a"] == 1
    assert cmp_["n_only_b"] == 1


# --- infra failures --------------------------------------------------------


def test_paused_runs_excluded_from_k_and_reported_as_infra():
    spec = {"a": 3, "b": 0, "c": 2}
    runs = make_fixed_runs(spec, 3, "C1", cost=2.0)
    runs += inject_infra_runs(["a", "b"], "C1", outcome="paused")
    runs += inject_infra_runs(["c"], "C1", outcome="error")
    runs += inject_infra_runs(["c"], "C1", outcome="parse_error")

    pi = stats.per_instance(runs, "C1")
    assert pi == {"a": (3, 3), "b": (0, 3), "c": (2, 3)}
    assert all(k == 3 for _, k in pi.values())

    cost = stats.cost_summary(runs, "C1")
    assert cost["n_counted"] == 9
    assert cost["resolved_count"] == 5
    assert cost["total_cost_usd"] == pytest.approx(18.0)
    assert cost["mean_cost_per_run"] == pytest.approx(2.0)
    assert cost["cost_per_solve"] == pytest.approx(18.0 / 5)
    assert cost["mean_wall_s"] == pytest.approx(300.0)
    assert cost["mean_num_turns"] == pytest.approx(12.0)
    assert cost["infra_failures"] == {"error": 1, "parse_error": 1, "paused": 2}
    assert cost["infra_failures_total"] == 4


def test_cost_per_solve_is_none_without_solves():
    runs = make_fixed_runs({"a": 0, "b": 0}, 2, "C0", cost=1.0)
    cost = stats.cost_summary(runs, "C0")
    assert cost["resolved_count"] == 0
    assert cost["cost_per_solve"] is None
    assert cost["total_cost_usd"] == pytest.approx(4.0)


# --- report / summarize / CLI ----------------------------------------------


def test_report_mentions_conditions_and_pass_rate():
    spec_a, spec_b, _ = _paired_fixture()
    runs = make_fixed_runs(spec_a, 3, "C0") + make_fixed_runs(spec_b, 3, "C1")
    runs += inject_infra_runs(["inst000"], "C0", outcome="paused")
    text = stats.report(runs, ["C0", "C1"], n_boot=200, seed=0)
    assert isinstance(text, str)
    assert "C0" in text and "C1" in text
    assert "pass rate" in text
    assert "flips_up" in text
    assert "solid_pass" in text
    assert "paused" in text


def test_summarize_is_json_serializable_and_complete():
    spec_a, spec_b, _ = _paired_fixture()
    runs = make_fixed_runs(spec_a, 3, "C0") + make_fixed_runs(spec_b, 3, "C1")
    data = stats.summarize(runs, None, n_boot=200, seed=0)
    assert data["conditions"] == ["C0", "C1"]
    assert data["per_condition"]["C1"]["n_instances"] == 20
    assert data["per_condition"]["C1"]["k_min"] == 3
    assert data["per_condition"]["C1"]["k_max"] == 3
    assert len(data["paired"]) == 1
    json.dumps(stats._json_safe(data))


def test_cli_writes_json_and_prints_report(tmp_path, capsys):
    spec_a, spec_b, _ = _paired_fixture()
    runs = make_fixed_runs(spec_a, 3, "C0") + make_fixed_runs(spec_b, 3, "C1")
    path = tmp_path / "runs.jsonl"
    path.write_text(
        "\n".join(json.dumps(r) for r in runs) + "\n", encoding="utf-8"
    )
    out_json = tmp_path / "site" / "stats.json"
    rc = stats.main(
        [
            "--runs",
            str(path),
            "--conditions",
            "C0",
            "C1",
            "--json",
            str(out_json),
            "--seed",
            "0",
            "--n-boot",
            "200",
        ]
    )
    assert rc == 0
    printed = capsys.readouterr().out
    assert "pass rate" in printed
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["conditions"] == ["C0", "C1"]
    assert payload["paired"][0]["flips_up"] == 8
