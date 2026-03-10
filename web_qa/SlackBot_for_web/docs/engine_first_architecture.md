# Engine-First Architecture

## Goal
- Treat Slack as a transport channel only.
- Keep QA behavior in a reusable engine.
- Make CLI, Slack, dashboard, and future channels consume the same runtime path.

## Current split

### Core engine
- `src/slackbot_for_web/qa_engine.py`
- `src/slackbot_for_web/webqa_runner.py`
- `src/slackbot_for_web/models.py`
- `src/slackbot_for_web/config.py`

### Transport / channel layer
- `src/slackbot_for_web/slack_app.py`
- `src/slackbot_for_web/queue_worker.py`
- `src/slackbot_for_web/engine_cli.py`
- `src/slackbot_for_web/dashboard.py`

### Review / operations UI
- `review_ui/`

## Runtime flow
1. A transport receives a request.
2. The transport builds `QaRunRequest`.
3. The transport calls `QaEngine.run(request)`.
4. The engine executes `Map -> Plan -> Execute -> Report`.
5. Artifacts are written under `artifacts/<JOB_ID>/`.
6. The transport renders a response for its own channel.

## Current user-facing exposure
- Slack users do not choose among multiple modes.
- Slack requests are normalized to `full_web_qa`.
- User-facing label is `Full QA (E2E)`.
- Legacy aliases such as `qa_smoke` and `landing_page_qa` are normalized to the same runtime mode.

## Reliability policy
- Hard timeout is controlled by `HARD_TIMEOUT_MINUTES` and defaults to `60`.
- Self-healing sequence in one run:
  1. Vibium retry `5` -> DevTools diagnostic sets `3`
  2. Vibium retry `5` -> DevTools diagnostic sets `2`
  3. Vibium retry `5`
  4. unresolved -> `needs_review`

Immediate `needs_review` triggers:
- auth wall
- captcha
- anti-bot
- evidence conflict
- accumulated tool failures

## Current execution shape

### Planning
- Coverage/test case planning happens inside the engine.
- Planning can retrieve past Slack QA memory through local vector search.
- Retrieval output is stored as `memory_retrieval.json`.

### Execution
- Execution uses deterministic visual probes:
  - `scroll_probe`
  - `hover_probe`
  - `clickability_probe`
- Probe outputs are written to `visual_probes.json`.

### Reporting
- Final outputs include:
  - `qa_report.json`
  - `result.json`
  - `regression_diff.json`

## Local QA memory path
The engine now has a local memory path for human QA feedback.

1. Slack thread is captured through `Save Thread to QA Memory`
2. Raw archive is stored under `artifacts/_memory/MEM-*/`
3. Raw thread is converted into `issue_memory_cards.json`
4. Cards are indexed locally
5. Planning retrieves relevant cards and uses them as hints

Current default embedding model:
- `intfloat/multilingual-e5-large-instruct`

## Why this architecture helps
- QA behavior is not tied to Slack.
- CLI and dashboard use the same engine path as Slack.
- Artifacts become the source of truth.
- Regression diff and failure reruns remain centralized.
- Memory retrieval can improve planning without changing transport code.

## Current limits
- Same-domain memory weighting is still weak because older memory manifests do not yet store enough `target_url / host` metadata.
- Claude runtime remains placeholder-level.
- Some stage artifacts are still not under strict schema validation.

## Main commands

### Engine
```powershell
webqa-engine --url https://example.com --agent openai --mode full_web_qa
```

### Slack app
```powershell
webqa-slack
```

### Dashboard
```powershell
webqa-dashboard --host 127.0.0.1 --port 8787
```

### Failure rerun
```powershell
python -m slackbot_for_web.engine_cli --rerun-failures-from JOB-1234abcd --max-cases 20
```
