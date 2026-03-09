from __future__ import annotations

from dataclasses import replace

from slackbot_for_web.config import Settings
from slackbot_for_web.models import AgentResult, QaRunRequest
from slackbot_for_web.webqa_runner import run_web_qa_with_gemini_api, run_web_qa_with_openai_api

FULL_WEB_QA_PRESET = "full_web_qa"


class QaEngine:
    """Core QA execution engine. Channel adapters (e.g., Slack) should call this."""

    def __init__(self, settings: Settings):
        self._settings = settings

    def run(self, request: QaRunRequest) -> AgentResult:
        effective_request = request
        if (request.mode_key or "").strip().lower() != FULL_WEB_QA_PRESET:
            effective_request = replace(request, mode_key=FULL_WEB_QA_PRESET)

        agent = (effective_request.agent or "").strip().lower()
        if agent == "gemini":
            return run_web_qa_with_gemini_api(self._settings, effective_request)
        if agent in {"openai", "codex"}:
            return run_web_qa_with_openai_api(self._settings, effective_request)
        if agent == "claude":
            return AgentResult(
                status="needs_review",
                summary="Claude engine path is scaffolded but not wired yet.",
                raw_output=(
                    "TODO: implement Claude execution path.\n"
                    f"Received URL={effective_request.url}, mode_key={effective_request.mode_key}"
                ),
                started_at=effective_request.request_ts,
                completed_at=effective_request.request_ts,
                step_logs=["step: engine placeholder"],
            )
        raise ValueError(f"Unsupported agent: {effective_request.agent}")
