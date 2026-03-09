from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class TokenUsageModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @field_validator("prompt_tokens", "completion_tokens", "total_tokens", mode="before")
    @classmethod
    def _coerce_non_negative_int(cls, value: Any) -> int:
        try:
            number = int(value)
        except Exception:  # noqa: BLE001
            number = 0
        return max(0, number)


class ResultArtifactModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    job_id: str
    agent: str
    preset: str
    mode: str = ""
    url: str
    status: Literal["pass", "fail", "needs_review"]
    summary: str
    summary_lines: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    screenshot_refs: list[str] = Field(default_factory=list)
    top3_deep_dive_candidates: list[str] = Field(default_factory=list)
    external_navigation_events: list[dict[str, Any]] = Field(default_factory=list)
    execution_log: list[str] = Field(default_factory=list)
    token_usage: TokenUsageModel = Field(default_factory=TokenUsageModel)
    step_logs: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    raw_output_file: str | None = None
    started_at: str
    completed_at: str


class TestCaseResultSummaryModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    total: int = 0
    pass_count: int = Field(default=0, alias="pass")
    fail: int = 0
    needs_review: int = 0

    @field_validator("total", "pass_count", "fail", "needs_review", mode="before")
    @classmethod
    def _coerce_summary_int(cls, value: Any) -> int:
        try:
            number = int(value)
        except Exception:  # noqa: BLE001
            number = 0
        return max(0, number)


class TestCaseResultItemModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    case_id: str
    status: Literal["pass", "fail", "needs_review"]
    status_reason: str
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def _normalize_evidence_refs(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]


class TestCaseResultsArtifactModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int
    run_id: str
    stage: Literal["test_case_results"]
    created_at: str
    summary: TestCaseResultSummaryModel
    results: list[TestCaseResultItemModel] = Field(default_factory=list)


class QaReportCoverageSummaryModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    canonical_host: str = ""
    visited_count: int = 0
    visited_urls: list[str] = Field(default_factory=list)
    external_navigation_events: list[dict[str, Any]] = Field(default_factory=list)
    map_stop_reason: str = "completed"


class QaReportFindingModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    page_url: str | None = None
    severity: Literal["P0", "P1", "P2", "P3"] = "P3"
    type: str
    observation: str
    why_it_matters: str
    next_check: str
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("severity", mode="before")
    @classmethod
    def _normalize_severity(cls, value: Any) -> str:
        return str(value or "P3").upper().strip()


class QaReportArtifactModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int
    run_id: str
    stage: Literal["qa_report"]
    created_at: str
    overall_status: Literal["pass", "fail", "needs_review"]
    overall_reason: str
    status_reason: str
    summary: str
    summary_lines: list[str] = Field(default_factory=list)
    coverage_summary: QaReportCoverageSummaryModel
    findings: list[QaReportFindingModel] = Field(default_factory=list)
    deep_dive_candidates: list[str] = Field(default_factory=list)
    top3_deep_dive_candidates: list[str] = Field(default_factory=list)
    unresolved_items: list[dict[str, Any]] = Field(default_factory=list)
    token_usage: TokenUsageModel = Field(default_factory=TokenUsageModel)
    needs_review_triggers: list[str] = Field(default_factory=list)
    self_healing_policy: list[dict[str, Any]] = Field(default_factory=list)
    self_healing_attempts: list[dict[str, Any]] = Field(default_factory=list)
    refs: dict[str, str] = Field(default_factory=dict)


_ARTIFACT_MODEL_BY_FILENAME = {
    "result.json": ResultArtifactModel,
    "test_case_results.json": TestCaseResultsArtifactModel,
    "qa_report.json": QaReportArtifactModel,
}


def validate_artifact_payload(filename: str, payload: dict[str, Any]) -> dict[str, Any]:
    model_cls = _ARTIFACT_MODEL_BY_FILENAME.get(str(filename).strip().lower())
    if model_cls is None:
        return payload
    model = model_cls.model_validate(payload)
    return model.model_dump(by_alias=True)


def summarize_validation_error(error: ValidationError) -> str:
    lines: list[str] = []
    for item in error.errors():
        loc = ".".join(str(part) for part in item.get("loc") or [])
        msg = str(item.get("msg") or "invalid value")
        lines.append(f"{loc}: {msg}" if loc else msg)
    return " | ".join(lines[:6]) or str(error)
