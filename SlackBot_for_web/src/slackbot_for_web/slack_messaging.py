from __future__ import annotations

import logging
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def safe_post_message(
    client: WebClient,
    primary_channel: str,
    fallback_user_id: str,
    text: str,
    delete_action_id: str,
    logger: logging.Logger,
    thread_ts: str | None = None,
) -> tuple[str, str | None]:
    blocks = build_deletable_blocks(text, delete_action_id=delete_action_id)
    try:
        payload = {"channel": primary_channel, "text": text}
        if blocks:
            payload["blocks"] = blocks
        if thread_ts:
            payload["thread_ts"] = thread_ts
        resp = client.chat_postMessage(**payload)
        resolved_channel = resp.get("channel") or primary_channel
        return resolved_channel, resp.get("ts")
    except SlackApiError as exc:
        logger.warning("Slack post failed channel=%s error=%s", primary_channel, exc.response.get("error"))
        if thread_ts:
            try:
                retry_payload = {"channel": primary_channel, "text": text}
                if blocks:
                    retry_payload["blocks"] = blocks
                resp = client.chat_postMessage(**retry_payload)
                resolved_channel = resp.get("channel") or primary_channel
                return resolved_channel, resp.get("ts")
            except Exception as retry_exc:  # noqa: BLE001
                logger.warning("Slack post retry(no-thread) failed channel=%s exc=%s", primary_channel, retry_exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Slack post failed channel=%s exc=%s", primary_channel, exc)

    if fallback_user_id:
        try:
            dm_channel = open_dm_channel(client, fallback_user_id)
            if dm_channel:
                dm_payload = {"channel": dm_channel, "text": text}
                if blocks:
                    dm_payload["blocks"] = blocks
                resp = client.chat_postMessage(**dm_payload)
                resolved_channel = resp.get("channel") or dm_channel
                return resolved_channel, resp.get("ts")
        except SlackApiError as exc:
            logger.warning("Slack fallback post failed user=%s error=%s", fallback_user_id, exc.response.get("error"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Slack fallback post failed user=%s exc=%s", fallback_user_id, exc)
    return primary_channel, None


def open_dm_channel(client: WebClient, user_id: str) -> str:
    if not user_id:
        return ""
    resp = client.conversations_open(users=user_id)
    channel = resp.get("channel")
    if isinstance(channel, dict):
        channel_id = channel.get("id")
        if isinstance(channel_id, str):
            return channel_id.strip()
    return ""


def build_deletable_blocks(text: str, delete_action_id: str) -> list[dict[str, Any]]:
    sections = split_text_for_blocks(text, chunk_size=2800, max_chunks=8)
    if not sections:
        return []

    blocks: list[dict[str, Any]] = []
    for chunk in sections:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "삭제"},
                    "style": "danger",
                    "action_id": delete_action_id,
                    "value": "delete",
                }
            ],
        }
    )
    return blocks


def split_text_for_blocks(text: str, chunk_size: int, max_chunks: int) -> list[str]:
    source = (text or "").strip()
    if not source:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(source) and len(chunks) < max_chunks:
        end = min(len(source), start + chunk_size)
        if end < len(source):
            newline_at = source.rfind("\n", start, end)
            if newline_at > start:
                end = newline_at + 1
        chunks.append(source[start:end].strip())
        start = end

    if start < len(source) and chunks:
        chunks[-1] = _trim_text(chunks[-1] + "\n...", chunk_size)
    return [c for c in chunks if c]


def _trim_text(value: str, limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."

