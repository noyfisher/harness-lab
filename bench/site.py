"""Static results page for the harness benchmark.

Turns the append-only run manifest (``results/runs.jsonl``, see
``docs/manifest-schema.md``) into a single self-contained ``index.html`` plus the
``data.json`` that produced it::

    python -m bench.site --runs results/runs.jsonl --out results/site

The page has no external resources: inline CSS, inline SVG, no fonts, no
scripts. Everything a reader needs to judge the numbers is on the page, in the
order the protocol argues for: the claim, the headline table, the curve, the
paired comparisons (which are the actual evidence), the per-instance detail, the
infrastructure failures, and the protocol's own caveats.

Determinism
-----------
CI regenerates the page and diffs it against the committed one, so the output
must be byte-identical for the same manifest. That means: no wall-clock
timestamps, no host paths, no dict iteration that depends on insertion luck, a
fixed bootstrap seed, and fixed-precision number formatting. The only thing that
identifies *when* a page was made is the provenance line, which names the
manifest by basename, its line count, and its sha256.

The statistics all come from :mod:`bench.stats`; this module only formats them.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import sys
from typing import Any, Mapping, Sequence

import numpy as np

from bench import stats

__all__ = [
    "DEFAULT_TITLE",
    "is_candidate",
    "order_conditions",
    "render_page",
    "build",
    "main",
]

DEFAULT_TITLE = "Harness Lab"

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
DEFAULT_PROTOCOL = os.path.join(_REPO_ROOT, "docs", "protocol.md")

NA = "n/a"

#: One-sentence version of the claim in docs/protocol.md.
CLAIM = (
    "Does a multi-agent Claude Code harness resolve more SWE-bench Verified "
    "issues than a single-agent <code>claude -p</code> baseline running the "
    "same model, effort, budget, prompt rules and container, measured on a "
    "fixed stratified subset of the arm64-available Verified instances?"
)

# --- small formatting helpers ----------------------------------------------


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and (
        math.isfinite(float(value))
    )


def _fmt_rate(value: Any, spec: str = ".3f") -> str:
    return format(float(value), spec) if _finite(value) else NA


def _fmt_int(value: Any) -> str:
    return str(int(value)) if _finite(value) else NA


def _fmt_money(value: Any) -> str:
    return f"${float(value):,.2f}" if _finite(value) else NA


def _fmt_secs(value: Any) -> str:
    return f"{float(value):,.1f}" if _finite(value) else NA


def _fmt_p(value: Any) -> str:
    """p-value, already HTML-escaped (the ``<`` in ``<0.0001``)."""
    if not _finite(value):
        return NA
    p = float(value)
    return "&lt;0.0001" if p < 1e-4 else f"{p:.4f}"


def _esc(text: Any) -> str:
    return html.escape(str(text), quote=False)


def _md_inline(text: str) -> str:
    """Escape, then honour the only two inline markdown forms the docs use."""
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    return out


def _num(value: float) -> str:
    """Fixed-precision SVG coordinate, so the bytes never wobble."""
    out = f"{float(value):.2f}"
    return "0.00" if out == "-0.00" else out


def _json_safe(obj: Any) -> Any:
    """Non-finite floats become null; numpy scalars become python scalars."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return _json_safe(obj.item())
    return obj


# --- condition ordering -----------------------------------------------------

_CAND_RE = re.compile(r"^cand[-_]", re.IGNORECASE)
_MAIN_RE = re.compile(r"^C(\d+)(.*)$")


def is_candidate(condition: str) -> bool:
    """True for improver screens (``cand-<sha7>``), which are not headline."""
    return bool(_CAND_RE.match(condition))


def _main_key(condition: str) -> tuple[int, int, str, str]:
    m = _MAIN_RE.match(condition)
    if m:
        return (0, int(m.group(1)), m.group(2), condition)
    return (1, 0, "", condition)


def order_conditions(
    conditions: Sequence[str], explicit: bool = False
) -> tuple[list[str], list[str]]:
    """Split into (headline conditions, candidate screens).

    Headline conditions sort C0, C1, C1o, C2, ... then anything unrecognised
    alphabetically; candidates always come last. When ``explicit`` is set the
    caller named the conditions on the command line, so their order is kept and
    only the candidate split is applied.
    """
    mains = [c for c in conditions if not is_candidate(c)]
    cands = [c for c in conditions if is_candidate(c)]
    if not explicit:
        mains = sorted(mains, key=_main_key)
        cands = sorted(cands)
    return mains, cands


def _repo_of(instance_id: str) -> str:
    """SWE-bench ids look like ``django__django-11039``; take the prefix."""
    head = instance_id.split("__", 1)[0] if "__" in instance_id else ""
    return head or NA


# --- provenance -------------------------------------------------------------


def _provenance(runs_path: str) -> dict[str, Any]:
    """Basename, non-empty line count and sha256 of the manifest file."""
    with open(runs_path, "rb") as fh:
        blob = fh.read()
    n_lines = sum(1 for line in blob.split(b"\n") if line.strip())
    return {
        "name": os.path.basename(runs_path),
        "n_lines": n_lines,
        "sha256": hashlib.sha256(blob).hexdigest(),
    }


# --- protocol.md scraping ---------------------------------------------------


def _section(text: str, title_prefix: str) -> list[str]:
    """Lines of the first ``## <title_prefix>...`` section, heading excluded."""
    out: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip().lower().startswith(title_prefix.lower())
            continue
        if inside:
            out.append(line)
    return out


def _parse_caveats(text: str) -> list[str]:
    """The numbered items under ``## Caveats``, continuation lines folded in."""
    items: list[str] = []
    for line in _section(text, "caveats"):
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^\d+\.\s+(.*)$", stripped)
        if m:
            items.append(m.group(1).strip())
        elif items:
            items[-1] = f"{items[-1]} {stripped}"
    return items


def _parse_table(lines: Sequence[str]) -> tuple[list[str], list[list[str]]]:
    rows: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if all(set(c) <= set("-: ") and c for c in cells):
            continue  # markdown separator row
        rows.append(cells)
    if not rows:
        return ([], [])
    return (rows[0], rows[1:])


def _parse_versions(text: str) -> tuple[list[str], list[list[str]]]:
    return _parse_table(_section(text, "pinned versions"))


def read_protocol(path: str | None) -> dict[str, Any] | None:
    """Caveats and pinned versions from ``docs/protocol.md``; None if absent."""
    if not path or not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    header, rows = _parse_versions(text)
    return {
        "caveats": _parse_caveats(text),
        "versions_header": header,
        "versions_rows": rows,
    }


# --- stylesheet -------------------------------------------------------------

CSS = """
:root {
  color-scheme: light;
  --bg: #ffffff;
  --surface: #fbfbfa;
  --surface-2: #f2f2ef;
  --text: #14140f;
  --text-2: #52514e;
  --text-3: #78776f;
  --line: #dedddb;
  --line-2: #c4c3c0;
  --accent: #2a78d6;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --bg: #14140f;
    --surface: #1c1c18;
    --surface-2: #26261f;
    --text: #f4f4ef;
    --text-2: #c3c2b7;
    --text-3: #93928a;
    --line: #38372f;
    --line-2: #4c4b42;
    --accent: #3987e5;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 28px 20px 64px;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, sans-serif;
  font-size: 15px;
  line-height: 1.55;
}
main { max-width: 1000px; margin: 0 auto; }
h1 { font-size: 26px; line-height: 1.25; margin: 0 0 10px; }
h2 {
  font-size: 19px;
  margin: 40px 0 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--line);
}
h3 { font-size: 16px; margin: 26px 0 8px; }
p { margin: 0 0 12px; }
a { color: var(--accent); }
code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.9em;
  background: var(--surface-2);
  padding: 1px 4px;
  border-radius: 3px;
}
.claim { font-size: 16px; color: var(--text); margin-bottom: 14px; }
.prov, .caption, .note {
  font-size: 13px;
  color: var(--text-2);
}
.prov code { font-size: 0.85em; word-break: break-all; }
.caption { margin: 8px 0 0; }
.notice {
  background: var(--surface);
  border: 1px solid var(--line);
  border-left: 3px solid var(--accent);
  border-radius: 4px;
  padding: 14px 16px;
  margin: 18px 0;
}
.scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 12px 0; }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
caption { caption-side: top; text-align: left; padding-bottom: 6px;
  font-size: 13px; color: var(--text-2); }
th, td {
  border: 1px solid var(--line);
  padding: 6px 10px;
  text-align: left;
  white-space: nowrap;
  vertical-align: top;
}
thead th { background: var(--surface-2); font-weight: 600; }
tbody th { background: var(--surface); font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.ci { color: var(--text-3); font-variant-numeric: tabular-nums; }
.cls-solid_pass { color: var(--accent); font-weight: 600; }
.cls-flaky { color: var(--text); }
.cls-solid_fail { color: var(--text-3); }
.na { color: var(--text-3); }
figure { margin: 16px 0 0; }
svg.chart {
  display: block;
  width: 100%;
  max-width: 700px;
  height: auto;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 4px;
}
svg.chart .grid { stroke: var(--line); stroke-width: 1; }
svg.chart .axis { stroke: var(--line-2); stroke-width: 1; }
svg.chart .ax { font-size: 11px; fill: var(--text-3); }
svg.chart .axname { font-size: 11px; fill: var(--text-2); }
svg.chart .val { font-size: 11px; fill: var(--text-2);
  font-variant-numeric: tabular-nums; paint-order: stroke;
  stroke: var(--surface); stroke-width: 3px; stroke-linejoin: round; }
svg.chart .tick { font-size: 12px; fill: var(--text-2); }
svg.chart .series { fill: none; stroke: var(--accent); stroke-width: 2;
  stroke-linejoin: round; stroke-linecap: round; }
svg.chart .whisker { stroke: var(--accent); stroke-width: 1.5; opacity: 0.55; }
svg.chart .point { fill: var(--accent); stroke: var(--surface);
  stroke-width: 2; }
svg.chart .bar { fill: var(--accent); }
details {
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 10px 14px;
  background: var(--surface);
  margin: 12px 0;
}
details[open] { padding-bottom: 14px; }
summary { cursor: pointer; font-weight: 600; }
ol.caveats { padding-left: 22px; margin: 8px 0 0; }
ol.caveats li { margin-bottom: 8px; color: var(--text-2); }
footer {
  margin-top: 48px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
  font-size: 13px;
  color: var(--text-2);
}
@media (max-width: 640px) {
  body { padding: 20px 12px 48px; }
  h1 { font-size: 22px; }
  th, td { padding: 5px 8px; }
}
"""


# --- charts -----------------------------------------------------------------
#
# One accent colour, recessive grey grid, no gradients, no fills under the line.
# A single series, so no legend is needed; every point carries a direct label
# because there are only a handful of conditions.

_CURVE_W, _CURVE_H = 700, 320
_COST_W, _COST_H = 700, 210


_NICE_STEPS = (1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0)


def _nice_max(value: float, headroom: float = 1.0) -> float:
    """Smallest nice ceiling above ``value * headroom``.

    The headroom keeps the tallest bar clear of the top gridline, so its value
    label has somewhere to sit.
    """
    if not _finite(value) or value <= 0:
        return 1.0
    target = float(value) * headroom
    exp = math.floor(math.log10(target))
    base = 10.0 ** exp
    for mult in _NICE_STEPS:
        if target <= mult * base * (1 + 1e-12):
            return mult * base
    return 10.0 * base


def _svg_open(width: int, height: int, label: str, title: str) -> list[str]:
    return [
        f'<svg class="chart" xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" '
        f'role="img" aria-label="{html.escape(label)}">',
        f"<title>{_esc(title)}</title>",
    ]


def _svg_curve(points: Sequence[Mapping[str, Any]], conf: int) -> str:
    """Pass rate per condition, y from 0 to 1, with CI whiskers."""
    width, height = _CURVE_W, _CURVE_H
    left, right, top, bottom = 62, 24, 22, 52
    inner_w = width - left - right
    inner_h = height - top - bottom
    n = max(len(points), 1)

    def px(i: int) -> float:
        return left + inner_w * (i + 0.5) / n

    def py(v: float) -> float:
        return top + inner_h * (1.0 - max(0.0, min(1.0, float(v))))

    parts = _svg_open(
        width,
        height,
        f"Pass rate by condition with {conf} percent confidence intervals",
        f"Pass rate by condition ({conf}% CI)",
    )
    for gv in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = py(gv)
        parts.append(
            f'<line class="grid" x1="{_num(left)}" y1="{_num(y)}" '
            f'x2="{_num(left + inner_w)}" y2="{_num(y)}" />'
        )
        parts.append(
            f'<text class="ax" x="{_num(left - 9)}" y="{_num(y)}" '
            f'text-anchor="end" dominant-baseline="middle">{gv:.2f}</text>'
        )
    parts.append(
        f'<line class="axis" x1="{_num(left)}" y1="{_num(top)}" '
        f'x2="{_num(left)}" y2="{_num(top + inner_h)}" />'
    )
    parts.append(
        f'<line class="axis" x1="{_num(left)}" y1="{_num(top + inner_h)}" '
        f'x2="{_num(left + inner_w)}" y2="{_num(top + inner_h)}" />'
    )

    # connect only consecutive points that both have a rate
    segments: list[list[str]] = []
    current: list[str] = []
    for i, pt in enumerate(points):
        if _finite(pt["rate"]):
            current.append(f"{_num(px(i))} {_num(py(pt['rate']))}")
        elif current:
            segments.append(current)
            current = []
    if current:
        segments.append(current)
    for seg in segments:
        if len(seg) < 2:
            continue
        parts.append(f'<path class="series" d="M {" L ".join(seg)}" />')

    for i, pt in enumerate(points):
        x = px(i)
        lo, hi, rate = pt["lo"], pt["hi"], pt["rate"]
        if _finite(lo) and _finite(hi) and float(hi) > float(lo):
            y_lo, y_hi = py(lo), py(hi)
            parts.append(
                f'<line class="whisker" x1="{_num(x)}" y1="{_num(y_lo)}" '
                f'x2="{_num(x)}" y2="{_num(y_hi)}" />'
            )
            for cap in (y_lo, y_hi):
                parts.append(
                    f'<line class="whisker" x1="{_num(x - 5)}" '
                    f'y1="{_num(cap)}" x2="{_num(x + 5)}" y2="{_num(cap)}" />'
                )
        if _finite(rate):
            parts.append(
                f'<circle class="point" cx="{_num(x)}" cy="{_num(py(rate))}" '
                f'r="4.5" />'
            )
            top_y = py(hi) if _finite(hi) else py(rate)
            bot_y = py(lo) if _finite(lo) else py(rate)
            if top_y - 10.0 >= top + 10.0:
                label_y = top_y - 10.0
            else:
                label_y = min(bot_y + 15.0, top + inner_h - 4.0)
            parts.append(
                f'<text class="val" x="{_num(x)}" y="{_num(label_y)}" '
                f'text-anchor="middle">{_fmt_rate(rate)}</text>'
            )
        else:
            parts.append(
                f'<text class="val na" x="{_num(x)}" '
                f'y="{_num(top + inner_h / 2)}" text-anchor="middle" '
                f'fill="currentColor">{NA}</text>'
            )
        parts.append(
            f'<text class="tick" x="{_num(x)}" y="{_num(top + inner_h + 20)}" '
            f'text-anchor="middle">{_esc(pt["label"])}</text>'
        )

    parts.append(
        f'<text class="axname" x="{_num(left + inner_w / 2)}" '
        f'y="{_num(height - 10)}" text-anchor="middle">condition</text>'
    )
    parts.append(
        f'<text class="axname" x="14" y="{_num(top + inner_h / 2)}" '
        f'text-anchor="middle" transform="rotate(-90 14 '
        f'{_num(top + inner_h / 2)})">mean pass@1</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def _bar_path(x: float, y: float, w: float, baseline: float) -> str:
    """Bar anchored to the baseline with 4px rounded top corners."""
    h = baseline - y
    r = min(4.0, w / 2.0, max(h, 0.0))
    if h <= 0.5:
        return (
            f'M {_num(x)} {_num(baseline)} L {_num(x + w)} {_num(baseline)}'
        )
    return (
        f"M {_num(x)} {_num(baseline)} "
        f"L {_num(x)} {_num(y + r)} "
        f"Q {_num(x)} {_num(y)} {_num(x + r)} {_num(y)} "
        f"L {_num(x + w - r)} {_num(y)} "
        f"Q {_num(x + w)} {_num(y)} {_num(x + w)} {_num(y + r)} "
        f"L {_num(x + w)} {_num(baseline)} Z"
    )


def _svg_cost(points: Sequence[Mapping[str, Any]]) -> str:
    """Cost per solved instance per condition, as bars."""
    width, height = _COST_W, _COST_H
    left, right, top, bottom = 62, 24, 20, 50
    inner_w = width - left - right
    inner_h = height - top - bottom
    n = max(len(points), 1)
    values = [p["value"] for p in points if _finite(p["value"])]
    vmax = _nice_max(max(values), headroom=1.2) if values else 1.0

    def py(v: float) -> float:
        return top + inner_h * (1.0 - (float(v) / vmax if vmax else 0.0))

    parts = _svg_open(
        width,
        height,
        "Cost per solved instance by condition, US dollars",
        "Cost per solve by condition (USD)",
    )
    for frac in (0.0, 0.5, 1.0):
        gv = vmax * frac
        y = py(gv)
        parts.append(
            f'<line class="grid" x1="{_num(left)}" y1="{_num(y)}" '
            f'x2="{_num(left + inner_w)}" y2="{_num(y)}" />'
        )
        parts.append(
            f'<text class="ax" x="{_num(left - 9)}" y="{_num(y)}" '
            f'text-anchor="end" dominant-baseline="middle">'
            f'{_fmt_money(gv)}</text>'
        )
    parts.append(
        f'<line class="axis" x1="{_num(left)}" y1="{_num(top + inner_h)}" '
        f'x2="{_num(left + inner_w)}" y2="{_num(top + inner_h)}" />'
    )

    band = inner_w / n
    bar_w = min(52.0, band * 0.5)
    baseline = top + inner_h
    for i, pt in enumerate(points):
        cx = left + band * (i + 0.5)
        value = pt["value"]
        if _finite(value):
            y = py(value)
            parts.append(
                f'<path class="bar" d="'
                f'{_bar_path(cx - bar_w / 2, y, bar_w, baseline)}" />'
            )
            parts.append(
                f'<text class="val" x="{_num(cx)}" '
                f'y="{_num(max(top + 10.0, y - 7.0))}" text-anchor="middle">'
                f'{_fmt_money(value)}</text>'
            )
        else:
            parts.append(
                f'<text class="val" x="{_num(cx)}" y="{_num(baseline - 7)}" '
                f'text-anchor="middle">{NA}</text>'
            )
        parts.append(
            f'<text class="tick" x="{_num(cx)}" '
            f'y="{_num(baseline + 20)}" text-anchor="middle">'
            f'{_esc(pt["label"])}</text>'
        )
    parts.append(
        f'<text class="axname" x="14" y="{_num(top + inner_h / 2)}" '
        f'text-anchor="middle" transform="rotate(-90 14 '
        f'{_num(top + inner_h / 2)})">USD per solve</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


# --- table fragments --------------------------------------------------------


def _k_text(row: Mapping[str, Any]) -> str:
    k_min, k_max = row.get("k_min"), row.get("k_max")
    if k_min is None or k_max is None:
        return NA
    return str(int(k_min)) if k_min == k_max else f"{int(k_min)}-{int(k_max)}"


def _cost_per_solve(cost: Mapping[str, Any]) -> float | None:
    """None when no run in the condition reported a cost at all.

    ``stats.cost_summary`` sums an empty cost list to 0.0, so a condition whose
    runs never reported ``total_cost_usd`` would otherwise show a confident
    $0.00 per solve. Unknown is not zero.
    """
    if not cost.get("n_cost_reported"):
        return None
    return cost.get("cost_per_solve")


def _cls_html(cls: str) -> str:
    return f'<span class="cls-{_esc(cls)}">{_esc(cls)}</span>'


def _headline_table(
    data: Mapping[str, Any], conds: Sequence[str], conf: int, caption: str
) -> str:
    pc = data["per_condition"]
    out = ['<div class="scroll">', "<table>"]
    if caption:
        out.append(f"<caption>{_esc(caption)}</caption>")
    out.append("<thead><tr>")
    out.append("<th>condition</th>")
    for name in (
        "instances",
        "k",
        f"pass rate ({conf}% CI)",
        "solid_pass",
        "flaky",
        "solid_fail",
        "resolved / counted",
        "cost per solve",
        "mean cost per run",
        "mean wall (s)",
        "infra failures",
    ):
        out.append(f'<th class="num">{_esc(name)}</th>')
    out.append("</tr></thead><tbody>")
    for cond in conds:
        row = pc[cond]
        counts = row["class_counts"]
        cost = row["cost"]
        rate = _fmt_rate(row["pass_rate"])
        ci = (
            f'<span class="ci">[{_fmt_rate(row["ci_lo"])}, '
            f'{_fmt_rate(row["ci_hi"])}]</span>'
        )
        out.append("<tr>")
        out.append(f"<th>{_esc(cond)}</th>")
        out.append(f'<td class="num">{row["n_instances"]}</td>')
        out.append(f'<td class="num">{_k_text(row)}</td>')
        out.append(f'<td class="num">{rate} {ci}</td>')
        out.append(f'<td class="num">{counts["solid_pass"]}</td>')
        out.append(f'<td class="num">{counts["flaky"]}</td>')
        out.append(f'<td class="num">{counts["solid_fail"]}</td>')
        out.append(
            f'<td class="num">{cost["resolved_count"]} / '
            f'{cost["n_counted"]}</td>'
        )
        out.append(
            f'<td class="num">{_fmt_money(_cost_per_solve(cost))}</td>'
        )
        out.append(
            f'<td class="num">{_fmt_money(cost["mean_cost_per_run"])}</td>'
        )
        out.append(f'<td class="num">{_fmt_secs(cost["mean_wall_s"])}</td>')
        out.append(f'<td class="num">{cost["infra_failures_total"]}</td>')
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)


def _transition_table(cmp_: Mapping[str, Any]) -> str:
    tt = cmp_["transition_table"]
    a, b = cmp_["cond_a"], cmp_["cond_b"]
    out = ['<div class="scroll">', "<table>"]
    out.append(
        f"<caption>Class transitions: rows are {_esc(a)}, "
        f"columns are {_esc(b)}.</caption>"
    )
    out.append(f"<thead><tr><th>{_esc(a)} to {_esc(b)}</th>")
    for cls in tt["classes"]:
        out.append(f'<th class="num">{_esc(cls)}</th>')
    out.append("</tr></thead><tbody>")
    for i, cls in enumerate(tt["classes"]):
        out.append(f"<tr><th>{_cls_html(cls)}</th>")
        for value in tt["matrix"][i]:
            out.append(f'<td class="num">{value}</td>')
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)


def _paired_block(cmp_: Mapping[str, Any]) -> str:
    a, b = cmp_["cond_a"], cmp_["cond_b"]
    disc = cmp_["discordant"]
    wil = cmp_["wilcoxon"]
    sgn = cmp_["sign_test"]
    out = [f"<h3>{_esc(a)} to {_esc(b)}</h3>"]
    out.append(
        f'<div class="scroll"><table>'
        f"<caption>Paired on the {cmp_['n_instances']} instance(s) present in "
        f"both conditions ({cmp_['n_only_a']} only in {_esc(a)}, "
        f"{cmp_['n_only_b']} only in {_esc(b)}).</caption>"
        "<thead><tr><th>measure</th><th class=\"num\">value</th>"
        "<th>reading</th></tr></thead><tbody>"
    )
    rows = [
        (
            "flips_up",
            str(cmp_["flips_up"]),
            f"solid_fail in {_esc(a)} became solid_pass in {_esc(b)}",
        ),
        (
            "regressions",
            str(cmp_["regressions"]),
            f"solid_pass in {_esc(a)} stopped being solid_pass in {_esc(b)}",
        ),
        (
            "discordant pairs",
            str(disc["n_discordant"]),
            f"{disc['b_only']} favour {_esc(b)}, {disc['a_only']} favour "
            f"{_esc(a)}; concordant: {disc['both']} pass, "
            f"{disc['neither']} fail",
        ),
        (
            "Wilcoxon p",
            _fmt_p(wil["p_value"]),
            (
                f"signed-rank on per-instance pass counts, "
                f"n_nonzero = {wil['n_nonzero']}"
                + (f"; {_esc(wil['note'])}" if wil["note"] else "")
            ),
        ),
        (
            "sign-test p",
            _fmt_p(sgn["p_value"]),
            (
                f"exact test on {sgn['n_discordant']} discordant majority "
                f"pair(s)" + (f"; {_esc(sgn['note'])}" if sgn["note"] else "")
            ),
        ),
    ]
    for name, value, reading in rows:
        out.append(
            f"<tr><th>{_esc(name)}</th>"
            f'<td class="num">{value}</td><td>{reading}</td></tr>'
        )
    out.append("</tbody></table></div>")
    if cmp_["k_mismatch_instances"]:
        shown = ", ".join(_esc(i) for i in cmp_["k_mismatch_instances"][:5])
        out.append(
            f'<p class="note">k differs between conditions for '
            f'{len(cmp_["k_mismatch_instances"])} instance(s): {shown}'
            f'{" and more" if len(cmp_["k_mismatch_instances"]) > 5 else ""}.'
            f"</p>"
        )
    out.append(_transition_table(cmp_))
    return "\n".join(out)


def _per_instance_table(data: Mapping[str, Any], conds: Sequence[str]) -> str:
    pc = data["per_condition"]
    ids: set[str] = set()
    for cond in conds:
        ids.update(pc[cond]["per_instance"])
    ordered_ids = sorted(ids)
    out = ["<details>"]
    out.append(
        f"<summary>Per-instance results ({len(ordered_ids)} instance(s))"
        "</summary>"
    )
    out.append(
        '<p class="caption">Pass count out of k, and the resulting class, for '
        "every instance in every condition. Instances a condition never ran "
        f"show {NA}.</p>"
    )
    out.append('<div class="scroll"><table>')
    out.append("<thead><tr><th>instance_id</th><th>repo</th>")
    for cond in conds:
        out.append(f'<th class="num">{_esc(cond)}</th>')
    out.append("</tr></thead><tbody>")
    for iid in ordered_ids:
        out.append(f"<tr><th>{_esc(iid)}</th><td>{_esc(_repo_of(iid))}</td>")
        for cond in conds:
            cell = pc[cond]["per_instance"].get(iid)
            if cell is None:
                out.append(f'<td class="num na">{NA}</td>')
            else:
                out.append(
                    f'<td class="num">{cell["passes"]}/{cell["k"]} '
                    f'{_cls_html(cell["class"])}</td>'
                )
        out.append("</tr>")
    out.append("</tbody></table></div></details>")
    return "\n".join(out)


def _infra_table(data: Mapping[str, Any], conds: Sequence[str]) -> str:
    pc = data["per_condition"]
    rows: list[str] = []
    for cond in conds:
        infra = pc[cond]["cost"]["infra_failures"]
        for outcome in sorted(infra):
            rows.append(
                f"<tr><th>{_esc(cond)}</th><td>{_esc(outcome)}</td>"
                f'<td class="num">{infra[outcome]}</td></tr>'
            )
    if not rows:
        return '<p class="note">None recorded.</p>'
    out = ['<div class="scroll"><table>']
    out.append(
        "<caption>Runs that did not count toward k and were re-run. These are "
        "not missing at random, so they travel with every headline number."
        "</caption>"
    )
    out.append(
        "<thead><tr><th>condition</th><th>outcome</th>"
        '<th class="num">runs</th></tr></thead><tbody>'
    )
    out.extend(rows)
    out.append("</tbody></table></div>")
    return "\n".join(out)


# --- page -------------------------------------------------------------------


def _how_to_read(protocol: Mapping[str, Any] | None) -> list[str]:
    if not protocol or not protocol.get("caveats"):
        return []
    out = ["<h2>How to read this</h2>"]
    out.append(
        "<p>A run counts toward k only when the agent had its chance "
        "(<code>resolved</code>, <code>unresolved</code>, <code>no_diff</code>, "
        "<code>budget</code>, <code>timeout</code>). Infrastructure failures "
        "(<code>paused</code>, <code>error</code>, <code>parse_error</code>) "
        "are re-run and reported separately. Per instance and condition the "
        "class is solid_pass (k of k), solid_fail (0 of k), or flaky. The "
        "bootstrap resamples <em>instances</em>, not runs, because the k "
        "repeats of one instance are not independent observations.</p>"
    )
    out.append(
        '<p class="caption">Caveats, copied from '
        "<code>docs/protocol.md</code> at generation time:</p>"
    )
    out.append('<ol class="caveats">')
    for item in protocol["caveats"]:
        out.append(f"<li>{_md_inline(item)}</li>")
    out.append("</ol>")
    return out


def _footer(protocol: Mapping[str, Any] | None) -> list[str]:
    out = ["<footer>"]
    rows = protocol.get("versions_rows") if protocol else None
    if rows:
        header = protocol.get("versions_header") or ["component", "value"]
        out.append("<p><strong>Pinned versions</strong></p>")
        out.append('<div class="scroll"><table><thead><tr>')
        for cell in header:
            out.append(f"<th>{_md_inline(cell)}</th>")
        out.append("</tr></thead><tbody>")
        for row in rows:
            out.append("<tr>")
            for j, cell in enumerate(row):
                tag = "th" if j == 0 else "td"
                out.append(
                    f'<{tag} style="white-space:normal">'
                    f"{_md_inline(cell)}</{tag}>"
                )
            out.append("</tr>")
        out.append("</tbody></table></div>")
    out.append(
        "<p>This page is generated by <code>bench/site.py</code> from the run "
        "manifest and is never hand edited. Regenerate with "
        "<code>python -m bench.site --runs results/runs.jsonl --out "
        "results/site</code>.</p>"
    )
    out.append("</footer>")
    return out


def render_page(
    data: Mapping[str, Any],
    mains: Sequence[str],
    cands: Sequence[str],
    title: str = DEFAULT_TITLE,
    provenance: Mapping[str, Any] | None = None,
    protocol: Mapping[str, Any] | None = None,
) -> str:
    """Full ``index.html`` text for a :func:`bench.stats.summarize` structure."""
    params = data["params"]
    conf = int(round((1.0 - float(params["alpha"])) * 100))
    pc = data["per_condition"]
    mains = [c for c in mains if c in pc]
    cands = [c for c in cands if c in pc]
    ordered = list(mains) + list(cands)
    has_runs = int(data["n_runs_loaded"]) > 0

    body: list[str] = ["<main>"]
    body.append(f"<h1>{_esc(title)}</h1>")
    body.append(f'<p class="claim">{CLAIM}</p>')
    if provenance:
        body.append(
            f'<p class="prov">Generated from '
            f'<code>{_esc(provenance["name"])}</code> with '
            f'{provenance["n_lines"]} lines, sha256 '
            f'<code>{_esc(provenance["sha256"])}</code>. '
            f'{data["n_runs_loaded"]} runs loaded, {data["n_runs_counted"]} '
            f"counted toward k. Bootstrap: {params['n_boot']} instance "
            f"resamples, seed {params['seed']}, alpha {params['alpha']}.</p>"
        )

    if not has_runs:
        body.append(
            '<div class="notice"><p><strong>No runs yet.</strong> The manifest '
            "has no usable run lines, so there is nothing to summarise. This "
            "page will fill in as <code>results/runs.jsonl</code> grows.</p>"
            "</div>"
        )
    else:
        body.append("<h2>Headline</h2>")
        if mains:
            body.append(
                _headline_table(
                    data,
                    mains,
                    conf,
                    "One row per condition. Rates are the mean over instances "
                    "of passes/k; N instances, not N*k runs, sets the width of "
                    "the interval.",
                )
            )
        else:
            body.append('<p class="note">No headline conditions found.</p>')
        if cands:
            body.append("<details>")
            body.append(
                f"<summary>Candidate screens ({len(cands)})</summary>"
            )
            body.append(
                '<p class="caption">Improver screens at reduced k. These are '
                "screening statistics, not headline results.</p>"
            )
            body.append(_headline_table(data, cands, conf, ""))
            body.append("</details>")

        if mains:
            body.append("<h2>Pass rate by condition</h2>")
            points = [
                {
                    "label": cond,
                    "rate": pc[cond]["pass_rate"],
                    "lo": pc[cond]["ci_lo"],
                    "hi": pc[cond]["ci_hi"],
                }
                for cond in mains
            ]
            body.append("<figure>")
            body.append(_svg_curve(points, conf))
            body.append(
                f'<figcaption class="caption">Mean pass@1 per condition; '
                f"whiskers are the {conf}% bootstrap interval over instances. "
                "Overlapping intervals do not mean the paired difference is "
                "null, because the conditions share instances.</figcaption>"
            )
            body.append("</figure>")

            cost_points = [
                {"label": cond, "value": _cost_per_solve(pc[cond]["cost"])}
                for cond in mains
            ]
            if any(_finite(p["value"]) for p in cost_points):
                body.append("<figure>")
                body.append(_svg_cost(cost_points))
                body.append(
                    '<figcaption class="caption">Total condition cost divided '
                    "by resolved runs; failed runs stay in the numerator by "
                    "design. Client-side estimate at API list price, not a "
                    "subscription cost.</figcaption>"
                )
                body.append("</figure>")
            else:
                body.append(
                    '<p class="note">No cost data reported, so there is no '
                    "cost per solve chart.</p>"
                )

        main_set = set(mains)
        pairs = [
            cmp_
            for cmp_ in data["paired"]
            if cmp_["cond_a"] in main_set and cmp_["cond_b"] in main_set
        ]
        if pairs:
            body.append("<h2>Paired comparisons</h2>")
            body.append(
                '<p class="caption">Each comparison is paired on the instances '
                "the two conditions share, so instance difficulty cancels "
                "instead of swamping the effect. The p-values are not "
                "corrected for multiple comparisons.</p>"
            )
            for cmp_ in pairs:
                body.append(_paired_block(cmp_))

        if ordered:
            body.append("<h2>Per-instance detail</h2>")
            body.append(_per_instance_table(data, ordered))

            body.append("<h2>Infrastructure failures</h2>")
            body.append(_infra_table(data, ordered))

    body.extend(_how_to_read(protocol))
    body.append("</main>")
    body.extend(_footer(protocol))

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, '
            'initial-scale=1">',
            f"<title>{_esc(title)}</title>",
            "<style>" + CSS.strip() + "</style>",
            "</head>",
            "<body>",
            *body,
            "</body>",
            "</html>",
            "",
        ]
    )


# --- build ------------------------------------------------------------------


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def build(
    runs_path: str | os.PathLike[str],
    out_dir: str | os.PathLike[str],
    conditions: Sequence[str] | None = None,
    seed: int = 0,
    title: str = DEFAULT_TITLE,
    n_boot: int = 10000,
    alpha: float = 0.05,
    protocol_path: str | os.PathLike[str] | None = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    """Write ``index.html`` and ``data.json`` into ``out_dir``.

    Byte-identical for the same manifest, conditions, seed and title.
    """
    runs_src = os.fspath(runs_path)
    out = os.fspath(out_dir)
    provenance = _provenance(runs_src)
    runs = stats.load_runs(runs_src)

    explicit = bool(conditions)
    found = (
        list(conditions)
        if explicit
        else sorted(
            {
                run["condition"]
                for run in runs
                if isinstance(run.get("condition"), str)
            }
        )
    )
    mains, cands = order_conditions(found, explicit=explicit)
    ordered = mains + cands

    data = stats.summarize(
        runs, ordered, n_boot=n_boot, seed=seed, alpha=alpha
    )
    protocol = read_protocol(
        os.fspath(protocol_path) if protocol_path else None
    )
    page = render_page(
        data,
        mains=mains,
        cands=cands,
        title=title,
        provenance=provenance,
        protocol=protocol,
    )

    os.makedirs(out, exist_ok=True)
    index_path = os.path.join(out, "index.html")
    data_path = os.path.join(out, "data.json")
    _write(index_path, page)
    _write(
        data_path,
        json.dumps(_json_safe(data), indent=2, sort_keys=False) + "\n",
    )
    return {
        "index_html": index_path,
        "data_json": data_path,
        "data": data,
        "provenance": provenance,
        "conditions": ordered,
        "html": page,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m bench.site",
        description="Render results/runs.jsonl into a static results page.",
    )
    parser.add_argument("--runs", required=True, help="path to runs.jsonl")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument(
        "--conditions",
        nargs="*",
        default=None,
        help="conditions in comparison order (default: all found, sorted)",
    )
    parser.add_argument("--seed", type=int, default=0, help="bootstrap seed")
    parser.add_argument(
        "--title", default=DEFAULT_TITLE, help="page title (h1 and tab)"
    )
    parser.add_argument(
        "--n-boot", type=int, default=10000, help="bootstrap resamples"
    )
    parser.add_argument(
        "--alpha", type=float, default=0.05, help="1 - confidence level"
    )
    parser.add_argument(
        "--protocol",
        default=DEFAULT_PROTOCOL,
        help="docs/protocol.md, for caveats and pinned versions",
    )
    args = parser.parse_args(argv)

    if not os.path.isfile(args.runs):
        print(f"site: error: no such runs file: {args.runs}", file=sys.stderr)
        return 2

    result = build(
        args.runs,
        args.out,
        conditions=args.conditions,
        seed=args.seed,
        title=args.title,
        n_boot=args.n_boot,
        alpha=args.alpha,
        protocol_path=args.protocol,
    )
    print(f"wrote {result['index_html']}")
    print(f"wrote {result['data_json']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
