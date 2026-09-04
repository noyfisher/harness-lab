"""Aggregation and statistics for the harness benchmark.

Reads the append-only run manifest described in ``docs/manifest-schema.md``
(``results/runs.jsonl``) and produces the numbers the measurement protocol asks
for: mean pass@1 over k repeats with a bootstrap 95% CI, the
solid_pass / flaky / solid_fail split per condition, paired comparisons between
consecutive conditions, and cost per solved instance.

Pure functions plus a small CLI; no pandas.

Why the *instance* is the bootstrap unit
----------------------------------------
Every instance is run k times under a condition, so those k runs are not k
independent observations: they share a repository, a bug, a gold patch, a test
suite, and whatever else makes that instance easy or hard.  The per-run outcomes
within an instance are strongly correlated, and the between-instance variance
(some SWE-bench bugs are simply out of reach, others are nearly free) dominates
the within-instance repeat noise.

Two consequences:

1. Resampling *runs* would treat k clustered observations as k independent ones
   and shrink the interval by roughly a factor of sqrt(k) relative to the truth,
   producing confidence intervals that are far too narrow.
2. The population we want to generalize to is "other SWE-bench-like instances",
   not "more repeats of these particular 30-40 instances".  The instance is the
   sampling unit of the experiment, so the instance is the resampling unit of
   the bootstrap.

So ``bootstrap_ci`` resamples instance ids with replacement, recomputes the mean
of the per-instance rates ``passes / k`` on each resample, and takes a
percentile interval.  Note that this interval covers *instance sampling* noise;
it does not separately model grading noise or the fact that the same k repeats
are reused across conditions.

Why the comparisons are paired
------------------------------
Conditions (C0 plain agent, C1 seeded harness, C2.. accepted variants) are
evaluated on the *same* instance set with the same repeat indices.  Because
between-instance variance dwarfs the effect of a harness change, comparing two
headline pass rates as if they came from independent samples throws away the
pairing and buries a real effect under instance difficulty.  Differencing within
an instance removes that instance's difficulty entirely, so a Wilcoxon
signed-rank test on per-instance pass-count differences (plus an exact sign test
on discordant majority pairs as a coarser, assumption-light second view) is much
more sensitive than any unpaired comparison at this sample size.

The paired *decision* rule of the protocol is also inherently per-instance:
a real gain is a solid_fail -> solid_pass flip, a regression is any solid_pass
that stops being solid_pass.  ``paired_compare`` reports both the flip counts
and the full 3x3 class transition table alongside the p-values.

Caveats worth stating in ``docs/protocol.md``
---------------------------------------------
* The p-values are not corrected for multiple comparisons; every accepted
  variant is another look at the same held-out instances.
* Instances are the unit, so N (30-40), not N*k, drives the width of the CI.
* Reusing the same instances across conditions makes the *comparison* sharp but
  makes the absolute pass rates correlated across conditions; the CIs on two
  conditions overlapping does not mean the paired difference is null.
* ``total_cost_usd`` is a client-side estimate at API list price, and
  ``cost_per_solve`` divides total cost (including failed runs) by resolved runs.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from scipy import stats as _sp_stats

__all__ = [
    "COUNTED_OUTCOMES",
    "NON_COUNTED_OUTCOMES",
    "CLASS_ORDER",
    "load_runs",
    "counted",
    "is_pass",
    "per_instance",
    "classify",
    "classes",
    "pass_rate",
    "bootstrap_ci",
    "paired_compare",
    "cost_summary",
    "summarize",
    "report",
    "main",
]

# --- schema constants ------------------------------------------------------

#: Outcomes where the agent "had its chance"; these count toward k.
COUNTED_OUTCOMES = frozenset(
    {"resolved", "unresolved", "no_diff", "budget", "timeout"}
)

#: Infrastructure failures: not counted toward k, re-run, reported separately.
NON_COUNTED_OUTCOMES = frozenset({"paused", "error", "parse_error"})

#: Canonical ordering for the per-instance classes.
CLASS_ORDER = ("solid_pass", "flaky", "solid_fail")

_REQUIRED_FIELDS = ("run_id", "condition", "instance_id", "outcome")


def _warn(msg: str) -> None:
    print(f"stats: warning: {msg}", file=sys.stderr)


# --- 1. loading ------------------------------------------------------------


def load_runs(path: str | os.PathLike[str]) -> list[dict]:
    """Load ``runs.jsonl``, apply ``supersedes``, drop malformed lines.

    A later line carrying ``supersedes: X`` replaces run ``X`` in place (chains
    are followed, so C superseding B superseding A leaves only C).  Lines that
    are not valid JSON objects, or that are missing any of ``run_id``,
    ``condition``, ``instance_id``, ``outcome``, are dropped with a warning on
    stderr.  Duplicate ``run_id``s that do *not* declare ``supersedes`` are also
    dropped, since the manifest is append-only and corrections must be explicit.
    """
    records: list[dict | None] = []
    pos: dict[str, int] = {}
    superseded: set[str] = set()
    src = os.fspath(path)

    with open(src, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                _warn(f"{src}:{lineno}: dropping unparseable line ({exc.msg})")
                continue
            if not isinstance(obj, dict):
                _warn(f"{src}:{lineno}: dropping line, not a JSON object")
                continue
            missing = [
                f
                for f in _REQUIRED_FIELDS
                if not isinstance(obj.get(f), str) or not obj.get(f)
            ]
            if missing:
                _warn(
                    f"{src}:{lineno}: dropping line, missing/invalid "
                    f"field(s): {', '.join(missing)}"
                )
                continue

            run_id = obj["run_id"]
            sup = obj.get("supersedes")
            if sup is not None and not isinstance(sup, str):
                _warn(
                    f"{src}:{lineno}: ignoring non-string 'supersedes' on {run_id}"
                )
                sup = None

            if run_id in pos:
                _warn(
                    f"{src}:{lineno}: duplicate run_id {run_id!r} without "
                    "'supersedes'; dropping the later line"
                    if not sup
                    else f"{src}:{lineno}: duplicate run_id {run_id!r}; dropping"
                )
                continue

            slot: int | None = None
            if sup is not None:
                if sup in pos:
                    slot = pos.pop(sup)
                    records[slot] = None
                    superseded.add(sup)
                elif sup in superseded:
                    _warn(
                        f"{src}:{lineno}: {run_id} supersedes {sup!r} which was "
                        "already superseded; appending"
                    )
                else:
                    _warn(
                        f"{src}:{lineno}: {run_id} supersedes unknown run_id "
                        f"{sup!r}; keeping the line"
                    )

            if slot is None:
                records.append(obj)
                pos[run_id] = len(records) - 1
            else:
                records[slot] = obj
                pos[run_id] = slot

    return [r for r in records if r is not None]


# --- 2. counting rules -----------------------------------------------------


def counted(run: Mapping[str, Any]) -> bool:
    """True if ``run`` counts toward k (the agent had its chance)."""
    return run.get("outcome") in COUNTED_OUTCOMES


def is_pass(run: Mapping[str, Any]) -> bool:
    """True if a counted run is a pass (``resolved == true``).

    Falls back to ``outcome == "resolved"`` when the ``resolved`` verdict is
    absent or null, so an ungraded-but-resolved line is not silently a fail.
    """
    verdict = run.get("resolved")
    if verdict is True:
        return True
    if verdict is False:
        return False
    return run.get("outcome") == "resolved"


# --- 3. per-instance aggregation -------------------------------------------


def per_instance(
    runs: Iterable[Mapping[str, Any]], condition: str
) -> dict[str, tuple[int, int]]:
    """``{instance_id: (passes, k)}`` over counted runs of ``condition``."""
    out: dict[str, list[int]] = {}
    for run in runs:
        if run.get("condition") != condition or not counted(run):
            continue
        iid = run.get("instance_id")
        if not isinstance(iid, str):
            continue
        slot = out.setdefault(iid, [0, 0])
        slot[1] += 1
        if is_pass(run):
            slot[0] += 1
    return {iid: (p, k) for iid, (p, k) in out.items()}


# --- 4. classification -----------------------------------------------------


def classify(passes: int, k: int) -> str:
    """``solid_pass`` (k/k), ``solid_fail`` (0/k), else ``flaky``."""
    if k <= 0:
        raise ValueError("k must be positive to classify an instance")
    if not 0 <= passes <= k:
        raise ValueError(f"passes={passes} out of range for k={k}")
    if passes == k:
        return "solid_pass"
    if passes == 0:
        return "solid_fail"
    return "flaky"


def classes(pi: Mapping[str, tuple[int, int]]) -> dict[str, str]:
    """``{instance_id: class}`` for a ``per_instance`` mapping."""
    return {iid: classify(p, k) for iid, (p, k) in pi.items()}


def class_counts(pi: Mapping[str, tuple[int, int]]) -> dict[str, int]:
    """``{class: n_instances}`` in :data:`CLASS_ORDER`."""
    counts = {c: 0 for c in CLASS_ORDER}
    for cls in classes(pi).values():
        counts[cls] += 1
    return counts


# --- 5. headline rate ------------------------------------------------------


def _rate_array(pi: Mapping[str, tuple[int, int]]) -> np.ndarray:
    """Per-instance pass rates, ordered by instance id for determinism."""
    return np.array(
        [pi[iid][0] / pi[iid][1] for iid in sorted(pi) if pi[iid][1] > 0],
        dtype=float,
    )


def pass_rate(pi: Mapping[str, tuple[int, int]]) -> float:
    """Mean over instances of ``passes / k`` (mean pass@1 over k repeats).

    Returns NaN for an empty condition rather than a misleading 0.0.
    """
    rates = _rate_array(pi)
    if rates.size == 0:
        return float("nan")
    return float(rates.mean())


# --- 6. bootstrap ----------------------------------------------------------


def bootstrap_ci(
    pi: Mapping[str, tuple[int, int]],
    n_boot: int = 10000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Percentile bootstrap CI for :func:`pass_rate`, resampling *instances*.

    Instances (not runs) are resampled with replacement because the k repeats of
    one instance are clustered observations of the same underlying difficulty;
    see the module docstring.
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    rates = _rate_array(pi)
    n = rates.size
    if n == 0:
        return (float("nan"), float("nan"))
    if n == 1:
        return (float(rates[0]), float(rates[0]))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(int(n_boot), n))
    means = rates[idx].mean(axis=1)
    lo = float(np.percentile(means, 100.0 * (alpha / 2.0)))
    hi = float(np.percentile(means, 100.0 * (1.0 - alpha / 2.0)))
    return (lo, hi)


# --- 7. paired comparison --------------------------------------------------


def _majority(passes: int, k: int) -> bool:
    """Per-instance majority pass: ``passes > k / 2``."""
    return passes * 2 > k


def paired_compare(
    runs: Iterable[Mapping[str, Any]], cond_a: str, cond_b: str
) -> dict[str, Any]:
    """Paired A-vs-B comparison restricted to instances present in both.

    Returns a JSON-serializable dict with per-instance pass counts, the 3x3
    class transition table (rows = class in A, cols = class in B), flip and
    regression counts, discordant majority pairs, a Wilcoxon signed-rank test on
    per-instance pass-count differences, and an exact sign test on the
    discordant majority pairs as a second view.
    """
    runs = list(runs)
    pi_a = per_instance(runs, cond_a)
    pi_b = per_instance(runs, cond_b)
    common = sorted(set(pi_a) & set(pi_b))

    cls_a = classes(pi_a)
    cls_b = classes(pi_b)

    matrix = [[0 for _ in CLASS_ORDER] for _ in CLASS_ORDER]
    index = {c: i for i, c in enumerate(CLASS_ORDER)}

    instances: list[dict[str, Any]] = []
    diffs: list[int] = []
    flips_up = 0
    regressions = 0
    b_only = 0  # majority pass in B but not A
    a_only = 0  # majority pass in A but not B
    both = 0
    neither = 0
    k_mismatch: list[str] = []

    for iid in common:
        pa, ka = pi_a[iid]
        pb, kb = pi_b[iid]
        if ka != kb:
            # Protocol caveat 4: pass counts on different k are not on a common scale, so the
            # instance is listed and EXCLUDED from the transition table and both paired tests.
            k_mismatch.append(iid)
            continue
        ca, cb = cls_a[iid], cls_b[iid]
        matrix[index[ca]][index[cb]] += 1
        diff = pb - pa
        diffs.append(diff)
        if ca == "solid_fail" and cb == "solid_pass":
            flips_up += 1
        if ca == "solid_pass" and cb != "solid_pass":
            regressions += 1
        ma, mb = _majority(pa, ka), _majority(pb, kb)
        if ma and mb:
            both += 1
        elif ma and not mb:
            a_only += 1
        elif mb and not ma:
            b_only += 1
        else:
            neither += 1
        instances.append(
            {
                "instance_id": iid,
                "a_passes": int(pa),
                "a_k": int(ka),
                "b_passes": int(pb),
                "b_k": int(kb),
                "a_class": ca,
                "b_class": cb,
                "diff": int(diff),
                "a_majority": bool(ma),
                "b_majority": bool(mb),
            }
        )

    # Wilcoxon signed-rank on per-instance pass-count differences.
    wilcoxon_stat: float | None = None
    wilcoxon_p: float | None = None
    wilcoxon_note = ""
    d = np.asarray(diffs, dtype=float)
    if d.size == 0:
        wilcoxon_note = "no instances present in both conditions"
    elif not np.any(d != 0):
        # zero_method="wilcox" discards zeros and raises when all are zero;
        # an all-tied comparison is simply "no evidence of a difference".
        wilcoxon_p = 1.0
        wilcoxon_note = "all per-instance differences are zero"
    else:
        try:
            res = _sp_stats.wilcoxon(d, zero_method="wilcox")
            wilcoxon_stat = float(res.statistic)
            wilcoxon_p = float(res.pvalue)
        except ValueError as exc:  # pragma: no cover - defensive
            wilcoxon_p = 1.0
            wilcoxon_note = f"wilcoxon unavailable: {exc}"

    # Exact sign test on discordant majority pairs.
    n_discordant = a_only + b_only
    if n_discordant == 0:
        sign_p: float | None = 1.0
        sign_note = "no discordant majority pairs"
    else:
        sign_p = float(
            _sp_stats.binomtest(
                k=b_only, n=n_discordant, p=0.5, alternative="two-sided"
            ).pvalue
        )
        sign_note = ""

    return {
        "cond_a": cond_a,
        "cond_b": cond_b,
        "n_instances": len(common),
        "n_only_a": len(set(pi_a) - set(pi_b)),
        "n_only_b": len(set(pi_b) - set(pi_a)),
        "k_mismatch_instances": k_mismatch,
        "instances": instances,
        "pass_counts_a": {iid: int(pi_a[iid][0]) for iid in common},
        "pass_counts_b": {iid: int(pi_b[iid][0]) for iid in common},
        "k_a": {iid: int(pi_a[iid][1]) for iid in common},
        "k_b": {iid: int(pi_b[iid][1]) for iid in common},
        "flips_up": int(flips_up),
        "regressions": int(regressions),
        "transition_table": {
            "classes": list(CLASS_ORDER),
            "matrix": matrix,
            "rows": {
                CLASS_ORDER[i]: {
                    CLASS_ORDER[j]: matrix[i][j] for j in range(len(CLASS_ORDER))
                }
                for i in range(len(CLASS_ORDER))
            },
            "total": int(sum(sum(row) for row in matrix)),
        },
        "discordant": {
            "n_discordant": int(n_discordant),
            "b_only": int(b_only),
            "a_only": int(a_only),
            "both": int(both),
            "neither": int(neither),
        },
        "wilcoxon": {
            "statistic": wilcoxon_stat,
            "p_value": wilcoxon_p,
            "zero_method": "wilcox",
            "n_nonzero": int(np.count_nonzero(d)) if d.size else 0,
            "note": wilcoxon_note,
        },
        "sign_test": {
            "p_value": sign_p,
            "n_discordant": int(n_discordant),
            "b_better": int(b_only),
            "note": sign_note,
        },
    }


# --- 8. cost ---------------------------------------------------------------


def _mean_of(values: Sequence[float]) -> float | None:
    return float(sum(values) / len(values)) if values else None


def cost_summary(
    runs: Iterable[Mapping[str, Any]], condition: str
) -> dict[str, Any]:
    """Cost / time / turn summary plus infrastructure-failure counts."""
    n_counted = 0
    resolved_count = 0
    costs: list[float] = []
    walls: list[float] = []
    turns: list[float] = []
    infra: dict[str, int] = {}

    for run in runs:
        if run.get("condition") != condition:
            continue
        if not counted(run):
            outcome = run.get("outcome")
            key = outcome if isinstance(outcome, str) else "unknown"
            infra[key] = infra.get(key, 0) + 1
            continue
        n_counted += 1
        if is_pass(run):
            resolved_count += 1
        cost = run.get("total_cost_usd")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            costs.append(float(cost))
        wall = run.get("wall_s")
        if isinstance(wall, (int, float)) and not isinstance(wall, bool):
            walls.append(float(wall))
        nt = run.get("num_turns")
        if isinstance(nt, (int, float)) and not isinstance(nt, bool):
            turns.append(float(nt))

    total_cost = float(sum(costs)) if costs else 0.0
    return {
        "condition": condition,
        "n_counted": int(n_counted),
        "total_cost_usd": total_cost,
        "n_cost_reported": len(costs),
        "mean_cost_per_run": _mean_of(costs),
        "resolved_count": int(resolved_count),
        "cost_per_solve": (
            float(total_cost / resolved_count) if resolved_count else None
        ),
        "mean_wall_s": _mean_of(walls),
        "mean_num_turns": _mean_of(turns),
        "infra_failures": dict(sorted(infra.items())),
        "infra_failures_total": int(sum(infra.values())),
    }


# --- 9. report -------------------------------------------------------------


def _all_conditions(runs: Iterable[Mapping[str, Any]]) -> list[str]:
    return sorted(
        {
            run["condition"]
            for run in runs
            if isinstance(run.get("condition"), str)
        }
    )


def summarize(
    runs: Sequence[Mapping[str, Any]],
    conditions: Sequence[str] | None = None,
    n_boot: int = 10000,
    seed: int = 0,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Full computed structure (JSON-serializable) for report + site generator."""
    runs = list(runs)
    conds = list(conditions) if conditions else _all_conditions(runs)

    per_condition: dict[str, Any] = {}
    for cond in conds:
        pi = per_instance(runs, cond)
        ks = [k for _, k in pi.values()]
        lo, hi = bootstrap_ci(pi, n_boot=n_boot, seed=seed, alpha=alpha)
        per_condition[cond] = {
            "condition": cond,
            "n_instances": len(pi),
            "k_min": int(min(ks)) if ks else None,
            "k_max": int(max(ks)) if ks else None,
            "n_counted_runs": int(sum(ks)),
            "pass_rate": pass_rate(pi),
            "ci_lo": lo,
            "ci_hi": hi,
            "ci_alpha": alpha,
            "class_counts": class_counts(pi),
            "per_instance": {
                iid: {
                    "passes": int(p),
                    "k": int(k),
                    "class": classify(p, k),
                }
                for iid, (p, k) in sorted(pi.items())
            },
            "cost": cost_summary(runs, cond),
        }

    paired = [
        paired_compare(runs, conds[i], conds[i + 1])
        for i in range(len(conds) - 1)
    ]

    return {
        "params": {
            "n_boot": int(n_boot),
            "seed": int(seed),
            "alpha": float(alpha),
            "counted_outcomes": sorted(COUNTED_OUTCOMES),
            "non_counted_outcomes": sorted(NON_COUNTED_OUTCOMES),
        },
        "conditions": conds,
        "n_runs_loaded": len(runs),
        "n_runs_counted": sum(1 for r in runs if counted(r)),
        "per_condition": per_condition,
        "paired": paired,
    }


def _fmt(value: Any, spec: str = "", dash: str = "n/a") -> str:
    if value is None:
        return dash
    if isinstance(value, float) and not math.isfinite(value):
        return dash
    return format(value, spec) if spec else str(value)


def _fmt_p(p: float | None) -> str:
    if p is None:
        return "n/a"
    if p < 1e-4:
        return "<0.0001"
    return f"{p:.4f}"


def report(
    runs: Sequence[Mapping[str, Any]],
    conditions: Sequence[str] | None = None,
    n_boot: int = 10000,
    seed: int = 0,
    alpha: float = 0.05,
    data: Mapping[str, Any] | None = None,
) -> str:
    """Markdown report: per-condition table, paired comparisons, infra failures."""
    d = (
        dict(data)
        if data is not None
        else summarize(
            runs, conditions, n_boot=n_boot, seed=seed, alpha=alpha
        )
    )
    conds: list[str] = list(d["conditions"])
    pc: dict[str, Any] = d["per_condition"]
    conf = int(round((1.0 - float(d["params"]["alpha"])) * 100))

    out: list[str] = []
    out.append("# Harness benchmark report")
    out.append("")
    out.append(
        f"{d['n_runs_loaded']} runs loaded, {d['n_runs_counted']} counted "
        f"toward k. Conditions: {', '.join(conds) if conds else '(none)'}."
    )
    out.append(
        f"Bootstrap: {d['params']['n_boot']} resamples of *instances*, "
        f"seed {d['params']['seed']}."
    )
    out.append("")

    # (a) per-condition table
    out.append("## Per-condition summary")
    out.append("")
    out.append(
        "| condition | instances | k (min/max) | pass rate "
        f"({conf}% CI) | solid_pass | flaky | solid_fail | resolved runs | "
        "cost per solve | mean wall (s) |"
    )
    out.append("|---|---:|---:|---|---:|---:|---:|---:|---:|---:|")
    for cond in conds:
        row = pc[cond]
        cc = row["class_counts"]
        cost = row["cost"]
        k_txt = (
            f"{row['k_min']}/{row['k_max']}"
            if row["k_min"] is not None
            else "n/a"
        )
        rate_txt = (
            f"{_fmt(row['pass_rate'], '.3f')} "
            f"[{_fmt(row['ci_lo'], '.3f')}, {_fmt(row['ci_hi'], '.3f')}]"
        )
        cps = cost["cost_per_solve"]
        out.append(
            f"| {cond} | {row['n_instances']} | {k_txt} | {rate_txt} | "
            f"{cc['solid_pass']} | {cc['flaky']} | {cc['solid_fail']} | "
            f"{cost['resolved_count']} | "
            f"{('$' + format(cps, '.2f')) if cps is not None else 'n/a'} | "
            f"{_fmt(cost['mean_wall_s'], '.1f')} |"
        )
    out.append("")

    # (b) paired comparisons
    out.append("## Paired comparisons")
    out.append("")
    if not d["paired"]:
        out.append("_Fewer than two conditions; nothing to compare._")
        out.append("")
    for cmp_ in d["paired"]:
        a, b = cmp_["cond_a"], cmp_["cond_b"]
        out.append(f"### {a} -> {b}")
        out.append("")
        out.append(
            f"Instances in both conditions: {cmp_['n_instances']} "
            f"({cmp_['n_only_a']} only in {a}, {cmp_['n_only_b']} only in {b})."
        )
        out.append("")
        out.append(
            f"- flips_up (solid_fail in {a} -> solid_pass in {b}): "
            f"**{cmp_['flips_up']}**"
        )
        out.append(
            f"- regressions (solid_pass in {a} -> not solid_pass in {b}): "
            f"**{cmp_['regressions']}**"
        )
        disc = cmp_["discordant"]
        out.append(
            f"- discordant majority pairs: {disc['n_discordant']} "
            f"({b} better: {disc['b_only']}, {a} better: {disc['a_only']}); "
            f"concordant: {disc['both']} pass / {disc['neither']} fail"
        )
        wil = cmp_["wilcoxon"]
        note = f" ({wil['note']})" if wil["note"] else ""
        out.append(
            "- Wilcoxon signed-rank on per-instance pass counts: "
            f"statistic={_fmt(wil['statistic'], '.1f')}, "
            f"p={_fmt_p(wil['p_value'])}{note}"
        )
        sgn = cmp_["sign_test"]
        snote = f" ({sgn['note']})" if sgn["note"] else ""
        out.append(
            "- sign test on discordant majority pairs: "
            f"p={_fmt_p(sgn['p_value'])}{snote}"
        )
        if cmp_["k_mismatch_instances"]:
            out.append(
                f"- warning: k differs between conditions for "
                f"{len(cmp_['k_mismatch_instances'])} instance(s): "
                + ", ".join(cmp_["k_mismatch_instances"][:5])
            )
        out.append("")
        tt = cmp_["transition_table"]
        out.append(f"Transition table (rows = {a}, cols = {b}):")
        out.append("")
        out.append("| " + f"{a} \\ {b}" + " | " + " | ".join(tt["classes"]) + " |")
        out.append("|---|" + "---:|" * len(tt["classes"]))
        for i, cls in enumerate(tt["classes"]):
            out.append(
                f"| {cls} | " + " | ".join(str(v) for v in tt["matrix"][i]) + " |"
            )
        out.append("")

    # (c) infra failures
    out.append("## Infrastructure failures (not counted toward k)")
    out.append("")
    rows: list[str] = []
    for cond in conds:
        infra = pc[cond]["cost"]["infra_failures"]
        for outcome, n in sorted(infra.items()):
            rows.append(f"| {cond} | {outcome} | {n} |")
    if rows:
        out.append("| condition | outcome | runs |")
        out.append("|---|---|---:|")
        out.extend(rows)
    else:
        out.append("_None._")
    out.append("")
    return "\n".join(out)


# --- CLI -------------------------------------------------------------------


def _json_safe(obj: Any) -> Any:
    """Replace non-finite floats with None so the dump is valid JSON."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return _json_safe(obj.item())
    return obj


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m bench.stats",
        description="Aggregate results/runs.jsonl into a markdown report.",
    )
    parser.add_argument(
        "--runs", required=True, help="path to results/runs.jsonl"
    )
    parser.add_argument(
        "--conditions",
        nargs="*",
        default=None,
        help="conditions in comparison order (default: all found, sorted)",
    )
    parser.add_argument(
        "--json", dest="json_out", default=None, help="dump full structure here"
    )
    parser.add_argument("--seed", type=int, default=0, help="bootstrap seed")
    parser.add_argument(
        "--n-boot", type=int, default=10000, help="bootstrap resamples"
    )
    parser.add_argument(
        "--alpha", type=float, default=0.05, help="1 - confidence level"
    )
    args = parser.parse_args(argv)

    runs = load_runs(args.runs)
    if not runs:
        _warn(f"no usable runs in {args.runs}")
    data = summarize(
        runs,
        args.conditions,
        n_boot=args.n_boot,
        seed=args.seed,
        alpha=args.alpha,
    )
    if args.json_out:
        os.makedirs(
            os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True
        )
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(_json_safe(data), fh, indent=2, sort_keys=False)
            fh.write("\n")
    print(report(runs, data=data))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
