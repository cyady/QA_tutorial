# HITL Trigger Matrix (MVP)

| Trigger | Detection Signal | Agent Action | Required Evidence | Final Status |
|---|---|---|---|---|
| Auth Wall | Redirect/login gate, protected page message, blocked route after valid nav | Stop autonomous flow for that path | URL transition, page text/screenshot, route intent | needs_review |
| CAPTCHA | Visual/text captcha challenge appears | Do not bypass; stop step | Screenshot, page text, action context | needs_review |
| Anti-Bot | Bot challenge, repeated access denial, script challenge loop | Stop step, collect diagnostics | Console/network evidence, screenshot, retry history | needs_review |
| Evidence Conflict | Tool outputs disagree (URL/state/text/DOM conflict) and cannot reconcile | Mark case unresolved | Conflicting evidence refs + conflict note | needs_review |
| Accumulated Tool Failures | Same action fails after Vibium 15 retries and DevTools 5 diagnosis sets | Abort case path and escalate | Retry counters, error chain, diagnostics bundle | needs_review |

## Notes
- `needs_review` means HITL is required to finalize the verdict.
- If a hard functional break is still provable despite trigger context, `fail` can be used for that specific case with explicit evidence.
