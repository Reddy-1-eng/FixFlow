"""
BuildFail-SLM Acceptance Test Suite:
Root-Cause-to-Fix Consistency Validation Stage (Rules 1-19)
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.analyzer import validate_root_cause_fix_consistency
from backend.predictor import BuildFailPredictor
from backend.schemas import FailureDiagnosisResponse


def test_user_example_duplicate_log_inconsistent():
    """
    User's exact example:
    Root Cause: AssertionError: body["total"] == 100.0 + jitter
    Repair Target: tools/check_duplicates.py
    Proposed Fix: A change related to duplicate-log detection/evaluation.
    Expected: Inconsistent.
    """
    diff = """--- a/tools/check_duplicates.py
+++ b/tools/check_duplicates.py
@@ -10,3 +10,5 @@
 def check_duplicates(logs):
+    seen = set()
+    return [x for x in logs if not (x in seen or seen.add(x))]
"""
    status, reason = validate_root_cause_fix_consistency(
        failure_type="Test Failure",
        root_cause='AssertionError: body["total"] == 100.0 + jitter',
        actual_repair_target="tools/check_duplicates.py",
        repair_type="Source Code",
        proposed_fix=diff,
        evidence={"assertion_stmt": 'assert body["total"] == 100.0 + jitter'}
    )
    print(f"\n[Test 1 User Example] Status: {status} | Reason: {reason}")
    assert status == "Inconsistent", f"Expected Inconsistent, got {status}"
    assert "symbols" in reason.lower() or "does not address" in reason.lower()
    print("=> TEST 1 PASSED!")


def test_consistent_test_failure_fix():
    """
    Consistent fix modifying total calculation with jitter in cart.py.
    """
    diff = """--- a/src/cart.py
+++ b/src/cart.py
@@ -25,3 +25,3 @@
-    total = base_price
+    total = base_price + jitter
     return total
"""
    status, reason = validate_root_cause_fix_consistency(
        failure_type="Test Failure",
        root_cause='AssertionError: body["total"] == 100.0 + jitter',
        actual_repair_target="src/cart.py",
        repair_type="Source Code",
        proposed_fix=diff,
        evidence={"assertion_stmt": 'assert body["total"] == 100.0 + jitter', "failing_symbol": "total"}
    )
    print(f"\n[Test 2 Consistent Test Failure Fix] Status: {status} | Reason: {reason}")
    assert status == "Consistent", f"Expected Consistent, got {status}"
    print("=> TEST 2 PASSED!")


def test_target_mismatch_inconsistent():
    """
    Diff modifies a file that does not match actual repair target.
    """
    diff = """--- a/tools/check_duplicates.py
+++ b/tools/check_duplicates.py
@@ -10,3 +10,4 @@
 def check_duplicates(logs):
+    pass
"""
    status, reason = validate_root_cause_fix_consistency(
        failure_type="Test Failure",
        root_cause='AssertionError: body["total"] == 100.0 + jitter',
        actual_repair_target="src/cart.py",
        repair_type="Source Code",
        proposed_fix=diff
    )
    print(f"\n[Test 3 Target Mismatch] Status: {status} | Reason: {reason}")
    assert status == "Inconsistent", f"Expected Inconsistent, got {status}"
    assert "tools/check_duplicates.py" in reason
    assert "src/cart.py" in reason
    print("=> TEST 3 PASSED!")


def test_dependency_error_modifying_source_inconsistent():
    """
    Dependency Error proposing code changes to test or app code instead of manifest.
    """
    diff = """--- a/tests/test_cart.py
+++ b/tests/test_cart.py
@@ -1,3 +1,3 @@
-import langchain_core
+# removed import
"""
    status, reason = validate_root_cause_fix_consistency(
        failure_type="Dependency Error",
        root_cause="ModuleNotFoundError: No module named 'langchain_core'",
        actual_repair_target="requirements.txt",
        repair_type="Dependency",
        proposed_fix=diff
    )
    print(f"\n[Test 4 Dependency Code Change] Status: {status} | Reason: {reason}")
    assert status == "Inconsistent", f"Expected Inconsistent, got {status}"
    assert "manifest" in reason.lower() or "application/test code" in reason.lower()
    print("=> TEST 4 PASSED!")


def test_dependency_error_correct_manifest():
    """
    Dependency Error declaring missing package in requirements.txt.
    """
    diff = """--- a/requirements.txt
+++ b/requirements.txt
@@ -1,1 +1,2 @@
 pytest>=7.0
+langchain-core>=0.1.0
"""
    status, reason = validate_root_cause_fix_consistency(
        failure_type="Dependency Error",
        root_cause="ModuleNotFoundError: No module named 'langchain_core'",
        actual_repair_target="requirements.txt",
        repair_type="Dependency",
        proposed_fix=diff
    )
    print(f"\n[Test 5 Dependency Correct Manifest] Status: {status} | Reason: {reason}")
    assert status == "Consistent", f"Expected Consistent, got {status}"
    print("=> TEST 5 PASSED!")


def test_dependency_error_wrong_package():
    """
    Dependency Error adding unrelated package instead of diagnosed missing package.
    """
    diff = """--- a/requirements.txt
+++ b/requirements.txt
@@ -1,1 +1,2 @@
 pytest>=7.0
+requests>=2.28.0
"""
    status, reason = validate_root_cause_fix_consistency(
        failure_type="Dependency Error",
        root_cause="ModuleNotFoundError: No module named 'langchain_core'",
        actual_repair_target="requirements.txt",
        repair_type="Dependency",
        proposed_fix=diff
    )
    print(f"\n[Test 6 Dependency Wrong Package] Status: {status} | Reason: {reason}")
    assert status == "Inconsistent", f"Expected Inconsistent, got {status}"
    assert "langchain_core" in reason.lower() or "missing package" in reason.lower()
    print("=> TEST 6 PASSED!")


def test_environment_error_modifying_source():
    """
    Environment Error proposing application code edit instead of config/env.
    """
    diff = """--- a/src/db.py
+++ b/src/db.py
@@ -5,2 +5,2 @@
-    url = os.environ["DATABASE_URL"]
+    url = "sqlite://"
"""
    status, reason = validate_root_cause_fix_consistency(
        failure_type="Environment Error",
        root_cause="KeyError: 'DATABASE_URL'",
        actual_repair_target=".env.example",
        repair_type="Environment",
        proposed_fix=diff
    )
    print(f"\n[Test 7 Environment Error Source Edit] Status: {status} | Reason: {reason}")
    assert status == "Inconsistent", f"Expected Inconsistent, got {status}"
    print("=> TEST 7 PASSED!")


def test_environment_error_actionable_remediation():
    """
    Environment Error with actionable remediation.
    """
    remediation = "Actionable Remediation: Configure required environment variables (DATABASE_URL) in CI workflow settings or .env file."
    status, reason = validate_root_cause_fix_consistency(
        failure_type="Environment Error",
        root_cause="KeyError: 'DATABASE_URL'",
        actual_repair_target=".env.example",
        repair_type="Environment",
        proposed_fix=remediation
    )
    print(f"\n[Test 8 Environment Error Remediation] Status: {status} | Reason: {reason}")
    assert status == "Consistent", f"Expected Consistent, got {status}"
    print("=> TEST 8 PASSED!")


def test_test_failure_modifying_test_inconsistent():
    """
    Test Failure: diff modifies test code instead of implementation when implementation is wrong.
    """
    diff = """--- a/tests/test_cart.py
+++ b/tests/test_cart.py
@@ -10,3 +10,3 @@
-    assert body["total"] == 100.0 + jitter
+    assert True
"""
    status, reason = validate_root_cause_fix_consistency(
        failure_type="Test Failure",
        root_cause='AssertionError: body["total"] == 100.0 + jitter',
        actual_repair_target="tests/test_cart.py",
        repair_type="Source Code",
        proposed_fix=diff,
        test_vs_implementation="TEST CORRECT / IMPLEMENTATION WRONG"
    )
    print(f"\n[Test 9 Test Failure Modifying Test] Status: {status} | Reason: {reason}")
    assert status == "Inconsistent", f"Expected Inconsistent, got {status}"
    assert "test code" in reason.lower()
    print("=> TEST 9 PASSED!")


def test_code_error_consistency():
    """
    Code Error (TypeError) with implementation fix.
    """
    diff = """--- a/src/utils.py
+++ b/src/utils.py
@@ -15,3 +15,3 @@
-    return prefix + count
+    return prefix + str(count)
"""
    status, reason = validate_root_cause_fix_consistency(
        failure_type="Code Error",
        root_cause="TypeError: can only concatenate str (not 'int') to str in prefix + count",
        actual_repair_target="src/utils.py",
        repair_type="Source Code",
        proposed_fix=diff
    )
    print(f"\n[Test 10 Code Error Consistent] Status: {status} | Reason: {reason}")
    assert status == "Consistent", f"Expected Consistent, got {status}"
    print("=> TEST 10 PASSED!")


def test_infrastructure_error_source_edit():
    """
    Infrastructure Error proposing application source edits.
    """
    diff = """--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,2 @@
-app = App()
+app = None
"""
    status, reason = validate_root_cause_fix_consistency(
        failure_type="Infrastructure Error",
        root_cause="GitHub Actions runner exceeded memory limit OOMKilled",
        actual_repair_target=".github/workflows/ci.yml",
        repair_type="Infrastructure",
        proposed_fix=diff
    )
    print(f"\n[Test 11 Infra Error Source Edit] Status: {status} | Reason: {reason}")
    assert status == "Inconsistent", f"Expected Inconsistent, got {status}"
    print("=> TEST 11 PASSED!")


def test_rule_10_patch_applicability_does_not_override_inconsistency():
    """
    Rule 10: Do NOT consider a patch correct merely because git apply succeeds.
    Predictor parse_prediction must reject inconsistent patch even if syntactically valid.
    """
    predictor = BuildFailPredictor()
    model_output = """### Failure Category:
Test Failure

### Technical Root Cause:
AssertionError: body["total"] == 100.0 + jitter

### Target Repair File:
tools/check_duplicates.py

### Unified Git Diff:
```diff
--- a/tools/check_duplicates.py
+++ b/tools/check_duplicates.py
@@ -10,3 +10,4 @@
 def check_duplicates(logs):
+    seen = set()
```
"""
    prediction = predictor.parse_prediction(
        model_output,
        default_file="tools/check_duplicates.py",
        failure_location="tests/test_cart.py",
        repo_files=["tools/check_duplicates.py", "tests/test_cart.py", "src/cart.py"],
        failure_log='AssertionError: body["total"] == 100.0 + jitter\n> assert body["total"] == 100.0 + jitter'
    )

    print(f"\n[Test 12 Rule 10 Inconsistent Patch Enforcement]")
    print(f"  Consistency:          {prediction.get('consistency')}")
    print(f"  Consistency Reason:   {prediction.get('consistency_reason')}")
    print(f"  Diff Validation:      {prediction.get('diff_validation')}")
    print(f"  Patch Applicability:  {prediction.get('patch_applicability')}")
    print(f"  is_repaired:          {prediction.get('is_repaired')}")
    print(f"  Confidence:           {prediction.get('confidence')}")

    assert prediction["consistency"] == "Inconsistent", f"Expected Inconsistent, got {prediction['consistency']}"
    assert prediction["is_repaired"] is False, "Must not be reported as repaired when inconsistent"
    assert prediction["patch_applicability"] in ("Failed", "Not Run"), f"Applicability must be Failed or Not Run, got {prediction['patch_applicability']}"
    assert prediction["confidence"] == "Low"
    print("=> TEST 12 PASSED!")


def test_strict_13_field_output_contract():
    """
    Verify the final response complies with the complete 13-field output contract.
    """
    predictor = BuildFailPredictor()
    model_output = """### Failure Category:
Dependency Error

### Technical Root Cause:
The test module requires 'langchain_core' which is missing from requirements.txt.

### Target Repair File:
requirements.txt

### Unified Git Diff:
```diff
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,1 +1,2 @@
 pytest>=7.0
+langchain-core>=0.1.0
```

### Recommended Remediation:
pip install -r requirements.txt && pytest
"""
    prediction = predictor.parse_prediction(
        model_output,
        default_file="requirements.txt",
        failure_location="samples/demo_repo/tests/test_cart.py",
        repo_files=["requirements.txt", "samples/demo_repo/tests/test_cart.py"],
        failure_log="ModuleNotFoundError: No module named 'langchain_core'"
    )

    resp = FailureDiagnosisResponse(
        repository="demo/repo",
        language="Python",
        ci_workflow="CI",
        failure_type=prediction["failure_type"],
        root_cause=prediction["root_cause"],
        source_file=prediction["source_file"],
        failure_location=prediction["failure_location"],
        repair_target_type=prediction["repair_target_type"],
        repair_type=prediction["repair_type"],
        test_vs_implementation=prediction.get("test_vs_implementation"),
        proposed_diff=prediction["proposed_diff"],
        consistency=prediction.get("consistency"),
        consistency_reason=prediction.get("consistency_reason"),
        diff_validation=prediction.get("diff_validation"),
        patch_verification=prediction.get("patch_verification"),
        patch_applicability=prediction.get("patch_applicability"),
        verification=prediction["verification"],
        verification_result=prediction.get("verification_result", "Not Run"),
        confidence=prediction["confidence"],
        is_repaired=prediction["is_repaired"],
        diff_valid=prediction.get("diff_valid", False)
    )

    print("\n[Test 13 13-Field User Output Contract Validation]")
    print(f"1.  Failure Type:              {resp.failure_type}")
    print(f"2.  Root Cause:                {resp.root_cause}")
    print(f"3.  Observed Failure Location: {resp.failure_location}")
    print(f"4.  Actual Repair Target:      {resp.source_file}")
    print(f"5.  Repair Type:               {resp.repair_type}")
    print(f"6.  Proposed Fix:              \n{resp.proposed_diff}")
    print(f"7.  Diagnosis-Fix Consistency: {resp.consistency}")
    print(f"8.  Consistency Reason:        {resp.consistency_reason}")
    print(f"9.  Diff Validation:           {resp.diff_validation}")
    print(f"10. Patch Applicability:       {resp.patch_applicability}")
    print(f"11. Verification:              {resp.verification}")
    print(f"12. Verification Result:       {resp.verification_result}")
    print(f"13. Confidence:                {resp.confidence}")

    assert resp.failure_type == "Dependency Error"
    assert resp.failure_location == "samples/demo_repo/tests/test_cart.py"
    assert resp.source_file == "requirements.txt"
    assert resp.repair_type == "Dependency"
    assert resp.consistency == "Consistent"
    assert resp.diff_validation == "Valid"
    assert resp.confidence == "High"
    print("=> TEST 13 PASSED!")


if __name__ == "__main__":
    print("="*70)
    print("RUNNING ROOT-CAUSE-TO-FIX CONSISTENCY ACCEPTANCE TEST SUITE")
    print("="*70)

    test_user_example_duplicate_log_inconsistent()
    test_consistent_test_failure_fix()
    test_target_mismatch_inconsistent()
    test_dependency_error_modifying_source_inconsistent()
    test_dependency_error_correct_manifest()
    test_dependency_error_wrong_package()
    test_environment_error_modifying_source()
    test_environment_error_actionable_remediation()
    test_test_failure_modifying_test_inconsistent()
    test_code_error_consistency()
    test_infrastructure_error_source_edit()
    test_rule_10_patch_applicability_does_not_override_inconsistency()
    test_strict_13_field_output_contract()

    print("\n" + "="*70)
    print("SUCCESS: ALL 13 CONSISTENCY VALIDATION ACCEPTANCE TESTS PASSED WITH 100% SUCCESS!")
    print("="*70)
