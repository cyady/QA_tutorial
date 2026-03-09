from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from slackbot_for_web.config import load_settings
from slackbot_for_web.models import QaRunRequest
from slackbot_for_web.qa_engine import QaEngine
from slackbot_for_web.presets import normalize_mode_key, resolve_mode_instruction

FULL_WEB_QA_MODE_KEY = "full_web_qa"


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    project_root = Path(__file__).resolve().parents[2]
    dotenv_path = project_root / ".env"
    load_dotenv(dotenv_path=dotenv_path)
    settings = load_settings(require_slack_tokens=False)

    engine = QaEngine(settings)
    if args.rerun_failures_from:
        payload = _run_batch_rerun(args=args, settings=settings, engine=engine)
    else:
        payload = _run_single(args=args, engine=engine)

    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.output_json:
        output_path = Path(args.output_json).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved: {output_path}")

    if args.show_raw:
        print("\n--- RAW OUTPUT ---")
        raw_outputs = payload.get("raw_output")
        if isinstance(raw_outputs, str):
            print(raw_outputs)
        elif isinstance(raw_outputs, list):
            for idx, item in enumerate(raw_outputs, start=1):
                print(f"[{idx}] {item}")


def _run_single(args: argparse.Namespace, engine: QaEngine) -> dict[str, Any]:
    mode_key = _resolve_requested_mode(args)
    if mode_key != FULL_WEB_QA_MODE_KEY:
        raise ValueError("Only `full_web_qa` is supported in the current engine.")

    request = QaRunRequest(
        user_id=args.user_id.strip(),
        channel_id="engine-cli",
        agent=args.agent.strip().lower(),
        url=str(args.url or "").strip(),
        mode_key=mode_key,
        custom_prompt=_load_custom_prompt(args),
    )
    result = engine.run(request)
    return {
        "command_mode": "single_run",
        "qa_mode_key": mode_key,
        "job_id": request.job_id,
        "status": result.status,
        "summary": result.summary,
        "summary_lines": result.summary_lines,
        "findings": result.findings,
        "token_usage": result.token_usage,
        "artifacts": result.artifact_paths,
        "regression_diff": _load_regression_diff(result.artifact_paths),
        "started_at": result.started_at,
        "completed_at": result.completed_at,
        "raw_output": result.raw_output if args.show_raw else "",
    }


def _run_batch_rerun(args: argparse.Namespace, settings, engine: QaEngine) -> dict[str, Any]:
    source_dir = _resolve_batch_source_dir(args.rerun_failures_from, settings.artifact_root)
    test_case_results = _load_json_file(source_dir / "test_case_results.json")
    test_cases_payload = _load_json_file(source_dir / "test_cases.json")
    started_payload = _load_json_file(source_dir / "started.json")
    result_payload = _load_json_file(source_dir / "result.json")

    if not isinstance(test_case_results, dict):
        raise ValueError(f"Invalid or missing test_case_results.json: {source_dir}")
    if not isinstance(test_cases_payload, dict):
        raise ValueError(f"Invalid or missing test_cases.json: {source_dir}")

    source_url = str((started_payload or {}).get("url") or (result_payload or {}).get("url") or "").strip()
    source_mode_key = normalize_mode_key(
        (started_payload or {}).get("mode")
        or (result_payload or {}).get("mode")
        or (started_payload or {}).get("preset")
        or (result_payload or {}).get("preset")
        or ""
    )
    source_agent = str(
        (args.rerun_agent or "").strip().lower()
        or (started_payload or {}).get("agent")
        or (result_payload or {}).get("agent")
        or args.agent
    ).strip().lower()
    if not source_url:
        raise ValueError(f"Cannot resolve source URL from artifact: {source_dir}")
    if not source_mode_key:
        source_mode_key = FULL_WEB_QA_MODE_KEY

    failed_ids = _collect_failed_case_ids(
        test_case_results_payload=test_case_results,
        include_needs_review=bool(args.include_needs_review),
    )
    case_map = _index_test_cases(test_cases_payload)
    selected_ids = failed_ids[: max(1, int(args.max_cases))]

    rerun_results: list[dict[str, Any]] = []
    for case_id in selected_ids:
        case_obj = case_map.get(case_id, {"case_id": case_id, "title": "unknown_case"})
        custom_prompt = _build_rerun_prompt(
            settings=settings,
            mode_key=source_mode_key,
            target_url=source_url,
            case_obj=case_obj,
        )
        request = QaRunRequest(
            user_id=args.user_id.strip(),
            channel_id="engine-cli-batch",
            agent=source_agent,
            url=source_url,
            mode_key=source_mode_key,
            custom_prompt=custom_prompt,
        )
        result = engine.run(request)
        rerun_results.append(
            {
                "original_case_id": case_id,
                "rerun_job_id": request.job_id,
                "status": result.status,
                "summary": result.summary,
                "token_usage": result.token_usage,
                "regression_diff": _load_regression_diff(result.artifact_paths),
                "artifacts": result.artifact_paths,
                "raw_output": result.raw_output if args.show_raw else "",
            }
        )

    batch_summary = _summarize_batch(rerun_results)
    batch_payload = {
        "command_mode": "batch_rerun_failures",
        "source_dir": str(source_dir),
        "source_url": source_url,
        "source_mode_key": source_mode_key,
        "source_agent": source_agent,
        "selected_case_count": len(selected_ids),
        "selected_case_ids": selected_ids,
        "summary": batch_summary,
        "results": rerun_results,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    batch_output_dir = Path(settings.artifact_root) / f"BATCH-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    batch_output_dir.mkdir(parents=True, exist_ok=True)
    default_batch_report = batch_output_dir / "batch_rerun_report.json"
    default_batch_report.write_text(json.dumps(batch_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    batch_payload["batch_report_path"] = str(default_batch_report.resolve())
    return batch_payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Web QA engine without Slack transport.")
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--url", help="Target URL to test.")
    mode_group.add_argument(
        "--rerun-failures-from",
        default="",
        help="Source JOB_ID or artifact directory/file to batch rerun failed cases.",
    )
    parser.add_argument("--agent", default="openai", help="Agent to use: gemini|openai|codex|claude")
    parser.add_argument("--rerun-agent", default="", help="Optional agent override for batch rerun mode.")
    parser.add_argument(
        "--mode",
        default="",
        help="QA mode key: full_web_qa (default: full_web_qa)",
    )
    parser.add_argument("--preset", dest="legacy_preset", default="", help=argparse.SUPPRESS)
    parser.add_argument("--custom-prompt", default="", help="Inline custom prompt instruction.")
    parser.add_argument("--custom-prompt-file", default="", help="Path to custom prompt text file.")
    parser.add_argument("--user-id", default="engine-cli", help="Execution requester id for traceability.")
    parser.add_argument("--include-needs-review", action="store_true", help="Include needs_review cases in batch rerun.")
    parser.add_argument("--max-cases", type=int, default=20, help="Maximum number of failed cases to rerun.")
    parser.add_argument("--output-json", default="", help="Optional path to save a result JSON.")
    parser.add_argument("--show-raw", action="store_true", help="Print raw model output.")
    return parser.parse_args()


def _load_custom_prompt(args: argparse.Namespace) -> str:
    inline_text = (args.custom_prompt or "").strip()
    file_path = (args.custom_prompt_file or "").strip()
    if inline_text:
        return inline_text
    if not file_path:
        return ""
    prompt_path = Path(file_path).expanduser().resolve()
    if not prompt_path.exists():
        raise FileNotFoundError(f"custom prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def _load_regression_diff(artifact_paths: list[str]) -> dict[str, Any] | None:
    for raw in artifact_paths:
        path = Path(raw)
        if path.name != "regression_diff.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
        if isinstance(payload, dict):
            return payload
    return None


def _resolve_batch_source_dir(raw: str, artifact_root: str) -> Path:
    token = (raw or "").strip()
    if not token:
        raise ValueError("--rerun-failures-from is required for batch mode")

    root = Path(artifact_root)
    job_dir = root / token
    if job_dir.exists() and job_dir.is_dir():
        return job_dir.resolve()

    candidate = Path(token).expanduser().resolve()
    if candidate.is_file():
        return candidate.parent
    if candidate.is_dir():
        return candidate
    raise FileNotFoundError(f"Batch source not found: {raw}")


def _load_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _collect_failed_case_ids(test_case_results_payload: dict[str, Any], include_needs_review: bool) -> list[str]:
    rows = test_case_results_payload.get("results")
    if not isinstance(rows, list):
        return []
    failed_ids: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").strip().lower()
        case_id = str(row.get("case_id") or "").strip()
        if not case_id:
            continue
        if status == "fail" or (include_needs_review and status == "needs_review"):
            failed_ids.append(case_id)
    return failed_ids


def _index_test_cases(test_cases_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    test_cases = test_cases_payload.get("test_cases")
    if not isinstance(test_cases, list):
        return {}
    output: dict[str, dict[str, Any]] = {}
    for case in test_cases:
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("case_id") or "").strip()
        if case_id:
            output[case_id] = case
    return output


def _build_rerun_prompt(settings, mode_key: str, target_url: str, case_obj: dict[str, Any]) -> str:
    base_instruction = resolve_mode_instruction(
        key=mode_key,
        target_url=target_url,
        store_path=settings.mode_store_path,
    )
    case_text = json.dumps(case_obj, ensure_ascii=False)
    return (
        f"{base_instruction}\n\n"
        "재검증 모드 (배치):\n"
        "- 아래 단일 테스트 케이스만 검증하라.\n"
        "- 다른 케이스/다른 경로로 범위를 확장하지 마라.\n"
        "- 결과는 동일 JSON 스키마 형식을 유지하라.\n"
        f"- 대상 케이스: {case_text}\n"
    )


def _summarize_batch(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"pass": 0, "fail": 0, "needs_review": 0}
    for row in results:
        status = str(row.get("status") or "").strip().lower()
        if status not in summary:
            status = "needs_review"
        summary[status] += 1
    return summary


def _resolve_requested_mode(args: argparse.Namespace) -> str:
    return normalize_mode_key(
        getattr(args, "mode", "")
        or getattr(args, "legacy_preset", "")
        or FULL_WEB_QA_MODE_KEY
    )


if __name__ == "__main__":
    main()
