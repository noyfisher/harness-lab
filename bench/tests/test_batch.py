"""Unit tests for bench.batch: ordering, resume, pause/resume, infra guard, preflight.

Nothing here touches Docker, Claude, or results/runs.jsonl: `bench.run.run_one` is replaced by
a fake and every module-level path in bench.batch is redirected into tmp_path.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from bench import batch, run, stats


# --- fakes -----------------------------------------------------------------


def _manifest(condition, instance, repeat, outcome, *, resolved=None, cost=0.5, wall=1.0, n=0):
    """A manifest shaped like the one run.run_one returns (docs/manifest-schema.md)."""
    return {
        "run_id": f"{condition}-{instance}-r{repeat}-fake{n:03d}",
        "ts": "2026-09-03T00:00:00Z",
        "condition": condition,
        "harness_sha": "f" * 40,
        "cli_version": "2.1.76",
        "model": "sonnet",
        "effort": "medium",
        "credential": "dry",
        "instance_id": instance,
        "repeat": repeat,
        "outcome": outcome,
        "resolved": resolved,
        "num_turns": 3,
        "total_cost_usd": cost,
        "wall_s": wall,
        "notes": "",
        "supersedes": None,
    }


class FakeRunner:
    """Stand-in for run.run_one.

    `script` maps (condition, instance, repeat) -> list of outcomes, consumed one per call;
    anything unscripted gets `default`.  Every start/end is appended to `events` so tests can
    assert on ordering (e.g. that nothing started while the batch was paused).
    """

    def __init__(self, script=None, default="unresolved", hook=None):
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.default = default
        self.hook = hook
        self.calls = []          # namespaces, in call order
        self.events = []         # ("start", key) / ("end", key, outcome) / ("sleep", seconds)
        self._lock = threading.Lock()
        self._n = 0

    def __call__(self, ns):
        key = (ns.condition, ns.instance, ns.repeat)
        with self._lock:
            self.calls.append(ns)
            self.events.append(("start", key))
            self._n += 1
            n = self._n
            queue = self.script.get(key)
            outcome = queue.pop(0) if queue else self.default
        if self.hook is not None:
            self.hook(key)
        with self._lock:
            self.events.append(("end", key, outcome))
        resolved = True if outcome == "resolved" else (False if outcome == "unresolved" else None)
        return _manifest(*key, outcome, resolved=resolved, n=n)

    @property
    def keys(self):
        return [(ns.condition, ns.instance, ns.repeat) for ns in self.calls]

    @property
    def starts(self):
        return [e[1] for e in self.events if e[0] == "start"]


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Redirect every path and every shell-out seam in bench.batch."""
    monkeypatch.setattr(batch, "RUNS", tmp_path / "runs.jsonl")
    monkeypatch.setattr(batch, "DRYRUNS", tmp_path / "dryruns.jsonl")
    monkeypatch.setattr(batch, "BATCH_DIR", tmp_path / "batches")
    monkeypatch.setattr(batch, "SUBSET", tmp_path / "subset.json")
    monkeypatch.setattr(batch, "_git_rev_parse", lambda ref: "a" * 40)
    monkeypatch.setattr(batch, "docker_available", lambda: True)
    monkeypatch.setattr(batch, "image_exists", lambda iid: True)
    sleeps: list[float] = []
    monkeypatch.setattr(batch, "_sleep", lambda s: sleeps.append(s))
    tmp_path.joinpath("sleeps").write_text("")   # keeps tmp_path non-empty for clarity
    return type("Env", (), {"tmp": tmp_path, "sleeps": sleeps, "monkeypatch": monkeypatch})()


def _install(env, fake):
    env.monkeypatch.setattr(run, "run_one", fake)
    return fake


def _write_runs(path: Path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


def _record(env, batch_id):
    return json.loads((env.tmp / "batches" / f"{batch_id}.json").read_text())


# --- 1. work list ----------------------------------------------------------


def test_work_list_is_repeat_major():
    items = batch.work_list("C1", ["b", "a", "c"], 3)
    assert items == [
        ("C1", "a", 0), ("C1", "b", 0), ("C1", "c", 0),
        ("C1", "a", 1), ("C1", "b", 1), ("C1", "c", 1),
        ("C1", "a", 2), ("C1", "b", 2), ("C1", "c", 2),
    ]
    # every instance completes repeat r before any instance starts repeat r+1
    repeats = [r for _, _, r in items]
    assert repeats == sorted(repeats)


def test_work_list_sorts_and_dedupes():
    assert batch.work_list("C0", ["z", "a", "a"], 1) == [("C0", "a", 0), ("C0", "z", 0)]
    assert batch.work_list("C0", ["a"], 0) == []


def test_batch_runs_in_repeat_major_order(env):
    fake = _install(env, FakeRunner())
    rc = batch.main(["--condition", "C1", "--instances", "b,a", "--k", "2",
                     "--workers", "1", "--batch-id", "t"])
    assert rc == batch.EXIT_OK
    assert fake.keys == [("C1", "a", 0), ("C1", "b", 0), ("C1", "a", 1), ("C1", "b", 1)]


# --- 2. resume -------------------------------------------------------------


def test_resume_skips_counted_and_keeps_non_counted(env, capsys):
    _write_runs(env.tmp / "runs.jsonl", [
        _manifest("C0", "a", 0, "no_diff"),                      # counted -> skip
        _manifest("C0", "b", 0, "paused"),                       # not counted -> re-run
        _manifest("C0", "a", 1, "error"),                        # not counted -> re-run
        _manifest("C0", "b", 1, "resolved", resolved=True),      # counted -> skip
        _manifest("C1", "a", 0, "unresolved", resolved=False),   # other condition -> irrelevant
    ])
    fake = _install(env, FakeRunner())
    rc = batch.main(["--condition", "C0", "--instances", "a,b", "--k", "2",
                     "--workers", "1", "--batch-id", "t"])
    assert rc == batch.EXIT_OK
    assert fake.keys == [("C0", "b", 0), ("C0", "a", 1)]
    out = capsys.readouterr().out
    assert "resume: 2 already have a counted run" in out


def test_resume_applies_supersedes(env):
    """A counted run superseded by an infra failure must be re-run, not skipped."""
    first = _manifest("C0", "a", 0, "no_diff")
    correction = _manifest("C0", "a", 0, "error", n=9)
    correction["supersedes"] = first["run_id"]
    _write_runs(env.tmp / "runs.jsonl", [first, correction])
    fake = _install(env, FakeRunner())
    rc = batch.main(["--condition", "C0", "--instances", "a", "--k", "1",
                     "--workers", "1", "--batch-id", "t"])
    assert rc == batch.EXIT_OK
    assert fake.keys == [("C0", "a", 0)]


def test_resume_of_a_complete_batch_runs_nothing(env, capsys):
    _write_runs(env.tmp / "runs.jsonl", [
        _manifest("C0", "a", 0, "no_diff"), _manifest("C0", "a", 1, "unresolved", resolved=False),
    ])
    fake = _install(env, FakeRunner())
    rc = batch.main(["--condition", "C0", "--instances", "a", "--k", "2",
                     "--workers", "1", "--batch-id", "t"])
    assert rc == batch.EXIT_OK
    assert fake.calls == []
    assert "nothing to run" in capsys.readouterr().out


def test_dry_reads_and_resumes_from_dryruns_file(env):
    """--dry must consult dryruns.jsonl, never the counted runs file."""
    _write_runs(env.tmp / "runs.jsonl", [_manifest("C0", "a", 0, "no_diff")])
    _write_runs(env.tmp / "dryruns.jsonl", [_manifest("C0", "b", 0, "no_diff")])
    fake = _install(env, FakeRunner())
    rc = batch.main(["--condition", "C0", "--instances", "a,b", "--k", "1", "--dry",
                     "--workers", "1", "--batch-id", "t"])
    assert rc == batch.EXIT_OK
    assert fake.keys == [("C0", "a", 0)]            # 'b' skipped from dryruns, 'a' still runs
    assert all(ns.dry is True for ns in fake.calls)
    assert _record(env, "t")["results_file"].endswith("dryruns.jsonl")


# --- 3. pause handling -----------------------------------------------------


def test_pause_requeues_the_paused_item_and_sleeps(env):
    fake = _install(env, FakeRunner(script={("C0", "a", 0): ["paused", "unresolved"]}))
    rc = batch.main(["--condition", "C0", "--instances", "a,b", "--k", "1", "--workers", "1",
                     "--pause-minutes", "2", "--batch-id", "t"])
    assert rc == batch.EXIT_OK
    # the paused item is retried first, before any new work starts
    assert fake.starts == [("C0", "a", 0), ("C0", "a", 0), ("C0", "b", 0)]
    assert env.sleeps == [120.0]


def test_pause_starts_no_new_jobs_while_paused(env):
    """With 3 workers and 3 items, the pause must stop the *unstarted* item from starting."""
    gate = threading.Event()

    def hook(key):
        if key == ("C0", "a", 0):
            return
        gate.wait(timeout=2.0)      # b and c linger so the pause is processed while they run

    fake = FakeRunner(script={("C0", "a", 0): ["paused", "unresolved"]}, hook=hook)
    _install(env, fake)
    env.monkeypatch.setattr(batch, "_sleep", lambda s: (fake.events.append(("sleep", s)),
                                                        env.sleeps.append(s)))
    threading.Timer(0.05, gate.set).start()
    rc = batch.main(["--condition", "C0", "--instances", "a,b,c", "--k", "1", "--workers", "2",
                     "--pause-minutes", "1", "--batch-id", "t"])
    assert rc == batch.EXIT_OK
    idx = next(i for i, e in enumerate(fake.events) if e[0] == "sleep")
    started_before_pause_lifted = [e[1] for e in fake.events[:idx] if e[0] == "start"]
    assert ("C0", "c", 0) not in started_before_pause_lifted   # never started while paused
    assert sorted(set(fake.keys)) == [("C0", "a", 0), ("C0", "b", 0), ("C0", "c", 0)]
    assert env.sleeps == [60.0]


def test_pause_budget_exhausted_exits_3(env, capsys):
    fake = _install(env, FakeRunner(default="paused"))
    rc = batch.main(["--condition", "C0", "--instances", "a", "--k", "1", "--workers", "1",
                     "--pause-minutes", "0.5", "--max-pause-hours", "0.01",  # 30s pause, 36s cap
                     "--batch-id", "t"])
    assert rc == batch.EXIT_PAUSE
    assert env.sleeps == [30.0]          # one pause fits under the cap, the second does not
    assert "pause budget exhausted" in capsys.readouterr().out
    assert _record(env, "t")["result"]["exit_code"] == batch.EXIT_PAUSE


# --- 4. infra guard --------------------------------------------------------


def test_infra_guard_trips_at_threshold(env, capsys):
    fake = _install(env, FakeRunner(default="error"))
    rc = batch.main(["--condition", "C0", "--instances", "a,b", "--k", "2", "--workers", "1",
                     "--max-infra-errors", "3", "--batch-id", "t"])
    assert rc == batch.EXIT_INFRA
    assert len(fake.calls) == 3          # stops on the 3rd consecutive failure, not the 4th job
    assert "consecutive infra failures" in capsys.readouterr().out


def test_parse_error_counts_toward_the_infra_guard(env):
    fake = _install(env, FakeRunner(default="parse_error"))
    rc = batch.main(["--condition", "C0", "--instances", "a,b,c", "--k", "1", "--workers", "1",
                     "--max-infra-errors", "2", "--batch-id", "t"])
    assert rc == batch.EXIT_INFRA
    assert len(fake.calls) == 2


def test_infra_error_is_requeued_once_and_the_counter_resets(env):
    fake = _install(env, FakeRunner(script={("C0", "a", 0): ["error", "unresolved"]}))
    rc = batch.main(["--condition", "C0", "--instances", "a,b", "--k", "1", "--workers", "1",
                     "--max-infra-errors", "2", "--batch-id", "t"])
    assert rc == batch.EXIT_OK
    # requeued at the back, so 'b' runs before the retry; its success resets the counter
    assert fake.keys == [("C0", "a", 0), ("C0", "b", 0), ("C0", "a", 0)]
    assert _record(env, "t")["result"]["requeued"] == 1


def test_infra_error_is_requeued_only_once(env):
    """A second failure of the same item is not re-queued a second time."""
    fake = _install(env, FakeRunner(script={("C0", "a", 0): ["error", "error", "unresolved"]}))
    rc = batch.main(["--condition", "C0", "--instances", "a,b", "--k", "1", "--workers", "1",
                     "--max-infra-errors", "9", "--batch-id", "t"])
    assert rc == batch.EXIT_OK
    assert fake.keys == [("C0", "a", 0), ("C0", "b", 0), ("C0", "a", 0)]
    assert _record(env, "t")["result"]["outcomes"] == {"error": 2, "unresolved": 1}


def test_run_one_exception_is_recorded_as_an_error_not_a_crash(env):
    def boom(ns):
        raise SystemExit("agent image missing: harness-lab/agent.arm64.a")

    env.monkeypatch.setattr(run, "run_one", boom)
    rc = batch.main(["--condition", "C0", "--instances", "a", "--k", "1", "--workers", "1",
                     "--max-infra-errors", "2", "--batch-id", "t"])
    assert rc == batch.EXIT_INFRA
    rec = _record(env, "t")
    assert rec["result"]["outcomes"] == {"error": 2}


# --- 5. harness sha --------------------------------------------------------


def test_harness_sha_resolved_once_and_shared_by_every_job(env):
    calls = []

    def rev_parse(ref):
        calls.append(ref)
        return "b" * 40

    env.monkeypatch.setattr(batch, "_git_rev_parse", rev_parse)
    fake = _install(env, FakeRunner())
    rc = batch.main(["--condition", "C1", "--instances", "a,b", "--k", "3", "--workers", "1",
                     "--harness-sha", "HEAD", "--batch-id", "t"])
    assert rc == batch.EXIT_OK
    assert calls == ["HEAD"]                                   # resolved exactly once
    assert len(fake.calls) == 6
    assert {ns.harness_sha for ns in fake.calls} == {"b" * 40}  # same full sha for every job
    assert _record(env, "t")["harness_sha"] == "b" * 40


def test_unresolvable_harness_sha_fails_before_anything_runs(env, capsys):
    env.monkeypatch.setattr(batch, "_git_rev_parse", lambda ref: "")
    fake = _install(env, FakeRunner())
    rc = batch.main(["--condition", "C1", "--instances", "a", "--k", "1", "--batch-id", "t"])
    assert rc == batch.EXIT_PREFLIGHT
    assert fake.calls == []
    assert "cannot resolve --harness-sha" in capsys.readouterr().out


# --- 6. preflight ----------------------------------------------------------


def test_preflight_missing_image_lists_it_and_runs_nothing(env, capsys):
    env.monkeypatch.setattr(batch, "image_exists", lambda iid: iid != "b")
    fake = _install(env, FakeRunner())
    rc = batch.main(["--condition", "C0", "--instances", "a,b", "--k", "2", "--batch-id", "t"])
    assert rc == batch.EXIT_PREFLIGHT
    assert fake.calls == []                                  # nothing half-ran
    out = capsys.readouterr().out
    assert "preflight FAILED" in out
    assert "harness-lab/agent.arm64.b" in out
    assert "harness-lab/agent.arm64.a" not in out
    assert not (env.tmp / "batches" / "t.log").exists()


def test_preflight_fails_when_docker_is_down(env, capsys):
    env.monkeypatch.setattr(batch, "docker_available", lambda: False)
    fake = _install(env, FakeRunner())
    rc = batch.main(["--condition", "C0", "--instances", "a", "--k", "1", "--batch-id", "t"])
    assert rc == batch.EXIT_PREFLIGHT
    assert fake.calls == []
    assert "docker daemon not reachable" in capsys.readouterr().out


def test_preflight_checks_every_instance_in_the_work_list(env):
    seen = []
    env.monkeypatch.setattr(batch, "image_exists", lambda iid: (seen.append(iid), True)[1])
    _install(env, FakeRunner())
    batch.main(["--condition", "C0", "--instances", "a,b,c", "--k", "3", "--workers", "1",
                "--batch-id", "t"])
    assert sorted(seen) == ["a", "b", "c"]     # once per instance, not once per job


# --- 7. splits -------------------------------------------------------------


@pytest.fixture
def subset(env):
    path = env.tmp / "subset.json"
    path.write_text(json.dumps({"train": ["t2", "t1"], "heldout": ["h1"]}))
    return path


@pytest.mark.parametrize("split,expected", [
    ("train", ["t1", "t2"]),
    ("heldout", ["h1"]),
    ("all", ["h1", "t1", "t2"]),
])
def test_split_selection(env, subset, split, expected):
    fake = _install(env, FakeRunner())
    rc = batch.main(["--condition", "C0", "--subset", str(subset), "--split", split,
                     "--k", "1", "--workers", "1", "--batch-id", "t"])
    assert rc == batch.EXIT_OK
    assert [ns.instance for ns in fake.calls] == expected
    assert _record(env, "t")["instances"] == expected


def test_instances_override_the_subset_entirely(env, subset):
    fake = _install(env, FakeRunner())
    batch.main(["--condition", "C0", "--subset", str(subset), "--split", "all",
                "--instances", "x,y", "--k", "1", "--workers", "1", "--batch-id", "t"])
    assert [ns.instance for ns in fake.calls] == ["x", "y"]
    rec = _record(env, "t")
    assert rec["split"] == "instances" and rec["subset"] is None


def test_missing_subset_file_is_a_clear_preflight_failure(env, capsys):
    fake = _install(env, FakeRunner())
    rc = batch.main(["--condition", "C0", "--split", "train", "--k", "1", "--batch-id", "t"])
    assert rc == batch.EXIT_PREFLIGHT
    assert fake.calls == []
    assert "cannot read split 'train'" in capsys.readouterr().out


# --- 8. job namespace, records, concurrency --------------------------------


def test_job_namespace_mirrors_run_argparse(env):
    """The fields batch passes must be exactly the fields run.py's parser produces."""
    captured = {}

    def capture(ns):
        captured["run"] = ns
        return _manifest(ns.condition, ns.instance, ns.repeat, "no_diff")

    env.monkeypatch.setattr(run, "run_one", capture)
    run.main(["--instance", "a", "--condition", "C0"])
    from_run = set(vars(captured["run"]))

    fake = _install(env, FakeRunner())
    batch.main(["--condition", "C0", "--instances", "a", "--k", "1", "--workers", "1",
                "--model", "sonnet", "--effort", "high", "--budget-usd", "2.5",
                "--timeout", "1200", "--batch-id", "t"])
    ns = fake.calls[0]
    assert set(vars(ns)) == from_run
    assert (ns.model, ns.effort, ns.budget_usd, ns.timeout) == ("sonnet", "high", 2.5, 1200)
    assert (ns.grade_timeout, ns.network, ns.no_grade, ns.keep_tmp, ns.dry) == (1800, "bridge", False, False, False)


def test_batch_log_and_record_are_written(env):
    _install(env, FakeRunner(script={("C0", "a", 0): ["resolved"]}))
    rc = batch.main(["--condition", "C0", "--instances", "a,b", "--k", "1", "--workers", "1",
                     "--model", "sonnet", "--effort", "medium", "--batch-id", "t"])
    assert rc == batch.EXIT_OK
    lines = (env.tmp / "batches" / "t.log").read_text().splitlines()
    assert len(lines) == 2
    assert all(line.count("\t") == 8 for line in lines)
    assert "C0\ta\tr0\tresolved\tresolved=True" in lines[0]
    rec = _record(env, "t")
    for key in ("batch_id", "condition", "harness_sha", "split", "k", "instances", "model",
                "effort", "budget_usd", "timeout", "workers", "started", "ended", "result"):
        assert key in rec, key
    assert rec["result"]["resolved"] == 1
    assert rec["result"]["outcomes"] == {"resolved": 1, "unresolved": 1}
    assert len(rec["run_ids"]) == 2


def test_summary_counts_match_stats_counting_rules(env, capsys):
    _install(env, FakeRunner(script={
        ("C0", "a", 0): ["resolved"], ("C0", "b", 0): ["timeout"], ("C0", "c", 0): ["paused"],
    }, default="unresolved"))
    batch.main(["--condition", "C0", "--instances", "a,b,c", "--k", "1", "--workers", "1",
                "--pause-minutes", "0.01", "--batch-id", "t"])
    rec = _record(env, "t")["result"]
    # paused does not count toward k; its retry (unresolved) does
    assert rec["counted"] == 3 and rec["resolved"] == 1 and rec["infra_failures"] == 1
    assert stats.COUNTED_OUTCOMES.issuperset({"resolved", "timeout", "unresolved"})
    assert "total cost" in capsys.readouterr().out


def test_workers_run_concurrently_up_to_the_cap(env):
    barrier = threading.Barrier(3)
    live = {"now": 0, "max": 0}
    lock = threading.Lock()

    def hook(key):
        with lock:
            live["now"] += 1
            live["max"] = max(live["max"], live["now"])
        try:
            barrier.wait(timeout=5)
        except threading.BrokenBarrierError:
            pass
        with lock:
            live["now"] -= 1

    fake = FakeRunner(hook=hook)
    _install(env, fake)
    rc = batch.main(["--condition", "C0", "--instances", "a,b,c,d,e,f", "--k", "1",
                     "--workers", "3", "--batch-id", "t"])
    assert rc == batch.EXIT_OK
    assert live["max"] == 3            # the barrier only releases if 3 really ran at once
    assert len(fake.calls) == 6


def test_single_worker_never_overlaps(env):
    live = {"now": 0, "max": 0}
    lock = threading.Lock()

    def hook(key):
        with lock:
            live["now"] += 1
            live["max"] = max(live["max"], live["now"])
        time.sleep(0.01)
        with lock:
            live["now"] -= 1

    _install(env, FakeRunner(hook=hook))
    batch.main(["--condition", "C0", "--instances", "a,b,c", "--k", "1", "--workers", "1",
                "--batch-id", "t"])
    assert live["max"] == 1


def test_bad_batch_id_is_rejected(env):
    fake = _install(env, FakeRunner())
    assert batch.main(["--condition", "C0", "--instances", "a", "--k", "1",
                       "--batch-id", "../escape"]) == batch.EXIT_PREFLIGHT
    assert fake.calls == []


def test_nothing_is_written_outside_tmp_path(env):
    """Guard: a batch run must not touch the real results/ tree."""
    real = batch.ROOT / "results"
    before = sorted((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in real.rglob("*"))
    _install(env, FakeRunner())
    batch.main(["--condition", "C0", "--instances", "a,b", "--k", "2", "--workers", "1",
                "--batch-id", "t"])
    after = sorted((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in real.rglob("*"))
    assert before == after
