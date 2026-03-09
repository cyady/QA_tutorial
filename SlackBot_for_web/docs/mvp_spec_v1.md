# Web QA Agent MVP Spec v1

## 1. Scope and Goals
This spec defines the MVP execution contract for a staged Web QA agent pipeline:
1. Domain Context Mapping
2. Coverage Planning
3. Test Case Design
4. Execution
5. Report

Primary goal: maximize QA target quality coverage, not minimize internal processing.

## 2. Locked MVP Decisions
- Coverage/action/url budget: no hard limit in MVP.
- Run-level hard timeout: 60 minutes.
- Per-action fallback policy:
  - Vibium retries (`n`): 15
  - DevTools diagnosis sets (`m`): 5
- HITL verdict status: `needs_review`.
- Default domain boundary:
  - Internal: exact canonical host of the target site.
  - External: different host, different subdomain, or different protocol.
  - Embedded map/youtube/instagram/external widgets: external context only.
- All artifacts require common keys:
  - `schema_version`
  - `run_id`

## 3. Stage Pipeline Contracts
### 3.1 Domain Context Mapping Agent
Input:
- `target_url` (required)
- `note` (optional)

Output:
- `domain_context_map.json`

Responsibilities:
- Resolve canonical host.
- Build representative site context using header/CTA/form/footer plus discovered key links.
- Record external links as context; do not deeply map external domains.

### 3.2 Coverage Planning Agent
Input:
- `domain_context_map.json`
- `note` (optional)

Output:
- `coverage_plan.json`

Responsibilities:
- Define what to test, what to skip, and why.
- Prioritize by user impact and risk.

### 3.3 Test Design Agent
Input:
- `domain_context_map.json`
- `coverage_plan.json`

Output:
- `test_cases.json`

Responsibilities:
- Produce deterministic, executable cases with clear expected outcomes and evidence requirements.

### 3.4 Execution Agent
Input:
- `domain_context_map.json`
- `coverage_plan.json`
- `test_cases.json`

Output:
- `execution_log.json`
- `test_case_results.json`

Responsibilities:
- Execute test cases in browser tools.
- Apply fallback state machine (`n=15`, `m=5`) per action.
- Enforce run-level hard timeout (60 minutes).

### 3.5 Report Agent
Input:
- all previous artifacts
- `note` (optional)

Output:
- `qa_report.json`
- Slack summary

Responsibilities:
- Build evidence-based verdict (`pass`, `fail`, `needs_review`).
- Summarize coverage achieved vs unresolved areas.
- List prioritized findings with traceable evidence refs.

## 4. Needs Review (HITL) Trigger Policy
`needs_review` must be used when autonomous confidence is structurally limited.

Primary triggers:
- auth wall
- captcha
- anti-bot challenge
- evidence conflict
- accumulated tool failures

Detailed matrix: `docs/hitl_trigger_matrix.md`.

## 5. Domain Boundary Rules
Internal scope = canonical host only.

Examples (target: `https://www.meisterkor.com/`):
- Internal:
  - `https://www.meisterkor.com/company`
  - `https://www.meisterkor.com/contact`
- External:
  - `https://recatch.cc/ko`
  - embedded maps provider URLs
  - youtube/instagram external profiles

External links are logged under `external_navigation_events` and mapped as context only.

## 6. Risk Review: Fixed Map Basis (header/cta/form/footer)
Using only header/CTA/form/footer as fixed map anchors is practical but has blind spots:
- Hidden nav paths behind menu toggles, tabs, accordions.
- Router-driven pages without static `<a href>` links.
- Shadow DOM / iframe app shells.
- Dynamic modules loaded after user gesture or delayed fetch.
- Locale, A/B, or user-agent specific branches.
- Orphan but important URLs not reachable from current navigation graph.

Mitigation in MVP:
- Keep fixed anchors as baseline, but allow expansion from discovered high-signal links.
- Record uncovered hypotheses in `coverage_plan.exclusions` and `qa_report.unresolved_items`.
- Escalate to `needs_review` when evidence indicates likely hidden high-impact paths.

## 7. Artifact Schema Baseline
Schemas are stored at:
- `docs/schemas/domain_context_map.schema.json`
- `docs/schemas/coverage_plan.schema.json`
- `docs/schemas/test_cases.schema.json`
- `docs/schemas/execution_log.schema.json`
- `docs/schemas/test_case_results.schema.json`
- `docs/schemas/qa_report.schema.json`

## 8. Operational Notes
- No quality budget caps in MVP, but all runs must track cost/time/tool-call metrics.
- Hard timeout is safety guardrail only, not coverage limiter.
- All stage outputs must be persisted even on partial failure.
