"""Unit tests for bench/live.py and bench/select_live.py.

Synthetic data only -- no network, no Docker, no harness subprocess.  The one
place a subprocess would run (``grade_live``) is monkeypatched with a fake that
writes the report.json the real harness would write, so the command line and the
report parsing are both exercised for real.
"""

from __future__ import annotations

import collections
import json
import subprocess
from pathlib import Path

import pytest

from bench import live, select_live

# --------------------------------------------------------------------------- #
# image naming
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "instance_id,expected",
    [
        ("joke2k__faker-2190", "starryzhang/sweb.eval.x86_64.joke2k_1776_faker-2190"),
        ("yt-dlp__yt-dlp-11425", "starryzhang/sweb.eval.x86_64.yt-dlp_1776_yt-dlp-11425"),
        ("deepset-ai__haystack-8981", "starryzhang/sweb.eval.x86_64.deepset-ai_1776_haystack-8981"),
        ("pydata__xarray-9974", "starryzhang/sweb.eval.x86_64.pydata_1776_xarray-9974"),
    ],
)
def test_image_ref_known_instances(instance_id, expected):
    assert live.image_ref(instance_id) == expected


def test_image_ref_lowercases_the_whole_name():
    # Live repos include mixed case (e.g. Instagram/MonkeyType); Docker Hub
    # repository paths must be lowercase.
    assert live.image_ref("Instagram__MonkeyType-42") == "starryzhang/sweb.eval.x86_64.instagram_1776_monkeytype-42"


def test_image_ref_replaces_every_double_underscore():
    assert live.image_ref("a__b__c-1").endswith("a_1776_b_1776_c-1")


def test_image_ref_leaves_single_underscores_alone():
    assert live.image_ref("my_org__my_repo-7").endswith("my_org_1776_my_repo-7")


def test_repo_name_matches_image_ref():
    assert live.repo_name("joke2k__faker-2190") == live.image_ref("joke2k__faker-2190")


# --------------------------------------------------------------------------- #
# FAIL_TO_PASS / PASS_TO_PASS parsing
# --------------------------------------------------------------------------- #
def test_parse_list_python_literal_form():
    # The dataset's actual shape: single quotes, so json.loads alone fails.
    raw = "['tests/test_a.py::test_one', 'tests/test_b.py::test_two']"
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)
    assert live.parse_list(raw) == ["tests/test_a.py::test_one", "tests/test_b.py::test_two"]


def test_parse_list_json_form():
    assert live.parse_list('["a::t1", "b::t2"]') == ["a::t1", "b::t2"]


def test_parse_list_passthrough_and_empty():
    assert live.parse_list(["a", "b"]) == ["a", "b"]
    assert live.parse_list(("a",)) == ["a"]
    assert live.parse_list("") == []
    assert live.parse_list("   ") == []
    assert live.parse_list(None) == []


def test_parse_list_handles_embedded_quotes_and_brackets():
    raw = "[\"tests/test_x.py::test_it[a-b]\", 'tests/test_y.py::test_q']"
    assert live.parse_list(raw) == ["tests/test_x.py::test_it[a-b]", "tests/test_y.py::test_q"]


def test_parse_list_rejects_garbage():
    with pytest.raises(ValueError):
        live.parse_list("not a list at all [[[")


def test_parse_list_wraps_a_bare_scalar():
    assert live.parse_list("'only_one'") == ["only_one"]


# --------------------------------------------------------------------------- #
# difficulty parsing
# --------------------------------------------------------------------------- #
def test_parse_difficulty_python_literal_form():
    assert live.parse_difficulty("{'files': 2, 'hunks': 7, 'lines': 26}") == {
        "files": 2,
        "hunks": 7,
        "lines": 26,
    }


def test_parse_difficulty_json_form_and_passthrough():
    assert live.parse_difficulty('{"files": 1, "hunks": 1, "lines": 3}')["lines"] == 3
    assert live.parse_difficulty({"lines": 5}) == {"lines": 5}


def test_parse_difficulty_degrades_to_empty_dict():
    for bad in (None, "", "   ", "not a dict", "[1, 2]", 17):
        assert live.parse_difficulty(bad) == {}


def test_to_iso_accepts_datetime_and_string():
    import datetime

    dt = datetime.datetime(2024, 11, 3, 12, 30, 0)
    assert live.to_iso(dt).startswith("2024-11-03T12:30")
    assert live.to_iso("2024-11-03T12:30:00") == "2024-11-03T12:30:00"
    assert live.to_iso(None) == ""


# --------------------------------------------------------------------------- #
# predictions file format (the upstream harness expects a dict keyed by id)
# --------------------------------------------------------------------------- #
def test_write_predictions_is_a_dict_keyed_by_instance_id(tmp_path):
    path = live.write_predictions(
        tmp_path / "preds.json",
        [{"instance_id": "a__b-1", "model_name_or_path": "harness-lab", "model_patch": "diff"}],
    )
    payload = json.loads(path.read_text())
    assert isinstance(payload, dict)
    # This is the exact access the harness performs.
    assert "a__b-1" in payload.keys()
    assert payload["a__b-1"]["model_patch"] == "diff"


# --------------------------------------------------------------------------- #
# grade_live
# --------------------------------------------------------------------------- #
GOLD_DIFF = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n"


def report_fixture(resolved: bool, instance_id="joke2k__faker-2190") -> dict:
    """The exact shape evaluation.py::run_instance writes."""
    return {
        "instance_id": instance_id,
        "resolved": resolved,
        "PASS_TO_PASS": {
            "success": ["t/p1", "t/p2", "t/p3"],
            "failure": [] if resolved else ["t/p4"],
        },
        "FAIL_TO_PASS": {
            "success": ["t/f1", "t/f2"] if resolved else [],
            "failure": [] if resolved else ["t/f1", "t/f2"],
        },
    }


def fake_harness(report: dict | None, returncode: int = 0, record: list | None = None):
    """Stand-in for subprocess.run that writes the report the harness would write."""

    def _run(cmd, **kwargs):
        if record is not None:
            record.append((list(cmd), kwargs))
        out_dir = Path(cmd[cmd.index("--output_dir") + 1])
        iid = cmd[cmd.index("--instance_ids") + 1]
        if report is not None:
            (out_dir / iid).mkdir(parents=True, exist_ok=True)
            (out_dir / iid / "report.json").write_text(json.dumps(report))
        return subprocess.CompletedProcess(cmd, returncode)

    return _run


@pytest.fixture
def graded(tmp_path, monkeypatch):
    """grade_live wired to a tmp results dir, no docker, no real harness."""
    monkeypatch.setattr(live, "GRADE_DIR", tmp_path / "grading")
    monkeypatch.setattr(live, "ensure_image", lambda iid, pull=True: True)
    return tmp_path


def test_grade_live_resolved(graded, monkeypatch):
    calls: list = []
    monkeypatch.setattr(live.subprocess, "run", fake_harness(report_fixture(True), record=calls))
    out = live.grade_live("joke2k__faker-2190", GOLD_DIFF, "r1")

    assert out["resolved"] is True
    assert out["infra_failure"] is False
    assert out["infra_failure_reason"] is None
    assert out["patch_exists"] is True
    assert out["patch_is_None"] is False
    assert out["patch_successfully_applied"] is True
    assert out["f2p"] == "2/2"
    assert out["p2p"] == "3/3"
    assert out["instance_id"] == "joke2k__faker-2190"
    assert out["run_id"] == "r1"
    assert isinstance(out["wall_s"], float)

    cmd, kwargs = calls[0]
    assert cmd[1:3] == ["-m", "evaluation.evaluation"]
    assert cmd[cmd.index("--dataset") + 1] == live.DATASET
    assert cmd[cmd.index("--split") + 1] == live.SPLIT
    assert cmd[cmd.index("--platform") + 1] == "linux"
    assert cmd[cmd.index("--workers") + 1] == "1"
    assert cmd[cmd.index("--overwrite") + 1] == "1"
    assert cmd[cmd.index("--patch_dir") + 1].endswith("preds.json")
    assert kwargs["cwd"] == str(live.LIVE_REPO)
    assert kwargs["env"]["DOCKER_DEFAULT_PLATFORM"] == "linux/amd64"


def test_grade_live_keys_match_bench_grade():
    """The driver reads one shape whichever grader ran."""
    expected = {
        "patch_is_None", "patch_exists", "patch_successfully_applied", "resolved",
        "infra_failure", "infra_failure_reason", "instance_id", "run_id", "wall_s", "f2p", "p2p",
    }
    out = live.grade_live("a__b-1", None, "r0")  # short-circuits, no harness needed
    assert set(out) == expected


def test_grade_live_unresolved(graded, monkeypatch):
    monkeypatch.setattr(live.subprocess, "run", fake_harness(report_fixture(False)))
    out = live.grade_live("joke2k__faker-2190", GOLD_DIFF, "r2")
    assert out["resolved"] is False
    assert out["infra_failure"] is False
    assert out["f2p"] == "0/2"
    assert out["p2p"] == "3/4"
    # The harness ran the tests and scored them, so the patch reached the suite.
    assert out["patch_successfully_applied"] is True


def test_grade_live_missing_report_is_infra_failure(graded, monkeypatch):
    monkeypatch.setattr(live.subprocess, "run", fake_harness(None))
    out = live.grade_live("joke2k__faker-2190", GOLD_DIFF, "r3")
    assert out["infra_failure"] is True
    assert "no report.json" in out["infra_failure_reason"]
    assert out["resolved"] is False
    assert out["patch_successfully_applied"] is False
    assert out["f2p"] == "0/0"


def test_grade_live_nonzero_exit_is_infra_failure(graded, monkeypatch):
    monkeypatch.setattr(live.subprocess, "run", fake_harness(None, returncode=1))
    out = live.grade_live("joke2k__faker-2190", GOLD_DIFF, "r4")
    assert out["infra_failure"] is True
    assert "exited 1" in out["infra_failure_reason"]


def test_grade_live_timeout_is_infra_failure(graded, monkeypatch):
    def _boom(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 5)

    monkeypatch.setattr(live.subprocess, "run", _boom)
    out = live.grade_live("joke2k__faker-2190", GOLD_DIFF, "r5", timeout=5)
    assert out["infra_failure"] is True
    assert "timeout" in out["infra_failure_reason"]


def test_grade_live_missing_image_is_infra_failure(graded, monkeypatch):
    monkeypatch.setattr(live, "ensure_image", lambda iid, pull=True: False)
    monkeypatch.setattr(live.subprocess, "run", fake_harness(report_fixture(True)))
    out = live.grade_live("joke2k__faker-2190", GOLD_DIFF, "r6")
    assert out["infra_failure"] is True
    assert "image not available" in out["infra_failure_reason"]


def test_grade_live_empty_patch_never_invokes_the_harness(graded, monkeypatch):
    def _fail(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("the harness must not be invoked for an empty patch")

    monkeypatch.setattr(live.subprocess, "run", _fail)
    for patch, is_none in ((None, True), ("", False), ("   \n", False)):
        out = live.grade_live("joke2k__faker-2190", patch, "r7")
        assert out["patch_is_None"] is is_none
        assert out["patch_exists"] is False
        assert out["resolved"] is False
        assert out["infra_failure"] is False


def test_grade_live_writes_preds_next_to_the_report(graded, monkeypatch):
    monkeypatch.setattr(live.subprocess, "run", fake_harness(report_fixture(True)))
    live.grade_live("joke2k__faker-2190", GOLD_DIFF, "r8")
    preds = json.loads((live.GRADE_DIR / "r8" / "preds.json").read_text())
    assert preds["joke2k__faker-2190"]["model_patch"] == GOLD_DIFF
    assert (live.GRADE_DIR / "r8" / "harness.log").exists()


# --------------------------------------------------------------------------- #
# buckets
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "lines,expected",
    [(0, "small"), (1, "small"), (15, "small"), (16, "medium"), (60, "medium"),
     (61, "large"), (600, "large")],
)
def test_bucket_boundaries(lines, expected):
    assert select_live.bucket_for({"difficulty": {"lines": lines}}) == expected


def test_bucket_unknown_when_difficulty_is_unusable():
    for difficulty in ({}, None, "junk", {"files": 1}, {"lines": "many"}, {"lines": -1}):
        assert select_live.bucket_for({"difficulty": difficulty}) == "unknown"


# --------------------------------------------------------------------------- #
# select_live
# --------------------------------------------------------------------------- #
REPOS = [
    "yt-dlp/yt-dlp", "pydata/xarray", "mikedh/trimesh", "joke2k/faker",
    "deepset-ai/haystack", "matplotlib/matplotlib", "scikit-learn/scikit-learn",
    "pandas-dev/pandas", "dask/dask", "astropy/astropy", "getmoto/moto", "pylint-dev/pylint",
]
REPO_WEIGHTS = [30, 24, 20, 18, 15, 12, 10, 9, 8, 7, 6, 5]
LINES_BY_BUCKET = {"small": 8, "medium": 30, "large": 140}
BUCKET_WEIGHTS = {"small": 90, "medium": 50, "large": 20}  # 160 instances


def make_instances() -> list[dict]:
    repo_slots = []
    for repo, weight in zip(REPOS, REPO_WEIGHTS):
        repo_slots.extend([repo] * weight)
    instances, slot = [], 0
    for bucket, count in BUCKET_WEIGHTS.items():
        for _ in range(count):
            repo = repo_slots[slot % len(repo_slots)]
            slot += 1
            instances.append(
                {
                    "instance_id": f"{repo.split('/')[1]}__{repo.split('/')[1]}-{slot:04d}",
                    "repo": repo,
                    "difficulty": {"files": 1, "hunks": 2, "lines": LINES_BY_BUCKET[bucket]},
                    "base_commit": f"c{slot:040d}",
                }
            )
    return instances


def fake_check(available_ids):
    allowed = set(available_ids)

    def _check(instance_ids, workers=8):
        return {iid: iid in allowed for iid in instance_ids}

    return _check


ALL_AVAILABLE = fake_check([i["instance_id"] for i in make_instances()])


def test_select_live_is_deterministic():
    instances = make_instances()
    a = select_live.build(instances, n=40, seed=20260912, check=ALL_AVAILABLE, verbose=False)
    b = select_live.build(instances, n=40, seed=20260912, check=ALL_AVAILABLE, verbose=False)
    assert a == b
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_select_live_different_seed_gives_a_different_draw():
    instances = make_instances()
    a = select_live.build(instances, n=40, seed=20260912, check=ALL_AVAILABLE, verbose=False)
    b = select_live.build(instances, n=40, seed=20260913, check=ALL_AVAILABLE, verbose=False)
    assert set(a["train"] + a["heldout"]) != set(b["train"] + b["heldout"])


def test_select_live_preserves_bucket_proportions():
    instances = make_instances()
    out = select_live.build(instances, n=40, seed=20260912, max_per_repo=None,
                            check=ALL_AVAILABLE, verbose=False)
    assert out["n"] == 40
    pool_total = sum(BUCKET_WEIGHTS.values())
    for bucket, weight in BUCKET_WEIGHTS.items():
        want = 40 * weight / pool_total
        assert abs(out["strata"][bucket] - want) <= 1, (bucket, out["strata"])


def test_select_live_honours_the_repo_cap():
    instances = make_instances()
    out = select_live.build(instances, n=40, seed=20260912, max_per_repo=6,
                            check=ALL_AVAILABLE, verbose=False)
    assert max(out["repos"].values()) <= 6
    assert out["filters"]["max_per_repo"] == 6


def test_select_live_filters_to_available_images():
    instances = make_instances()
    subset_ids = [i["instance_id"] for i in instances[:50]]
    out = select_live.build(instances, n=20, seed=20260912, max_per_repo=None,
                            check=fake_check(subset_ids), verbose=False)
    assert out["filters"]["image_available"] == 50
    assert set(out["train"] + out["heldout"]) <= set(subset_ids)


def test_select_live_filters_to_gold_passing(tmp_path):
    instances = make_instances()
    passing = [i["instance_id"] for i in instances[::3]]
    gold = {i["instance_id"]: i["instance_id"] in passing for i in instances}
    gold_path = tmp_path / "gold.json"
    gold_path.write_text(json.dumps(gold))
    out = select_live.build(instances, n=20, seed=20260912, max_per_repo=None,
                            gold_results=str(gold_path), check=ALL_AVAILABLE, verbose=False)
    assert out["filters"]["gold_passing"] == len(passing)
    assert set(out["train"] + out["heldout"]) <= set(passing)


def test_select_live_train_heldout_split_is_60_40_and_disjoint():
    instances = make_instances()
    out = select_live.build(instances, n=40, seed=20260912, check=ALL_AVAILABLE, verbose=False)
    train, heldout = out["train"], out["heldout"]
    assert len(train) == 24 and len(heldout) == 16
    assert not set(train) & set(heldout)
    assert len(set(train + heldout)) == 40
    assert train == sorted(train) and heldout == sorted(heldout)


def test_select_live_candidates_mode_emits_a_flat_list():
    instances = make_instances()
    out = select_live.build(instances, n=90, seed=20260912, max_per_repo=None,
                            check=ALL_AVAILABLE, split=False, verbose=False)
    assert "candidates" in out and "train" not in out
    assert len(out["candidates"]) == 90
    assert out["candidates"] == sorted(out["candidates"])


def test_select_live_output_carries_the_bench_tag_and_bucket_definition():
    instances = make_instances()
    out = select_live.build(instances, n=10, seed=20260912, check=ALL_AVAILABLE, verbose=False)
    assert out["bench"] == "live"
    assert out["dataset"] == live.DATASET and out["split"] == live.SPLIT
    assert out["buckets"]["small"] == "<= 15"
    assert out["buckets"]["medium"] == "16-60"
    assert out["buckets"]["large"] == "> 60"
    assert set(out["strata"]) <= {"small", "medium", "large", "unknown"}


def test_select_live_unknown_bucket_instances_still_stratify():
    instances = make_instances()
    for inst in instances[:20]:
        inst["difficulty"] = {}
    out = select_live.build(instances, n=40, seed=20260912, max_per_repo=None,
                            check=ALL_AVAILABLE, verbose=False)
    assert out["pool_strata"]["unknown"] == 20
    assert out["n"] == 40


def test_select_live_never_exceeds_the_pool():
    instances = make_instances()[:10]
    out = select_live.build(instances, n=40, seed=20260912, max_per_repo=None,
                            check=fake_check([i["instance_id"] for i in instances]), verbose=False)
    assert out["n"] == 10
    assert out["requested_n"] == 40


# --------------------------------------------------------------------------- #
# registry probe (no network: _get is monkeypatched)
# --------------------------------------------------------------------------- #
def test_probe_hub_maps_statuses(monkeypatch):
    monkeypatch.setattr(live, "_get", lambda url, headers: (200, b"{}"))
    assert live._probe_hub("a__b-1") is True
    monkeypatch.setattr(live, "_get", lambda url, headers: (404, b'{"message":"object not found"}'))
    assert live._probe_hub("a__b-1") is False
    monkeypatch.setattr(live, "_get", lambda url, headers: (429, b""))
    assert live._probe_hub("a__b-1") is None


def test_probe_falls_back_to_the_registry_when_hub_is_inconclusive(monkeypatch):
    monkeypatch.setattr(live, "_probe_hub", lambda iid: None)
    monkeypatch.setattr(live, "_probe_registry", lambda iid: True)
    assert live._probe("a__b-1") is True


def test_probe_prefers_hub_and_never_touches_the_rate_limited_registry(monkeypatch):
    def _boom(iid):  # pragma: no cover - must never run
        raise AssertionError("registry probe must not run when hub was definitive")

    monkeypatch.setattr(live, "_probe_hub", lambda iid: False)
    monkeypatch.setattr(live, "_probe_registry", _boom)
    assert live._probe("a__b-1") is False


def test_check_many_never_caches_an_inconclusive_result(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "REGISTRY_CACHE", tmp_path / "registry-live.json")
    verdicts = {"a__b-1": True, "a__b-2": False, "a__b-3": None}
    monkeypatch.setattr(live, "_resolve", lambda iid: verdicts[iid])
    results = live.check_many(list(verdicts), workers=1)
    assert results == {"a__b-1": True, "a__b-2": False, "a__b-3": False}
    cached = json.loads((tmp_path / "registry-live.json").read_text())
    assert cached == {"a__b-1": True, "a__b-2": False}  # the None is absent
    missing, unknown = live.split_negatives(results)
    assert missing == ["a__b-2"]
    assert unknown == ["a__b-3"]
