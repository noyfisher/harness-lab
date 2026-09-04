"""Unit tests for improver.loop.

Nothing here spends anything: the `claude -p` invocation, the harness-load smoke check and the
`bench.batch` call are all replaced by fakes, and every module-level path in `improver.loop` is
redirected into a throwaway repo under tmp_path.  `results/runs.jsonl` in the real repo is never
opened -- a live batch is usually appending to it.

Git, by contrast, is *real*: each test builds an actual repository (with a `harness/` tree and a
`harness-seed` tag) so branch creation, the harness reset, the candidate commit, the
outside-harness revert, tagging and the return to `main` are exercised as they will run.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from improver import loop  # noqa: E402

#: Captured before any fixture patches it, so the real invocation can still be tested.
REAL_INVOKE = loop.invoke_improver


TRAIN = ["aa__aa-1001", "aa__aa-1002", "aa__aa-1003", "aa__aa-1004"]
HELDOUT = ["bb__bb-2001", "bb__bb-2002", "bb__bb-2003"]

#: The hidden test names that must never appear in harness/.
HIDDEN = {
    iid: [f"tests/test_{iid.replace('-', '_')}.py::test_hidden_behaviour_{n}"]
    for n, iid in enumerate(TRAIN + HELDOUT)
}

VALID_HYPOTHESIS = {
    "hypothesis": "Telling the lead to run the nearest existing tests before declaring done "
                  "should convert reproduce-only runs into real fixes.",
    "target_files": ["harness/CLAUDE.md"],
    "expected_flips": [TRAIN[0], TRAIN[1]],
    "rationale": "Both train solid_fail traces stopped after an edit with no test executed at "
                 "all, so the done-condition is the thing that is missing.",
    "category": "prompt_rule",
}


# --- the temp repo ---------------------------------------------------------------------------


def _git(root, *args, check=True):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr or r.stdout}")
    return r


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A real git repo shaped like harness-lab, with loop's paths redirected into it."""
    root = tmp_path / "repo"
    (root / "harness" / "agents").mkdir(parents=True)
    (root / "harness" / "schemas").mkdir(parents=True)
    (root / "bench").mkdir()
    (root / "results").mkdir()
    (root / "docs").mkdir()
    (root / ".claude" / "commands").mkdir(parents=True)
    (root / "improver" / "state").mkdir(parents=True)

    (root / ".gitignore").write_text("harness/.claude.json\nharness/backups/\n")
    (root / "harness" / "CLAUDE.md").write_text("# harness operating rules\n\nFix the issue.\n")
    (root / "harness" / "agents" / "lead.md").write_text("---\nname: lead\n---\nOrchestrate.\n")
    (root / "harness" / "settings.json").write_text("{}\n")
    (root / "harness" / "schemas" / "hypothesis.schema.json").write_text(
        (Path(_ROOT) / "harness" / "schemas" / "hypothesis.schema.json").read_text()
    )
    (root / "bench" / "subset.json").write_text(
        json.dumps({"n": len(TRAIN) + len(HELDOUT), "train": TRAIN, "heldout": HELDOUT})
    )
    (root / "bench" / "instances.json").write_text(json.dumps([
        {"instance_id": iid, "FAIL_TO_PASS": HIDDEN[iid],
         "PASS_TO_PASS": ["tests/test_common.py::test_untouched_baseline_behaviour"]}
        for iid in TRAIN + HELDOUT
    ]))
    (root / ".claude" / "commands" / "improve.md").write_text("Read the train failures.\n")
    (root / "improver" / "state" / "owner-decisions.md").write_text(
        "# Owner decisions queue\n\n(empty)\n"
    )
    (root / "results" / "runs.jsonl").write_text("")

    _git(root, "init", "-q")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(root, "config", "user.email", "bench@harness-lab")
    _git(root, "config", "user.name", "harness-lab")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed")
    _git(root, "tag", "harness-seed")

    monkeypatch.setattr(loop, "ROOT", root)
    monkeypatch.setattr(loop, "STATE_DIR", root / "improver" / "state")
    monkeypatch.setattr(loop, "ARCHIVE", root / "improver" / "state" / "archive.json")
    monkeypatch.setattr(loop, "BEST", root / "improver" / "state" / "best.json")
    monkeypatch.setattr(loop, "OWNER_DECISIONS", root / "improver" / "state" / "owner-decisions.md")
    monkeypatch.setattr(loop, "HARNESS", root / "harness")
    monkeypatch.setattr(loop, "HYPOTHESIS", root / "harness" / "HYPOTHESIS.json")
    monkeypatch.setattr(loop, "SCHEMA", root / "harness" / "schemas" / "hypothesis.schema.json")
    monkeypatch.setattr(loop, "IMPROVE_COMMAND", root / ".claude" / "commands" / "improve.md")
    monkeypatch.setattr(loop, "RUNS", root / "results" / "runs.jsonl")
    monkeypatch.setattr(loop, "DRYRUNS", root / "results" / "dryruns.jsonl")
    monkeypatch.setattr(loop, "SUBSET", root / "bench" / "subset.json")
    monkeypatch.setattr(loop, "INSTANCES", root / "bench" / "instances.json")

    # the two seams that would otherwise touch the network or the owner's subscription
    monkeypatch.setattr(loop, "smoke_check", lambda d: (0, "lead\nplanner\nbackend-dev\n"))
    monkeypatch.setattr(loop, "invoke_improver", _no_spend)
    monkeypatch.setattr(loop, "run_batch_cmd", _no_batch)
    return root


def _no_spend(a):  # pragma: no cover - a test that reaches this has failed
    raise AssertionError("the improver agent must not be invoked in tests")


def _no_batch(argv):  # pragma: no cover - a test that reaches this has failed
    raise AssertionError(f"a batch must not be run in tests: {argv}")


# --- fakes -----------------------------------------------------------------------------------


def fake_agent(root, *, hypothesis=VALID_HYPOTHESIS, raw_hypothesis=None,
               harness_edits=(("harness/CLAUDE.md", "\nRun the nearest existing tests.\n"),),
               outside=(), is_error=False, stage_outside=False):
    """A stand-in for `claude -p /improve`: it only edits files, exactly like the real agent."""
    def _agent(a):
        for rel, text in harness_edits:
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a") as fh:
                fh.write(text)
        for rel, text in outside:
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
            if stage_outside:
                _git(root, "add", "--", rel)
        if raw_hypothesis is not None:
            (root / "harness" / "HYPOTHESIS.json").write_text(raw_hypothesis)
        elif hypothesis is not None:
            (root / "harness" / "HYPOTHESIS.json").write_text(json.dumps(hypothesis, indent=2))
        return {"rc": 0, "is_error": is_error, "subtype": "success", "num_turns": 7,
                "total_cost_usd": 1.42, "error": "boom" if is_error else None}
    return _agent


def manifest(condition, instance, repeat, passed, tag="fake"):
    """One line shaped like docs/manifest-schema.md."""
    return {
        "run_id": f"{condition}-{instance}-r{repeat}-{tag}",
        "ts": "2026-09-04T00:00:00Z", "condition": condition, "harness_sha": "f" * 40,
        "cli_version": "2.1.76", "model": "claude-sonnet-5", "effort": "medium",
        "credential": "subscription", "instance_id": instance, "repeat": repeat,
        "outcome": "resolved" if passed else "unresolved", "resolved": bool(passed),
        "touched_tests": False, "stripped_test_hunks": 0, "num_turns": 9,
        "total_cost_usd": 1.0, "wall_s": 200.0, "notes": "", "supersedes": None,
    }


def append_runs(path, records):
    with open(path, "a") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def seed_base(root, *, solid_pass=(), solid_fail=(), flaky=(), condition="C1", k=3):
    """Write the base condition's k=3 manifests: k/k, 0/k, and 1/k respectively."""
    recs = []
    for iid in solid_pass:
        recs += [manifest(condition, iid, r, True) for r in range(k)]
    for iid in solid_fail:
        recs += [manifest(condition, iid, r, False) for r in range(k)]
    for iid in flaky:
        recs += [manifest(condition, iid, r, r == 0) for r in range(k)]
    append_runs(root / "results" / "runs.jsonl", recs)


def arg_of(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


class FakeBatch:
    """Stands in for `bench.batch.main`: honours --split/--k, resumes, appends manifests."""

    def __init__(self, root, passing, rc=0, dry=False):
        self.root = root
        self.passing = set(passing)          # instance ids the candidate resolves
        self.rc = rc
        self.calls: list[list[str]] = []
        self.path = root / "results" / ("dryruns.jsonl" if dry else "runs.jsonl")

    def __call__(self, argv):
        self.calls.append(list(argv))
        if self.rc:
            return self.rc
        condition = arg_of(argv, "--condition")
        split = arg_of(argv, "--split")
        k = int(arg_of(argv, "--k"))
        instances = json.loads((self.root / "bench" / "subset.json").read_text())
        ids = sorted(set(instances["train"] if split == "train" else
                         instances["heldout"] if split == "heldout" else
                         instances["train"] + instances["heldout"]))
        done = set()
        if self.path.exists():
            for rec in loop.stats.load_runs(self.path):
                if loop.stats.counted(rec):
                    done.add((rec["condition"], rec["instance_id"], rec.get("repeat")))
        out = []
        for repeat in range(k):                       # repeat-major, like the real batch
            for iid in ids:
                if (condition, iid, repeat) in done:
                    continue
                out.append(manifest(condition, iid, repeat, iid in self.passing,
                                    tag=f"b{len(self.calls)}"))
        append_runs(self.path, out)
        return 0


def porcelain(root, ignore=("results/", "improver/state/")):
    r = _git(root, "status", "--porcelain")
    return [ln for ln in r.stdout.splitlines()
            if not any(ln[3:].startswith(pre) for pre in ignore)]


# --- 1. preconditions ------------------------------------------------------------------------


def test_dirty_tree_aborts_before_spending(repo, monkeypatch):
    (repo / "bench" / "scratch.py").write_text("print('wip')\n")
    assert loop.main(["--once"]) == loop.EXIT_DIRTY
    assert loop.load_archive() == []
    assert loop.current_branch() == "main"


def test_dirty_results_are_ignored_by_default(repo, monkeypatch):
    """A live batch appends to results/ constantly; that must not block the loop."""
    append_runs(repo / "results" / "runs.jsonl", [manifest("C1", TRAIN[0], 0, True)])
    (repo / "results" / "patches").mkdir()
    (repo / "results" / "patches" / "x.diff").write_text("diff\n")
    assert loop.working_tree_changes() == []
    assert loop.working_tree_changes(ignore=()) != []


def test_missing_improve_command_aborts_before_spending(repo, monkeypatch):
    (repo / ".claude" / "commands" / "improve.md").unlink()
    _git(repo, "commit", "-qam", "drop improve command")
    monkeypatch.setattr(loop, "invoke_improver", _no_spend)
    assert loop.main(["--once"]) == loop.EXIT_NO_COMMAND
    assert loop.load_archive() == []


def test_best_json_is_created_lazily_from_the_seed_tag(repo):
    best = loop.load_best()
    assert best["condition"] == "C1" and best["tag"] == "harness-seed"
    assert best["sha"] == loop.rev_parse("harness-seed")
    assert json.loads((repo / "improver" / "state" / "best.json").read_text()) == best


# --- 2. mechanical validation ----------------------------------------------------------------


def _reject_run(repo, monkeypatch, agent):
    monkeypatch.setattr(loop, "invoke_improver", agent)
    code = loop.main(["--once"])
    archive = loop.load_archive()
    return code, archive[-1] if archive else None


def test_rejects_edits_outside_harness_and_reverts_them(repo, monkeypatch):
    agent = fake_agent(repo, outside=(("bench/sneaky.py", "SUBSET = 'mine'\n"),))
    code, rec = _reject_run(repo, monkeypatch, agent)
    assert code == loop.EXIT_OK
    assert rec["status"] == "rejected" and "outside harness/" in rec["reason"]
    assert not (repo / "bench" / "sneaky.py").exists()
    assert porcelain(repo) == [] and loop.current_branch() == "main"


def test_rejects_staged_edits_outside_harness(repo, monkeypatch):
    agent = fake_agent(repo, outside=(("bench/stats.py", "# rewritten\n"),), stage_outside=True)
    code, rec = _reject_run(repo, monkeypatch, agent)
    assert code == loop.EXIT_OK and "outside harness/" in rec["reason"]
    assert porcelain(repo) == []


def test_rejects_invalid_hypothesis(repo, monkeypatch):
    bad = dict(VALID_HYPOTHESIS, category="vibes", hypothesis="too short")
    code, rec = _reject_run(repo, monkeypatch, fake_agent(repo, hypothesis=bad))
    assert code == loop.EXIT_OK
    assert "HYPOTHESIS.json invalid" in rec["reason"]
    assert "category" in rec["reason"] and "hypothesis" in rec["reason"]


def test_rejects_unparseable_hypothesis(repo, monkeypatch):
    code, rec = _reject_run(repo, monkeypatch, fake_agent(repo, raw_hypothesis="{not json"))
    assert code == loop.EXIT_OK and "not valid JSON" in rec["reason"]


def test_rejects_missing_hypothesis(repo, monkeypatch):
    code, rec = _reject_run(repo, monkeypatch, fake_agent(repo, hypothesis=None))
    assert code == loop.EXIT_OK and "HYPOTHESIS.json is missing" in rec["reason"]


def test_rejects_heldout_id_in_expected_flips(repo, monkeypatch):
    bad = dict(VALID_HYPOTHESIS, expected_flips=[HELDOUT[0]])
    code, rec = _reject_run(repo, monkeypatch, fake_agent(repo, hypothesis=bad))
    assert code == loop.EXIT_OK and "not a train-split instance id" in rec["reason"]


def test_rejects_target_file_that_does_not_exist(repo, monkeypatch):
    bad = dict(VALID_HYPOTHESIS, target_files=["harness/agents/ghost.md"])
    code, rec = _reject_run(repo, monkeypatch, fake_agent(repo, hypothesis=bad))
    assert code == loop.EXIT_OK and "does not exist" in rec["reason"]


def test_rejects_hypothesis_only_change(repo, monkeypatch):
    code, rec = _reject_run(repo, monkeypatch, fake_agent(repo, harness_edits=()))
    assert code == loop.EXIT_OK
    assert "other than HYPOTHESIS.json" in rec["reason"]


def test_rejects_leaked_hidden_test_name(repo, monkeypatch):
    leak = HIDDEN[TRAIN[0]][0]
    agent = fake_agent(repo, harness_edits=(("harness/CLAUDE.md", f"\nAlways run {leak} first.\n"),))
    code, rec = _reject_run(repo, monkeypatch, agent)
    assert code == loop.EXIT_OK and "leaked hidden test name" in rec["reason"]
    assert leak in rec["reason"]


def test_rejects_leaked_instance_id_outside_the_hypothesis(repo, monkeypatch):
    agent = fake_agent(repo, harness_edits=(
        ("harness/agents/lead.md", f"\nFor {TRAIN[2]} try harder.\n"),))
    code, rec = _reject_run(repo, monkeypatch, agent)
    assert code == loop.EXIT_OK and TRAIN[2] in rec["reason"]


def test_expected_flips_may_name_train_ids_in_the_hypothesis_file(repo, monkeypatch):
    """HYPOTHESIS.json is required to name train ids; that alone is not a leak."""
    monkeypatch.setattr(loop, "invoke_improver", fake_agent(repo))
    batch = FakeBatch(repo, passing=[])
    monkeypatch.setattr(loop, "run_batch_cmd", batch)
    seed_base(repo, solid_fail=TRAIN, solid_pass=HELDOUT)
    assert loop.main(["--once"]) == loop.EXIT_OK
    rec = loop.load_archive()[-1]
    assert "leak" not in rec["reason"]                    # got past validation ...
    assert "zero solid_fail -> pass flips" in rec["reason"]   # ... and died on the screen


def test_rejects_failed_smoke_check(repo, monkeypatch):
    monkeypatch.setattr(loop, "smoke_check", lambda d: (1, "SyntaxError in agents/lead.md"))
    code, rec = _reject_run(repo, monkeypatch, fake_agent(repo))
    assert code == loop.EXIT_OK and "smoke check failed" in rec["reason"]


def test_rejects_smoke_check_missing_lead(repo, monkeypatch):
    monkeypatch.setattr(loop, "smoke_check", lambda d: (0, "planner\ntester\n"))
    code, rec = _reject_run(repo, monkeypatch, fake_agent(repo))
    assert code == loop.EXIT_OK and "did not list ['lead']" in rec["reason"]


def test_smoke_check_leftovers_are_deleted(repo, monkeypatch):
    def dirty_smoke(harness_dir):
        Path(harness_dir, ".claude.json").write_text("{}")
        Path(harness_dir, "backups").mkdir(exist_ok=True)
        return 0, "lead\n"
    monkeypatch.setattr(loop, "smoke_check", dirty_smoke)
    monkeypatch.setattr(loop, "invoke_improver", fake_agent(repo))
    monkeypatch.setattr(loop, "run_batch_cmd", FakeBatch(repo, passing=[]))
    seed_base(repo, solid_fail=TRAIN, solid_pass=HELDOUT)
    loop.main(["--once"])
    assert not (repo / "harness" / ".claude.json").exists()
    assert not (repo / "harness" / "backups").exists()


def test_agent_failure_halts_without_judging_the_variant(repo, monkeypatch):
    monkeypatch.setattr(loop, "invoke_improver", fake_agent(repo, is_error=True))
    assert loop.main(["--once"]) == loop.EXIT_AGENT
    rec = loop.load_archive()[-1]
    assert rec["status"] == "screening" and "improver agent failed" in rec["reason"]
    assert loop.current_branch() == "main"


# --- 3. schema validator ---------------------------------------------------------------------


def test_schema_validator_accepts_the_reference_hypothesis(repo):
    schema = json.loads((repo / "harness" / "schemas" / "hypothesis.schema.json").read_text())
    assert loop.validate_hypothesis(VALID_HYPOTHESIS, schema, TRAIN, repo / "harness") == []


@pytest.mark.parametrize("mutation,fragment", [
    ({"category": "nonsense"}, "not one of"),
    ({"hypothesis": "short"}, "shorter than"),
    ({"target_files": ["bench/run.py"]}, "does not match"),
    ({"target_files": []}, "at least 1"),
    ({"expected_flips": []}, "at least 1"),
    ({"rationale": 7}, "expected string"),
    ({"extra": 1}, "unexpected property"),
])
def test_schema_validator_rejects(repo, mutation, fragment):
    schema = json.loads((repo / "harness" / "schemas" / "hypothesis.schema.json").read_text())
    doc = dict(VALID_HYPOTHESIS, **mutation)
    errs = loop.validate_hypothesis(doc, schema, TRAIN, repo / "harness")
    assert any(fragment in e for e in errs), errs


def test_schema_validator_reports_missing_required(repo):
    schema = json.loads((repo / "harness" / "schemas" / "hypothesis.schema.json").read_text())
    doc = {k: v for k, v in VALID_HYPOTHESIS.items() if k != "rationale"}
    errs = loop.validate_hypothesis(doc, schema, TRAIN, repo / "harness")
    assert any("missing required property 'rationale'" in e for e in errs), errs


# --- 4. flip / regression arithmetic ---------------------------------------------------------


def test_transitions_base_k3_vs_candidate_k1():
    """Base classified at k=3, candidate screened at k=1: the asymmetry the screens rely on."""
    runs = []
    runs += [manifest("C1", "i-solidfail", r, False) for r in range(3)]
    runs += [manifest("C1", "i-solidpass", r, True) for r in range(3)]
    runs += [manifest("C1", "i-flaky", r, r == 0) for r in range(3)]
    runs += [manifest("C1", "i-ignored", r, True) for r in range(3)]
    runs += [
        manifest("cand-abc1234", "i-solidfail", 0, True),    # flip up
        manifest("cand-abc1234", "i-solidpass", 0, False),   # regression
        manifest("cand-abc1234", "i-flaky", 0, True),        # flaky gain
    ]
    t = loop.transitions(runs, "C1", "cand-abc1234",
                         ["i-solidfail", "i-solidpass", "i-flaky", "i-missing"])
    assert (t["flips_up"], t["regressions"], t["flaky_gains"]) == (1, 1, 1)
    assert t["flips_up_ids"] == ["i-solidfail"]
    assert t["regression_ids"] == ["i-solidpass"]
    assert t["n_compared"] == 3 and t["k_base"] == [3, 3] and t["k_cand"] == [1, 1]
    assert "i-missing" in t["n_cand_missing"]
    assert "i-ignored" not in t["base_classes"]           # restricted to the requested split


def test_transitions_k3_both_sides_uses_solid_classes():
    runs = []
    runs += [manifest("C1", "i-a", r, False) for r in range(3)]
    runs += [manifest("C1", "i-b", r, True) for r in range(3)]
    runs += [manifest("C2", "i-a", r, r < 2) for r in range(3)]   # 2/3 -> flaky, NOT a flip
    runs += [manifest("C2", "i-b", r, r < 2) for r in range(3)]   # solid_pass -> flaky = regression
    t = loop.transitions(runs, "C1", "C2", ["i-a", "i-b"])
    assert t["flips_up"] == 0 and t["regressions"] == 1
    assert t["cand_classes"]["flaky"] == 2


def test_transitions_ignores_infrastructure_failures():
    runs = [manifest("C1", "i-a", r, False) for r in range(3)]
    cand = manifest("cand-abc1234", "i-a", 0, True)
    cand["outcome"] = "paused"
    cand["resolved"] = None
    t = loop.transitions(runs + [cand], "C1", "cand-abc1234", ["i-a"])
    assert t["n_compared"] == 0 and t["flips_up"] == 0
    assert t["n_cand_missing"] == ["i-a"]


# --- 5. the screens --------------------------------------------------------------------------


def _screen_run(repo, monkeypatch, passing, **seed):
    monkeypatch.setattr(loop, "invoke_improver", fake_agent(repo))
    batch = FakeBatch(repo, passing=passing)
    monkeypatch.setattr(loop, "run_batch_cmd", batch)
    seed_base(repo, **seed)
    code = loop.main(["--once"])
    return code, loop.load_archive()[-1], batch


def test_train_screen_rejects_zero_flips(repo, monkeypatch):
    code, rec, batch = _screen_run(
        repo, monkeypatch, passing=[TRAIN[2]],
        solid_fail=[TRAIN[0], TRAIN[1]], solid_pass=[TRAIN[2]], flaky=[TRAIN[3]])
    assert code == loop.EXIT_OK
    assert rec["status"] == "rejected" and rec["stage"] == "train_k1"
    assert "zero solid_fail -> pass flips" in rec["reason"]
    assert len(batch.calls) == 1                     # the held-out screen never ran
    assert rec["results"]["train_k1"]["flips_up"] == 0


def test_train_screen_rejects_a_regression(repo, monkeypatch):
    code, rec, batch = _screen_run(
        repo, monkeypatch, passing=[TRAIN[0], TRAIN[1]],
        solid_fail=[TRAIN[0], TRAIN[1]], solid_pass=[TRAIN[2]], flaky=[TRAIN[3]])
    assert rec["stage"] == "train_k1" and "regression" in rec["reason"]
    assert TRAIN[2] in rec["reason"]
    assert rec["results"]["train_k1"]["flips_up"] == 2
    assert len(batch.calls) == 1


def test_heldout_screen_rejects_a_regression(repo, monkeypatch):
    code, rec, batch = _screen_run(
        repo, monkeypatch,
        passing=[TRAIN[0], TRAIN[1], TRAIN[2], TRAIN[3], HELDOUT[1], HELDOUT[2]],
        solid_fail=[TRAIN[0], TRAIN[1]], solid_pass=[TRAIN[2], HELDOUT[0], HELDOUT[1]],
        flaky=[TRAIN[3]])
    assert rec["stage"] == "heldout_k1" and "held-out k=1" in rec["reason"]
    assert HELDOUT[0] in rec["reason"]
    assert [arg_of(c, "--split") for c in batch.calls] == ["train", "heldout"]
    assert [arg_of(c, "--k") for c in batch.calls] == ["1", "1"]


def test_confirmation_rejects_when_train_flips_fall_short(repo, monkeypatch):
    """One flip survives the k=1 screen but the k=3 confirmation needs two."""
    monkeypatch.setattr(loop, "invoke_improver", fake_agent(repo))

    class Flaky(FakeBatch):
        def __call__(self, argv):
            if arg_of(argv, "--k") == "3":            # the second flip is flaky at k=3
                self.passing.discard(TRAIN[1])
            return super().__call__(argv)

    batch = Flaky(repo, passing={TRAIN[0], TRAIN[1], TRAIN[2], TRAIN[3], *HELDOUT})
    monkeypatch.setattr(loop, "run_batch_cmd", batch)
    seed_base(repo, solid_fail=[TRAIN[0], TRAIN[1]], solid_pass=[TRAIN[2], *HELDOUT],
              flaky=[TRAIN[3]])
    assert loop.main(["--once"]) == loop.EXIT_OK
    rec = loop.load_archive()[-1]
    assert rec["stage"] == "confirm_k3" and "flips_up=1 < 2" in rec["reason"]
    assert rec["results"]["confirm_k3"]["train"]["flips_up"] == 1
    assert loop.load_best()["condition"] == "C1"      # unchanged


def test_batch_exit_code_is_passed_through(repo, monkeypatch):
    monkeypatch.setattr(loop, "invoke_improver", fake_agent(repo))
    monkeypatch.setattr(loop, "run_batch_cmd", FakeBatch(repo, passing=[], rc=2))
    seed_base(repo, solid_fail=TRAIN, solid_pass=HELDOUT)
    assert loop.main(["--once"]) == 2
    rec = loop.load_archive()[-1]
    assert rec["status"] == "screening"               # infra stop, not a judgement
    assert rec["results"]["train_k1"]["batch_exit"] == 2
    assert loop.current_branch() == "main"


def test_batch_argv_pins_every_protocol_flag(repo, monkeypatch):
    _, _, batch = _screen_run(repo, monkeypatch, passing=[], solid_fail=TRAIN, solid_pass=HELDOUT)
    argv = batch.calls[0]
    assert arg_of(argv, "--condition").startswith("cand-")
    assert arg_of(argv, "--harness-sha") == loop.rev_parse(loop.load_archive()[-1]["sha"])
    assert arg_of(argv, "--model") == "claude-sonnet-5"
    assert arg_of(argv, "--effort") == "medium"
    assert arg_of(argv, "--budget-usd") == "4.0"
    assert arg_of(argv, "--timeout") == "2400"
    assert arg_of(argv, "--workers") == "3"
    assert arg_of(argv, "--subset") == str(repo / "bench" / "subset.json")
    assert arg_of(argv, "--batch-id").endswith("-train1")
    assert "--dry" not in argv


# --- 6. accept -------------------------------------------------------------------------------


def _accept_run(repo, monkeypatch):
    monkeypatch.setattr(loop, "invoke_improver", fake_agent(repo))
    batch = FakeBatch(repo, passing=set(TRAIN) | set(HELDOUT))
    monkeypatch.setattr(loop, "run_batch_cmd", batch)
    seed_base(repo, solid_fail=[TRAIN[0], TRAIN[1]], solid_pass=[TRAIN[2], HELDOUT[0], HELDOUT[1]],
              flaky=[TRAIN[3], HELDOUT[2]])
    code = loop.main(["--once"])
    return code, loop.load_archive()[-1], batch


def test_accept_path(repo, monkeypatch):
    code, rec, batch = _accept_run(repo, monkeypatch)
    assert code == loop.EXIT_OK
    assert rec["status"] == "accepted" and rec["stage"] == "done"
    assert rec["accepted_condition"] == "C2"
    assert rec["results"]["confirm_k3"]["train"]["flips_up"] == 2
    assert rec["results"]["confirm_k3"]["heldout"]["regressions"] == 0
    assert rec["hypothesis"]["category"] == "prompt_rule"
    assert rec["agent"]["total_cost_usd"] == 1.42

    # the three stages, in order, at the protocol's k
    assert [(arg_of(c, "--split"), arg_of(c, "--k")) for c in batch.calls] == [
        ("train", "1"), ("heldout", "1"), ("all", "3")]

    # best.json and the tag now point at the candidate commit
    best = loop.load_best()
    assert best == {"condition": "C2", "sha": rec["sha"], "tag": "C2"}
    assert loop.rev_parse("C2") == rec["sha"]
    assert loop.current_branch() == "main"
    assert porcelain(repo) == []
    # the branch survives so the diff and hypothesis stay inspectable
    assert loop.rev_parse(rec["branch"]) == rec["sha"]


def test_accept_relabels_manifests_with_supersedes(repo, monkeypatch):
    code, rec, batch = _accept_run(repo, monkeypatch)
    cand = rec["cand_condition"]
    raw = [json.loads(ln) for ln in
           (repo / "results" / "runs.jsonl").read_text().splitlines() if ln.strip()]
    relabeled = [r for r in raw if r["condition"] == "C2"]
    originals = [r for r in raw if r["condition"] == cand]

    assert len(relabeled) == len(originals) == (len(TRAIN) + len(HELDOUT)) * 3
    assert rec["relabeled_runs"] == len(relabeled)
    for r in relabeled:
        assert r["supersedes"] in {o["run_id"] for o in originals}
        assert r["run_id"] == f"{r['supersedes']}-as-C2"
        assert "relabeled from" in r["notes"] and "not re-executed" in r["notes"]

    # after supersedes resolution the candidate condition is gone and C2 holds the same runs
    resolved = loop.stats.load_runs(repo / "results" / "runs.jsonl")
    assert not [r for r in resolved if r["condition"] == cand]
    pi = loop.stats.per_instance(resolved, "C2")
    assert set(pi) == set(TRAIN) | set(HELDOUT)
    assert all(k == 3 for _, k in pi.values())
    # nothing was re-run: the accepted condition's cost is the candidate's cost
    assert loop.stats.cost_summary(resolved, "C2")["n_counted"] == len(relabeled)


def test_second_accepted_variant_is_c3(repo, monkeypatch):
    archive = [{"variant_id": "old", "status": "accepted", "stage": "done",
                "accepted_condition": "C2"}]
    loop.save_archive(archive)
    code, rec, _ = _accept_run(repo, monkeypatch)
    assert rec["accepted_condition"] == "C3"
    assert loop.load_best()["condition"] == "C3"


def test_accepted_variant_becomes_the_next_base(repo, monkeypatch):
    _, rec, _ = _accept_run(repo, monkeypatch)
    monkeypatch.setattr(loop, "invoke_improver", fake_agent(repo))
    batch = FakeBatch(repo, passing=[])
    monkeypatch.setattr(loop, "run_batch_cmd", batch)
    loop.main(["--once"])
    second = loop.load_archive()[-1]
    assert second["base_condition"] == "C2" and second["base_sha"] == rec["sha"]
    # the new candidate is built on the accepted harness, not on the seed
    assert loop.git("diff", "--quiet", rec["sha"], second["parent_sha"],
                    "--", "harness").returncode == 0


# --- 7. guards -------------------------------------------------------------------------------


def test_wedge_after_consecutive_rejects(repo, monkeypatch):
    loop.save_archive([{"variant_id": f"v{i}", "status": "rejected", "stage": "smoke",
                        "cand_condition": f"cand-000000{i}", "reason": "no flips"}
                       for i in range(3)])
    monkeypatch.setattr(loop, "invoke_improver", fake_agent(repo))
    monkeypatch.setattr(loop, "run_batch_cmd", FakeBatch(repo, passing=[]))
    seed_base(repo, solid_fail=TRAIN, solid_pass=HELDOUT)

    assert loop.main(["--once"]) == loop.EXIT_WEDGED
    text = (repo / "improver" / "state" / "owner-decisions.md").read_text()
    assert "Improver loop wedged: 4 consecutive rejected variants" in text
    assert "Evidence:" in text and "Consequence:" in text and "DECIDE" in text
    assert "--max-consecutive-rejects 4" in text
    assert loop.current_branch() == "main"


def test_wedge_blocks_the_next_iteration_before_spending(repo, monkeypatch):
    loop.save_archive([{"variant_id": f"v{i}", "status": "rejected", "reason": "no flips"}
                       for i in range(4)])
    monkeypatch.setattr(loop, "invoke_improver", _no_spend)
    monkeypatch.setattr(loop, "run_batch_cmd", _no_batch)
    assert loop.main(["--once"]) == loop.EXIT_WEDGED
    assert "improver-wedge:v3" in (repo / "improver" / "state" / "owner-decisions.md").read_text()


def test_wedge_item_is_written_once(repo):
    streak = [{"variant_id": "v9", "status": "rejected", "reason": "no flips"}]
    assert loop.record_wedge(streak, 4) is True
    assert loop.record_wedge(streak, 4) is False
    text = (repo / "improver" / "state" / "owner-decisions.md").read_text()
    assert text.count("improver-wedge:v9") == 1


def test_an_accepted_variant_clears_the_streak(repo):
    archive = ([{"variant_id": f"v{i}", "status": "rejected"} for i in range(3)]
               + [{"variant_id": "v3", "status": "accepted"}]
               + [{"variant_id": "v4", "status": "rejected"}])
    assert [r["variant_id"] for r in loop.reject_streak(archive)] == ["v4"]


def test_iterations_stop_on_the_first_non_zero_exit(repo, monkeypatch):
    calls = []

    def counting(a):
        calls.append(a)
        return loop.EXIT_OK if len(calls) < 2 else loop.EXIT_WEDGED
    monkeypatch.setattr(loop, "iterate", counting)
    assert loop.main(["--iterations", "5"]) == loop.EXIT_WEDGED
    assert len(calls) == 2


def test_keyboard_interrupt_finishes_the_stage_and_exits_130(repo, monkeypatch):
    monkeypatch.setattr(loop, "invoke_improver", fake_agent(repo))

    def interrupting(argv):
        raise KeyboardInterrupt
    monkeypatch.setattr(loop, "run_batch_cmd", interrupting)
    seed_base(repo, solid_fail=TRAIN, solid_pass=HELDOUT)
    assert loop.main(["--once"]) == loop.EXIT_INTERRUPT
    rec = loop.load_archive()[-1]
    assert rec["status"] == "screening" and "interrupted" in rec["reason"]
    assert loop.current_branch() == "main" and porcelain(repo) == []


def test_usage_errors(repo):
    assert loop.main(["--iterations", "0"]) == loop.EXIT_USAGE
    assert loop.main(["--workers", "0"]) == loop.EXIT_USAGE


# --- 8. state files --------------------------------------------------------------------------


def test_archive_is_restored_from_bak_when_corrupt(repo):
    archive_path = repo / "improver" / "state" / "archive.json"
    good = [{"variant_id": "v1", "status": "accepted"}]
    loop.save_archive(good)                       # creates archive.json (no .bak yet)
    loop.save_archive(good + [{"variant_id": "v2", "status": "rejected"}])
    archive_path.write_text("{ truncated")        # simulate a crash mid-write
    restored = loop.load_archive()
    assert restored == good                       # the .bak is the previous good state
    assert json.loads(archive_path.read_text()) == good


def test_corrupt_archive_without_bak_is_an_error(repo):
    (repo / "improver" / "state" / "archive.json").write_text("{ truncated")
    with pytest.raises(loop.LoopError):
        loop.load_archive()


def test_write_makes_a_bak_before_every_mutation(repo):
    loop.save_archive([{"variant_id": "v1"}])
    loop.save_archive([{"variant_id": "v2"}])
    bak = repo / "improver" / "state" / "archive.json.bak"
    assert json.loads(bak.read_text()) == [{"variant_id": "v1"}]


def test_the_record_is_on_disk_at_every_stage(repo, monkeypatch):
    """A crash between stages must leave the archive readable and the stage recoverable."""
    seen = []
    monkeypatch.setattr(loop, "invoke_improver", fake_agent(repo))

    class Watching(FakeBatch):
        def __call__(self, argv):
            seen.append(loop.load_archive()[-1]["stage"])
            return super().__call__(argv)

    monkeypatch.setattr(loop, "run_batch_cmd",
                        Watching(repo, passing=set(TRAIN) | set(HELDOUT)))
    seed_base(repo, solid_fail=[TRAIN[0], TRAIN[1]], solid_pass=[TRAIN[2], *HELDOUT],
              flaky=[TRAIN[3]])
    assert loop.main(["--once"]) == loop.EXIT_OK
    assert seen == ["train_k1", "heldout_k1", "confirm_k3"]


# --- 9. dry run ------------------------------------------------------------------------------


def test_dry_run_uses_the_stub_and_never_touches_runs_jsonl(repo, monkeypatch):
    monkeypatch.setattr(loop, "invoke_improver", _no_spend)
    batch = FakeBatch(repo, passing=[], dry=True)
    monkeypatch.setattr(loop, "run_batch_cmd", batch)
    before = (repo / "results" / "runs.jsonl").read_text()

    assert loop.main(["--dry", "--once"]) == loop.EXIT_OK
    rec = loop.load_archive()[-1]
    assert rec["dry"] is True and rec["agent"]["stub"] is True
    assert rec["hypothesis"]["expected_flips"] == [TRAIN[0]]
    assert all("--dry" in c for c in batch.calls)
    assert (repo / "results" / "runs.jsonl").read_text() == before
    assert (repo / "results" / "dryruns.jsonl").exists()
    assert loop.current_branch() == "main" and porcelain(repo) == []


# --- 10. safety asserts on the real invocation ------------------------------------------------


def test_the_real_invocation_never_passes_bare_or_skips_permissions(repo, monkeypatch):
    captured = {}

    class Result:
        returncode = 0
        stdout = json.dumps({"subtype": "success", "total_cost_usd": 2.5, "num_turns": 11,
                             "is_error": False, "session_id": "s1"})
        stderr = ""

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured["cwd"] = kw.get("cwd")
        return Result()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    a = loop.build_parser().parse_args([])
    out = REAL_INVOKE(a)
    cmd = captured["cmd"]
    assert "--bare" not in cmd and "--dangerously-skip-permissions" not in cmd
    assert cmd[:3] == ["claude", "-p", "/improve"]
    assert "--permission-mode" in cmd and cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"
    assert cmd[cmd.index("--model") + 1] == "opus"
    assert cmd[cmd.index("--max-budget-usd") + 1] == "8.0"
    assert cmd[cmd.index("--effort") + 1] == "high"
    assert "--no-session-persistence" in cmd and "--output-format" in cmd
    assert captured["cwd"] == str(repo)
    assert out["total_cost_usd"] == 2.5 and out["is_error"] is False


def test_invoke_improver_reports_unparseable_output_as_an_error(repo, monkeypatch):
    class Result:
        returncode = 0
        stdout = "not json"
        stderr = "boom"

    monkeypatch.setattr(loop.subprocess, "run", lambda cmd, **kw: Result())
    out = REAL_INVOKE(loop.build_parser().parse_args([]))
    assert "no JSON result" in out["error"]


def test_two_iterations_in_the_same_second_get_distinct_variants(repo, monkeypatch):
    """utc_stamp has one-second resolution; ids and branches must still not collide."""
    monkeypatch.setattr(loop, "utc_stamp", lambda: "20260904T000000")
    monkeypatch.setattr(loop, "invoke_improver", fake_agent(repo, harness_edits=()))
    assert loop.main(["--iterations", "2"]) == loop.EXIT_OK
    archive = loop.load_archive()
    assert len(archive) == 2
    assert [r["variant_id"] for r in archive] == ["20260904T000000", "20260904T000000-2"]
    assert all(r["status"] == "rejected" for r in archive)
