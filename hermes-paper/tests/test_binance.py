from __future__ import annotations

import anyio
import httpx2

from paper_engine.binance import BinanceGateway


def test_top_symbols_retries_transient_ticker_protocol_error() -> None:
    # Given: Binance closes the first 24hr ticker stream and the immediate retry succeeds.
    calls = 0

    def handle_request(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx2.RemoteProtocolError("transient HTTP/2 connection close", request=request)
        return httpx2.Response(
            200,
            json=[
                {"symbol": "ETHUSDT", "quoteVolume": "3000"},
                {"symbol": "BTCUSDT", "quoteVolume": "5000"},
                {"symbol": "DOGEUSDT", "quoteVolume": "9000"},
                {"symbol": "SOLUSDT", "quoteVolume": "1000"},
            ],
            request=request,
        )

    async def run_gateway() -> list[str]:
        transport = httpx2.MockTransport(handle_request)
        async with httpx2.AsyncClient(transport=transport, base_url="https://fapi.binance.com") as client:
            gateway = BinanceGateway(client, ticker_retry_backoff_seconds=0.0)
            return await gateway.top_symbols({"BTCUSDT", "ETHUSDT", "SOLUSDT"}, 2)

    # When: top_symbols fetches the ranked ticker list.
    symbols = anyio.run(run_gateway)

    # Then: the transient protocol failure is retried and the ranked allowlist is returned.
    assert symbols == ["BTCUSDT", "ETHUSDT"]
    assert calls == 2
