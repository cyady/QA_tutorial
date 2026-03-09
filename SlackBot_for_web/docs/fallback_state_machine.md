# Fallback State Machine (MVP)

## Constants
- `RUN_HARD_TIMEOUT_MINUTES = 60`
- `SELF_HEALING_PHASE_1 = Vibium(5) -> DevTools(3)`
- `SELF_HEALING_PHASE_2 = Vibium(5) -> DevTools(2)`
- `SELF_HEALING_PHASE_3 = Vibium(5) -> HITL if unresolved`

## Definitions
- Diagnosis set (DevTools): one bundled diagnostic attempt containing console + network + DOM/state snapshot, followed by one guided recovery attempt.
- If DevTools MCP is not configured, each diagnosis set is logged as `devtools_skipped` and flow continues.

## Per-Action Flow
1. Start action execution.
2. Attempt via Vibium.
3. If success -> action `pass`.
4. If fail -> run phase 1 budget: Vibium retries up to 5, then DevTools diagnosis sets up to 3.
5. If unresolved -> run phase 2 budget: Vibium retries up to 5, then DevTools diagnosis sets up to 2.
6. If unresolved -> run phase 3 budget: Vibium retries up to 5.
7. If still unresolved -> action result `needs_review` with diagnostics (`HITL`).

## Immediate HITL Triggers
- auth wall
- captcha
- anti-bot
- evidence conflict
- accumulated tool failures

## Global Interrupt
- At any time, if run duration exceeds 60 minutes:
  - stop new actions,
  - flush current evidence,
  - finalize unresolved cases as `needs_review` with `status_reason = hard_timeout`.

## Required Logging
Each attempt must log:
- timestamp
- case_id/action_id
- tool (`vibium` or `devtools`)
- attempt index
- result (`success` / `fail` / `needs_review`)
- error or evidence reference
