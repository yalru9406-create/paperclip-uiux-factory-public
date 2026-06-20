from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, RootModel

from paper_engine.models import Kline


class ExchangeSymbolPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    symbol: str
    status: str
    contract_type: str = Field(alias="contractType")
    quote_asset: str = Field(alias="quoteAsset")


class ExchangeInfoPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    symbols: tuple[ExchangeSymbolPayload, ...]


class TickerPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    symbol: str
    quote_volume: float = Field(alias="quoteVolume")


class KlinePayload(RootModel[tuple[int, str, str, str, str, str, int, str, int, str, str, str]]):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    def to_kline(self) -> Kline:
        row = self.root
        return Kline(
            open_time_ms=row[0],
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            quote_volume=float(row[7]),
            taker_buy_quote_volume=float(row[10]),
        )


class DepthPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    event_time_ms: int = Field(default=0, alias="E")
    bids: tuple[tuple[str, str], ...]
    asks: tuple[tuple[str, str], ...]


class AggTradePayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    price: float = Field(alias="p")
    quantity: float = Field(alias="q")
    event_time_ms: int = Field(alias="T")
    buyer_is_maker: bool = Field(alias="m")

    @property
    def quote_volume(self) -> float:
        return self.price * self.quantity


class OpenInterestPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    symbol: str
    open_interest: float = Field(alias="openInterest")
    time: int


class FundingPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    symbol: str
    last_funding_rate: float = Field(alias="lastFundingRate")
    next_funding_time: int = Field(alias="nextFundingTime")
    time: int


class ForceOrderDetailPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    symbol: str = Field(alias="s")
    side: str = Field(alias="S")
    average_price: float = Field(alias="ap")
    original_quantity: float = Field(alias="q")


class ForceOrderPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    event_time_ms: int = Field(alias="E")
    order: ForceOrderDetailPayload = Field(alias="o")
