"""
BuildFail-SLM: Master Acceptance Test Suite (Scenarios A through T)
Executes comprehensive evaluation against the live backend/predictor across:
  A. Python implementation failure
  B. Python test failure (contradictory/impossible test)
  C. Python dependency failure
  D. Python environment failure
  E. Python no-failure repository
  F. JavaScript implementation/test failure
  G. Node dependency failure
  H. Node workflow failure
  I. Java build failure
  J. Internal import/package failure
  K. Configuration failure
  L. Runtime failure
  M. Infrastructure failure
  N. System/runner traceback
  O. Multiple simultaneous failures
  P. Missing source
  Q. Invalid generated diff (placeholders/commands)
  R. Nonexistent file
  S. Valid applicable diff
  T. Semantically incorrect but applicable diff
"""

import os
import sys
import json
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.analyzer import (
    validate_repository_file,
    validate_diff,
    check_patch_applicability_and_semantic_verify,
    is_test_file,
    extract_assertion_evidence,
    classify_failure_nature,
    derive_repository_verification_command,
    assess_test_vs_implementation,
    detect_multiple_failures
)
from backend.predictor import BuildFailPredictor


def run_acceptance_tests():
    print("=" * 75)
    print("🚀 RUNNING BUILDFAIL-SLM MASTER ACCEPTANCE TEST SUITE (20 SCENARIOS)")
    print("=" * 75)

    predictor = BuildFailPredictor(model_loader=None)
    results = []

    # -------------------------------------------------------------
    # Scenario A: Python implementation failure
    # -------------------------------------------------------------
    log_a = """
    FAILED tests/test_calculator.py::test_add - AssertionError: assert -2 == 8
    + where -2 = add(3, 5)
    """
    repo_files_a = ["app/calculator.py", "tests/test_calculator.py", "requirements.txt"]
    cat_a, target_type_a = classify_failure_nature(log_a, repo_files_a)
    ev_a = extract_assertion_evidence(log_a)
    verdict_a, _ = assess_test_vs_implementation("assert add(3, 5) == 8", "def add(a, b):\n    return a - b", ev_a)
    verif_a = derive_repository_verification_command("Python", cat_a, target_type_a, "tests/test_calculator.py", repo_files=repo_files_a)
    
    mock_out_a = """### Failure Category:
Test Failure
### Root Cause Analysis:
The implementation in app/calculator.py uses subtraction instead of addition, returning -2 instead of expected 8.
### Proposed Unified Diff:
```diff
--- a/app/calculator.py
+++ b/app/calculator.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
```
### Recommended Remediation:
pytest tests/test_calculator.py
"""
    pred_a = predictor.parse_prediction(
        mock_out_a,
        impl_file="app/calculator.py",
        test_file="tests/test_calculator.py",
        failure_location="tests/test_calculator.py",
        repair_target_type=target_type_a,
        test_vs_implementation=verdict_a,
        repo_files=repo_files_a,
        language="Python",
        failure_log=log_a,
        evidence=ev_a
    )
    pass_a = pred_a["failure_type"] == "Test Failure" and pred_a["source_file"] == "app/calculator.py" and pred_a["diff_valid"] and "pytest" in pred_a["verification"]
    results.append(("A. Python implementation failure", pass_a, pred_a))

    # -------------------------------------------------------------
    # Scenario B: Python test failure (contradictory / impossible test)
    # -------------------------------------------------------------
    log_b = """
    FAILED tests/test_math.py::test_impossible - AssertionError: assert 4 == 99
    + where 4 = add(2, 2)
    """
    repo_files_b = ["app/math.py", "tests/test_math.py"]
    ev_b = extract_assertion_evidence(log_b)
    verdict_b, target_type_b = assess_test_vs_implementation("assert add(2, 2) == 99", "def add(a, b):\n    return a + b", ev_b)
    pass_b = verdict_b == "IMPLEMENTATION CORRECT / TEST WRONG" and target_type_b == "TEST"
    results.append(("B. Python test failure (impossible test)", pass_b, {"verdict": verdict_b, "target_type": target_type_b}))

    # -------------------------------------------------------------
    # Scenario C: Python dependency failure
    # -------------------------------------------------------------
    log_c = "ModuleNotFoundError: No module named 'requests'"
    repo_files_c = ["app/main.py", "tests/test_main.py"]
    cat_c, target_type_c = classify_failure_nature(log_c, repo_files_c)
    pred_c = predictor.parse_prediction(
        "### Failure Category:\nDependency Error\n### Root Cause Analysis:\nrequests missing",
        impl_file="app/main.py",
        repair_target_type=target_type_c,
        repo_files=repo_files_c,
        language="Python",
        failure_log=log_c
    )
    pass_c = pred_c["failure_type"] == "Dependency Error" and pred_c["source_file"] == "Not identified" and pred_c["proposed_diff"].startswith("No source-code fix") and "pip install" in pred_c["verification"]
    results.append(("C. Python dependency failure", pass_c, pred_c))

    # -------------------------------------------------------------
    # Scenario D: Python environment failure
    # -------------------------------------------------------------
    log_d = "KeyError: 'DATABASE_URL'"
    cat_d, target_type_d = classify_failure_nature(log_d, ["app/db.py"])
    pred_d = predictor.parse_prediction(
        "### Failure Category:\nEnvironment Error\n### Root Cause Analysis:\nDATABASE_URL missing",
        impl_file="app/db.py",
        repair_target_type=target_type_d,
        repo_files=["app/db.py"],
        language="Python",
        failure_log=log_d
    )
    pass_d = pred_d["failure_type"] == "Environment Error" and pred_d["source_file"] == "Not identified" and (pred_d["proposed_diff"].startswith("No source-code fix") or pred_d["proposed_diff"].startswith("Actionable Remediation"))
    results.append(("D. Python environment failure", pass_d, pred_d))

    # -------------------------------------------------------------
    # Scenario E: Python no-failure repository (Section 19)
    # -------------------------------------------------------------
    log_e = "All tests passed successfully (0 failures)."
    cat_e, target_type_e = classify_failure_nature(log_e, ["app/main.py"])
    pred_e = predictor.parse_prediction(
        "### Failure Category:\nNone",
        impl_file="app/main.py",
        repair_target_type="NONE",
        repo_files=["app/main.py"],
        language="Python",
        failure_log=log_e
    )
    pass_e = pred_e["failure_type"] == "None" and pred_e["root_cause"] == "No CI/CD failure detected." and pred_e["source_file"] == "Not identified" and pred_e["proposed_diff"].startswith("No source-code fix") and pred_e["confidence"] == "High"
    results.append(("E. Python no-failure repository", pass_e, pred_e))


    # -------------------------------------------------------------
    # Scenario F: JavaScript implementation/test failure
    # -------------------------------------------------------------
    log_f = """
    FAIL tests/app/arrays.test.js
    ● arrays › deduplicate should remove duplicate numbers
      Expected: [1, 2, 3]
      Received: [1, 2, 2, 3]
    """
    repo_files_f = ["app/arrays.js", "tests/app/arrays.test.js", "package.json"]
    cat_f, target_type_f = classify_failure_nature(log_f, repo_files_f)
    ev_f = extract_assertion_evidence(log_f)
    verif_f = derive_repository_verification_command("JavaScript", cat_f, target_type_f, "tests/app/arrays.test.js", repo_files=repo_files_f)
    mock_out_f = """### Failure Category:
Test Failure
### Root Cause Analysis:
arrays.js deduplicate function does not create a unique Set.
### Proposed Unified Diff:
```diff
--- a/app/arrays.js
+++ b/app/arrays.js
@@ -1,3 +1,3 @@
 function deduplicate(arr) {
-    return arr;
+    return [...new Set(arr)];
 }
```
### Recommended Remediation:
npm test
"""
    pred_f = predictor.parse_prediction(
        mock_out_f,
        impl_file="app/arrays.js",
        test_file="tests/app/arrays.test.js",
        failure_location="tests/app/arrays.test.js",
        repair_target_type=target_type_f,
        repo_files=repo_files_f,
        language="JavaScript",
        failure_log=log_f,
        evidence=ev_f
    )
    pass_f = pred_f["failure_type"] == "Test Failure" and pred_f["source_file"] == "app/arrays.js" and "pytest" not in pred_f["verification"] and "npm test" in pred_f["verification"]
    results.append(("F. JavaScript implementation/test failure", pass_f, pred_f))

    # -------------------------------------------------------------
    # Scenario G: Node dependency failure
    # -------------------------------------------------------------
    log_g = "npm ERR! 404 Not Found - GET https://registry.npmjs.org/nonexistent-package"
    repo_files_g = ["index.js", "package.json"]
    cat_g, target_type_g = classify_failure_nature(log_g, repo_files_g)
    verif_g = derive_repository_verification_command("JavaScript", cat_g, target_type_g, repo_files=repo_files_g)
    pass_g = cat_g == "Dependency Error" and target_type_g == "DEPENDENCY" and "npm install" in verif_g and "pytest" not in verif_g
    results.append(("G. Node dependency failure", pass_g, {"cat": cat_g, "verif": verif_g}))

    # -------------------------------------------------------------
    # Scenario H: Node workflow failure
    # -------------------------------------------------------------
    log_h = "The workflow is not valid. .github/workflows/ci.yml (Line: 14, Col: 7): Unrecognized named-value: 'secrets.WRONG'"
    repo_files_h = [".github/workflows/ci.yml", "package.json"]
    cat_h, target_type_h = classify_failure_nature(log_h, repo_files_h)
    pass_h = cat_g == "Dependency Error" and cat_h == "Configuration Error" and target_type_h == "CONFIGURATION"
    results.append(("H. Node workflow failure", pass_h, {"cat": cat_h, "target_type": target_type_h}))

    # -------------------------------------------------------------
    # Scenario I: Java build failure
    # -------------------------------------------------------------
    log_i = "[ERROR] COMPILATION ERROR : cannot find symbol class StringUtils [pom.xml:24]"
    repo_files_i = ["src/main/java/App.java", "pom.xml"]
    cat_i, target_type_i = classify_failure_nature(log_i, repo_files_i)
    verif_i = derive_repository_verification_command("Java", cat_i, target_type_i, repo_files=repo_files_i)
    pass_i = cat_i == "Compilation Error" and "mvn" in verif_i
    results.append(("I. Java build failure", pass_i, {"cat": cat_i, "verif": verif_i}))

    # -------------------------------------------------------------
    # Scenario J: Internal import/package failure
    # -------------------------------------------------------------
    log_j = "ModuleNotFoundError: No module named 'app.utils' in tests/test_main.py"
    repo_files_j = ["app/utils.py", "app/main.py", "tests/test_main.py"]
    cat_j, target_type_j = classify_failure_nature(log_j, repo_files_j)
    pass_j = cat_j == "Code Error" and target_type_j == "IMPLEMENTATION"  # distinguished from external dependency
    results.append(("J. Internal import/package failure", pass_j, {"cat": cat_j, "target_type": target_type_j}))

    # -------------------------------------------------------------
    # Scenario K: Configuration failure
    # -------------------------------------------------------------
    log_k = "YAML syntax error in .github/workflows/ci.yml: mapping values are not allowed here"
    cat_k, target_type_k = classify_failure_nature(log_k, [".github/workflows/ci.yml"])
    pass_k = cat_k == "Configuration Error" and target_type_k == "CONFIGURATION"
    results.append(("K. Configuration failure", pass_k, {"cat": cat_k, "target_type": target_type_k}))

    # -------------------------------------------------------------
    # Scenario L: Runtime failure
    # -------------------------------------------------------------
    log_l = "TypeError: unsupported operand type(s) for +: 'int' and 'str'"
    cat_l, target_type_l = classify_failure_nature(log_l, ["app/calc.py"])
    pass_l = cat_l == "Runtime Error" and target_type_l == "IMPLEMENTATION"
    results.append(("L. Runtime failure", pass_l, {"cat": cat_l, "target_type": target_type_l}))

    # -------------------------------------------------------------
    # Scenario M: Infrastructure failure
    # -------------------------------------------------------------
    log_m = "Runner has encountered an internal error. Hosted runner is unavailable. OOMKilled"
    cat_m, target_type_m = classify_failure_nature(log_m, ["app/main.py"])
    pred_m = predictor.parse_prediction(
        "### Failure Category:\nInfrastructure Error\n### Root Cause Analysis:\nOOMKilled by runner",
        impl_file="app/main.py",
        repair_target_type=target_type_m,
        repo_files=["app/main.py"],
        language="Python",
        failure_log=log_m
    )
    pass_m = pred_m["failure_type"] == "Infrastructure Error" and pred_m["source_file"] == "Not identified" and (pred_m["proposed_diff"].startswith("No source-code fix") or pred_m["proposed_diff"].startswith("Actionable Remediation"))
    results.append(("M. Infrastructure failure", pass_m, pred_m))

    # -------------------------------------------------------------
    # Scenario N: System/runner traceback path defense
    # -------------------------------------------------------------
    system_paths = [
        "C:\\Program Files\\WindowsApps\\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\\Lib\\importlib\\__init__.py",
        "/opt/hostedtoolcache/Python/3.11.4/x64/lib/python3.11/site-packages/pytest/__init__.py",
        "/usr/lib/python3.10/unittest/runner.py",
        "/home/runner/work/_temp/virtualenv/lib/site-packages/pkg.py"
    ]
    repo_files_n = ["app/main.py", "tests/test_main.py"]
    pass_n = all(validate_repository_file(sp, repository_files=repo_files_n) == "Not identified" for sp in system_paths)
    results.append(("N. System/runner traceback path rejection", pass_n, {"tested": len(system_paths)}))

    # -------------------------------------------------------------
    # Scenario O: Multiple simultaneous failures
    # -------------------------------------------------------------
    log_o = """
    FAILED tests/test_a.py::test_one - AssertionError
    FAILED tests/test_b.py::test_two - KeyError: 'API_KEY'
    FAILED tests/test_c.py::test_three - ModuleNotFoundError: No module named 'yaml'
    """
    multi_o = detect_multiple_failures(log_o)
    pass_o = multi_o["has_multiple"] and multi_o["failure_count"] >= 3
    results.append(("O. Multiple simultaneous failures", pass_o, multi_o))

    # -------------------------------------------------------------
    # Scenario P: Missing source
    # -------------------------------------------------------------
    pred_p = predictor.parse_prediction(
        "### Failure Category:\nTest Failure\n### Root Cause Analysis:\nLogic mismatch",
        impl_file="Not identified",
        test_file="Not identified",
        repair_target_type="IMPLEMENTATION",
        repo_files=[],
        language="Python",
        failure_log="AssertionError: assert 1 == 2"
    )
    pass_p = pred_p["source_file"] == "Not identified" and pred_p["proposed_diff"].startswith("No source-code fix")
    results.append(("P. Missing source handling", pass_p, pred_p))

    # -------------------------------------------------------------
    # Scenario Q: Invalid generated diff (placeholders/commands)
    # -------------------------------------------------------------
    bad_diff_1 = "```diff\n--- a/app/main.py\n+++ b/app/main.py\n@@ -1 +1 @@\n-<old code>\n+<fixed code>\n```"
    bad_diff_2 = "```diff\n--- a/app/main.py\n+++ b/app/main.py\n@@ -1 +1 @@\n-def add():\n+pip install pytest\n```"
    val_q1, _ = validate_diff(bad_diff_1, "app/main.py", ["app/main.py"])
    val_q2, _ = validate_diff(bad_diff_2, "app/main.py", ["app/main.py"])
    pass_q = (not val_q1) and (not val_q2)
    results.append(("Q. Invalid generated diff rejection", pass_q, {"rejected_placeholder": not val_q1, "rejected_command": not val_q2}))

    # -------------------------------------------------------------
    # Scenario R: Nonexistent file rejection
    # -------------------------------------------------------------
    diff_r = "```diff\n--- a/does_not_exist.py\n+++ b/does_not_exist.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n```"
    val_r, _ = validate_diff(diff_r, "does_not_exist.py", ["app/main.py"])
    pass_r = not val_r
    results.append(("R. Nonexistent file diff rejection", pass_r, {"val": val_r}))

    # -------------------------------------------------------------
    # Scenario S: Valid applicable diff
    # -------------------------------------------------------------
    diff_s = "--- a/app/calc.py\n+++ b/app/calc.py\n@@ -1,2 +1,2 @@\n def sub(a, b):\n-    return a + b\n+    return a - b"
    val_s, clean_s = validate_diff(diff_s, "app/calc.py", ["app/calc.py"])
    pass_s = val_s and "return a - b" in clean_s
    results.append(("S. Valid applicable diff synthesis", pass_s, {"val": val_s}))

    # -------------------------------------------------------------
    # Scenario T: Semantically inconsistent diff rejection (Diagnosis-Diff consistency)
    # -------------------------------------------------------------
    # Diagnosis is Dependency Error, but model generated a code diff changing business logic
    diff_t = "--- a/app/calc.py\n+++ b/app/calc.py\n@@ -1,2 +1,2 @@\n-def calc():\n+def calc_fixed():"
    val_t, _ = validate_diff(diff_t, "app/calc.py", ["app/calc.py"], root_cause="Missing package requests", repair_target_type="DEPENDENCY")
    pass_t = not val_t  # Successfully rejected because Dependency Error must not produce code diff!
    results.append(("T. Diagnosis-Diff consistency gate (Reject code diff on non-code error)", pass_t, {"val": val_t}))

    # -------------------------------------------------------------
    # Scenario U: Example 23 Defense (Never inject test harnesses into production files)
    # -------------------------------------------------------------
    diff_u = "--- a/app/orchestrator.py\n+++ b/app/orchestrator.py\n@@ -1,3 +1,6 @@\n+import unittest\n+self.assertEqual(1, 1)\n def run():\n     pass"
    val_u, _ = validate_diff(diff_u, "app/orchestrator.py", ["app/orchestrator.py"])
    pass_u = not val_u  # Successfully rejected because production code cannot have test harness injected!
    results.append(("U. Example 23 Defense (Reject test injection in production code)", pass_u, {"val": val_u}))

    # -------------------------------------------------------------
    # Scenario V: Generic Root Cause Rejection
    # -------------------------------------------------------------
    pred_v = predictor.parse_prediction(
        "### Failure Category:\nDependency Error\n### Root Cause Analysis:\nNo test source available.",
        impl_file="app/main.py",
        repair_target_type="DEPENDENCY",
        repo_files=["app/main.py", "requirements.txt"],
        language="Python",
        failure_log="ModuleNotFoundError: No module named 'flask'"
    )
    pass_v = "no test source available" not in pred_v["root_cause"].lower() and "package" in pred_v["root_cause"].lower()
    results.append(("V. Generic root cause rejection & technical enrichment", pass_v, pred_v["root_cause"]))

    # -------------------------------------------------------------
    # Summary Table
    # -------------------------------------------------------------
    print("\n" + "=" * 75)
    print(f"{'#':<3} | {'Scenario':<52} | {'Status':<8}")
    print("-" * 75)
    all_passed = True
    for idx, (name, passed, detail) in enumerate(results, 1):
        status_str = "✅ PASS" if passed else "❌ FAIL"
        if not passed:
            all_passed = False
        print(f"{idx:<3} | {name:<52} | {status_str}")

    print("=" * 75)
    print(f"Total: {len(results)} Scenarios | Passed: {sum(1 for _, p, _ in results if p)}/{len(results)}")
    if all_passed:
        print("🎯 ALL 22 ACCEPTANCE CRITERIA PASSED WITH 100% SUCCESS!")
    else:
        print("⚠️ Some acceptance tests failed.")
    print("=" * 75 + "\n")
    return all_passed


if __name__ == "__main__":
    success = run_acceptance_tests()
    sys.exit(0 if success else 1)
