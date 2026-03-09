from __future__ import annotations

import json
import logging
import queue
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from slack_sdk import WebClient

from slackbot_for_web.config import Settings
from slackbot_for_web.models import QaRunRequest
from slackbot_for_web.qa_engine import QaEngine
from slackbot_for_web.slack_messaging import safe_post_message

DELETE_ACTION_ID = "delete_bot_message"
USER_FACING_MODE_LABEL = "Full QA (E2E)"


@dataclass
class JobQueueWorker:
    settings: Settings
    client: WebClient

    def __post_init__(self) -> None:
        self._logger = logging.getLogger(__name__)
        self._engine = QaEngine(self.settings)
        self._queue: queue.Queue[QaRunRequest] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def enqueue(self, job: QaRunRequest) -> None:
        self._queue.put(job)

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            try:
                self._logger.info("Starting job %s url=%s agent=%s", job.job_id, job.url, job.agent)
                self._safe_post_message(
                    primary_channel=job.thread_channel_id or job.channel_id,
                    fallback_user_id=job.user_id,
                    thread_ts=job.thread_ts,
                    text=(
                        f"[{job.job_id}] 요청 접수 및 실행 시작\n"
                        f"대상 URL: {job.url}\n"
                        f"점검 모드: `{USER_FACING_MODE_LABEL}`"
                    ),
                )

                result = self._engine.run(job)

                completion_text = self._build_completion_message(job, result)

                self._safe_post_message(
                    primary_channel=job.thread_channel_id or job.channel_id,
                    fallback_user_id=job.user_id,
                    thread_ts=job.thread_ts,
                    text=completion_text,
                )
                self._upload_artifacts(
                    channel_id=job.thread_channel_id or job.channel_id,
                    thread_ts=job.thread_ts,
                    job_id=job.job_id,
                    artifact_paths=result.artifact_paths,
                    verbose=self.settings.slack_verbose_output,
                )
            except Exception as exc:  # noqa: BLE001
                self._logger.exception("Job %s failed: %s", job.job_id, exc)
                error_message, token_usage = self._resolve_job_error_payload(job.job_id, fallback=str(exc))
                token_usage_text = (
                    f"prompt={token_usage.get('prompt_tokens', 0)}, "
                    f"completion={token_usage.get('completion_tokens', 0)}, "
                    f"total={token_usage.get('total_tokens', 0)}"
                    if token_usage
                    else "unknown"
                )
                self._safe_post_message(
                    primary_channel=job.thread_channel_id or job.channel_id,
                    fallback_user_id=job.user_id,
                    thread_ts=job.thread_ts,
                    text=(
                        f"[{job.job_id}] 실행 중 오류가 발생했습니다.\n"
                        f"URL: {job.url}\n"
                        f"오류: {error_message}\n"
                        f"토큰 사용량: {token_usage_text}"
                    ),
                )
            finally:
                self._queue.task_done()

    def _upload_artifacts(
        self,
        channel_id: str,
        thread_ts: str | None,
        job_id: str,
        artifact_paths: list[str],
        verbose: bool,
    ) -> None:
        if not artifact_paths:
            return
        candidates = self._select_artifacts_for_slack(artifact_paths=artifact_paths, verbose=verbose)
        for raw_path in candidates:
            path = Path(raw_path)
            if not path.exists():
                continue
            try:
                self.client.files_upload_v2(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    title=f"{job_id} artifact: {path.name}",
                    file=str(path),
                )
            except Exception as exc:  # noqa: BLE001
                self._logger.warning("Artifact upload failed job=%s path=%s exc=%s", job_id, path, exc)

    def _safe_post_message(
        self,
        primary_channel: str,
        fallback_user_id: str,
        text: str,
        thread_ts: str | None = None,
    ) -> None:
        resolved_channel, message_ts = safe_post_message(
            client=self.client,
            primary_channel=primary_channel,
            fallback_user_id=fallback_user_id,
            text=text,
            delete_action_id=DELETE_ACTION_ID,
            logger=self._logger,
            thread_ts=thread_ts,
        )
        self._logger.info(
            "Slack post dispatch channel=%s resolved_channel=%s thread_ts=%s message_ts=%s",
            primary_channel,
            resolved_channel,
            thread_ts,
            message_ts,
        )

    def _build_completion_message(self, job: QaRunRequest, result) -> str:
        summary_lines = result.summary_lines[:3] if result.summary_lines else [result.summary]
        summary_text = "\n".join(f"- {line}" for line in summary_lines if line)
        finding_lines = self._compact_findings(result.findings, limit=6)
        findings_text = "\n".join(f"- {line}" for line in finding_lines) if finding_lines else "- 발견된 이슈 없음"
        status_kr = self._status_to_korean(result.status)
        token_usage = result.token_usage or {}
        token_usage_text = (
            f"prompt={token_usage.get('prompt_tokens', 0)}, "
            f"completion={token_usage.get('completion_tokens', 0)}, "
            f"total={token_usage.get('total_tokens', 0)}"
            if token_usage
            else "unknown"
        )

        message = (
            f"[{job.job_id}] 점검 완료\n"
            f"결과: `{result.status}` ({status_kr})\n"
            f"URL: {job.url}\n"
            f"토큰 사용량: {token_usage_text}\n"
            f"요약:\n{summary_text}\n\n"
            f"주요 이슈:\n{findings_text}"
        )

        if self.settings.slack_verbose_output:
            debug_logs = "\n".join(f"- {x}" for x in result.step_logs[:6]) if result.step_logs else "- none"
            message += f"\n\n[debug]\nStep logs:\n{debug_logs}"
        return message

    def _compact_findings(self, findings: list[str], limit: int) -> list[str]:
        out: list[str] = []
        for raw in findings[:limit]:
            text = str(raw).strip()
            if not text:
                continue
            parts = [p.strip() for p in text.split(" | ")]
            fid = parts[0] if len(parts) > 0 else "F-??"
            severity = parts[1] if len(parts) > 1 else "P3"
            location = parts[2] if len(parts) > 2 else "unknown"
            obs = self._extract_kv(text, "obs")
            why = self._extract_kv(text, "why")
            if obs:
                line = f"{fid} [{severity}] {location}: {obs}"
                if why:
                    line += f" (영향: {why})"
            else:
                line = f"{fid} [{severity}] {location}"
            out.append(line)
        return out

    def _extract_kv(self, raw: str, key: str) -> str:
        pattern = rf"{re.escape(key)}:\s*(.*?)(?:\s+\|\s+\w+:|$)"
        match = re.search(pattern, raw)
        if not match:
            return ""
        return match.group(1).strip()

    def _status_to_korean(self, status: str) -> str:
        normalized = (status or "").strip().lower()
        if normalized == "pass":
            return "통과"
        if normalized == "fail":
            return "실패"
        return "검토 필요"

    def _select_artifacts_for_slack(self, artifact_paths: list[str], verbose: bool) -> list[str]:
        if verbose:
            return artifact_paths[:5]
        image_ext = {".png", ".jpg", ".jpeg", ".webp"}
        selected: list[str] = []
        for raw in artifact_paths:
            ext = Path(raw).suffix.lower()
            if ext in image_ext:
                selected.append(raw)
            if len(selected) >= 3:
                break
        return selected

    def _resolve_job_error_payload(self, job_id: str, fallback: str) -> tuple[str, dict[str, int]]:
        error_path = Path(self.settings.artifact_root) / job_id / "error.json"
        if not error_path.exists():
            return fallback, {}
        try:
            payload = json.loads(error_path.read_text(encoding="utf-8"))
            error = payload.get("error")
            token_usage_raw = payload.get("token_usage")
            token_usage: dict[str, int] = {}
            if isinstance(token_usage_raw, dict):
                token_usage = {
                    "prompt_tokens": int(token_usage_raw.get("prompt_tokens", 0) or 0),
                    "completion_tokens": int(token_usage_raw.get("completion_tokens", 0) or 0),
                    "total_tokens": int(token_usage_raw.get("total_tokens", 0) or 0),
                }
            if isinstance(error, str) and error.strip():
                return error.strip(), token_usage
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Failed to read error artifact for %s: %s", job_id, exc)
        return fallback, {}

