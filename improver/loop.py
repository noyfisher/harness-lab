"""The improvement loop: propose a harness variant, screen it cheaply, confirm it, accept or reject.

The harness is code (``harness/``) and a variant is a git commit.  This module owns git, all
disk state, and every decision; the improver *agent* (a ``claude -p`` session on the host,
driven by ``.claude/commands/improve.md``) only edits files.  Nothing the agent says is
trusted -- what it wrote is re-derived from ``git status`` and re-validated here.

One iteration (``python -m improver.loop --once``)::

    base            best.json -> (condition, sha); C1/harness-seed until something is accepted
    propose         branch cand/<utc>, harness/ reset to the base variant, then `claude -p /improve`
    validate        only harness/ touched; HYPOTHESIS.json valid; a real file changed;
                    no hidden test name leaked; `claude agents` still loads the harness
    train  k=1      reject unless flips_up >= 1 and regressions == 0
    heldout k=1     reject on any regression
    confirm k=3     accept iff held-out regressions == 0 and train flips_up >= 2
    accept          relabel the candidate's manifests as C<n>, tag the commit, update best.json

Why two cheap screens and one real decision
-------------------------------------------
A single run of a SWE-bench instance is a coin flip with unknown bias: run-to-run variance on
Verified exceeds 1.5 points even at temperature 0, and on a 40-instance subset one run carries a
CI of roughly +/-13 points.  So a k=1 result cannot decide anything -- an instance that passes
once may be flaky, and an instance that fails once may be solid.

The k=1 stages are therefore **filters, not tests**.  They are one-sided on purpose: a candidate
that produces zero solid_fail -> pass flips at k=1 almost certainly produces zero at k=3 (you
cannot flip three coins heads without flipping one), and a candidate that breaks a *base
solid_pass* instance on its very first attempt is cheap evidence of real damage.  Both screens
compare the candidate's k=1 result against the **base condition's k=3 classes**, which are the
sharp side of the comparison; that asymmetry is the whole point -- we spend the repeats on the
baseline once and reuse them for every candidate.

Only the k=3 confirmation applies the protocol's accept rule (``docs/protocol.md``, "Improver
accept rule"): both conditions classified at k=3 on both splits, accept iff held-out
``regressions == 0`` and train ``flips_up >= 2``.  Numbers from the k=1 screens are recorded in
the archive as screening statistics and are never reported as results.  The k=1 screens can only
ever *reject*; nothing is accepted without the confirmation.

State
-----
``improver/state/archive.json`` (every variant, accepted or not) and ``improver/state/best.json``
(the current best condition/sha/tag).  Both are written with the team-auto protocol: copy to
``.bak``, write, re-parse, restore the ``.bak`` on failure.  Rejected variants keep their branch
and their record; the archive is the search history, not a log of winners.

Exit codes
----------
0 iteration completed (accepted or rejected), 1 usage error, 2/3/130 passed through from
``bench.batch`` (infra guard / pause budget / interrupt), 4 dirty working tree or git failure,
5 ``.claude/commands/improve.md`` missing (abort before spending anything), 6 wedged
(``--max-consecutive-rejects``; an item is appended to ``improver/state/owner-decisions.md``),
7 the improver agent invocation failed, 130 interrupted.

Never ``--bare`` and never ``--dangerously-skip-permissions``: the improver agent runs on the
host, in the real repo, with ``--permission-mode acceptEdits`` and a dollar budget.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from bench import batch as bench_batch
from bench import stats

# --- module-level paths (tests redirect every one of these into a temp repo) -----------------

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "improver" / "state"
ARCHIVE = STATE_DIR / "archive.json"
BEST = STATE_DIR / "best.json"
OWNER_DECISIONS = STATE_DIR / "owner-decisions.md"
HARNESS = ROOT / "harness"
HYPOTHESIS = HARNESS / "HYPOTHESIS.json"
#: Repo-relative path of the hypothesis file (git pathspecs are relative to the repo root).
HYPOTHESIS_REL = "harness/HYPOTHESIS.json"
SCHEMA = ROOT / "improver" / "hypothesis.schema.json"  # loop-owned; harness/ is reset to the base sha per candidate
IMPROVE_COMMAND = ROOT / ".claude" / "commands" / "improve.md"
RUNS = ROOT / "results" / "runs.jsonl"
DRYRUNS = ROOT / "results" / "dryruns.jsonl"
SUBSET = ROOT / "bench" / "subset.json"
INSTANCES = ROOT / "bench" / "instances.json"

SEED_TAG = "harness-seed"
SEED_CONDITION = "C1"
#: Paths a dirty-tree check ignores.  results/ is owned by the batch runner, which appends to it
#: live (a C1 batch may be running while the loop iterates); improver/state/ is owned by this
#: module and is rewritten at every stage.  Neither is ever part of a candidate.
DIRTY_IGNORE = ("results/", "improver/state/")
#: Agents the harness-load smoke check must list (a malformed frontmatter fails here).
REQUIRED_AGENTS = ("lead",)
#: Shortest string accepted as a leak needle; every real node id and instance id clears it.
MIN_NEEDLE = 8

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_DIRTY = 4
EXIT_NO_COMMAND = 5
EXIT_WEDGED = 6
EXIT_AGENT = 7
EXIT_INTERRUPT = 130


class LoopError(RuntimeError):
    """A precondition the loop refuses to work around (git, state, schema)."""


def log(msg: str) -> None:
    print(f"[improver] {msg}", flush=True)


def utc_stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%S", time.gmtime())


def utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --- 1. git ---------------------------------------------------------------------------------


def git(*args: str):
    """Run git in the repo root.  ROOT is read at call time so tests can redirect it."""
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


def git_ok(*args: str) -> str:
    r = git(*args)
    if r.returncode != 0:
        raise LoopError(f"git {' '.join(args)} failed: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def rev_parse(ref: str) -> str:
    r = git("rev-parse", "--verify", f"{ref}^{{commit}}")
    return r.stdout.strip() if r.returncode == 0 else ""


def current_branch() -> str:
    name = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    return "" if name in ("", "HEAD") else name


def parse_porcelain_z(data: str) -> list[tuple[str, str, str | None]]:
    """[(xy, path, orig_path_or_None)] from ``git status --porcelain -z``.

    ``-z`` avoids every quoting question; a rename/copy entry is followed by one extra
    NUL-terminated field holding the original path, and both paths count as changed.
    """
    out: list[tuple[str, str, str | None]] = []
    fields = iter([f for f in data.split("\0")])
    for entry in fields:
        if len(entry) < 4:
            continue
        xy, path = entry[:2], entry[3:]
        orig = next(fields, "") if ("R" in xy or "C" in xy) else None
        out.append((xy, path, orig or None))
    return out


def working_tree_changes(ignore: tuple[str, ...] = DIRTY_IGNORE) -> list[tuple[str, str]]:
    """[(xy, path)] for every changed path, minus the ignored prefixes, order preserved."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for xy, path, orig in parse_porcelain_z(git("status", "--porcelain", "-z").stdout):
        for p in (path, orig):
            if not p or p in seen or any(p.startswith(pre) for pre in ignore):
                continue
            seen.add(p)
            out.append((xy, p))
    return out


def revert_paths(paths: list[str]) -> None:
    """Undo changes to specific paths: tracked ones are checked out, untracked ones removed.

    Deliberately path-scoped -- a blanket ``git checkout -- . && git clean -fd`` would also throw
    away the candidate's harness/ edits, which are the evidence we are about to record.  Anything
    the agent staged is unstaged first, so a ``git add``-ed new file is classified as untracked
    and removed rather than silently surviving into the candidate commit.
    """
    if not paths:
        return
    git("reset", "-q", "HEAD", "--", *paths)
    entries = parse_porcelain_z(git("status", "--porcelain", "-z", "--", *paths).stdout)
    untracked = [p for xy, p, _ in entries if xy == "??"]
    for xy, p, _ in entries:
        if xy != "??":
            git("checkout", "--", p)
    if untracked:
        git("clean", "-fdq", "--", *untracked)


# --- 2. disk state (.bak protocol from ~/.claude/team-auto/loop-prompt.md) -------------------


def _bak(path) -> Path:
    return Path(str(path) + ".bak")


def read_json_state(path, default=None):
    """Parse ``path``; on corruption restore its ``.bak`` and use that instead."""
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        bak = _bak(p)
        if not bak.exists():
            raise LoopError(f"{p} is corrupt ({exc}) and there is no {bak.name} to restore")
        try:
            data = json.loads(bak.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc2:
            raise LoopError(f"{p} and {bak.name} are both corrupt ({exc2})") from exc2
        shutil.copy2(bak, p)
        log(f"state: {p.name} was corrupt ({exc.__class__.__name__}); restored from {bak.name}")
        return data


def write_json_state(path, data) -> None:
    """Copy to ``.bak``, write, re-parse; restore the ``.bak`` if the write did not parse."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    bak = _bak(p)
    if p.exists():
        shutil.copy2(p, bak)
    p.write_text(json.dumps(data, indent=1) + "\n")
    try:
        json.loads(p.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        if bak.exists():
            shutil.copy2(bak, p)
            raise LoopError(f"invalid JSON written to {p} ({exc}); restored {bak.name}") from exc
        raise LoopError(f"invalid JSON written to {p} ({exc})") from exc


def load_archive() -> list[dict]:
    data = read_json_state(ARCHIVE, default=[])
    if not isinstance(data, list):
        raise LoopError(f"{ARCHIVE} must hold a JSON list of variant records")
    return data


def save_archive(records: list[dict]) -> None:
    write_json_state(ARCHIVE, records)


def upsert(records: list[dict], record: dict) -> list[dict]:
    """Replace the record with the same ``variant_id``, or append it."""
    for i, existing in enumerate(records):
        if existing.get("variant_id") == record.get("variant_id"):
            records[i] = record
            return records
    records.append(record)
    return records


def load_best() -> dict:
    """The current best variant; created lazily from the ``harness-seed`` tag on first use."""
    data = read_json_state(BEST, default=None)
    if data is None:
        sha = rev_parse(SEED_TAG)
        if not sha:
            raise LoopError(f"no {BEST} and tag {SEED_TAG!r} does not resolve; cannot pick a base")
        data = {"condition": SEED_CONDITION, "sha": sha, "tag": SEED_TAG}
        write_json_state(BEST, data)
        log(f"best.json initialized: {SEED_CONDITION} at {sha[:7]} ({SEED_TAG})")
    return data


# --- 3. hypothesis validation ---------------------------------------------------------------

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def validate_schema(doc, schema: dict, where: str = "$") -> list[str]:
    """Validate against the subset of draft-07 the hypothesis schema uses.

    ``jsonschema`` is not a dependency of this project (requirements.txt is pinned and the
    benchmark does not need it), so the keywords actually used by
    ``improver/hypothesis.schema.json`` are checked directly: type, required,
    properties, additionalProperties, enum, minLength/maxLength, minItems/maxItems,
    uniqueItems, items, pattern.  Returns a list of human-readable errors ([] means valid).
    """
    errs: list[str] = []
    expected = schema.get("type")
    if expected and not _TYPES[expected](doc):
        return [f"{where}: expected {expected}, got {type(doc).__name__}"]
    if "enum" in schema and doc not in schema["enum"]:
        errs.append(f"{where}: {doc!r} is not one of {schema['enum']}")
    if isinstance(doc, str):
        if "minLength" in schema and len(doc) < schema["minLength"]:
            errs.append(f"{where}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(doc) > schema["maxLength"]:
            errs.append(f"{where}: longer than {schema['maxLength']} characters")
        if "pattern" in schema and not re.search(schema["pattern"], doc):
            errs.append(f"{where}: {doc!r} does not match {schema['pattern']}")
    if isinstance(doc, list):
        if "minItems" in schema and len(doc) < schema["minItems"]:
            errs.append(f"{where}: needs at least {schema['minItems']} item(s)")
        if "maxItems" in schema and len(doc) > schema["maxItems"]:
            errs.append(f"{where}: at most {schema['maxItems']} item(s) allowed")
        if schema.get("uniqueItems") and len(doc) != len({json.dumps(v, sort_keys=True) for v in doc}):
            errs.append(f"{where}: items must be unique")
        if "items" in schema:
            for i, item in enumerate(doc):
                errs += validate_schema(item, schema["items"], f"{where}[{i}]")
    if isinstance(doc, dict):
        props = schema.get("properties") or {}
        for key in schema.get("required") or []:
            if key not in doc:
                errs.append(f"{where}: missing required property {key!r}")
        if schema.get("additionalProperties") is False:
            for key in doc:
                if key not in props:
                    errs.append(f"{where}: unexpected property {key!r}")
        for key, sub in props.items():
            if key in doc:
                errs += validate_schema(doc[key], sub, f"{where}.{key}")
    return errs


def validate_hypothesis(doc, schema: dict, train_ids, harness_dir) -> list[str]:
    """Schema errors plus the three constraints JSON Schema cannot express."""
    errs = validate_schema(doc, schema)
    if errs or not isinstance(doc, dict):
        return errs
    repo = Path(harness_dir).parent
    for path in doc.get("target_files") or []:
        if isinstance(path, str) and not (repo / path).exists():
            errs.append(f"$.target_files: {path!r} does not exist")
    known = set(train_ids)
    for iid in doc.get("expected_flips") or []:
        if iid not in known:
            errs.append(f"$.expected_flips: {iid!r} is not a train-split instance id")
    return errs


# --- 4. leak check --------------------------------------------------------------------------


def leak_needles(instances_path, train_ids) -> tuple[set[str], set[str]]:
    """``(test_needles, id_needles)`` for the *train* split -- strings the harness must not name.

    ``test_needles`` are every FAIL_TO_PASS / PASS_TO_PASS node id, plus the bare test name after
    ``::`` when it is long enough to be unambiguous, so
    ``test_separable[compound_model6-result6]`` is caught even without its file path.  A harness
    that names the hidden tests is not a better harness, it is a leak.

    ``id_needles`` are the train instance ids.  They are kept separate because
    ``HYPOTHESIS.json`` is *required* to name train instance ids in ``expected_flips``: they are
    checked everywhere under harness/ except in that one file (see :func:`find_leaks` callers).
    """
    wanted = set(train_ids)
    id_needles = {i for i in wanted if len(i) >= MIN_NEEDLE}
    test_needles: set[str] = set()
    data = json.loads(Path(instances_path).read_text())
    for rec in data:
        if rec.get("instance_id") not in wanted:
            continue
        for field in ("FAIL_TO_PASS", "PASS_TO_PASS"):
            value = rec.get(field)
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = [value]
            for name in value or []:
                if not isinstance(name, str):
                    continue
                name = name.strip()
                if len(name) >= MIN_NEEDLE:
                    test_needles.add(name)
                tail = name.split("::")[-1]
                if len(tail) >= 12:
                    test_needles.add(tail)
    return test_needles, id_needles


def added_lines(base_sha: str, head_sha: str, pathspec: list[str]) -> list[str]:
    """Lines the candidate *added* under ``pathspec``.

    Removed lines are not checked: a line that only exists in the base cannot be something the
    candidate leaked, and rejecting a candidate for deleting a pre-existing string would be both
    confusing and backwards.
    """
    diff = git("diff", "--unified=0", f"{base_sha}..{head_sha}", "--", *pathspec).stdout
    return [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]


def find_leaks(lines, needles) -> list[str]:
    hits: list[str] = []
    for line in lines:
        for needle in needles:
            if needle in line:
                hits.append(f"{needle!r} in {line.strip()[:120]!r}")
                break
        if len(hits) >= 5:
            break
    return hits


def leak_check(base_sha: str, head_sha: str, instances_path, train_ids) -> list[str]:
    """Every leak hit in the candidate's added harness lines, HYPOTHESIS.json handled apart."""
    test_needles, id_needles = leak_needles(instances_path, train_ids)
    body = added_lines(base_sha, head_sha, ["harness", f":(exclude){HYPOTHESIS_REL}"])
    hypothesis = added_lines(base_sha, head_sha, [HYPOTHESIS_REL])
    return (find_leaks(body, test_needles | id_needles)
            + find_leaks(hypothesis, test_needles))


# --- 5. seams (monkeypatched in tests; the only places this module spends or shells out) -----


def smoke_check(harness_dir) -> tuple[int, str]:
    """``CLAUDE_CONFIG_DIR=<harness> claude agents`` -- does the harness still load at all?"""
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(harness_dir))
    try:
        r = subprocess.run(["claude", "agents"], capture_output=True, text=True,
                           env=env, cwd=str(ROOT), timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def clean_harness_state(harness_dir) -> None:
    """Delete what a ``claude`` invocation writes into a config dir (both are gitignored)."""
    Path(harness_dir, ".claude.json").unlink(missing_ok=True)
    shutil.rmtree(Path(harness_dir, "backups"), ignore_errors=True)


def generate_dossiers(base_condition: str, runs_path=None) -> int:
    """Write results/dossiers/<base>/ for the base condition's TRAIN solid_fail + flaky instances.

    The improver reads these instead of raw traces. Train split only: the improver must never see
    held-out failures.
    """
    from bench import dossier as _dossier
    args = ["--condition", base_condition, "--classes", "solid_fail,flaky", "--split", "train"]
    if runs_path is not None:
        args += ["--runs", str(runs_path)]
    return _dossier.main(args)


def invoke_improver(a) -> dict:
    """Run the improver agent on the HOST.  It only edits files; every check happens here."""
    base = load_best().get("condition", "C1")
    try:
        generate_dossiers(base)
    except Exception as exc:  # dossiers are advisory input; record and continue
        log(f"dossier generation failed for {base}: {type(exc).__name__}: {exc}")
    cmd = [
        "claude", "-p", "/improve",
        "--model", a.improver_model,
        "--effort", "high",
        "--max-budget-usd", str(a.improver_budget),
        "--permission-mode", "acceptEdits",
        "--setting-sources", "project,local",  # skip the user-level Stop hook and allowlists
        "--output-format", "json",
        "--no-session-persistence",
    ]
    assert "--bare" not in cmd, "non-negotiable 6: --bare skips agents and subscription auth"
    assert "--dangerously-skip-permissions" not in cmd, "never on the host"
    log(f"agent: {' '.join(cmd)} (cwd {ROOT})")
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=a.agent_timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"rc": -1, "is_error": True, "error": f"{type(exc).__name__}: {exc}",
                "total_cost_usd": None, "num_turns": None}
    result = None
    try:
        parsed = json.loads(r.stdout or "")
        result = parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        result = None
    out = {
        "rc": r.returncode,
        "is_error": bool(r.returncode != 0 or (result or {}).get("is_error")),
        "subtype": (result or {}).get("subtype"),
        "session_id": (result or {}).get("session_id"),
        "num_turns": (result or {}).get("num_turns"),
        "total_cost_usd": (result or {}).get("total_cost_usd"),
    }
    if result is None:
        out["error"] = f"no JSON result (rc={r.returncode}): {(r.stderr or r.stdout)[-400:]}"
    return out


def stub_improver(a) -> dict:
    """``--dry`` stand-in: a valid HYPOTHESIS.json and one trivial harness edit, no spend."""
    train = bench_batch.load_split(SUBSET, "train")
    target = Path(HARNESS) / "CLAUDE.md"
    if not target.exists():
        target.write_text("# harness rules\n")
    with open(target, "a") as fh:
        fh.write(f"\n<!-- improver dry run {utc_iso()}: plumbing exercise, no behaviour change -->\n")
    doc = {
        "hypothesis": "Dry-run stub: append an inert comment to harness/CLAUDE.md so the loop "
                      "plumbing can be exercised end to end without spending anything.",
        "target_files": ["harness/CLAUDE.md"],
        "expected_flips": train[:1] or ["dry__dry-0"],
        "rationale": "Not a real hypothesis. --dry exists to prove that git, validation, the "
                     "batch wiring and the archive all work before any usage is burned.",
        "category": "other",
    }
    Path(HYPOTHESIS).write_text(json.dumps(doc, indent=2) + "\n")
    return {"rc": 0, "is_error": False, "subtype": "dry", "num_turns": 0, "total_cost_usd": 0.0,
            "stub": True}


def run_batch_cmd(argv: list[str]) -> int:
    """Call ``bench.batch`` in-process.  Tests replace this; it is the only benchmark spend."""
    return bench_batch.main(list(argv))


# --- 6. screen arithmetic -------------------------------------------------------------------


def transitions(runs, base_condition: str, cand_condition: str, instance_ids) -> dict:
    """Class transitions from ``base_condition`` to ``cand_condition`` over ``instance_ids``.

    ``flips_up`` = base solid_fail -> candidate solid_pass, ``regressions`` = base solid_pass ->
    candidate anything else, ``flaky_gains`` = base flaky -> candidate solid_pass.  At k=1 a
    candidate's solid_pass simply means "the one run passed" and solid_fail "it failed", which is
    exactly the screen's question; at k=3 these are the protocol's classes on both sides.
    """
    wanted = set(instance_ids)
    base_pi = {i: v for i, v in stats.per_instance(runs, base_condition).items() if i in wanted}
    cand_pi = {i: v for i, v in stats.per_instance(runs, cand_condition).items() if i in wanted}
    base_cls, cand_cls = stats.classes(base_pi), stats.classes(cand_pi)
    common = sorted(set(base_cls) & set(cand_cls))

    flips_up, regressions, flaky_gains = [], [], []
    for iid in common:
        b, c = base_cls[iid], cand_cls[iid]
        if b == "solid_fail" and c == "solid_pass":
            flips_up.append(iid)
        if b == "solid_pass" and c != "solid_pass":
            regressions.append(iid)
        if b == "flaky" and c == "solid_pass":
            flaky_gains.append(iid)
    ks_base = [k for _, k in base_pi.values()]
    ks_cand = [k for _, k in cand_pi.values()]
    return {
        "base_condition": base_condition,
        "cand_condition": cand_condition,
        "n_requested": len(wanted),
        "n_compared": len(common),
        "n_base_only": len(set(base_cls) - set(cand_cls)),
        "n_cand_missing": sorted(set(wanted) - set(cand_cls))[:10],
        "k_base": [min(ks_base), max(ks_base)] if ks_base else None,
        "k_cand": [min(ks_cand), max(ks_cand)] if ks_cand else None,
        "base_classes": {c: sum(1 for i in common if base_cls[i] == c) for c in stats.CLASS_ORDER},
        "cand_classes": {c: sum(1 for i in common if cand_cls[i] == c) for c in stats.CLASS_ORDER},
        "flips_up": len(flips_up),
        "regressions": len(regressions),
        "flaky_gains": len(flaky_gains),
        "flips_up_ids": flips_up,
        "regression_ids": regressions,
        "flaky_gain_ids": flaky_gains,
    }


# --- 7. wedge guard -------------------------------------------------------------------------


def reject_streak(archive: list[dict]) -> list[dict]:
    """The trailing run of rejected records (an accepted one, or a crash, breaks the streak)."""
    streak: list[dict] = []
    for rec in reversed(archive):
        if rec.get("status") != "rejected":
            break
        streak.append(rec)
    return list(reversed(streak))


def record_wedge(streak: list[dict], limit: int) -> bool:
    """Append an evidence+consequence item to owner-decisions.md.  False if already recorded."""
    last = streak[-1] if streak else {}
    marker = f"improver-wedge:{last.get('variant_id', 'unknown')}"
    path = Path(OWNER_DECISIONS)
    existing = path.read_text() if path.exists() else "# Owner decisions queue\n"
    if marker in existing:
        return False
    evidence = "; ".join(
        f"{r.get('variant_id')} ({r.get('cand_condition') or 'no commit'}) — "
        f"{(r.get('reason') or '?')}" for r in streak
    )
    item = (
        f"\n- [{time.strftime('%Y-%m-%d', time.gmtime())}] **Improver loop wedged: "
        f"{len(streak)} consecutive rejected variants** (`{marker}`). DECIDE.\n"
        f"  - Evidence: {evidence} (full records in `improver/state/archive.json`).\n"
        f"  - Consequence: `python -m improver.loop` now refuses to propose and spends nothing "
        f"until this is decided; the cap is `--max-consecutive-rejects {limit}`.\n"
        f"  - Options: revise `.claude/commands/improve.md` (the hypotheses being generated are "
        f"not working), raise the cap and keep searching, or stop the loop and write up "
        f"\"no variant beat baseline beyond noise\" as the finding.\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(item)
    return True


# --- 8. one iteration -----------------------------------------------------------------------


def _runs_path(a) -> Path:
    """``--dry`` batches read and write results/dryruns.jsonl; runs.jsonl is never touched."""
    return Path(DRYRUNS if a.dry else RUNS)


def _batch_argv(a, cand_condition: str, sha: str, split: str, k: int, batch_id: str) -> list[str]:
    """Every protocol-relevant flag is explicit, so a change to batch.py's defaults cannot
    silently make a candidate screen incomparable with the C0/C1 baselines."""
    argv = [
        "--condition", cand_condition,
        "--harness-sha", sha,
        "--subset", str(SUBSET),
        "--split", split,
        "--k", str(k),
        "--workers", str(a.workers),
        "--model", a.model,
        "--effort", a.effort,
        "--budget-usd", str(a.run_budget_usd),
        "--timeout", str(a.run_timeout),
        "--batch-id", batch_id,
    ]
    if a.dry:
        argv.append("--dry")
    return argv


def _stage(a, cand_condition: str, sha: str, split: str, k: int,
           base_condition: str, stage: str) -> tuple[int, dict]:
    """Run one batch stage and compute its transitions.  Returns (batch_exit_code, numbers)."""
    batch_id = f"{cand_condition}-{stage}"
    argv = _batch_argv(a, cand_condition, sha, split, k, batch_id)
    log(f"{stage}: batch {' '.join(argv)}")
    code = run_batch_cmd(argv)
    if code != 0:
        return code, {"batch_exit": code, "batch_id": batch_id}
    runs = stats.load_runs(_runs_path(a))
    if split == "all":
        numbers = {
            "batch_exit": code, "batch_id": batch_id, "k": k,
            "train": transitions(runs, base_condition, cand_condition,
                                 bench_batch.load_split(SUBSET, "train")),
            "heldout": transitions(runs, base_condition, cand_condition,
                                   bench_batch.load_split(SUBSET, "heldout")),
        }
    else:
        numbers = {"batch_exit": code, "batch_id": batch_id, "k": k, "split": split,
                   **transitions(runs, base_condition, cand_condition,
                                 bench_batch.load_split(SUBSET, split))}
    return 0, numbers


def relabel_manifests(runs_path, cand_condition: str, new_condition: str) -> int:
    """Append a superseding copy of every counted candidate manifest under the new condition.

    The manifest is append-only (``docs/manifest-schema.md``), so an accepted variant is not
    re-run and no line is edited: each counted ``cand-<sha7>`` line gets a twin carrying
    ``supersedes``, which ``stats.load_runs`` resolves by replacing the original in place.
    """
    path = Path(runs_path)
    if not path.exists():
        return 0
    relabeled = []
    for rec in stats.load_runs(path):
        if rec.get("condition") != cand_condition or not stats.counted(rec):
            continue
        old_id = rec["run_id"]
        new = dict(rec)
        new["condition"] = new_condition
        new["run_id"] = f"{old_id}-as-{new_condition}"
        new["supersedes"] = old_id
        note = (rec.get("notes") or "").strip()
        new["notes"] = (f"{note} | " if note else "") + (
            f"relabeled from {cand_condition} to {new_condition} by improver/loop.py on accept; "
            f"same run, not re-executed"
        )
        relabeled.append(new)
    with open(path, "a") as fh:
        for rec in relabeled:
            fh.write(json.dumps(rec) + "\n")
    return len(relabeled)


def iterate(a) -> int:
    """One full iteration.  Returns the process exit code; state is on disk at every step."""
    archive = load_archive()

    streak = reject_streak(archive)
    if len(streak) >= a.max_consecutive_rejects:
        fresh = record_wedge(streak, a.max_consecutive_rejects)
        log(f"WEDGED: {len(streak)} consecutive rejects (cap {a.max_consecutive_rejects}); "
            f"{'appended to' if fresh else 'already in'} {OWNER_DECISIONS}. Nothing was spent.")
        return EXIT_WEDGED

    if not Path(IMPROVE_COMMAND).exists():
        log(f"ABORT: {IMPROVE_COMMAND} is missing; the /improve command must exist before the "
            f"agent is invoked. Nothing was spent.")
        return EXIT_NO_COMMAND

    dirty = working_tree_changes(tuple(a.ignore_dirty))
    if dirty:
        listing = ", ".join(f"{xy.strip() or '??'} {p}" for xy, p in dirty[:8])
        log(f"ABORT: working tree is not clean ({len(dirty)} path(s): {listing}). Commit or stash "
            f"first, or add a prefix to --ignore-dirty. Nothing was spent.")
        return EXIT_DIRTY

    best = load_best()
    base_condition, base_sha = best["condition"], best["sha"]
    if not rev_parse(base_sha):
        log(f"ABORT: best.json points at {base_sha[:12]} which does not resolve.")
        return EXIT_DIRTY
    home = current_branch() or "main"
    # The stamp has one-second resolution; two iterations inside the same second would otherwise
    # share a branch and overwrite each other's archive record.
    taken = {r.get("variant_id") for r in archive}
    stamp = utc_stamp()
    variant_id, n = stamp, 1
    while variant_id in taken or rev_parse(f"cand/{variant_id}"):
        n += 1
        variant_id = f"{stamp}-{n}"
    branch = f"cand/{variant_id}"

    record = {
        "variant_id": variant_id, "branch": branch, "home_branch": home,
        "sha": None, "parent_sha": None,
        "base_condition": base_condition, "base_sha": base_sha, "cand_condition": None,
        "hypothesis": None, "created": utc_iso(), "status": "screening", "stage": "smoke",
        "results": {}, "reason": "", "agent": None, "dry": bool(a.dry),
    }

    def persist() -> None:
        save_archive(upsert(archive, dict(record)))

    def go_home() -> None:
        clean_harness_state(HARNESS)
        r = git("checkout", "-q", home)
        if r.returncode != 0:
            log(f"WARNING: could not return to {home}: {(r.stderr or '').strip()}")

    def reject(reason: str, stage: str | None = None) -> int:
        record["status"] = "rejected"
        record["reason"] = reason
        if stage:
            record["stage"] = stage
        persist()
        go_home()
        log(f"REJECT {variant_id} at {record['stage']}: {reason}")
        log(f"branch {branch} kept; record in {ARCHIVE}")
        after = reject_streak(load_archive())
        if len(after) >= a.max_consecutive_rejects:
            record_wedge(after, a.max_consecutive_rejects)
            log(f"WEDGED: {len(after)} consecutive rejects; see {OWNER_DECISIONS}")
            return EXIT_WEDGED
        return EXIT_OK

    def halt(reason: str, code: int) -> int:
        """Infrastructure stop: the variant is not judged, so the streak is not advanced."""
        record["reason"] = reason
        persist()
        go_home()
        log(f"STOP {variant_id} at {record['stage']}: {reason} (exit {code})")
        return code

    log(f"iteration {variant_id}: base {base_condition} at {base_sha[:7]}, branch {branch}"
        f"{' [DRY]' if a.dry else ''}")

    try:
        # --- 2. propose -----------------------------------------------------------------
        # The branch starts at the *current* HEAD, not at the base sha: only harness/ is under
        # test, and a checkout of an old base commit would drag bench/, docs/ and
        # .claude/commands/improve.md back with it (see docs/protocol.md).
        git_ok("checkout", "-q", "-B", branch)
        git("rm", "-r", "-q", "--ignore-unmatch", "--", "harness")
        git_ok("checkout", base_sha, "--", "harness")
        clean_harness_state(HARNESS)
        if git("diff", "--cached", "--quiet", "--", "harness").returncode != 0 or \
                git("diff", "--quiet", "--", "harness").returncode != 0:
            git_ok("add", "-A", "--", "harness")
            git_ok("commit", "-q", "-m",
                   f"base: harness at {base_sha[:7]} ({base_condition}) for {branch}")
        record["parent_sha"] = rev_parse("HEAD")
        if git("diff", "--quiet", base_sha, "HEAD", "--", "harness").returncode != 0:
            return halt(f"harness/ at {record['parent_sha'][:7]} does not match base {base_sha[:7]}",
                        EXIT_DIRTY)
        persist()

        agent = stub_improver(a) if a.dry else invoke_improver(a)
        record["agent"] = agent
        persist()
        cost = agent.get("total_cost_usd")
        log(f"agent done: rc={agent.get('rc')} turns={agent.get('num_turns')} "
            f"cost=${0.0 if cost is None else float(cost):.2f}")
        if agent.get("is_error"):
            return halt(f"improver agent failed: {agent.get('error') or agent.get('subtype')}",
                        EXIT_AGENT)

        # --- 3. validate mechanically ---------------------------------------------------
        train_ids = bench_batch.load_split(SUBSET, "train")
        reasons: list[str] = []

        changes = working_tree_changes(tuple(a.ignore_dirty))
        outside = [(xy, p) for xy, p in changes if not p.startswith("harness/")]
        if outside:
            listing = ", ".join(p for _, p in outside[:8])
            revert_paths([p for _, p in outside])
            reasons.append(f"edited outside harness/ ({len(outside)} path(s): {listing}); reverted")
        harness_changes = [p for _, p in changes if p.startswith("harness/")]

        doc = None
        if not Path(HYPOTHESIS).exists():
            reasons.append("harness/HYPOTHESIS.json is missing")
        else:
            try:
                doc = json.loads(Path(HYPOTHESIS).read_text())
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                reasons.append(f"harness/HYPOTHESIS.json is not valid JSON: {exc}")
        if doc is not None:
            schema = json.loads(Path(SCHEMA).read_text())
            errs = validate_hypothesis(doc, schema, train_ids, HARNESS)
            if errs:
                reasons.append("HYPOTHESIS.json invalid: " + "; ".join(errs[:6]))
            else:
                record["hypothesis"] = doc
        substantive = [p for p in harness_changes if p != "harness/HYPOTHESIS.json"]
        if not substantive:
            reasons.append("no file under harness/ changed other than HYPOTHESIS.json")

        # commit whatever is left under harness/, so a rejected candidate is still evidence
        sha = None
        if harness_changes:
            subject = "candidate (rejected before screening)"
            if isinstance(doc, dict) and isinstance(doc.get("hypothesis"), str):
                subject = doc["hypothesis"].strip().splitlines()[0][:72]
            body = json.dumps(doc, indent=2) if doc is not None else "(no valid HYPOTHESIS.json)"
            git_ok("add", "-A", "--", "harness")
            git_ok("commit", "-q", "-m", f"cand: {subject}\n\n{body}")
            sha = rev_parse("HEAD")
            record["sha"] = sha
            record["cand_condition"] = f"cand-{sha[:7]}"
            persist()

        if sha and not reasons:
            leaks = leak_check(record["parent_sha"], sha, INSTANCES, train_ids)
            if leaks:
                reasons.append("leaked hidden test name(s)/instance id(s): " + "; ".join(leaks))

        if sha and not reasons:
            rc, out = smoke_check(HARNESS)
            clean_harness_state(HARNESS)
            missing = [name for name in REQUIRED_AGENTS if name not in out]
            if rc != 0:
                reasons.append(f"harness-load smoke check failed (claude agents exit {rc}): "
                               f"{out.strip()[:200]}")
            elif missing:
                reasons.append(f"harness-load smoke check did not list {missing}: "
                               f"{out.strip()[:200]}")
        clean_harness_state(HARNESS)

        if reasons:
            return reject("; ".join(reasons), stage="smoke")
        cand_condition = record["cand_condition"]
        log(f"validated: {cand_condition} at {sha[:7]}, {len(substantive)} harness file(s) changed, "
            f"category {(doc or {}).get('category')}")

        # --- 4. train screen, k=1 --------------------------------------------------------
        record["stage"] = "train_k1"
        persist()
        code, numbers = _stage(a, cand_condition, sha, "train", 1, base_condition, "train1")
        record["results"]["train_k1"] = numbers
        persist()
        if code != 0:
            return halt(f"train k=1 batch exited {code}", code)
        log(f"train k=1: flips_up={numbers['flips_up']} regressions={numbers['regressions']} "
            f"flaky_gains={numbers['flaky_gains']} over {numbers['n_compared']} instance(s)")
        if numbers["flips_up"] == 0:
            return reject("train k=1 screen: zero solid_fail -> pass flips")
        if numbers["regressions"] > 0:
            return reject(f"train k=1 screen: {numbers['regressions']} solid_pass regression(s) "
                          f"({', '.join(numbers['regression_ids'][:5])})")

        # --- 5. held-out screen, k=1 -----------------------------------------------------
        record["stage"] = "heldout_k1"
        persist()
        code, numbers = _stage(a, cand_condition, sha, "heldout", 1, base_condition, "heldout1")
        record["results"]["heldout_k1"] = numbers
        persist()
        if code != 0:
            return halt(f"held-out k=1 batch exited {code}", code)
        log(f"heldout k=1: regressions={numbers['regressions']} flips_up={numbers['flips_up']} "
            f"over {numbers['n_compared']} instance(s)")
        if numbers["regressions"] > 0:
            return reject(f"held-out k=1 screen: {numbers['regressions']} solid_pass regression(s) "
                          f"({', '.join(numbers['regression_ids'][:5])})")

        # --- 6. confirmation, k=3 --------------------------------------------------------
        record["stage"] = "confirm_k3"
        persist()
        code, numbers = _stage(a, cand_condition, sha, "all", a.k, base_condition, "confirm")
        record["results"]["confirm_k3"] = numbers
        persist()
        if code != 0:
            return halt(f"confirmation k={a.k} batch exited {code}", code)
        train, heldout = numbers["train"], numbers["heldout"]
        log(f"confirm k={a.k}: train flips_up={train['flips_up']} regressions={train['regressions']}"
            f" | heldout flips_up={heldout['flips_up']} regressions={heldout['regressions']}")
        if heldout["regressions"] > 0:
            return reject(f"confirmation k={a.k}: {heldout['regressions']} held-out regression(s) "
                          f"({', '.join(heldout['regression_ids'][:5])})")
        if train["flips_up"] < 2:
            return reject(f"confirmation k={a.k}: train flips_up={train['flips_up']} < 2")

        # --- 7. accept -------------------------------------------------------------------
        n_accepted = sum(1 for r in archive if r.get("status") == "accepted"
                         and r.get("variant_id") != variant_id)
        new_condition = f"C{n_accepted + 2}"
        n_relabeled = relabel_manifests(_runs_path(a), cand_condition, new_condition)
        tag = git("tag", new_condition, sha)
        if tag.returncode != 0:
            log(f"WARNING: could not tag {new_condition}: {(tag.stderr or '').strip()}")
        write_json_state(BEST, {"condition": new_condition, "sha": sha, "tag": new_condition})
        record["status"] = "accepted"
        record["stage"] = "done"
        record["accepted_condition"] = new_condition
        record["relabeled_runs"] = n_relabeled
        record["reason"] = (f"held-out regressions 0, train flips_up {train['flips_up']} >= 2 "
                            f"at k={a.k}")
        persist()
        go_home()
        log(f"ACCEPT {variant_id} as {new_condition} ({sha[:7]}); {n_relabeled} manifest(s) "
            f"relabeled in {_runs_path(a)}; tag {new_condition}; best.json updated")
        return EXIT_OK

    except KeyboardInterrupt:
        record["reason"] = f"interrupted during {record['stage']}"
        try:
            persist()
            go_home()
        except Exception as exc:  # pragma: no cover - best effort on the way out
            log(f"WARNING: cleanup after interrupt failed: {exc}")
        log(f"INTERRUPTED at {record['stage']}; record kept, branch {branch} kept")
        return EXIT_INTERRUPT
    except LoopError as exc:
        return halt(str(exc), EXIT_DIRTY)


# --- 9. CLI ---------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m improver.loop",
                                description=__doc__.split("\n")[0])
    p.add_argument("--once", action="store_true", help="exactly one iteration (the default)")
    p.add_argument("--iterations", type=int, default=1,
                   help="run up to K iterations sequentially; stops on the first non-zero exit")
    p.add_argument("--dry", action="store_true",
                   help="stub the improver agent and thread --dry into every batch; no spend")
    p.add_argument("--max-consecutive-rejects", type=int, default=4,
                   help="consecutive rejected variants that wedge the loop (exit 6)")
    p.add_argument("--improver-model", default="opus", help="model for the improver agent")
    p.add_argument("--improver-budget", type=float, default=8.0,
                   help="--max-budget-usd for one improver agent session")
    p.add_argument("--agent-timeout", type=int, default=5400,
                   help="wall-clock seconds for the improver agent session")
    p.add_argument("--workers", type=int, default=3, help="batch concurrency (protocol cap: 3)")
    p.add_argument("--k", type=int, default=3, help="repeats for the confirmation batch")
    p.add_argument("--model", default="claude-sonnet-5", help="model for the benchmark runs")
    p.add_argument("--effort", default="medium", help="effort for the benchmark runs")
    p.add_argument("--run-budget-usd", type=float, default=4.0,
                   help="per-run budget for the benchmark runs (protocol: $4.00)")
    p.add_argument("--run-timeout", type=int, default=2400,
                   help="per-run wall clock for the benchmark runs (protocol: 2400 s)")
    p.add_argument("--ignore-dirty", action="append", default=None, metavar="PREFIX",
                   help=f"path prefixes the clean-tree check ignores (default: "
                        f"{' '.join(DIRTY_IGNORE)}; a live batch appends to results/)")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    if a.ignore_dirty is None:
        a.ignore_dirty = list(DIRTY_IGNORE)
    if a.once:
        a.iterations = 1
    if a.iterations < 1:
        print("[improver] --iterations must be >= 1")
        return EXIT_USAGE
    if a.workers < 1 or a.k < 1:
        print("[improver] --workers and --k must be >= 1")
        return EXIT_USAGE

    code = EXIT_OK
    for i in range(a.iterations):
        log(f"=== iteration {i + 1}/{a.iterations} ===")
        try:
            code = iterate(a)
        except KeyboardInterrupt:
            log("interrupted between stages")
            return EXIT_INTERRUPT
        except LoopError as exc:
            log(f"ABORT: {exc}")
            return EXIT_DIRTY
        if code != EXIT_OK:
            log(f"stopping after iteration {i + 1}: exit {code}")
            break
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
