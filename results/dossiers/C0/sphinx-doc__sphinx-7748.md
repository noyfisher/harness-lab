# sphinx-doc__sphinx-7748 under C0: solid_fail (0/3 passes)

repo: sphinx-doc/sphinx  version: 3.1  difficulty: 15 min - 1 hour

## Problem statement

autodoc_docstring_signature with overloaded methods
When using swig to wrap C++ classes for python, if they have overloaded methods, I believe the convention is to place the signatures for each of the overloaded C++ methods at the start of the docstring. Currently, `autodoc_docstring_signature` can only pick up the first one. It would be nice to be able to pick up all of them.

## Gold patch touches (files only): sphinx/ext/autodoc/__init__.py

## Run r0: outcome=unresolved resolved=False turns=58 cost=$1.44 wall=294.4s

Agent summary:
```json
{
 "blocked": false,
 "confidence": 0.75,
 "files_changed": [
  "sphinx/ext/autodoc/__init__.py"
 ],
 "notes": "Root cause: DocstringSignatureMixin._find_signature() in sphinx/ext/autodoc/__init__.py only matched the first leading line of a docstring against the signature regex and stopped ('don't look any further'), so SWIG-style docstrings with one overloaded C++ signature per line only had the first signature recognized while remaining signature lines leaked into the rendered docstring body. Fixed by making _find_signature keep consuming consecutive matching signature lines (collecting a list of (args, retann) pairs) and updating format_signature in DocstringSignatureMixin/DocstringStripSignatureMixin to emit all found signatures (joined with '\\n', the same convention already used for singledispatch overloads and rendered by add_directive_header as multiple indented signature lines under one directive). tests/test_ext_autodoc.py::test_autodoc fails both before and after the fix with an unrelated ANSI-escape-code AssertionError (verified pre-existing by reverting the fix and re-running); all other 66 tests in test_ext_autodoc.py and test_ext_autodoc_configs.py pass.",
 "reproduction": {
  "script": "/task/repro/repro.py",
  "passes": true
 },
 "tests_run": [
  "python /task/repro/repro.py",
  "python -m pytest tests/test_ext_autodoc_configs.py -q",
  "python -m pytest tests/test_ext_autodoc.py -q"
 ]
}
```

tools: {'ToolSearch': 2, 'Read': 14, 'Bash': 23, 'Grep': 4, 'Write': 5, 'Edit': 7, 'StructuredOutput': 1}
specialists spawned: []
files edited: ['/harness/projects/-testbed/memory/MEMORY.md', '/task/repro/repro.py', '/task/repro/testroot/conf.py', '/task/repro/testroot/index.rst', '/task/repro/testroot/overloaded_mod.py', '/testbed/sphinx/ext/autodoc/__init__.py']
tests run (4):
  - python -m pytest tests/test_ext_autodoc_configs.py -q 2>&1 | tail -40
  - python -m pytest tests/test_ext_autodoc.py -q 2>&1 | tail -20
  - git checkout -- sphinx/ext/autodoc/__init__.py && python -m pytest tests/test_ext_autodoc.py::test_autodoc -q 2>&1 | tail -15
  - python -m pytest tests/test_ext_autodoc.py tests/test_ext_autodoc_configs.py -q 2>&1 | tail -15
bash commands (23, first 23):
  - grep -rn "autodoc_docstring_signature" /testbed/sphinx --include=*.py | head -50
  - grep -n "class MethodDocumenter\|class ClassDocumenter\|class DocstringSignatureMixin\|def format_signature" /testbed/sphinx/ext/autodoc/__init__.py
  - grep -rn "docstring_signature" /testbed/tests/*.py | head -30
  - grep -n "DocstringSig" -A 40 /testbed/tests/roots/test-ext-autodoc/target/__init__.py | head -60
  - grep -n -i "overload\|docstring_signature\|multiple signature" /testbed/CHANGES | head -30
  - head -5 /testbed/CHANGES; grep -n "^Release" /testbed/CHANGES | head -3; git log --oneline -1
  - grep -n "self\.args\b\|self\.retann\b" /testbed/sphinx/ext/autodoc/__init__.py
  - grep -n "format_signature(" /testbed/sphinx/ext/autodoc/__init__.py
  - mkdir -p /task/repro
  - sed -n '1,60p' /testbed/tests/test_ext_autodoc.py
  - sed -n '1,80p' /testbed/sphinx/testing/util.py | grep -n "class SphinxTestApp" -A 40
  - mkdir -p /task/repro/testroot
  - python /task/repro/repro.py 2>&1 | tail -60
  - grep -n "^from typing import\|^import typing" /testbed/sphinx/ext/autodoc/__init__.py; git diff
  - python /task/repro/repro.py 2>&1 | tail -60
  - python /task/repro/repro.py 2>&1 | tail -60
  - python -m pytest tests/test_ext_autodoc_configs.py -q 2>&1 | tail -40
  - python -m pytest tests/test_ext_autodoc.py -q 2>&1 | tail -20
  - git diff > /tmp/fix.patch && wc -l /tmp/fix.patch
  - git checkout -- sphinx/ext/autodoc/__init__.py && python -m pytest tests/test_ext_autodoc.py::test_autodoc -q 2>&1 | tail -15
  - git apply /tmp/fix.patch && git diff --stat
  - python -m pytest tests/test_ext_autodoc.py tests/test_ext_autodoc_configs.py -q 2>&1 | tail -15
  - python /task/repro/repro.py 2>&1 | tail -20; echo "---"; git -C /testbed diff --name-only
last agent messages:
  > All three done-condition items are satisfied. Let me save a brief memory note about this pre-existing test failure pattern for future benefit.
  > ```json
{
  "files_changed": ["sphinx/ext/autodoc/__init__.py"],
  "tests_run": [
    "python /task/repro/repro.py",
    "python -m pytest tests/test_ext_autodoc_configs.py -q",
    "python -m pytest tests/test_ext_autodoc.py -q"
  ],
  "reproduction": { "script": "/task/repro/repro.py", "passes": true },
  "confidence": 0.75,
  "blocked": false,
  "notes": "Root cause: DocstringSignatureMixin._fi
  > Structured output submitted. Summary: fixed `sphinx/ext/autodoc/__init__.py` so `autodoc_docstring_signature` picks up all consecutive overloaded signature lines (SWIG-style) at the start of a docstring instead of only the first one; verified with a standalone repro script and the existing `test_ext_autodoc.py`/`test_ext_autodoc_configs.py` suites (one pre-existing, unrelated failure confirmed pre

grading: applied=True resolved=False F2P failed 2 passed 0; P2P failed 0 passed 12
still-failing hidden tests (F2P):
  - tests/test_ext_autodoc_configs.py::test_autoclass_content_and_docstring_signature_init
  - tests/test_ext_autodoc_configs.py::test_autoclass_content_and_docstring_signature_both
test output tail:
```
mary info ============================
PASSED tests/test_ext_autodoc_configs.py::test_autoclass_content_class
PASSED tests/test_ext_autodoc_configs.py::test_autoclass_content_init
PASSED tests/test_ext_autodoc_configs.py::test_autoclass_content_both
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_inherit_docstrings
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_docstring_signature
PASSED tests/test_ext_autodoc_configs.py::test_autoclass_content_and_docstring_signature_class
PASSED tests/test_ext_autodoc_configs.py::test_mocked_module_imports
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_typehints_signature
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_typehints_none
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_typehints_description
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_default_options
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_default_options_with_values
FAILED tests/test_ext_autodoc_configs.py::test_autoclass_content_and_docstring_signature_init
FAILED tests/test_ext_autodoc_configs.py::test_autoclass_content_and_docstring_signature_both
================== 2 failed, 12 passed, 41 warnings in 0.53s ===================
py39: exit 1 (0.90 seconds) /testbed> pytest -rA --durations 25 tests/roots/test-ext-autodoc/target/docstring_signature.py tests/test_ext_autodoc_configs.py pid=56
  py39: FAIL code 1 (0.91=setup[0.01]+cmd[0.90] seconds)
  evaluation failed :( (0.96 seconds)
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '
```

model patch touches: sphinx/ext/autodoc/__init__.py
```diff
diff --git a/sphinx/ext/autodoc/__init__.py b/sphinx/ext/autodoc/__init__.py
index f8e4be9..f55bce8 100644
--- a/sphinx/ext/autodoc/__init__.py
+++ b/sphinx/ext/autodoc/__init__.py
@@ -1037,14 +1037,14 @@ class DocstringSignatureMixin:
     feature of reading the signature from the docstring.
     """
 
-    def _find_signature(self, encoding: str = None) -> Tuple[str, str]:
+    def _find_signature(self, encoding: str = None) -> List[Tuple[str, str]]:
         if encoding is not None:
             warnings.warn("The 'encoding' argument to autodoc.%s._find_signature() is "
                           "deprecated." % self.__class__.__name__,
                           RemovedInSphinx40Warning, stacklevel=2)
         docstrings = self.get_doc()
         self._new_docstrings = docstrings[:]
-        result = None
+        results = []
         for i, doclines in enumerate(docstrings):
             # no lines in docstring, no match
             if not doclines:
@@ -1062,14 +1062,30 @@ class DocstringSignatureMixin:
                     valid_names.extend(cls.__name__ for cls in self.object.__mro__)
             if base not in valid_names:
                 continue
+
+            # keep consuming leading lines as long as they also look like
+            # signatures for the same object (SWIG-style overloaded methods
+            # put one signature per line at the top of the docstring)
+            line_no = 1
+            while True:
+                results.append((args, retann))
+                if line_no >= len(doclines):
+                    break
+                match = py_ext_sig_re.match(doclines[line_no])
+                if not match:
+                    break
+                exmod, path, base, args, retann = match.groups()
+                if base not in valid_names:
+                    break
+                line_no += 1
+
             # re-prepare docstring to ignore more leading indentation
             tab_width = self.directive.state.document.settings.tab_width  # type: ignore
-            self._new_docstrings[i] = prepare_docstring('\n'.join(doclines[1:]),
+            self._new_docstrings[i] = prepare_docstring('\n'.join(doclines[line_no:]),
                                                         tabsize=tab_width)
-            result = args, retann
             # don't look any further
             break
-        return result
+        return results
 
     def get_doc(self, encoding: str = None, ignore: int = None) -> List[List[str]]:
         if encoding is not None:
@@ -1085,9 +1101,16 @@ class DocstringSignatureMixin:
         if self.args is None and self.env.config.autodoc_docstring_signature:  # type: ignore
             # only act if a signature is not explicitly given already, and if
             # the feature is enabled
-            result = self._find_signature()
-            if result is not None:
-                self.args, self.retann = result
+            results = self._find_signature()
+            if results:
+                # if multiple signatures are found, output them all as
+                # separate signature lines (eg. overloaded C++ methods
+                # wrapped by SWIG)
+                sigs = []
+                for args, retann in results:
+                    self.args, self.retann = args, retann
+                    sigs.append(super().format_signature(**kwargs))  # type: ignore
+                return "\n".join(sigs)
         return super().format_signature(**kwargs)  # type: ignore
 
 
@@ -1100,12 +1123,12 @@ class DocstringStripSignatureMixin(DocstringSignatureMixin):
         if self.args is None and self.env.config.autodoc_docstring_signature:  # type: ignore
             # only act if a signature is not explicitly given already, and if
             # the feature is enabled
-            result = self._find_signature()
-            if result is not None:
+            results = self._find_signature()
+            if results:
                 # Discarding _args is a on
```

## Run r1: outcome=unresolved resolved=False turns=47 cost=$1.22 wall=226.1s

Agent summary:
```json
{
 "files_changed": [
  "sphinx/ext/autodoc/__init__.py"
 ],
 "tests_run": [
  "python3 /task/repro/repro.py",
  "python3 -m pytest tests/test_ext_autodoc.py tests/test_ext_autodoc_configs.py -q",
  "python3 -m pytest tests/test_ext_autodoc_configs.py -q"
 ],
 "reproduction": {
  "script": "/task/repro/repro.py",
  "passes": true
 },
 "confidence": 0.85,
 "blocked": false,
 "notes": "Root cause: DocstringSignatureMixin._find_signature() in sphinx/ext/autodoc/__init__.py only matched the first line of a docstring against the signature regex, then stopped, so subsequent overloaded-method signature lines (as emitted by SWIG for wrapped C++ overloads) were left in the docstring body instead of being surfaced as additional `.. py:method::` signatures. Fixed by continuing to scan and collect consecutive matching signature lines into self._signatures, stripping them all from the docstring, and joining them into format_signature()'s output (which the base Documenter.add_directive_header already renders as one directive line per '\\n'-separated signature, mirroring existing singledispatch handling). tests/test_ext_autodoc.py::test_autodoc fails identically on the unmodified base repo (pre-existing, unrelated to this change) \u2014 verified via git stash comparison. All 66 other tests in test_ext_autodoc.py and all 14 tests in test_ext_autodoc_configs.py (including test_autodoc_docstring_signature) pass."
}
```

tools: {'ToolSearch': 3, 'Read': 9, 'Grep': 13, 'Bash': 9, 'Write': 5, 'Edit': 5, 'StructuredOutput': 1}
specialists spawned: []
files edited: ['/task/repro/repro.py', '/task/repro/srcdir/conf.py', '/task/repro/srcdir/index.rst', '/task/repro/srcdir/overloaded_target.py', '/testbed/sphinx/ext/autodoc/__init__.py']
tests run (3):
  - python3 -m pytest tests/test_ext_autodoc.py tests/test_ext_autodoc_configs.py -q 2>&1 | tail -40
  - git stash && python3 -m pytest tests/test_ext_autodoc.py::test_autodoc -q 2>&1 | tail -15 && git stash pop
  - python3 -m pytest tests/test_ext_autodoc_configs.py -q 2>&1 | tail -10
bash commands (9, first 9):
  - mkdir -p /task/repro/srcdir && ls /task/repro
  - python3 /task/repro/repro.py
  - python3 /task/repro/repro.py
  - python3 /task/repro/repro.py
  - python3 -m pytest tests/test_ext_autodoc.py tests/test_ext_autodoc_configs.py -q 2>&1 | tail -40
  - git stash && python3 -m pytest tests/test_ext_autodoc.py::test_autodoc -q 2>&1 | tail -15 && git stash pop
  - python3 -m pytest tests/test_ext_autodoc_configs.py -q 2>&1 | tail -10
  - git -C /testbed diff
  - git -C /testbed diff --name-only
last agent messages:
  > All pass, including `test_autodoc_docstring_signature`, which directly exercises this mixin.
  > ```json
{
  "files_changed": ["sphinx/ext/autodoc/__init__.py"],
  "tests_run": [
    "python3 /task/repro/repro.py",
    "python3 -m pytest tests/test_ext_autodoc.py tests/test_ext_autodoc_configs.py -q",
    "python3 -m pytest tests/test_ext_autodoc_configs.py -q"
  ],
  "reproduction": { "script": "/task/repro/repro.py", "passes": true },
  "confidence": 0.85,
  "blocked": false,
  "notes": "Ro
  > Done. Summary of the fix:

**Root cause**: `DocstringSignatureMixin._find_signature()` in `sphinx/ext/autodoc/__init__.py` only checked the first line of a docstring against the signature regex and stopped there, so additional overloaded-method signature lines (e.g. as SWIG generates for overloaded C++ methods) were left stranded in the docstring body instead of being picked up as extra signatures

grading: applied=True resolved=False F2P failed 2 passed 0; P2P failed 0 passed 12
still-failing hidden tests (F2P):
  - tests/test_ext_autodoc_configs.py::test_autoclass_content_and_docstring_signature_init
  - tests/test_ext_autodoc_configs.py::test_autoclass_content_and_docstring_signature_both
test output tail:
```
mary info ============================
PASSED tests/test_ext_autodoc_configs.py::test_autoclass_content_class
PASSED tests/test_ext_autodoc_configs.py::test_autoclass_content_init
PASSED tests/test_ext_autodoc_configs.py::test_autoclass_content_both
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_inherit_docstrings
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_docstring_signature
PASSED tests/test_ext_autodoc_configs.py::test_autoclass_content_and_docstring_signature_class
PASSED tests/test_ext_autodoc_configs.py::test_mocked_module_imports
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_typehints_signature
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_typehints_none
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_typehints_description
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_default_options
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_default_options_with_values
FAILED tests/test_ext_autodoc_configs.py::test_autoclass_content_and_docstring_signature_init
FAILED tests/test_ext_autodoc_configs.py::test_autoclass_content_and_docstring_signature_both
================== 2 failed, 12 passed, 41 warnings in 0.57s ===================
py39: exit 1 (1.01 seconds) /testbed> pytest -rA --durations 25 tests/roots/test-ext-autodoc/target/docstring_signature.py tests/test_ext_autodoc_configs.py pid=56
  py39: FAIL code 1 (1.02=setup[0.01]+cmd[1.01] seconds)
  evaluation failed :( (1.08 seconds)
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '
```

model patch touches: sphinx/ext/autodoc/__init__.py
```diff
diff --git a/sphinx/ext/autodoc/__init__.py b/sphinx/ext/autodoc/__init__.py
index f8e4be9..63c9cce 100644
--- a/sphinx/ext/autodoc/__init__.py
+++ b/sphinx/ext/autodoc/__init__.py
@@ -1044,6 +1044,7 @@ class DocstringSignatureMixin:
                           RemovedInSphinx40Warning, stacklevel=2)
         docstrings = self.get_doc()
         self._new_docstrings = docstrings[:]
+        self._signatures = []
         result = None
         for i, doclines in enumerate(docstrings):
             # no lines in docstring, no match
@@ -1062,11 +1063,28 @@ class DocstringSignatureMixin:
                     valid_names.extend(cls.__name__ for cls in self.object.__mro__)
             if base not in valid_names:
                 continue
+            result = args, retann
+            # look for additional signatures for overloaded methods, as
+            # generated eg. by SWIG for wrapped C++ overloaded methods:
+            # they are placed as further lines at the start of the docstring
+            line_no = 1
+            while line_no < len(doclines):
+                line = doclines[line_no]
+                if not line:
+                    break
+                match = py_ext_sig_re.match(line)
+                if not match:
+                    break
+                exmod, path, base, args, retann = match.groups()
+                if base not in valid_names:
+                    break
+                sig = "(%s)" % args + ((' -> %s' % retann) if retann else '')
+                self._signatures.append(sig)
+                line_no += 1
             # re-prepare docstring to ignore more leading indentation
             tab_width = self.directive.state.document.settings.tab_width  # type: ignore
-            self._new_docstrings[i] = prepare_docstring('\n'.join(doclines[1:]),
+            self._new_docstrings[i] = prepare_docstring('\n'.join(doclines[line_no:]),
                                                         tabsize=tab_width)
-            result = args, retann
             # don't look any further
             break
         return result
@@ -1088,7 +1106,11 @@ class DocstringSignatureMixin:
             result = self._find_signature()
             if result is not None:
                 self.args, self.retann = result
-        return super().format_signature(**kwargs)  # type: ignore
+        sig = super().format_signature(**kwargs)  # type: ignore
+        if getattr(self, '_signatures', None):
+            return "\n".join([sig] + self._signatures)
+        else:
+            return sig
 
 
 class DocstringStripSignatureMixin(DocstringSignatureMixin):

```

## Run r2: outcome=unresolved resolved=False turns=53 cost=$1.35 wall=278.7s

Agent summary:
```json
{
 "blocked": false,
 "confidence": 0.75,
 "files_changed": [
  "sphinx/ext/autodoc/__init__.py"
 ],
 "notes": "Root cause: DocstringSignatureMixin._find_signature() in sphinx/ext/autodoc/__init__.py only inspected doclines[0] of a docstring and stopped at the first regex match, so a second consecutive overload-signature line (as SWIG emits for overloaded C++ methods) was left in the docstring body instead of being recognized as a signature. Fixed by scanning consecutive leading lines for additional py_ext_sig_re matches and collecting all of them, then having format_signature() join the resulting signatures with '\\n' (the same mechanism already used for singledispatch overloads), so each is rendered as a signature line under one directive. Verified against the full test_ext_autodoc.py/test_ext_autodoc_configs.py suites; the only failing test (test_autodoc, an ANSI-color assertion) fails identically on the unmodified repo (confirmed via git stash) and is unrelated to this change. No hidden/official test for this exact feature exists in the repo to check against, so confidence is based on matching the existing singledispatch overload-signature rendering convention.",
 "reproduction": {
  "script": "/task/repro/repro.py",
  "passes": true
 },
 "tests_run": [
  "python /task/repro/repro.py",
  "python -m pytest tests/test_ext_autodoc.py tests/test_ext_autodoc_configs.py -q"
 ]
}
```

tools: {'ToolSearch': 2, 'Read': 16, 'Grep': 12, 'Bash': 12, 'Write': 4, 'Edit': 4, 'StructuredOutput': 1}
specialists spawned: []
files edited: ['/task/repro/repro.py', '/task/repro/srcdir/conf.py', '/task/repro/srcdir/index.rst', '/task/repro/srcdir/mymodule.py', '/testbed/sphinx/ext/autodoc/__init__.py']
tests run (4):
  - python -m pytest tests/test_ext_autodoc.py tests/test_ext_autodoc_configs.py -q 2>&1 | tail -40
  - git stash && python -m pytest tests/test_ext_autodoc.py::test_singledispatch tests/test_ext_autodoc.py::test_autodoc -q 2>&1 | tail -20; git stash pop
  - python -m pytest tests/test_ext_autodoc.py::test_singledispatch -q 2>&1 | head -60
  - python -m pytest tests/test_ext_autodoc.py tests/test_ext_autodoc_configs.py -q 2>&1 | tail -15
bash commands (12, first 12):
  - mkdir -p /task/repro/srcdir && ls /task/repro
  - python -m pip show sphinx 2>/dev/null | head -3; python -c "import sphinx; print(sphinx.__file__)"
  - python /task/repro/repro.py
  - python /task/repro/repro.py
  - python /task/repro/repro.py
  - python -m pytest tests/test_ext_autodoc.py tests/test_ext_autodoc_configs.py -q 2>&1 | tail -40
  - git stash && python -m pytest tests/test_ext_autodoc.py::test_singledispatch tests/test_ext_autodoc.py::test_autodoc -q 2>&1 | tail -20; git stash pop
  - python -m pytest tests/test_ext_autodoc.py::test_singledispatch -q 2>&1 | head -60
  - python /task/repro/repro.py && echo "REPRO_OK"
  - python -m pytest tests/test_ext_autodoc.py tests/test_ext_autodoc_configs.py -q 2>&1 | tail -15
  - git -C /testbed diff
  - git -C /testbed diff --name-only
last agent messages:
  > Only the pre-existing unrelated `test_autodoc` failure remains (confirmed to fail identically on unmodified repo — an ANSI-color assertion issue unrelated to this change). All 66 other tests pass, including `test_singledispatch`. Let's view the final diff and double check.
  > ```json
{
  "files_changed": ["sphinx/ext/autodoc/__init__.py"],
  "tests_run": [
    "python /task/repro/repro.py",
    "python -m pytest tests/test_ext_autodoc.py tests/test_ext_autodoc_configs.py -q"
  ],
  "reproduction": { "script": "/task/repro/repro.py", "passes": true },
  "confidence": 0.75,
  "blocked": false,
  "notes": "Root cause: DocstringSignatureMixin._find_signature() in sphinx/ex
  > Done. Summary submitted via StructuredOutput.

grading: applied=True resolved=False F2P failed 2 passed 0; P2P failed 0 passed 12
still-failing hidden tests (F2P):
  - tests/test_ext_autodoc_configs.py::test_autoclass_content_and_docstring_signature_init
  - tests/test_ext_autodoc_configs.py::test_autoclass_content_and_docstring_signature_both
test output tail:
```
==============
PASSED tests/test_ext_autodoc_configs.py::test_autoclass_content_class
PASSED tests/test_ext_autodoc_configs.py::test_autoclass_content_init
PASSED tests/test_ext_autodoc_configs.py::test_autoclass_content_both
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_inherit_docstrings
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_docstring_signature
PASSED tests/test_ext_autodoc_configs.py::test_autoclass_content_and_docstring_signature_class
PASSED tests/test_ext_autodoc_configs.py::test_mocked_module_imports
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_typehints_signature
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_typehints_none
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_typehints_description
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_default_options
PASSED tests/test_ext_autodoc_configs.py::test_autodoc_default_options_with_values
FAILED tests/test_ext_autodoc_configs.py::test_autoclass_content_and_docstring_signature_init
FAILED tests/test_ext_autodoc_configs.py::test_autoclass_content_and_docstring_signature_both
================== 2 failed, 12 passed, 41 warnings in 0.50s ===================
py39: exit 1 (0.84 seconds) /testbed> pytest -rA --durations 25 tests/roots/test-ext-autodoc/target/docstring_signature.py tests/test_ext_autodoc_configs.py pid=56
  py39: FAIL code 1 (0.85=setup[0.01]+cmd[0.84] seconds)
  evaluation failed :( (0.90 seconds)
>>>>> Test Exit Code: 1
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '
```

model patch touches: sphinx/ext/autodoc/__init__.py
```diff
diff --git a/sphinx/ext/autodoc/__init__.py b/sphinx/ext/autodoc/__init__.py
index f8e4be9..297cb63 100644
--- a/sphinx/ext/autodoc/__init__.py
+++ b/sphinx/ext/autodoc/__init__.py
@@ -1037,14 +1037,14 @@ class DocstringSignatureMixin:
     feature of reading the signature from the docstring.
     """
 
-    def _find_signature(self, encoding: str = None) -> Tuple[str, str]:
+    def _find_signature(self, encoding: str = None) -> List[Tuple[str, str]]:
         if encoding is not None:
             warnings.warn("The 'encoding' argument to autodoc.%s._find_signature() is "
                           "deprecated." % self.__class__.__name__,
                           RemovedInSphinx40Warning, stacklevel=2)
         docstrings = self.get_doc()
         self._new_docstrings = docstrings[:]
-        result = None
+        results = []  # type: List[Tuple[str, str]]
         for i, doclines in enumerate(docstrings):
             # no lines in docstring, no match
             if not doclines:
@@ -1062,14 +1062,24 @@ class DocstringSignatureMixin:
                     valid_names.extend(cls.__name__ for cls in self.object.__mro__)
             if base not in valid_names:
                 continue
+            results.append((args, retann))
+            # look for more matching signature lines directly following
+            # this one (e.g. for overloaded methods generated by SWIG)
+            for line in doclines[1:]:
+                match = py_ext_sig_re.match(line)
+                if not match:
+                    break
+                exmod, path, base, args, retann = match.groups()
+                if base not in valid_names:
+                    break
+                results.append((args, retann))
             # re-prepare docstring to ignore more leading indentation
             tab_width = self.directive.state.document.settings.tab_width  # type: ignore
-            self._new_docstrings[i] = prepare_docstring('\n'.join(doclines[1:]),
+            self._new_docstrings[i] = prepare_docstring('\n'.join(doclines[len(results):]),
                                                         tabsize=tab_width)
-            result = args, retann
             # don't look any further
             break
-        return result
+        return results
 
     def get_doc(self, encoding: str = None, ignore: int = None) -> List[List[str]]:
         if encoding is not None:
@@ -1085,9 +1095,15 @@ class DocstringSignatureMixin:
         if self.args is None and self.env.config.autodoc_docstring_signature:  # type: ignore
             # only act if a signature is not explicitly given already, and if
             # the feature is enabled
-            result = self._find_signature()
-            if result is not None:
-                self.args, self.retann = result
+            results = self._find_signature()
+            if results:
+                # signature(s) found in the docstring, use them (there may be
+                # more than one for overloaded methods)
+                sigs = []
+                for args, retann in results:
+                    self.args, self.retann = args, retann
+                    sigs.append(super().format_signature(**kwargs))  # type: ignore
+                return "\n".join(sigs)
         return super().format_signature(**kwargs)  # type: ignore
 
 
@@ -1100,12 +1116,12 @@ class DocstringStripSignatureMixin(DocstringSignatureMixin):
         if self.args is None and self.env.config.autodoc_docstring_signature:  # type: ignore
             # only act if a signature is not explicitly given already, and if
             # the feature is enabled
-            result = self._find_signature()
-            if result is not None:
+            results = self._find_signature()
+            if results:
                 # Discarding _args is a only difference with
                 # DocstringSignatureMixin.format_signature.
                 # Documenter.format_signature use self.args value to format.
-              
```
