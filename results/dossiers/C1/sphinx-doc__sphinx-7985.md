# sphinx-doc__sphinx-7985 under C1: solid_fail (0/3 passes)

repo: sphinx-doc/sphinx  version: 3.2  difficulty: 15 min - 1 hour

## Problem statement

linkcheck could also check local (internal) links
Subject: linkcheck currently doesn't check local (internal) links, but this would be useful.

<!--
  Important: This is a list of issues for Sphinx, not a forum.
  If you'd like to post a question, please move to sphinx-users group.
  https://groups.google.com/forum/#!forum/sphinx-users

  Thanks,
-->

### Problem
See above.

#### Procedure to reproduce the problem
Create a template project with sphinx-quickstart, put the following in index.rst
```
broken external-link_
broken local-link_

.. _external-link: https://lkfqhlkghflkhs
.. _local-link: doesntexist
```

Run `make linkcheck`

#### Error logs / results
```
Running Sphinx v1.7.6
making output directory...
loading pickled environment... done
building [mo]: targets for 0 po files that are out of date
building [linkcheck]: targets for 1 source files that are out of date
updating environment: 0 added, 0 changed, 0 removed
looking for now-outdated files... none found
preparing documents... done
writing output... [100%] index                                                                   
(line   14) -local-   doesntexist
(line   14) broken    https://lkfqhlkghflkhs - HTTPSConnectionPool(host='lkfqhlkghflkhs', port=443): Max retries exceeded with url: / (Caused by NewConnectionError('<urllib3.connection.VerifiedHTTPSConnection object at 0x7faed7ddfc88>: Failed to establish a new connection: [Errno -2] Name or service not known',))

build finished with problems.
make: *** [Makefile:20: linkcheck] Error 1
```

#### Expected results
Also a check for the local link.

### Reproducible project / your project
N/A

### Environment info
- OS: Arch Linux
- Python version: 3.6
- Sphinx version: 1.7.6

## Gold patch touches (files only): sphinx/builders/linkcheck.py

## Run r0: outcome=unresolved resolved=False turns=32 cost=$2.65 wall=795.1s

Agent summary:
```json
{
 "files_changed": [
  "sphinx/builders/linkcheck.py"
 ],
 "tests_run": [
  "python /task/repro/test_linkcheck_local_broken.py",
  "python /task/repro/test_linkcheck_html_link_and_rootrelative.py",
  "cd /testbed && python -m pytest tests/test_build_linkcheck.py -v"
 ],
 "reproduction": {
  "script": "/task/repro/test_linkcheck_local_broken.py",
  "passes": true
 },
 "confidence": 0.55,
 "blocked": false,
 "notes": "Root cause: in CheckExternalLinksBuilder.check_thread's check() (sphinx/builders/linkcheck.py), any non-http(s) refuri was unconditionally returned as status 'local' with no existence check, so broken local/internal links were silently accepted and app.statuscode never flipped to 1. Fix: for non-http(s) URIs with no other URI scheme, resolve the path (handling '#anchor' splitting and root-relative '/' paths against self.srcdir) and mark 'broken' if neither the literal file nor a matching docname (after stripping an output suffix like .html, checked against self.env.found_docs) exists; URIs with another scheme (tel:, data:, irc:, etc.) are returned 'unchecked' to avoid false positives. Two rounds of code review caught and fixed real regressions (false 'broken' for hand-written cross-page .html links and for other URI schemes) before this final version. Unverified: local anchors within an existing local file are not validated (only file/docname existence), and I could not compare against Sphinx's actual upstream fix for this issue (no network access), so the hidden
```

tools: {'ToolSearch': 3, 'Bash': 60, 'Read': 25, 'Agent': 7, 'Write': 2, 'Edit': 4, 'Grep': 6, 'Glob': 2, 'StructuredOutput': 1}
specialists spawned: ['tester', 'backend-dev', 'code-reviewer', 'tester', 'backend-dev', 'critic', 'backend-dev']
files edited: ['/task/repro/test_linkcheck_html_link_and_rootrelative.py', '/task/repro/test_linkcheck_local_broken.py', '/testbed/sphinx/builders/linkcheck.py']
tests run (10):
  - python -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -40
  - python -m pytest tests/test_build_linkcheck.py -v 2>&1 | grep -E "PASSED|FAILED|ERROR|passed|failed|error"
  - python -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -40
  - python -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -40
  - python -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -60
  - python -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -40
  - python /task/repro/test_linkcheck_local_broken.py > /tmp/r1.log 2>&1; echo "repro1 exit=$?"; tail -5 /tmp/r1.log python /task/repro/test_linkcheck_html_link_and
  - python -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -20
  - python -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -40
  - python -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -20
bash commands (60, first 40):
  - echo "$CLAUDE_CONFIG_DIR"
  - git log --oneline -5 && find . -iname "*linkcheck*" -not -path "*/node_modules/*"
  - ls /testbed; echo "---"; cat /testbed/setup.py 2>/dev/null | head -30; echo "---"; ls /testbed/tests/roots/test-linkcheck
  - cat /testbed/tests/roots/test-linkcheck/links.txt; echo "---conf---"; cat /testbed/tests/roots/test-linkcheck/conf.py; echo "---CHANGES head---"; head -60 /test
  - mkdir -p /task/repro && ls /task/repro 2>&1
  - python /task/repro/test_linkcheck_local_broken.py; echo "EXIT CODE: $?"
  - python -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -40
  - python -m pytest tests/test_build_linkcheck.py -v 2>&1 | grep -E "PASSED|FAILED|ERROR|passed|failed|error"
  - git status --short && git diff --stat
  - python /task/repro/test_linkcheck_local_broken.py; echo "EXIT:$?"
  - python /task/repro/test_linkcheck_local_broken.py; echo "EXIT:$?"
  - python -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -40
  - git -C /testbed diff --stat && echo "---" && git -C /testbed diff
  - git diff
  - python /task/repro/test_linkcheck_local_broken.py
  - python -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -40
  - git -C /testbed diff --name-only
  - git -C /testbed diff --stat; echo ---; git -C /testbed diff --name-only
  - ls -la /task/repro/ 2>/dev/null; find /task/repro -type f 2>/dev/null -exec echo {} \; -exec cat {} \;
  - git -C /testbed diff
  - git -C /testbed diff | grep -nE '^\+.*(print\(|breakpoint\(|pdb|console\.log)' ; echo "---diff---"; git -C /testbed diff
  - git status --short
  - python /task/repro/test_linkcheck_local_broken.py; echo "EXIT: $?"
  - find /testbed/tests -iname "*linkcheck*"
  - git -C /testbed status --porcelain; echo ---; ls /testbed/tests/roots/test-linkcheck
  - python -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -60
  - cd /tmp && rm -rf linkchecktest && mkdir linkchecktest && cd linkchecktest && mkdir src && cat > src/conf.py <<'EOF' EOF cat > src/index.rst <<'EOF' Test ====  
  - cd /tmp/linkchecktest && rm -rf out doctree && cat > src/index.rst <<'EOF' Test ====  See `abs link <__nonexistent_root_test__>`_ for details.  .. toctree::    
  - cd /tmp/linkchecktest && rm -rf out doctree && cat > src/index.rst <<'EOF' Test ====  See `abs link <__nonexistent_root_test__>`_ for details.  .. toctree::    
  - cd /tmp/linkchecktest && rm -rf out doctree && cat > src/index.rst <<'EOF' Test ====  broken abslink_  .. _abslink: /this/does/not/exist/anywhere12345 EOF pytho
  - git -C /testbed diff
  - grep -n "self.srcdir\|self.env.srcdir\|found_docs" -r /testbed/sphinx/builders/__init__.py /testbed/sphinx/environment/__init__.py | head -30
  - python /task/repro/test_linkcheck_local_broken.py; echo "EXIT: $?"
  - grep -n "found_docs" -A 10 /testbed/sphinx/environment/__init__.py | head -20
  - python /task/repro/test_linkcheck_local_broken.py; echo "EXIT: $?"
  - python /task/repro/test_linkcheck_html_link_and_rootrelative.py; echo "EXIT: $?"
  - python3 -c " from os import path srcdir = '/tmp/some/src' path_part = '/this/does/not/exist/anywhere12345' full_path = path.join(srcdir, path_part.lstrip('/').l
  - python -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -40
  - git -C /testbed diff --stat && echo "---" && git -C /testbed diff
  - grep -n "print(\|pdb\|breakpoint" /testbed/sphinx/builders/linkcheck.py
last agent messages:
  > Let me do my own final verification: full diff, both repro scripts, nearest tests, and debug-print scan.
  > ```json
{
  "files_changed": ["sphinx/builders/linkcheck.py"],
  "tests_run": [
    "python /task/repro/test_linkcheck_local_broken.py",
    "python /task/repro/test_linkcheck_html_link_and_rootrelative.py",
    "cd /testbed && python -m pytest tests/test_build_linkcheck.py -v"
  ],
  "reproduction": { "script": "/task/repro/test_linkcheck_local_broken.py", "passes": true },
  "confidence": 0.55,

  > Fix complete and verified.

**Summary:** `sphinx/builders/linkcheck.py` classified any non-http(s) `refuri` as `'local'` without ever checking whether the target existed, so broken local/internal links (e.g. `.. _local-link: doesntexist`) were silently accepted. Fixed `check()` to resolve non-http(s), non-other-scheme URIs against the filesystem (with anchor-splitting, root-relative path handling,

grading: applied=True resolved=False F2P failed 2 passed 0; P2P failed 0 passed 3
still-failing hidden tests (F2P):
  - tests/test_build_linkcheck.py::test_defaults
  - tests/test_build_linkcheck.py::test_anchors_ignored
test output tail:
```
================== slowest 25 durations =============================
0.52s call     tests/test_build_linkcheck.py::test_defaults
0.49s call     tests/test_build_linkcheck.py::test_defaults_json
0.18s setup    tests/test_build_linkcheck.py::test_defaults
0.12s call     tests/test_build_linkcheck.py::test_anchors_ignored
0.02s setup    tests/test_build_linkcheck.py::test_defaults_json
0.01s setup    tests/test_build_linkcheck.py::test_anchors_ignored
0.01s call     tests/test_build_linkcheck.py::test_auth
0.01s call     tests/test_build_linkcheck.py::test_linkcheck_request_headers
0.01s setup    tests/test_build_linkcheck.py::test_auth
0.01s setup    tests/test_build_linkcheck.py::test_linkcheck_request_headers

(5 durations < 0.005s hidden.  Use -vv to show these durations.)
=========================== short test summary info ============================
PASSED tests/test_build_linkcheck.py::test_defaults_json
PASSED tests/test_build_linkcheck.py::test_auth
PASSED tests/test_build_linkcheck.py::test_linkcheck_request_headers
FAILED tests/test_build_linkcheck.py::test_defaults - assert 7 == 6
FAILED tests/test_build_linkcheck.py::test_anchors_ignored - AssertionError: ...
================== 2 failed, 3 passed, 192 warnings in 1.45s ===================
py39: exit 1 (1.78 seconds) /testbed> pytest -rA --durations 25 tests/test_build_linkcheck.py pid=54
  py39: FAIL code 1 (1.79=setup[0.01]+cmd[1.78] seconds)
  evaluation failed :( (1.84 seconds)
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '
```

model patch touches: sphinx/builders/linkcheck.py
```diff
diff --git a/sphinx/builders/linkcheck.py b/sphinx/builders/linkcheck.py
index dd53170..3e50644 100644
--- a/sphinx/builders/linkcheck.py
+++ b/sphinx/builders/linkcheck.py
@@ -213,7 +213,32 @@ class CheckExternalLinksBuilder(Builder):
             if len(uri) == 0 or uri.startswith(('#', 'mailto:', 'ftp:')):
                 return 'unchecked', '', 0
             elif not uri.startswith(('http:', 'https:')):
-                return 'local', '', 0
+                if urlparse(uri).scheme:
+                    # not http(s) but still has a URI scheme (e.g. tel:,
+                    # data:, irc:) -- not a filesystem path, so skip it
+                    return 'unchecked', '', 0
+                srcdir = path.dirname(self.env.doc2path(docname))
+                if '#' in uri:
+                    path_part = uri.split('#', 1)[0]
+                else:
+                    path_part = uri
+                if not path_part:
+                    return 'local', '', 0
+                if path_part.startswith('/') or path_part.startswith(path.sep):
+                    full_path = path.join(self.srcdir, path_part.lstrip('/').lstrip(path.sep))
+                else:
+                    full_path = path.join(srcdir, path_part)
+                if path.exists(full_path):
+                    return 'local', '', 0
+                # the target file itself does not exist; it may still be a
+                # valid reference to a document by its *built* filename
+                # (e.g. ``other.html`` for source doc ``other.rst``)
+                docname_part = path.splitext(full_path)[0]
+                to_docname = path.relpath(docname_part, self.srcdir).replace(path.sep, '/')
+                if to_docname in self.env.found_docs:
+                    return 'local', '', 0
+                self.broken[uri] = 'Not found'
+                return 'broken', 'Not found', 0
             elif uri in self.good:
                 return 'working', 'old', 0
             elif uri in self.broken:

```

## Run r1: outcome=unresolved resolved=False turns=36 cost=$0.94 wall=182.3s

Agent summary:
```json
{
 "files_changed": [
  "sphinx/builders/linkcheck.py"
 ],
 "tests_run": [
  "python3 /task/repro/repro.py",
  "python3 -m pytest tests/test_build_linkcheck.py -v"
 ],
 "reproduction": {
  "script": "/task/repro/repro.py",
  "passes": true
 },
 "confidence": 0.55,
 "blocked": false,
 "notes": "Root cause: linkcheck's check() short-circuited any non-http(s) URI to status 'local' without ever verifying the file exists, so broken local links were silently reported as -local- and app.statuscode stayed 0. Fix adds check_local_uri() to resolve the URI relative to the referencing doc's directory and mark it broken (populating self.broken) if the target file doesn't exist. This addresses the exact repro from the issue (a bare relative filename target) but the real upstream Sphinx feature (added later, e.g. resolving :doc:/toctree-style html-relative targets, anchor checking within local HTML output, image/download role targets) may differ in scope from this minimal implementation, so a hidden test checking additional local-link scenarios (like anchors within local files, or :download: targets) may not be fully covered."
}
```

tools: {'ToolSearch': 3, 'Bash': 14, 'Read': 7, 'Grep': 5, 'Write': 1, 'Edit': 3, 'StructuredOutput': 1}
specialists spawned: []
files edited: ['/task/repro/repro.py', '/testbed/sphinx/builders/linkcheck.py']
tests run (1):
  - python3 -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -60
bash commands (14, first 14):
  - echo "$CLAUDE_CONFIG_DIR"
  - git log --oneline -5 && cat setup.py 2>/dev/null | head -20 && find . -iname "*linkcheck*" -not -path "*/node_modules/*"
  - pip show sphinx 2>/dev/null; python3 -c "import sphinx; print(sphinx.__file__)" 2>/dev/null; find / -name "linkcheck.py" 2>/dev/null | grep -v /testbed
  - find tests/roots/test-linkcheck -type f | xargs -I{} sh -c 'echo ==={}===; cat {}'
  - mkdir -p /task/repro && ls /task/repro
  - python3 /task/repro/repro.py; echo "EXIT: $?"
  - python3 /task/repro/repro.py; echo "EXIT: $?"
  - cd /tmp && python3 -c " import shutil, tempfile from pathlib import Path from sphinx.application import Sphinx  SRC = Path(tempfile.mkdtemp()) / 'src' OUT = Pat
  - python3 /task/repro/repro.py; echo "EXIT: $?"
  - python3 -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -60
  - git -C /testbed diff
  - git -C /testbed diff --stat; echo "---debug check---"; git -C /testbed diff | grep -nE '^\+.*(print\(|breakpoint\(|pdb|console\.log)' || echo "none found"
  - cd /tmp && python3 -c " import shutil, tempfile from pathlib import Path from sphinx.application import Sphinx  SRC = Path(tempfile.mkdtemp()) / 'src' OUT = Pat
  - git -C /testbed diff --name-only; echo "---"; git -C /testbed status --short
last agent messages:
  > Valid local links are correctly not flagged as broken. The fix works correctly and existing tests pass.
  > **Summary**

Root cause: `sphinx/builders/linkcheck.py`, in `check()` (around line 213-216 in the original file), any URI not starting with `http:`/`https:` was unconditionally classified as `'local'` and returned immediately — it was never checked against the filesystem, so a broken local link (e.g. `.. _local-link: doesntexist`) was silently logged as `-local-` instead of being flagged broken, a
  > Structured output submitted. Summary of the fix:

**Root cause:** In `sphinx/builders/linkcheck.py`, `check()` short-circuited any non-`http(s)` URI to status `'local'` and returned immediately without ever checking the filesystem — so a broken local link like `.. _local-link: doesntexist` was only logged as `-local-`, never as broken, and the build exit status stayed 0.

**Fix:** Added `check_loc

grading: applied=True resolved=False F2P failed 2 passed 0; P2P failed 0 passed 3
still-failing hidden tests (F2P):
  - tests/test_build_linkcheck.py::test_defaults
  - tests/test_build_linkcheck.py::test_anchors_ignored
test output tail:
```
st 25 durations =============================
0.82s call     tests/test_build_linkcheck.py::test_defaults
0.58s call     tests/test_build_linkcheck.py::test_defaults_json
0.18s setup    tests/test_build_linkcheck.py::test_defaults
0.14s call     tests/test_build_linkcheck.py::test_anchors_ignored
0.02s setup    tests/test_build_linkcheck.py::test_defaults_json
0.01s setup    tests/test_build_linkcheck.py::test_anchors_ignored
0.01s call     tests/test_build_linkcheck.py::test_auth
0.01s call     tests/test_build_linkcheck.py::test_linkcheck_request_headers
0.01s setup    tests/test_build_linkcheck.py::test_auth
0.01s setup    tests/test_build_linkcheck.py::test_linkcheck_request_headers

(5 durations < 0.005s hidden.  Use -vv to show these durations.)
=========================== short test summary info ============================
PASSED tests/test_build_linkcheck.py::test_defaults_json
PASSED tests/test_build_linkcheck.py::test_auth
PASSED tests/test_build_linkcheck.py::test_linkcheck_request_headers
FAILED tests/test_build_linkcheck.py::test_defaults - assert 7 == 6
FAILED tests/test_build_linkcheck.py::test_anchors_ignored - assert not "link...
================== 2 failed, 3 passed, 192 warnings in 1.87s ===================
py39: exit 1 (2.19 seconds) /testbed> pytest -rA --durations 25 tests/test_build_linkcheck.py pid=54
  py39: FAIL code 1 (2.20=setup[0.01]+cmd[2.19] seconds)
  evaluation failed :( (2.25 seconds)
>>>>> Test Exit Code: 1
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '
```

model patch touches: sphinx/builders/linkcheck.py
```diff
diff --git a/sphinx/builders/linkcheck.py b/sphinx/builders/linkcheck.py
index dd53170..8a2d2c3 100644
--- a/sphinx/builders/linkcheck.py
+++ b/sphinx/builders/linkcheck.py
@@ -208,12 +208,26 @@ class CheckExternalLinksBuilder(Builder):
                 else:
                     return 'redirected', new_url, 0
 
+        def check_local_uri() -> Tuple[str, str, int]:
+            # split off anchor
+            if '#' in uri:
+                req_url, _ = uri.split('#', 1)
+            else:
+                req_url = uri
+
+            filename = path.join(path.dirname(self.env.doc2path(docname)), req_url)
+            if req_url and not path.exists(filename):
+                info = __('Local file %r does not exist') % req_url
+                self.broken[uri] = info
+                return 'broken', info, 0
+            return 'local', '', 0
+
         def check() -> Tuple[str, str, int]:
             # check for various conditions without bothering the network
             if len(uri) == 0 or uri.startswith(('#', 'mailto:', 'ftp:')):
                 return 'unchecked', '', 0
             elif not uri.startswith(('http:', 'https:')):
-                return 'local', '', 0
+                return check_local_uri()
             elif uri in self.good:
                 return 'working', 'old', 0
             elif uri in self.broken:

```

## Run r2: outcome=unresolved resolved=False turns=49 cost=$1.90 wall=456.3s

Agent summary:
```json
{
 "files_changed": [
  "sphinx/builders/linkcheck.py"
 ],
 "tests_run": [
  "python3 /task/repro/repro_local_linkcheck.py",
  "python3 -m pytest tests/test_build_linkcheck.py -v"
 ],
 "reproduction": {
  "script": "/task/repro/repro_local_linkcheck.py",
  "passes": true
 },
 "confidence": 0.7,
 "blocked": false,
 "notes": "Root cause: linkcheck's check() classified all non-http(s) URIs as status 'local' without ever verifying them, so broken relative/internal links were silently never flagged as broken. Fix resolves schemeless non-http(s) URIs against the referring document's source directory (path.dirname(self.env.doc2path(docname))) and reports 'broken' if the target file doesn't exist (registering it in self.broken so app.statuscode is set), while URIs with an unrelated non-file scheme (tel:, javascript:, etc.) are left 'unchecked' to avoid false positives (a code-reviewer subagent caught this regression in my first pass; I fixed and re-verified it). Confirmed no false positives for genuine Sphinx internal cross-references (:doc:, :ref:) since this builder's get_target_uri always returns '', so resolved refs have refuri=='' and are filtered earlier. All 5 existing tests in tests/test_build_linkcheck.py pass; repro passes. Unverified: exact match to the upstream/hidden test's expected message wording or status conventions, since the hidden test isn't visible to me."
}
```

tools: {'ToolSearch': 3, 'Bash': 43, 'Read': 15, 'Grep': 10, 'Edit': 4, 'Agent': 2, 'StructuredOutput': 1}
specialists spawned: ['code-reviewer', 'tester']
files edited: ['/testbed/sphinx/builders/linkcheck.py']
tests run (5):
  - python3 -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -40
  - python3 -m pytest tests/test_build_linkcheck.py -v 2>&1 | head -20
  - python3 -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -60
  - python -m pytest tests/test_build_linkcheck.py -q 2>&1 | tail -40
  - python3 /task/repro/repro_local_linkcheck.py && echo "---nearest tests---" && python3 -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -20
bash commands (43, first 40):
  - echo "$CLAUDE_CONFIG_DIR"
  - ls /harness/projects/-testbed/memory/ 2>/dev/null
  - git status --short && echo "---" && ls && echo "---setup---" && cat setup.py 2>/dev/null | head -30
  - find /testbed/tests -iname "*linkcheck*"
  - git log --oneline -5 -- sphinx/builders/linkcheck.py
  - ls -la /testbed/tests/roots/test-linkcheck/ && cat /testbed/tests/roots/test-linkcheck/index.rst 2>/dev/null && echo "---conf---" && cat /testbed/tests/roots/te
  - grep -n "version_info\|__version__" /testbed/sphinx/__init__.py | head -5
  - mkdir -p /task/repro && cat /task/repro/exp_project/index.rst 2>/dev/null; mkdir -p /task/repro/exp_project cat > /task/repro/exp_project/index.rst << 'EOF' Tes
  - python3 - << 'EOF' import sys sys.path.insert(0, '/testbed') from sphinx.application import Sphinx from docutils import nodes  srcdir = '/task/repro/exp_project
  - python3 - << 'EOF' import sys sys.path.insert(0, '/testbed') from sphinx.application import Sphinx from docutils import nodes from sphinx.builders.linkcheck imp
  - rm -rf /task/repro/exp_project /tmp/exp_out /tmp/exp_doctree /tmp/exp_out2 /tmp/exp_doctree2 mkdir -p /task/repro/project cat > /task/repro/project/index.rst <<
  - python3 /task/repro/repro_local_linkcheck.py
  - python3 /task/repro/repro_local_linkcheck.py
  - python3 -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -40
  - python3 -m pytest tests/test_build_linkcheck.py -v 2>&1 | head -20
  - git -C /testbed diff --stat && echo "---diff---" && git -C /testbed diff && echo "---debug check---" && git -C /testbed diff | grep -nE '^\+.*(print\(|breakpoin
  - cd /task/repro/project && cat > extra.rst << 'EOF' Extra ===== EOF cat >> index.rst << 'EOF'  valid local-file-link_  .. _local-file-link: extra.rst EOF python3
  - rm -f /task/repro/project/extra.rst cat > /task/repro/project/index.rst << 'EOF' Test ====  broken local-link_  .. _local-link: doesntexist EOF python3 /task/re
  - python3 /task/repro/repro_local_linkcheck.py; echo "EXIT_CODE=$?"
  - python3 -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -60
  - git -C /testbed diff --stat
  - git -C /testbed diff --stat && echo "---FULL DIFF---" && git -C /testbed diff
  - git -C /testbed diff -- sphinx/builders/linkcheck.py
  - git -C /testbed status --short
  - grep -rn "get_relative_uri\b" sphinx/ | head -30
  - python3 -c " from sphinx.util.osutil import relative_uri print(repr(relative_uri('', ''))) "
  - git -C /testbed status --porcelain echo "---" git -C /testbed diff --name-only echo "--- test file check ---" git -C /testbed diff -- tests/ echo "--- links.txt
  - ls /task/repro/ 2>/dev/null; cat /task/repro/*.py 2>/dev/null; cat /task/repro/*.sh 2>/dev/null; cat /task/repro/run* 2>/dev/null
  - python -m pytest tests/test_build_linkcheck.py -q 2>&1 | tail -40
  - cd /task/repro && python repro_local_linkcheck.py 2>&1 | tail -30
  - cat /task/repro/project/*.rst 2>/dev/null; echo "---conf---"; cat /task/repro/project/conf.py 2>/dev/null
  - grep -n "'local'" /testbed/sphinx/builders/linkcheck.py
  - python3 -c " from os import path print(path.join('/a/b','doesntexist')) print(path.join('/a/b','/abs/path')) print(path.join('/a/b','sub/doesntexist')) print(pa
  - grep -n -i "linkcheck" /testbed/CHANGES 2>/dev/null | head -30
  - python3 -c " from urllib.parse import urlparse for u in ['doesntexist', 'javascript:void(0)', 'tel:+1234', 'urn:isbn:0-486-27557-4', 'irc://example', 'data:text
  - cd /tmp && rm -rf schemetest && mkdir -p schemetest/src schemetest/out schemetest/doctree cat > schemetest/src/conf.py <<'EOF' master_doc = 'index' EOF cat > sc
  - grep -n "def doc2path" -A 15 /testbed/sphinx/environment/__init__.py
  - rm -rf /tmp/schemetest
  - python3 - << 'EOF' import sys, shutil sys.path.insert(0, '/testbed') from sphinx.application import Sphinx  srcdir = '/tmp/scheme_test' shutil.rmtree(srcdir, ig
  - python3 /task/repro/repro_local_linkcheck.py && echo "---nearest tests---" && python3 -m pytest tests/test_build_linkcheck.py -v 2>&1 | tail -20
last agent messages:
  > **Root cause:** `sphinx/builders/linkcheck.py`'s `check()` classified every non-http(s) URI as status `'local'` without ever verifying it, so broken relative/local links were silently ignored instead of being reported as broken.

**Fix:** In the `check()` closure (`sphinx/builders/linkcheck.py:215-227`), non-http(s) URIs with no URI scheme (a true relative path) are now resolved against the referr
  > ```json
{
  "files_changed": ["sphinx/builders/linkcheck.py"],
  "tests_run": [
    "python3 /task/repro/repro_local_linkcheck.py",
    "python3 -m pytest tests/test_build_linkcheck.py -v"
  ],
  "reproduction": { "script": "/task/repro/repro_local_linkcheck.py", "passes": true },
  "confidence": 0.7,
  "blocked": false,
  "notes": "Root cause: linkcheck's check() classified all non-http(s) URIs a
  > Structured output submitted. Summary of the fix:

- **File changed:** `sphinx/builders/linkcheck.py`
- **Root cause:** the `linkcheck` builder classified every non-http(s) URI as status `'local'` without verification, so broken local/internal links (e.g. a relative hyperlink target pointing to a nonexistent file) were never reported as broken.
- **Fix:** schemeless non-http(s) URIs are now resolve

grading: applied=True resolved=False F2P failed 1 passed 1; P2P failed 0 passed 3
still-failing hidden tests (F2P):
  - tests/test_build_linkcheck.py::test_anchors_ignored
test output tail:
```
00m

============================= slowest 25 durations =============================
0.56s call     tests/test_build_linkcheck.py::test_defaults_json
0.48s call     tests/test_build_linkcheck.py::test_defaults
0.17s setup    tests/test_build_linkcheck.py::test_defaults
0.12s call     tests/test_build_linkcheck.py::test_anchors_ignored
0.01s setup    tests/test_build_linkcheck.py::test_anchors_ignored
0.01s setup    tests/test_build_linkcheck.py::test_defaults_json
0.01s call     tests/test_build_linkcheck.py::test_auth
0.01s call     tests/test_build_linkcheck.py::test_linkcheck_request_headers
0.01s setup    tests/test_build_linkcheck.py::test_auth
0.01s setup    tests/test_build_linkcheck.py::test_linkcheck_request_headers

(5 durations < 0.005s hidden.  Use -vv to show these durations.)
=========================== short test summary info ============================
PASSED tests/test_build_linkcheck.py::test_defaults
PASSED tests/test_build_linkcheck.py::test_defaults_json
PASSED tests/test_build_linkcheck.py::test_auth
PASSED tests/test_build_linkcheck.py::test_linkcheck_request_headers
FAILED tests/test_build_linkcheck.py::test_anchors_ignored - AssertionError: ...
================== 1 failed, 4 passed, 192 warnings in 1.45s ===================
py39: exit 1 (1.78 seconds) /testbed> pytest -rA --durations 25 tests/test_build_linkcheck.py pid=54
  py39: FAIL code 1 (1.78=setup[0.01]+cmd[1.78] seconds)
  evaluation failed :( (1.83 seconds)
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '
```

model patch touches: sphinx/builders/linkcheck.py
```diff
diff --git a/sphinx/builders/linkcheck.py b/sphinx/builders/linkcheck.py
index dd53170..cfa2157 100644
--- a/sphinx/builders/linkcheck.py
+++ b/sphinx/builders/linkcheck.py
@@ -213,7 +213,19 @@ class CheckExternalLinksBuilder(Builder):
             if len(uri) == 0 or uri.startswith(('#', 'mailto:', 'ftp:')):
                 return 'unchecked', '', 0
             elif not uri.startswith(('http:', 'https:')):
-                return 'local', '', 0
+                if urlparse(uri).scheme:
+                    # unhandled non-http(s) URI scheme (e.g. tel:, javascript:)
+                    return 'unchecked', '', 0
+                if '#' in uri:
+                    req_url, _ = uri.split('#', 1)
+                else:
+                    req_url = uri
+                srcdir = path.dirname(self.env.doc2path(docname))
+                if path.exists(path.join(srcdir, req_url)):
+                    return 'working', '', 0
+                else:
+                    self.broken[uri] = ''
+                    return 'broken', '', 0
             elif uri in self.good:
                 return 'working', 'old', 0
             elif uri in self.broken:

```
