# Failure taxonomy, version 1

**This file is NOT an input to the harness.** It is a human-facing analysis. It quotes hidden
test names for diagnosis. No hidden test name, expected value, or gold-patch path from this
document may be copied into `harness/`, `bench/c0-prompt.md`, or any prompt an agent sees.

Scope: the TRAIN split only. Dossiers read: `results/dossiers/C1/INDEX.md` (7 instances,
21 runs) and `results/dossiers/C0/INDEX.md` (6 instances, 18 runs). Four files under
`results/dossiers/C0/` (matplotlib-20676, seaborn-3187, sphinx-7748, sympy-19783) are
held-out instances not linked from that INDEX; they were deliberately not read.

## 1. Headline

| metric | C0 (single agent) | C1 (seeded multi-agent) |
|---|---|---|
| pass@1, 40 instances, k=3 | **0.783** (95% CI 0.658 to 0.900) | **0.750** (95% CI 0.625 to 0.875) |
| classes | 30 solid_pass / 3 flaky / 7 solid_fail | 28 / 3 / 9 |
| cost per solve | $1.00 | $1.73 |
| mean cost per run | $0.79 | $1.30 |
| mean wall | 212 s | 367 s |
| mean turns | 35.3 | 34.1 |
| infra failures | 0 | 0 |

Transition table (C0 rows to C1 columns, 40 paired instances):

| C0 \ C1 | solid_pass | flaky | solid_fail |
|---|---|---|---|
| solid_pass | 28 | 1 | 1 |
| flaky | 0 | 2 | 1 |
| solid_fail | 0 | 0 | 7 |

`flips_up` = 0, `regressions` = 2, discordant majority pairs = 2 (1 each way), Wilcoxon
p = 0.257 (n_nonzero = 4), sign test p = 1.0.

Plainly: the seeded harness is not better than the single agent on this subset, and it costs
about 1.7x per solved instance. The 3.3-point gap runs the wrong way and is inside noise: no
instance moved from solid_fail to solid_pass, both paired tests are non-significant, and the
per-condition CIs overlap almost entirely.

## 2. Failure modes

Modes are not exclusive; most failing runs carry two or three. "Signals" are what to grep for
in a trace or dossier.

### Process failures (a harness rule could plausibly prevent these)

**P1. Example-locked reproduction.** The repro is a transcription of the issue's snippet and
the fix is validated against nothing else, so it covers the literal case and misses the
sibling case the maintainers fixed. Signals: repro mirrors the issue verbatim; no second,
adversarially chosen input. django-15732 is the cleanest instance: every run keyed on "primary
key" in the body and added `primary_key: False`, while the hidden test
`test_remove_unique_together_on_unique_field` uses an ordinary field with its own
`unique=True`, which the issue *title* names. C1: 15732 r0-r2, 16667 r0-r2. C0: identical.

**P2. Rationalized red test.** A nearest existing test goes red and the agent argues it away
in `notes` rather than stopping; `blocked` stays false. Signals: "expected failure", "asserted
the old buggy behavior as correct", alongside a non-zero test exit code reported as done. Seen
on pylint-8898, where `tests/config/test_config.py::test_csv_regex_error` asserts the pre-fix
crash. C1: r0, r2. C0: r1 (which nonetheless resolved, the only pass in the pylint set).

**P3. Constraint inversion.** The opposite reflex to P2: the fix is designed so the
bug-asserting test stays green, shipping semantics nobody asked for. Signal: notes saying the
design "is the only fix compatible with that existing unmodifiable test", or an escape syntax
invented from scratch. The backslash-escape variants of pylint-8898 do this and break a
pass-to-pass test too. C1: r1. C0: r0, r2.

**P4. Router collapse (Lead implements it itself).** `lead.md` step 2 says "You never edit
library code yourself, at any size", but the router classifies nearly everything XS and the
Lead then greps, edits `/testbed`, tests and signs off alone. Signals: `specialists spawned:
[]` with Edit calls on `/testbed`; messages like "This is XS-sized ... so I completed it
directly without spawning specialists". 10 of the 19 failing C1 train runs spawned nobody.

**P5. Confidence miscalibration.** `confidence` >= 0.85 with `blocked: false` on a run where
every hidden test fails. django-16667 reports 0.90 to 0.95 across six runs of a patch that
fails its hidden test. sphinx-7985 is the honest counterexample at 0.55 to 0.70.

**P6. Standing-rule violations.** The rules exist; nothing enforces them. Signals: `git stash`
in the bash list (banned by rule 6); `files edited` outside `/testbed` and `/task/repro/`,
specifically writes to `/harness/projects/-testbed/memory/`; one C0 sphinx-7985 run ran `pip
download`, breaking the no-network rule and self-reporting it. None caused a graded failure,
but they show the done-condition is self-attested rather than checked.

**P7. Single-file tunnel vision.** No run in either condition produced a patch touching more
than one file, although two of the six shared failing instances have multi-file gold patches
(pylint-8898: 3 files; sympy-22080: 2). Signal: `files_changed` length 1 plus a "minimal fix"
quote in the notes.

### Task-difficulty failures

**T1. Symptom site instead of invariant site.** The patch lands where the traceback surfaces;
the owner of the broken invariant is a layer away. sympy-20428: every run patched
`densetools.py` or `densearith.py` to strip a stray zero, while the gold patch is in
`sympy/polys/domains/expressiondomain.py`. Recognizable as: repro passes, suite green, hidden
test still asserts an equality the patch never establishes.

**T2. Underspecified contract.** The issue says what should happen but not in what form, and
the hidden tests pin an exact status string, message, or count. sphinx-7985 is a feature
request; `test_defaults` asserts a row count and `test_anchors_ignored` a status label that no
reading of the issue determines. django-16667 is the same shape at smaller scale: the fallback
return value is a free choice and the hidden parametrization expects one specific string.

**T3. Environment cannot exercise the real path.** django-15732 is a PostgreSQL introspection
bug and the container has SQLite only. Every run monkeypatched `get_constraints()` to imitate
Postgres, so the repro could only confirm the assumption its author had already made.

**T4. Coupled multi-site change required.** sympy-22080 needs both `precedence.py` and
`codeprinter.py`; every run fixed one site, cleared two of three hidden tests and left
`test_create_expand_pow_optimization` failing. Recognizable as: F2P partially passing.

### Grading artifacts

**G1. Pass-to-pass regression.** The patch applies and addresses the issue but breaks an
existing test. C1: pylint-8898 r1. C0: pylint-8898 r0, r2 (all three the P3 design).

**G2. Patch failed to apply.** Not observed; `applied=True` on all 39 dossier runs.

**G3. Hidden test is a rewritten existing test.** For pylint-8898, sphinx-7985 and
django-16667 the `test_patch` edits a test that already exists in the repo with different
expectations. This is what makes P2 and P3 decisive rather than cosmetic: the agent can see
the old assertion and cannot see that it is about to be replaced.

## 3. Counts

Failing runs in the train dossiers: C1 = 19 of 21, C0 = 17 of 18. Modes overlap.

| mode | C1 runs | C1 instances | C0 runs | C0 instances |
|---|---|---|---|---|
| P1 example-locked repro | 6 | 2 | 6 | 2 |
| P2 rationalized red test | 2 | 1 | 0 | 1 (in the passing run) |
| P3 constraint inversion | 1 | 1 | 2 | 1 |
| P4 router collapse | 10 | 5 | n/a | n/a |
| P5 confidence miscalibration | 11 | 4 | 9 | 4 |
| P6 standing-rule violation | 4 | 3 | 8 | 5 |
| P7 single-file tunnel vision | 6 | 2 | 5 | 2 |
| T1 symptom vs invariant site | 3 | 1 | 3 | 1 |
| T2 underspecified contract | 6 | 2 | 6 | 2 |
| T3 environment limit | 3 | 1 | 3 | 1 |
| T4 coupled multi-site change | 3 | 1 | 3 | 1 |
| G1 P2P regression | 1 | 1 | 2 | 1 |
| G2 patch failed to apply | 0 | 0 | 0 | 0 |
| G3 hidden test rewrites existing test | 9 | 3 | 8 | 3 |

## 4. What C1 does differently on the same failing instances

On the six instances that fail under both conditions (18 runs each), C1 spends more and reads
more, and none of it changes the grade:

| | C0 | C1 |
|---|---|---|
| mean cost per run | $0.88 | $1.27 |
| mean wall | 220 s | 313 s |
| bash commands (total / mean) | 230 / 12.8 | 479 / 26.6 |
| Read calls (total / mean) | 109 / 6.1 | 198 / 11.0 |
| distinct test invocations (total / mean) | 55 / 3.1 | 86 / 4.8 |
| runs with zero specialists spawned | n/a | 10 of 18 |

The extra cost does buy more evidence-gathering: roughly twice the shell commands, 1.8x the
reads, 1.6x the test invocations. It buys zero flips.

Where the structure hurts:

- **It is often absent.** More than half the failing C1 runs spawn nobody (P4). django-15732
  and sympy-22080 ran all three repeats with an empty roster, making C1 a slower C0.
- **Review pressure produces elaboration, not correctness.** pylint-8898 is the sharpest case.
  C0 r1 (zero spawns, $0.69) shipped a splitter tracking only `{}` and `[]`, and resolved. C1
  r0 and r2 (4 spawns each, $1.82 and $1.70, with a second backend-dev or tester round) shipped
  splitters that also track parentheses and character-class edge cases; both failed
  `test_csv_regex_error`. The review rounds made the patch bigger and moved it away from the
  graded behavior.
- **Reviewer approval is treated as evidence despite the rule against it.** sympy-20428 r0:
  "The code-reviewer approved. All done conditions are satisfied", submitted at confidence
  0.85, with the patch in the wrong module.
- **Heaviest orchestration, worst result.** sphinx-7985 r0 spawned 7 specialists over 795 s
  and $2.65 across three backend-dev rounds, still failed both hidden tests, and spent the
  review rounds adding false-positive guards in a region the hidden tests never touch.
- **Structure can convert a pass into a loss.** On django-15128 (solid under C0, flaky under
  C1) the spawn-free repeat r0 ($0.94) matched the gold shape with a one-line assertion
  relaxation and passed; the two repeats that spawned a code-reviewer produced much larger
  alias-threading patches, one of which ($1.87) failed with a SQL error. The headline
  regressions are sympy-14248 (solid_pass to solid_fail) and django-15128 (to flaky);
  sympy-14248 is held out, so no trace evidence is available here.

## 5. Three candidate hypotheses for the improver

Suggestions for a human reader. The improver forms its own; these are not instructions to it.

1. **Adversarial second case in the reproduction.** In `harness/commands/swe-fix.md` rule 1
   and the tester mode-A brief in `harness/agents/tester.md`, require the repro to contain two
   failing cases: the issue's literal example, and one sibling that generalizes the condition
   the issue names (another entity with the same property, another member of the same input
   class). Require `backend-dev` to state in one sentence which class of inputs the fix
   covers. Plausible train flips: 1 to 2 (django-15732 near-certain, since the correct
   generalization is one keyword away; django-16667 possible).
2. **Invariant ownership, and permission to touch more than one file.** In
   `harness/agents/planner.md`, require the plan to name the module that *owns* the violated
   invariant and to list one alternative site a layer up or down the call stack, with the
   reason for the choice. In `harness/commands/swe-fix.md` rule 3, restate "minimal fix" to
   mean smallest correct change, not fewest files, when the invariant spans modules. Plausible
   train flips: 1 to 2 (sympy-22080 is the better bet, with 2 of 3 hidden tests already
   passing; sympy-20428 needs real domain insight).
3. **A red nearest test is a blocker.** In `harness/agents/lead.md` step 8 and the playbook:
   if a nearest existing test that passed on the unmodified repo fails after the fix, the Lead
   must either obtain a fix that keeps it green or set `blocked: true` with `confidence <=
   0.3`. Forbid both halves of the pylint trap: never argue in `notes` that a failing existing
   test is wrong, and never choose a fix design in order to keep a test that asserts the
   reported bug. Plausible train flips: 1 (pylint-8898), plus removal of the three G1 P2P
   regressions.

## 6. Limits of this taxonomy

n is small and thin in exactly the places that matter. There are 24 train instances; only 6
are C1 solid_fail on the train split. C1 has 9 solid_fail on the full 40-instance subset, but
3 of those are held out with no dossier, so every claim here about "C1's failure profile" is a
claim about six instances and nineteen runs. Mode assignments are one reader's judgment from
dossier summaries, tool tallies and diffs, not a coded rubric with a second annotator. The
process versus task-difficulty boundary is the softest part: T1 would become a process failure
under a harness that forced an ownership question, and P1 would become task difficulty if the
issue body were genuinely the only evidence available. P6 counts depend on what the dossiers
happened to capture, so they are lower bounds. Finally, hidden test names appear throughout
because they are the only way to say what went wrong; they must never reach the harness, a
prompt, or an agent definition, or every number in section 1 becomes meaningless.
