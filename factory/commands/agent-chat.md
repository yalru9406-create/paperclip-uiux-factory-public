# Agent Room Chat Commands

Use these commands when the operator wants Paperclip to behave like a chat room without modifying upstream Paperclip code.

## Create Or Reuse Room

```bash
yalru-uiux-factory provision-agent-keys
yalru-uiux-factory room ensure
```

`provision-agent-keys` creates per-agent Paperclip API keys and writes them to `config/agent-api.env` with mode `0600`.
`room ensure` creates or reuses the persistent `Agent Room: YALRU UI/UX Factory` Paperclip issue and writes the issue id to `rooms/state.json`.

## Send To Hermes

```bash
yalru-uiux-factory hermes --message "Turn this request into a Work Packet and assign lanes."
```

## Send To Worker Lanes

```bash
yalru-uiux-factory lazycodex --message "Implement the approved scope and attach verification."
yalru-uiux-factory gajecode --message "Draft product screens and states."
yalru-uiux-factory freeclaude --message "Critique slop, overclaims, and missing evidence."
yalru-uiux-factory antigravity --message "Review screenshots and document consistency."
yalru-uiux-factory qa --message "Run the final evidence gate."
```

## Smoke Without Starting A Run

```bash
yalru-uiux-factory chat hermes --message "Smoke note only." --no-wake
```

`--no-wake` appends the message to the room issue but does not start agent execution.
