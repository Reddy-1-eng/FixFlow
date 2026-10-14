"""
BuildFail-SLM Final Acceptance Test Suite:
Validates the 5 mandatory final scenarios requested by the user:
1. A healthy repository.
2. A dependency failure where localization and repair target differ.
3. A test/code failure where localization and repair target may be different.
4. A failure where both are correctly the same.
5. A bad unrelated patch that applies but must be rejected as semantically invalid.
"""

import sys
import tempfile
import shutil
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.predictor import BuildFailPredictor
from backend.analyzer import (
    determine_actual_repair_target,
    validate_root_cause_fix_consistency,
    check_patch_applicability_and_semantic_verify
)
from backend.schemas import FailureDiagnosisResponse


def test_1_healthy_repository():
    """
    1. A healthy repository with no CI/CD failure:
    Failure Type: None
    Root Cause: No CI/CD failure detected.
    Fault Localization: Not identified
    Actual Repair Target: Not identified
    Proposed Fix: No source-code fix proposed.
    Patch Applicability: Not Run
    Verification Result: Not Run
    """
    print("\n" + "=" * 60)
    print("TEST 1: Healthy Repository (No CI/CD Failure)")
    print("=" * 60)

    predictor = BuildFailPredictor()
    prediction = predictor.parse_prediction(
        raw_output="### Failure Category:\nNone\n### Root Cause Analysis:\nNo CI/CD failure detected.",
        default_file="Not identified",
        repair_target_type="NONE",
        repo_files=["src/main.py", "tests/test_main.py"],
        failure_log="All tests passed successfully (0 failures)."
    )

    resp = FailureDiagnosisResponse(
        repository="user/healthy-repo",
        language="Python",
        ci_workflow="CI",
        failure_type=prediction["failure_type"],
        root_cause=prediction["root_cause"],
        source_file=prediction["source_file"],
        actual_repair_target=prediction["actual_repair_target"],
        failure_location=prediction["failure_location"],
        fault_localization=prediction["fault_localization"],
        repair_type=prediction["repair_type"],
        proposed_diff=prediction["proposed_diff"],
        consistency=prediction["consistency"],
        diff_validation=prediction["diff_validation"],
        patch_applicability=prediction["patch_applicability"],
        semantic_fix_validity=prediction["semantic_fix_validity"],
        verification_result=prediction["verification_result"],
        confidence=prediction["confidence"],
        is_repaired=prediction["is_repaired"]
    )

    print(f"Failure Type:            {resp.failure_type}")
    print(f"Root Cause:              {resp.root_cause}")
    print(f"Fault Localization:      {resp.fault_localization}")
    print(f"Actual Repair Target:    {resp.actual_repair_target}")
    print(f"Proposed Fix:            {resp.proposed_diff}")
    print(f"Patch Applicability:     {resp.patch_applicability}")
    print(f"Verification Result:     {resp.verification_result}")
    print(f"Diff Validation:         {resp.diff_validation}")
    print(f"Semantic Fix Validity:   {resp.semantic_fix_validity}")
    print(f"is_repaired:             {resp.is_repaired}")

    assert resp.failure_type == "None"
    assert resp.root_cause == "No CI/CD failure detected."
    assert resp.fault_localization == "Not identified"
    assert resp.actual_repair_target == "Not identified"
    assert resp.proposed_diff == "No source-code fix proposed."
    assert resp.patch_applicability == "Not Run"
    assert resp.verification_result == "Not Run"
    assert resp.diff_validation == "Not Available"
    assert resp.semantic_fix_validity == "Not Available"
    assert resp.is_repaired is False
    print("=> TEST 1 PASSED: Healthy repository strictly complies with Section 9!")


def test_2_dependency_failure_differing_targets():
    """
    2. A dependency failure where localization and repair target differ:
    Fault Localization: tests/test_cart.py
    Actual Repair Target: requirements.txt
    """
    print("\n" + "=" * 60)
    print("TEST 2: Dependency Failure (Localization != Repair Target)")
    print("=" * 60)

    repo_files = ["tests/test_cart.py", "src/cart.py", "requirements.txt"]
    log = "ModuleNotFoundError: No module named 'requests' in tests/test_cart.py"

    target_file, target_type, rep_type, conf = determine_actual_repair_target(
        failure_type="Dependency Error",
        failure_log=log,
        observed_failure_location="tests/test_cart.py",
        repo_files=repo_files,
        test_file="tests/test_cart.py"
    )

    predictor = BuildFailPredictor()
    model_output = """### Failure Category:
Dependency Error
### Technical Root Cause:
ModuleNotFoundError: No module named 'requests'. Package is missing from requirements.txt.
### Target Repair File:
requirements.txt
### Unified Git Diff:
```diff
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,1 +1,2 @@
 pytest>=7.0
+requests>=2.28.0
```
### Recommended Remediation:
pip install -r requirements.txt && pytest
"""
    prediction = predictor.parse_prediction(
        model_output,
        default_file=target_file,
        failure_location="tests/test_cart.py",
        repo_files=repo_files,
        failure_log=log
    )

    print(f"Fault Localization:   {prediction['fault_localization']}")
    print(f"Actual Repair Target: {prediction['actual_repair_target']}")
    print(f"Repair Type:          {prediction['repair_type']}")
    print(f"Consistency:          {prediction['consistency']}")
    print(f"Diff Validation:      {prediction['diff_validation']}")
    print(f"Semantic Validity:    {prediction['semantic_fix_validity']}")

    assert prediction["fault_localization"] == "tests/test_cart.py"
    assert prediction["actual_repair_target"] == "requirements.txt"
    assert prediction["fault_localization"] != prediction["actual_repair_target"], "Localization and repair target MUST differ!"
    assert prediction["failure_type"] == "Dependency Error"
    assert prediction["repair_type"] == "Dependency"
    assert prediction["consistency"] == "Consistent"
    assert prediction["diff_validation"] == "Valid"
    assert prediction["semantic_fix_validity"] == "Valid"
    print("=> TEST 2 PASSED: Dependency failure correctly separates localization from repair target!")


def test_3_test_failure_differing_targets():
    """
    3. A test/code failure where localization and repair target may be different:
    Fault Localization: tests/test_payment.py
    Actual Repair Target: src/payment.py
    """
    print("\n" + "=" * 60)
    print("TEST 3: Test Failure (Localization != Repair Target)")
    print("=" * 60)

    repo_files = ["tests/test_payment.py", "src/payment.py", "requirements.txt"]
    log = """
    FAILED tests/test_payment.py::test_calculate_total - AssertionError: assert 120 == 100
    + where 120 = calculate_total(100, tax=0.2)
    """

    target_file, target_type, rep_type, conf = determine_actual_repair_target(
        failure_type="Test Failure",
        failure_log=log,
        observed_failure_location="tests/test_payment.py",
        repo_files=repo_files,
        test_file="tests/test_payment.py",
        impl_file="src/payment.py"
    )

    predictor = BuildFailPredictor()
    model_output = """### Failure Category:
Test Failure
### Technical Root Cause:
calculate_total in src/payment.py incorrectly adds tax to base amount when tax is inclusive, returning 120 instead of expected 100.
### Target Repair File:
src/payment.py
### Unified Git Diff:
```diff
--- a/src/payment.py
+++ b/src/payment.py
@@ -10,3 +10,3 @@
 def calculate_total(amount, tax=0.0):
-    return amount * (1.0 + tax)
+    return amount
```
### Recommended Remediation:
pytest tests/test_payment.py
"""
    prediction = predictor.parse_prediction(
        model_output,
        impl_file=target_file,
        test_file="tests/test_payment.py",
        failure_location="tests/test_payment.py",
        repo_files=repo_files,
        failure_log=log,
        evidence={"assertion_stmt": "assert calculate_total(100, tax=0.2) == 100", "failing_symbol": "calculate_total"}
    )

    print(f"Fault Localization:   {prediction['fault_localization']}")
    print(f"Actual Repair Target: {prediction['actual_repair_target']}")
    print(f"Repair Type:          {prediction['repair_type']}")
    print(f"Consistency:          {prediction['consistency']}")
    print(f"Diff Validation:      {prediction['diff_validation']}")
    print(f"Semantic Validity:    {prediction['semantic_fix_validity']}")

    assert prediction["fault_localization"] == "tests/test_payment.py"
    assert prediction["actual_repair_target"] == "src/payment.py"
    assert prediction["fault_localization"] != prediction["actual_repair_target"], "Localization and repair target MUST differ!"
    assert prediction["failure_type"] == "Test Failure"
    assert prediction["repair_type"] == "Source Code"
    assert prediction["consistency"] == "Consistent"
    assert prediction["diff_validation"] == "Valid"
    assert prediction["semantic_fix_validity"] == "Valid"
    print("=> TEST 3 PASSED: Test failure correctly exposes defect in implementation!")


def test_4_failure_where_both_are_same():
    """
    4. A failure where both are correctly the same:
    Fault Localization: src/payment.py
    Actual Repair Target: src/payment.py
    """
    print("\n" + "=" * 60)
    print("TEST 4: Code Error (Localization == Repair Target)")
    print("=" * 60)

    repo_files = ["src/payment.py", "tests/test_payment.py", "requirements.txt"]
    log = """
    Traceback (most recent call last):
      File "src/payment.py", line 42, in process_charge
        rate = 100 / divisor
    ZeroDivisionError: division by zero
    """

    target_file, target_type, rep_type, conf = determine_actual_repair_target(
        failure_type="Code Error",
        failure_log=log,
        observed_failure_location="src/payment.py",
        repo_files=repo_files,
        impl_file="src/payment.py"
    )

    predictor = BuildFailPredictor()
    model_output = """### Failure Category:
Code Error
### Technical Root Cause:
ZeroDivisionError in src/payment.py line 42 when divisor is 0.
### Target Repair File:
src/payment.py
### Unified Git Diff:
```diff
--- a/src/payment.py
+++ b/src/payment.py
@@ -41,3 +41,4 @@
 def process_charge(amount, divisor):
+    if divisor == 0: return 0
     rate = 100 / divisor
```
### Recommended Remediation:
pytest
"""
    prediction = predictor.parse_prediction(
        model_output,
        impl_file=target_file,
        failure_location="src/payment.py",
        repo_files=repo_files,
        failure_log=log,
        evidence={"error_type": "ZeroDivisionError", "failing_symbol": "process_charge"}
    )

    print(f"Fault Localization:   {prediction['fault_localization']}")
    print(f"Actual Repair Target: {prediction['actual_repair_target']}")
    print(f"Repair Type:          {prediction['repair_type']}")
    print(f"Consistency:          {prediction['consistency']}")
    print(f"Diff Validation:      {prediction['diff_validation']}")
    print(f"Semantic Validity:    {prediction['semantic_fix_validity']}")

    assert prediction["fault_localization"] == "src/payment.py"
    assert prediction["actual_repair_target"] == "src/payment.py"
    assert prediction["fault_localization"] == prediction["actual_repair_target"], "Localization and repair target MUST be the same!"
    assert prediction["failure_type"] == "Code Error"
    assert prediction["repair_type"] == "Source Code"
    assert prediction["consistency"] == "Consistent"
    assert prediction["diff_validation"] == "Valid"
    assert prediction["semantic_fix_validity"] == "Valid"
    print("=> TEST 4 PASSED: Code failure correctly identifies implementation as both localization and repair target!")


def test_5_bad_unrelated_patch_rejected_semantically():
    """
    5. A bad unrelated patch that applies cleanly but must be rejected as semantically invalid:
    Root Cause: AssertionError involving body["total"] and jitter
    Proposed Fix: Only changes a documentation string / comment in payment.py.
    Expected:
    Diff Validation: Valid
    Patch Applicability: Passed
    Diagnosis-Fix Consistency: Inconsistent
    Semantic Fix Validity: Invalid
    Verification Result: Not Run
    """
    print("\n" + "=" * 60)
    print("TEST 5: Bad Unrelated Patch (Applies Cleanly, Rejected Semantically)")
    print("=" * 60)

    temp_dir = tempfile.mkdtemp(prefix="buildfail_test5_")
    try:
        repo_path = Path(temp_dir)
        src_file = repo_path / "src" / "payment.py"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("""# Payment processing module
def calculate_charge(body, jitter):
    return body["total"] + jitter
""", encoding="utf-8")

        diff = """--- a/src/payment.py
+++ b/src/payment.py
@@ -1,3 +1,4 @@
 # Payment processing module
+# Updated documentation comment for payment module
 def calculate_charge(body, jitter):
"""
        # Test dry-run applicability on disk
        diff_v, patch_app, verif_r = check_patch_applicability_and_semantic_verify(
            diff,
            target_file="src/payment.py",
            repo_path=repo_path
        )
        assert diff_v is True, "Diff syntax must be valid"
        assert patch_app is True, "Patch must apply cleanly to src/payment.py on disk"

        predictor = BuildFailPredictor()
        model_output = f"""### Failure Category:
Test Failure
### Technical Root Cause:
AssertionError: body["total"] == 100.0 + jitter. Precision mismatch in total calculation.
### Target Repair File:
src/payment.py
### Unified Git Diff:
```diff
{diff}
```
### Recommended Remediation:
pytest
"""
        prediction = predictor.parse_prediction(
            model_output,
            impl_file="src/payment.py",
            failure_location="tests/test_payment.py",
            repo_files=["src/payment.py", "tests/test_payment.py"],
            repo_path=repo_path,
            failure_log='AssertionError: body["total"] == 100.0 + jitter\n> assert body["total"] == 100.0 + jitter',
            evidence={"assertion_stmt": 'assert body["total"] == 100.0 + jitter', "failing_symbol": "total"}
        )

        print(f"Diff Validation:           {prediction['diff_validation']}")
        print(f"Patch Applicability:       {prediction['patch_applicability']}")
        print(f"Diagnosis-Fix Consistency: {prediction['consistency']}")
        print(f"Consistency Reason:        {prediction['consistency_reason']}")
        print(f"Semantic Fix Validity:     {prediction['semantic_fix_validity']}")
        print(f"Verification Result:       {prediction['verification_result']}")
        print(f"is_repaired:               {prediction['is_repaired']}")

        # EXACT USER SPECIFICATION IN SECTION 6:
        # Diff Validation: Valid
        # Patch Applicability: Passed
        # Diagnosis-Fix Consistency: Inconsistent
        # Semantic Fix Validity: Invalid
        # Verification Result: Not Run
        assert prediction["diff_validation"] == "Valid", f"Expected Valid, got {prediction['diff_validation']}"
        assert prediction["patch_applicability"] == "Passed", f"Expected Passed, got {prediction['patch_applicability']}"
        assert prediction["consistency"] == "Inconsistent", f"Expected Inconsistent, got {prediction['consistency']}"
        assert prediction["semantic_fix_validity"] == "Invalid", f"Expected Invalid, got {prediction['semantic_fix_validity']}"
        assert prediction["verification_result"] == "Not Run", f"Expected Not Run, got {prediction['verification_result']}"
        assert prediction["is_repaired"] is False, "Must NOT be marked as repaired!"
        print("=> TEST 5 PASSED: Bad unrelated patch successfully rejected as semantically invalid despite applying cleanly!")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    print("=" * 70)
    print("RUNNING FINAL USER CRITERIA ACCEPTANCE TEST SUITE")
    print("=" * 70)

    test_1_healthy_repository()
    test_2_dependency_failure_differing_targets()
    test_3_test_failure_differing_targets()
    test_4_failure_where_both_are_same()
    test_5_bad_unrelated_patch_rejected_semantically()

    print("\n" + "=" * 70)
    print("SUCCESS: ALL 5 FINAL ACCEPTANCE TEST SCENARIOS PASSED 100%!")
    print("=" * 70)
