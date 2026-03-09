# QA_tutorial

QA automation, review tooling, and small operator utilities are curated here as a personal monorepo.
The goal of this cleanup is to keep reusable projects in Git while excluding local credentials, generated artifacts, and heavy dependency folders.

## Active Projects

- `agent_a`
  Candidate-pool extractor that turns memo text into structured `candidate_pool.jsonl`.
- `schema_generator`
  Effective-schema and FN review input generators used in the Re:catch QA flow.
- `qa_review_ui`
  Streamlit review UI for TP/FP/FN decisions and field-level QA metrics.
- `SlackBot_for_web`
  Slack slash-command driven MVP for browser-based web QA orchestration.

## Separate Repositories

- `Codex/codex_QA_Automation`
  Kept as an independent Git repository with its own remote and release history.

## Repository Rules

- Credentials, local `.env` files, runtime logs, screenshots, and temporary outputs are not committed.
- Heavy local dependency folders such as `node_modules/`, `.next/`, and virtual environments are ignored at the repo root.
- Some workspaces remain local-only until they are cleaned up enough to publish.

## Legacy Notes

Older tutorial assets such as `selenium_study/` and `web/` were learning snapshots.
They are being removed from the curated repository so the remaining history reflects current QA automation work instead of archived practice material.
