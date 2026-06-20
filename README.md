# Paperclip UI/UX Factory Public Export

This repository is a sanitized source export for the Yalru/Paperclip orchestration work. It contains the dashboard sidecar, Discord agent routing contract, operational runbooks, and the paper-engine retry fix/test surface.

## Layout

- `factory/` - Paperclip UI/UX factory, Yalru agent dashboard sidecar, Discord agent router, runbooks, and templates.
- `hermes-paper/` - Paper trading engine source/test subset including the transient Binance ticker retry fix.

## Safety Boundary

This export intentionally excludes live credentials, `.env` files, `.omo` ledgers, raw evidence logs/screenshots, runtime state, paper/live position data, `.codegraph`, caches, and service-private files. Live trading mutations are not part of this repository.

## Verification Run Before Publish

- `python3 factory/agent-dashboard-cli/test_discord_surfaces.py`
- `python3 factory/agent-dashboard-cli/test_private_access.py`
- `python3 -m unittest discover -s factory/discord-agent-router -p "test_*.py"`
- `python3 -m py_compile factory/agent-dashboard-cli/*.py factory/discord-agent-router/*.py`
- `cd hermes-paper && uv run pytest -q`
- `cd hermes-paper && uv run basedpyright src tests`
- `cd hermes-paper && uv run ruff check src tests`

The live VPS QA also passed with `factory/agent-dashboard-cli/qa-vps.sh`, including public `/yalru-agent-cli/*` read-only routes and a private guard check that `/yalru-terminal/lazycodex/` returns `403` from the public host.
