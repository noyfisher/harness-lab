# Owner decisions queue

The queue of things the loop cannot decide for itself. Each item carries its evidence and its
consequence. When decided, mark DECIDED with date and outcome; never delete.

(empty)

- [2026-09-05] **Improver loop wedged: 4 consecutive rejected variants** (`improver-wedge:20260905T085311`). DECIDE.
  - Evidence: 20260905T001449 (cand-1c1a458) — train k=1 screen: zero solid_fail -> pass flips; 20260905T011537 (cand-6e9817c) — train k=1 screen: zero solid_fail -> pass flips; 20260905T022623 (cand-5777b17) — confirmation k=3: 1 held-out regression(s) (matplotlib__matplotlib-20859); 20260905T085311 (cand-b64eadc) — train k=1 screen: 2 solid_pass regression(s) (sphinx-doc__sphinx-10466, sympy__sympy-19040) (full records in `improver/state/archive.json`).
  - Consequence: `python -m improver.loop` now refuses to propose and spends nothing until this is decided; the cap is `--max-consecutive-rejects 4`.
  - Options: revise `.claude/commands/improve.md` (the hypotheses being generated are not working), raise the cap and keep searching, or stop the loop and write up "no variant beat baseline beyond noise" as the finding.
