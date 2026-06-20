# YALRU UI/UX Factory Agent Rules

All work under this factory follows:

`raw input -> actual goal -> risk level -> needed context -> must-not-do -> done definition -> Work Packet -> verification`

Durable loop:

`observe -> normalize -> risk classify -> execute/block -> verify -> journal`

Rules:

- `log.md` is append-only.
- Worker output is evidence, not truth. Hermes/Codex must verify it.
- No external repository writes unless `target_repo`, `write_scope`, and an `[APPROVAL]` entry exist.
- GLM 5.2 drafts visual/product-screen structure; Codex/GPT turns it into maintainable product code; Antigravity reviews screenshots/long docs; QA Harness verifies browser/CLI evidence.
- UI work must create or read `DESIGN.md` before components.
- Product UI must not render requirements, design contracts, migration notes, or implementation memos.
- Completion requires observable evidence, not just a green command.

