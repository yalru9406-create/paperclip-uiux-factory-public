from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import anyio
import httpx2
from pydantic import TypeAdapter

from paper_engine.api_models import (
    AggTradePayload,
    DepthPayload,
    ExchangeInfoPayload,
    FundingPayload,
    KlinePayload,
    OpenInterestPayload,
    TickerPayload,
)
from paper_engine.models import Kline

TICKER_24HR_PATH: Final = "/fapi/v1/ticker/24hr"


@dataclass(frozen=True, slots=True)
class BinanceGateway:
    client: httpx2.AsyncClient
    ticker_retry_backoff_seconds: float = 0.25

    async def tradable_symbols(self) -> set[str]:
        response = await self.client.get("/fapi/v1/exchangeInfo")
        _ = response.raise_for_status()
        payload = ExchangeInfoPayload.model_validate(response.json())
        return {
            item.symbol
            for item in payload.symbols
            if item.status == "TRADING" and item.contract_type == "PERPETUAL" and item.quote_asset == "USDT"
        }

    async def top_symbols(self, allowed_symbols: set[str], top_n: int) -> list[str]:
        response = await self._ticker_24hr_response()
        _ = response.raise_for_status()
        tickers = TypeAdapter(list[TickerPayload]).validate_python(response.json())
        ranked = sorted(
            (ticker for ticker in tickers if ticker.symbol in allowed_symbols),
            key=lambda ticker: ticker.quote_volume,
            reverse=True,
        )
        return [ticker.symbol for ticker in ranked[:top_n]]

    async def _ticker_24hr_response(self) -> httpx2.Response:
        try:
            return await self.client.get(TICKER_24HR_PATH)
        except httpx2.TransportError:
            if self.ticker_retry_backoff_seconds > 0.0:
                await anyio.sleep(self.ticker_retry_backoff_seconds)
            return await self.client.get(TICKER_24HR_PATH)

    async def klines(self, symbol: str, interval: str, limit: int) -> list[Kline]:
        response = await self.client.get(
            "/fapi/v1/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        _ = response.raise_for_status()
        payload = TypeAdapter(list[KlinePayload]).validate_python(response.json())
        return [row.to_kline() for row in payload]

    async def depth(self, symbol: str, limit: int) -> DepthPayload:
        response = await self.client.get("/fapi/v1/depth", params={"symbol": symbol, "limit": limit})
        _ = response.raise_for_status()
        return DepthPayload.model_validate(response.json())

    async def agg_trades(self, symbol: str, limit: int) -> list[AggTradePayload]:
        response = await self.client.get("/fapi/v1/aggTrades", params={"symbol": symbol, "limit": limit})
        _ = response.raise_for_status()
        return TypeAdapter(list[AggTradePayload]).validate_python(response.json())

    async def open_interest(self, symbol: str) -> OpenInterestPayload:
        response = await self.client.get("/fapi/v1/openInterest", params={"symbol": symbol})
        _ = response.raise_for_status()
        return OpenInterestPayload.model_validate(response.json())

    async def funding(self, symbol: str) -> FundingPayload:
        response = await self.client.get("/fapi/v1/premiumIndex", params={"symbol": symbol})
        _ = response.raise_for_status()
        return FundingPayload.model_validate(response.json())
