# django__django-15732 under C0: solid_fail (0/3 passes)

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

## Run r0: outcome=unresolved resolved=False turns=43 cost=$0.79 wall=154.4s

Agent summary:
```json
{
 "files_changed": [
  "django/db/backends/base/schema.py"
 ],
 "tests_run": [
  "python /task/repro/repro.py",
  "python tests/runtests.py schema.tests -v 2"
 ],
 "reproduction": {
  "script": "/task/repro/repro.py",
  "passes": true
 },
 "confidence": 0.75,
 "blocked": false,
 "notes": "Root cause: alter_unique_together's constraint lookup in _delete_composed_index filtered only on unique=True, which on PostgreSQL also matches the implicit primary-key constraint (also reported unique=True there), causing a 'wrong number of constraints' error when dropping unique_together on a PK column; fixed by adding primary_key=False to the filter, matching the existing pattern already used in alter_field (schema.py:826). No PostgreSQL server was available in this sandbox, so end-to-end DB behavior was verified by simulating PostgreSQL-style introspection output (get_constraints) on top of SQLite rather than against a live PostgreSQL instance; the underlying schema.py logic fixed is backend-agnostic and identical to the code path PostgreSQL uses."
}
```

tools: {'ToolSearch': 3, 'Read': 7, 'Grep': 14, 'Bash': 10, 'Write': 2, 'Edit': 4, 'StructuredOutput': 1}
specialists spawned: []
files edited: ['/task/repro/repro.py', '/testbed/django/db/backends/base/schema.py']
tests run (1):
  - python tests/runtests.py schema.tests -v 2 2>&1 | tail -60
bash commands (10, first 10):
  - mkdir -p /task/repro && ls /task/repro
  - python /task/repro/repro.py; echo "EXIT CODE: $?"
  - python /task/repro/repro.py; echo "EXIT CODE: $?"
  - python /task/repro/repro.py; echo "EXIT CODE: $?"
  - which psql pg_ctl postgres 2>&1; python -c "import psycopg2" 2>&1; python -c "import psycopg" 2>&1; env | grep -i postg 2>&1; cat /task/problem.md 2>&1 | head -
  - python /task/repro/repro.py; echo "EXIT CODE: $?"
  - python /task/repro/repro.py; echo "EXIT CODE: $?"
  - python tests/runtests.py schema.tests -v 2 2>&1 | tail -60
  - git -C /testbed diff
  - git -C /testbed diff --name-only
last agent messages:
  > All 179 schema tests pass (28 skipped due to SQLite backend limitations, none related to the fix). Let's also run the broader `migrations` test suite for `AlterUniqueTogether` sanity, and confirm the git diff.
  > **Root cause:** `alter_unique_together()` in `django/db/backends/base/schema.py` deletes a stale `unique_together` constraint via `_delete_composed_index(model, fields, {"unique": True}, ...)`, which looks up constraints filtering only on `unique=True`. On PostgreSQL (and similar backends), the implicit primary-key constraint is also reported as `unique=True`, so for a `unique_together = (('id',),
  > Done. Summary of the fix:

**Root cause:** `alter_unique_together()` in `django/db/backends/base/schema.py` deleted a stale unique-together constraint by looking up constraints filtered only on `unique=True`. On PostgreSQL, the implicit primary-key constraint also reports `unique=True`, so for `unique_together = (('id',),)` on the PK column, two constraints matched, causing `ValueError: Found wron

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
Ran 132 tests in 0.729s

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

## Run r1: outcome=unresolved resolved=False turns=39 cost=$0.78 wall=178.8s

Agent summary:
```json
{
 "files_changed": [
  "django/db/backends/base/schema.py"
 ],
 "tests_run": [
  "python /task/repro/repro.py",
  "python tests/runtests.py schema -v 2",
  "python tests/runtests.py migrations"
 ],
 "reproduction": {
  "script": "/task/repro/repro.py",
  "passes": true
 },
 "confidence": 0.85,
 "blocked": false,
 "notes": "Root cause: BaseDatabaseSchemaEditor._delete_composed_index() (django/db/backends/base/schema.py:559) looks up constraints with {\"unique\": True} without excluding primary-key constraints; on PostgreSQL the introspection reports the pk constraint with unique=True as well as primary_key=True, so a model with unique_together on its pk column alone matches two constraints and raises 'Found wrong number (2) of constraints'. Fixed by always excluding primary_key constraints from that lookup (primary_key=False merged into constraint_kwargs), since neither caller (alter_unique_together, alter_index_together) intends to match the pk constraint. Verified via a repro that monkeypatches introspection.get_constraints on sqlite to add a synthetic pk-unique entry (mirroring postgres's actual behavior), since no Postgres/MySQL/Oracle client is available in this sandboxed, network-less container to reproduce against a real Postgres server directly."
}
```

tools: {'ToolSearch': 2, 'Read': 7, 'Bash': 16, 'Grep': 7, 'Write': 2, 'Edit': 2, 'StructuredOutput': 1}
specialists spawned: []
files edited: ['/task/repro/repro.py', '/testbed/django/db/backends/base/schema.py']
tests run (3):
  - python tests/runtests.py schema -v 2 2>&1 | tail -40
  - python tests/runtests.py migrations -v 1 2>&1 | tail -20
  - python tests/runtests.py migrations 2>&1 | grep -E "^(OK|FAILED|Ran)"
bash commands (16, first 16):
  - git log -1 --format='%H %ci' && python -c "import django; print(django.__version__)" 2>/dev/null; find . -maxdepth 1
  - cat tests/test_sqlite.py 2>/dev/null | head -20; echo ---; python -c "import django; print(django.VERSION)"; echo ---; find . -name "*.cfg" -maxdepth 1
  - mkdir -p /task/repro
  - python /task/repro/repro.py
  - python -c " import django, os from django.conf import settings settings.configure(DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memor
  - which psql pg_ctl postgres 2>&1; python -c "import psycopg2" 2>&1; python -c "import psycopg" 2>&1; pip list 2>/dev/null | grep -i psycopg
  - which mysql mysqld 2>&1; python -c "import MySQLdb" 2>&1; pip list 2>/dev/null | grep -iE "mysql|psycopg|oracle|cx_Oracle"
  - python /task/repro/repro.py
  - python /task/repro/repro.py
  - git stash && python /task/repro/repro.py; echo "EXIT:$?"; git stash pop
  - python /task/repro/repro.py; echo "EXIT:$?"
  - python tests/runtests.py schema -v 2 2>&1 | tail -40
  - python tests/runtests.py migrations -v 1 2>&1 | tail -20
  - python tests/runtests.py migrations 2>&1 | grep -E "^(OK|FAILED|Ran)"
  - git -C /testbed diff
  - git -C /testbed diff --name-only
last agent messages:
  > Diff is minimal, non-empty, only touches `django/db/backends/base/schema.py`. All checks satisfied.
  > ```json
{
  "files_changed": ["django/db/backends/base/schema.py"],
  "tests_run": [
    "python /task/repro/repro.py",
    "python tests/runtests.py schema -v 2",
    "python tests/runtests.py migrations"
  ],
  "reproduction": { "script": "/task/repro/repro.py", "passes": true },
  "confidence": 0.85,
  "blocked": false,
  "notes": "Root cause: BaseDatabaseSchemaEditor._delete_composed_index() (
  > Structured output submitted. Summary:

- **Root cause**: `BaseDatabaseSchemaEditor._delete_composed_index()` in `django/db/backends/base/schema.py` searches for constraints matching `{"unique": True}` without excluding primary-key constraints. On PostgreSQL, the primary key constraint is reported with `unique=True` in addition to `primary_key=True`, so a model with `unique_together = (("id",),)` o

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
  File "/testbed/django/db/backends/base/schema.py", line 572, in _delete_composed_index
    raise ValueError(
ValueError: Found wrong number (2) of constraints for test_rutouf_pony(name)

----------------------------------------------------------------------
Ran 132 tests in 0.709s

FAILED (errors=1, skipped=1)
Destroying test database for alias 'default' ('file:memorydb_default?mode=memory&cache=shared')...
Destroying test database for alias 'other' ('file:memorydb_other?mode=memory&cache=shared')...
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '
```

model patch touches: django/db/backends/base/schema.py
```diff
diff --git a/django/db/backends/base/schema.py b/django/db/backends/base/schema.py
index f2ca8c8..56bed62 100644
--- a/django/db/backends/base/schema.py
+++ b/django/db/backends/base/schema.py
@@ -566,7 +566,7 @@ class BaseDatabaseSchemaEditor:
             model,
             columns,
             exclude=meta_constraint_names | meta_index_names,
-            **constraint_kwargs,
+            **{"primary_key": False, **constraint_kwargs},
         )
         if len(constraint_names) != 1:
             raise ValueError(

```

## Run r2: outcome=unresolved resolved=False turns=40 cost=$0.68 wall=202.8s

Agent summary:
```json
{
 "files_changed": [
  "django/db/backends/base/schema.py"
 ],
 "tests_run": [
  "python /task/repro/repro.py",
  "python tests/runtests.py schema --parallel=1",
  "python tests/runtests.py migrations --parallel=1"
 ],
 "reproduction": {
  "script": "/task/repro/repro.py",
  "passes": true
 },
 "confidence": 0.75,
 "blocked": false,
 "notes": "Root cause: on PostgreSQL, get_constraints() reports the primary key constraint with both primary_key=True and unique=True, so when a model has unique_together on its single pk column (e.g. unique_together = (('id',),)), _delete_composed_index() finds 2 unique constraints matching column 'id' (the pk and the unique_together constraint) instead of 1 and raises ValueError; fixed by adding primary_key=False to the constraint_kwargs used when deleting unique_together constraints so the pk's own constraint is excluded. No live PostgreSQL server was available in this container, so the repro simulates PostgreSQL's introspection behavior by monkeypatching get_constraints() on top of a real sqlite in-memory table to inject a pk entry with unique=True (matching Postgres semantics) and drives the actual SchemaEditor.alter_unique_together code path \u2014 this exercises the real buggy logic in _delete_composed_index/_constraint_names, but was not verified against an actual PostgreSQL server."
}
```

tools: {'ToolSearch': 3, 'Read': 4, 'Grep': 10, 'Bash': 13, 'Write': 5, 'Edit': 2, 'StructuredOutput': 1}
specialists spawned: []
files edited: ['/harness/projects/-testbed/memory/MEMORY.md', '/harness/projects/-testbed/memory/django-schema-notes.md', '/task/repro/repro.py', '/testbed/django/db/backends/base/schema.py']
tests run (2):
  - python tests/runtests.py schema --parallel=1 2>&1 | tail -30
  - python tests/runtests.py migrations --parallel=1 2>&1 | tail -20
bash commands (13, first 13):
  - mkdir -p /task/repro && ls /task/repro
  - python -c "import django; print(django.VERSION)"
  - python /task/repro/repro.py
  - which psql pg_ctl postgres 2>&1; python -c "import psycopg2" 2>&1; python -c "import psycopg" 2>&1
  - python -c " import django from django.conf import settings settings.configure(DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}
  - python /task/repro/repro.py 2>&1 | tail -40
  - python /task/repro/repro.py 2>&1 | tail -40
  - python /task/repro/repro.py 2>&1 | tail -40
  - git diff
  - python tests/runtests.py schema --parallel=1 2>&1 | tail -30
  - python tests/runtests.py migrations --parallel=1 2>&1 | tail -20
  - git -C /testbed diff --name-only; echo "---"; git -C /testbed diff --stat
  - git -C /testbed diff
last agent messages:
  > Now let's finalize with the summary.
  > ```json
{
  "files_changed": ["django/db/backends/base/schema.py"],
  "tests_run": [
    "python /task/repro/repro.py",
    "python tests/runtests.py schema --parallel=1",
    "python tests/runtests.py migrations --parallel=1"
  ],
  "reproduction": { "script": "/task/repro/repro.py", "passes": true },
  "confidence": 0.75,
  "blocked": false,
  "notes": "Root cause: on PostgreSQL, get_constraints
  > Done. Summary of the fix:

**Root cause:** In `django/db/backends/base/schema.py`, `alter_unique_together` calls `_delete_composed_index(model, fields, {"unique": True}, ...)` to find and drop the unique constraint backing a removed `unique_together`. On PostgreSQL, `get_constraints()` reports the primary key constraint with `unique: True` as well as `primary_key: True` (since a PK is implemented 

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
Ran 132 tests in 0.696s

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
