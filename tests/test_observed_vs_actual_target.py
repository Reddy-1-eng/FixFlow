"""
Test suite validating the separation of Observed Failure Location from Actual Repair Target.
"""
import sys
import os
from pathlib import Path

# Ensure workspace root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from backend.analyzer import (
    classify_failure_nature,
    determine_actual_repair_target,
    classify_repair_type,
    locate_faulty_file,
    validate_repository_file
)
from backend.predictor import BuildFailPredictor

def test_user_example_dependency_error():
    """
    Example from user request:
    ModuleNotFoundError: No module named 'langchain_core'
    Observed location: samples/demo_repo/tests/test_cart.py
    Desired:
    Observed Failure Location: samples/demo_repo/tests/test_cart.py
    Actual Repair Target: requirements.txt
    Repair Type: Dependency
    """
    log = """
    Traceback (most recent call last):
      File "samples/demo_repo/tests/test_cart.py", line 4, in <module>
        import langchain_core
    ModuleNotFoundError: No module named 'langchain_core'
    """
    repo_files = [
        "requirements.txt",
        "samples/demo_repo/cart.py",
        "samples/demo_repo/tests/test_cart.py",
        ".github/workflows/ci.yml"
    ]

    inferred_cat, repair_target_type = classify_failure_nature(log, repo_files)
    assert inferred_cat == "Dependency Error", f"Expected Dependency Error, got {inferred_cat}"

    observed = locate_faulty_file(log, repo_files=repo_files)
    assert observed == "samples/demo_repo/tests/test_cart.py", f"Expected observed test file, got {observed}"

    actual_target, r_target_type, r_type, conf = determine_actual_repair_target(
        failure_type=inferred_cat,
        failure_log=log,
        observed_failure_location=observed,
        repo_files=repo_files,
        test_file=observed,
        impl_file="samples/demo_repo/cart.py"
    )

    print(f"\n[Test 1: User Example Dependency Error]")
    print(f"  Observed Failure Location: {observed}")
    print(f"  Actual Repair Target:      {actual_target}")
    print(f"  Repair Type:               {r_type}")
    print(f"  Confidence:                {conf}")

    assert observed != actual_target, "Observed location must NOT equal actual repair target for dependency error!"
    assert actual_target == "requirements.txt", f"Expected requirements.txt, got {actual_target}"
    assert r_type == "Dependency", f"Expected Dependency, got {r_type}"
    print("  => PASSED!")

def test_pyproject_dependency_error():
    """Verify pyproject.toml is selected when requirements.txt does not exist."""
    log = """
    Traceback (most recent call last):
      File "tests/test_auth.py", line 2, in <module>
        from fastapi import FastAPI
    ModuleNotFoundError: No module named 'fastapi'
    """
    repo_files = [
        "pyproject.toml",
        "poetry.lock",
        "auth/service.py",
        "tests/test_auth.py",
        ".github/workflows/test.yml"
    ]
    observed = locate_faulty_file(log, repo_files=repo_files)
    inferred_cat, _ = classify_failure_nature(log, repo_files)

    actual_target, _, r_type, conf = determine_actual_repair_target(
        failure_type=inferred_cat,
        failure_log=log,
        observed_failure_location=observed,
        repo_files=repo_files,
        test_file=observed
    )

    print(f"\n[Test 2: pyproject.toml Dependency Error]")
    print(f"  Observed Failure Location: {observed}")
    print(f"  Actual Repair Target:      {actual_target}")
    print(f"  Repair Type:               {r_type}")

    assert observed == "tests/test_auth.py"
    assert actual_target == "pyproject.toml"
    assert r_type == "Dependency"
    print("  => PASSED!")

def test_environment_error_separation():
    """Environment error surfacing in app code must target .env.example or CI workflow, not app code."""
    log = """
    Traceback (most recent call last):
      File "app/database.py", line 12, in init_db
        db_url = os.environ['DATABASE_URL']
      File ".../os.py", line 679, in __getitem__
        raise KeyError(key) from None
    KeyError: 'DATABASE_URL'
    """
    repo_files = [
        "app/database.py",
        "app/main.py",
        ".env.example",
        ".github/workflows/ci.yml"
    ]
    observed = locate_faulty_file(log, repo_files=repo_files)
    inferred_cat, _ = classify_failure_nature(log, repo_files)

    actual_target, _, r_type, conf = determine_actual_repair_target(
        failure_type=inferred_cat,
        failure_log=log,
        observed_failure_location=observed,
        repo_files=repo_files,
        impl_file=observed
    )

    print(f"\n[Test 3: Environment Error]")
    print(f"  Observed Failure Location: {observed}")
    print(f"  Actual Repair Target:      {actual_target}")
    print(f"  Repair Type:               {r_type}")

    assert observed == "app/database.py"
    assert actual_target == ".env.example"
    assert r_type == "Environment"
    print("  => PASSED!")

def test_test_failure_implementation_wrong():
    """Test failure where implementation is wrong must target implementation, NOT test."""
    log = """
    def test_calculate_total():
    >       assert calculate_total([10, 20]) == 30
    E       AssertionError: assert 25 == 30
    tests/test_cart.py:15: AssertionError
    """
    repo_files = [
        "cart/calculator.py",
        "tests/test_cart.py"
    ]
    observed = "tests/test_cart.py"
    inferred_cat, _ = classify_failure_nature(log, repo_files)

    actual_target, _, r_type, conf = determine_actual_repair_target(
        failure_type=inferred_cat,
        failure_log=log,
        observed_failure_location=observed,
        repo_files=repo_files,
        test_file=observed,
        impl_file="cart/calculator.py",
        test_vs_impl="TEST CORRECT / IMPLEMENTATION WRONG"
    )

    print(f"\n[Test 4: Test Failure - Implementation Wrong]")
    print(f"  Observed Failure Location: {observed}")
    print(f"  Actual Repair Target:      {actual_target}")
    print(f"  Repair Type:               {r_type}")

    assert observed == "tests/test_cart.py"
    assert actual_target == "cart/calculator.py"
    assert r_type == "Source Code"
    print("  => PASSED!")

def test_predictor_parsing_contract():
    """Test predictor parse_prediction output contract."""
    predictor = BuildFailPredictor()
    model_output = """### Failure Category:
Dependency Error

### Root Cause Analysis:
The test module requires 'langchain_core' which is missing from requirements.txt.

### Target Repair File:
requirements.txt

### Proposed Fix:
--- a/requirements.txt
+++ b/requirements.txt
@@ -1 +1,2 @@
+langchain_core

### Recommended Remediation:
pip install -r requirements.txt && pytest
"""
    log = "ModuleNotFoundError: No module named 'langchain_core'\nsamples/demo_repo/tests/test_cart.py:4"
    repo_files = ["requirements.txt", "samples/demo_repo/tests/test_cart.py"]

    res = predictor.parse_prediction(
        raw_output=model_output,
        default_file="requirements.txt",
        test_file="samples/demo_repo/tests/test_cart.py",
        failure_location="samples/demo_repo/tests/test_cart.py",
        repo_files=repo_files,
        failure_log=log
    )

    print(f"\n[Test 5: Predictor Output Contract]")
    print(f"  Failure Type:              {res['failure_type']}")
    print(f"  Root Cause:                {res['root_cause']}")
    print(f"  Observed Failure Location: {res['failure_location']}")
    print(f"  Actual Repair Target:      {res['source_file']}")
    print(f"  Repair Type:               {res['repair_type']}")
    print(f"  Confidence:                {res['confidence']}")
    print(f"  Diff Validation:           {res['patch_verification']}")
    print(f"  Patch Applicability:       {res['patch_applicability']}")
    print(f"  Verification Result:       {res['verification_result']}")

    assert res['failure_type'] == "Dependency Error"
    assert res['failure_location'] == "samples/demo_repo/tests/test_cart.py"
    assert res['source_file'] == "requirements.txt"
    assert res['repair_type'] == "Dependency"
    assert res['failure_type'] != "Unknown"
    print("  => PASSED!")

if __name__ == "__main__":
    test_user_example_dependency_error()
    test_pyproject_dependency_error()
    test_environment_error_separation()
    test_test_failure_implementation_wrong()
    test_predictor_parsing_contract()
    print("\nALL REPAIR TARGET REASONING TESTS PASSED PERFECTLY!")
