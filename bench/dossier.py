"""Build failure dossiers: one markdown file per (condition, instance) that the improver reads.

A dossier is the compact evidence for *why* a run failed: the problem statement, what the
agent said it did (its JSON summary), what it actually ran (Bash commands, tests, files
edited, specialists spawned), the patch it produced, and which hidden tests still fail.
Hidden test names are included here because dossiers are read by the improver on the TRAIN
split only, never by the agent under test; the improver may not copy test names into the
harness (loop.py checks for that).

    python -m bench.dossier --condition C0 --classes solid_fail,flaky [--split train] [--out results/dossiers]
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

from bench.run import ROOT, RUNS
from bench.stats import classes, load_runs, per_instance
from swebench.task.repo import load_task

TASKS = ROOT / "bench" / ".cache" / "swe-bench-tasks" / "tasks"
TEST_CMD_RE = re.compile(r"pytest|runtests\.py|bin/test|python -m unittest|tox\b|nosetests", re.I)


def trace_summary(trace_path: Path, max_cmds: int = 40) -> dict:
    tools, spawns, cmds, edits, tests = Counter(), [], [], [], []
    texts = []
    with gzip.open(trace_path, "rt", errors="replace") as fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = ev.get("message") or {}
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for blk in content:
                if blk.get("type") == "tool_use":
                    name = blk.get("name"); inp = blk.get("input") or {}
                    tools[name] += 1
                    if name == "Agent":
                        spawns.append(inp.get("subagent_type"))
                    elif name == "Bash":
                        c = (inp.get("command") or "").strip().replace("\n", " ")
                        cmds.append(c[:160])
                        if TEST_CMD_RE.search(c):
                            tests.append(c[:160])
                    elif name in ("Edit", "Write", "MultiEdit"):
                        edits.append(inp.get("file_path"))
                elif blk.get("type") == "text" and ev.get("type") == "assistant":
                    t = (blk.get("text") or "").strip()
                    if t:
                        texts.append(t[:400])
    return {
        "tools": dict(tools), "spawns": spawns, "commands": cmds[:max_cmds], "n_commands": len(cmds),
        "tests_run": tests, "files_edited": sorted({e for e in edits if e}), "last_texts": texts[-3:],
    }


def grading_detail(grade_run_id: str | None, instance_id: str) -> dict:
    if not grade_run_id:
        return {}
    p = ROOT / "results" / "grading" / grade_run_id / instance_id / "report.json"
    if not p.exists():
        return {}
    rep = json.load(open(p)).get(instance_id, {})
    ts = rep.get("tests_status") or {}
    out = {"patch_applied": rep.get("patch_successfully_applied"), "resolved": rep.get("resolved")}
    for key in ("FAIL_TO_PASS", "PASS_TO_PASS"):
        d = ts.get(key, {})
        out[key] = {"failed": d.get("failure", [])[:15], "n_failed": len(d.get("failure", [])), "n_passed": len(d.get("success", []))}
    log = p.with_name("test_output.txt")
    if log.exists():
        txt = log.read_text(errors="replace")
        # keep the tail of the test output between the markers, trimmed
        seg = txt.split(">>>>> Start Test Output")[-1].split(">>>>> End Test Output")[0]
        out["test_output_tail"] = seg[-2500:]
    return out


def build_dossier(cond: str, iid: str, runs: list[dict], k_info: tuple[int, int], cls: str) -> str:
    task = load_task(TASKS / iid)
    lines = [f"# {iid} under {cond}: {cls} ({k_info[0]}/{k_info[1]} passes)", ""]
    lines += [f"repo: {task['repo']}  version: {task['version']}  difficulty: {task.get('difficulty')}", ""]
    lines += ["## Problem statement", "", task["problem_statement"][:2500].strip(), ""]
    gold_files = re.findall(r"^diff --git a/(\S+)", task["patch"], re.M)
    lines += [f"## Gold patch touches (files only): {', '.join(gold_files)}", ""]
    for m in sorted(runs, key=lambda r: r["repeat"]):
        lines += [f"## Run r{m['repeat']}: outcome={m['outcome']} resolved={m.get('resolved')} turns={m.get('num_turns')} cost=${(m.get('total_cost_usd') or 0):.2f} wall={m.get('wall_s')}s"]
        s = m.get("summary")
        if s:
            lines += ["", "Agent summary:", "```json", json.dumps(s, indent=1)[:1500], "```"]
        if m.get("trace_path") and (ROOT / m["trace_path"]).exists():
            t = trace_summary(ROOT / m["trace_path"])
            lines += ["", f"tools: {t['tools']}", f"specialists spawned: {t['spawns']}", f"files edited: {t['files_edited']}",
                      f"tests run ({len(t['tests_run'])}):"] + [f"  - {c}" for c in t["tests_run"][:12]]
            lines += [f"bash commands ({t['n_commands']}, first {len(t['commands'])}):"] + [f"  - {c}" for c in t["commands"]]
            if t["last_texts"]:
                lines += ["last agent messages:"] + [f"  > {x}" for x in t["last_texts"]]
        g = grading_detail(m.get("grade_run_id"), iid)
        if g:
            lines += ["", f"grading: applied={g.get('patch_applied')} resolved={g.get('resolved')} "
                          f"F2P failed {g['FAIL_TO_PASS']['n_failed']} passed {g['FAIL_TO_PASS']['n_passed']}; "
                          f"P2P failed {g['PASS_TO_PASS']['n_failed']} passed {g['PASS_TO_PASS']['n_passed']}"]
            if g["FAIL_TO_PASS"]["failed"]:
                lines += ["still-failing hidden tests (F2P):"] + [f"  - {x}" for x in g["FAIL_TO_PASS"]["failed"]]
            if g["PASS_TO_PASS"]["failed"]:
                lines += ["broken existing tests (P2P):"] + [f"  - {x}" for x in g["PASS_TO_PASS"]["failed"]]
            if g.get("test_output_tail"):
                lines += ["test output tail:", "```", g["test_output_tail"][-1500:], "```"]
        if m.get("patch_path") and (ROOT / m["patch_path"]).exists():
            patch = (ROOT / m["patch_path"]).read_text()
            model_files = re.findall(r"^diff --git a/(\S+)", patch, re.M)
            lines += ["", f"model patch touches: {', '.join(model_files) or '(none)'}", "```diff", patch[:4000], "```"]
        lines += [""]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--condition", required=True)
    ap.add_argument("--classes", default="solid_fail,flaky")
    ap.add_argument("--split", choices=["train", "heldout", "all"], default="train")
    ap.add_argument("--runs", default=str(RUNS))
    ap.add_argument("--out", default=str(ROOT / "results" / "dossiers"))
    a = ap.parse_args(argv)
    runs = load_runs(a.runs)
    pi = per_instance(runs, a.condition)
    cl = classes(pi)
    wanted = set(a.classes.split(","))
    ids = sorted(i for i, c in cl.items() if c in wanted)
    if a.split != "all":
        subset = json.load(open(ROOT / "bench" / "subset.json"))
        ids = [i for i in ids if i in set(subset[a.split])]
    out = Path(a.out) / a.condition
    # Wipe first: a previous run over a wider split must not leave held-out dossiers behind
    # where the improver could read them.
    import shutil
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    index = [f"# Dossiers for {a.condition} ({a.split}, classes {sorted(wanted)}): {len(ids)} instances", ""]
    for iid in ids:
        rs = [r for r in runs if r["condition"] == a.condition and r["instance_id"] == iid]
        text = build_dossier(a.condition, iid, rs, pi[iid], cl[iid])
        (out / f"{iid}.md").write_text(text)
        index.append(f"- [{iid}]({iid}.md): {cl[iid]} {pi[iid][0]}/{pi[iid][1]}")
    (out / "INDEX.md").write_text("\n".join(index) + "\n")
    print(f"wrote {len(ids)} dossiers to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
