from __future__ import annotations

import argparse
import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiohttp import web
from dotenv import load_dotenv

from slackbot_for_web.config import load_settings

MAX_TEXT_PREVIEW_CHARS = 20000

KNOWN_JSON_ARTIFACTS = {
    "started.json": "started",
    "result.json": "result",
    "error.json": "error",
    "domain_context_map.json": "domain_context_map",
    "coverage_plan.json": "coverage_plan",
    "test_cases.json": "test_cases",
    "memory_retrieval.json": "memory_retrieval",
    "execution_log.json": "execution_log",
    "test_case_results.json": "test_case_results",
    "visual_probes.json": "visual_probes",
    "qa_report.json": "qa_report",
    "regression_diff.json": "regression_diff",
}

KNOWN_TEXT_ARTIFACTS = {
    "runner.log",
    "openai_raw.txt",
    "gemini_raw.txt",
    "traceback.txt",
}
USER_FACING_MODE_LABEL = "Full QA (E2E)"
FULL_WEB_QA_MODE_KEY = "full_web_qa"


def main() -> None:
    args = _parse_args()
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(dotenv_path=project_root / ".env")
    settings = load_settings(require_slack_tokens=False)

    artifact_root = Path(settings.artifact_root).resolve()
    if not artifact_root.exists():
        artifact_root.mkdir(parents=True, exist_ok=True)

    review_dist = project_root / "review_ui" / "dist"
    app = _build_app(artifact_root=artifact_root, review_dist=review_dist)
    web.run_app(app, host=args.host, port=args.port)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Web QA dashboard UI for LangGraph artifacts and QA results.")
    parser.add_argument("--host", default="127.0.0.1", help="Dashboard bind host.")
    parser.add_argument("--port", type=int, default=8787, help="Dashboard bind port.")
    return parser.parse_args()


def _build_app(artifact_root: Path, review_dist: Path) -> web.Application:
    app = web.Application()
    app["artifact_root"] = artifact_root
    app["review_dist"] = review_dist.resolve()
    app.router.add_get("/", _handle_index)
    app.router.add_get("/api", _handle_api_index)
    app.router.add_get("/legacy", _handle_legacy_index)
    app.router.add_get("/review", _handle_review_app)
    app.router.add_get("/review/{tail:.*}", _handle_review_app)
    app.router.add_get("/workflow", _handle_review_app)
    app.router.add_get("/workflow/{tail:.*}", _handle_review_app)
    app.router.add_get("/api/runs", _handle_runs)
    app.router.add_get("/api/runs/{run_id}", _handle_run_detail)
    app.router.add_get("/api/runs/{run_id}/files/{filename}", _handle_run_file)
    return app


async def _handle_index(request: web.Request) -> web.Response:
    review_dist: Path = request.app["review_dist"]
    if review_dist.exists():
        return _serve_review_index(review_dist)
    return web.Response(text=_index_html(), content_type="text/html")


async def _handle_legacy_index(_request: web.Request) -> web.Response:
    return web.Response(text=_index_html(), content_type="text/html")


async def _handle_api_index(_request: web.Request) -> web.Response:
    return web.Response(text=_api_index_html(), content_type="text/html")


async def _handle_review_app(request: web.Request) -> web.StreamResponse:
    review_dist: Path = request.app["review_dist"]
    if not review_dist.exists():
        raise web.HTTPNotFound(
            text=(
                "React review UI build not found. "
                "Run `cd review_ui && npm install && npm run build` first."
            )
        )

    tail = Path(request.match_info.get("tail", "")).as_posix().lstrip("/")
    if tail:
        candidate = (review_dist / tail).resolve()
        if not candidate.is_relative_to(review_dist.resolve()):
            raise web.HTTPNotFound(text=f"invalid path: {tail}")
        if candidate.exists() and candidate.is_file():
            return web.FileResponse(candidate)
    return _serve_review_index(review_dist)


def _serve_review_index(review_dist: Path) -> web.Response:
    index_path = review_dist / "index.html"
    if not index_path.exists():
        raise web.HTTPNotFound(text=f"review UI index missing: {index_path}")
    html = index_path.read_text(encoding="utf-8")
    return web.Response(text=html, content_type="text/html")


async def _handle_runs(request: web.Request) -> web.Response:
    artifact_root: Path = request.app["artifact_root"]
    limit = int(request.query.get("limit", "200"))
    runs = _list_runs(artifact_root, limit=max(1, min(limit, 1000)))
    summary = _summarize_runs(runs)
    payload = {
        "artifact_root": str(artifact_root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "runs": runs,
    }
    return web.json_response(payload, dumps=_json_dumps)


async def _handle_run_detail(request: web.Request) -> web.Response:
    artifact_root: Path = request.app["artifact_root"]
    run_id = request.match_info["run_id"].strip()
    run_dir = _resolve_run_dir(artifact_root, run_id)
    if run_dir is None or not run_dir.exists():
        raise web.HTTPNotFound(text=f"run not found: {run_id}")

    summary = _build_run_summary(run_dir)
    files = _list_files_for_run(run_dir)
    detail = {
        "summary": summary,
        "pipeline_trace": _pipeline_trace(summary),
        "artifacts": _load_artifact_bundle(run_dir),
        "text_previews": _load_text_previews(run_dir),
        "files": files,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return web.json_response(detail, dumps=_json_dumps)


async def _handle_run_file(request: web.Request) -> web.StreamResponse:
    artifact_root: Path = request.app["artifact_root"]
    run_id = request.match_info["run_id"].strip()
    filename = Path(request.match_info["filename"]).name
    run_dir = _resolve_run_dir(artifact_root, run_id)
    if run_dir is None:
        raise web.HTTPNotFound(text=f"run not found: {run_id}")

    path = run_dir / filename
    if not path.exists() or not path.is_file():
        raise web.HTTPNotFound(text=f"file not found: {filename}")

    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if content_type.startswith("text/") or path.suffix.lower() in {".json", ".log", ".txt"}:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if path.suffix.lower() == ".json":
            try:
                payload = json.loads(text)
                text = json.dumps(payload, ensure_ascii=False, indent=2)
            except Exception:  # noqa: BLE001
                pass
        return web.Response(text=text, content_type="text/plain")
    return web.FileResponse(path)


def _resolve_run_dir(artifact_root: Path, run_id: str) -> Path | None:
    if not run_id:
        return None
    safe_name = Path(run_id).name
    candidate = artifact_root / safe_name
    if not candidate.resolve().is_relative_to(artifact_root.resolve()):
        return None
    return candidate


def _list_runs(artifact_root: Path, limit: int) -> list[dict[str, Any]]:
    candidates = [d for d in artifact_root.iterdir() if d.is_dir() and (d.name.startswith("JOB-") or d.name.startswith("BATCH-"))]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    runs: list[dict[str, Any]] = []
    for run_dir in candidates[:limit]:
        runs.append(_build_run_summary(run_dir))
    return runs


def _build_run_summary(run_dir: Path) -> dict[str, Any]:
    run_type = "batch" if run_dir.name.startswith("BATCH-") else "job"
    started = _read_json(run_dir / "started.json") or {}
    result = _read_json(run_dir / "result.json") or {}
    error = _read_json(run_dir / "error.json") or {}
    qa_report = _read_json(run_dir / "qa_report.json") or {}
    regression = _read_json(run_dir / "regression_diff.json") or {}
    batch_report = _read_json(run_dir / "batch_rerun_report.json") or {}

    started_at = _first_non_empty(started.get("started_at"), result.get("started_at"), "")
    completed_at = _first_non_empty(result.get("completed_at"), error.get("completed_at"), "")
    if run_type == "batch":
        status = "completed" if batch_report else "running"
    else:
        status = _first_non_empty(result.get("status"), "error" if error else "running")
    token_total = _as_int((result.get("token_usage") or {}).get("total_tokens"))
    finding_count = len(result.get("findings") or []) if isinstance(result.get("findings"), list) else 0
    image_count = len([f for f in run_dir.iterdir() if f.is_file() and f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}])
    visual_probe_diff = (regression.get("visual_probe_diff") or {}) if isinstance(regression, dict) else {}
    visual_probe_delta = (visual_probe_diff.get("delta") or {}) if isinstance(visual_probe_diff, dict) else {}
    preset = _first_non_empty(result.get("preset"), started.get("preset"), "")
    mode_key = _normalize_mode_key(_first_non_empty(result.get("mode"), started.get("mode"), preset))
    mode_label = _mode_label_for_mode(mode_key)

    return {
        "run_id": run_dir.name,
        "run_type": run_type,
        "status": str(status).strip().lower(),
        "agent": _first_non_empty(result.get("agent"), started.get("agent"), ""),
        "mode_key": mode_key,
        "mode_label": mode_label,
        "url": _first_non_empty(result.get("url"), started.get("url"), ""),
        "started_at": started_at,
        "completed_at": completed_at,
        "token_total": token_total,
        "finding_count": finding_count,
        "image_count": image_count,
        "has_error": bool(error),
        "has_qa_report": bool(qa_report),
        "has_regression_diff": bool(regression),
        "has_batch_report": bool(batch_report),
        "status_reason": _first_non_empty(qa_report.get("status_reason"), error.get("error"), ""),
        "visual_probe_direction": str(visual_probe_diff.get("direction") or ""),
        "visual_probe_fail_delta": _as_int(visual_probe_delta.get("fail")),
        "visual_probe_review_delta": _as_int(visual_probe_delta.get("needs_review")),
        "mtime": datetime.fromtimestamp(run_dir.stat().st_mtime, tz=timezone.utc).isoformat(),
    }


def _normalize_mode_key(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"", FULL_WEB_QA_MODE_KEY, "qa_smoke", "landing_page_qa"}:
        return FULL_WEB_QA_MODE_KEY
    return normalized or FULL_WEB_QA_MODE_KEY


def _mode_label_for_mode(mode_key: Any) -> str:
    normalized = _normalize_mode_key(mode_key)
    if normalized == FULL_WEB_QA_MODE_KEY:
        return USER_FACING_MODE_LABEL
    return normalized


def _summarize_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"pass": 0, "fail": 0, "needs_review": 0, "error": 0, "running": 0, "completed": 0}
    total_tokens = 0
    total_findings = 0
    for run in runs:
        status = str(run.get("status", "running")).lower()
        if status not in counts:
            status = "running"
        counts[status] += 1
        total_tokens += _as_int(run.get("token_total"))
        total_findings += _as_int(run.get("finding_count"))
    return {
        "run_count": len(runs),
        "status_counts": counts,
        "token_total_sum": total_tokens,
        "finding_total_sum": total_findings,
    }


def _pipeline_trace(summary: dict[str, Any]) -> list[dict[str, Any]]:
    run_id = str(summary.get("run_id") or "")
    base = f"/api/runs/{run_id}/files"
    return [
        {
            "stage": "Map",
            "artifact": "domain_context_map.json",
            "ready": bool(summary.get("run_type") == "job"),
            "url": f"{base}/domain_context_map.json",
        },
        {
            "stage": "Plan",
            "artifact": "coverage_plan.json / test_cases.json / memory_retrieval.json",
            "ready": bool(summary.get("run_type") == "job"),
            "url": f"{base}/coverage_plan.json",
        },
        {
            "stage": "Execute",
            "artifact": "execution_log.json / test_case_results.json / visual_probes.json",
            "ready": bool(summary.get("run_type") == "job"),
            "url": f"{base}/execution_log.json",
        },
        {
            "stage": "Report",
            "artifact": "qa_report.json / result.json",
            "ready": bool(summary.get("run_type") == "job"),
            "url": f"{base}/qa_report.json",
        },
    ]


def _load_artifact_bundle(run_dir: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for filename, key in KNOWN_JSON_ARTIFACTS.items():
        value = _read_json(run_dir / filename)
        if value is not None:
            payload[key] = value
    return payload


def _load_text_previews(run_dir: Path) -> dict[str, str]:
    previews: dict[str, str] = {}
    for filename in KNOWN_TEXT_ARTIFACTS:
        path = run_dir / filename
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        previews[filename] = text[:MAX_TEXT_PREVIEW_CHARS]
    return previews


def _list_files_for_run(run_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file in sorted(run_dir.iterdir(), key=lambda p: p.name.lower()):
        if not file.is_file():
            continue
        rows.append(
            {
                "name": file.name,
                "size": file.stat().st_size,
                "modified_at": datetime.fromtimestamp(file.stat().st_mtime, tz=timezone.utc).isoformat(),
                "is_image": file.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"},
                "is_json": file.suffix.lower() == ".json",
                "url": f"/api/runs/{run_dir.name}/files/{file.name}",
            }
        )
    return rows


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return None
    return payload if isinstance(payload, dict) else None


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:  # noqa: BLE001
        return 0


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value not in {None, ""}:
            return value
    return ""


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _index_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Web QA Engine Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    mermaid.initialize({ startOnLoad: true, theme: "base" });
  </script>
  <style>
    :root {
      --bg: #0f1720;
      --panel: rgba(20, 31, 43, 0.9);
      --panel-soft: rgba(29, 45, 62, 0.75);
      --line: rgba(142, 181, 206, 0.28);
      --text: #eaf2f8;
      --muted: #9bb0c1;
      --accent: #17bebb;
      --accent-2: #ff9f1c;
      --pass: #3ac17e;
      --fail: #ff5d5d;
      --review: #ffd166;
      --error: #ff5d5d;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--text);
      font-family: "Space Grotesk", sans-serif;
      background:
        radial-gradient(circle at 12% 8%, rgba(23,190,187,0.2), transparent 32%),
        radial-gradient(circle at 85% 18%, rgba(255,159,28,0.15), transparent 30%),
        linear-gradient(170deg, #0b131b 0%, #0f1720 35%, #102332 100%);
      min-height: 100vh;
    }
    .shell { display: grid; grid-template-columns: 360px 1fr; min-height: 100vh; }
    .sidebar {
      border-right: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(7,14,20,0.92), rgba(11,20,28,0.95));
      backdrop-filter: blur(6px);
      padding: 18px 16px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .main {
      padding: 20px;
      display: grid;
      grid-template-rows: auto auto auto 1fr;
      gap: 16px;
    }
    .title {
      font-size: 24px;
      font-weight: 700;
      letter-spacing: 0.2px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .badge {
      font-family: "IBM Plex Mono", monospace;
      font-size: 12px;
      color: #d4e1eb;
      padding: 5px 8px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: rgba(35, 59, 78, 0.5);
    }
    .controls { display: grid; grid-template-columns: 1fr auto; gap: 8px; }
    .input, .btn, select {
      font: inherit;
      color: var(--text);
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px 12px;
    }
    .btn {
      cursor: pointer;
      background: linear-gradient(140deg, rgba(23,190,187,0.2), rgba(23,190,187,0.04));
      transition: transform .15s ease, border-color .15s ease;
    }
    .btn:hover { transform: translateY(-1px); border-color: rgba(23,190,187,0.6); }
    .cards { display: grid; grid-template-columns: repeat(5, minmax(100px,1fr)); gap: 8px; }
    .card {
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--panel-soft);
    }
    .card .k { color: var(--muted); font-size: 12px; }
    .card .v { font-family: "IBM Plex Mono", monospace; font-size: 18px; margin-top: 4px; }
    .run-list { overflow: auto; border: 1px solid var(--line); border-radius: 12px; background: var(--panel); }
    .run-item {
      border-bottom: 1px solid rgba(142, 181, 206, 0.12);
      padding: 12px;
      cursor: pointer;
      display: grid;
      gap: 6px;
      transition: background .18s ease;
    }
    .run-item:hover { background: rgba(40, 64, 84, 0.45); }
    .run-item.active { background: linear-gradient(120deg, rgba(23,190,187,0.18), rgba(23,190,187,0.06)); }
    .run-id { font-family: "IBM Plex Mono", monospace; font-size: 12px; color: #b7c8d6; }
    .run-meta { display: flex; flex-wrap: wrap; gap: 6px; font-size: 12px; color: var(--muted); }
    .pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 1px 7px;
      font-family: "IBM Plex Mono", monospace;
      font-size: 11px;
    }
    .status-pass { color: var(--pass); border-color: rgba(58,193,126,.5); }
    .status-fail { color: var(--fail); border-color: rgba(255,93,93,.5); }
    .status-needs_review { color: var(--review); border-color: rgba(255,209,102,.5); }
    .status-error { color: var(--error); border-color: rgba(255,93,93,.5); }
    .status-running { color: var(--accent); border-color: rgba(23,190,187,.5); }
    .status-completed { color: #8bd8ff; border-color: rgba(139,216,255,.5); }
    .panel {
      border: 1px solid var(--line);
      border-radius: 14px;
      background: var(--panel);
      padding: 14px;
    }
    .section-title { font-size: 14px; font-weight: 700; margin-bottom: 10px; letter-spacing: .3px; }
    .flow {
      background: rgba(15, 29, 41, 0.84);
      border: 1px dashed rgba(142,181,206,0.3);
      border-radius: 12px;
      padding: 8px;
      overflow: auto;
    }
    .trace-grid { display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 8px; }
    .trace-card {
      border: 1px solid var(--line);
      background: rgba(28, 42, 58, 0.72);
      border-radius: 10px;
      padding: 10px;
    }
    .trace-card .stage { font-weight: 700; }
    .trace-card .artifact { color: var(--muted); font-size: 12px; }
    .trace-card a { color: var(--accent); font-size: 12px; text-decoration: none; }
    .detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .box {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px;
      background: rgba(20, 33, 47, 0.68);
      min-height: 120px;
    }
    pre {
      margin: 0;
      font-family: "IBM Plex Mono", monospace;
      font-size: 12px;
      white-space: pre-wrap;
      word-break: break-word;
      color: #d9e5ef;
      max-height: 320px;
      overflow: auto;
    }
    .files {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 8px;
    }
    .file-card {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 9px;
      background: rgba(17, 27, 39, 0.78);
      display: grid;
      gap: 6px;
    }
    .file-card a { color: #8bd8ff; text-decoration: none; font-size: 12px; }
    .tiny { color: var(--muted); font-size: 11px; }
    .empty { color: var(--muted); text-align: center; padding: 30px 12px; }
    @media (max-width: 1100px) {
      .shell { grid-template-columns: 1fr; }
      .cards { grid-template-columns: repeat(3, minmax(100px, 1fr)); }
      .trace-grid { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
      .detail-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 700px) {
      .cards { grid-template-columns: repeat(2, minmax(100px, 1fr)); }
      .trace-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <div class="title">
        <span>QA Runs</span>
        <span class="badge" id="run-count">0</span>
      </div>
      <div class="controls">
        <input id="search" class="input" placeholder="Search run id / url / mode"/>
        <button id="refresh" class="btn">Refresh</button>
      </div>
      <div class="cards">
        <div class="card"><div class="k">PASS</div><div class="v" id="count-pass">0</div></div>
        <div class="card"><div class="k">FAIL</div><div class="v" id="count-fail">0</div></div>
        <div class="card"><div class="k">REVIEW</div><div class="v" id="count-review">0</div></div>
        <div class="card"><div class="k">ERROR</div><div class="v" id="count-error">0</div></div>
        <div class="card"><div class="k">TOKENS</div><div class="v" id="sum-token">0</div></div>
      </div>
      <div id="run-list" class="run-list"></div>
    </aside>
    <main class="main">
      <section class="panel">
        <div class="section-title">LangGraph Pipeline Visualization</div>
        <div class="flow">
<pre class="mermaid">
flowchart LR
  U[Transport: Slack/CLI/API] --> ORCH[Orchestrator: LangGraph]
  ORCH --> MAP[Map Agent]
  MAP --> PLAN[Plan Agent]
  PLAN --> EXEC[Execution Agent]
  EXEC -->|Self-healing| EXEC
  EXEC --> REPORT[Report Agent]
  REPORT --> OUT[QA Result + Dashboard]
</pre>
        </div>
      </section>
      <section class="panel">
        <div class="section-title">Traceability Chain</div>
        <div id="trace-grid" class="trace-grid"></div>
      </section>
      <section class="panel">
        <div class="section-title">Run Overview</div>
        <div id="overview" class="detail-grid"></div>
      </section>
      <section class="panel">
        <div class="section-title">Artifacts & QA Result</div>
        <div id="artifacts" class="files"></div>
      </section>
    </main>
  </div>

  <script>
    const state = {
      runs: [],
      filtered: [],
      selected: null,
      selectedDetail: null,
    };

    const el = (id) => document.getElementById(id);

    function statusClass(status) {
      const v = (status || "").toLowerCase();
      if (v === "pass") return "status-pass";
      if (v === "fail") return "status-fail";
      if (v === "needs_review") return "status-needs_review";
      if (v === "error") return "status-error";
      if (v === "completed") return "status-completed";
      return "status-running";
    }

    function asText(value) {
      if (value === null || value === undefined) return "";
      return String(value);
    }

    function fmtNumber(value) {
      const n = Number(value || 0);
      return n.toLocaleString("en-US");
    }

    function esc(value) {
      return asText(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }

    async function loadRuns() {
      const res = await fetch("/api/runs?limit=300");
      if (!res.ok) throw new Error("failed to load runs");
      const data = await res.json();
      state.runs = data.runs || [];
      applyFilter();
      renderSummary(data.summary || {});
      if (!state.selected && state.filtered.length > 0) {
        await selectRun(state.filtered[0].run_id);
      } else if (state.selected) {
        await selectRun(state.selected.run_id, true);
      }
    }

    function applyFilter() {
      const q = asText(el("search").value).toLowerCase().trim();
      state.filtered = state.runs.filter((run) => {
        if (!q) return true;
        return [run.run_id, run.url, run.mode_label, run.mode_key, run.agent, run.status].some((x) => asText(x).toLowerCase().includes(q));
      });
      renderRunList();
    }

    function renderSummary(summary) {
      const c = summary.status_counts || {};
      el("run-count").textContent = fmtNumber(summary.run_count || 0);
      el("count-pass").textContent = fmtNumber(c.pass || 0);
      el("count-fail").textContent = fmtNumber(c.fail || 0);
      el("count-review").textContent = fmtNumber(c.needs_review || 0);
      el("count-error").textContent = fmtNumber(c.error || 0);
      el("sum-token").textContent = fmtNumber(summary.token_total_sum || 0);
    }

    function renderRunList() {
      const list = el("run-list");
      if (!state.filtered.length) {
        list.innerHTML = '<div class="empty">No runs found.</div>';
        return;
      }
      list.innerHTML = state.filtered.map((run) => `
        <div class="run-item ${state.selected && state.selected.run_id === run.run_id ? "active" : ""}" data-run="${esc(run.run_id)}">
          <div class="run-id">${esc(run.run_id)}</div>
          <div class="run-meta">
            <span class="pill ${statusClass(run.status)}">${esc(run.status)}</span>
            <span>${esc(run.agent || "-")}</span>
            <span>${esc(run.mode_label || run.mode_key || "-")}</span>
          </div>
          <div class="tiny">${esc(run.url || "-")}</div>
          <div class="tiny">tokens: ${fmtNumber(run.token_total || 0)} | findings: ${fmtNumber(run.finding_count || 0)}</div>
        </div>
      `).join("");
      for (const node of list.querySelectorAll(".run-item")) {
        node.addEventListener("click", async () => {
          await selectRun(node.getAttribute("data-run"));
        });
      }
    }

    async function selectRun(runId, keepCurrent = false) {
      if (!runId) return;
      const run = state.runs.find((x) => x.run_id === runId);
      if (!run) return;
      if (!keepCurrent) {
        state.selected = run;
        renderRunList();
      }

      const res = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
      if (!res.ok) throw new Error("failed to load run detail");
      const detail = await res.json();
      state.selected = run;
      state.selectedDetail = detail;
      renderTrace(detail.pipeline_trace || []);
      renderOverview(detail.summary || {}, detail.artifacts || {}, detail.text_previews || {});
      renderArtifacts(detail.files || [], detail.artifacts || {});
      renderRunList();
    }

    function renderTrace(traceRows) {
      const box = el("trace-grid");
      if (!traceRows.length) {
        box.innerHTML = '<div class="empty">No pipeline trace available.</div>';
        return;
      }
      box.innerHTML = traceRows.map((row) => `
        <div class="trace-card">
          <div class="stage">${esc(row.stage)}</div>
          <div class="artifact">${esc(row.artifact)}</div>
          <div class="tiny">${row.ready ? "artifact ready" : "artifact pending"}</div>
          <a href="${esc(row.url)}" target="_blank">open artifact</a>
        </div>
      `).join("");
    }

    function renderOverview(summary, artifacts, previews) {
      const overview = el("overview");
      const qaReport = artifacts.qa_report || {};
      const result = artifacts.result || {};
      const regression = artifacts.regression_diff || {};
      const selfHealing = qaReport.self_healing_attempts || [];

      const left = `
        <div class="box">
          <div class="section-title">Run Snapshot</div>
          <pre>${esc(JSON.stringify({
            run_id: summary.run_id,
            status: summary.status,
            agent: summary.agent,
            mode: summary.mode_label || summary.mode_key,
            url: summary.url,
            started_at: summary.started_at,
            completed_at: summary.completed_at,
            token_total: summary.token_total,
            finding_count: summary.finding_count
          }, null, 2))}</pre>
        </div>
      `;

      const right = `
        <div class="box">
          <div class="section-title">QA Result + Self-healing</div>
          <pre>${esc(JSON.stringify({
            overall_status: qaReport.overall_status || result.status || summary.status,
            status_reason: qaReport.status_reason || summary.status_reason,
            summary_lines: qaReport.summary_lines || result.summary_lines || [],
            self_healing_attempts: selfHealing,
            regression_diff: regression || null
          }, null, 2))}</pre>
        </div>
      `;

      const lowerLeft = `
        <div class="box">
          <div class="section-title">Report Artifact</div>
          <pre>${esc(JSON.stringify(qaReport, null, 2))}</pre>
        </div>
      `;

      const runnerLog = previews["runner.log"] || "runner.log not found";
      const lowerRight = `
        <div class="box">
          <div class="section-title">Runner Log Preview</div>
          <pre>${esc(runnerLog)}</pre>
        </div>
      `;

      overview.innerHTML = left + right + lowerLeft + lowerRight;
    }

    function renderArtifacts(files, artifacts) {
      const wrap = el("artifacts");
      if (!files.length) {
        wrap.innerHTML = '<div class="empty">No artifacts available.</div>';
        return;
      }
      wrap.innerHTML = files.map((file) => `
        <div class="file-card">
          <div><strong>${esc(file.name)}</strong></div>
          <div class="tiny">size: ${fmtNumber(file.size)} bytes</div>
          <div class="tiny">modified: ${esc(file.modified_at)}</div>
          <a href="${esc(file.url)}" target="_blank">open file</a>
        </div>
      `).join("");
    }

    el("refresh").addEventListener("click", async () => {
      try { await loadRuns(); } catch (err) { console.error(err); }
    });
    el("search").addEventListener("input", () => applyFilter());

    loadRuns().catch((err) => {
      console.error(err);
      el("run-list").innerHTML = `<div class="empty">Failed to load runs: ${esc(err.message)}</div>`;
    });
  </script>
</body>
</html>
"""


def _api_index_html() -> str:
    return """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Web QA Python API</title>
  <style>
    body {
      margin: 0;
      font-family: "Segoe UI", sans-serif;
      background: linear-gradient(180deg, #f6f9fd 0%, #edf3fb 100%);
      color: #132030;
    }
    .page {
      max-width: 980px;
      margin: 0 auto;
      padding: 32px 20px 48px;
      display: grid;
      gap: 18px;
    }
    .hero, .card {
      background: rgba(255, 255, 255, 0.94);
      border: 1px solid #d4dfec;
      border-radius: 16px;
      box-shadow: 0 10px 24px rgba(17, 40, 70, 0.06);
      padding: 18px;
    }
    h1, h2 { margin: 0 0 8px; }
    p { margin: 0; line-height: 1.6; color: #4f6176; }
    .nav {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 14px;
    }
    .nav a, .endpoint a {
      display: inline-block;
      text-decoration: none;
      border: 1px solid #c7d6e7;
      border-radius: 999px;
      background: #fff;
      color: #0b58dc;
      padding: 8px 12px;
      font-weight: 600;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
    }
    .endpoint {
      display: grid;
      gap: 10px;
    }
    code {
      display: block;
      padding: 10px 12px;
      border-radius: 10px;
      background: #f4f8fc;
      border: 1px solid #d8e3ef;
      font-family: "Cascadia Mono", "Consolas", monospace;
      color: #203245;
      word-break: break-all;
    }
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <h1>Python API</h1>
      <p>리뷰 화면과 동일한 런 데이터를 JSON으로 조회하는 엔드포인트입니다.</p>
      <div class="nav">
        <a href="/review">리뷰 화면</a>
        <a href="/legacy">기존 대시보드</a>
        <a href="/api/runs?limit=20">최근 run 목록 JSON</a>
      </div>
    </section>

    <section class="grid">
      <article class="card endpoint">
        <h2>Run 목록</h2>
        <code>GET /api/runs?limit=300</code>
        <p>최근 job/batch 목록과 요약 메트릭을 반환합니다.</p>
        <a href="/api/runs?limit=20">예시 열기</a>
      </article>

      <article class="card endpoint">
        <h2>Run 상세</h2>
        <code>GET /api/runs/&lt;run_id&gt;</code>
        <p>pipeline trace, artifacts, text preview, file 목록을 반환합니다.</p>
      </article>

      <article class="card endpoint">
        <h2>Artifact 파일</h2>
        <code>GET /api/runs/&lt;run_id&gt;/files/&lt;filename&gt;</code>
        <p>JSON, 로그, 스크린샷 등 개별 산출물을 직접 조회합니다.</p>
      </article>
    </section>
  </div>
</body>
</html>
"""


if __name__ == "__main__":
    main()
