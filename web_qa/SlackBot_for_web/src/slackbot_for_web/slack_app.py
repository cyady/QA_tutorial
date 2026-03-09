from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from slack_bolt import App
from slack_sdk import WebClient

from slackbot_for_web.config import Settings
from slackbot_for_web.models import QaRunRequest
from slackbot_for_web.queue_worker import JobQueueWorker
from slackbot_for_web.slack_messaging import safe_post_message

_LOG = logging.getLogger(__name__)

DELETE_ACTION_ID = "delete_bot_message"
USER_FACING_PRESET_KEY = "full_web_qa"
USER_FACING_MODE_LABEL = "Full QA (E2E)"
USER_FACING_AGENT_FALLBACK = "openai"


def build_slack_app(settings: Settings) -> App:
    app = App(token=settings.slack_bot_token)
    worker = JobQueueWorker(settings=settings, client=WebClient(token=settings.slack_bot_token))
    _append_runtime_event(
        settings,
        "app_init",
        {"default_agent": settings.default_agent, "artifact_root": settings.artifact_root},
    )

    @app.command("/webqa")
    def open_webqa_modal(ack, body, client, logger):
        ack()
        channel_id = str(body.get("channel_id", "")).strip()
        user_id = str(body.get("user_id", "")).strip()
        request_thread_ts = _read_thread_ts(body)
        seed_text = body.get("text", "")
        if not isinstance(seed_text, str):
            seed_text = ""

        _append_runtime_event(
            settings,
            "slash_command_received",
            {
                "channel_id": channel_id,
                "user_id": user_id,
                "thread_ts": request_thread_ts,
                "text_len": len(seed_text),
            },
        )

        try:
            client.views_open(
                trigger_id=body["trigger_id"],
                view=_build_modal_view(
                    settings=settings,
                    channel_id=channel_id,
                    user_id=user_id,
                    request_thread_ts=request_thread_ts,
                    seed_text=seed_text.strip(),
                ),
            )
            _append_runtime_event(
                settings,
                "modal_opened",
                {"channel_id": channel_id, "user_id": user_id, "thread_ts": request_thread_ts},
            )
        except Exception as exc:  # noqa: BLE001
            _append_runtime_event(
                settings,
                "modal_open_failed",
                {
                    "channel_id": channel_id,
                    "user_id": user_id,
                    "thread_ts": request_thread_ts,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            if channel_id or user_id:
                _safe_post_message(
                    client=client,
                    primary_channel=channel_id or user_id,
                    fallback_user_id=user_id,
                    text=f"Web QA modal open failed: `{type(exc).__name__}: {exc}`",
                )
            logger.exception("Failed to open modal: %s", exc)

    @app.action(DELETE_ACTION_ID)
    def delete_bot_message(ack, body, client, logger):
        ack()
        try:
            channel = body.get("channel", {})
            message = body.get("message", {})
            channel_id = channel.get("id") if isinstance(channel, dict) else ""
            message_ts = message.get("ts") if isinstance(message, dict) else ""
            user_id = _read_user_id(body)
            if not isinstance(channel_id, str) or not channel_id.strip():
                raise ValueError("missing channel id in delete action payload")
            if not isinstance(message_ts, str) or not message_ts.strip():
                raise ValueError("missing message ts in delete action payload")

            client.chat_delete(channel=channel_id.strip(), ts=message_ts.strip())
            _append_runtime_event(
                settings,
                "message_deleted",
                {"channel_id": channel_id, "ts": message_ts, "actor_user_id": user_id},
            )
        except Exception as exc:  # noqa: BLE001
            _append_runtime_event(
                settings,
                "message_delete_failed",
                {
                    "channel_id": channel_id if isinstance(channel_id, str) else "",
                    "ts": message_ts if isinstance(message_ts, str) else "",
                    "actor_user_id": user_id if isinstance(user_id, str) else "",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            logger.exception("Failed to delete bot message: %s", exc)

    @app.view("webqa_submit")
    def submit_webqa(ack, body, client, logger):
        acked = False
        channel_id = ""
        user_id = ""
        try:
            view = body.get("view", {})
            values = (view.get("state") or {}).get("values", {})
            url = _read_value(values, "url_block", "url_action")
            agent = _resolve_user_facing_agent(settings.default_agent)
            mode_key = USER_FACING_PRESET_KEY
            custom_prompt = ""
            meta = _read_private_metadata(view.get("private_metadata"))
            channel_id = meta.get("channel_id", "") or _read_channel_id(body)
            user_id = meta.get("user_id", "") or _read_user_id(body)
            request_thread_ts = meta.get("thread_ts", "") or _read_thread_ts(body)

            _append_runtime_event(
                settings,
                "modal_submit_received",
                {
                    "channel_id": channel_id,
                    "user_id": user_id,
                    "thread_ts": request_thread_ts,
                    "agent": agent,
                    "mode": USER_FACING_MODE_LABEL,
                    "url_preview": _trim_text(url, 200),
                },
            )

            errors: dict[str, str] = {}
            if not _is_valid_http_url(url):
                errors["url_block"] = "Enter a valid URL starting with http:// or https://"

            if errors:
                ack(response_action="errors", errors=errors)
                _append_runtime_event(
                    settings,
                    "modal_submit_validation_error",
                    {"channel_id": channel_id, "user_id": user_id, "errors": errors},
                )
                return

            ack()
            acked = True

            if not channel_id:
                raise ValueError("Missing channel_id in modal metadata.")
            if not user_id:
                raise ValueError("Missing user_id in modal metadata.")

            job = QaRunRequest(
                user_id=user_id,
                channel_id=channel_id,
                agent=agent,
                url=url,
                mode_key=mode_key,
                custom_prompt=custom_prompt,
            )

            _persist_submit_snapshot(
                settings=settings,
                job=job,
                payload={
                    "job_id": job.job_id,
                    "channel_id": job.channel_id,
                    "user_id": job.user_id,
                    "request_thread_ts": request_thread_ts,
                    "agent": job.agent,
                    "preset": job.mode_key,
                    "mode": job.mode_key,
                    "mode_label": USER_FACING_MODE_LABEL,
                    "url": job.url,
                    "custom_prompt_len": len(job.custom_prompt),
                    "received_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            queued_channel, queued_ts = _safe_post_message(
                client=client,
                primary_channel=job.channel_id,
                fallback_user_id=job.user_id,
                thread_ts=request_thread_ts or None,
                text=(
                    f"[{job.job_id}] queued by <@{job.user_id}>.\n"
                    f"Agent: `{job.agent}` | Mode: `{USER_FACING_MODE_LABEL}`\n"
                    f"URL: {job.url}"
                ),
            )
            logger.info(
                "Queued job=%s user=%s requested_channel=%s resolved_channel=%s thread_ts=%s",
                job.job_id,
                job.user_id,
                job.channel_id,
                queued_channel,
                queued_ts,
            )
            _append_runtime_event(
                settings,
                "job_queued",
                {
                    "job_id": job.job_id,
                    "channel_id": job.channel_id,
                    "user_id": job.user_id,
                    "resolved_channel": queued_channel,
                    "request_thread_ts": request_thread_ts,
                    "thread_ts": queued_ts,
                },
            )

            job = replace(job, thread_channel_id=queued_channel, thread_ts=(queued_ts or request_thread_ts or None))
            worker.enqueue(job)
        except Exception as exc:  # noqa: BLE001
            if not acked:
                ack()
            _append_runtime_event(
                settings,
                "modal_submit_failed",
                {
                    "channel_id": channel_id,
                    "user_id": user_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            if channel_id or user_id:
                _safe_post_message(
                    client=client,
                    primary_channel=channel_id or user_id,
                    fallback_user_id=user_id,
                    text=f"Web QA submit failed before queue: `{type(exc).__name__}: {exc}`",
                )
            logger.exception("Failed to submit webqa job: %s", exc)

    @app.error
    def global_error_handler(error, body, logger):
        _append_runtime_event(
            settings,
            "bolt_error",
            {
                "error_type": type(error).__name__,
                "error": str(error),
                "body_type": type(body).__name__,
            },
        )
        logger.exception("Unhandled Bolt error: %s", error)

    return app


def _build_modal_view(
    settings: Settings,
    channel_id: str,
    user_id: str,
    request_thread_ts: str,
    seed_text: str,
) -> dict[str, Any]:
    default_agent = _resolve_user_facing_agent(settings.default_agent)
    blocks: list[dict[str, Any]] = [
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"*실행 모드:* `{USER_FACING_MODE_LABEL}`  "
                        f"*엔진:* `{default_agent}`\n"
                        "사용자 선택 모드는 제공하지 않으며, 동일 도메인 기준 E2E Full QA로 실행됩니다."
                    ),
                }
            ],
        },
        {
            "type": "input",
            "block_id": "url_block",
            "label": {"type": "plain_text", "text": "Target URL"},
            "element": {
                "type": "plain_text_input",
                "action_id": "url_action",
                "placeholder": {
                    "type": "plain_text",
                    "text": "https://example.com",
                },
                "initial_value": seed_text if seed_text else "",
            },
        },
    ]

    return {
        "type": "modal",
        "callback_id": "webqa_submit",
        "title": {"type": "plain_text", "text": "Web QA"},
        "submit": {"type": "plain_text", "text": "Run"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": json.dumps(
            {"channel_id": channel_id, "user_id": user_id, "thread_ts": request_thread_ts}
        ),
        "blocks": blocks,
    }
def _read_value(values: dict[str, Any], block_id: str, action_id: str) -> str:
    block = values.get(block_id, {})
    action = block.get(action_id, {}) if isinstance(block, dict) else {}
    value = action.get("value", "") if isinstance(action, dict) else ""
    return value.strip() if isinstance(value, str) else ""


def _is_valid_http_url(raw: str) -> bool:
    parsed = urlparse(raw.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _safe_post_message(
    client,
    primary_channel: str,
    fallback_user_id: str,
    text: str,
    thread_ts: str | None = None,
) -> tuple[str, str | None]:
    return safe_post_message(
        client=client,
        primary_channel=primary_channel,
        fallback_user_id=fallback_user_id,
        text=text,
        delete_action_id=DELETE_ACTION_ID,
        logger=_LOG,
        thread_ts=thread_ts,
    )


def _read_private_metadata(raw: Any) -> dict[str, str]:
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(parsed, dict):
        return {}
    channel_id = str(parsed.get("channel_id", "")).strip()
    user_id = str(parsed.get("user_id", "")).strip()
    thread_ts = str(parsed.get("thread_ts", "")).strip()
    return {"channel_id": channel_id, "user_id": user_id, "thread_ts": thread_ts}


def _read_channel_id(body: dict[str, Any]) -> str:
    if not isinstance(body, dict):
        return ""
    channel = body.get("channel")
    if isinstance(channel, dict):
        channel_id = channel.get("id")
        if isinstance(channel_id, str):
            return channel_id.strip()
    channel_id = body.get("channel_id")
    if isinstance(channel_id, str):
        return channel_id.strip()
    return ""


def _read_user_id(body: dict[str, Any]) -> str:
    if not isinstance(body, dict):
        return ""
    user = body.get("user")
    if isinstance(user, dict):
        user_id = user.get("id")
        if isinstance(user_id, str):
            return user_id.strip()
    user_id = body.get("user_id")
    if isinstance(user_id, str):
        return user_id.strip()
    return ""


def _read_thread_ts(body: dict[str, Any]) -> str:
    if not isinstance(body, dict):
        return ""
    thread_ts = body.get("thread_ts")
    if isinstance(thread_ts, str):
        return thread_ts.strip()
    return ""


def _persist_submit_snapshot(settings: Settings, job: QaRunRequest, payload: dict[str, Any]) -> None:
    artifact_dir = Path(settings.artifact_root) / job.job_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = artifact_dir / "submitted.json"
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_runtime_event(settings: Settings, event: str, payload: dict[str, Any]) -> None:
    try:
        runtime_log = Path(settings.artifact_root) / "_runtime" / "slack_events.log"
        runtime_log.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "payload": payload,
        }
        with runtime_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        # Logging path issues should never break the request flow.
        return


def _trim_text(value: str, limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _fit_modal_text(value: str, limit: int = 2900) -> str:
    text = value if isinstance(value, str) else ""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _resolve_user_facing_agent(raw: str) -> str:
    normalized = (raw or "").strip().lower()
    if normalized in {"gemini", "openai"}:
        return normalized
    return USER_FACING_AGENT_FALLBACK
