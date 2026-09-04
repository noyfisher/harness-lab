# sympy__sympy-20428 under C1: solid_fail (0/3 passes)

repo: sympy/sympy  version: 1.8  difficulty: 15 min - 1 hour

## Problem statement

Result from clear_denoms() prints like zero poly but behaves wierdly (due to unstripped DMP)
The was the immediate cause of the ZeroDivisionError in #17990.

Calling `clear_denoms()` on a complicated constant poly that turns out to be zero:

```
>>> from sympy import *
>>> x = symbols("x")
>>> f = Poly(sympify("-117968192370600*18**(1/3)/(217603955769048*(24201 + 253*sqrt(9165))**(1/3) + 2273005839412*sqrt(9165)*(24201 + 253*sqrt(9165))**(1/3)) - 15720318185*2**(2/3)*3**(1/3)*(24201 + 253*sqrt(9165))**(2/3)/(217603955769048*(24201 + 253*sqrt(9165))**(1/3) + 2273005839412*sqrt(9165)*(24201 + 253*sqrt(9165))**(1/3)) + 15720318185*12**(1/3)*(24201 + 253*sqrt(9165))**(2/3)/(217603955769048*(24201 + 253*sqrt(9165))**(1/3) + 2273005839412*sqrt(9165)*(24201 + 253*sqrt(9165))**(1/3)) + 117968192370600*2**(1/3)*3**(2/3)/(217603955769048*(24201 + 253*sqrt(9165))**(1/3) + 2273005839412*sqrt(9165)*(24201 + 253*sqrt(9165))**(1/3))"), x)
>>> coeff, bad_poly = f.clear_denoms()
>>> coeff
(217603955769048*(24201 + 253*sqrt(9165))**(1/3) + 2273005839412*sqrt(9165)*(24201 + 253*sqrt(9165))**(1/3)
>>> bad_poly
Poly(0, x, domain='EX'))
```

The result prints like the zero polynomial but behaves inconsistently:

```
>>> bad_poly
Poly(0, x, domain='EX')
>>> bad_poly.is_zero
False
>>> bad_poly.as_expr()
0
>>> _.is_zero
True
```

~~There may be valid cases (at least with EX coefficients) where the two valued Poly.is_zero is False but as_expr() evaluates to 0~~ (@jksuom points out this is a bug in #20428), but other Poly methods don't handle `bad_poly` very well.

e.g.

```
>>> Poly(0, x).terms_gcd()
((0,), Poly(0, x, domain='ZZ'))
>>> bad_poly.terms_gcd()
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
  File "/Users/ehren/Documents/esym26/sympy/polys/polytools.py", line 1227, in terms_gcd
    J, result = f.rep.terms_gcd()
  File "/Users/ehren/Documents/esym26/sympy/polys/polyclasses.py", line 410, in terms_gcd
    J, F = dmp_terms_gcd(f.rep, f.lev, f.dom)
  File "/Users/ehren/Documents/esym26/sympy/polys/densebasic.py", line 1681, in dmp_terms_gcd
    G = monomial_min(*list(F.keys()))
  File "/Users/ehren/Documents/esym26/sympy/polys/monomials.py", line 359, in monomial_min
    M = list(monoms[0])
IndexError: tuple index out of range
```

Also sometime in the last year Poly.primitive has been changed to slightly better handle this bad poly.

```
>>> Poly(0, x).primitive()
(0, Poly(0, x, domain='ZZ'))
>

## Gold patch touches (files only): sympy/polys/domains/expressiondomain.py

## Run r0: outcome=unresolved resolved=False turns=46 cost=$1.09 wall=260.4s

Agent summary:
```json
{
 "files_changed": [
  "sympy/polys/densearith.py"
 ],
 "tests_run": [
  "python /task/repro/repro.py",
  "python -c \"import sympy; sympy.test('sympy/polys/tests/test_densearith.py', verbose=False)\"",
  "python -c \"import sympy; sympy.test('sympy/polys/tests/test_densetools.py', 'sympy/polys/tests/test_densebasic.py', 'sympy/polys/tests/test_polytools.py', 'sympy/polys/tests/test_polyclasses.py', verbose=False)\"",
  "python -c \"import sympy; sympy.test('sympy/polys/', verbose=False)\""
 ],
 "reproduction": {
  "script": "/task/repro/repro.py",
  "passes": true
 },
 "confidence": 0.85,
 "blocked": false,
 "notes": "Root cause: dup_mul_ground/dmp_mul_ground in sympy/polys/densearith.py multiplied each coefficient by the ground constant but never stripped leading zeros from the result, unlike every sibling arithmetic function in the file (dup_add, dmp_add, dup_mul, etc.). In the EX domain, a coefficient's product with the constant can symbolically collapse to literal 0 even though neither factor prints as zero, leaving an unstripped [EX(0)] rep instead of []; this made Poly.clear_denoms() on a zero constant poly return a Poly with is_zero=False that crashed terms_gcd() with IndexError. Fix: wrap both functions' return values in dup_strip(...)/dmp_strip(..., u) (already imported). Verified: repro passes (rep is DMP([], EX, None), is_zero True, terms_gcd and primitive both work); full sympy/polys test suite (944 tests) passes with only pre-existing skips/xfails, no new failu
```

tools: {'ToolSearch': 3, 'Bash': 32, 'Read': 12, 'Edit': 5, 'Agent': 1, 'Grep': 2, 'Write': 2, 'StructuredOutput': 1}
specialists spawned: ['code-reviewer']
files edited: ['/harness/projects/-testbed/memory/MEMORY.md', '/harness/projects/-testbed/memory/sympy.md', '/testbed/sympy/polys/densearith.py']
tests run (6):
  - python -m pytest sympy/polys/tests/test_densearith.py -q 2>&1 | tail -25
  - python -m pytest sympy/polys/tests/test_densearith.py -q 2>&1 | tail -20
  - python bin/test sympy/polys/tests/test_densearith.py 2>&1 | tail -30
  - python bin/test sympy/polys/tests/test_densetools.py 2>&1 | tail -20
  - python bin/test sympy/polys/tests/test_polytools.py 2>&1 | tail -20
  - python bin/test sympy/polys/tests/test_euclidtools.py sympy/polys/tests/test_factortools.py sympy/polys/tests/test_sqfreetools.py sympy/polys/tests/test_orthopo
bash commands (32, first 32):
  - echo "$CLAUDE_CONFIG_DIR"
  - git status --short && echo "---" && ls && echo "---" && find . -maxdepth 2 -iname "*.cfg" -o -iname "setup.py" -maxdepth 2 2>/dev/null
  - grep -n "def clear_denoms" sympy/polys/polytools.py
  - grep -n "def clear_denoms\|def _clear_denoms\|clear_denoms" sympy/polys/polyclasses.py sympy/polys/rings.py 2>/dev/null
  - grep -n "def dmp_clear_denoms\|def dup_clear_denoms" sympy/polys/densetools.py
  - grep -n "def dup_mul_ground\|def dmp_mul_ground" sympy/polys/densearith.py
  - mkdir -p /task/repro && cat > /task/repro/repro.py << 'PYEOF' from sympy import * x = symbols("x") f = Poly(sympify("-117968192370600*18**(1/3)/(217603955769048
  - python3 << 'PYEOF' from sympy import * x = symbols("x") f = Poly(sympify("-117968192370600*18**(1/3)/(217603955769048*(24201 + 253*sqrt(9165))**(1/3) + 22730058
  - grep -n "def dup_strip\|def dmp_strip" sympy/polys/densebasic.py | head grep -n "dup_strip\|dmp_strip" sympy/polys/densearith.py | head -30
  - grep -n "if not c or not f" sympy/polys/densearith.py
  - git diff
  - python /task/repro/repro.py
  - python3 -c " from sympy import * x = symbols('x') f = Poly(sympify('-117968192370600*18**(1/3)/(217603955769048*(24201 + 253*sqrt(9165))**(1/3) + 2273005839412*
  - find /testbed/sympy/polys/tests -iname "*densearith*" -o -iname "*dense*"
  - python -m pytest sympy/polys/tests/test_densearith.py -q 2>&1 | tail -25
  - python -c " import sympy sympy.test('sympy/polys/tests/test_densearith.py', verbose=False) " 2>&1 | tail -30
  - python -c " import sympy sympy.test('sympy/polys/tests/test_densetools.py', 'sympy/polys/tests/test_densebasic.py', 'sympy/polys/tests/test_polytools.py', 'symp
  - timeout 300 python -c " import sympy sympy.test('sympy/polys/', verbose=False) " 2>&1 | tail -60
  - grep -n "test_apart_extension_xfail" -A 15 sympy/polys/tests/test_partfrac.py | head -20
  - git -C /testbed diff --stat; echo "---"; git -C /testbed diff | grep -nE '^\+.*(print\(|breakpoint\(|pdb)' || echo "no debug leftovers"
  - git -C /testbed diff --stat; echo "-----"; git -C /testbed diff
  - grep -n "^from\|^import" /testbed/sympy/polys/densearith.py | head -20 echo "-----" sed -n '1,30p' /testbed/sympy/polys/densearith.py echo "-----dup_mul_ground 
  - grep -n "^def dmp_strip\|^def dup_strip" -A 25 /testbed/sympy/polys/densebasic.py | head -60
  - ls /task/repro/ 2>/dev/null; echo "---"; cat /task/repro/*.py 2>/dev/null | head -60
  - python -m pytest sympy/polys/tests/test_densearith.py -q 2>&1 | tail -20
  - python /task/repro/repro.py
  - python -m sympy.utilities.runtests sympy/polys/tests/test_densearith.py 2>&1 | tail -30 || python -c " import sympy.polys.tests.test_densearith as t import insp
  - python bin/test sympy/polys/tests/test_densearith.py 2>&1 | tail -30
  - python bin/test sympy/polys/tests/test_densetools.py 2>&1 | tail -20
  - python bin/test sympy/polys/tests/test_polytools.py 2>&1 | tail -20
  - python bin/test sympy/polys/tests/test_euclidtools.py sympy/polys/tests/test_factortools.py sympy/polys/tests/test_sqfreetools.py sympy/polys/tests/test_orthopo
  - git -C /testbed diff --name-only
last agent messages:
  > The code-reviewer approved. All done conditions are satisfied: repro passes, nearest tests run and shown, diff non-empty and minimal.
  > ```json
{
  "files_changed": ["sympy/polys/densearith.py"],
  "tests_run": [
    "python /task/repro/repro.py",
    "python -c \"import sympy; sympy.test('sympy/polys/tests/test_densearith.py', verbose=False)\"",
    "python -c \"import sympy; sympy.test('sympy/polys/tests/test_densetools.py', 'sympy/polys/tests/test_densebasic.py', 'sympy/polys/tests/test_polytools.py', 'sympy/polys/tests/test_po
  > Done. The fix is in `sympy/polys/densearith.py` — `dup_mul_ground`/`dmp_mul_ground` now strip leading-zero coefficients after multiplying, fixing the unstripped `DMP` bug behind `clear_denoms()`'s inconsistent zero polynomials. Reproduction passes and the full `sympy/polys` test suite (944 tests) is green.

grading: applied=True resolved=False F2P failed 1 passed 0; P2P failed 0 passed 154
still-failing hidden tests (F2P):
  - test_issue_20427
test output tail:
```
ok
test_primitive ok
test_compose ok
test_shift ok
test_transform ok
test_sturm ok
test_gff ok
test_norm ok
test_sqf_norm ok
test_sqf ok
test_factor ok
test_factor_large ok
test_factor_noeval ok
test_intervals ok
test_refine_root ok
test_count_roots ok
test_Poly_root ok
test_real_roots ok
test_all_roots ok
test_nroots ok
test_ground_roots ok
test_nth_power_roots_poly ok
test_torational_factor_list ok
test_cancel ok
test_reduced ok
test_groebner ok
test_fglm ok
test_is_zero_dimensional ok
test_GroebnerBasis ok
test_poly ok
test_keep_coeff ok
test_poly_matching_consistency ok
test_issue_5786 ok
test_noncommutative ok
test_to_rational_coeffs ok
test_factor_terms ok
test_as_list ok
test_issue_11198 ok
test_Poly_precision ok
test_issue_12400 ok
test_issue_14364 ok
test_issue_15669 ok
test_issue_17988 ok
test_issue_18205 ok
test_issue_8695 ok
test_issue_19113 ok
test_issue_19360 ok
test_poly_copy_equals_original ok
test_deserialized_poly_equals_original ok                                 [FAIL]


________________________________________________________________________________
_____________ sympy/polys/tests/test_polytools.py:test_issue_20427 _____________
Traceback (most recent call last):
  File "/testbed/sympy/polys/tests/test_polytools.py", line 1472, in test_issue_20427
    assert f == Poly(0, x, domain='EX')
AssertionError

============ tests finished: 155 passed, 1 failed, in 7.11 seconds =============
DO *NOT* COMMIT!
>>>>> Test Exit Code: 1
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '
```

model patch touches: sympy/polys/densearith.py
```diff
diff --git a/sympy/polys/densearith.py b/sympy/polys/densearith.py
index bce08bb..7f7a88b 100644
--- a/sympy/polys/densearith.py
+++ b/sympy/polys/densearith.py
@@ -269,7 +269,7 @@ def dup_mul_ground(f, c, K):
     if not c or not f:
         return []
     else:
-        return [ cf * c for cf in f ]
+        return dup_strip([ cf * c for cf in f ])
 
 
 def dmp_mul_ground(f, c, u, K):
@@ -291,7 +291,7 @@ def dmp_mul_ground(f, c, u, K):
 
     v = u - 1
 
-    return [ dmp_mul_ground(cf, c, v, K) for cf in f ]
+    return dmp_strip([ dmp_mul_ground(cf, c, v, K) for cf in f ], u)
 
 
 def dup_quo_ground(f, c, K):

```

## Run r1: outcome=unresolved resolved=False turns=42 cost=$0.97 wall=196.9s

Agent summary:
```json
{
 "files_changed": [
  "sympy/polys/densetools.py"
 ],
 "tests_run": [
  "python /task/repro/repro_clear_denoms.py",
  "python -c \"import sympy; sympy.test('sympy/polys/tests/test_densetools.py')\"",
  "python -c \"import sympy; sympy.test('sympy/polys/tests/test_polytools.py')\"",
  "python -c \"import sympy; sympy.test('sympy/polys/tests/test_densearith.py', 'sympy/polys/tests/test_rings.py', 'sympy/polys/tests/test_polyclasses.py')\""
 ],
 "reproduction": {
  "script": "/task/repro/repro_clear_denoms.py",
  "passes": true
 },
 "confidence": 0.85,
 "blocked": false,
 "notes": "Root cause: in dup_clear_denoms/dmp_clear_denoms (sympy/polys/densetools.py), multiplying an EX-domain coefficient by the common denominator can cancel it to exactly zero (EX multiplication calls .cancel()), but the resulting coefficient list was never re-stripped, leaving an invalid unstripped DMP ([EX(0)] instead of []). Fix adds dup_strip/dmp_strip after the dup_mul_ground/dmp_mul_ground calls in both functions (2-line diff). Repro now shows bad_poly.rep == DMP([], EX, None), is_zero is True, and terms_gcd() no longer raises IndexError. 36 densetools tests, 155 polytools tests, and 130 densearith/rings/polyclasses tests all pass, including the existing dup_clear_denoms([EX(sin(x)/x), EX(0)], EX) case, confirming no regression for trailing (non-leading) zero coefficients."
}
```

tools: {'ToolSearch': 3, 'Bash': 15, 'Read': 9, 'Grep': 8, 'Write': 1, 'Edit': 3, 'StructuredOutput': 1}
specialists spawned: []
files edited: ['/task/repro/repro_clear_denoms.py', '/testbed/sympy/polys/densetools.py']
tests run (1):
  - timeout 300 python -m pytest sympy/polys/tests/test_densetools.py -q 2>&1 | tail -30
bash commands (15, first 15):
  - echo "$CLAUDE_CONFIG_DIR"
  - git status --short && echo "---" && ls && echo "---" && cat setup.py 2>/dev/null | head -20
  - python -c " from sympy import EX from sympy.polys.densetools import dup_clear_denoms from sympy.abc import x  # simulate: an EX-domain coeff list with a hidden 
  - timeout 60 python -c " from sympy import EX, sqrt, Symbol from sympy.polys.densetools import dup_clear_denoms  x = Symbol('x') a = sqrt(2) # coefficient that lo
  - timeout 90 python -c " from sympy import * x = symbols('x') f = Poly(sympify('-117968192370600*18**(1/3)/(217603955769048*(24201 + 253*sqrt(9165))**(1/3) + 2273
  - mkdir -p /task/repro
  - timeout 90 python /task/repro/repro_clear_denoms.py
  - timeout 90 python -c " from sympy import * x = symbols('x') expr = sympify('-117968192370600*18**(1/3)/(217603955769048*(24201 + 253*sqrt(9165))**(1/3) + 227300
  - timeout 90 python /task/repro/repro_clear_denoms.py
  - timeout 300 python -m pytest sympy/polys/tests/test_densetools.py -q 2>&1 | tail -30
  - timeout 300 python -c "import sympy; sympy.test('sympy/polys/tests/test_densetools.py')" 2>&1 | tail -30
  - timeout 300 python -c "import sympy; sympy.test('sympy/polys/tests/test_polytools.py')" 2>&1 | tail -30
  - timeout 300 python -c "import sympy; sympy.test('sympy/polys/tests/test_densearith.py', 'sympy/polys/tests/test_rings.py', 'sympy/polys/tests/test_polyclasses.p
  - git -C /testbed diff --stat && echo "---DIFF---" && git -C /testbed diff && echo "---DEBUG CHECK---" && git -C /testbed diff | grep -nE '^\+.*(print\(|breakpoin
  - git -C /testbed diff --name-only
last agent messages:
  > Diff is minimal (2 lines), touches only library code, no test files, no debug leftovers. All conditions of the done condition are demonstrated. Final summary:
  > ```json
{
  "files_changed": ["sympy/polys/densetools.py"],
  "tests_run": [
    "python /task/repro/repro_clear_denoms.py",
    "python -c \"import sympy; sympy.test('sympy/polys/tests/test_densetools.py')\"",
    "python -c \"import sympy; sympy.test('sympy/polys/tests/test_polytools.py')\"",
    "python -c \"import sympy; sympy.test('sympy/polys/tests/test_densearith.py', 'sympy/polys/tests/tes
  > Fix complete and verified. Summary:

- **Root cause**: `dup_clear_denoms`/`dmp_clear_denoms` in `sympy/polys/densetools.py` multiply EX-domain coefficients by a common denominator via `dup_mul_ground`/`dmp_mul_ground`. For EX (arbitrary-expression) domain, this multiplication can cancel a coefficient to exactly `0`, but the resulting coefficient list was never re-stripped of that new zero — leavin

grading: applied=True resolved=False F2P failed 1 passed 0; P2P failed 0 passed 154
still-failing hidden tests (F2P):
  - test_issue_20427
test output tail:
```
t_monic ok
test_content ok
test_primitive ok
test_compose ok
test_shift ok
test_transform ok
test_sturm ok
test_gff ok
test_norm ok
test_sqf_norm ok
test_sqf ok
test_factor ok
test_factor_large ok
test_factor_noeval ok
test_intervals ok
test_refine_root ok
test_count_roots ok
test_Poly_root ok
test_real_roots ok
test_all_roots ok
test_nroots ok
test_ground_roots ok
test_nth_power_roots_poly ok
test_torational_factor_list ok
test_cancel ok
test_reduced ok
test_groebner ok
test_fglm ok
test_is_zero_dimensional ok
test_GroebnerBasis ok
test_poly ok
test_keep_coeff ok
test_poly_matching_consistency ok
test_issue_5786 ok
test_noncommutative ok
test_to_rational_coeffs ok
test_factor_terms ok
test_as_list ok
test_issue_11198 ok
test_Poly_precision ok
test_issue_12400 ok
test_issue_14364 ok
test_issue_15669 ok
test_issue_17988 ok
test_issue_18205 ok
test_issue_8695 ok
test_issue_19113 ok
test_issue_19360 ok
test_poly_copy_equals_original ok
test_deserialized_poly_equals_original ok                                 [FAIL]


________________________________________________________________________________
_____________ sympy/polys/tests/test_polytools.py:test_issue_20427 _____________
Traceback (most recent call last):
  File "/testbed/sympy/polys/tests/test_polytools.py", line 1472, in test_issue_20427
    assert f == Poly(0, x, domain='EX')
AssertionError

============ tests finished: 155 passed, 1 failed, in 6.60 seconds =============
DO *NOT* COMMIT!
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '
```

model patch touches: sympy/polys/densetools.py
```diff
diff --git a/sympy/polys/densetools.py b/sympy/polys/densetools.py
index f057824..d298c3c 100644
--- a/sympy/polys/densetools.py
+++ b/sympy/polys/densetools.py
@@ -1197,6 +1197,7 @@ def dup_clear_denoms(f, K0, K1=None, convert=False):
 
     if not K1.is_one(common):
         f = dup_mul_ground(f, common, K0)
+        f = dup_strip(f)
 
     if not convert:
         return common, f
@@ -1251,6 +1252,7 @@ def dmp_clear_denoms(f, u, K0, K1=None, convert=False):
 
     if not K1.is_one(common):
         f = dmp_mul_ground(f, common, u, K0)
+        f = dmp_strip(f, u)
 
     if not convert:
         return common, f

```

## Run r2: outcome=unresolved resolved=False turns=41 cost=$0.89 wall=227.2s

Agent summary:
```json
{
 "files_changed": [
  "sympy/polys/densetools.py"
 ],
 "tests_run": [
  "python /task/repro/repro_clear_denoms.py",
  "python bin/test sympy/polys/tests/test_densetools.py sympy/polys/tests/test_polyclasses.py sympy/polys/tests/test_polytools.py",
  "python bin/doctest sympy/polys/densetools.py",
  "python bin/test sympy/polys/"
 ],
 "reproduction": {
  "script": "/task/repro/repro_clear_denoms.py",
  "passes": true
 },
 "confidence": 0.85,
 "blocked": false,
 "notes": "Root cause: dup_clear_denoms/dmp_clear_denoms multiply by `common` via dup_mul_ground/dmp_mul_ground without re-stripping; for EX-domain coefficients the multiplication's cancel()/expand() can turn a structurally-nonzero coefficient into a real 0, leaving an unstripped [EX(0)] in the DMP rep. Fix adds dup_strip/dmp_strip after the multiplication in sympy/polys/densetools.py. Full sympy/polys/ suite (944 tests) and densetools/polyclasses/polytools doctests all pass; one xpassed test (test_apart_extension_xfail) is pre-existing on the unmodified repo and unrelated to this change."
}
```

tools: {'ToolSearch': 3, 'Bash': 25, 'Read': 6, 'Write': 1, 'Edit': 3, 'StructuredOutput': 1}
specialists spawned: []
files edited: ['/task/repro/repro_clear_denoms.py', '/testbed/sympy/polys/densetools.py']
tests run (4):
  - timeout 300 python -m pytest sympy/polys/tests/test_densetools.py sympy/polys/tests/test_polyclasses.py sympy/polys/tests/test_polytools.py -q 2>&1 | tail -30
  - timeout 300 python bin/test sympy/polys/tests/test_densetools.py sympy/polys/tests/test_polyclasses.py sympy/polys/tests/test_polytools.py 2>&1 | tail -40
  - timeout 300 python bin/test sympy/polys/ 2>&1 | tail -40
  - git stash && timeout 60 python bin/test sympy/polys/tests/test_partfrac.py 2>&1 | tail -15 && git stash pop
bash commands (25, first 25):
  - echo "$CLAUDE_CONFIG_DIR"
  - git -C /testbed status --short; echo "---LS---"; ls /testbed; echo "---REPO---"; ls /task/repro 2>/dev/null || echo "no repro dir"
  - mkdir -p /task/repro
  - grep -rn "def clear_denoms" /testbed/sympy/polys/
  - grep -rn "def dmp_clear_denoms\|def dup_clear_denoms" /testbed/sympy/polys/densetools.py
  - timeout 60 python -c " from sympy import * x = symbols('x') f = Poly(sympify('-117968192370600*18**(1/3)/(217603955769048*(24201 + 253*sqrt(9165))**(1/3) + 2273
  - timeout 60 python -c " from sympy import * x = symbols('x') f = Poly(sympify('-117968192370600*18**(1/3)/(217603955769048*(24201 + 253*sqrt(9165))**(1/3) + 2273
  - grep -n "def dup_strip\|def dmp_strip" -A 20 /testbed/sympy/polys/densebasic.py
  - grep -n "def is_zero\|class EX\b" -A 15 /testbed/sympy/polys/domains/expressiondomain.py 2>/dev/null || find /testbed/sympy/polys -iname "*expression*"
  - grep -n "def dup_mul_ground\|def dmp_mul_ground" -A 20 /testbed/sympy/polys/densearith.py
  - grep -n "def per" -A 20 /testbed/sympy/polys/polyclasses.py
  - timeout 60 python -c " from sympy import * from sympy.polys.densetools import dmp_clear_denoms x = symbols('x') f = Poly(sympify('-117968192370600*18**(1/3)/(21
  - grep -n "class DMP" -A 40 /testbed/sympy/polys/polyclasses.py | head -60
  - grep -n "^from sympy.polys.densebasic\|^from \.densebasic\|import.*densebasic" /testbed/sympy/polys/densetools.py | head -20
  - timeout 60 python /task/repro/repro_clear_denoms.py; echo "EXIT: $?"
  - timeout 60 python /task/repro/repro_clear_denoms.py; echo "EXIT: $?"
  - ls /testbed/sympy/polys/tests/ | grep -i "densetools\|polyclasses\|polytools"
  - timeout 300 python -m pytest sympy/polys/tests/test_densetools.py sympy/polys/tests/test_polyclasses.py sympy/polys/tests/test_polytools.py -q 2>&1 | tail -30
  - timeout 300 python -m sympy.testing.runtests --help 2>&1 | head -5; echo "---"; ls bin/ | grep -i test
  - timeout 300 python bin/test sympy/polys/tests/test_densetools.py sympy/polys/tests/test_polyclasses.py sympy/polys/tests/test_polytools.py 2>&1 | tail -40
  - git -C /testbed diff --stat; echo "---FULL DIFF---"; git -C /testbed diff; echo "---DEBUG CHECK---"; git -C /testbed diff | grep -nE '^\+.*(print\(|breakpoint\(
  - timeout 60 python -m sympy.polys.densetools 2>&1 | tail -5; echo "---doctest run---"; timeout 60 python bin/doctest sympy/polys/densetools.py 2>&1 | tail -20
  - timeout 300 python bin/test sympy/polys/ 2>&1 | tail -40
  - git stash && timeout 60 python bin/test sympy/polys/tests/test_partfrac.py 2>&1 | tail -15 && git stash pop
  - git -C /testbed diff --stat; git -C /testbed status --short
last agent messages:
  > Confirmed: the xpassed test is pre-existing on the unmodified repo (unrelated to my change). Stash pop restored my fix correctly. Let's do a final diff/status confirmation.
  > **Root cause:** `dup_clear_denoms`/`dmp_clear_denoms` in `sympy/polys/densetools.py` multiply coefficients by `common` via `dup_mul_ground`/`dmp_mul_ground` but never re-strip the result. For most domains this is safe (multiplying a nonzero leading coefficient by nonzero `common` stays nonzero), but for the `EX` domain, `Expression.__mul__` calls `.cancel().expand()`, which can genuinely simplify 
  > Structured output submitted. Summary: fixed the unstripped-zero bug in `clear_denoms()` by adding `dup_strip`/`dmp_strip` calls in `sympy/polys/densetools.py` after `dup_mul_ground`/`dmp_mul_ground`, verified via a reproduction script and the full `sympy/polys/` test suite (944 passed).

grading: applied=True resolved=False F2P failed 1 passed 0; P2P failed 0 passed 154
still-failing hidden tests (F2P):
  - test_issue_20427
test output tail:
```
ok
test_primitive ok
test_compose ok
test_shift ok
test_transform ok
test_sturm ok
test_gff ok
test_norm ok
test_sqf_norm ok
test_sqf ok
test_factor ok
test_factor_large ok
test_factor_noeval ok
test_intervals ok
test_refine_root ok
test_count_roots ok
test_Poly_root ok
test_real_roots ok
test_all_roots ok
test_nroots ok
test_ground_roots ok
test_nth_power_roots_poly ok
test_torational_factor_list ok
test_cancel ok
test_reduced ok
test_groebner ok
test_fglm ok
test_is_zero_dimensional ok
test_GroebnerBasis ok
test_poly ok
test_keep_coeff ok
test_poly_matching_consistency ok
test_issue_5786 ok
test_noncommutative ok
test_to_rational_coeffs ok
test_factor_terms ok
test_as_list ok
test_issue_11198 ok
test_Poly_precision ok
test_issue_12400 ok
test_issue_14364 ok
test_issue_15669 ok
test_issue_17988 ok
test_issue_18205 ok
test_issue_8695 ok
test_issue_19113 ok
test_issue_19360 ok
test_poly_copy_equals_original ok
test_deserialized_poly_equals_original ok                                 [FAIL]


________________________________________________________________________________
_____________ sympy/polys/tests/test_polytools.py:test_issue_20427 _____________
Traceback (most recent call last):
  File "/testbed/sympy/polys/tests/test_polytools.py", line 1472, in test_issue_20427
    assert f == Poly(0, x, domain='EX')
AssertionError

============ tests finished: 155 passed, 1 failed, in 6.35 seconds =============
DO *NOT* COMMIT!
>>>>> Test Exit Code: 1
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '
```

model patch touches: sympy/polys/densetools.py
```diff
diff --git a/sympy/polys/densetools.py b/sympy/polys/densetools.py
index f057824..d298c3c 100644
--- a/sympy/polys/densetools.py
+++ b/sympy/polys/densetools.py
@@ -1197,6 +1197,7 @@ def dup_clear_denoms(f, K0, K1=None, convert=False):
 
     if not K1.is_one(common):
         f = dup_mul_ground(f, common, K0)
+        f = dup_strip(f)
 
     if not convert:
         return common, f
@@ -1251,6 +1252,7 @@ def dmp_clear_denoms(f, u, K0, K1=None, convert=False):
 
     if not K1.is_one(common):
         f = dmp_mul_ground(f, common, u, K0)
+        f = dmp_strip(f, u)
 
     if not convert:
         return common, f

```
