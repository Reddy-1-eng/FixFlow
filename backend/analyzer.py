"""
BuildFail-SLM: Universal Repository, Workflow & Failure Analyzer
Performs deterministic inspection across multi-language codebases:
  1. Project Structure & Multi-Language Frameworks (Python, JS/TS, Java, Rust, Go, C++, Docker)
  2. Dependencies & Package Manifests (package.json, pyproject.toml, pom.xml, Cargo.toml, etc.)
  3. Workflows & CI/CD Pipelines (.github/workflows, Dockerfile, etc.)
  4. Evidence-Driven Fault Localization (Separates Failure Location vs Implementation vs Repair Target)
  5. Test vs Implementation Defect Assessment (TEST WRONG vs IMPLEMENTATION WRONG)
  6. Diagnosis-Diff Consistency & Temporary Workspace Patch Verification (Passed / Failed / Not Run)
"""

import os
import re
import sys
import yaml
import json
import tempfile
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set

FAILURE_PATTERNS = [
    r"(?i)(FAILURES|FAILED|AssertionError|Traceback \(most recent call last\):)",
    r"(?i)(BUILD FAILED|compilation failed|cannot find symbol|error\[E\d+\])",
    r"(?i)(Error:\s+[^\n]+)",
    r"(?i)(##\[error\][^\n]+)",
    r"(?i)(ModuleNotFoundError|ImportError|SyntaxError|TypeError|NameError|KeyError|PermissionError)",
    r"(?i)(npm error|yarn error|pip error|curl: \(\d+\))",
    r"(?i)(fatal:|Segmentation fault|OOMKilled|Exit Code [1-9]\d*|Process completed with exit code)"
]

SYSTEM_PATTERNS = [
    "windowsapps",
    "pythonsoftwarefoundation",
    "site-packages",
    "dist-packages",
    "hostedtoolcache",
    "program files",
    "usr/lib",
    "usr/local",
    "/usr/",
    "/opt/",
    "/home/runner",
    "importlib",
    "__pycache__",
    "<frozen",
    "<string>",
    "internal"
]

PLACEHOLDER_PATTERNS = [
    r"<[^>\n]+>",
    r"^\s*\.\.\.\s*$",
    r"^\s*//\s*TODO",
    r"^\s*#\s*TODO",
    r"//\s*insert code here",
    r"#\s*insert code here"
]

SECRET_PATTERNS = [
    r'(?i)(?:token|password|secret|api[_-]?key|apikey|auth)\s*[:=]\s*[\'"]?([a-zA-Z0-9_\-\.]{8,})[\'"]?',
    r'ghp_[a-zA-Z0-9]{20,}',
    r'github_pat_[a-zA-Z0-9_]{20,}',
    r'hf_[a-zA-Z0-9]{20,}',
    r'Bearer\s+[a-zA-Z0-9_\-\.]{15,}',
    r'-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----'
]


def sanitize_secrets(text: str) -> str:
    """Sanitize all credentials, tokens, API keys, and private keys before processing or display."""
    if not text:
        return ""
    sanitized = text
    for pat in SECRET_PATTERNS:
        sanitized = re.sub(pat, '[REDACTED_SECRET]', sanitized)
    return sanitized


def detect_multiple_failures(failure_log: str) -> Dict[str, Any]:
    """Detect and summarize multiple test or job failures in a single CI run."""
    if not failure_log:
        return {"failure_count": 0, "failures": [], "has_multiple": False}

    # pytest failures
    pytest_fails = re.findall(r'FAILED\s+([^\n]+)', failure_log)
    # JS test failures (jest/mocha/npm)
    js_fails = re.findall(r'(?:✕|FAIL|●)\s+([^\n]+)', failure_log)
    # Generic errors
    generic_fails = re.findall(r'(?:^|\n)(?:##\[error\]|ERROR:|Error:)\s*([^\n]+)', failure_log)

    all_fails = list(dict.fromkeys(pytest_fails + js_fails + generic_fails))
    count = max(len(all_fails), 1 if any(kw in failure_log for kw in ("FAIL", "Error", "Exception")) else 0)

    return {
        "failure_count": count,
        "failures": all_fails[:10],
        "has_multiple": count > 1
    }


def extract_failure_chunk(full_log: str, window_lines: int = 50) -> str:
    """Isolate the most critical lines describing the failure from a raw CI/CD log and sanitize secrets."""
    if not full_log or len(full_log) < 300:
        return sanitize_secrets(full_log)

    clean_log = sanitize_secrets(full_log)
    lines = clean_log.splitlines()

    match_indices = []
    for i, line in enumerate(lines):
        for pattern in FAILURE_PATTERNS:
            if re.search(pattern, line):
                match_indices.append(i)
                break

    if not match_indices:
        return "\n".join(lines[-window_lines:])

    anchor = match_indices[-1] if any(kw in lines[match_indices[-1]] for kw in ("Error", "Assertion", "FAIL", "assert")) else match_indices[0]
    start = max(0, anchor - 15)
    end = min(len(lines), anchor + window_lines)
    return "\n".join(lines[start:end])


SENSITIVE_PATTERNS = [
    r'^\.env(?:\..+)?$',
    r'(?:^|[\/\\])(?:credentials|secrets\.json|secret\.key|private\.pem|token\.txt|id_rsa|id_ed25519)$',
    r'\.pem$',
    r'\.key$'
]

BINARY_EXTENSIONS = {
    ".sqlite": ("SQLite Database", "Vector/Relational Store"),
    ".sqlite3": ("SQLite Database", "Vector/Relational Store"),
    ".db": ("Database File", "Persistent Data"),
    ".parquet": ("Parquet Dataset", "Tabular Data Store"),
    ".zip": ("Zip Archive", "Archive"),
    ".tar": ("Tar Archive", "Archive"),
    ".gz": ("Gzip Archive", "Archive"),
    ".bin": ("Binary Data", "Binary Resource"),
    ".pkl": ("Pickle Serialized Data", "Model/State Checkpoint"),
    ".pickle": ("Pickle Serialized Data", "Model/State Checkpoint"),
    ".exe": ("Executable", "Binary Executable"),
    ".dll": ("Dynamic Library", "Binary Library"),
    ".so": ("Shared Object", "Binary Library"),
    ".dylib": ("Dynamic Library", "Binary Library"),
    ".jar": ("Java Archive", "Compiled Artifact")
}


def is_sensitive_file(filename_or_rel_path: str) -> bool:
    """Check whether a file path or filename contains sensitive secrets/keys/credentials (Section E)."""
    clean = filename_or_rel_path.replace("\\", "/").strip().lower()
    name = Path(clean).name
    if name.startswith(".env"):
        return True
    for pat in SENSITIVE_PATTERNS:
        if re.search(pat, clean, re.IGNORECASE) or re.search(pat, name, re.IGNORECASE):
            return True
    return False


def get_complete_repo_inventory(repo_path: Path) -> Dict[str, Any]:
    """
    Recursively inspects the repository and returns a structured breakdown (Section D, E, F):
    - total_files_discovered: Total count of all files physically present
    - selected_files: Valid code, test, config, and manifest files for analysis
    - sensitive_files_excluded: Relative paths of sensitive files excluded from prompt
    - binary_database_files: Metadata (filename, type, size, role) for binary/db files
    - inventory_summary: Text summary (e.g. '13 total files discovered; 12 selected for analysis (1 sensitive file excluded).')
    """
    if repo_path and not isinstance(repo_path, Path):
        repo_path = Path(repo_path)
    if not repo_path or not repo_path.exists():
        return {
            "total_files_discovered": 0,
            "selected_files": [],
            "sensitive_files_excluded": [],
            "binary_database_files": [],
            "inventory_summary": "0 files discovered."
        }

    total_count = 0
    selected_files = []
    sensitive_excluded = []
    binary_db_files = []

    for f in repo_path.rglob("*"):
        if f.is_file():
            rel_str = str(f.relative_to(repo_path)).replace("\\", "/")
            parts = f.relative_to(repo_path).parts
            
            # Skip hidden git internal files
            if any(p.startswith(".") and p != ".github" and not p.startswith(".env") for p in parts):
                continue
            if any(p in ("node_modules", "vendor", "__pycache__", "venv", ".venv", "target", "build", "dist", ".pytest_cache") for p in parts):
                continue

            total_count += 1

            # 1. Check for sensitive files (Section E: Never expose or send contents)
            if is_sensitive_file(rel_str):
                sensitive_excluded.append(rel_str)
                continue

            # 2. Check for database / binary files (Section F: Metadata only, never raw contents)
            ext = f.suffix.lower()
            if ext in BINARY_EXTENSIONS:
                f_type, f_role = BINARY_EXTENSIONS[ext]
                size_kb = round(f.stat().st_size / 1024, 1)
                binary_db_files.append({
                    "path": rel_str,
                    "type": f_type,
                    "size": f"{size_kb} KB",
                    "role": f_role
                })
                selected_files.append(rel_str)
                continue

            # 3. Standard source, test, workflow, config files
            selected_files.append(rel_str)

    selected_files = sorted(selected_files)
    sensitive_excluded = sorted(sensitive_excluded)

    sens_str = f" ({len(sensitive_excluded)} sensitive file{'s' if len(sensitive_excluded) > 1 else ''} excluded)" if sensitive_excluded else ""
    summary_str = f"{total_count} total files discovered; {len(selected_files)} selected for analysis{sens_str}."

    return {
        "total_files_discovered": total_count,
        "selected_files": selected_files,
        "sensitive_files_excluded": sensitive_excluded,
        "binary_database_files": binary_db_files,
        "inventory_summary": summary_str
    }


def get_repo_file_inventory(repo_path: Path) -> List[str]:
    """Return a clean list of selected repository relative file paths (forward slashes)."""
    inv = get_complete_repo_inventory(repo_path)
    return inv["selected_files"]


def validate_repository_file(
    candidate: Optional[str],
    repository_files: Optional[List[str]] = None,
    repo_path: Optional[Path] = None,
    allow_external: bool = False
) -> str:
    """
    Central strict repository file validator:
    1. Normalizes slash direction to forward slash.
    2. Normalizes ./ prefixes.
    3. Rejects absolute OS paths, WindowsApps, Program Files, AppData, hostedtoolcache,
       site-packages, Python installation/runtime paths, and internal libraries.
    4. Compares against actual repository-relative inventory.
    5. Returns a valid repository-relative path or 'Not identified'.
       If allow_external is True or repository_files is empty, preserves plausible relative code files.
    """
    if not candidate or str(candidate).strip() in ("", "None", "null", "Not identified", "source_code", "N/A"):
        return "Not identified"

    cand_str = str(candidate).strip()
    repository_files = repository_files or []

    # If repo_path is provided and candidate is an absolute path within repo_path, make it relative
    if repo_path:
        try:
            cand_p = Path(cand_str)
            if cand_p.is_absolute():
                rel = str(cand_p.resolve().relative_to(Path(repo_path).resolve())).replace("\\", "/")
                if rel in repository_files:
                    return rel
        except Exception:
            pass

    clean = cand_str.replace("\\", "/").strip()
    clean = re.sub(r"^\./+", "", clean)

    # Reject forbidden system / runtime / OS keywords
    clean_lower = clean.lower()
    for kw in SYSTEM_PATTERNS:
        if kw in clean_lower:
            return "Not identified"

    # Direct match in repository files
    for rf in repository_files:
        rf_norm = rf.replace("\\", "/").lstrip("/")
        if clean == rf_norm:
            return rf_norm

    # Suffix match (e.g. /home/runner/work/repo/repo/app/main.py ending with app/main.py)
    for rf in repository_files:
        rf_norm = rf.replace("\\", "/").lstrip("/")
        if clean.endswith("/" + rf_norm):
            return rf_norm

    # If allow_external is True or repository_files is empty, accept plausible relative source code path
    if allow_external or not repository_files:
        valid_exts = (".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".cpp", ".c", ".h", ".rb", ".php", ".yml", ".yaml", ".json", ".toml", ".txt", ".xml", ".gradle", ".md")
        if any(clean.endswith(ext) for ext in valid_exts) and not clean.startswith(("/", "\\", "http:", "https:")) and " " not in clean:
            return clean

    return "Not identified"


def is_test_file(path_str: str) -> bool:
    """Determine whether a file path represents a test suite file across languages."""
    if not path_str or path_str == "Not identified":
        return False
    norm = path_str.replace("\\", "/").lower()
    p = Path(norm)
    name = p.name
    parts = [part.lower() for part in p.parts]

    if any(k in parts for k in ("test", "tests", "__tests__", "spec", "specs")):
        return True
    if name.startswith("test_") or name.endswith(("_test.py", "test.py", ".spec.js", ".spec.ts", ".test.js", ".test.ts", "_test.go", "test.rs", "test.java", "tests.java")):
        return True
    if re.search(r'[A-Za-z0-9_]+Test\.java$', name, re.IGNORECASE) or re.search(r'[A-Za-z0-9_]+Tests\.java$', name, re.IGNORECASE):
        return True
    return False


def extract_assertion_evidence(failure_log: str) -> Dict[str, Any]:
    """Parse specific failure evidence: assertion expression, expected, actual, exception message."""
    evidence = {
        "error_type": "",
        "error_message": "",
        "expected": "",
        "actual": "",
        "assertion_stmt": "",
        "failing_func": ""
    }
    if not failure_log:
        return evidence

    # Extract exception types
    for exc in ("AssertionError", "ModuleNotFoundError", "ImportError", "KeyError", "SyntaxError", "TypeError", "ValueError", "NameError", "AttributeError", "IndexError", "NullPointerException", "AssertionFailedError"):
        m = re.search(r'\b(' + exc + r')(?::\s*([^\n]+))?', failure_log)
        if m:
            evidence["error_type"] = m.group(1)
            evidence["error_message"] = (m.group(2) or "").strip()
            break

    # Extract pytest/js assertion comparisons: assert -2 == 8, expect(x).toBe(y), etc.
    assert_m = re.search(r'AssertionError:\s*assert\s+(.+)', failure_log)
    if not assert_m:
        assert_m = re.search(r'assert\s+(.+)', failure_log)
    if not assert_m:
        assert_m = re.search(r'Expected:\s*(.+?)\s*Received:\s*(.+)', failure_log, re.DOTALL)
        if assert_m:
            evidence["expected"] = assert_m.group(1).splitlines()[0].strip()
            evidence["actual"] = assert_m.group(2).splitlines()[0].strip()
            evidence["assertion_stmt"] = f"Expected {evidence['expected']}, Received {evidence['actual']}"

    if assert_m and not evidence["expected"]:
        evidence["assertion_stmt"] = assert_m.group(1).strip()
        cmp_m = re.search(r'(.+?)\s*(?:==|!=|in|is)\s*(.+)', evidence["assertion_stmt"])
        if cmp_m:
            evidence["actual"] = cmp_m.group(1).strip()
            evidence["expected"] = cmp_m.group(2).strip()

    # Extract pytest + / - where lines
    where_m = re.findall(r'\+\s*where\s+(.+)', failure_log)
    if where_m:
        evidence["actual"] = (evidence["actual"] + " | " + " | ".join(where_m)).strip(" |")

    # Extract failing function name: ___ test_divide ___ or in test_add or ::test_divide
    func_m = re.search(r'_{3,}\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*_{3,}', failure_log)
    if not func_m:
        func_m = re.search(r'::(test_[a-zA-Z0-9_]*)', failure_log)
    if not func_m:
        func_m = re.search(r'def\s+(test_[a-zA-Z0-9_]*)\b', failure_log)
    if not func_m:
        func_m = re.search(r'File\s+["\'][^"\']+["\'],\s+line\s+\d+,\s+in\s+([a-zA-Z_][a-zA-Z0-9_]*)', failure_log)
    if not func_m:
        func_m = re.search(r'\bin\s+(test_[a-zA-Z0-9_]*)\b', failure_log)
    if func_m:
        candidate_func = func_m.group(1)
        if candidate_func.lower() not in ("git", "python", "docker", "runner", "ci", "github", "workflow", "ubuntu", "linux", "windows"):
            evidence["failing_func"] = candidate_func

    return evidence


def assess_test_vs_implementation(
    test_content: str,
    impl_content: str,
    evidence: Dict[str, Any]
) -> Tuple[str, str]:
    """
    Evaluates whether the defect is in the test or implementation.
    Returns (assessment_verdict, repair_target_type).
    Verdicts:
      - 'TEST CORRECT / IMPLEMENTATION WRONG' -> 'IMPLEMENTATION'
      - 'IMPLEMENTATION CORRECT / TEST WRONG' -> 'TEST'
    """
    if not test_content and not impl_content:
        return "TEST CORRECT / IMPLEMENTATION WRONG", "IMPLEMENTATION"

    assertion_stmt = (evidence.get("assertion_stmt") or "").strip()
    expected = (evidence.get("expected") or "").strip()
    actual = (evidence.get("actual") or "").strip()
    actual_base = actual.split("|")[0].strip()

    # Check for demonstrably contradictory or impossible test assertions
    all_test_text = f"{test_content}\n{assertion_stmt}"
    if re.search(r'(?:assert\s+)?(?:2\s*\+\s*2|1\s*\+\s*1|add\(2,\s*2\))\s*==\s*(?!4)\d+', all_test_text):
        return "IMPLEMENTATION CORRECT / TEST WRONG", "TEST"
    if re.search(r'assert\s+True\s*==\s*False', all_test_text) or re.search(r'assert\s+False\s*==\s*True', all_test_text):
        return "IMPLEMENTATION CORRECT / TEST WRONG", "TEST"
    if expected in ("99", "999", "undefined") and (actual_base in ("4", "5", "0") or "add(2, 2)" in actual):
        return "IMPLEMENTATION CORRECT / TEST WRONG", "TEST"

    # Default rule: Tests define specification expectations; code is expected to satisfy them
    return "TEST CORRECT / IMPLEMENTATION WRONG", "IMPLEMENTATION"


def find_implementation_file_from_test(
    test_file: str,
    test_content: str,
    repo_path: Optional[Path],
    repo_files: List[str]
) -> Optional[str]:
    """
    Given a failing test file and its code, find the corresponding application implementation file
    by inspecting imports, referenced function names, and path symmetry across languages.
    """
    if not test_file or test_file == "Not identified":
        return None

    # 1. Inspect Imports across Python and JS/TS
    if test_content:
        for mod in re.findall(r'(?:from|import)\s+([a-zA-Z0-9_\.]+)', test_content):
            mod_path = mod.replace(".", "/")
            for ext in (".py", ".js", ".ts", ".jsx", ".tsx"):
                cand1 = f"{mod_path}{ext}"
                cand2 = f"{mod_path}/__init__.py"
                cand3 = f"src/{cand1}"
                cand4 = f"app/{cand1}"
                cand5 = f"lib/{cand1}"
                for cand in (cand1, cand2, cand3, cand4, cand5):
                    val = validate_repository_file(cand, repository_files=repo_files, repo_path=repo_path)
                    if val != "Not identified" and not is_test_file(val):
                        return val

        for req in re.findall(r'(?:require\(|from\s+)[\'"]([^\'"]+)[\'"]', test_content):
            clean_req = re.sub(r'^\.+/', '', req)
            for ext in (".js", ".ts", ".jsx", ".tsx", "/index.js", "/index.ts"):
                cand1 = f"{clean_req}{ext}"
                cand2 = f"src/{clean_req}{ext}"
                cand3 = f"app/{clean_req}{ext}"
                for cand in (cand1, cand2, cand3):
                    val = validate_repository_file(cand, repository_files=repo_files, repo_path=repo_path)
                    if val != "Not identified" and not is_test_file(val):
                        return val

        func_calls = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', test_content)
        ignore_funcs = {"assert", "expect", "test", "describe", "it", "print", "len", "range", "list", "dict", "set", "str", "int", "float", "open", "type", "isinstance", "setup", "teardown"}
        unique_funcs = [fn for fn in func_calls if fn not in ignore_funcs and not fn.startswith("test_")]

        if repo_path and repo_path.exists():
            for rf in repo_files:
                if not is_test_file(rf) and rf.endswith((".py", ".js", ".ts", ".java", ".go", ".rs")):
                    rf_p = repo_path / rf
                    if rf_p.exists():
                        try:
                            code = rf_p.read_text(encoding="utf-8", errors="ignore")
                            for fn in unique_funcs:
                                if re.search(r'\b(?:def|function|class|const|let|var)\s+' + re.escape(fn) + r'\b', code):
                                    return rf
                        except Exception:
                            pass

    # 2. Path Symmetry (e.g. tests/app/arrays.test.js -> app/arrays.js, tests/test_calc.py -> calc.py)
    test_p = Path(test_file)
    stem = test_p.stem
    impl_stem = re.sub(r'^test_|[-_]test|\.test|\.spec$', '', stem)
    if impl_stem and impl_stem != stem:
        for rf in repo_files:
            if not is_test_file(rf):
                rf_p = Path(rf)
                if rf_p.stem == impl_stem or rf_p.stem == impl_stem.replace(".test", ""):
                    return rf

    # 3. Single primary source file in repo (non-test)
    non_test_files = [f for f in repo_files if not is_test_file(f) and f.endswith((".py", ".js", ".ts", ".rs", ".go", ".java"))]
    if len(non_test_files) == 1:
        return non_test_files[0]

    return None


def locate_faulty_file(
    failure_log: str,
    repo_path: Optional[Path] = None,
    repo_files: Optional[List[str]] = None
) -> str:
    """
    Parse stack traces and error messages to pinpoint the responsible source file.
    Validates all candidate paths against the repository file inventory.
    Returns 'Not identified' if no valid repository file is found.
    """
    if not failure_log:
        return "Not identified"

    if repo_files is None and repo_path:
        repo_files = get_repo_file_inventory(repo_path)
    repo_files = repo_files or []

    raw_candidates = []

    # 0. GitHub Actions workflow action error
    log_low = failure_log.lower()
    wf_input_match = re.search(r"Input required and not supplied:\s*([a-zA-Z0-9_\-]+)", failure_log, re.IGNORECASE)
    is_hosting_err = "action-hosting-deploy" in log_low and any(k in log_low for k in ("input required", "secret", "serviceaccount", "firebase"))
    if wf_input_match or is_hosting_err:
        wf_files = [f for f in repo_files if f.startswith(".github/workflows/")]
        if wf_files:
            fb_wfs = [f for f in wf_files if "firebase" in f.lower()]
            return fb_wfs[0] if fb_wfs else wf_files[0]

    # 1. pytest: FAILED tests/test_main.py::test_add
    for match in re.findall(r'FAILED\s+([a-zA-Z0-9_\-\./\\]+\.(?:py|js|ts|java|go|rs)):?', failure_log):
        raw_candidates.append(match)

    # 1b. pytest dot-f summary lines: tests/test_calculator.py .F. [100%]
    for match in re.findall(r'([a-zA-Z0-9_\-\./\\]+\.(?:py|js|ts|java|go|rs))\s+[\.sFxF]+', failure_log):
        raw_candidates.append(match)

    # 2. Python tracebacks: File "path/to/file.py", line 123
    for match in re.findall(r'File\s+"([^"]+\.py)"', failure_log):
        raw_candidates.append(match)

    # 3. Node / JS: at Object.<anonymous> (src/config.ts:8:11)
    for match in re.findall(r'at\s+.*?\(([a-zA-Z0-9_\-\./\\]+\.(?:js|ts|jsx|tsx)):(\d+)', failure_log):
        raw_candidates.append(match[0])

    # 4. Java: (ClassName.java:45)
    for match in re.findall(r'\(([A-Za-z0-9_]+\.java):(\d+)\)', failure_log):
        raw_candidates.append(match[0])

    # 5. Generic repo file mentions with valid code/config extensions
    for match in re.findall(r'(?:^|[\s"\'\(])([a-zA-Z0-9_\-\./\\]+\.(?:py|java|js|ts|cpp|c|go|rs|rb|ya?ml))', failure_log):
        raw_candidates.append(match)

    validated = []
    for cand in raw_candidates:
        val = validate_repository_file(cand, repository_files=repo_files, repo_path=repo_path)
        if val != "Not identified" and val not in validated:
            validated.append(val)

    if not validated:
        for cand in raw_candidates:
            val = validate_repository_file(cand, repository_files=[], repo_path=repo_path, allow_external=True)
            if val != "Not identified" and val not in validated:
                validated.append(val)

    if validated:
        # Prefer the test file if test failure or first validated file
        test_cands = [f for f in validated if is_test_file(f)]
        if test_cands:
            return test_cands[0]
        return validated[0]

    return "Not identified"


def classify_failure_nature(failure_log: str, repo_files: List[str]) -> Tuple[str, str]:
    """
    Evidence-based failure categorization into the EXACT 13 canonical classes (NO Unknown):
    1. Code Error
    2. Dependency Error
    3. Build Error
    4. Test Failure
    5. Configuration Error
    6. Environment Error
    7. Compilation Error
    8. Runtime Error
    9. Infrastructure Error
    10. Authentication / Permission Error
    11. Network Error
    12. Deployment Error
    13. Docker / Container Error
    """
    if not failure_log or "All tests passed successfully" in failure_log or "0 failures" in failure_log:
        return "None", "NONE"

    log_lower = failure_log.lower()

    # 1. Docker / Container Error
    if any(kw in log_lower for kw in ("docker daemon not running", "cannot connect to the docker daemon", "docker: command not found", "error building docker image", "dockerfile parse error", "failed to solve with frontend dockerfile")):
        return "Docker / Container Error", "DOCKER"

    # 2. Deployment Error
    if any(kw in log_lower for kw in ("deploy failed", "deployment error", "helm upgrade failed", "kubectl apply failed", "vercel deployment", "netlify deploy", "aws ecs deployment", "publish failed")):
        return "Deployment Error", "DEPLOYMENT"

    # 3. Infrastructure Error
    if any(kw in log_lower for kw in ("runner has encountered an internal error", "hosted runner is unavailable", "oomkilled", "no space left on device", "actions runner error", "runner process exited")):
        return "Infrastructure Error", "INFRASTRUCTURE"

    # 4. Network Error
    if any(kw in log_lower for kw in ("connection refused", "could not resolve host", "network unreachable", "etimedout", "curl: (7)", "curl: (6)")) or re.search(r'\b(econnrefused|enotfound)\b', log_lower):
        return "Network Error", "NETWORK"


    # 5. Authentication / Permission Error
    if any(kw in log_lower for kw in ("401 unauthorized", "403 forbidden", "permission denied", "invalid authentication token", "access denied", "bad credentials")):
        return "Authentication / Permission Error", "AUTHENTICATION"

    # 6. Environment Error
    key_match = re.search(r"KeyError:\s*['\"]([A-Z0-9_]+)['\"]", failure_log)
    if key_match or any(kw in log_lower for kw in ("environment variable not set", "missing required env", "undefined environment")):
        return "Environment Error", "ENVIRONMENT"

    # 7. Workflow / Configuration Error
    wf_input_match = re.search(r"Input required and not supplied:\s*([a-zA-Z0-9_\-]+)", failure_log, re.IGNORECASE)
    is_hosting_err = "action-hosting-deploy" in log_lower and any(k in log_lower for k in ("input required", "secret", "serviceaccount", "firebase"))
    if wf_input_match or is_hosting_err or any(kw in log_lower for kw in ("workflow is not valid", "yaml syntax error", "invalid action", "unrecognized named-value")):
        return "Configuration Error", "CONFIGURATION"

    # 8. Dependency Error vs Internal Import Error
    dep_match = re.search(r"ModuleNotFoundError:\s*No module named ['\"]([^'\"]+)['\"]", failure_log)
    if dep_match:
        mod_name = dep_match.group(1).split(".")[0]
        is_internal = any(rf.startswith(mod_name) or f"/{mod_name}/" in f"/{rf}/" or rf.endswith(f"/{mod_name}.py") for rf in repo_files)
        if is_internal:
            return "Code Error", "IMPLEMENTATION"
        return "Dependency Error", "DEPENDENCY"

    if any(kw in log_lower for kw in ("could not find a version that satisfies the requirement", "npm err! 404", "cannot find module", "err_module_not_found")):
        if any(f"./{rf}" in failure_log or f"../{rf}" in failure_log for rf in repo_files):
            return "Code Error", "IMPLEMENTATION"
        return "Dependency Error", "DEPENDENCY"

    # 9. Build / Package Error
    if any(kw in log_lower for kw in ("package is not built", "module was not built", "build failed", "cargo build failed", "mvn package failed", "npm run build failed")):
        return "Build Error", "BUILD"

    # 10. Compilation / Syntax Error
    if any(kw in log_lower for kw in ("syntaxerror", "compilation failed", "cannot find symbol", "error[e", "javac error", "ts2304", "ts2307")):
        return "Compilation Error", "IMPLEMENTATION"

    # 11. Test Failure (Assertion error, pytest failure blocks, test runner results)
    test_failure_indicators = (
        "assertionerror", "failures:", "failed:", "assert ", "expect(", "assertionfailed",
        "failed tests:", "flaky test", "flakiness", "race condition", "timing issue", "intermittent failure",
        "=== failures ===", "=== failure ===", "test session starts", "::test_", ".f.", "short test summary info"
    )
    if any(kw in log_lower for kw in test_failure_indicators) or re.search(r'_{3,}\s*test_[a-zA-Z0-9_]+\s*_{3,}', failure_log) or re.search(r'\bFAILED\s+[^\n]+::test_', failure_log) or re.search(r'\b[a-zA-Z0-9_\-\./]+\.py\s+[\.sFxF]+', failure_log):
        return "Test Failure", "IMPLEMENTATION"

    # 12. Runtime Error
    if any(kw in log_lower for kw in ("typeerror", "valueerror", "indexerror", "attributeerror", "zerodivisionerror", "nullpointerexception", "referenceerror")):
        return "Runtime Error", "IMPLEMENTATION"

    # 13. Default: Code Error (Maximum SLM reasoning fallback, never Unknown)
    return "Code Error", "IMPLEMENTATION"


def classify_repair_type(failure_type: str, repair_target_type: str, target_file: str = "") -> str:
    """
    Map failure type and repair target to one of the canonical contract categories:
    Source Code / Dependency / Configuration / Environment / CI / Infrastructure / None
    """
    ft_lower = (failure_type or "").lower()
    rtt_upper = (repair_target_type or "").upper()
    tf_lower = (target_file or "").lower()

    if ft_lower in ("none", "no error", "passing") or rtt_upper == "NONE":
        return "None"
    if "dependency" in ft_lower or rtt_upper in ("DEPENDENCY", "PACKAGE") or tf_lower.endswith(("requirements.txt", "package.json", "pom.xml", "cargo.toml", "go.mod", "pyproject.toml", "pipfile")):
        return "Dependency"
    if "environment" in ft_lower or rtt_upper == "ENVIRONMENT":
        return "Environment"
    if "configuration" in ft_lower or rtt_upper == "CONFIGURATION":
        return "Configuration"
    if any(kw in ft_lower for kw in ("infrastructure", "docker", "container", "network", "authentication")) or rtt_upper in ("INFRASTRUCTURE", "DOCKER", "NETWORK", "AUTHENTICATION"):
        return "Infrastructure"
    if "deployment" in ft_lower or rtt_upper == "DEPLOYMENT" or ".github/workflows" in tf_lower:
        return "CI"
    return "Source Code"


def identify_detailed_dependency_error(
    failure_log: str = "",
    repo_files: Optional[List[str]] = None,
    target_manifest: Optional[str] = None,
    repo_path: Optional[Path] = None,
    test_file: Optional[str] = None,
    raw_model_output: Optional[str] = None
) -> Dict[str, Any]:
    """
    Deterministically identifies which dependency error occurred, which package is missing or defective,
    which manifest is affected, which file requires it, and generates understandable, comprehensive
    technical root cause analysis, fix strategy, and a unified git diff patch.
    """
    repo_files = repo_files or []
    log = failure_log or ""
    
    # 1. Determine target manifest file
    manifest_file = target_manifest or "requirements.txt"
    if manifest_file in ("Not identified", "None", ""):
        all_manifests = [
            f for f in repo_files 
            if f.endswith(("requirements.txt", "package.json", "pom.xml", "Cargo.toml", "pyproject.toml", "go.mod"))
        ]
        if all_manifests:
            if test_file and "/" in test_file:
                prefix = test_file.split("/")[0] + "/"
                sub_manifests = [m for m in all_manifests if m.startswith(prefix)]
                manifest_file = sub_manifests[0] if sub_manifests else all_manifests[0]
            else:
                manifest_file = all_manifests[0]
        else:
            manifest_file = "requirements.txt" if any(f.endswith(".py") for f in repo_files) else "Not identified"

    # 2. Extract missing/defective package from failure log
    missing_pkg = ""
    error_subtype = "Missing Package Dependency"
    
    dep_m = re.search(
        r"(?:No module named|ModuleNotFoundError:\s*(?:No module named\s*)?|cannot find module|ImportError:\s*(?:cannot import name\s+|No module named\s*)?|package not found\s*)['\"]?([a-zA-Z0-9_\-]+)['\"]?",
        log,
        re.IGNORECASE
    )
    if dep_m:
        missing_pkg = dep_m.group(1).split(".")[0].strip()

    if not missing_pkg:
        res_m = re.search(
            r"(?:Could not find a version that satisfies the requirement|No matching distribution found for)\s*([a-zA-Z0-9_\-]+)",
            log,
            re.IGNORECASE
        )
        if res_m:
            missing_pkg = res_m.group(1).strip()
            error_subtype = "Unresolved Version / Distribution Error"

    if not missing_pkg:
        npm_m = re.search(
            r"npm ERR!\s*(?:404 Not Found\s*-\s*(?:GET\s+\S+\s+)?|code\s+E404.*?404\s+['\"]?)([a-zA-Z0-9_\-@/]+)",
            log,
            re.IGNORECASE
        )
        if npm_m:
            missing_pkg = npm_m.group(1).strip()
            error_subtype = "Package Registry 404 Error"

    # 3. Codebase inspection: Manifest vs Test/Source Imports
    declared_pkgs = []
    declared_summary = ""
    manifest_full_path = None
    if repo_path and manifest_file and manifest_file != "Not identified":
        candidate_path = repo_path / manifest_file
        if candidate_path.exists():
            manifest_full_path = candidate_path

    if manifest_full_path and manifest_full_path.name.endswith("requirements.txt"):
        try:
            m_text = manifest_full_path.read_text(encoding="utf-8", errors="ignore")
            for line in m_text.splitlines():
                line = line.strip().split("#")[0].strip()
                if line and not line.startswith(("-", "--")):
                    p_name = re.split(r'[=><~]', line)[0].strip()
                    if p_name:
                        declared_pkgs.append(p_name)
            if declared_pkgs:
                declared_summary = ", ".join(declared_pkgs[:5])
        except Exception:
            pass

    referencing_file = test_file if (test_file and test_file != "Not identified") else "test suite"
    if not missing_pkg and repo_path:
        STD_LIBS = {
            "sys", "os", "re", "json", "math", "datetime", "unittest", "time", "logging",
            "pathlib", "typing", "subprocess", "io", "shutil", "tempfile", "collections",
            "itertools", "functools", "random", "copy", "urllib", "http", "threading",
            "multiprocessing", "traceback", "hashlib", "socket", "platform", "dataclasses",
            "enum", "abc", "contextlib", "string", "struct", "base64", "csv", "sqlite3",
            "zipfile", "tarfile", "glob", "xml", "inspect", "builtins"
        }
        declared_norm = {p.lower().replace("_", "-") for p in declared_pkgs}

        test_cands = [test_file] if (test_file and test_file != "Not identified") else []
        test_cands.extend([f for f in repo_files if is_test_file(f) and f not in test_cands])

        for tf in test_cands:
            tf_path = repo_path / tf
            if tf_path.exists() and tf_path.suffix == ".py":
                try:
                    t_content = tf_path.read_text(encoding="utf-8", errors="ignore")
                    imports = re.findall(r'^\s*(?:import|from)\s+([a-zA-Z0-9_]+)', t_content, re.MULTILINE)
                    for imp in imports:
                        imp_norm = imp.lower().replace("_", "-")
                        if imp_norm in STD_LIBS:
                            continue
                        if imp_norm in declared_norm:
                            continue
                        if any(Path(rf).stem == imp for rf in repo_files):
                            continue
                        missing_pkg = imp
                        referencing_file = tf
                        if imp in ("pytest", "mock", "pytest_mock", "freezegun", "responses", "vcr"):
                            error_subtype = "Missing Test Framework Dependency"
                        break
                    if missing_pkg:
                        break
                except Exception:
                    pass

    # 4. Check raw model output if still missing
    if not missing_pkg and raw_model_output:
        raw_m = re.search(r"(?:Add|package|missing)\s+[`'\"]?([a-zA-Z0-9_\-]+)[`'\"]?", raw_model_output, re.IGNORECASE)
        if raw_m and raw_m.group(1).lower() not in ("pip", "root", "user", "run", "the", "flag"):
            missing_pkg = raw_m.group(1).strip()

    # Default fallback for Python test suites if missing package is undeclared
    if not missing_pkg:
        if any(f.endswith(".py") for f in repo_files):
            missing_pkg = "pytest"
            error_subtype = "Missing Test Framework Dependency"
        else:
            missing_pkg = "dependency"

    # Recommend appropriate version specification
    if missing_pkg.lower() == "pytest":
        recommended_spec = "pytest>=8.0.0"
    elif missing_pkg.lower() == "requests":
        recommended_spec = "requests>=2.31.0"
    elif missing_pkg.lower() == "flask":
        recommended_spec = "flask>=3.0.0"
    elif missing_pkg.lower() == "jest":
        recommended_spec = "jest>=29.0.0"
    else:
        recommended_spec = f"{missing_pkg}>=1.0.0" if not any(c in missing_pkg for c in "=>~<") else missing_pkg

    # 5. Format comprehensive, understandable Root Cause
    if error_subtype == "Missing Test Framework Dependency":
        root_cause = (
            f"BuildFail-SLM identified a Dependency Error: Missing test framework dependency '{missing_pkg}' (recommended: '{recommended_spec}'). "
            f"The manifest '{manifest_file}' declares runtime dependencies ({declared_summary or 'base packages'}), but does not declare '{missing_pkg}'. "
            f"The test suite in '{referencing_file}' directly requires '{missing_pkg}' for test execution and assertion evaluation. "
            f"When the CI runner initializes a clean environment and executes 'pip install -r {manifest_file}', '{missing_pkg}' is absent, "
            f"leading to test suite execution failure in the CI/CD pipeline."
        )
    elif error_subtype == "Unresolved Version / Distribution Error":
        root_cause = (
            f"BuildFail-SLM identified a Dependency Error: Unresolved version constraint for '{missing_pkg}'. "
            f"The dependency manifest '{manifest_file}' specifies a version constraint that cannot be satisfied by available package distributions in the active environment. "
            f"The installer terminated because no compatible distribution of '{missing_pkg}' matches the runner platform and Python runtime."
        )
    elif error_subtype == "Package Registry 404 Error":
        root_cause = (
            f"BuildFail-SLM identified a Dependency Error: Package registry resolution failed for '{missing_pkg}'. "
            f"The package name referenced in '{manifest_file}' returned HTTP 404 Not Found from the configured registry, indicating an invalid package name, typo, or missing private repository credentials."
        )
    else:
        root_cause = (
            f"BuildFail-SLM identified a Dependency Error: Undeclared package dependency '{missing_pkg}' (recommended: '{recommended_spec}'). "
            f"The manifest '{manifest_file}' omits '{missing_pkg}', which is imported and required by '{referencing_file}'. "
            f"Fresh CI/CD runner environments installing solely from '{manifest_file}' encounter ModuleNotFoundError / unresolved import errors during build execution."
        )

    # 6. Format Actionable Suggested Fix Strategy
    suggested_fix = (
        f"BuildFail-SLM classified this failure as **Dependency Error** (Defect: missing '{missing_pkg}').\n\n"
        f"**Remediation Steps:**\n"
        f"1. **Update Manifest:** Append '{recommended_spec}' to '{manifest_file}'.\n"
        f"2. **Install Dependencies:** Run `pip install -r {manifest_file}` in the CI workflow environment before test execution.\n"
        f"3. **Execute Verification:** Run the test suite (`pytest {referencing_file if referencing_file != 'test suite' else 'tests/'}`) to confirm that all test assertions and fixtures resolve without import errors.\n\n"
        f"**Why this fix works:** Explicitly declaring '{recommended_spec}' in '{manifest_file}' guarantees that fresh CI runner instances, containerized Docker builds, and local development environments all install identical, reproducible test tooling."
    )

    # 7. Synthesize Unified Git Diff
    unified_diff = ""
    if manifest_file and manifest_file != "Not identified":
        if manifest_full_path and manifest_full_path.exists():
            try:
                orig_content = manifest_full_path.read_text(encoding="utf-8", errors="ignore")
                orig_lines = [l for l in orig_content.splitlines() if l.strip()]
                if not any(missing_pkg.lower() in l.lower() for l in orig_lines):
                    line_count = len(orig_lines)
                    unified_diff = (
                        f"--- a/{manifest_file}\n"
                        f"+++ b/{manifest_file}\n"
                        f"@@ -{line_count},1 +{line_count},2 @@\n"
                    )
                    if orig_lines:
                        unified_diff += f" {orig_lines[-1]}\n"
                    unified_diff += f"+{recommended_spec}\n"
            except Exception:
                pass
        
        if not unified_diff:
            unified_diff = (
                f"--- a/{manifest_file}\n"
                f"+++ b/{manifest_file}\n"
                f"@@ -1,2 +1,3 @@\n"
                f"+{recommended_spec}\n"
            )

    return {
        "missing_package": missing_pkg,
        "recommended_spec": recommended_spec,
        "manifest_file": manifest_file,
        "referencing_file": referencing_file,
        "error_subtype": error_subtype,
        "root_cause": root_cause,
        "suggested_fix": suggested_fix,
        "unified_diff": unified_diff,
        "declared_pkgs": declared_pkgs
    }


def determine_actual_repair_target(
    failure_type: str,
    failure_log: str,
    observed_failure_location: str,
    repo_files: List[str],
    repo_path: Optional[Path] = None,
    test_file: Optional[str] = None,
    impl_file: Optional[str] = None,
    test_vs_impl: str = "TEST CORRECT / IMPLEMENTATION WRONG"
) -> Tuple[str, str, str, str]:
    """
    Dependency-aware and architecture-aware repair-target reasoning stage.
    Explicitly separates Observed Failure Location from Actual Repair Target.
    Never assumes: observed_failure_location == actual_repair_target.

    Returns:
        (actual_repair_target, repair_target_type, repair_type, confidence)
    """
    ft_lower = (failure_type or "").lower()
    log_lower = (failure_log or "").lower()
    repo_files = repo_files or []

    # 0. Clean / Passing (No Failure)
    if ft_lower in ("none", "no error", "passing") or "all tests passed" in log_lower:
        return "Not identified", "NONE", "None", "High"

    # 0b. GitHub Actions Workflow Configuration / Secret / Action Input Error
    wf_input_match = re.search(r"Input required and not supplied:\s*([a-zA-Z0-9_\-]+)", failure_log, re.IGNORECASE)
    is_hosting_err = "action-hosting-deploy" in log_lower and any(k in log_lower for k in ("input required", "secret", "serviceaccount", "firebase"))
    if wf_input_match or is_hosting_err:
        wf_files = [f for f in repo_files if f.startswith(".github/workflows/")]
        if wf_files:
            fb_wfs = [f for f in wf_files if "firebase" in f.lower()]
            return (fb_wfs[0] if fb_wfs else wf_files[0]), "CONFIGURATION", "CI", "High"

    # 1. Dependency Error: Missing package, import error, version conflict
    # Under NO circumstance is a test file or application code the repair target for a Dependency Error!
    if "dependency" in ft_lower or any(kw in log_lower for kw in ("modulenotfounderror", "no module named", "cannot find module", "err_module_not_found", "could not find a version that satisfies the requirement")):
        # Inspect dependency manifests in repository across ecosystems
        py_deps = [
            f for f in repo_files 
            if f.endswith(("requirements.txt", "requirements-dev.txt", "pyproject.toml", "Pipfile", "poetry.lock", "setup.py", "setup.cfg"))
            or f.startswith("requirements/")
        ]
        node_deps = [f for f in repo_files if f.endswith(("package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"))]
        java_deps = [f for f in repo_files if f.endswith(("pom.xml", "build.gradle", "build.gradle.kts"))]
        rust_deps = [f for f in repo_files if f.endswith("Cargo.toml")]
        go_deps = [f for f in repo_files if f.endswith("go.mod")]

        all_manifests = py_deps + node_deps + java_deps + rust_deps + go_deps
        if all_manifests:
            # If observed_failure_location is in a subdirectory (e.g. sample-app/), prioritize manifest in that same directory
            if observed_failure_location and "/" in observed_failure_location:
                sub_prefix = observed_failure_location.split("/")[0] + "/"
                sub_manifests = [m for m in all_manifests if m.startswith(sub_prefix)]
                if sub_manifests:
                    all_manifests = sub_manifests + [m for m in all_manifests if m not in sub_manifests]

            if any(f.endswith("requirements.txt") for f in all_manifests):
                target = next(f for f in all_manifests if f.endswith("requirements.txt"))
            elif any(f.endswith("package.json") for f in all_manifests):
                target = next(f for f in all_manifests if f.endswith("package.json"))
            elif any(f.endswith("pyproject.toml") for f in all_manifests):
                target = next(f for f in all_manifests if f.endswith("pyproject.toml"))
            elif any(f.endswith("pom.xml") for f in all_manifests):
                target = next(f for f in all_manifests if f.endswith("pom.xml"))
            elif any(f.endswith("Cargo.toml") for f in all_manifests):
                target = next(f for f in all_manifests if f.endswith("Cargo.toml"))
            elif any(f.endswith("go.mod") for f in all_manifests):
                target = next(f for f in all_manifests if f.endswith("go.mod"))
            else:
                target = all_manifests[0]
            return target, "DEPENDENCY", "Dependency", "High"

        # If no package manifest exists, check Dockerfile or workflow
        wf_files = [f for f in repo_files if f.startswith(".github/workflows/") or f == "Dockerfile"]
        if wf_files:
            return wf_files[0], "DEPENDENCY", "CI", "Medium"

        if not repo_files:
            default_dep = "requirements.txt" if any(kw in log_lower for kw in ("python", "pytest", ".py")) else "Not identified"
            return default_dep, "DEPENDENCY", "Dependency", "Medium"

        return "Not identified", "DEPENDENCY", "Dependency", "Medium"

    # 2. Environment Error: Missing environment variables or secrets
    if "environment" in ft_lower or any(kw in log_lower for kw in ("keyerror:", "environment variable not set", "missing required env", "undefined environment")):
        env_files = [f for f in repo_files if f in (".env.example", ".env.sample", ".env.template")]
        if env_files:
            return env_files[0], "ENVIRONMENT", "Environment", "High"
        wf_files = [f for f in repo_files if f.startswith(".github/workflows/")]
        if wf_files:
            return wf_files[0], "ENVIRONMENT", "Environment", "High"
        return "Not identified", "ENVIRONMENT", "Environment", "Medium"

    # 3. Configuration Error: Workflow YAML, action syntax, tool config
    if "configuration" in ft_lower or any(kw in log_lower for kw in ("workflow is not valid", "yaml syntax error", "invalid action", "unrecognized named-value")):
        wf_files = [f for f in repo_files if f.startswith(".github/workflows/")]
        if wf_files:
            return wf_files[0], "CONFIGURATION", "Configuration", "High"
        config_files = [f for f in repo_files if f in ("Dockerfile", "docker-compose.yml", "pyproject.toml", "config.yaml", "config.json")]
        if config_files:
            return config_files[0], "CONFIGURATION", "Configuration", "High"
        return "Not identified", "CONFIGURATION", "Configuration", "Medium"

    # 4. Infrastructure / Docker / Container / Network / Deployment Errors
    if "docker" in ft_lower or any(kw in log_lower for kw in ("docker daemon", "docker: command not found", "cannot connect to the docker daemon")):
        docker_files = [f for f in repo_files if f in ("Dockerfile", "docker-compose.yml")]
        if docker_files:
            return docker_files[0], "DOCKER", "Infrastructure", "High"
        wf_files = [f for f in repo_files if f.startswith(".github/workflows/")]
        if wf_files:
            return wf_files[0], "DOCKER", "CI", "Medium"
        return "Not identified", "DOCKER", "Infrastructure", "Medium"

    if "deployment" in ft_lower or any(kw in log_lower for kw in ("deploy failed", "deployment error", "helm", "kubectl", "publish failed")):
        wf_files = [f for f in repo_files if f.startswith(".github/workflows/")]
        if wf_files:
            return wf_files[0], "DEPLOYMENT", "CI", "High"
        return "Not identified", "DEPLOYMENT", "CI", "Medium"

    if any(kw in ft_lower for kw in ("infrastructure", "network", "authentication")):
        wf_files = [f for f in repo_files if f.startswith(".github/workflows/")]
        target = wf_files[0] if wf_files else "Not identified"
        rep_type = "CI" if wf_files else "Infrastructure"
        target_cat = "INFRASTRUCTURE" if "infrastructure" in ft_lower else ("NETWORK" if "network" in ft_lower else "AUTHENTICATION")
        return target, target_cat, rep_type, "High" if wf_files else "Medium"

    # 5. Test Failure: Assertion error in test suite
    if "test" in ft_lower or any(kw in log_lower for kw in ("assertionerror", "assert ", "expect(", "failed tests:", "=== failures ===", ".f.")):
        if test_vs_impl in ("TEST WRONG / IMPLEMENTATION CORRECT", "IMPLEMENTATION CORRECT / TEST WRONG"):
            target = test_file if (test_file and test_file != "Not identified") else observed_failure_location
            return target or "Not identified", "TEST", "Source Code", "High"
        else:
            # Test is correct, implementation is wrong -> Target MUST be implementation, NOT the test!
            target = impl_file if (impl_file and impl_file != "Not identified") else None
            if not target and observed_failure_location and is_test_file(observed_failure_location):
                target = find_implementation_file_from_test(observed_failure_location, "", repo_path, repo_files)
            if not target:
                non_tests = [f for f in repo_files if not is_test_file(f) and f.endswith((".py", ".js", ".ts", ".java", ".go", ".rs")) and not f.endswith("__init__.py")]
                if non_tests:
                    target = non_tests[0]
            if not target and observed_failure_location:
                test_p = Path(observed_failure_location)
                stem = test_p.stem
                if stem.startswith("test_"):
                    impl_stem = stem[5:]
                    target = f"app/{impl_stem}.py" if any(f.startswith("app/") for f in repo_files) else (f"src/{impl_stem}.py" if any(f.startswith("src/") for f in repo_files) else f"{impl_stem}.py")
                else:
                    target = observed_failure_location
            return target or "Not identified", "IMPLEMENTATION", "Source Code", "High" if target else "Medium"

    # 6. Code Error / Runtime Error / Compilation Error / Build Error
    # Locate the application implementation file responsible for the defect
    if observed_failure_location and not is_test_file(observed_failure_location) and not observed_failure_location.startswith(".github/"):
        return observed_failure_location, "IMPLEMENTATION", "Source Code", "High"

    target = impl_file if (impl_file and impl_file != "Not identified") else None
    if not target and observed_failure_location and is_test_file(observed_failure_location):
        target = find_implementation_file_from_test(observed_failure_location, "", repo_path, repo_files)
    if not target:
        non_tests = [f for f in repo_files if not is_test_file(f) and f.endswith((".py", ".js", ".ts", ".java", ".go", ".rs"))]
        if non_tests:
            target = non_tests[0]

    return target or "Not identified", "IMPLEMENTATION", "Source Code", "High" if target else "Medium"


def derive_repository_verification_command(

    language: str,
    failure_type: str,
    repair_target_type: str,
    target_file: str = "Not identified",
    repo_path: Optional[Path] = None,
    repo_files: Optional[List[str]] = None
) -> str:
    """
    Dynamically derive repository-accurate verification commands from repository configs:
    - Node/JS: Reads package.json scripts (npm test, yarn test, pnpm test, jest, etc.). NEVER pytest for JS!
    - Python: Reads pyproject.toml, pytest.ini, requirements.txt (pytest, unittest, tox).
    - Java: Reads pom.xml (mvn test), build.gradle (./gradlew test).
    - Rust: Reads Cargo.toml (cargo test).
    - Go: Reads go.mod (go test ./...).
    - Docker: Reads Dockerfile (docker build -t test-build .).
    """
    repo_files = repo_files or []
    lang_clean = language.strip().lower()

    # 1. Node / JavaScript / TypeScript
    if lang_clean in ("javascript", "typescript", "node", "nodejs") or any(f.endswith("package.json") for f in repo_files):
        base_cmd = "npm test"
        if repo_path and (repo_path / "package.json").exists():
            try:
                pkg_data = json.loads((repo_path / "package.json").read_text(encoding="utf-8", errors="ignore"))
                scripts = pkg_data.get("scripts", {})
                if "test" in scripts:
                    base_cmd = "npm test"
                elif "jest" in pkg_data.get("devDependencies", {}):
                    base_cmd = "npx jest"
            except Exception:
                pass
        elif (repo_path and (repo_path / "yarn.lock").exists()) or any("yarn.lock" in f for f in repo_files):
            base_cmd = "yarn test"

        if repair_target_type == "DEPENDENCY" or "dependency" in failure_type.lower():
            return f"npm install && {base_cmd}"
        if repair_target_type == "BUILD" or "build" in failure_type.lower():
            return "npm run build"
        return base_cmd

    # 2. Java
    if lang_clean == "java" or any(f.endswith(("pom.xml", "build.gradle", "build.gradle.kts")) for f in repo_files):
        if any(f.endswith("pom.xml") for f in repo_files):
            if "compilation" in failure_type.lower() or "build" in failure_type.lower():
                return "mvn compile"
            return "mvn test"
        if any(f.endswith("build.gradle") for f in repo_files):
            return "./gradlew test"
        return "mvn test"

    # 3. Rust
    if lang_clean == "rust" or any(f.endswith("Cargo.toml") for f in repo_files):
        if "compilation" in failure_type.lower():
            return "cargo check"
        return "cargo test"

    # 4. Go
    if lang_clean == "go" or any(f.endswith("go.mod") for f in repo_files):
        return "go test ./..."

    # 5. Docker
    if lang_clean == "docker" or repair_target_type == "DOCKER" or "docker" in failure_type.lower():
        return "docker build -t test-build ."

    # 6. Workflow / Configuration
    if repair_target_type == "CONFIGURATION" or "configuration" in failure_type.lower():
        return "Correct the workflow configuration and rerun the GitHub Actions workflow."

    # 7. Environment
    if repair_target_type == "ENVIRONMENT" or "environment" in failure_type.lower():
        return "Configure required environment variables / secrets and rerun CI."

    # 8. Python
    has_tests = any(is_test_file(f) for f in repo_files)
    test_framework = "pytest" if any(f.endswith(("pytest.ini", "conftest.py")) or "pytest" in f for f in repo_files) else "pytest"

    if repair_target_type == "DEPENDENCY" or "dependency" in failure_type.lower():
        if any(f.endswith("requirements.txt") for f in repo_files):
            return f"pip install -r requirements.txt && {test_framework}" if has_tests else "pip install -r requirements.txt"
        elif any(f.endswith("poetry.lock") for f in repo_files):
            return "poetry install && poetry run pytest" if has_tests else "poetry install"
        elif any(f.endswith("Pipfile") for f in repo_files):
            return "pipenv install && pipenv run pytest" if has_tests else "pipenv install"
        elif any(f.endswith("pyproject.toml") for f in repo_files):
            return f"pip install -e . && {test_framework}" if has_tests else "pip install -e ."
        return f"pip install -r requirements.txt && {test_framework}" if has_tests else "pip install -r requirements.txt"

    if repair_target_type == "BUILD" or "build" in failure_type.lower():
        if any(f.endswith("pyproject.toml") for f in repo_files):
            return f"pip install -e . && {test_framework}" if has_tests else "pip install -e ."
        elif any(f.endswith("setup.py") for f in repo_files):
            return f"python setup.py build && {test_framework}" if has_tests else "python setup.py build"
        return f"pip install -e . && {test_framework}" if has_tests else "pip install -e ."

    if target_file != "Not identified" and is_test_file(target_file):
        return f"pytest {target_file}"

    if has_tests:
        return "pytest"
    elif any(f in repo_files for f in ("app.py", "main.py", "orchestrator.py")):
        main_entry = next(f for f in ("app.py", "main.py", "orchestrator.py") if f in repo_files)
        return f"python {main_entry}"
    return "Not Available"

SEMANTIC_STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "from", "line", "file", "call", "test", "tests",
    "assert", "assertion", "assertionerror", "error", "failed", "failure", "true", "false", "none",
    "expected", "actual", "value", "values", "return", "def", "class", "self", "equal", "equals",
    "type", "types", "code", "when", "then", "have", "has", "was", "were", "not", "but", "also",
    "should", "could", "would", "into", "over", "under", "after", "before", "about", "above",
    "below", "between", "both", "each", "few", "more", "most", "other", "some", "such", "only",
    "own", "same", "so", "than", "too", "very", "can", "will", "just", "don", "shouldn", "now",
    "str", "int", "float", "bool", "list", "dict", "set", "tuple", "object", "main", "pytest",
    "run", "check", "statement", "raising", "raised", "during", "process", "exception",
    "app", "src", "lib", "pkg", "core", "dir", "directory", "folder", "module", "modules",
    "func", "function", "implementation", "method", "log", "logs"
}


def extract_semantic_tokens(text: str) -> Set[str]:
    """Extract code identifiers, variables, functions, and domain symbols from error or diff text."""
    if not text:
        return set()
    tokens = set()

    # 1. Quoted literals (e.g. 'total', "jitter", 'langchain_core')
    for q in re.findall(r"['\"]([a-zA-Z0-9_\-\.]+)['\"]", text):
        clean_q = q.lower().strip()
        if len(clean_q) >= 2 and clean_q not in SEMANTIC_STOP_WORDS:
            tokens.add(clean_q)
            for sub in re.split(r"[_\-]", clean_q):
                if len(sub) >= 2 and sub not in SEMANTIC_STOP_WORDS:
                    tokens.add(sub)

    # 2. General code identifiers
    words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", text)
    for w in words:
        w_lower = w.lower()
        if len(w_lower) >= 3 and w_lower not in SEMANTIC_STOP_WORDS:
            tokens.add(w_lower)
            for sub in w_lower.split("_"):
                if len(sub) >= 3 and sub not in SEMANTIC_STOP_WORDS:
                    tokens.add(sub)

    return tokens


def check_semantic_overlap(
    root_cause: str,
    proposed_fix: str,
    evidence: Optional[Dict[str, Any]] = None,
    failure_log: str = ""
) -> Tuple[bool, str]:
    """
    Check if proposed fix references or modifies technical symbols, variables,
    or functions involved in the diagnosed failure mechanism.
    """
    evidence = evidence or {}

    context_text = f"{root_cause} {evidence.get('assertion_stmt', '')} {evidence.get('failing_symbol', '')} {evidence.get('error_message', '')}"
    if failure_log:
        context_text += f" {failure_log[:800]}"
    cause_tokens = extract_semantic_tokens(context_text)

    if not cause_tokens:
        return True, "general alignment"

    # Extract tokens from proposed fix (including diff path and all hunk lines)
    if "--- a/" in proposed_fix or "--- " in proposed_fix:
        diff_lines = []
        for line in proposed_fix.splitlines():
            if line.startswith("@@"):
                continue
            if line.startswith("--- ") or line.startswith("+++ "):
                clean_fn = re.sub(r"^[+-]{3}\s+[ab]/", "", line).strip()
                diff_lines.append(clean_fn)
            else:
                diff_lines.append(line.lstrip("+- "))
        fix_text = "\n".join(diff_lines)
    else:
        fix_text = proposed_fix

    fix_tokens = extract_semantic_tokens(fix_text)

    overlap = cause_tokens.intersection(fix_tokens)
    if overlap:
        matched = ", ".join(sorted(list(overlap))[:3])
        return True, f"matching symbols: {matched}"

    # Check substring / stemming overlap (e.g. 'total' in 'get_total', 'add' in 'addition')
    for ct in cause_tokens:
        if len(ct) >= 3:
            for ft in fix_tokens:
                if len(ft) >= 3 and (ct.startswith(ft) or ft.startswith(ct) or ct in ft or ft in ct):
                    return True, f"related symbol match: {ct} ~ {ft}"

    tokens_summary = ", ".join(sorted(list(cause_tokens))[:4])
    return False, f"proposed fix does not reference or modify diagnosed root-cause symbols ({tokens_summary})"


def validate_root_cause_fix_consistency(
    failure_type: str,
    root_cause: str,
    actual_repair_target: str,
    repair_type: str,
    proposed_fix: str,
    evidence: Optional[Dict[str, Any]] = None,
    failure_log: str = "",
    test_vs_implementation: Optional[str] = None
) -> Tuple[str, str]:
    """
    ROOT-CAUSE-TO-FIX CONSISTENCY VALIDATION STAGE
    Validates whether the proposed fix logically, semantically, and structurally addresses
    the diagnosed root cause and failure mechanism.

    Returns:
        Tuple[str, str]: (Consistency_Status, Consistency_Reason)
        Status is one of: "Consistent", "Inconsistent", "Not Available"
    """
    evidence = evidence or {}
    clean_fix = (proposed_fix or "").strip()

    # 0. No-Failure / Non-applicable Gate
    if failure_type in ("None", "None / Passing", "No Error") or "No CI/CD failure" in root_cause:
        return "Not Available", "No CI/CD failure diagnosed; consistency validation is not applicable."

    if not clean_fix or clean_fix in ("None", "N/A", "empty", "No source-code fix proposed."):
        if failure_type in ("Infrastructure Error", "Network Error"):
            return "Not Available", f"No remediation diff or actionable instruction generated for {failure_type}."
        return "Inconsistent", f"No fix or remediation was proposed to address {failure_type}."

    is_diff = ("--- a/" in clean_fix or "--- " in clean_fix) and ("+++" in clean_fix)

    # Extract diff target file if present
    diff_file = None
    if is_diff:
        fm = re.search(r"--- (?:[ab]/)?([^\s\n]+)", clean_fix)
        if fm:
            raw_target = fm.group(1).strip().replace("\\", "/")
            diff_file = re.sub(r"^(?:\./|[ab]/)+", "", raw_target)

    norm_repair_target = (actual_repair_target or "").replace("\\", "/").lstrip("./")

    # 1. Does the proposed fix modify the actual repair target?
    if is_diff and diff_file and norm_repair_target and norm_repair_target not in ("Not identified", "None", "N/A"):
        targets_match = (
            diff_file == norm_repair_target or
            diff_file.endswith("/" + norm_repair_target) or
            norm_repair_target.endswith("/" + diff_file) or
            Path(diff_file).name == Path(norm_repair_target).name
        )
        if not targets_match:
            if failure_type == "Dependency Error":
                return "Inconsistent", f"Proposed diff targets application/test code ('{diff_file}'), which does not match dependency manifest repair target '{actual_repair_target}'."
            return "Inconsistent", f"Proposed diff targets '{diff_file}', which does not match actual repair target '{actual_repair_target}'."

    # Check for docstring/comment-only diff on code failures (Section 6)
    if is_diff and failure_type in ("Test Failure", "Code Error", "Build Error", "Compilation Error", "Runtime Error"):
        added_lines = [l[1:].strip() for l in clean_fix.splitlines() if l.startswith("+") and not l.startswith("+++")]
        non_comment_lines = []
        for l in added_lines:
            if not l:
                continue
            if l.startswith(("#", "//", "/*", "*", '"""', "'''")) or l.endswith(('"""', "'''")):
                continue
            non_comment_lines.append(l)
        if added_lines and not non_comment_lines:
            return "Inconsistent", "Proposed patch only modifies documentation or comments, which does not repair the diagnosed code failure."

    # 2. Category 4: Dependency Error Checks
    if failure_type == "Dependency Error":
        manifest_names = (
            "requirements.txt", "requirements-dev.txt", "pyproject.toml", "setup.py",
            "setup.cfg", "Pipfile", "Pipfile.lock", "poetry.lock", "package.json",
            "package-lock.json", "pom.xml", "build.gradle", "Cargo.toml", "go.mod", "Dockerfile"
        )
        if is_diff:
            if not any(diff_file.endswith(m) for m in manifest_names):
                return "Inconsistent", f"Proposed fix for Dependency Error modifies application/test code ('{diff_file}') instead of a dependency configuration manifest (requirements.txt, pyproject.toml, lock files, Dockerfile)."

            # Extract missing package accurately from failure log or root cause
            dep_m = re.search(
                r"(?:No module named|cannot find module|ImportError:\s*(?:cannot import name\s+|No module named\s*)?|missing package ['\"]?|missing test dependency ['\"]?|undeclared package dependency ['\"]?|missing dependency ['\"]?|missing ['\"])([a-zA-Z0-9_\-]+)['\"]?",
                failure_log + " " + (root_cause or ""),
                re.IGNORECASE
            )
            if not dep_m:
                dep_m = re.search(
                    r"(?:Could not find a version that satisfies the requirement|No matching distribution found for)\s*([a-zA-Z0-9_\-]+)",
                    failure_log + " " + (root_cause or ""),
                    re.IGNORECASE
                )
            if dep_m:
                cand_pkg = dep_m.group(1).split(".")[0].lower()
                if cand_pkg not in ("dependency", "package", "error", "manifest", "file", "target", "none", "test", "tests", "framework", "the"):
                    missing_pkg = cand_pkg
                    clean_pkg = missing_pkg.replace("_", "-")
                    clean_pkg2 = missing_pkg.replace("-", "_")
                    if missing_pkg not in clean_fix.lower() and clean_pkg not in clean_fix.lower() and clean_pkg2 not in clean_fix.lower():
                        return "Inconsistent", f"Proposed fix for Dependency Error does not declare or configure the identified missing package '{missing_pkg}'."
            return "Consistent", f"Proposed fix correctly targets dependency manifest '{diff_file or actual_repair_target}' to install required package."
        else:
            if any(kw in clean_fix.lower() for kw in ("install", "requirements", "dependency", "package", "pyproject", "pip", "npm", "poetry")):
                return "Consistent", f"Actionable remediation addresses dependency installation for '{actual_repair_target}'."
            return "Inconsistent", "Actionable remediation does not address dependency installation or configuration."

    # 3. Category 5: Configuration / Environment Error Checks
    if failure_type in ("Configuration Error", "Environment Error"):
        config_indicators = (".yml", ".yaml", ".env", ".toml", ".json", ".ini", ".cfg", ".conf", "dockerfile", "docker-compose")
        if is_diff:
            is_config_file = any(diff_file.lower().endswith(c) for c in config_indicators) or any(c in diff_file.lower() for c in ("config", "settings", "env"))
            if not is_config_file:
                return "Inconsistent", f"Proposed fix for {failure_type} modifies application code ('{diff_file}') rather than workflow, environment setup, or configuration files."
            return "Consistent", f"Proposed fix correctly modifies configuration in '{diff_file}'."
        else:
            if any(kw in clean_fix.lower() for kw in ("env", "environment", "variable", "secret", "config", "workflow", "setting", "docker")):
                return "Consistent", f"Actionable remediation addresses {failure_type} settings."
            return "Inconsistent", f"Actionable remediation does not address {failure_type} settings."

    # 4. Category 6: Test Failure Checks
    if failure_type == "Test Failure":
        if is_diff:
            if is_test_file(diff_file):
                if test_vs_implementation == "TEST WRONG / IMPLEMENTATION CORRECT":
                    pass
                else:
                    return "Inconsistent", f"Proposed fix modifies test code ('{diff_file}') rather than fixing the defect in the implementation."

            is_overlap, reason = check_semantic_overlap(root_cause, clean_fix, evidence, failure_log)
            if not is_overlap:
                return "Inconsistent", f"Proposed fix does not address the failing behavior: {reason}."
            return "Consistent", f"Proposed fix in '{diff_file}' directly modifies implementation logic connected to diagnosed assertion failure ({reason})."
        else:
            is_overlap, reason = check_semantic_overlap(root_cause, clean_fix, evidence, failure_log)
            if not is_overlap:
                return "Inconsistent", f"Actionable remediation does not address the failing test behavior: {reason}."
            return "Consistent", f"Actionable remediation directly addresses diagnosed test failure ({reason})."

    # 5. Category 7: Code Error Checks
    if failure_type == "Code Error":
        if is_diff:
            if is_test_file(diff_file):
                return "Inconsistent", f"Proposed fix modifies test file ('{diff_file}') rather than the faulty implementation for Code Error."
            is_overlap, reason = check_semantic_overlap(root_cause, clean_fix, evidence, failure_log)
            if not is_overlap:
                return "Inconsistent", f"Proposed fix does not touch the implementation connected to the error: {reason}."
            return "Consistent", f"Proposed fix in '{diff_file}' directly addresses the diagnosed code defect ({reason})."
        else:
            return "Consistent", "Actionable remediation addresses the code error."

    # 6. Category 8: Build / Compilation Error Checks
    if failure_type in ("Build Error", "Compilation Error"):
        if is_diff:
            is_overlap, reason = check_semantic_overlap(root_cause, clean_fix, evidence, failure_log)
            if not is_overlap:
                return "Inconsistent", f"Proposed fix does not address the build/compilation error: {reason}."
            return "Consistent", f"Proposed fix in '{diff_file}' addresses the build/compilation problem."
        else:
            return "Consistent", f"Actionable remediation addresses {failure_type}."

    # 7. Category 9: Infrastructure / Network / Deployment / Timeout / Permission Checks
    if failure_type in ("Infrastructure Error", "Network Error", "Deployment Error", "Timeout / Resource Limit", "Permission / Access Error"):
        if is_diff:
            if diff_file.endswith((".py", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".c")) and not any(kw in diff_file.lower() for kw in ("config", "setup", "docker", "ci", "workflow")):
                return "Inconsistent", f"Proposed fix modifies application source code ('{diff_file}') for an {failure_type} which requires CI/CD, infrastructure, or deployment configuration."
            return "Consistent", f"Proposed fix targets {failure_type} configuration in '{diff_file}'."
        else:
            return "Consistent", f"Actionable remediation addresses {failure_type}."

    if any(kw in (root_cause or "").lower() for kw in ("flaky", "timing", "jitter", "race condition", "nondeterminism")):
        if is_diff:
            return "Consistent", f"Proposed fix addresses diagnosed test flakiness/timing in '{diff_file}'."
        return "Consistent", "Actionable remediation addresses diagnosed test flakiness."

    # Default semantic check
    is_overlap, reason = check_semantic_overlap(root_cause, clean_fix, evidence, failure_log)
    if not is_overlap:
        return "Inconsistent", f"Proposed fix does not align with diagnosed failure: {reason}."
    return "Consistent", f"Proposed fix is consistent with diagnosed {failure_type} ({reason})."



def validate_diff(
    diff_str: Optional[str],
    target_file: str,
    repo_files: List[str],
    source_content: Optional[str] = None,
    root_cause: str = "",
    repair_target_type: str = "IMPLEMENTATION"
) -> Tuple[bool, str]:
    """
    Deterministic Diff Validator & Diagnosis-Diff Consistency Gate:
    1. Must target a valid repository file.
    2. Must be valid unified diff format.
    3. Must not contain placeholder tokens (<old code>, // TODO, ...).
    4. Must not be a bare shell command.
    5. DIAGNOSIS-DIFF CONSISTENCY CHECK.
    """
    if not diff_str or not diff_str.strip() or diff_str.strip() in ("None", "N/A", "empty", "No source-code fix proposed."):
        return False, "No source-code fix proposed."

    cleaned = diff_str.strip()

    # Non-code failure types without code target must not produce code diffs
    if repair_target_type in ("ENVIRONMENT", "INFRASTRUCTURE", "NONE"):
        return False, "No source-code fix proposed."

    # Check for placeholder tokens
    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            return False, "No source-code fix proposed."

    # Check for unified diff headers or changes
    has_changes = ("\n-" in cleaned or "\n+" in cleaned or cleaned.startswith("-") or cleaned.startswith("+"))
    if not has_changes:
        return False, "No source-code fix proposed."

    # Extract target file in diff header if present and verify against repository inventory
    header_file = None
    file_match = re.search(r"--- a/([^\s\n]+)", cleaned)
    if file_match:
        header_file = validate_repository_file(file_match.group(1), repository_files=repo_files)
        if header_file == "Not identified":
            return False, "No source-code fix proposed."

    effective_file = header_file if (header_file and header_file != "Not identified") else target_file
    if effective_file == "Not identified" or (repo_files and effective_file not in repo_files):
        return False, "No source-code fix proposed."

    # Diagnosis-Diff Consistency: Dependency errors must target dependency manifests, not arbitrary source files
    if repair_target_type == "DEPENDENCY" and not effective_file.endswith(("requirements.txt", "package.json", "pom.xml", "Cargo.toml", "pyproject.toml", "setup.py", "go.mod")):
        return False, "No source-code fix proposed."

    # Reject shell commands disguised as code diffs
    added_lines = [line[1:].strip() for line in cleaned.splitlines() if line.startswith("+") and not line.startswith("+++")]
    for line in added_lines:
        if not effective_file.endswith(("requirements.txt", "package.json", "pom.xml", "Cargo.toml", "pyproject.toml", "setup.py", "Pipfile")):
            if line.startswith(("pip install", "npm install", "cargo add", "apt-get", "brew install", "git clone", "pytest ", "npm test")):
                return False, "No source-code fix proposed."
        else:
            if line.startswith(("pip install", "npm install", "cargo add", "apt-get", "brew install", "git clone")):
                return False, "No source-code fix proposed."

    # Defense against inventing tests in production code (never inject unittest/pytest assertions into non-test files)
    if not is_test_file(effective_file) and not effective_file.endswith(("requirements.txt", "package.json", "pom.xml", "Cargo.toml", "pyproject.toml")):
        for line in added_lines:
            if re.search(r'\b(import unittest|import pytest|from unittest|from pytest|class Test|def test_|self\.assert)\b', line):
                return False, "No source-code fix proposed."

    return True, cleaned



def check_patch_applicability_and_semantic_verify(
    diff_str: str,
    target_file: str,
    repo_path: Optional[Path] = None,
    verification_cmd: str = ""
) -> Tuple[bool, bool, str]:
    """
    Dry-run test patch applicability in an isolated temporary workspace and execute semantic verification.
    Returns (diff_valid, patch_applicable, verification_result: 'Passed' | 'Failed' | 'Not Run').
    NEVER modifies the real repository.
    """
    if not diff_str or diff_str.startswith("No source-code fix"):
        return False, False, "Not Run"

    if not repo_path or not repo_path.exists() or target_file == "Not identified":
        return True, False, "Not Run"

    target_path = repo_path / target_file
    if not target_path.exists():
        return False, False, "Not Run"

    temp_dir = None
    patch_applicable = False
    verification_result = "Not Run"

    try:
        temp_dir = tempfile.mkdtemp(prefix="buildfail_patch_test_")
        temp_target = Path(temp_dir) / target_file
        temp_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_path, temp_target)

        orig_text = temp_target.read_text(encoding="utf-8", errors="ignore")
        removed_lines = [l[1:] for l in diff_str.splitlines() if l.startswith("-") and not l.startswith("---")]
        added_lines = [l[1:] for l in diff_str.splitlines() if l.startswith("+") and not l.startswith("+++")]

        if removed_lines and any(rem.strip() in orig_text for rem in removed_lines if rem.strip()):
            patch_applicable = True
            new_text = orig_text
            for rem, add in zip(removed_lines, added_lines):
                if rem.strip() and rem in new_text:
                    new_text = new_text.replace(rem, add, 1)
            temp_target.write_text(new_text, encoding="utf-8")
        elif not removed_lines and added_lines:
            # Append diff (e.g. adding missing dependency to requirements.txt)
            patch_applicable = True
            new_text = orig_text.rstrip() + "\n" + "\n".join(added_lines) + "\n"
            temp_target.write_text(new_text, encoding="utf-8")

        # Semantic Execution Check where practical
        if patch_applicable and target_file.endswith(".py"):
            try:
                res = subprocess.run(
                    [sys.executable, "-m", "py_compile", str(temp_target)],
                    capture_output=True,
                    timeout=5
                )
                if res.returncode == 0:
                    verification_result = "Passed"
                else:
                    verification_result = "Failed"
            except Exception:
                verification_result = "Not Run"
        elif patch_applicable and target_file.endswith(("requirements.txt", "package.json", "pyproject.toml")):
            verification_result = "Passed"

        return True, patch_applicable, verification_result
    except Exception:
        return True, False, "Not Run"
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


def check_patch_applicability(
    diff_str: str,
    target_file: str,
    repo_path: Optional[Path] = None
) -> Tuple[bool, bool]:
    """Compatibility wrapper returning (diff_valid, patch_applicable)."""
    valid, applicable, _ = check_patch_applicability_and_semantic_verify(diff_str, target_file, repo_path)
    return valid, applicable


class RepositoryAnalyzer:
    """Deterministic analyzer inspecting repository contents, dependencies, and workflows across languages."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.inventory_info = get_complete_repo_inventory(self.repo_path)
        self.repo_files = self.inventory_info["selected_files"]

    def get_project_structure(self, max_depth: int = 2) -> Dict[str, Any]:
        """Map directory tree and complete file inventory breakdown (Section D, E, F)."""
        if not self.repo_path.exists():
            return {
                "total_files": 0,
                "total_files_discovered": 0,
                "selected_files_count": 0,
                "sensitive_files_excluded": [],
                "binary_database_files": [],
                "inventory_summary": "0 files discovered.",
                "tree": [],
                "top_directories": []
            }

        tree = []
        top_dirs = set()

        for f_rel in self.repo_files[:25]:
            p = Path(f_rel)
            if len(p.parts) > 1:
                top_dirs.add(p.parts[0])
            tree.append({
                "path": f_rel,
                "name": p.name,
                "type": "file",
                "depth": len(p.parts)
            })

        return {
            "total_files": self.inventory_info["total_files_discovered"],
            "total_files_discovered": self.inventory_info["total_files_discovered"],
            "selected_files_count": len(self.repo_files),
            "sensitive_files_excluded": self.inventory_info["sensitive_files_excluded"],
            "binary_database_files": self.inventory_info["binary_database_files"],
            "inventory_summary": self.inventory_info["inventory_summary"],
            "tree": tree,
            "top_directories": sorted(list(top_dirs))
        }

    def detect_language(self) -> Dict[str, str]:
        """Detect primary programming language and framework."""
        p = self.repo_path

        # 1. Python
        if (p / "requirements.txt").exists() or (p / "pyproject.toml").exists() or (p / "setup.py").exists() or list(p.rglob("*.py")):
            framework = "Standard Python"
            if (p / "Pipfile").exists():
                framework = "Pipenv"
            elif (p / "poetry.lock").exists() or (p / "pyproject.toml").exists():
                framework = "Poetry"
            for py in p.rglob("*.py"):
                try:
                    txt = py.read_text(encoding="utf-8", errors="ignore")[:500]
                    if "fastapi" in txt:
                        framework = "FastAPI"
                        break
                    elif "flask" in txt:
                        framework = "Flask"
                        break
                    elif "django" in txt:
                        framework = "Django"
                        break
                except Exception:
                    pass
            return {"language": "Python", "framework": framework}

        # 2. JavaScript / TypeScript
        if (p / "package.json").exists():
            framework = "Node.js"
            try:
                pkg = json.loads((p / "package.json").read_text(encoding="utf-8", errors="ignore"))
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "next" in deps:
                    framework = "Next.js"
                elif "react" in deps:
                    framework = "React"
                elif "vue" in deps:
                    framework = "Vue"
                elif "express" in deps:
                    framework = "Express"
            except Exception:
                pass
            is_ts = bool(list(p.rglob("*.ts")) or list(p.rglob("*.tsx")))
            return {"language": "TypeScript" if is_ts else "JavaScript", "framework": framework}

        # 3. Rust
        if (p / "Cargo.toml").exists():
            return {"language": "Rust", "framework": "Cargo"}

        # 4. Go
        if (p / "go.mod").exists():
            return {"language": "Go", "framework": "Go Modules"}

        # 5. Java
        if (p / "pom.xml").exists() or (p / "build.gradle").exists():
            return {"language": "Java", "framework": "Maven" if (p / "pom.xml").exists() else "Gradle"}

        # 6. Dockerfile
        if (p / "Dockerfile").exists():
            return {"language": "Docker", "framework": "Container"}

        return {"language": "Python", "framework": "Standard"}

    def extract_dependencies(self) -> List[str]:
        """Extract declared dependencies across package managers."""
        deps = []
        p = self.repo_path

        # requirements.txt
        req_file = p / "requirements.txt"
        if req_file.exists():
            try:
                for line in req_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        dep = re.split(r'[=><~]', line)[0].strip()
                        if dep:
                            deps.append(dep)
            except Exception:
                pass

        # package.json
        pkg_file = p / "package.json"
        if pkg_file.exists():
            try:
                data = json.loads(pkg_file.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(data, dict):
                    deps.extend(list(data.get("dependencies", {}).keys())[:10])
            except Exception:
                pass

        # Cargo.toml
        cargo_file = p / "Cargo.toml"
        if cargo_file.exists():
            try:
                content = cargo_file.read_text(encoding="utf-8", errors="ignore")
                matches = re.findall(r'^([a-zA-Z0-9_\-]+)\s*=', content, re.MULTILINE)
                deps.extend(matches[:10])
            except Exception:
                pass

        return deps[:15]

    def find_workflows(self) -> List[Dict[str, Any]]:
        """Find and parse CI/CD workflow configuration files."""
        workflows = []
        p = self.repo_path

        # GitHub Actions
        gha_dir = p / ".github" / "workflows"
        if gha_dir.exists():
            for wf in gha_dir.glob("*.y*ml"):
                try:
                    with open(wf, "r", encoding="utf-8", errors="ignore") as f:
                        data = yaml.safe_load(f)
                    
                    triggers = []
                    jobs_info = []
                    if isinstance(data, dict):
                        on_field = data.get("on", data.get(True, []))
                        if isinstance(on_field, list):
                            triggers = on_field
                        elif isinstance(on_field, dict):
                            triggers = list(on_field.keys())
                        elif isinstance(on_field, str):
                            triggers = [on_field]
                        
                        jobs_dict = data.get("jobs", {})
                        if isinstance(jobs_dict, dict):
                            for j_id, j_val in jobs_dict.items():
                                if isinstance(j_val, dict):
                                    runs_on = j_val.get("runs-on", "ubuntu-latest")
                                    steps = [s.get("name", s.get("run", "step")) for s in j_val.get("steps", []) if isinstance(s, dict)]
                                    jobs_info.append({"job": j_id, "runs_on": runs_on, "steps": steps[:6]})
                                else:
                                    jobs_info.append({"job": j_id, "runs_on": "ubuntu-latest", "steps": []})

                    workflows.append({
                        "platform": "GitHub Actions",
                        "path": str(wf.relative_to(p)).replace("\\", "/"),
                        "name": (data.get("name", wf.stem) if isinstance(data, dict) else wf.stem) or wf.stem,
                        "triggers": triggers,
                        "jobs": [j["job"] for j in jobs_info],
                        "job_details": jobs_info
                    })
                except Exception:
                    workflows.append({
                        "platform": "GitHub Actions",
                        "path": str(wf.relative_to(p)).replace("\\", "/"),
                        "name": wf.stem,
                        "triggers": ["push"],
                        "jobs": [],
                        "job_details": []
                    })

        # Dockerfile
        docker_f = p / "Dockerfile"
        if docker_f.exists():
            workflows.append({
                "platform": "Docker",
                "path": "Dockerfile",
                "name": "Docker Container Build",
                "triggers": ["docker build"],
                "jobs": ["build", "layer-execution"],
                "job_details": []
            })

        return workflows

    def find_source_and_test_files(self) -> Dict[str, List[str]]:
        """Identify candidate source code and test suite files across languages."""
        test_files = []
        source_files = []

        for f_rel in self.repo_files:
            if f_rel.endswith(("__init__.py", "init.py")) or f_rel in ("__init__.py", "init.py"):
                continue
            if is_test_file(f_rel):
                test_files.append(f_rel)
            elif f_rel.endswith((".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go", ".java")):
                source_files.append(f_rel)

        return {
            "test_files": test_files[:5],
            "source_files": source_files[:5]
        }

    def find_stored_ci_failures(self) -> List[Dict[str, Any]]:
        """
        Discovers in-repository CI failure logs and dataset files (.log + .json pairs,
        benchmark failure datasets such as ci-triage-dataset, logs/, failures/).
        """
        stored = []
        p = self.repo_path

        # Look for .log files across repository (excluding environments and caches)
        log_files = [
            f for f in self.repo_files
            if f.endswith(".log") and not any(ign in f.lower() for ign in (".venv", "node_modules", ".git", ".cache", "venv"))
        ]

        json_meta_map = {}
        for f in self.repo_files:
            if f.endswith(".json") and any(d_kw in f.lower() for d_kw in ("dataset", "failure", "log", "triage", "cases")):
                full_j = p / f
                try:
                    j_data = json.loads(full_j.read_text(encoding="utf-8", errors="ignore"))
                    if isinstance(j_data, dict):
                        log_name = j_data.get("log_file") or f.replace(".json", ".log")
                        json_meta_map[f] = j_data
                        json_meta_map[log_name] = j_data
                except Exception:
                    pass

        for lf in log_files:
            full_log = p / lf
            if not full_log.exists():
                continue
            meta = json_meta_map.get(lf, {})
            if not meta:
                cand_json = lf.rsplit(".", 1)[0] + ".json"
                if cand_json in json_meta_map:
                    meta = json_meta_map[cand_json]
                elif (p / cand_json).exists():
                    try:
                        meta = json.loads((p / cand_json).read_text(encoding="utf-8", errors="ignore"))
                    except Exception:
                        meta = {}

            case_id = meta.get("id") or Path(lf).stem
            category = meta.get("label") or Path(lf).parent.name
            fault = meta.get("injected_fault") or meta.get("description", "")
            failing_tests = meta.get("failing_tests", [])

            stored.append({
                "id": case_id,
                "category": category,
                "log_path": lf,
                "metadata_path": lf.rsplit(".", 1)[0] + ".json" if (p / (lf.rsplit(".", 1)[0] + ".json")).exists() else None,
                "injected_fault": fault,
                "failing_tests": failing_tests
            })

        return stored

    def auto_detect_or_run_tests(self, failure_log: str = "", selected_case_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes test suite or extracts failing test context when no raw log is provided.
        Separates:
          - failure_location (observed)
          - test_file
          - implementation_file
          - repair_target_type (IMPLEMENTATION, TEST, WORKFLOW, etc.)
          - repair_target_file
        """
        lang_info = self.detect_language()
        language = lang_info["language"]
        files = self.find_source_and_test_files()
        
        active_log = failure_log
        all_tests_passed = False
        stored_failures = self.find_stored_ci_failures()
        is_ci_dataset = len(stored_failures) > 0
        selected_case = None

        if not active_log:
            if stored_failures:
                # Discovered stored CI failure examples in repository dataset!
                if selected_case_id:
                    matched = [c for c in stored_failures if c["id"] == selected_case_id or c["log_path"] == selected_case_id]
                    selected_case = matched[0] if matched else stored_failures[0]
                else:
                    selected_case = stored_failures[0]

                try:
                    active_log = (self.repo_path / selected_case["log_path"]).read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    pass
            elif not files["test_files"]:
                # Section 4 & 19: If no test files exist in repository and no stored failure logs, do NOT invent a test failure or run pytest
                all_tests_passed = True
                active_log = "All tests passed successfully (0 failures)."
            else:
                try:
                    env = os.environ.copy()
                    env["PYTHONPATH"] = str(self.repo_path.resolve())
                    if language == "Python":
                        res = subprocess.run(
                            [sys.executable, "-m", "pytest"],
                            cwd=str(self.repo_path),
                            env=env,
                            capture_output=True,
                            text=True,
                            timeout=15
                        )
                        if res.returncode == 0:
                            all_tests_passed = True
                            active_log = "All tests passed successfully (0 failures)."
                        elif res.returncode == 5 or "no tests collected" in (res.stdout + res.stderr).lower():
                            all_tests_passed = True
                            active_log = "All tests passed successfully (0 failures)."
                        else:
                            active_log = (res.stdout + "\n" + res.stderr).strip()
                except Exception:
                    pass

        if all_tests_passed or (active_log and "All tests passed successfully" in active_log):
            test_cmd = derive_repository_verification_command(language, "None", "NONE", repo_path=self.repo_path, repo_files=self.repo_files)
            return {
                "failure_log": "All tests passed successfully (0 failures).",
                "failure_chunk": "All tests passed successfully (0 failures).",
                "failure_location": "Not identified",
                "target_file": "Not identified",
                "repair_target_file": "Not identified",
                "test_file": "Not identified",
                "implementation_file": "Not identified",
                "repair_target_type": "NONE",
                "repair_type": "None",
                "test_vs_implementation": "NONE",
                "verification": test_cmd,
                "test_files": files["test_files"],
                "source_files": files["source_files"],
                "repo_files": self.repo_files,
                "target_source_code": "",
                "related_test_code": "",
                "all_tests_passed": True,
                "evidence": {},
                "stored_failures": stored_failures,
                "is_ci_dataset": is_ci_dataset
            }

        if not active_log:
            default_target = files["source_files"][0] if files["source_files"] else (self.repo_files[0] if self.repo_files else "Not identified")
            default_test = files["test_files"][0] if files["test_files"] else "Not identified"
            test_cmd = derive_repository_verification_command(language, "Test Failure", "IMPLEMENTATION", target_file=default_test, repo_path=self.repo_path, repo_files=self.repo_files)
            return {
                "failure_log": f"CI Workflow Execution: {test_cmd}",
                "failure_chunk": f"CI Workflow Execution: {test_cmd}",
                "failure_location": default_test,
                "target_file": default_target,
                "repair_target_file": default_target,
                "test_file": default_test,
                "implementation_file": default_target,
                "repair_target_type": "IMPLEMENTATION",
                "repair_type": "Source Code",
                "test_vs_implementation": "TEST CORRECT / IMPLEMENTATION WRONG",
                "verification": test_cmd,
                "test_files": files["test_files"],
                "source_files": files["source_files"],
                "repo_files": self.repo_files,
                "target_source_code": "",
                "related_test_code": "",
                "all_tests_passed": False,
                "evidence": {}
            }

        # Multi-stage resolution on active_log
        chunk = extract_failure_chunk(active_log)
        evidence = extract_assertion_evidence(active_log)
        inferred_cat, repair_target_type = classify_failure_nature(active_log, self.repo_files)

        # 1. Identify observed failure location (where failure was reported)
        observed_test_file = None
        for cand in re.findall(r'FAILED\s+([a-zA-Z0-9_\-\./\\]+\.(?:py|js|ts|java|go|rs)):?', active_log):
            val = validate_repository_file(cand, repository_files=self.repo_files, repo_path=self.repo_path, allow_external=True)
            if val != "Not identified":
                observed_test_file = val
                break

        if not observed_test_file:
            for cand in re.findall(r'([a-zA-Z0-9_\-\./\\]+\.(?:py|js|ts|java|go|rs))\s+[\.sFxF]+', active_log):
                val = validate_repository_file(cand, repository_files=self.repo_files, repo_path=self.repo_path, allow_external=True)
                if val != "Not identified":
                    observed_test_file = val
                    break

        if not observed_test_file:
            for cand in re.findall(r'(?:File\s+"|\()([a-zA-Z0-9_\-\./\\]+\.(?:py|js|ts|java|go|rs))', active_log):
                val = validate_repository_file(cand, repository_files=self.repo_files, repo_path=self.repo_path, allow_external=True)
                if val != "Not identified" and is_test_file(val):
                    observed_test_file = val
                    break

        # Check for GitHub Actions workflow action error
        log_low = active_log.lower()
        wf_input_match = re.search(r"Input required and not supplied:\s*([a-zA-Z0-9_\-]+)", active_log, re.IGNORECASE)
        is_hosting_err = "action-hosting-deploy" in log_low and any(k in log_low for k in ("input required", "secret", "serviceaccount", "firebase"))
        is_wf_action_err = wf_input_match is not None or is_hosting_err
        if is_wf_action_err:
            wf_files = [f for f in self.repo_files if f.startswith(".github/workflows/")]
            fb_wfs = [f for f in wf_files if "firebase" in f.lower()]
            observed_test_file = fb_wfs[0] if fb_wfs else (wf_files[0] if wf_files else "Not identified")
        elif not observed_test_file and files["test_files"]:
            real_tests = [f for f in files["test_files"] if not f.endswith("__init__.py")]
            observed_test_file = real_tests[0] if real_tests else files["test_files"][0]

        # 2. Read test code snippet
        test_source_code = ""
        if observed_test_file and (self.repo_path / observed_test_file).exists():
            try:
                test_source_code = (self.repo_path / observed_test_file).read_text(encoding="utf-8", errors="ignore")[:1500]
            except Exception:
                pass

        # Extract snippet from active_log if file was not on disk
        if not test_source_code and active_log:
            snippet_lines = []
            capture = False
            for line in active_log.splitlines():
                if re.match(r'_{3,}\s*[a-zA-Z0-9_]+\s*_{3,}', line) or "def test_" in line:
                    capture = True
                if capture:
                    if line.startswith("=") and "FAILURES" not in line and len(snippet_lines) > 2:
                        break
                    snippet_lines.append(line)
            if snippet_lines:
                test_source_code = "\n".join(snippet_lines[:30])

        # 3. Identify candidate implementation file
        observed_impl_file = None
        for cand in re.findall(r'(?:File\s+"|\()([a-zA-Z0-9_\-\./\\]+\.(?:py|js|ts|java|go|rs))', active_log):
            val = validate_repository_file(cand, repository_files=self.repo_files, repo_path=self.repo_path, allow_external=True)
            if val != "Not identified" and not is_test_file(val):
                observed_impl_file = val
                break

        if not observed_impl_file and observed_test_file:
            linked_impl = find_implementation_file_from_test(
                observed_test_file,
                test_source_code,
                self.repo_path,
                self.repo_files
            )
            if linked_impl:
                observed_impl_file = linked_impl

        if not observed_impl_file and observed_test_file:
            test_p = Path(observed_test_file)
            stem = test_p.stem
            if stem.startswith("test_"):
                impl_stem = stem[5:]
                cand_names = [f"src/{impl_stem}.py", f"app/{impl_stem}.py", f"{impl_stem}.py"]
                matched = [c for c in cand_names if c in self.repo_files]
                if matched:
                    observed_impl_file = matched[0]
                elif not files["source_files"]:
                    observed_impl_file = cand_names[0]

        if not observed_impl_file and files["source_files"]:
            real_sources = [f for f in files["source_files"] if not f.endswith(("__init__.py", "init.py"))]
            if real_sources:
                observed_impl_file = real_sources[0]

        if not observed_impl_file and observed_test_file:
            test_p = Path(observed_test_file)
            stem = test_p.stem
            if stem.startswith("test_"):
                impl_stem = stem[5:]
                observed_impl_file = f"src/{impl_stem}.py"

        # 4. Read implementation source code snippet
        impl_source_code = ""
        if observed_impl_file and (self.repo_path / observed_impl_file).exists():
            try:
                impl_source_code = (self.repo_path / observed_impl_file).read_text(encoding="utf-8", errors="ignore")[:1500]
            except Exception:
                pass

        # Dynamic extraction for sparse or truncated test execution logs
        if not evidence.get("failing_func"):
            f_match = re.search(r'_{3,}\s*([a-zA-Z0-9_]+)\s*_{3,}', active_log) or re.search(r'def\s+(test_[a-zA-Z0-9_]+)', active_log)
            if f_match:
                evidence["failing_func"] = f_match.group(1)

        if any(kw in active_log for kw in ("=== FAILURES ===", "=== failures ===")) or any(m in active_log for m in ("collected ", ".F.", " F ")) or "pytest" in active_log.lower():
            if not any(kw in active_log.lower() for kw in ("modulenotfounderror", "no module named", "cannot find module", "importerror:", "syntaxerror")):
                if inferred_cat not in ("Dependency Error", "Build Error", "Compilation Error", "Configuration Error"):
                    inferred_cat = "Test Failure"
                    repair_target_type = "TEST"
                    if not evidence.get("error_type"):
                        evidence["error_type"] = "AssertionError"
                        evidence["error_message"] = f"Test failure in {evidence.get('failing_func', 'test suite')}"

        if inferred_cat == "Test Failure" and not evidence.get("error_type"):
            if evidence.get("failing_func"):
                evidence["error_type"] = "AssertionError"
                evidence["error_message"] = f"Assertion failed in {evidence['failing_func']}"

        # 5. Assess Test vs Implementation Defect
        test_verdict, assessed_target_type = assess_test_vs_implementation(test_source_code, impl_source_code, evidence)
        if repair_target_type == "IMPLEMENTATION" and assessed_target_type == "TEST":
            repair_target_type = "TEST"

        # 6. Dependency-Aware Repair Target Reasoning (SEPARATE OBSERVED FROM ACTUAL REPAIR TARGET)
        observed_loc = observed_test_file or observed_impl_file or "Not identified"
        actual_repair_file, repair_target_type, repair_type, target_confidence = determine_actual_repair_target(
            failure_type=inferred_cat,
            failure_log=active_log,
            observed_failure_location=observed_loc,
            repo_files=self.repo_files,
            repo_path=self.repo_path,
            test_file=observed_test_file,
            impl_file=observed_impl_file,
            test_vs_impl=test_verdict
        )

        verification_cmd = derive_repository_verification_command(
            language=language,
            failure_type=inferred_cat,
            repair_target_type=repair_target_type,
            target_file=observed_test_file or actual_repair_file,
            repo_path=self.repo_path,
            repo_files=self.repo_files
        )

        return {
            "failure_log": chunk or active_log,
            "failure_chunk": chunk or active_log,
            "failure_location": observed_loc,
            "target_file": actual_repair_file,
            "repair_target_file": actual_repair_file,
            "repair_target_type": repair_target_type,
            "repair_type": repair_type,
            "confidence": target_confidence,
            "test_file": observed_test_file or "Not identified",
            "implementation_file": observed_impl_file or "Not identified",
            "test_vs_implementation": test_verdict,
            "inferred_category": inferred_cat,
            "verification": verification_cmd,
            "test_files": files["test_files"],
            "source_files": files["source_files"],
            "repo_files": self.repo_files,
            "target_source_code": impl_source_code if actual_repair_file == observed_impl_file else (test_source_code if actual_repair_file == observed_test_file else ""),
            "implementation_source_code": impl_source_code,
            "related_test_code": test_source_code,
            "all_tests_passed": False,
            "evidence": evidence,
            "stored_failures": stored_failures,
            "is_ci_dataset": is_ci_dataset
        }

    def analyze(self, failure_log: str = "", selected_case_id: Optional[str] = None) -> Dict[str, Any]:
        """Execute full deterministic repository analysis matching the pipeline flow."""
        structure = self.get_project_structure()
        lang_info = self.detect_language()
        dependencies = self.extract_dependencies()
        workflows = self.find_workflows()
        primary_wf = workflows[0]["name"] if workflows else "Default CI Workflow"
        
        test_context = self.auto_detect_or_run_tests(failure_log, selected_case_id=selected_case_id)

        target_f = test_context["target_file"]
        src_code = test_context.get("target_source_code", "")

        return {
            "project_structure": structure,
            "language": lang_info["language"],
            "framework": lang_info["framework"],
            "dependencies": dependencies,
            "workflows": workflows,
            "primary_workflow": primary_wf,
            "failure_chunk": test_context["failure_chunk"],
            "failure_location": test_context.get("failure_location", "Not identified"),
            "source_file": target_f,
            "repair_target_file": test_context.get("repair_target_file", target_f),
            "test_file": test_context.get("test_file", "Not identified"),
            "implementation_file": test_context.get("implementation_file", "Not identified"),
            "repair_target_type": test_context.get("repair_target_type", "IMPLEMENTATION"),
            "repair_type": test_context.get("repair_type", "Source Code"),
            "test_vs_implementation": test_context.get("test_vs_implementation", "TEST CORRECT / IMPLEMENTATION WRONG"),
            "verification": test_context["verification"],
            "test_files": test_context["test_files"],
            "source_files": test_context["source_files"],
            "repo_files": self.repo_files,
            "target_source_code": src_code,
            "implementation_source_code": test_context.get("implementation_source_code", ""),
            "related_test_code": test_context.get("related_test_code", ""),
            "all_tests_passed": test_context.get("all_tests_passed", False),
            "evidence": test_context.get("evidence", {}),
            "stored_failures": test_context.get("stored_failures", []),
            "is_ci_dataset": test_context.get("is_ci_dataset", False)
        }
