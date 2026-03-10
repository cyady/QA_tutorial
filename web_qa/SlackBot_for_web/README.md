# SlackBot_for_web

Engine-first web QA runtime with Slack, CLI, and dashboard transports.

## What This Project Does
- Runs web QA through a shared engine instead of channel-specific logic.
- Uses a LangGraph pipeline: `Map -> Plan -> Execute -> Report`.
- Exposes one user-facing mode only: `Full QA (E2E)`.
- Uses Vibium as the primary browser execution tool and Chrome DevTools as a diagnostic fallback.
- Stores every run as artifacts under `artifacts/<JOB_ID>/`.
- Supports local review UI at `/review` and workflow tracing at `/workflow`.
- Captures Slack QA threads into memory archives and retrieves past human QA notes through a local vector index.

## Current Runtime Shape

### Engine
- Core entry: `src/slackbot_for_web/qa_engine.py`
- Main runtime: `src/slackbot_for_web/webqa_runner.py`
- LangGraph stages:
  1. `Map`
  2. `Plan`
  3. `Execute`
  4. `Report`

### User-facing mode
- Slack users do not choose presets.
- Requests are normalized to `full_web_qa`.
- UI label is fixed as `Full QA (E2E)`.

### Current VLA-like hybrid
- Deterministic visual probes are built into execution:
  - `scroll_probe`
  - `hover_probe`
  - `clickability_probe`
- Probe outputs are stored in `visual_probes.json`.
- Review UI can show before/after evidence with overlay annotations.

### Slack QA memory
- Slack message shortcut: `Save Thread to QA Memory`
- Raw thread archives are stored under `artifacts/_memory/MEM-*/`
- Extracted issue cards are stored as `issue_memory_cards.json`
- Local vector retrieval uses `intfloat/multilingual-e5-large-instruct`
- Planning writes `memory_retrieval.json` and uses hits as `memory_hints`

## Verified State
- Current package version: `0.2.0`
- Current default memory embedding model: `intfloat/multilingual-e5-large-instruct`
- Local retrieval benchmark:
  - `top1_accuracy = 0.9`
  - `top3_accuracy = 1.0`
  - `mrr = 0.95`
- Latest validated Framer target run:
  - `JOB-112efc31`
  - `status = needs_review`
  - `total_tokens = 240,977`

## Project Layout
- `src/slackbot_for_web/`
  - engine, transports, dashboard, memory extraction, vector index
- `artifacts/`
  - run artifacts and memory archives
- `review_ui/`
  - React review UI
- `docs/`
  - implementation and architecture documents

## Installation
From the repository root:

```powershell
cd web_qa\SlackBot_for_web
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
```

## Environment
Copy `.env.example` to `.env`.

### Required for engine runs
- `OPENAI_API_KEY`

### Required for Slack app
- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN`

### Common runtime settings
- `DEFAULT_AGENT`
- `OPENAI_MODEL`
- `HARD_TIMEOUT_MINUTES`
- `USE_LANGGRAPH`
- `ARTIFACT_ROOT`
- `MEMORY_EMBEDDING_MODEL`
- `MEMORY_COMPARE_MODELS`

## Main Commands

### Run the engine
```powershell
webqa-engine --url https://example.com --agent openai --mode full_web_qa
```

### Run the Slack app
```powershell
webqa-slack
```

### Run the review dashboard
```powershell
webqa-dashboard --host 127.0.0.1 --port 8787
```

### Extract issue memory cards from a saved Slack thread
```powershell
webqa-memory-extract --memory-id MEM-fb9c644c
```

### Build/query local vector memory
```powershell
webqa-memory-index build
webqa-memory-index query --text "모바일 정렬 안맞음 스크롤 깜빡임 플로팅 CTA depth" --top-k 5
webqa-memory-index compare --top-k 5
```

## Artifact Model
Each run writes to `artifacts/<JOB_ID>/`.

Key outputs:
- `domain_context_map.json`
- `memory_retrieval.json`
- `coverage_plan.json`
- `test_cases.json`
- `visual_probes.json`
- `execution_log.json`
- `test_case_results.json`
- `qa_report.json`
- `result.json`
- `regression_diff.json`

Each Slack QA memory archive writes to `artifacts/_memory/MEM-*/`.

Key outputs:
- `thread_manifest.json`
- `thread_messages.json`
- `file_manifest.json`
- `issue_memory_cards.json`
- `files/*`

## Current Limits
- Retrieval quality is now usable, but same-domain prioritization is still weak.
- The main remaining blocker is missing `target_url` / `job_url` / `host` metadata in older memory manifests.
- Claude execution is still placeholder-level.
- Some stage artifacts are still not under strict Pydantic validation.

## Recommended Docs
- `docs/current_engine_version.md`
- `docs/engine_first_architecture.md`
- `docs/slack_thread_vector_memory_plan.md`
- `docs/vla_strategy_for_web_qa.md`
- `docs/artifact_mode_migration_plan.md`
