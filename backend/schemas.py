"""
BuildFail-SLM: Pydantic Schemas for API Requests and Responses
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class GitHubAnalysisRequest(BaseModel):
    repo_url: str = Field(..., description="GitHub repository URL (public, or private with token)")
    branch: Optional[str] = Field(None, description="Specific branch or tag to inspect")
    github_token: Optional[str] = Field(None, description="Optional GitHub Personal Access Token")
    failure_log: Optional[str] = Field(None, description="Optional raw failure log snippet")


class LocalAnalysisRequest(BaseModel):
    local_path: str = Field(..., description="Absolute or relative local directory path")
    failure_log: Optional[str] = Field(None, description="Optional raw failure log snippet")


class DiagnoseRequest(BaseModel):
    repository: Optional[str] = Field("demo/repository", description="Repository name or URL")
    language: Optional[str] = Field("Python", description="Detected programming language")
    ci_platform: Optional[str] = Field("GitHub Actions", description="Target CI/CD platform")
    workflow: Optional[str] = Field("CI", description="Failing workflow name")
    source_file: Optional[str] = Field(None, description="Localized candidate faulty file")
    failure_location: Optional[str] = Field(None, description="Observed failure location in CI log")
    repo_files: Optional[List[str]] = Field(default_factory=list, description="Available repository file paths")
    failure_log: Optional[str] = Field(None, description="Raw build or test failure log")


class RepoAnalysisResponse(BaseModel):
    repository: str
    language: str
    framework: str
    project_structure: Dict[str, Any]
    dependencies: List[str]
    workflows: List[Dict[str, Any]]
    primary_workflow: str
    failure_chunk: Optional[str] = None
    source_file: Optional[str] = None
    repo_files: Optional[List[str]] = None
    stored_failures: Optional[List[Dict[str, Any]]] = None
    is_ci_dataset: Optional[bool] = False


class FailureDiagnosisResponse(BaseModel):
    repository: str
    language: str
    ci_workflow: Optional[str] = None
    failure_type: str = Field(..., description="Classified failure category from 13-class taxonomy (No Unknown)")
    root_cause: str = Field(..., description="Technical root cause explanation")
    source_file: Optional[str] = Field(None, description="Actual Repair Target localized (or Not identified)")
    actual_repair_target: Optional[str] = Field(None, description="Actual Repair Target localized (or Not identified)")
    failure_location: Optional[str] = Field(None, description="Fault Localization / Observed Failure Location in CI log")
    fault_localization: Optional[str] = Field(None, description="Fault Localization: Where the CI/CD failure surfaced")
    repair_target_type: Optional[str] = Field("IMPLEMENTATION", description="Internal repair target classification")
    repair_type: Optional[str] = Field("Source Code", description="Repair type: Source Code, Dependency, Configuration, Environment, CI, Infrastructure, None")
    test_vs_implementation: Optional[str] = Field(None, description="Test vs implementation defect assessment")
    proposed_diff: Optional[str] = Field(None, description="Non-destructive code diff in unified format or actionable remediation")
    explanation: Optional[str] = Field(None, description="Detailed explanation of the diagnosis and patch")
    suggested_fix: Optional[str] = Field(None, description="Actionable suggested fix strategy")
    verification: Optional[str] = Field(None, description="Recommended remediation or verification command")
    verification_result: Optional[str] = Field("Not Run", description="Actual patch execution result (Passed, Failed, Not Run)")
    patch_verification: Optional[str] = Field("Not Available", description="Patch syntax verification (Valid, Invalid, Not Available)")
    diff_validation: Optional[str] = Field("Not Available", description="Diff Validation: Valid / Invalid / Not Available")
    patch_applicability: Optional[str] = Field("Not Run", description="Patch sandbox applicability (Passed, Failed, Not Run)")
    consistency: Optional[str] = Field("Not Available", description="Diagnosis-Fix Consistency: Consistent / Inconsistent / Not Available")
    consistency_reason: Optional[str] = Field(None, description="Technical rationale for consistency validation")
    semantic_fix_validity: Optional[str] = Field("Not Available", description="Semantic Fix Validity: Valid / Invalid / Not Available")
    confidence: Optional[str] = Field("High", description="Model confidence (High, Medium, Low)")
    is_repaired: bool = False
    diff_valid: bool = False
    multiple_failures: Optional[Dict[str, Any]] = None
    diagnosis_evidence: Optional[Dict[str, Any]] = None
    execution_diagnostics: Optional[Dict[str, Any]] = None



class FullPipelineResponse(BaseModel):
    repository_analysis: RepoAnalysisResponse
    diagnosis: FailureDiagnosisResponse


