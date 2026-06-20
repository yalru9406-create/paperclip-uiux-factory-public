# Work Packet: {{GOAL}}

## Raw Input

{{RAW_INPUT}}

## Actual Goal

Build a real UI/UX delivery loop for this request using Paperclip and the MultiAgent roles.

## Scope

- Target repo: `{{TARGET_REPO}}`
- Write scope: `{{WRITE_SCOPE}}`
- Screens/components: `{{SCREENS}}`
- Stack: `{{STACK}}`
- Design guide/reference: `{{DESIGN_GUIDE}}`

## Risk Level

- C1 for app code/docs/UI.
- C2 when creating Paperclip issues or touching remote VPS state.
- C3 only for scoped service restart, if needed.
- C4/C5 are out of scope unless explicitly approved.

## Needed Context

- UI must be a real product screen, not a spec page.
- Design guide must be normalized into `DESIGN.md` before UI implementation.
- Worker results must be verified by Hermes/Codex.
- External repo writes require `target_repo`, `write_scope`, and an `[APPROVAL]` log entry.

## Must Not Do

- Do not render requirements, Design contract, migration notes, or implementation memos inside product UI.
- Do not use paid API keys.
- Do not write outside `write_scope`.
- Do not claim done without screenshots/CLI/service evidence.
- Do not treat worker output as final truth.

## Role Assignment

- Hermes: orchestrate, enforce risk gates, own final evidence.
- GajeCode/GLM 5.2: visual/product-screen draft.
- LazyCodex/Codex: product code, state model, tests, accessibility, cleanup.
- Antigravity: screenshot/document/vision review.
- FreeClaude: critic review and overclaim prevention.
- QA Harness: final browser/CLI/service evidence.

## Done Definition

- File workspace exists with append-only log and approval record.
- Paperclip parent/child issue tree exists.
- `DESIGN.md` exists or the run is blocked before implementation.
- 375/768/1280 screenshot QA is required for UI implementation.
- Adapter/service health checks are recorded.
- Final result distinguishes verified work, unverified work, and blocked gates.

## Verification

- `yalru-uiux-factory doctor`
- `yalru-uiux-factory status <run-dir>`
- Paperclip issue tree has no active recovery action.
- Browser screenshots exist when UI implementation occurred.

