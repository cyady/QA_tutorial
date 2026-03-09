from __future__ import annotations

import json
import os
import urllib.request
from abc import ABC, abstractmethod

from agent_a.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from agent_a.schema import Segment, SoftLLMCandidate, SoftLLMOutput


class BaseLLMClient(ABC):
    @abstractmethod
    def extract_soft_candidates(self, segments: list[Segment]) -> list[SoftLLMCandidate]:
        raise NotImplementedError


class MockLLMClient(BaseLLMClient):
    def extract_soft_candidates(self, segments: list[Segment]) -> list[SoftLLMCandidate]:
        return []


class OpenAIClient(BaseLLMClient):
    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAIClient")

    def _request(self, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            method="POST",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8")
        return json.loads(text)

    def extract_soft_candidates(self, segments: list[Segment]) -> list[SoftLLMCandidate]:
        seg_data = [{"segment_id": s.segment_id, "text": s.text} for s in segments]
        schema = SoftLLMOutput.model_json_schema()
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(seg_data)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "soft_llm_output",
                    "schema": schema,
                    "strict": True,
                },
            },
        }
        raw = self._request(payload)
        content = raw["choices"][0]["message"]["content"]
        parsed = SoftLLMOutput.model_validate_json(content)
        return parsed.candidates


def make_llm_client(enabled: bool) -> BaseLLMClient:
    if not enabled:
        return MockLLMClient()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return MockLLMClient()
    return OpenAIClient(api_key=api_key)
