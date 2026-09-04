# sympy__sympy-20428 under C0: solid_fail (0/3 passes)

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

## Run r0: outcome=unresolved resolved=False turns=35 cost=$0.70 wall=163.6s

Agent summary:
```json
{
 "files_changed": [
  "sympy/polys/densetools.py"
 ],
 "tests_run": [
  "python3 /task/repro/repro.py",
  "python3 bin/test sympy/polys/tests/test_densetools.py",
  "python3 bin/test sympy/polys/tests/test_polyclasses.py sympy/polys/tests/test_polytools.py"
 ],
 "reproduction": {
  "script": "/task/repro/repro.py",
  "passes": true
 },
 "confidence": 0.75,
 "blocked": false,
 "notes": "Root cause: dup_clear_denoms/dmp_clear_denoms multiply the poly by the cleared-denominator factor via dup_mul_ground/dmp_mul_ground but never re-strip the result; for the EX domain this multiplication can algebraically cancel a leading coefficient to exact zero, leaving an unstripped DMP([EX(0)], ...) whose is_zero is False while as_expr()==0. Fix adds dup_strip/dmp_strip after the multiplication in both functions. All existing densetools/polyclasses/polytools tests still pass."
}
```

tools: {'ToolSearch': 2, 'Read': 8, 'Grep': 8, 'Bash': 11, 'Write': 1, 'Edit': 2, 'StructuredOutput': 1}
specialists spawned: []
files edited: ['/task/repro/repro.py', '/testbed/sympy/polys/densetools.py']
tests run (3):
  - python3 -m pytest sympy/polys/tests/test_densetools.py -q 2>&1 | tail -30
  - python3 bin/test sympy/polys/tests/test_densetools.py 2>&1 | tail -30
  - python3 bin/test sympy/polys/tests/test_polyclasses.py sympy/polys/tests/test_polytools.py 2>&1 | tail -30
bash commands (11, first 11):
  - mkdir -p /task/repro && python3 -c " import sympy print(sympy.__version__) "
  - python3 -c " from sympy import * x = symbols('x') f = Poly(sympify(\"-117968192370600*18**(1/3)/(217603955769048*(24201 + 253*sqrt(9165))**(1/3) + 2273005839412
  - python3 -c " from sympy.polys.domains import EX from sympy import sympify e = EX(sympify(0)) print(bool(e), not e) print(e) "
  - python3 /task/repro/repro.py
  - python3 /task/repro/repro.py
  - python3 -m pytest sympy/polys/tests/test_densetools.py -q 2>&1 | tail -30
  - python3 -m sympy.testing.runtests sympy/polys/tests/test_densetools.py 2>&1 | tail -30
  - python3 bin/test sympy/polys/tests/test_densetools.py 2>&1 | tail -30
  - python3 bin/test sympy/polys/tests/test_polyclasses.py sympy/polys/tests/test_polytools.py 2>&1 | tail -30
  - git -C /testbed diff
  - git -C /testbed diff --name-only
last agent messages:
  > Diff is non-empty and localized as expected.
  > ```json
{
  "files_changed": ["sympy/polys/densetools.py"],
  "tests_run": [
    "python3 /task/repro/repro.py",
    "python3 bin/test sympy/polys/tests/test_densetools.py",
    "python3 bin/test sympy/polys/tests/test_polyclasses.py sympy/polys/tests/test_polytools.py"
  ],
  "reproduction": { "script": "/task/repro/repro.py", "passes": true },
  "confidence": 0.75,
  "blocked": false,
  "notes":
  > Done. Summary of the fix:

**Root cause:** `dup_clear_denoms`/`dmp_clear_denoms` in `sympy/polys/densetools.py` multiply a poly's coefficients by the LCM of denominators via `dup_mul_ground`/`dmp_mul_ground`, but never re-strip the result. For the `EX` domain, this multiplication can cause an exact algebraic cancellation of the leading coefficient to zero, leaving an unstripped `DMP([EX(0)], ...)`

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

============ tests finished: 155 passed, 1 failed, in 7.14 seconds =============
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

## Run r1: outcome=unresolved resolved=False turns=32 cost=$0.67 wall=148.4s

Agent summary:
```json
{
 "files_changed": [
  "sympy/polys/densetools.py"
 ],
 "tests_run": [
  "python /task/repro/repro.py",
  "python -c \"import sympy; sympy.test('sympy/polys/tests/test_densetools.py', 'sympy/polys/tests/test_polytools.py', 'sympy/polys/tests/test_rings.py')\""
 ],
 "reproduction": {
  "script": "/task/repro/repro.py",
  "passes": true
 },
 "confidence": 0.85,
 "blocked": false,
 "notes": "Root cause: in EX (ExpressionDomain), multiplying a nonzero-by-bool() coefficient by the common denominator in dup_mul_ground/dmp_mul_ground can symbolically cancel to exact EX(0), but dup_clear_denoms/dmp_clear_denoms never re-stripped the result afterward, leaving an unstripped leading-zero DMP; added dup_strip/dmp_strip calls after the multiply in both functions. All 253 tests in the nearest test files (test_densetools.py, test_polytools.py, test_rings.py) pass."
}
```

tools: {'ToolSearch': 2, 'Read': 5, 'Grep': 8, 'Bash': 10, 'Write': 1, 'Edit': 2, 'StructuredOutput': 2}
specialists spawned: []
files edited: ['/task/repro/repro.py', '/testbed/sympy/polys/densetools.py']
tests run (1):
  - python -m pytest sympy/polys/tests/test_densetools.py sympy/polys/tests/test_polytools.py sympy/polys/tests/test_rings.py -q 2>&1 | tail -40
bash commands (10, first 10):
  - mkdir -p /task/repro
  - python /task/repro/repro.py
  - python -c " from sympy import * x = symbols('x') f = Poly(sympify(\"-117968192370600*18**(1/3)/(217603955769048*(24201 + 253*sqrt(9165))**(1/3) + 2273005839412*
  - grep -n "class EX" -A 60 /testbed/sympy/polys/domains/expressiondomain.py | head -100
  - python /task/repro/repro.py
  - python -m pytest sympy/polys/tests/test_densetools.py sympy/polys/tests/test_polytools.py sympy/polys/tests/test_rings.py -q 2>&1 | tail -40
  - python -m sympy.testing.runtests --help 2>&1 | head -5; ls bin/ 2>/dev/null | head
  - python -c " import sympy sympy.test('sympy/polys/tests/test_densetools.py', 'sympy/polys/tests/test_polytools.py', 'sympy/polys/tests/test_rings.py') " 2>&1 | t
  - git -C /testbed diff
  - git -C /testbed diff --name-only
last agent messages:
  > Diff is clean and non-empty, all done.
  > ```json
{
  "files_changed": ["sympy/polys/densetools.py"],
  "tests_run": [
    "python /task/repro/repro.py",
    "python -c \"import sympy; sympy.test('sympy/polys/tests/test_densetools.py', 'sympy/polys/tests/test_polytools.py', 'sympy/polys/tests/test_rings.py')\""
  ],
  "reproduction": { "script": "/task/repro/repro.py", "passes": true },
  "confidence": 0.85,
  "blocked": false,
  "notes":
  > Structured output submitted successfully.

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

============ tests finished: 155 passed, 1 failed, in 6.50 seconds =============
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

## Run r2: outcome=unresolved resolved=False turns=36 cost=$0.77 wall=178.2s

Agent summary:
```json
{
 "files_changed": [
  "sympy/polys/densetools.py"
 ],
 "tests_run": [
  "python /task/repro/repro.py",
  "python bin/test sympy/polys/tests/test_densetools.py sympy/polys/tests/test_polyclasses.py sympy/polys/tests/test_polytools.py",
  "python bin/test sympy/polys/tests/test_densearith.py sympy/polys/tests/test_rings.py sympy/polys/tests/test_densebasic.py"
 ],
 "reproduction": {
  "script": "/task/repro/repro.py",
  "passes": true
 },
 "confidence": 0.85,
 "blocked": false,
 "notes": "Root cause: in the EX (ExpressionDomain) domain, multiplying a nonzero coefficient by the computed common denominator (dup_mul_ground/dmp_mul_ground) can simplify to a value that is recognized as zero (bool()==False) even though the resulting list wasn't re-stripped of leading zero coefficients; dup_clear_denoms/dmp_clear_denoms returned this unstripped DMP list (e.g. [EX(0)] instead of []), causing Poly.is_zero to be False while as_expr() gave 0, and downstream functions like terms_gcd/primitive to crash or misbehave. Fixed by stripping the result (dup_strip/dmp_strip) after multiplying by the common denominator in both dup_clear_denoms and dmp_clear_denoms in sympy/polys/densetools.py."
}
```

tools: {'ToolSearch': 2, 'Read': 9, 'Grep': 9, 'Bash': 10, 'Edit': 2, 'StructuredOutput': 2}
specialists spawned: []
files edited: ['/testbed/sympy/polys/densetools.py']
tests run (4):
  - timeout 600 python -m pytest sympy/polys/tests/test_densetools.py sympy/polys/tests/test_polyclasses.py sympy/polys/tests/test_polytools.py -q 2>&1 | tail -40
  - timeout 600 python -m sympy.testing.runtests sympy/polys/tests/test_densetools.py 2>&1 | tail -30 || timeout 600 bin/test sympy/polys/tests/test_densetools.py 2
  - timeout 600 python bin/test sympy/polys/tests/test_densetools.py sympy/polys/tests/test_polyclasses.py sympy/polys/tests/test_polytools.py 2>&1 | tail -40
  - timeout 600 python bin/test sympy/polys/tests/test_densearith.py sympy/polys/tests/test_rings.py sympy/polys/tests/test_densebasic.py 2>&1 | tail -20 echo "---D
bash commands (10, first 10):
  - mkdir -p /task/repro && cat > /task/repro/repro.py << 'EOF' from sympy import symbols, sympify, Poly  x = symbols("x") f = Poly(sympify("-117968192370600*18**(1
  - python -c " from sympy import symbols, sympify, Poly from sympy.polys.domains import EX  x = symbols('x') f = Poly(sympify(\"-117968192370600*18**(1/3)/(2176039
  - python -c " from sympy import symbols, sympify, Poly  x = symbols('x') f = Poly(sympify(\"-117968192370600*18**(1/3)/(217603955769048*(24201 + 253*sqrt(9165))**
  - python -c " from sympy.polys.densebasic import dup_strip from sympy.polys.domains import EX from sympy import sin from sympy.abc import x print(dup_strip([EX(si
  - timeout 120 python /task/repro/repro.py
  - timeout 600 python -m pytest sympy/polys/tests/test_densetools.py sympy/polys/tests/test_polyclasses.py sympy/polys/tests/test_polytools.py -q 2>&1 | tail -40
  - timeout 600 python -m sympy.testing.runtests sympy/polys/tests/test_densetools.py 2>&1 | tail -30 || timeout 600 bin/test sympy/polys/tests/test_densetools.py 2
  - timeout 600 python bin/test sympy/polys/tests/test_densetools.py sympy/polys/tests/test_polyclasses.py sympy/polys/tests/test_polytools.py 2>&1 | tail -40
  - timeout 600 python bin/test sympy/polys/tests/test_densearith.py sympy/polys/tests/test_rings.py sympy/polys/tests/test_densebasic.py 2>&1 | tail -20 echo "---D
  - git -C /testbed diff --name-only
last agent messages:
  > All tests pass and the diff is clean and minimal.
  > ```json
{
  "files_changed": ["sympy/polys/densetools.py"],
  "tests_run": [
    "python /task/repro/repro.py",
    "python bin/test sympy/polys/tests/test_densetools.py sympy/polys/tests/test_polyclasses.py sympy/polys/tests/test_polytools.py",
    "python bin/test sympy/polys/tests/test_densearith.py sympy/polys/tests/test_rings.py sympy/polys/tests/test_densebasic.py"
  ],
  "reproduction": { "
  > Structured output submitted successfully.

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

============ tests finished: 155 passed, 1 failed, in 6.62 seconds =============
DO *NOT* COMMIT!
>>>>> Test Exit Code: 1
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '
```

model patch touches: sympy/polys/densetools.py
```diff
diff --git a/sympy/polys/densetools.py b/sympy/polys/densetools.py
index f057824..931dfe8 100644
--- a/sympy/polys/densetools.py
+++ b/sympy/polys/densetools.py
@@ -1198,6 +1198,8 @@ def dup_clear_denoms(f, K0, K1=None, convert=False):
     if not K1.is_one(common):
         f = dup_mul_ground(f, common, K0)
 
+    f = dup_strip(f)
+
     if not convert:
         return common, f
     else:
@@ -1252,6 +1254,8 @@ def dmp_clear_denoms(f, u, K0, K1=None, convert=False):
     if not K1.is_one(common):
         f = dmp_mul_ground(f, common, u, K0)
 
+    f = dmp_strip(f, u)
+
     if not convert:
         return common, f
     else:

```
