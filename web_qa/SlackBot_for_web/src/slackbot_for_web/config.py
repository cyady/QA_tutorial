from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from slackbot_for_web.validation_models import summarize_validation_error


@dataclass(frozen=True)
class Settings:
    slack_bot_token: str
    slack_app_token: str
    default_agent: str
    gemini_api_key: str
    gemini_model: str
    gemini_fallback_models: tuple[str, ...]
    gemini_timeout_seconds: int
    gemini_max_remote_calls: int
    openai_api_key: str
    openai_model: str
    openai_timeout_seconds: int
    use_langgraph: bool
    hard_timeout_minutes: int
    vibium_mcp_command: str
    vibium_mcp_args: str
    devtools_mcp_command: str
    devtools_mcp_args: str
    artifact_root: str
    mode_store_path: str
    slack_verbose_output: bool
    memory_embedding_backend: str
    memory_embedding_model: str
    memory_compare_models: tuple[str, ...]

    @property
    def preset_store_path(self) -> str:
        return self.mode_store_path


class _SettingsValidationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slack_bot_token: str
    slack_app_token: str
    default_agent: str
    gemini_api_key: str
    gemini_model: str
    gemini_fallback_models: tuple[str, ...]
    gemini_timeout_seconds: int
    gemini_max_remote_calls: int
    openai_api_key: str
    openai_model: str
    openai_timeout_seconds: int
    use_langgraph: bool
    hard_timeout_minutes: int
    vibium_mcp_command: str
    vibium_mcp_args: str
    devtools_mcp_command: str
    devtools_mcp_args: str
    artifact_root: str
    mode_store_path: str
    slack_verbose_output: bool
    memory_embedding_backend: str
    memory_embedding_model: str
    memory_compare_models: tuple[str, ...]

    @field_validator(
        "default_agent",
        "gemini_model",
        "openai_model",
        "vibium_mcp_command",
        "vibium_mcp_args",
        "devtools_mcp_command",
        "devtools_mcp_args",
        "artifact_root",
        "mode_store_path",
        "memory_embedding_backend",
        "memory_embedding_model",
        mode="before",
    )
    @classmethod
    def _normalize_strings(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("gemini_timeout_seconds", "gemini_max_remote_calls", "openai_timeout_seconds", mode="before")
    @classmethod
    def _coerce_positive_runtime_limits(cls, value: object) -> int:
        try:
            number = int(value)
        except Exception:  # noqa: BLE001
            number = 0
        return max(1, number)

    @field_validator("hard_timeout_minutes", mode="before")
    @classmethod
    def _coerce_timeout_minutes(cls, value: object) -> int:
        try:
            number = int(value)
        except Exception:  # noqa: BLE001
            number = 60
        return max(1, number)


def load_settings(require_slack_tokens: bool = True) -> Settings:
    project_root = Path(__file__).resolve().parents[2]
    slack_bot_token = _read_env("SLACK_BOT_TOKEN")
    slack_app_token = _read_env("SLACK_APP_TOKEN")

    if require_slack_tokens:
        if not slack_bot_token:
            raise ValueError("SLACK_BOT_TOKEN is required")
        if not slack_app_token:
            raise ValueError("SLACK_APP_TOKEN is required")
    gemini_api_key = _read_env("GEMINI_API_KEY") or _read_env("GOOGLE_API_KEY")
    openai_api_key = _read_env("OPENAI_API_KEY")

    raw_settings = {
        "slack_bot_token": slack_bot_token,
        "slack_app_token": slack_app_token,
        "default_agent": os.getenv("DEFAULT_AGENT", "gemini").strip().lower(),
        "gemini_api_key": gemini_api_key,
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
        "gemini_fallback_models": _parse_csv_list(os.getenv("GEMINI_FALLBACK_MODELS", "")),
        "gemini_timeout_seconds": int(os.getenv("GEMINI_TIMEOUT_SECONDS", "300")),
        "gemini_max_remote_calls": int(os.getenv("GEMINI_MAX_REMOTE_CALLS", "5000")),
        "openai_api_key": openai_api_key,
        "openai_model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip(),
        "openai_timeout_seconds": int(os.getenv("OPENAI_TIMEOUT_SECONDS", "300")),
        "use_langgraph": _parse_bool(_read_env("USE_LANGGRAPH", "true")),
        "hard_timeout_minutes": int(os.getenv("HARD_TIMEOUT_MINUTES", "60")),
        "vibium_mcp_command": os.getenv("VIBIUM_MCP_COMMAND", "npx").strip(),
        "vibium_mcp_args": os.getenv("VIBIUM_MCP_ARGS", "vibium mcp --headless").strip(),
        "devtools_mcp_command": os.getenv("DEVTOOLS_MCP_COMMAND", "").strip(),
        "devtools_mcp_args": os.getenv("DEVTOOLS_MCP_ARGS", "").strip(),
        "artifact_root": _resolve_path(project_root, os.getenv("ARTIFACT_ROOT", "artifacts").strip()),
        "mode_store_path": _resolve_path(
            project_root,
            os.getenv(
                "PROMPT_MODE_STORE",
                os.getenv("PROMPT_PRESET_STORE", "artifacts/_runtime/custom_presets.json").strip(),
            ).strip(),
        ),
        "slack_verbose_output": _parse_bool(_read_env("SLACK_VERBOSE_OUTPUT", "false")),
        "memory_embedding_backend": os.getenv("MEMORY_EMBEDDING_BACKEND", "sentence_transformers").strip().lower(),
        "memory_embedding_model": os.getenv(
            "MEMORY_EMBEDDING_MODEL",
            "intfloat/multilingual-e5-large-instruct",
        ).strip(),
        "memory_compare_models": _parse_csv_list(
            os.getenv(
                "MEMORY_COMPARE_MODELS",
                "intfloat/multilingual-e5-large-instruct",
            )
        ),
    }

    try:
        validated = _SettingsValidationModel.model_validate(raw_settings)
    except ValidationError as exc:
        raise ValueError(f"Invalid environment settings: {summarize_validation_error(exc)}") from exc

    return Settings(**validated.model_dump())


def _parse_csv_list(raw: str) -> tuple[str, ...]:
    values: list[str] = []
    for chunk in (raw or "").split(","):
        value = chunk.strip()
        if value:
            values.append(value)
    return tuple(values)


def _resolve_path(project_root: Path, raw_path: str) -> str:
    path = Path(raw_path) if raw_path else Path("artifacts")
    if not path.is_absolute():
        path = project_root / path
    return str(path.resolve())


def _read_env(key: str, default: str = "") -> str:
    # Handle accidental UTF-8 BOM on the first .env key (e.g., "\ufeffSLACK_BOT_TOKEN").
    value = os.getenv(key)
    if value is None:
        value = os.getenv("\ufeff" + key)
    if value is None:
        value = default
    return str(value).strip()


def _parse_bool(raw: str) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}
