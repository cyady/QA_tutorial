# Engine-First Architecture

## Goal
- Treat Slack as a transport channel only.
- Keep all QA behavior in a reusable core engine.

## Current split
- Core engine:
  - `src/slackbot_for_web/qa_engine.py`
  - `src/slackbot_for_web/webqa_runner.py`
- Transport layer:
  - `src/slackbot_for_web/slack_app.py`
  - `src/slackbot_for_web/queue_worker.py`
- Legacy `adapters` routing layer is removed from runtime path.

## Runtime flow
1. Transport receives a request (Slack modal, CLI, API, etc.).
2. Transport builds `QaRunRequest`.
3. Transport calls `QaEngine.run(request)`.
4. Engine executes Map -> Plan -> Execute -> Report.
5. Engine writes artifacts under `artifacts/<JOB_ID>/`.
6. Transport renders final response for its own channel.

## Coverage and timeout policy (MVP)
- Domain coverage: same canonical host/scheme 범위를 가능한 한 넓게 탐색한다.
- URL/action/depth에 대한 하드 캡은 두지 않는다.
- 전역 실행 중단 기준은 `HARD_TIMEOUT_MINUTES`(기본 60분)만 강제한다.
- 비용 최적화는 사전 차단이 아니라 사후 측정(토큰/로그/회귀 diff) 기반으로 수행한다.

## Non-Slack execution
- A CLI transport is provided:
  - Module: `src/slackbot_for_web/engine_cli.py`
  - Command: `webqa-engine`
- This runs the exact same engine path as Slack.
- A dashboard transport is provided:
  - Module: `src/slackbot_for_web/dashboard.py`
  - Command: `webqa-dashboard`
  - Purpose: LangGraph visualization + artifact traceability + QA result dashboard

Example:
```bash
webqa-engine --url https://example.com --agent openai --mode full_web_qa
```

Or:
```bash
python -m slackbot_for_web.engine_cli --url https://example.com --agent openai --mode full_web_qa
```

Batch rerun failed cases from a prior run:
```bash
python -m slackbot_for_web.engine_cli --rerun-failures-from JOB-1234abcd --max-cases 20
```

## Reliability policy
- Self-healing schedule in one run:
  1. Vibium retry (n=5) -> DevTools diagnostic sets (m=3)
  2. Vibium retry (n=5) -> DevTools diagnostic sets (m=2)
  3. Vibium retry (n=5) -> if unresolved, `needs_review` (HITL)
- Immediate HITL triggers:
  - auth wall
  - captcha
  - anti-bot
  - evidence conflict
  - accumulated tool failures

## Regression diff
- On successful runs, the engine writes `regression_diff.json` when a previous run with the same `(url, agent, normalized mode)` exists.
- Diff includes:
  - status direction (`improved|regressed|unchanged`)
  - findings count delta
  - critical findings delta (P0/P1)
  - token total delta

## Why this helps
- New channels can be added without changing QA logic.
- Testing engine behavior becomes easier outside Slack.
- Operational controls (timeouts, retries, HITL) remain centralized.

## Current Slack exposure
- Slack is now a narrow intake channel.
- Slack users do not choose among multiple QA presets/modes.
- Slack requests are queued as `full_web_qa`, shown as `Full QA (E2E)`.
- Legacy mode aliases are normalized to `full_web_qa` at runtime and treated as the same regression bucket.
- Built-in catalog exposure is narrowed to `full_web_qa`; `qa_smoke` / `landing_page_qa` are now legacy aliases only.
