"""Tests for bench.site, the static results-page generator.

Everything is synthetic and fixed-seeded. The bootstrap runs at n_boot=500 so
the whole module stays fast; the page never renders the bootstrap count itself
except in the provenance line, so the small n_boot changes nothing structural.
"""

from __future__ import annotations

import json
import re

import pytest

from bench import site

try:  # the synthetic generators live with the stats tests
    from bench.tests.test_stats import (  # type: ignore[attr-defined]
        inject_infra_runs,
        make_fixed_runs,
        make_runs,
    )
except ImportError:  # pragma: no cover - fallback if that module moves

    def _run(condition, instance_id, repeat, outcome, resolved=None,
             cost=1.25, wall_s=300.0):
        return {
            "run_id": f"{condition}-{instance_id}-r{repeat}",
            "ts": "2026-09-03T00:00:00Z",
            "condition": condition,
            "instance_id": instance_id,
            "repeat": repeat,
            "outcome": outcome,
            "resolved": resolved,
            "num_turns": 12,
            "total_cost_usd": cost,
            "wall_s": wall_s,
            "notes": "",
        }

    def make_fixed_runs(spec, k, condition, cost=1.25):
        runs = []
        for iid, passes in sorted(spec.items()):
            for repeat in range(k):
                ok = repeat < passes
                runs.append(
                    _run(condition, iid, repeat,
                         "resolved" if ok else "unresolved", resolved=ok,
                         cost=cost)
                )
        return runs

    def make_runs(n_instances, k, p_by_instance=None, condition="C0", seed=0):
        ids = sorted(p_by_instance or {f"inst{i:03d}": 0.5
                                       for i in range(n_instances)})
        spec = {iid: (k if i % 2 else 0) for i, iid in enumerate(ids)}
        return make_fixed_runs(spec, k, condition)

    def inject_infra_runs(instance_ids, condition, outcome="paused",
                          n_per_instance=1, start_repeat=90):
        return [
            _run(condition, iid, start_repeat + j, outcome, resolved=None,
                 cost=None, wall_s=5.0)
            for iid in instance_ids
            for j in range(n_per_instance)
        ]


N_BOOT = 500

C0_SPEC = {
    "django__django-11039": 0,
    "django__django-12125": 3,
    "pytest-dev__pytest-5262": 0,
    "sympy__sympy-13031": 1,
}
C1_SPEC = {
    "django__django-11039": 3,
    "django__django-12125": 3,
    "pytest-dev__pytest-5262": 0,
    "sympy__sympy-13031": 2,
}


# --- helpers ----------------------------------------------------------------


def write_runs(path, runs):
    path.write_text(
        "".join(json.dumps(r) + "\n" for r in runs), encoding="utf-8"
    )
    return path


@pytest.fixture()
def two_condition_runs(tmp_path):
    runs = (
        make_fixed_runs(C0_SPEC, 3, "C0")
        + make_fixed_runs(C1_SPEC, 3, "C1", cost=2.0)
        + inject_infra_runs(["django__django-11039"], "C1", "paused")
        + inject_infra_runs(["sympy__sympy-13031"], "C0", "error")
    )
    return write_runs(tmp_path / "runs.jsonl", runs)


def build(runs_path, out_dir, **kwargs):
    kwargs.setdefault("n_boot", N_BOOT)
    return site.build(runs_path, out_dir, **kwargs)


# --- determinism ------------------------------------------------------------


def test_build_is_byte_identical_across_runs(two_condition_runs, tmp_path):
    a = tmp_path / "site-a"
    b = tmp_path / "site-b"
    build(two_condition_runs, a)
    build(two_condition_runs, b)

    for name in ("index.html", "data.json"):
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_rebuilding_into_the_same_dir_is_stable(two_condition_runs, tmp_path):
    out = tmp_path / "site"
    build(two_condition_runs, out)
    first = (out / "index.html").read_bytes()
    build(two_condition_runs, out)
    assert (out / "index.html").read_bytes() == first
    assert sorted(p.name for p in out.iterdir()) == ["data.json", "index.html"]


def test_page_carries_no_wall_clock_timestamp(two_condition_runs, tmp_path):
    page = build(two_condition_runs, tmp_path / "site")["html"]
    body = page.split("<body>", 1)[1]
    # the only dates on the page would come from a generation timestamp
    assert not re.search(r"\b20\d\d-\d\d-\d\dT\d\d:", body)


def test_provenance_names_the_manifest_and_its_hash(
    two_condition_runs, tmp_path
):
    result = build(two_condition_runs, tmp_path / "site")
    prov = result["provenance"]
    assert prov["name"] == "runs.jsonl"
    assert prov["n_lines"] == 26  # 24 counted + 2 infra
    assert len(prov["sha256"]) == 64
    page = result["html"]
    assert f"with {prov['n_lines']} lines" in page
    assert prov["sha256"] in page


# --- content ----------------------------------------------------------------


def test_index_html_has_the_expected_sections(two_condition_runs, tmp_path):
    page = build(two_condition_runs, tmp_path / "site")["html"]

    assert page.startswith("<!doctype html>")
    assert "<h1>Harness Lab</h1>" in page
    assert "prefers-color-scheme: dark" in page
    # self-contained: no external resources, no script
    assert "<script" not in page
    assert "http://" not in page.replace("http://www.w3.org/2000/svg", "")
    assert "https://" not in page

    # headline table
    assert "pass rate" in page
    assert ">C0<" in page and ">C1<" in page
    assert "solid_pass" in page and "flaky" in page and "solid_fail" in page
    assert "cost per solve" in page
    assert "resolved / counted" in page

    # charts
    assert page.count("<svg") == 2
    assert 'viewBox="0 0 700 320"' in page
    assert "</svg>" in page

    # paired comparison
    assert "Paired comparisons" in page
    assert "C0 to C1" in page
    assert "flips_up" in page and "regressions" in page
    assert "Wilcoxon p" in page and "sign-test p" in page
    assert "discordant" in page

    # per-instance table, collapsible, with the repo derived from the id
    assert "<details>" in page
    assert "Per-instance results" in page
    for iid in C0_SPEC:
        assert iid in page
    assert "<td>django</td>" in page
    assert "<td>pytest-dev</td>" in page

    # infra failures
    assert "Infrastructure failures" in page
    assert "paused" in page and "error" in page

    # caveats copied from docs/protocol.md
    assert "How to read this" in page
    assert "Caveats" in page

    # tables are mobile-safe
    assert page.count('class="scroll"') >= 4


def test_headline_numbers_match_the_stats_module(two_condition_runs, tmp_path):
    result = build(two_condition_runs, tmp_path / "site")
    data = result["data"]
    assert data["per_condition"]["C0"]["pass_rate"] == pytest.approx(1 / 3)
    assert data["per_condition"]["C1"]["pass_rate"] == pytest.approx(2 / 3)
    assert "0.333" in result["html"]
    assert "0.667" in result["html"]
    # C1 total cost is 12 counted runs at $2.00, over 8 resolved runs
    assert "$3.00" in result["html"]


def test_data_json_parses_and_matches_the_summary(
    two_condition_runs, tmp_path
):
    out = tmp_path / "site"
    result = build(two_condition_runs, out)
    data = json.loads((out / "data.json").read_text(encoding="utf-8"))

    assert data["conditions"] == ["C0", "C1"]
    assert set(data["per_condition"]) == {"C0", "C1"}
    assert data["n_runs_loaded"] == 26
    assert data["n_runs_counted"] == 24
    assert data["paired"][0]["cond_a"] == "C0"
    assert data["paired"][0]["flips_up"] == 1
    assert data["params"]["seed"] == 0
    assert result["data"]["conditions"] == data["conditions"]


# --- edge cases -------------------------------------------------------------


def test_empty_runs_file_renders_a_page(tmp_path):
    runs = write_runs(tmp_path / "runs.jsonl", [])
    out = tmp_path / "site"
    result = build(runs, out)

    page = (out / "index.html").read_text(encoding="utf-8")
    assert "No runs yet" in page
    assert "<h1>Harness Lab</h1>" in page
    assert "<svg" not in page
    assert "Paired comparisons" not in page

    data = json.loads((out / "data.json").read_text(encoding="utf-8"))
    assert data["conditions"] == []
    assert data["n_runs_loaded"] == 0
    assert result["provenance"]["n_lines"] == 0


def test_single_condition_has_no_paired_section(tmp_path):
    runs = write_runs(
        tmp_path / "runs.jsonl", make_fixed_runs(C0_SPEC, 3, "C0")
    )
    page = build(runs, tmp_path / "site")["html"]
    assert "Paired comparisons" not in page
    assert "Per-instance results" in page
    assert page.count("<svg") == 2


def test_missing_cost_and_wall_render_as_na(tmp_path):
    runs = make_fixed_runs({"a__a-1": 1, "a__a-2": 0}, 2, "C0", cost=None)
    for run in runs:
        run["wall_s"] = None
    page = build(write_runs(tmp_path / "runs.jsonl", runs), tmp_path / "s")[
        "html"
    ]
    assert "n/a" in page
    # no cost anywhere means no cost chart
    assert "no cost per solve chart" in page
    assert page.count("<svg") == 1


def test_zero_solves_leaves_cost_per_solve_na(tmp_path):
    runs = make_fixed_runs({"a__a-1": 0, "a__a-2": 0}, 2, "C0")
    page = build(write_runs(tmp_path / "runs.jsonl", runs), tmp_path / "s")[
        "html"
    ]
    assert "0.000" in page
    assert "n/a" in page


def test_conditions_with_different_instance_sets(tmp_path):
    runs = make_fixed_runs({"a__a-1": 2, "a__a-2": 0}, 2, "C0")
    runs += make_fixed_runs({"a__a-2": 2, "b__b-9": 1}, 2, "C1")
    out = tmp_path / "site"
    result = build(write_runs(tmp_path / "runs.jsonl", runs), out)
    page = result["html"]

    # the per-instance table spans the union and marks the gaps
    assert "a__a-1" in page and "b__b-9" in page
    assert 'class="num na">n/a' in page
    # the paired test only uses the shared instance
    assert result["data"]["paired"][0]["n_instances"] == 1
    assert result["data"]["paired"][0]["n_only_a"] == 1
    assert result["data"]["paired"][0]["n_only_b"] == 1


def test_k_mismatch_instances_are_flagged_as_excluded(tmp_path):
    """Protocol caveat 4 is rendered verbatim on the page, so the paired
    block has to say the same thing: the instance is listed, not counted."""
    runs = make_fixed_runs({"a__a-1": 0, "a__a-2": 3, "a__a-3": 1}, 3, "C0")
    runs += make_fixed_runs({"a__a-1": 3, "a__a-2": 3, "a__a-3": 1}, 3, "C1")
    # a fourth counted run in C1 only, so k is 3 vs 4 for a__a-1
    runs.append(dict(runs[-1], instance_id="a__a-1", repeat=3,
                     run_id="C1-a__a-1-r3", outcome="resolved", resolved=True))
    out = tmp_path / "site"
    result = build(write_runs(tmp_path / "runs.jsonl", runs), out)
    paired = result["data"]["paired"][0]
    assert paired["k_mismatch_instances"] == ["a__a-1"]
    assert paired["n_instances"] == 3
    assert paired["n_paired"] == 2
    assert paired["n_excluded"] == 1
    assert paired["transition_table"]["total"] == 2
    assert paired["flips_up"] == 0

    page = result["html"]
    assert "Paired on 2 of the 3 instance(s)" in page
    assert "1 excluded for k mismatch" in page
    assert "k differs between conditions for 1 instance(s): a__a-1" in page
    assert "excluded from the transition table and both paired tests" in page
    # the no-mismatch wording is untouched
    assert "Paired on the" not in page


def test_candidates_are_kept_out_of_the_headline(tmp_path):
    runs = make_fixed_runs(C0_SPEC, 3, "C0")
    runs += make_fixed_runs(C1_SPEC, 3, "C1")
    runs += make_fixed_runs(
        {iid: min(p, 1) for iid, p in C1_SPEC.items()}, 1,
        "cand-ab12cd3"
    )
    out = tmp_path / "site"
    result = build(write_runs(tmp_path / "runs.jsonl", runs), out)
    page = result["html"]

    assert result["conditions"] == ["C0", "C1", "cand-ab12cd3"]
    assert "Candidate screens (1)" in page
    # the candidate is not a point on the headline curve
    assert page.count(">cand-ab12cd3<") >= 1
    assert "cand-ab12cd3</text>" not in page
    # and it is not a paired comparison
    assert "C1 to cand-ab12cd3" not in page
    assert "C0 to C1" in page


def test_condition_ordering_is_c0_then_candidates_last():
    mains, cands = site.order_conditions(
        ["cand-zz", "C10", "C2", "C0", "C1o", "C1", "cand-aa", "other"]
    )
    assert mains == ["C0", "C1", "C1o", "C2", "C10", "other"]
    assert cands == ["cand-aa", "cand-zz"]
    assert site.is_candidate("cand-ab12cd3")
    assert not site.is_candidate("C1")


def test_explicit_conditions_keep_their_order(two_condition_runs, tmp_path):
    result = build(
        two_condition_runs, tmp_path / "site", conditions=["C1", "C0"]
    )
    assert result["conditions"] == ["C1", "C0"]
    assert result["data"]["paired"][0]["cond_a"] == "C1"
    assert "C1 to C0" in result["html"]


def test_named_condition_with_no_runs_renders_na(two_condition_runs, tmp_path):
    result = build(
        two_condition_runs, tmp_path / "site", conditions=["C0", "C1", "C2"]
    )
    assert result["data"]["per_condition"]["C2"]["n_instances"] == 0
    assert result["data"]["per_condition"]["C2"]["pass_rate"] != result[
        "data"
    ]["per_condition"]["C2"]["pass_rate"]  # NaN
    page = result["html"]
    assert ">C2<" in page
    assert "n/a" in page
    # NaN never reaches the JSON dump
    data = json.loads(
        (tmp_path / "site" / "data.json").read_text(encoding="utf-8")
    )
    assert data["per_condition"]["C2"]["pass_rate"] is None


def test_missing_protocol_omits_caveats_and_versions(
    two_condition_runs, tmp_path
):
    page = build(
        two_condition_runs,
        tmp_path / "site",
        protocol_path=str(tmp_path / "nope.md"),
    )["html"]
    assert "How to read this" not in page
    assert "Pinned versions" not in page
    assert "<h1>Harness Lab</h1>" in page


def test_protocol_scraping_reads_caveats_and_versions(tmp_path):
    doc = tmp_path / "protocol.md"
    doc.write_text(
        "# P\n\n## Pinned versions\n\n"
        "| component | value |\n|---|---|\n"
        "| Claude Code CLI | 2.1.76 with `DISABLE_AUTOUPDATER=1` |\n\n"
        "## Metrics\n\nnot a caveat\n\n"
        "## Caveats (from the stats review)\n\n"
        "1. First caveat, `cost_per_solve` included.\n"
        "   Continues on the next line.\n"
        "2. Second caveat.\n",
        encoding="utf-8",
    )
    parsed = site.read_protocol(str(doc))
    assert parsed is not None
    assert parsed["caveats"] == [
        "First caveat, `cost_per_solve` included. Continues on the next line.",
        "Second caveat.",
    ]
    assert parsed["versions_header"] == ["component", "value"]
    assert parsed["versions_rows"] == [
        ["Claude Code CLI", "2.1.76 with `DISABLE_AUTOUPDATER=1`"]
    ]
    assert site.read_protocol(str(tmp_path / "missing.md")) is None


def test_title_is_configurable(two_condition_runs, tmp_path):
    page = build(
        two_condition_runs, tmp_path / "site", title="Harness Lab week 3"
    )["html"]
    assert "<title>Harness Lab week 3</title>" in page
    assert "<h1>Harness Lab week 3</h1>" in page


def test_html_is_escaped(tmp_path):
    runs = make_fixed_runs({"<script>__x-1": 1}, 2, "C0")
    page = build(write_runs(tmp_path / "runs.jsonl", runs), tmp_path / "s")[
        "html"
    ]
    assert "<script>" not in page
    assert "&lt;script&gt;__x-1" in page


def test_malformed_lines_are_skipped_not_fatal(tmp_path, capsys):
    path = tmp_path / "runs.jsonl"
    good = make_fixed_runs({"a__a-1": 1}, 2, "C0")
    path.write_text(
        "{not json\n" + "".join(json.dumps(r) + "\n" for r in good),
        encoding="utf-8",
    )
    result = build(path, tmp_path / "site")
    assert result["data"]["n_runs_loaded"] == 2
    assert "No runs yet" not in result["html"]


# --- CLI --------------------------------------------------------------------


def test_cli_writes_both_files(two_condition_runs, tmp_path, capsys):
    out = tmp_path / "cli-site"
    rc = site.main(
        [
            "--runs",
            str(two_condition_runs),
            "--out",
            str(out),
            "--n-boot",
            str(N_BOOT),
            "--seed",
            "0",
            "--title",
            "Harness Lab",
        ]
    )
    assert rc == 0
    assert (out / "index.html").is_file()
    assert (out / "data.json").is_file()
    printed = capsys.readouterr().out
    assert "index.html" in printed and "data.json" in printed


def test_cli_reports_a_missing_runs_file(tmp_path, capsys):
    rc = site.main(
        ["--runs", str(tmp_path / "nope.jsonl"), "--out", str(tmp_path / "s")]
    )
    assert rc == 2
    assert "no such runs file" in capsys.readouterr().err


def test_json_safe_rounds_platform_noise():
    """Last-digit libm differences (Linux CI vs arm64 Mac) must not change the site."""
    from bench.site import _json_safe
    assert _json_safe(0.06836531288935432) == _json_safe(0.06836531288935434)
    assert _json_safe({"p": [0.031032519500144917]}) == {"p": [0.0310325195]}
    assert _json_safe(float("nan")) is None
