# django__django-16667 under C1: solid_fail (0/3 passes)

repo: django/django  version: 5.0  difficulty: 15 min - 1 hour

## Problem statement

SelectDateWidget can crash with OverflowError.
Description
	
Given a relatively common view like this:
from django import forms
from django.forms import SelectDateWidget
from django.http import HttpResponse
class ReproForm(forms.Form):
	 my_date = forms.DateField(widget=SelectDateWidget())
def repro_view(request):
	 form = ReproForm(request.GET) # for ease of reproducibility
	 if form.is_valid():
		 return HttpResponse("ok")
	 else:
		 return HttpResponse("not ok")
# urls.py
urlpatterns = [path('repro/', views.repro_view, name='repro')]
A user can trigger a server crash, reproducible by running locally and visiting ​http://127.0.0.1:8000/repro/?my_date_day=1&my_date_month=1&my_date_year=1234567821345678, which results in
[...] - ERROR - django.request: Internal Server Error: /repro/
Traceback (most recent call last):
[...]
 File "[...]/site-packages/django/forms/widgets.py", line 1160, in value_from_datadict
	date_value = datetime.date(int(y), int(m), int(d))
OverflowError: signed integer is greater than maximum
This can be triggered similarly for a post request.
The issue happens as part of the validation logic run in form.is_valid, specifically, when calling the SelectDateWidget.value_from_datadict, where the user-controlled value is converted into a date without guarding against a possible OverflowError.
Specifically, y, m and d are user controlled, and the code does this:
 date_value = datetime.date(int(y), int(m), int(d)) 
When large integers (larger than sys.maxsize) are supplied to date's constructor it will throw an OverflowError:
>>> import datetime, sys
>>> datetime.date(sys.maxsize+1, 3, 4)
Traceback (most recent call last):
 File "<stdin>", line 1, in <module>
OverflowError: Python int too large to convert to C long

## Gold patch touches (files only): django/forms/widgets.py

## Run r0: outcome=unresolved resolved=False turns=20 cost=$0.70 wall=177.3s

Agent summary:
```json
{
 "files_changed": [
  "django/forms/widgets.py"
 ],
 "tests_run": [
  "python /task/repro/repro_overflow.py",
  "cd /testbed/tests && python runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2"
 ],
 "reproduction": {
  "script": "/task/repro/repro_overflow.py",
  "passes": true
 },
 "confidence": 0.92,
 "blocked": false,
 "notes": "Root cause: SelectDateWidget.value_from_datadict (django/forms/widgets.py:1159) constructs datetime.date(int(y), int(m), int(d)) inside a try/except ValueError block, but a year larger than sys.maxsize raises OverflowError instead of ValueError, so it went uncaught and crashed form.is_valid() with a 500. Fix widens the except clause to (ValueError, OverflowError) so it falls through to the existing pseudo-ISO fallback, matching prior ValueError handling. Repro passes, all 15 nearest tests pass (reviewer also ran the full forms_tests suite, 931 tests, and reported all passing), diff is a single-line change with no test-file edits or debug output."
}
```

tools: {'ToolSearch': 2, 'Bash': 27, 'Read': 8, 'Grep': 2, 'Glob': 1, 'Agent': 3, 'Write': 2, 'Edit': 1, 'StructuredOutput': 1}
specialists spawned: ['tester', 'backend-dev', 'code-reviewer']
files edited: ['/task/repro/repro_overflow.py', '/testbed/django/forms/widgets.py']
tests run (7):
  - ls /testbed/tests/runtests.py 2>&1; python3 -c "import sys; print(sys.maxsize)"
  - cd /testbed/tests && python runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -40
  - cd /testbed/tests && python runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -40
  - python -m pytest tests/forms_tests/widget_tests/test_selectdatewidget.py -q 2>&1 | tail -30
  - python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 1 2>&1 | tail -30
  - python tests/runtests.py forms_tests -v 1 2>&1 | tail -15
  - cd /testbed/tests && python runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -20
bash commands (27, first 27):
  - echo "$CLAUDE_CONFIG_DIR"
  - mkdir -p /task/repro && git -C /testbed status --short
  - ls /testbed/tests/runtests.py 2>&1; python3 -c "import sys; print(sys.maxsize)"
  - ls /testbed/tests/forms_tests/widget_tests/base.py 2>&1 | head -5
  - python /task/repro/repro_overflow.py; echo "EXIT CODE: $?"
  - python /task/repro/repro_overflow.py; echo "EXIT CODE: $?"
  - python /task/repro/repro_overflow.py 2>&1 | tail -30
  - cd /testbed/tests && python runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -40
  - python -c " import django from django.conf import settings if not settings.configured:     settings.configure(USE_I18N=False, USE_TZ=False) django.setup() from 
  - git -C /testbed diff --stat; git -C /testbed status --porcelain
  - python /task/repro/repro_overflow.py; echo "EXIT:$?"
  - python /task/repro/repro_overflow.py; echo "EXIT:$?"
  - cd /testbed/tests && python runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -40
  - git -C /testbed diff --stat && echo "---" && git -C /testbed diff
  - git -C /testbed diff; echo "---STAT---"; git -C /testbed diff --stat
  - ls /task/repro/ 2>/dev/null; echo "---"; find /task/repro -type f 2>/dev/null | xargs -I{} echo {}
  - python /task/repro/repro_overflow.py; echo "EXIT:$?"
  - git -C /testbed status --porcelain; echo "---files changed---"; git -C /testbed diff --name-only
  - python -m pytest tests/forms_tests/widget_tests/test_selectdatewidget.py -q 2>&1 | tail -30
  - python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 1 2>&1 | tail -30
  - python tests/runtests.py forms_tests -v 1 2>&1 | tail -15
  - python /task/repro/repro_overflow.py; echo "EXIT: $?"
  - git -C /testbed diff --stat
  - git -C /testbed diff | grep -nE '^\+.*(print\(|breakpoint\(|pdb|console\.log)' || echo "no debug leftovers"
  - git -C /testbed diff
  - cd /testbed/tests && python runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -20
  - git -C /testbed diff --name-only
last agent messages:
  > All verified in my own shell: repro passes, diff is a single-line non-test change, no debug leftovers, nearest tests (15/15) pass.
  > ```json
{
  "files_changed": ["django/forms/widgets.py"],
  "tests_run": [
    "python /task/repro/repro_overflow.py",
    "cd /testbed/tests && python runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2"
  ],
  "reproduction": { "script": "/task/repro/repro_overflow.py", "passes": true },
  "confidence": 0.92,
  "blocked": false,
  "notes": "Root cause: SelectDateWidget.value_from_dat
  > Fix complete and verified. Summary:

- **Root cause**: `SelectDateWidget.value_from_datadict` in `django/forms/widgets.py:1159` only caught `ValueError` around `datetime.date(int(y), int(m), int(d))`, but a year exceeding `sys.maxsize` raises `OverflowError`, which propagated uncaught and crashed `form.is_valid()`.
- **Fix**: widened `except ValueError:` to `except (ValueError, OverflowError):` — 

grading: applied=True resolved=False F2P failed 1 passed 1; P2P failed 0 passed 24
still-failing hidden tests (F2P):
  - test_value_from_datadict (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_value_from_datadict)
test output tail:
```
idget.SelectDateWidgetTest.test_selectdate_empty_label) ... ok
test_selectdate_required (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_selectdate_required) ... ok
test_value_from_datadict (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_value_from_datadict) ... 
  test_value_from_datadict (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_value_from_datadict) (values=('9223372036854775808', '12', '1')) ... FAIL
test_value_omitted_from_data (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_value_omitted_from_data) ... ok
test_years_rendered_without_separator (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_years_rendered_without_separator) ... ok

======================================================================
FAIL: test_value_from_datadict (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_value_from_datadict) (values=('9223372036854775808', '12', '1'))
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/testbed/tests/forms_tests/widget_tests/test_selectdatewidget.py", line 622, in test_value_from_datadict
    self.assertEqual(
AssertionError: '9223372036854775808-12-1' != '0-0-0'
- 9223372036854775808-12-1
+ 0-0-0


----------------------------------------------------------------------
Ran 26 tests in 0.082s

FAILED (failures=1)
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '
```

model patch touches: django/forms/widgets.py
```diff
diff --git a/django/forms/widgets.py b/django/forms/widgets.py
index 842b73e..f4bc74b 100644
--- a/django/forms/widgets.py
+++ b/django/forms/widgets.py
@@ -1157,7 +1157,7 @@ class SelectDateWidget(Widget):
             input_format = formats.sanitize_strftime_format(input_format)
             try:
                 date_value = datetime.date(int(y), int(m), int(d))
-            except ValueError:
+            except (ValueError, OverflowError):
                 # Return pseudo-ISO dates with zeros for any unselected values,
                 # e.g. '2017-0-23'.
                 return "%s-%s-%s" % (y or 0, m or 0, d or 0)

```

## Run r1: outcome=unresolved resolved=False turns=26 cost=$0.44 wall=86.1s

Agent summary:
```json
{
 "files_changed": [
  "django/forms/widgets.py"
 ],
 "tests_run": [
  "python /task/repro/repro_overflow.py",
  "python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2",
  "python tests/runtests.py forms_tests.field_tests.test_datefield -v 1"
 ],
 "reproduction": {
  "script": "/task/repro/repro_overflow.py",
  "passes": true
 },
 "confidence": 0.9,
 "blocked": false,
 "notes": "Root cause: datetime.date() raises OverflowError (not ValueError) for years outside the C long range, and SelectDateWidget.value_from_datadict (django/forms/widgets.py:1159-1160) only caught ValueError, letting user-controlled GET/POST data crash the request with an unhandled 500. Fix widens the except clause to (ValueError, OverflowError) so oversized values fall through to the existing pseudo-ISO fallback path. All 15 SelectDateWidget tests and 11 DateField tests pass; diff is a single line in library code, no test files touched."
}
```

tools: {'ToolSearch': 3, 'Bash': 13, 'Read': 3, 'Grep': 1, 'Write': 1, 'Edit': 2, 'StructuredOutput': 1}
specialists spawned: []
files edited: ['/task/repro/repro_overflow.py', '/testbed/django/forms/widgets.py']
tests run (3):
  - python -m pytest tests/forms_tests/widget_tests/test_selectdatewidget.py -v 2>&1 | tail -60
  - python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -60
  - python tests/runtests.py forms_tests.field_tests.test_datefield -v 1 2>&1 | tail -20
bash commands (13, first 13):
  - echo "$CLAUDE_CONFIG_DIR"
  - git -C /testbed status --short; echo "---"; git -C /testbed log -1 --oneline
  - mkdir -p /task/repro
  - cat setup.cfg 2>/dev/null | head -30; echo "---"; ls tests/forms_tests/field_tests/ | grep -i date
  - find /testbed/tests/forms_tests -iname "*selectdate*"
  - python /task/repro/repro_overflow.py; echo "EXIT: $?"
  - python /task/repro/repro_overflow.py; echo "EXIT: $?"
  - python -m pytest tests/forms_tests/widget_tests/test_selectdatewidget.py -v 2>&1 | tail -60
  - python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -60
  - python tests/runtests.py forms_tests.field_tests.test_datefield -v 1 2>&1 | tail -20
  - git -C /testbed diff --stat; echo "---"; git -C /testbed diff
  - git -C /testbed diff | grep -nE '^\+.*(print\(|breakpoint\(|pdb|console\.log)' || echo "no debug leftovers"
  - true
last agent messages:
  > Diff is minimal (1 file, 1 line changed), scoped to library code only, no test files touched, no debug leftovers.

**Summary:**
- **Root cause:** `SelectDateWidget.value_from_datadict` (`django/forms/widgets.py:1159-1160`) only caught `ValueError` when constructing `datetime.date(int(y), int(m), int(d))`, but CPython's C-level date constructor raises `OverflowError` (not `ValueError`) when the yea
  > ```json
{
  "files_changed": ["django/forms/widgets.py"],
  "tests_run": [
    "python /task/repro/repro_overflow.py",
    "python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2",
    "python tests/runtests.py forms_tests.field_tests.test_datefield -v 1"
  ],
  "reproduction": { "script": "/task/repro/repro_overflow.py", "passes": true },
  "confidence": 0.9,
  "blocked": fa
  > Done. Fixed `django/forms/widgets.py:1160` — widened `except ValueError` to `except (ValueError, OverflowError)` in `SelectDateWidget.value_from_datadict` so an oversized year no longer crashes the request; verified via the repro script and the nearest existing test suites (all passing).

grading: applied=True resolved=False F2P failed 1 passed 1; P2P failed 0 passed 24
still-failing hidden tests (F2P):
  - test_value_from_datadict (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_value_from_datadict)
test output tail:
```
idget.SelectDateWidgetTest.test_selectdate_empty_label) ... ok
test_selectdate_required (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_selectdate_required) ... ok
test_value_from_datadict (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_value_from_datadict) ... 
  test_value_from_datadict (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_value_from_datadict) (values=('9223372036854775808', '12', '1')) ... FAIL
test_value_omitted_from_data (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_value_omitted_from_data) ... ok
test_years_rendered_without_separator (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_years_rendered_without_separator) ... ok

======================================================================
FAIL: test_value_from_datadict (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_value_from_datadict) (values=('9223372036854775808', '12', '1'))
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/testbed/tests/forms_tests/widget_tests/test_selectdatewidget.py", line 622, in test_value_from_datadict
    self.assertEqual(
AssertionError: '9223372036854775808-12-1' != '0-0-0'
- 9223372036854775808-12-1
+ 0-0-0


----------------------------------------------------------------------
Ran 26 tests in 0.078s

FAILED (failures=1)
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '
```

model patch touches: django/forms/widgets.py
```diff
diff --git a/django/forms/widgets.py b/django/forms/widgets.py
index 842b73e..f4bc74b 100644
--- a/django/forms/widgets.py
+++ b/django/forms/widgets.py
@@ -1157,7 +1157,7 @@ class SelectDateWidget(Widget):
             input_format = formats.sanitize_strftime_format(input_format)
             try:
                 date_value = datetime.date(int(y), int(m), int(d))
-            except ValueError:
+            except (ValueError, OverflowError):
                 # Return pseudo-ISO dates with zeros for any unselected values,
                 # e.g. '2017-0-23'.
                 return "%s-%s-%s" % (y or 0, m or 0, d or 0)

```

## Run r2: outcome=unresolved resolved=False turns=19 cost=$0.68 wall=183.5s

Agent summary:
```json
{
 "files_changed": [
  "django/forms/widgets.py"
 ],
 "tests_run": [
  "PYTHONPATH=/testbed python /task/repro/repro_overflow.py",
  "cd /testbed/tests && python runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2"
 ],
 "reproduction": {
  "script": "/task/repro/repro_overflow.py",
  "passes": true
 },
 "confidence": 0.9,
 "blocked": false,
 "notes": "Root cause: SelectDateWidget.value_from_datadict wrapped datetime.date(int(y), int(m), int(d)) in except ValueError only, but CPython raises OverflowError for integer components exceeding sys.maxsize; fixed by catching (ValueError, OverflowError) at django/forms/widgets.py:1160. Repro (exit 0 after fix, was exit 1 with unhandled OverflowError before) and all 15 nearest tests (forms_tests.widget_tests.test_selectdatewidget) pass; diff is a single-line change, no test files touched, no debug prints."
}
```

tools: {'ToolSearch': 2, 'Read': 8, 'Bash': 24, 'Grep': 6, 'Agent': 3, 'Write': 1, 'Edit': 1, 'StructuredOutput': 1}
specialists spawned: ['tester', 'backend-dev', 'code-reviewer']
files edited: ['/task/repro/repro_overflow.py', '/testbed/django/forms/widgets.py']
tests run (6):
  - ls /testbed/tests/runtests.py 2>&1 | head -5
  - cd /testbed/tests && python runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -40
  - cd /testbed/tests && python runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -30
  - python -m pytest tests/forms_tests/widget_tests/test_selectdatewidget.py -q 2>&1 | tail -30
  - python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -60
  - cd /testbed/tests && python runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -25
bash commands (24, first 24):
  - git -C /testbed status --short && echo "---" && ls /testbed
  - mkdir -p /task/repro && ls /task/repro
  - ls /testbed/tests/forms_tests/widget_tests/ | grep -i selectdate
  - mkdir -p /task/repro
  - PYTHONPATH=/testbed python /task/repro/repro_overflow.py; echo "EXIT CODE: $?"
  - ls /testbed/tests/runtests.py 2>&1 | head -5
  - cd /testbed/tests && python runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -40
  - git -C /testbed status --porcelain; echo "---"; git -C /testbed diff --stat
  - PYTHONPATH=/testbed python /task/repro/repro_overflow.py; echo "EXIT: $?"
  - PYTHONPATH=/testbed python /task/repro/repro_overflow.py; echo "EXIT: $?"
  - cd /testbed/tests && python runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -30
  - git -C /testbed diff --stat && echo "---" && git -C /testbed diff
  - git -C /testbed diff; echo "---STAT---"; git -C /testbed diff --stat
  - ls -la /task/repro/ 2>&1; echo "---"; cat /task/repro/repro_overflow.py 2>&1; echo "---git status repo---"; git -C /testbed status --porcelain
  - PYTHONPATH=/testbed python /task/repro/repro_overflow.py; echo "EXIT:$?"
  - python -m pytest tests/forms_tests/widget_tests/test_selectdatewidget.py -q 2>&1 | tail -30
  - python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -60
  - git -C /testbed diff --name-only; echo "---"; grep -rn "breakpoint()\|print(" /testbed/django/forms/widgets.py | head -20
  - git diff
  - PYTHONPATH=/testbed python /task/repro/repro_overflow.py; echo "EXIT: $?"
  - git diff --stat
  - git diff | grep -nE '^\+.*(print\(|breakpoint\(|pdb|console\.log)' ; echo "grep exit: $?"
  - cd /testbed/tests && python runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -25
  - git -C /testbed diff --name-only
last agent messages:
  > Verified in my own shell: repro passes (exit 0), diff is a single-line change to `django/forms/widgets.py` only, no test files or debug prints, nearest tests (15/15) pass.
  > ```json
{
  "files_changed": ["django/forms/widgets.py"],
  "tests_run": [
    "PYTHONPATH=/testbed python /task/repro/repro_overflow.py",
    "cd /testbed/tests && python runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2"
  ],
  "reproduction": { "script": "/task/repro/repro_overflow.py", "passes": true },
  "confidence": 0.9,
  "blocked": false,
  "notes": "Root cause: SelectDateWi
  > Fix complete: `django/forms/widgets.py:1160` now catches `(ValueError, OverflowError)` instead of just `ValueError`, preventing the crash when `SelectDateWidget.value_from_datadict` receives an out-of-range year/month/day. Reproduction script confirmed the bug before the fix and passes after; all 15 nearest tests pass; diff touches only that one line.

grading: applied=True resolved=False F2P failed 1 passed 1; P2P failed 0 passed 24
still-failing hidden tests (F2P):
  - test_value_from_datadict (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_value_from_datadict)
test output tail:
```
idget.SelectDateWidgetTest.test_selectdate_empty_label) ... ok
test_selectdate_required (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_selectdate_required) ... ok
test_value_from_datadict (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_value_from_datadict) ... 
  test_value_from_datadict (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_value_from_datadict) (values=('9223372036854775808', '12', '1')) ... FAIL
test_value_omitted_from_data (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_value_omitted_from_data) ... ok
test_years_rendered_without_separator (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_years_rendered_without_separator) ... ok

======================================================================
FAIL: test_value_from_datadict (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_value_from_datadict) (values=('9223372036854775808', '12', '1'))
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/testbed/tests/forms_tests/widget_tests/test_selectdatewidget.py", line 622, in test_value_from_datadict
    self.assertEqual(
AssertionError: '9223372036854775808-12-1' != '0-0-0'
- 9223372036854775808-12-1
+ 0-0-0


----------------------------------------------------------------------
Ran 26 tests in 0.075s

FAILED (failures=1)
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '
```

model patch touches: django/forms/widgets.py
```diff
diff --git a/django/forms/widgets.py b/django/forms/widgets.py
index 842b73e..f4bc74b 100644
--- a/django/forms/widgets.py
+++ b/django/forms/widgets.py
@@ -1157,7 +1157,7 @@ class SelectDateWidget(Widget):
             input_format = formats.sanitize_strftime_format(input_format)
             try:
                 date_value = datetime.date(int(y), int(m), int(d))
-            except ValueError:
+            except (ValueError, OverflowError):
                 # Return pseudo-ISO dates with zeros for any unselected values,
                 # e.g. '2017-0-23'.
                 return "%s-%s-%s" % (y or 0, m or 0, d or 0)

```
