# Hermes Paper Engine Subset

Sanitized paper-engine subset exported for the transient Binance ticker retry fix. Runtime paper trade data, logs, local virtualenvs, and private evidence are excluded.

Primary changed surface: `src/paper_engine/binance.py` retries one transient `httpx2.TransportError` from the 24h ticker endpoint before ranking symbols. The regression test is `tests/test_binance.py`.
