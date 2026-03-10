from __future__ import annotations

import json
import logging
import threading
import unicodedata
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from slack_bolt import App
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from slackbot_for_web.config import Settings
from slackbot_for_web.models import QaRunRequest
from slackbot_for_web.queue_worker import JobQueueWorker
from slackbot_for_web.slack_messaging import safe_post_message

_LOG = logging.getLogger(__name__)

DELETE_ACTION_ID = "delete_bot_message"
USER_FACING_PRESET_KEY = "full_web_qa"
USER_FACING_MODE_LABEL = "Full QA (E2E)"
USER_FACING_AGENT_FALLBACK = "openai"
QA_MEMORY_SHORTCUT_ID = "save_thread_to_qa_memory"
QA_MEMORY_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


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

    @app.shortcut(QA_MEMORY_SHORTCUT_ID)
    def save_thread_to_qa_memory(ack, body, client, logger):
        ack()
        channel_id = _read_channel_id(body)
        user_id = _read_user_id(body)
        message_ts = _read_message_ts(body)
        thread_ts = _read_message_thread_ts(body) or message_ts

        _append_runtime_event(
            settings,
            "qa_memory_shortcut_received",
            {
                "channel_id": channel_id,
                "user_id": user_id,
                "message_ts": message_ts,
                "thread_ts": thread_ts,
            },
        )

        threading.Thread(
            target=_run_qa_memory_capture,
            kwargs={
                "settings": settings,
                "client": client,
                "logger": logger,
                "channel_id": channel_id,
                "user_id": user_id,
                "message_ts": message_ts,
                "thread_ts": thread_ts,
            },
            daemon=True,
        ).start()

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


def _safe_post_ephemeral(
    client: WebClient,
    channel_id: str,
    user_id: str,
    text: str,
    thread_ts: str | None = None,
) -> None:
    if not channel_id or not user_id:
        return
    try:
        payload: dict[str, Any] = {"channel": channel_id, "user": user_id, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        client.chat_postEphemeral(**payload)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("Slack ephemeral post failed channel=%s user=%s exc=%s", channel_id, user_id, exc)


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


def _read_message_ts(body: dict[str, Any]) -> str:
    if not isinstance(body, dict):
        return ""
    message = body.get("message")
    if isinstance(message, dict):
        ts = message.get("ts")
        if isinstance(ts, str):
            return ts.strip()
    return ""


def _read_message_thread_ts(body: dict[str, Any]) -> str:
    if not isinstance(body, dict):
        return ""
    message = body.get("message")
    if isinstance(message, dict):
        thread_ts = message.get("thread_ts")
        if isinstance(thread_ts, str) and thread_ts.strip():
            return thread_ts.strip()
    return _read_thread_ts(body)


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


def _capture_thread_to_memory(
    settings: Settings,
    client: WebClient,
    channel_id: str,
    user_id: str,
    message_ts: str,
    thread_ts: str,
) -> dict[str, Any]:
    if not channel_id:
        raise ValueError("missing channel id in shortcut payload")
    if not thread_ts:
        raise ValueError("missing thread ts in shortcut payload")

    existing_archives = _find_existing_memory_archives(settings, channel_id=channel_id, thread_ts=thread_ts)
    archive_dir = _select_canonical_memory_archive(existing_archives)
    existing_manifest: dict[str, Any] = {}
    existing_messages: list[dict[str, Any]] = []
    existing_downloads: list[dict[str, Any]] = []
    if archive_dir is None:
        memory_id = f"MEM-{uuid4().hex[:8]}"
        archive_dir = Path(settings.artifact_root) / "_memory" / memory_id
    else:
        memory_id = archive_dir.name
        existing_manifest = _read_json_if_exists(archive_dir / "thread_manifest.json", default={})
        existing_messages = _read_json_if_exists(archive_dir / "thread_messages.json", default=[])
        existing_downloads = _read_json_if_exists(archive_dir / "file_manifest.json", default=[])
    files_dir = archive_dir / "files"
    archive_dir.mkdir(parents=True, exist_ok=True)
    files_dir.mkdir(parents=True, exist_ok=True)

    messages = _fetch_thread_messages(client, channel_id=channel_id, thread_ts=thread_ts)
    existing_download_map = {
        str(item.get("id", "")).strip(): item
        for item in existing_downloads
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }
    downloads = _download_thread_files(
        client,
        messages=messages,
        files_dir=files_dir,
        existing_download_map=existing_download_map,
    )
    merged_downloads = _merge_download_records(existing=existing_downloads, fresh=downloads)
    download_map = {str(item.get("id", "")).strip(): item for item in merged_downloads if str(item.get("id", "")).strip()}
    normalized_messages = _merge_thread_messages(
        existing=existing_messages,
        fresh=[_normalize_thread_message(message, download_map=download_map) for message in messages],
    )
    captured_at = datetime.now(timezone.utc).isoformat()
    first_captured_at = str(existing_manifest.get("first_captured_at") or existing_manifest.get("captured_at") or captured_at)
    capture_count = int(existing_manifest.get("capture_count") or 0) + 1
    manifest = {
        "memory_id": memory_id,
        "channel_id": channel_id,
        "user_id": user_id,
        "message_ts": message_ts,
        "thread_ts": thread_ts,
        "thread_key": _thread_key(channel_id, thread_ts),
        "captured_at": captured_at,
        "first_captured_at": first_captured_at,
        "last_captured_at": captured_at,
        "capture_count": capture_count,
        "message_count": len(normalized_messages),
        "downloaded_file_count": sum(1 for item in merged_downloads if item.get("status") == "downloaded"),
        "skipped_file_count": sum(1 for item in merged_downloads if item.get("status") != "downloaded"),
    }

    (archive_dir / "thread_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (archive_dir / "thread_messages.json").write_text(
        json.dumps(normalized_messages, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (archive_dir / "file_manifest.json").write_text(
        json.dumps(merged_downloads, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def _run_qa_memory_capture(
    settings: Settings,
    client: WebClient,
    logger,
    channel_id: str,
    user_id: str,
    message_ts: str,
    thread_ts: str,
) -> None:
    try:
        capture = _capture_thread_to_memory(
            settings=settings,
            client=client,
            channel_id=channel_id,
            user_id=user_id,
            message_ts=message_ts,
            thread_ts=thread_ts,
        )
        _safe_post_ephemeral(
            client=client,
            channel_id=channel_id,
            user_id=user_id,
            thread_ts=thread_ts or None,
            text=(
                f"QA memory {'updated' if int(capture.get('capture_count') or 1) > 1 else 'saved'}.\n"
                f"Memory ID: `{capture['memory_id']}`\n"
                f"Messages: `{capture['message_count']}` | Downloaded files: `{capture['downloaded_file_count']}` | Captures: `{capture['capture_count']}`"
            ),
        )
        _append_runtime_event(
            settings,
            "qa_memory_shortcut_completed",
            {
                "channel_id": channel_id,
                "user_id": user_id,
                "message_ts": message_ts,
                "thread_ts": thread_ts,
                "memory_id": capture["memory_id"],
                "message_count": capture["message_count"],
                "downloaded_file_count": capture["downloaded_file_count"],
                "capture_count": capture["capture_count"],
            },
        )
    except Exception as exc:  # noqa: BLE001
        _append_runtime_event(
            settings,
            "qa_memory_shortcut_failed",
            {
                "channel_id": channel_id,
                "user_id": user_id,
                "message_ts": message_ts,
                "thread_ts": thread_ts,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        _safe_post_ephemeral(
            client=client,
            channel_id=channel_id,
            user_id=user_id,
            thread_ts=thread_ts or None,
            text=f"QA memory save failed: `{type(exc).__name__}: {exc}`",
        )
        logger.exception("Failed to save QA memory from shortcut: %s", exc)


def _fetch_thread_messages(client: WebClient, channel_id: str, thread_ts: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    cursor: str | None = None
    join_retried = False
    while True:
        payload: dict[str, Any] = {"channel": channel_id, "ts": thread_ts, "limit": 200}
        if cursor:
            payload["cursor"] = cursor
        try:
            response = client.conversations_replies(**payload)
        except SlackApiError as exc:
            error_code = str(exc.response.get("error", "")).strip()
            if error_code == "not_in_channel" and not join_retried and _can_auto_join_channel(channel_id):
                join_retried = True
                if _try_join_channel(client, channel_id):
                    continue
            raise _build_thread_access_error(channel_id=channel_id, original=exc) from exc
        batch = response.get("messages")
        if isinstance(batch, list):
            messages.extend(item for item in batch if isinstance(item, dict))
        metadata = response.get("response_metadata")
        next_cursor = metadata.get("next_cursor") if isinstance(metadata, dict) else ""
        if isinstance(next_cursor, str) and next_cursor.strip():
            cursor = next_cursor.strip()
            continue
        break
    return messages


def _normalize_thread_message(message: dict[str, Any], download_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    files = []
    for file_info in _extract_message_files(message):
        file_id = str(file_info.get("id", "")).strip()
        downloaded = download_map.get(file_id, {})
        files.append(
            {
                "id": file_id,
                "name": str(file_info.get("name", "")).strip(),
                "mimetype": str(file_info.get("mimetype", "")).strip(),
                "filetype": str(file_info.get("filetype", "")).strip(),
                "size": int(file_info.get("size") or 0),
                "permalink": str(file_info.get("permalink", "")).strip(),
                "local_path": str(downloaded.get("local_path", "")).strip(),
                "status": str(downloaded.get("status", "")).strip(),
                "download_error": str(downloaded.get("error", "")).strip(),
            }
        )

    return {
        "ts": _normalize_unicode(str(message.get("ts", "")).strip()),
        "thread_ts": _normalize_unicode(str(message.get("thread_ts", "")).strip()),
        "user": _normalize_unicode(str(message.get("user", "")).strip()),
        "subtype": _normalize_unicode(str(message.get("subtype", "")).strip()),
        "text": _normalize_unicode(str(message.get("text", "")).strip()),
        "reply_count": int(message.get("reply_count") or 0),
        "files": files,
    }


def _download_thread_files(
    client: WebClient,
    messages: list[dict[str, Any]],
    files_dir: Path,
    existing_download_map: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    existing = existing_download_map if isinstance(existing_download_map, dict) else {}
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for message in messages:
        for file_info in _extract_message_files(message):
            file_id = str(file_info.get("id", "")).strip()
            if not file_id or file_id in seen_ids:
                continue
            seen_ids.add(file_id)
            previous = existing.get(file_id)
            if previous and str(previous.get("local_path", "")).strip():
                previous_path = Path(str(previous.get("local_path", "")).strip())
                if previous_path.exists():
                    normalized = dict(previous)
                    normalized["name"] = _normalize_unicode(str(normalized.get("name", "")).strip())
                    normalized["local_path"] = str(previous_path)
                    results.append(normalized)
                    continue
            results.append(_download_slack_file(client=client, file_info=file_info, files_dir=files_dir))
    return results


def _extract_message_files(message: dict[str, Any]) -> list[dict[str, Any]]:
    raw_files = message.get("files")
    if not isinstance(raw_files, list):
        return []
    return [item for item in raw_files if isinstance(item, dict)]


def _download_slack_file(client: WebClient, file_info: dict[str, Any], files_dir: Path) -> dict[str, Any]:
    file_id = str(file_info.get("id", "")).strip()
    file_name = _normalize_unicode(str(file_info.get("name", "")).strip()) or (file_id or "attachment")
    size = int(file_info.get("size") or 0)
    if size > QA_MEMORY_MAX_DOWNLOAD_BYTES:
        return {
            "id": file_id,
            "name": file_name,
            "size": size,
            "status": "skipped_too_large",
            "local_path": "",
            "error": f"file exceeds {QA_MEMORY_MAX_DOWNLOAD_BYTES} bytes limit",
        }

    download_url = str(file_info.get("url_private_download") or file_info.get("url_private") or "").strip()
    if not download_url:
        return {
            "id": file_id,
            "name": file_name,
            "size": size,
            "status": "skipped_no_url",
            "local_path": "",
            "error": "missing url_private/url_private_download",
        }

    safe_name = _make_safe_filename(file_name, fallback=file_id or "attachment", prefix=file_id)
    target_path = files_dir / safe_name
    request = Request(download_url, headers={"Authorization": f"Bearer {client.token}"})
    try:
        with urlopen(request, timeout=60) as response:  # noqa: S310
            target_path.write_bytes(response.read())
    except HTTPError as exc:
        return {
            "id": file_id,
            "name": file_name,
            "size": size,
            "status": "download_failed",
            "local_path": "",
            "error": f"HTTPError {exc.code}",
        }
    except URLError as exc:
        return {
            "id": file_id,
            "name": file_name,
            "size": size,
            "status": "download_failed",
            "local_path": "",
            "error": f"URLError {exc.reason}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "id": file_id,
            "name": file_name,
            "size": size,
            "status": "download_failed",
            "local_path": "",
            "error": str(exc),
        }

    return {
        "id": file_id,
        "name": file_name,
        "size": size,
        "status": "downloaded",
        "local_path": str(target_path),
        "error": "",
    }


def _make_safe_filename(raw_name: str, fallback: str, prefix: str = "") -> str:
    sanitized = "".join(ch if ch not in '<>:"/\\|?*' else "_" for ch in _normalize_unicode((raw_name or "").strip()))
    sanitized = sanitized.rstrip(" .")
    if not sanitized:
        sanitized = fallback
    if prefix:
        sanitized = f"{prefix}_{sanitized}"
    return sanitized[:180]


def _thread_key(channel_id: str, thread_ts: str) -> str:
    return f"{str(channel_id or '').strip()}:{str(thread_ts or '').strip()}"


def _find_existing_memory_archives(settings: Settings, *, channel_id: str, thread_ts: str) -> list[Path]:
    memory_root = Path(settings.artifact_root) / "_memory"
    if not memory_root.exists():
        return []
    matches: list[tuple[str, Path]] = []
    target_key = _thread_key(channel_id, thread_ts)
    for directory in memory_root.iterdir():
        if not directory.is_dir() or not directory.name.startswith("MEM-"):
            continue
        manifest = _read_json_if_exists(directory / "thread_manifest.json", default={})
        if not isinstance(manifest, dict):
            continue
        candidate_key = str(manifest.get("thread_key") or _thread_key(manifest.get("channel_id", ""), manifest.get("thread_ts", ""))).strip()
        if candidate_key != target_key:
            continue
        sort_key = str(manifest.get("first_captured_at") or manifest.get("captured_at") or "")
        matches.append((sort_key, directory))
    matches.sort(key=lambda item: (item[0], item[1].name))
    return [directory for _, directory in matches]


def _select_canonical_memory_archive(matches: list[Path]) -> Path | None:
    return matches[0] if matches else None


def _read_json_if_exists(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _merge_download_records(existing: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for source in (existing, fresh):
        for item in source:
            if not isinstance(item, dict):
                continue
            file_id = str(item.get("id", "")).strip()
            if not file_id:
                continue
            if file_id not in merged:
                order.append(file_id)
                merged[file_id] = dict(item)
                continue
            current = merged[file_id]
            for key, value in item.items():
                if value not in ("", None) and value != []:
                    current[key] = value
            merged[file_id] = current
    return [merged[file_id] for file_id in order]


def _merge_thread_messages(existing: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for source in (existing, fresh):
        for item in source:
            if not isinstance(item, dict):
                continue
            ts = _normalize_unicode(str(item.get("ts", "")).strip())
            if not ts:
                continue
            candidate = dict(item)
            if ts not in merged:
                order.append(ts)
                merged[ts] = candidate
                continue
            current = merged[ts]
            for key, value in candidate.items():
                if key == "files" and isinstance(value, list):
                    current_files = current.get("files") if isinstance(current.get("files"), list) else []
                    current["files"] = _merge_file_refs(current_files, value)
                elif value not in ("", None) and value != []:
                    current[key] = value
            merged[ts] = current
    return [merged[ts] for ts in sorted(order, key=lambda value: float(value) if value.replace('.', '', 1).isdigit() else value)]


def _merge_file_refs(existing: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for source in (existing, fresh):
        for item in source:
            if not isinstance(item, dict):
                continue
            file_id = str(item.get("id", "")).strip()
            if not file_id:
                continue
            if file_id not in merged:
                order.append(file_id)
                merged[file_id] = dict(item)
                continue
            current = merged[file_id]
            for key, value in item.items():
                if value not in ("", None) and value != []:
                    current[key] = value
            merged[file_id] = current
    return [merged[file_id] for file_id in order]


def _normalize_unicode(raw: str) -> str:
    return unicodedata.normalize("NFC", str(raw or ""))


def _can_auto_join_channel(channel_id: str) -> bool:
    return str(channel_id or "").startswith("C")


def _try_join_channel(client: WebClient, channel_id: str) -> bool:
    try:
        client.conversations_join(channel=channel_id)
        return True
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("Slack channel auto-join failed channel=%s exc=%s", channel_id, exc)
        return False


def _build_thread_access_error(channel_id: str, original: SlackApiError) -> ValueError:
    error_code = str(original.response.get("error", "")).strip()
    if error_code != "not_in_channel":
        return ValueError(f"Slack thread read failed: {error_code or type(original).__name__}")
    if str(channel_id or "").startswith("G"):
        return ValueError("The app is not a member of this private channel. Invite the app to the channel and try again.")
    if str(channel_id or "").startswith("C"):
        return ValueError(
            "The app is not a member of this public channel. Add the app to the channel, or grant channels:join and reinstall the app."
        )
    return ValueError("The app is not in this conversation. Add or invite the app, then try again.")
