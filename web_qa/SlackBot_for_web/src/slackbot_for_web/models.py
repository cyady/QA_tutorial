from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class QaRunRequest:
    agent: str
    url: str
    mode_key: str
    custom_prompt: str
    user_id: str = ""
    channel_id: str = ""
    thread_channel_id: str | None = None
    thread_ts: str | None = None
    request_ts: str = field(default_factory=now_iso)
    job_id: str = field(default_factory=lambda: f"JOB-{uuid4().hex[:8]}")

    @property
    def prompt_preset(self) -> str:
        return self.mode_key


@dataclass(frozen=True)
class AgentResult:
    status: str
    summary: str
    raw_output: str
    started_at: str
    completed_at: str
    step_logs: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    summary_lines: list[str] = field(default_factory=list)
    top3_deep_dive_candidates: list[str] = field(default_factory=list)
    artifact_paths: list[str] = field(default_factory=list)
    token_usage: dict[str, int] = field(default_factory=dict)
