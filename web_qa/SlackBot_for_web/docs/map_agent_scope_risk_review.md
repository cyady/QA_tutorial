# Map Agent Scope Risk Review (Fixed Basis: header/cta/form/footer)

## Question
What problems can happen if Map Agent coverage is fixed to auto-extracted header/CTA/form/footer anchors?

## Main Risks
1. Hidden navigation paths
- Hamburger menus, collapsed panels, tabs, and secondary nav may not be discovered without extra interactions.

2. Router-only transitions
- SPA routes can be triggered by JS handlers without stable anchor URLs, reducing static link discovery quality.

3. Dynamic loading paths
- Important content can appear only after scroll, delay, interaction, geolocation, or feature flags.

4. Template blind spots
- Policy/legal/help/blog detail pages may be low-visibility but high QA impact.

5. Embedded app/iframe complexity
- Contact maps, booking widgets, or third-party forms can influence user flow but are outside internal host scope.

6. Device/locale variance
- Mobile header/footer structure can differ significantly from desktop; single-view mapping misses paths.

## Recommendation for MVP
- Keep header/CTA/form/footer as baseline anchors.
- Add controlled expansion rules:
  - include high-signal internal links discovered from main content,
  - include at least one representative detail page from list/index pages,
  - include mobile viewport pass for navigation-only diff.
- Persist unresolved possible paths to `coverage_plan.exclusions` and `qa_report.unresolved_items`.
- If unresolved paths are likely high-impact, use `needs_review` instead of optimistic `pass`.

## Why this still fits your policy
- It preserves quality-first behavior (no hard budget caps).
- It keeps deterministic evidence and operator traceability via artifacts.
