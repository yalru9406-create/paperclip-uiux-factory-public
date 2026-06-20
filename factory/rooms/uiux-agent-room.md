# UI/UX Agent Room

This is the reusable room contract for UI/UX jobs created by `yalru-uiux-factory`.

## Room Rule

Hermes is the chair. Workers produce evidence, not final truth.

## Chat Surface

- The room is a persistent Paperclip issue created by `yalru-uiux-factory room ensure`.
- CLI-directed chat uses `paperclipai agent prompt --issue <room> --agent <agent>`.
- Messages are written as Paperclip issue comments, so the room remains visible from browser, local PC, and mobile access.
- Use `--no-wake` for notes or verification smoke tests that should not start agent execution.

## Conversation Lanes

1. Hermes opens the Work Packet and records the done definition.
2. GajeCode/GLM 5.2 drafts actual product screens.
3. LazyCodex/Codex turns the draft into maintainable code and browser QA.
4. Antigravity reviews screenshots and long design references.
5. FreeClaude critiques slop, missing states, and overclaims.
6. QA Harness confirms service/adapter/browser evidence.
7. Hermes closes only after the evidence gate.

## Required Artifacts

- `DESIGN.md`
- screenshots at 375px, 768px, 1280px
- `result.md`
- `log.md`
- Paperclip issue tree status

## Block Conditions

- No target repo or write scope.
- No design system before UI implementation.
- No screenshot evidence for visual work.
- Worker output conflicts and Hermes has not resolved it.
