# django__django-16667 under C0: solid_fail (0/3 passes)

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

## Run r0: outcome=unresolved resolved=False turns=21 cost=$0.32 wall=59.3s

Agent summary:
```json
{
 "files_changed": [
  "django/forms/widgets.py"
 ],
 "tests_run": [
  "python /task/repro/repro.py",
  "python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2",
  "python tests/runtests.py forms_tests.field_tests.test_datefield -v 1"
 ],
 "reproduction": {
  "script": "/task/repro/repro.py",
  "passes": true
 },
 "confidence": 0.92,
 "blocked": false,
 "notes": "Root cause: SelectDateWidget.value_from_datadict (django/forms/widgets.py:1159) constructs datetime.date(int(y), int(m), int(d)) and only catches ValueError, but overly large ints (> sys.maxsize) cause datetime.date's C constructor to raise OverflowError instead, crashing the request. Fix: also catch OverflowError alongside ValueError so the value degrades to the existing pseudo-ISO fallback string, matching prior invalid-date handling. All 15 SelectDateWidget tests and 11 DateField tests pass."
}
```

tools: {'ToolSearch': 2, 'Read': 3, 'Grep': 2, 'Bash': 8, 'Write': 2, 'Edit': 1, 'StructuredOutput': 1}
specialists spawned: []
files edited: ['/harness/projects/-testbed/memory/MEMORY.md', '/task/repro/repro.py', '/testbed/django/forms/widgets.py']
tests run (3):
  - python -m pytest tests/forms_tests/widget_tests/test_selectdatewidget.py -q 2>&1 | tail -30
  - python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -40
  - python tests/runtests.py forms_tests.field_tests.test_datefield -v 1 2>&1 | tail -20
bash commands (8, first 8):
  - ls /harness/projects/-testbed/memory/ 2>/dev/null
  - mkdir -p /task/repro
  - python /task/repro/repro.py; echo "EXIT CODE: $?"
  - python /task/repro/repro.py; echo "EXIT CODE: $?"
  - python -m pytest tests/forms_tests/widget_tests/test_selectdatewidget.py -q 2>&1 | tail -30
  - python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -40
  - python tests/runtests.py forms_tests.field_tests.test_datefield -v 1 2>&1 | tail -20
  - git -C /testbed diff
last agent messages:
  > Now let me save a memory note about this codebase/fix pattern for future reference.
  > ```json
{
  "files_changed": ["django/forms/widgets.py"],
  "tests_run": [
    "python /task/repro/repro.py",
    "python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2",
    "python tests/runtests.py forms_tests.field_tests.test_datefield -v 1"
  ],
  "reproduction": { "script": "/task/repro/repro.py", "passes": true },
  "confidence": 0.92,
  "blocked": false,
  "notes": "
  > Done. Summary:

- **Root cause**: `SelectDateWidget.value_from_datadict` in `django/forms/widgets.py:1159` calls `datetime.date(int(y), int(m), int(d))` with user-supplied values, but only catches `ValueError`. Integers larger than `sys.maxsize` cause the C-level date constructor to raise `OverflowError` instead, which propagated uncaught and crashed the request.
- **Fix**: Changed `except ValueEr

grading: applied=True resolved=False F2P failed 1 passed 1; P2P failed 0 passed 24
still-failing hidden tests (F2P):
  - test_value_from_datadict (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_value_from_datadict)
test output tail:
```
st.test_selectdate_empty_label) ... ok
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
>>>>> Test Exit Code: 1
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

## Run r1: outcome=unresolved resolved=False turns=23 cost=$0.34 wall=80.0s

Agent summary:
```json
{
 "files_changed": [
  "django/forms/widgets.py"
 ],
 "tests_run": [
  "python /task/repro/repro.py",
  "python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2",
  "python tests/runtests.py forms_tests.field_tests.test_datefield -v 1"
 ],
 "reproduction": {
  "script": "/task/repro/repro.py",
  "passes": true
 },
 "confidence": 0.9,
 "blocked": false,
 "notes": "Root cause: SelectDateWidget.value_from_datadict only caught ValueError around datetime.date(int(y), int(m), int(d)), but datetime.date raises OverflowError (not ValueError) when a component exceeds C long range, crashing form validation; fixed by also catching OverflowError so oversized values fall back to the existing pseudo-ISO-date handling like other invalid dates."
}
```

tools: {'ToolSearch': 4, 'Read': 2, 'Grep': 2, 'Bash': 8, 'Write': 2, 'Edit': 2, 'StructuredOutput': 1}
specialists spawned: []
files edited: ['/task/repro/repro.py', '/testbed/django/forms/widgets.py']
tests run (3):
  - python -m pytest tests/forms_tests/widget_tests/test_selectdatewidget.py -q 2>&1 | tail -30
  - python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -40
  - python tests/runtests.py forms_tests.field_tests.test_datefield -v 1 2>&1 | tail -20
bash commands (8, first 8):
  - mkdir -p /task/repro
  - python -c "import django; print(django.VERSION)"
  - python /task/repro/repro.py; echo "Exit code: $?"
  - python /task/repro/repro.py; echo "Exit code: $?"
  - python -m pytest tests/forms_tests/widget_tests/test_selectdatewidget.py -q 2>&1 | tail -30
  - python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -40
  - python tests/runtests.py forms_tests.field_tests.test_datefield -v 1 2>&1 | tail -20
  - git -C /testbed diff
last agent messages:
  > All done conditions met: reproduction script fails before fix and passes after, nearest existing tests pass, and the diff is non-empty and minimal.
  > ```json
{
  "files_changed": ["django/forms/widgets.py"],
  "tests_run": [
    "python /task/repro/repro.py",
    "python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2",
    "python tests/runtests.py forms_tests.field_tests.test_datefield -v 1"
  ],
  "reproduction": { "script": "/task/repro/repro.py", "passes": true },
  "confidence": 0.9,
  "blocked": false,
  "notes": "R
  > ```json
{
  "files_changed": ["django/forms/widgets.py"],
  "tests_run": [
    "python /task/repro/repro.py",
    "python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2",
    "python tests/runtests.py forms_tests.field_tests.test_datefield -v 1"
  ],
  "reproduction": { "script": "/task/repro/repro.py", "passes": true },
  "confidence": 0.9,
  "blocked": false,
  "notes": "R

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
Ran 26 tests in 0.076s

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

## Run r2: outcome=unresolved resolved=False turns=20 cost=$0.28 wall=54.5s

Agent summary:
```json
{
 "blocked": false,
 "confidence": 0.95,
 "files_changed": [
  "django/forms/widgets.py"
 ],
 "notes": "Root cause: SelectDateWidget.value_from_datadict (django/forms/widgets.py) only caught ValueError when constructing datetime.date(int(y), int(m), int(d)), but overly large integers (e.g. year > sys.maxsize) raise OverflowError instead, crashing form validation; fixed by also catching OverflowError so such input falls back to the existing pseudo-ISO invalid-date path.",
 "reproduction": {
  "script": "/task/repro/repro.py",
  "passes": true
 },
 "tests_run": [
  "python /task/repro/repro.py",
  "python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2",
  "python tests/runtests.py forms_tests.field_tests.test_datefield -v 1"
 ]
}
```

tools: {'ToolSearch': 2, 'Read': 2, 'Grep': 2, 'Bash': 7, 'Write': 1, 'Edit': 2, 'Glob': 1, 'StructuredOutput': 1}
specialists spawned: []
files edited: ['/task/repro/repro.py', '/testbed/django/forms/widgets.py']
tests run (3):
  - python -m pytest tests/forms_tests/widget_tests/test_selectdatewidget.py -v 2>&1 | tail -60
  - python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -60
  - python tests/runtests.py forms_tests.field_tests.test_datefield -v 1 2>&1 | tail -20
bash commands (7, first 7):
  - mkdir -p /task/repro && ls /task/repro
  - python /task/repro/repro.py; echo "EXIT CODE: $?"
  - python /task/repro/repro.py; echo "EXIT CODE: $?"
  - python -m pytest tests/forms_tests/widget_tests/test_selectdatewidget.py -v 2>&1 | tail -60
  - python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2 2>&1 | tail -60
  - python tests/runtests.py forms_tests.field_tests.test_datefield -v 1 2>&1 | tail -20
  - git -C /testbed diff
last agent messages:
  > All 15 existing tests pass. Let's also run the DateField tests since they're closely related and confirm the diff.
  > All checks pass and the diff is a minimal, single-line fix.

```json
{
  "files_changed": ["django/forms/widgets.py"],
  "tests_run": [
    "python /task/repro/repro.py",
    "python tests/runtests.py forms_tests.widget_tests.test_selectdatewidget -v 2",
    "python tests/runtests.py forms_tests.field_tests.test_datefield -v 1"
  ],
  "reproduction": { "script": "/task/repro/repro.py", "passes": t
  > Fix complete. Summary:

**Root cause**: `SelectDateWidget.value_from_datadict` in `django/forms/widgets.py:1158-1160` called `datetime.date(int(y), int(m), int(d))` inside a `try/except ValueError`, but overly large user-supplied integers (e.g., year values exceeding `sys.maxsize`) cause `datetime.date()` to raise `OverflowError` instead of `ValueError`, which was uncaught and crashed form validat

grading: applied=True resolved=False F2P failed 1 passed 1; P2P failed 0 passed 24
still-failing hidden tests (F2P):
  - test_value_from_datadict (forms_tests.widget_tests.test_selectdatewidget.SelectDateWidgetTest.test_value_from_datadict)
test output tail:
```
st.test_selectdate_empty_label) ... ok
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
Ran 26 tests in 0.074s

FAILED (failures=1)
>>>>> Test Exit Code: 1
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
