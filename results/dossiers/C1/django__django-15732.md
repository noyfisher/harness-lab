# django__django-15732 under C1: solid_fail (0/3 passes)

repo: django/django  version: 4.2  difficulty: 15 min - 1 hour

## Problem statement

Cannot drop unique_together constraint on a single field with its own unique=True constraint
Description
	
I have an erroneous unique_together constraint on a model's primary key (unique_together = (('id',),)) that cannot be dropped by a migration. Apparently the migration tries to find all unique constraints on the column and expects there to be only one, but I've got two — the primary key and the unique_together constraint:
Indexes:
	"foo_bar_pkey" PRIMARY KEY, btree (id)
	"foo_bar_id_1c3b3088c74c3b17_uniq" UNIQUE CONSTRAINT, btree (id)
Database is PostgreSQL, if that makes any difference.

## Gold patch touches (files only): django/db/backends/base/schema.py

## Run r0: outcome=unresolved resolved=False turns=33 cost=$0.69 wall=132.5s

Agent summary:
```json
{
 "files_changed": [
  "django/db/backends/base/schema.py"
 ],
 "tests_run": [
  "python /task/repro/repro.py",
  "cd /testbed/tests && python runtests.py schema -v1"
 ],
 "reproduction": {
  "script": "/task/repro/repro.py",
  "passes": true
 },
 "confidence": 0.75,
 "blocked": false,
 "notes": "Root cause: alter_unique_together's _delete_composed_index searches for unique=True constraints on the target columns without excluding the primary key; on PostgreSQL/MySQL the PK constraint is also reported unique=True, so when unique_together duplicates the PK column two constraints match and it raises ValueError instead of dropping the extra one. Fixed by excluding primary_key constraints from that search (primary_key: False added to the constraint_kwargs). Verified against real PostgreSQL/MySQL introspection code (both mark PK as unique=True) but could not exercise against a live PostgreSQL/MySQL server in this container (SQLite only, which doesn't naturally reproduce the bug), so the repro monkeypatches get_constraints() to mimic that introspection shape and drives the real schema-editor code path. Nearest existing tests (tests/schema/tests.py, 180 tests) all pass unmodified."
}
```

tools: {'ToolSearch': 3, 'Bash': 12, 'Read': 5, 'Grep': 6, 'Write': 2, 'Edit': 2, 'StructuredOutput': 1}
specialists spawned: []
files edited: ['/task/repro/repro.py', '/testbed/django/db/backends/base/schema.py']
tests run (2):
  - python -c "import django; print(django.VERSION)"; find /testbed -maxdepth 1 -name "*.cfg" -o -maxdepth 1 -name "conftest.py" | head; cat /testbed/tests/runtests
  - cd /testbed/tests && python runtests.py schema -v1 2>&1 | tail -30
bash commands (12, first 12):
  - echo "$CLAUDE_CONFIG_DIR"
  - git -C /testbed status --short; echo "---"; ls /testbed; echo "---"; git -C /testbed log -1 --format="%H %s"
  - mkdir -p /task/repro; ls /task/repro
  - python -c "import django; print(django.VERSION)"; find /testbed -maxdepth 1 -name "*.cfg" -o -maxdepth 1 -name "conftest.py" | head; cat /testbed/tests/runtests
  - python /task/repro/repro.py
  - python3 - <<'EOF' import django from django.conf import settings  settings.configure(     DEBUG=True,     DATABASES={         "default": {             "ENGINE":
  - grep -n -i "unique_together" /testbed/docs/releases/3.1.txt
  - python /task/repro/repro.py; echo "EXIT: $?"
  - python /task/repro/repro.py; echo "EXIT: $?"
  - cd /testbed/tests && python runtests.py schema -v1 2>&1 | tail -30
  - git -C /testbed diff --stat; echo "---"; git -C /testbed diff
  - git -C /testbed diff | grep -nE '^\+.*(print\(|breakpoint\(|pdb|console\.log)'; echo "exit: $?"
last agent messages:
  > Single-line-scope fix, no test file changes, no debug prints, only touches `/testbed` library code plus the repro script in `/task/repro/`. This is XS-sized (traceback names the exact file/line, one-line change), self-localized with grep/read evidence, so I completed it directly without spawning specialists.
  > No debug leftovers (no matches).

```json
{
  "files_changed": ["django/db/backends/base/schema.py"],
  "tests_run": [
    "python /task/repro/repro.py",
    "cd /testbed/tests && python runtests.py schema -v1"
  ],
  "reproduction": { "script": "/task/repro/repro.py", "passes": true },
  "confidence": 0.75,
  "blocked": false,
  "notes": "Root cause: alter_unique_together's _delete_composed_index
  > Structured output submitted. Summary:

- **Root cause**: `alter_unique_together` in `django/db/backends/base/schema.py` looked for `unique=True` constraints on the column without excluding the primary key. On PostgreSQL/MySQL, PK constraints are also reported as `unique=True`, so a `unique_together = (('id',),)` on the PK column caused two matches instead of one, raising `ValueError`.
- **Fix**: a

grading: applied=True resolved=False F2P failed 1 passed 0; P2P failed 0 passed 125
still-failing hidden tests (F2P):
  - test_remove_unique_together_on_unique_field (migrations.test_operations.OperationTests)
test output tail:
```
oveIndex operations ignore swapped models. ... ok
test_references_model_mixin (migrations.test_operations.TestCreateModel) ... ok

======================================================================
ERROR: test_remove_unique_together_on_unique_field (migrations.test_operations.OperationTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/testbed/django/test/testcases.py", line 1571, in skip_wrapper
    return test_func(*args, **kwargs)
  File "/testbed/tests/migrations/test_operations.py", line 2871, in test_remove_unique_together_on_unique_field
    operation.database_forwards(app_label, editor, project_state, new_state)
  File "/testbed/django/db/migrations/operations/models.py", line 565, in database_forwards
    alter_together(
  File "/testbed/django/db/backends/base/schema.py", line 530, in alter_unique_together
    self._delete_composed_index(
  File "/testbed/django/db/backends/base/schema.py", line 575, in _delete_composed_index
    raise ValueError(
ValueError: Found wrong number (2) of constraints for test_rutouf_pony(name)

----------------------------------------------------------------------
Ran 132 tests in 0.745s

FAILED (errors=1, skipped=1)
Destroying test database for alias 'default' ('file:memorydb_default?mode=memory&cache=shared')...
Destroying test database for alias 'other' ('file:memorydb_other?mode=memory&cache=shared')...
>>>>> Test Exit Code: 1
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '
```

model patch touches: django/db/backends/base/schema.py
```diff
diff --git a/django/db/backends/base/schema.py b/django/db/backends/base/schema.py
index f2ca8c8..594b155 100644
--- a/django/db/backends/base/schema.py
+++ b/django/db/backends/base/schema.py
@@ -528,7 +528,10 @@ class BaseDatabaseSchemaEditor:
         # Deleted uniques
         for fields in olds.difference(news):
             self._delete_composed_index(
-                model, fields, {"unique": True}, self.sql_delete_unique
+                model,
+                fields,
+                {"unique": True, "primary_key": False},
+                self.sql_delete_unique,
             )
         # Created uniques
         for field_names in news.difference(olds):

```

## Run r1: outcome=unresolved resolved=False turns=33 cost=$0.66 wall=140.3s

Agent summary:
```json
{
 "files_changed": [
  "django/db/backends/base/schema.py"
 ],
 "tests_run": [
  "python /task/repro/repro_unique_together_pk.py",
  "cd /testbed/tests && python runtests.py schema -v 1"
 ],
 "reproduction": {
  "script": "/task/repro/repro_unique_together_pk.py",
  "passes": true
 },
 "confidence": 0.85,
 "blocked": false,
 "notes": "Root cause: BaseDatabaseSchemaEditor._delete_composed_index (django/db/backends/base/schema.py) is called from alter_unique_together with constraint_kwargs={'unique': True}, and on PostgreSQL the primary-key constraint is also reported as unique=True by introspection, so a single-column unique_together on the PK column matches two constraints (the PK and the unique_together one) and the strict len==1 check raises ValueError, making the constraint undroppable. Fix adds 'primary_key': False to the constraint_kwargs passed for unique_together deletion so the PK constraint is excluded, leaving only the intended unique_together constraint. No PostgreSQL was available in this container, so the repro exercises the real schema.py code path on SQLite by monkeypatching introspection.get_constraints() to mark the PK constraint unique=True (matching documented PostgreSQL introspection output from the bug report), which reproduces the exact 'Found wrong number (2) of constraints' error pre-fix and succeeds post-fix. Full tests/schema suite (180 tests) passes unmodified."
}
```

tools: {'ToolSearch': 3, 'Bash': 15, 'Read': 5, 'Grep': 3, 'Write': 2, 'Edit': 2, 'StructuredOutput': 1}
specialists spawned: []
files edited: ['/task/repro/repro_unique_together_pk.py', '/testbed/django/db/backends/base/schema.py']
tests run (2):
  - python -m pytest tests/schema/tests.py -q 2>&1 | tail -30
  - cd /testbed/tests && python runtests.py schema -v 1 2>&1 | tail -30
bash commands (15, first 15):
  - echo "$CLAUDE_CONFIG_DIR"
  - git -C /testbed status --short; echo "---"; ls /testbed; echo "---"; git -C /testbed log -1
  - mkdir -p /task/repro; ls /task/repro
  - python -c "import django; print(django.VERSION)"; python -c "import sqlite3; print(sqlite3.sqlite_version)"
  - python -c "import django; print(django.__file__)"
  - python /task/repro/repro_unique_together_pk.py
  - python -c " import django from django.conf import settings settings.configure(DEBUG=True, DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME':
  - python -c "import psycopg2" 2>&1; python -c "import psycopg" 2>&1; which psql pg_ctl postgres 2>&1; pip list 2>/dev/null | grep -i psycopg
  - python /task/repro/repro_unique_together_pk.py
  - python /task/repro/repro_unique_together_pk.py
  - git -C /testbed diff
  - python -m pytest tests/schema/tests.py -q 2>&1 | tail -30
  - cd /testbed/tests && python runtests.py schema -v 1 2>&1 | tail -30
  - git -C /testbed diff --stat; echo "---"; git -C /testbed diff | grep -nE '^\+.*(print\(|breakpoint\(|pdb|console\.log)' || echo "no debug leftovers"
  - git -C /testbed diff --name-only
last agent messages:
  > All 180 tests in `tests/schema` pass. Let's also quickly check for a leftover-debug scan and confirm the diff only touches the one file.
  > ```json
{
  "files_changed": ["django/db/backends/base/schema.py"],
  "tests_run": [
    "python /task/repro/repro_unique_together_pk.py",
    "cd /testbed/tests && python runtests.py schema -v 1"
  ],
  "reproduction": { "script": "/task/repro/repro_unique_together_pk.py", "passes": true },
  "confidence": 0.85,
  "blocked": false,
  "notes": "Root cause: BaseDatabaseSchemaEditor._delete_composed
  > Done. Summary:

- **Root cause**: `BaseDatabaseSchemaEditor.alter_unique_together` (`django/db/backends/base/schema.py`) calls `_delete_composed_index` with `{"unique": True}` only. On PostgreSQL the primary key's constraint is also reported `unique=True` by introspection, so a `unique_together` on the PK column matches two constraints instead of one, triggering `ValueError: Found wrong number (2)

grading: applied=True resolved=False F2P failed 1 passed 0; P2P failed 0 passed 125
still-failing hidden tests (F2P):
  - test_remove_unique_together_on_unique_field (migrations.test_operations.OperationTests)
test output tail:
```
eOperationTests)
Add/RemoveIndex operations ignore swapped models. ... ok
test_references_model_mixin (migrations.test_operations.TestCreateModel) ... ok

======================================================================
ERROR: test_remove_unique_together_on_unique_field (migrations.test_operations.OperationTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/testbed/django/test/testcases.py", line 1571, in skip_wrapper
    return test_func(*args, **kwargs)
  File "/testbed/tests/migrations/test_operations.py", line 2871, in test_remove_unique_together_on_unique_field
    operation.database_forwards(app_label, editor, project_state, new_state)
  File "/testbed/django/db/migrations/operations/models.py", line 565, in database_forwards
    alter_together(
  File "/testbed/django/db/backends/base/schema.py", line 530, in alter_unique_together
    self._delete_composed_index(
  File "/testbed/django/db/backends/base/schema.py", line 575, in _delete_composed_index
    raise ValueError(
ValueError: Found wrong number (2) of constraints for test_rutouf_pony(name)

----------------------------------------------------------------------
Ran 132 tests in 0.738s

FAILED (errors=1, skipped=1)
Destroying test database for alias 'default' ('file:memorydb_default?mode=memory&cache=shared')...
Destroying test database for alias 'other' ('file:memorydb_other?mode=memory&cache=shared')...
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '
```

model patch touches: django/db/backends/base/schema.py
```diff
diff --git a/django/db/backends/base/schema.py b/django/db/backends/base/schema.py
index f2ca8c8..594b155 100644
--- a/django/db/backends/base/schema.py
+++ b/django/db/backends/base/schema.py
@@ -528,7 +528,10 @@ class BaseDatabaseSchemaEditor:
         # Deleted uniques
         for fields in olds.difference(news):
             self._delete_composed_index(
-                model, fields, {"unique": True}, self.sql_delete_unique
+                model,
+                fields,
+                {"unique": True, "primary_key": False},
+                self.sql_delete_unique,
             )
         # Created uniques
         for field_names in news.difference(olds):

```

## Run r2: outcome=unresolved resolved=False turns=44 cost=$0.83 wall=200.8s

Agent summary:
```json
{
 "files_changed": [
  "django/db/backends/base/schema.py"
 ],
 "tests_run": [
  "python3 /task/repro/repro.py",
  "python3 tests/runtests.py schema",
  "python3 tests/runtests.py migrations"
 ],
 "reproduction": {
  "script": "/task/repro/repro.py",
  "passes": true
 },
 "confidence": 0.85,
 "blocked": false,
 "notes": "Root cause: _delete_composed_index() in django/db/backends/base/schema.py queried unique constraints on the target columns without excluding the primary key's own constraint, so on backends (e.g. PostgreSQL) that report the PK constraint as unique=True, dropping unique_together=(('id',),) found 2 matches instead of 1 and raised ValueError. Fix passes primary_key=False to the _constraint_names() lookup. SQLite (the only backend available here) reports its PK constraint as unique=False, so the repro monkeypatches introspection.get_constraints() to reproduce the PostgreSQL-shaped constraint list and drive the real alter_unique_together()/_delete_composed_index() code path; this was necessary because no networked DB was available to reproduce natively, and was verified by direct inspection of the introspection output before writing the repro."
}
```

tools: {'ToolSearch': 3, 'Bash': 19, 'Read': 8, 'Grep': 5, 'Write': 1, 'Edit': 5, 'StructuredOutput': 1}
specialists spawned: []
files edited: ['/task/repro/repro.py', '/testbed/django/db/backends/base/schema.py']
tests run (4):
  - cat tests/runtests.py | head -5; ls tests/schema/
  - python3 tests/runtests.py schema 2>&1 | tail -30
  - python3 tests/runtests.py migrations 2>&1 | tail -20
  - python3 tests/runtests.py migrations 2>&1 | grep -E "^(OK|FAILED|Ran|Error)"
bash commands (19, first 19):
  - echo "$CLAUDE_CONFIG_DIR"
  - ls -la /harness/projects/-testbed/memory/ 2>&1
  - git -C /testbed status --short; echo "---"; git -C /testbed log --oneline -3; echo "---"; ls /testbed; echo "---"; cat /testbed/setup.py 2>/dev/null | head -20
  - grep -n "_constraint_names" /testbed/django/db/backends/base/schema.py | head -20
  - grep -n "def _constraint_names" -A 60 /testbed/django/db/backends/base/schema.py
  - mkdir -p /task/repro; cat /testbed/tests/schema/tests.py | grep -n "unique_together" | grep -i "pk\|primary"
  - python3 -c "import django; print(django.__file__)"; python3 -c "import django; print(django.VERSION)"
  - grep -n "alter_unique_together\|_delete_composed_index\|class DatabaseSchemaEditor" /testbed/django/db/backends/sqlite3/schema.py
  - grep -n "def create_model\|unique_together" /testbed/django/db/backends/base/schema.py | head -20
  - python3 /task/repro/repro.py
  - python3 - <<'EOF' import django from django.conf import settings settings.configure(DEBUG=True, DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "
  - python3 /task/repro/repro.py; echo "EXIT: $?"
  - python3 /task/repro/repro.py; echo "EXIT: $?"
  - cat tests/runtests.py | head -5; ls tests/schema/
  - python3 tests/runtests.py schema 2>&1 | tail -30
  - python3 tests/runtests.py migrations 2>&1 | tail -20
  - python3 tests/runtests.py migrations 2>&1 | grep -E "^(OK|FAILED|Ran|Error)"
  - git -C /testbed diff --stat echo "---" git -C /testbed diff echo "---DEBUG CHECK---" git -C /testbed diff | grep -nE '^\+.*(print\(|breakpoint\(|pdb|console\.lo
  - python3 /task/repro/repro.py; echo "EXIT: $?"
last agent messages:
  > Diff is minimal, single file, no test files touched, no debug output. Let's run the repro one final time to confirm end-to-end.
  > This is an XS-sized task (single-function, root cause identified via direct read/grep of `_delete_composed_index`), so I handled it directly without spawning specialists, per the complexity router.

```json
{
  "files_changed": ["django/db/backends/base/schema.py"],
  "tests_run": [
    "python3 /task/repro/repro.py",
    "python3 tests/runtests.py schema",
    "python3 tests/runtests.py migration
  > Done. Summary:

- **Root cause**: `_delete_composed_index()` in `django/db/backends/base/schema.py` looked up unique constraints on the target columns without excluding the primary key's own constraint. On backends where the PK constraint is reported as `unique=True` (e.g. PostgreSQL), dropping `unique_together = (('id',),)` matched both the PK constraint and the unique_together constraint, trippi

grading: applied=True resolved=False F2P failed 1 passed 0; P2P failed 0 passed 125
still-failing hidden tests (F2P):
  - test_remove_unique_together_on_unique_field (migrations.test_operations.OperationTests)
test output tail:
```
eOperationTests)
Add/RemoveIndex operations ignore swapped models. ... ok
test_references_model_mixin (migrations.test_operations.TestCreateModel) ... ok

======================================================================
ERROR: test_remove_unique_together_on_unique_field (migrations.test_operations.OperationTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/testbed/django/test/testcases.py", line 1571, in skip_wrapper
    return test_func(*args, **kwargs)
  File "/testbed/tests/migrations/test_operations.py", line 2871, in test_remove_unique_together_on_unique_field
    operation.database_forwards(app_label, editor, project_state, new_state)
  File "/testbed/django/db/migrations/operations/models.py", line 565, in database_forwards
    alter_together(
  File "/testbed/django/db/backends/base/schema.py", line 530, in alter_unique_together
    self._delete_composed_index(
  File "/testbed/django/db/backends/base/schema.py", line 576, in _delete_composed_index
    raise ValueError(
ValueError: Found wrong number (2) of constraints for test_rutouf_pony(name)

----------------------------------------------------------------------
Ran 132 tests in 0.675s

FAILED (errors=1, skipped=1)
Destroying test database for alias 'default' ('file:memorydb_default?mode=memory&cache=shared')...
Destroying test database for alias 'other' ('file:memorydb_other?mode=memory&cache=shared')...
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '
```

model patch touches: django/db/backends/base/schema.py
```diff
diff --git a/django/db/backends/base/schema.py b/django/db/backends/base/schema.py
index f2ca8c8..17ab158 100644
--- a/django/db/backends/base/schema.py
+++ b/django/db/backends/base/schema.py
@@ -566,6 +566,10 @@ class BaseDatabaseSchemaEditor:
             model,
             columns,
             exclude=meta_constraint_names | meta_index_names,
+            # A unique_together/index_together constraint is never the
+            # model's own primary key constraint, even if it shares columns
+            # with (and, on some backends, is reported alongside) the pk.
+            primary_key=False,
             **constraint_kwargs,
         )
         if len(constraint_names) != 1:

```
