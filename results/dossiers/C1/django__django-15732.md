# django__django-15732 under C1: solid_fail (0/1 passes)

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
