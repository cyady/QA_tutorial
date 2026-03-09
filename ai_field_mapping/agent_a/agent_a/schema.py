from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


SemanticType = Literal[
    "budget",
    "team_size",
    "people_count",
    "target_population",
    "case_metric",
    "lead_volume",
    "sales_activity",
    "timeline",
    "duration",
    "match_rate",
    "attrition_rate",
    "action_item",
    "constraint",
    "risk_or_concern",
    "collaboration_need",
    "kpi_definition",
    "deliverable_scope",
    "tool_or_channel",
    "stakeholder_or_team",
    "other",
]

ValueType = Literal[
    "currency",
    "number",
    "number_range",
    "percentage",
    "percentage_range",
    "date_expression",
    "duration",
    "email",
    "text",
    "text_list",
]


class Segment(BaseModel):
    segment_id: str
    section_path: list[str] = Field(default_factory=list)
    text: str
    start_char: int
    end_char: int


class Mention(BaseModel):
    segment_id: str
    section_path: list[str] = Field(default_factory=list)
    exact_quote: str
    start_char: int
    end_char: int


class Candidate(BaseModel):
    candidate_id: str = ""
    kind: Literal["hard", "soft"]
    semantic_type: SemanticType
    value_type: ValueType
    raw_text: str
    normalized: dict[str, Any] | None = None
    mentions: list[Mention] = Field(default_factory=list)
    dedupe_key: str
    confidence: float = 0.0


class ExtractionMetadata(BaseModel):
    extractor: str = "agent_a"
    version: str = "0.1.0"
    llm_enabled: bool
    prompt_version: str = "A_soft_v0.1"
    created_at: str


class CandidatePoolLine(BaseModel):
    run_id: str
    memo_id: str
    candidates: list[Candidate]
    extraction_metadata: ExtractionMetadata


class SoftLLMCandidate(BaseModel):
    semantic_type: Literal[
        "action_item",
        "constraint",
        "risk_or_concern",
        "collaboration_need",
        "kpi_definition",
        "deliverable_scope",
        "stakeholder_or_team",
        "other",
    ]
    value_type: Literal["text", "text_list"] = "text"
    raw_text: str
    segment_id: str
    exact_quote: str
    confidence: float = 0.0


class SoftLLMOutput(BaseModel):
    candidates: list[SoftLLMCandidate] = Field(default_factory=list)


def export_json_schemas() -> dict[str, dict[str, Any]]:
    return {
        "candidate_pool_line": CandidatePoolLine.model_json_schema(),
        "soft_llm_output": SoftLLMOutput.model_json_schema(),
    }


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
