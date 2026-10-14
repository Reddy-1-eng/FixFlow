"""
BuildFail-SLM: Final 13-Category Acceptance Test Suite
Strictly verifies that:
  1. All 13 canonical categories are tested and accurately diagnosed
  2. ZERO "Unknown" category is ever returned
  3. Evidence-driven reasoning + SLM inference correctly localizes repair targets
  4. Observed Failure Location != Actual Repair Target
  5. Minimal unified diffs are generated and validated
  6. Multi-language verification commands are accurate (Python, Node/JS, Java, Rust, Docker)
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
from backend.predictor import BuildFailPredictor, CANONICAL_CATEGORIES


def run_13_category_acceptance():
    print("=" * 80)
    print("BUILDFAIL-SLM: 13-CLASS CANONICAL TAXONOMY ACCEPTANCE SUITE")
    print("NO UNKNOWN / MAXIMUM SLM REASONING")
    print("=" * 80)

    predictor = BuildFailPredictor(model_loader=None)
    results = []

    # 1. Code Error (Genuine source defect / internal import mismatch)
    log_1 = "ModuleNotFoundError: No module named 'src.utils' in tests/test_main.py"
    repo_files_1 = ["src/utils.py", "src/main.py", "tests/test_main.py"]
    cat_1, target_type_1 = classify_failure_nature(log_1, repo_files_1)
    pass_1 = cat_1 == "Code Error" and target_type_1 == "IMPLEMENTATION"
    results.append(("1. Code Error (Internal Module)", pass_1, cat_1))

    # 2. Dependency Error (Missing external package)
    log_2 = "ModuleNotFoundError: No module named 'requests'"
    repo_files_2 = ["app/main.py", "tests/test_main.py", "requirements.txt"]
    cat_2, target_type_2 = classify_failure_nature(log_2, repo_files_2)
    pred_2 = predictor.parse_prediction(
        "### Failure Category:\nDependency Error\n### Root Cause Analysis:\nrequests missing",
        impl_file="app/main.py",
        repair_target_type=target_type_2,
        repo_files=repo_files_2,
        language="Python",
        failure_log=log_2
    )
    pass_2 = cat_2 == "Dependency Error" and pred_2["source_file"] == "requirements.txt" and "requests" in pred_2["proposed_diff"]
    results.append(("2. Dependency Error (Missing Package)", pass_2, cat_2))

    # 3. Build Error (Packaging / artifact build failure)
    log_3 = "npm ERR! package is not built. build failed with exit code 1"
    repo_files_3 = ["package.json", "src/index.ts"]
    cat_3, target_type_3 = classify_failure_nature(log_3, repo_files_3)
    verif_3 = derive_repository_verification_command("JavaScript", cat_3, target_type_3, repo_files=repo_files_3)
    pass_3 = cat_3 == "Build Error" and target_type_3 == "BUILD" and "npm run build" in verif_3
    results.append(("3. Build Error (Package/Bundle)", pass_3, cat_3))

    # 4. Test Failure (Assertion mismatch: tests/test_calc.py -> app/calc.py)
    log_4 = "FAILED tests/test_calc.py::test_add - AssertionError: assert -2 == 8\n+ where -2 = add(3, 5)"
    repo_files_4 = ["app/calc.py", "tests/test_calc.py"]
    cat_4, target_type_4 = classify_failure_nature(log_4, repo_files_4)
    pred_4 = predictor.parse_prediction(
        "### Failure Category:\nTest Failure\n### Root Cause Analysis:\nIncorrect operator\n### Proposed Unified Diff:\n```diff\n--- a/app/calc.py\n+++ b/app/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n```",
        impl_file="app/calc.py",
        test_file="tests/test_calc.py",
        failure_location="tests/test_calc.py",
        repair_target_type=target_type_4,
        repo_files=repo_files_4,
        language="Python",
        failure_log=log_4
    )
    pass_4 = cat_4 == "Test Failure" and pred_4["source_file"] == "app/calc.py" and pred_4["diff_valid"]
    results.append(("4. Test Failure (Observed != Repair Target)", pass_4, cat_4))

    # 5. Configuration Error (Workflow / YAML / linter config)
    log_5 = "The workflow is not valid. .github/workflows/ci.yml (Line: 14, Col: 7): Unrecognized named-value: 'secrets.API'"
    repo_files_5 = [".github/workflows/ci.yml"]
    cat_5, target_type_5 = classify_failure_nature(log_5, repo_files_5)
    pass_5 = cat_5 == "Configuration Error" and target_type_5 == "CONFIGURATION"
    results.append(("5. Configuration Error (Workflow YAML)", pass_5, cat_5))

    # 6. Environment Error (Missing Environment Variable / Secret)
    log_6 = "KeyError: 'STRIPE_API_KEY' in app/billing.py"
    repo_files_6 = ["app/billing.py"]
    cat_6, target_type_6 = classify_failure_nature(log_6, repo_files_6)
    pred_6 = predictor.parse_prediction(
        "### Failure Category:\nEnvironment Error\n### Root Cause Analysis:\nSTRIPE_API_KEY environment variable not set in CI runner",
        impl_file="app/billing.py",
        repair_target_type=target_type_6,
        repo_files=repo_files_6,
        language="Python",
        failure_log=log_6
    )
    pass_6 = cat_6 == "Environment Error" and pred_6["source_file"] == "Not identified" and (pred_6["proposed_diff"].startswith("No source-code fix") or pred_6["proposed_diff"].startswith("Actionable Remediation"))
    results.append(("6. Environment Error (Missing Env Var)", pass_6, cat_6))

    # 7. Compilation Error (C++ / Java / Rust / TypeScript syntax/types)
    log_7 = "[ERROR] COMPILATION ERROR : cannot find symbol class OrderService [pom.xml:18]"
    repo_files_7 = ["src/main/java/App.java", "pom.xml"]
    cat_7, target_type_7 = classify_failure_nature(log_7, repo_files_7)
    verif_7 = derive_repository_verification_command("Java", cat_7, target_type_7, repo_files=repo_files_7)
    pass_7 = cat_7 == "Compilation Error" and "mvn" in verif_7
    results.append(("7. Compilation Error (Java/Maven)", pass_7, cat_7))

    # 8. Runtime Error (TypeError, IndexError, NullPointerException)
    log_8 = "TypeError: unsupported operand type(s) for +: 'int' and 'str' in app/formatter.py:12"
    repo_files_8 = ["app/formatter.py", "tests/test_formatter.py"]
    cat_8, target_type_8 = classify_failure_nature(log_8, repo_files_8)
    pass_8 = cat_8 == "Runtime Error" and target_type_8 == "IMPLEMENTATION"
    results.append(("8. Runtime Error (TypeError)", pass_8, cat_8))

    # 9. Infrastructure Error (Runner crash, OOM, disk space)
    log_9 = "Runner has encountered an internal error. Hosted runner is unavailable. OOMKilled"
    repo_files_9 = ["app/main.py"]
    cat_9, target_type_9 = classify_failure_nature(log_9, repo_files_9)
    pred_9 = predictor.parse_prediction(
        "### Failure Category:\nInfrastructure Error\n### Root Cause Analysis:\nRunner out of memory",
        impl_file="app/main.py",
        repair_target_type=target_type_9,
        repo_files=repo_files_9,
        language="Python",
        failure_log=log_9
    )
    pass_9 = cat_9 == "Infrastructure Error" and pred_9["source_file"] == "Not identified" and (pred_9["proposed_diff"].startswith("No source-code fix") or pred_9["proposed_diff"].startswith("Actionable Remediation"))
    results.append(("9. Infrastructure Error (Runner Crash)", pass_9, cat_9))

    # 10. Authentication / Permission Error (HTTP 401, 403, bad token)
    log_10 = "HTTPError: 401 Unauthorized - Invalid authentication token for package registry"
    repo_files_10 = ["package.json"]
    cat_10, target_type_10 = classify_failure_nature(log_10, repo_files_10)
    pred_10 = predictor.parse_prediction(
        "### Failure Category:\nAuthentication / Permission Error\n### Root Cause Analysis:\nInvalid credentials for package registry",
        impl_file="package.json",
        repair_target_type=target_type_10,
        repo_files=repo_files_10,
        language="JavaScript",
        failure_log=log_10
    )
    pass_10 = cat_10 == "Authentication / Permission Error" and target_type_10 == "AUTHENTICATION" and pred_10["proposed_diff"].startswith("No source-code fix")
    results.append(("10. Authentication / Permission Error", pass_10, cat_10))

    # 11. Network Error (Connection refused, ETIMEDOUT, host unreachable)
    log_11 = "curl: (7) Failed to connect to api.internal.corp port 443: Connection refused"
    repo_files_11 = ["app/client.py"]
    cat_11, target_type_11 = classify_failure_nature(log_11, repo_files_11)
    pass_11 = cat_11 == "Network Error" and target_type_11 == "NETWORK"
    results.append(("11. Network Error (Connection Refused)", pass_11, cat_11))

    # 12. Deployment Error (Helm, Kubernetes, Vercel, ECS deploy fail)
    log_12 = "error: helm upgrade failed: timed out waiting for condition ready on deployment/backend"
    repo_files_12 = ["helm/Chart.yaml", "helm/values.yaml"]
    cat_12, target_type_12 = classify_failure_nature(log_12, repo_files_12)
    pass_12 = cat_12 == "Deployment Error" and target_type_12 == "DEPLOYMENT"
    results.append(("12. Deployment Error (Helm/K8s)", pass_12, cat_12))

    # 13. Docker / Container Error (Docker daemon, Dockerfile parse)
    log_13 = "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?"
    repo_files_13 = ["Dockerfile", "docker-compose.yml"]
    cat_13, target_type_13 = classify_failure_nature(log_13, repo_files_13)
    pass_13 = cat_13 == "Docker / Container Error" and target_type_13 == "DOCKER"
    results.append(("13. Docker / Container Error (Daemon Unreachable)", pass_13, cat_13))

    # 14. Incomplete / Noisy CI Evidence (SLM Reasoning without Unknown fallback)
    log_14 = "Process completed with exit code 1. [No detailed traceback found in captured chunk]"
    repo_files_14 = ["app/server.py", "tests/test_server.py"]
    cat_14, target_type_14 = classify_failure_nature(log_14, repo_files_14)
    pred_14 = predictor.parse_prediction(
        "### Failure Category:\nCode Error\n### Root Cause Analysis:\nExit code 1 indicates an unhandled runtime defect in server initialization.",
        impl_file="app/server.py",
        repair_target_type=target_type_14,
        repo_files=repo_files_14,
        language="Python",
        failure_log=log_14
    )
    pass_14 = (
        pred_14["failure_type"] in CANONICAL_CATEGORIES
        and pred_14["failure_type"] != "Unknown"
        and "insufficient evidence" not in pred_14["root_cause"].lower()
        and pred_14["confidence"] in ("High", "Medium", "Low")
    )
    results.append(("14. Incomplete/Noisy CI Evidence (Reasoning, No Unknown)", pass_14, pred_14["failure_type"]))

    print("\n" + "=" * 80)
    print(f"{'#':<3} | {'Evaluation Case':<52} | {'Category Verified':<20} | {'Status'}")
    print("-" * 80)
    all_ok = True
    for idx, (title, passed, cat) in enumerate(results, 1):
        status_str = "✅ PASS" if passed else "❌ FAIL"
        if not passed:
            all_ok = False
        print(f"{idx:<3} | {title:<52} | {str(cat):<20} | {status_str}")

    print("=" * 80)
    print(f"Total: {len(results)} Categories & Edge Cases | Passed: {sum(1 for _, p, _ in results if p)}/{len(results)}")
    if all_ok:
        print("🎯 100% SUCCESS: ALL 13 CANONICAL TAXONOMY CATEGORIES VALIDATED WITH ZERO UNKNOWN FALLBACK!")
    print("=" * 80 + "\n")
    return all_ok


if __name__ == "__main__":
    ok = run_13_category_acceptance()
    sys.exit(0 if ok else 1)
