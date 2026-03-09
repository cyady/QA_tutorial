from __future__ import annotations

SYSTEM_PROMPT = """You extract field-like candidate snippets from meeting memo segments.
Rules:
- Use ONLY evidence found in the provided segments.
- Never invent content.
- Output JSON only that matches the provided schema.
- Include exact_quote copied from segment text and segment_id.
- Prefer high recall for action items, constraints, risks, collaboration needs, KPI definitions, deliverable scope, stakeholder/team mentions.
"""


def build_user_prompt(segments: list[dict[str, str]]) -> str:
    return (
        "Extract soft candidates from these segments.\\n"
        "Segments JSON:\\n"
        f"{segments}"
    )
