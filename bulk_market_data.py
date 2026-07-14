from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

import pandas as pd
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest,
    StockSnapshotRequest,
)
from alpaca.data.timeframe import TimeFrame

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY


@dataclass(frozen=True)
class SnapshotRecord:
    ticker: str
    latest_price: float
    previous_close: float | None
    daily_volume: float | None
    dollar_volume: float
    daily_change_pct: float | None


def _client() -> StockHistoricalDataClient:
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        raise RuntimeError("Alpaca credentials are missing.")

    return StockHistoricalDataClient(
        api_key=ALPACA_API_KEY,
        secret_key=ALPACA_SECRET_KEY,
    )


def chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def get_bulk_snapshots(
    symbols: list[str],
    *,
    batch_size: int = 100,
) -> tuple[
    dict[str, SnapshotRecord],
    list[dict[str, str]],
]:
    client = _client()
    output: dict[str, SnapshotRecord] = {}
    errors: list[dict[str, str]] = []

    for batch in chunks(symbols, batch_size):
        try:
            request = StockSnapshotRequest(
                symbol_or_symbols=batch,
                feed=DataFeed.IEX,
            )
            snapshots = client.get_stock_snapshot(request)

            for symbol in batch:
                snapshot = snapshots.get(symbol)
                if snapshot is None:
                    continue

                latest_trade = getattr(
                    snapshot,
                    "latest_trade",
                    None,
                )
                daily_bar = getattr(
                    snapshot,
                    "daily_bar",
                    None,
                )
                previous_bar = getattr(
                    snapshot,
                    "previous_daily_bar",
                    None,
                )

                latest_price = None
                if (
                    latest_trade is not None
                    and latest_trade.price is not None
                ):
                    latest_price = float(latest_trade.price)
                elif (
                    daily_bar is not None
                    and daily_bar.close is not None
                ):
                    latest_price = float(daily_bar.close)

                if latest_price is None or latest_price <= 0:
                    continue

                previous_close = (
                    float(previous_bar.close)
                    if previous_bar is not None
                    and previous_bar.close is not None
                    else None
                )
                volume = (
                    float(daily_bar.volume)
                    if daily_bar is not None
                    and daily_bar.volume is not None
                    else None
                )
                dollar_volume = (
                    latest_price * volume
                    if volume is not None
                    else 0.0
                )
                daily_change_pct = (
                    (latest_price / previous_close - 1) * 100
                    if previous_close
                    else None
                )

                output[symbol] = SnapshotRecord(
                    ticker=symbol,
                    latest_price=latest_price,
                    previous_close=previous_close,
                    daily_volume=volume,
                    dollar_volume=dollar_volume,
                    daily_change_pct=daily_change_pct,
                )

        except Exception as exc:
            for symbol in batch:
                errors.append(
                    {"ticker": symbol, "error": str(exc)}
                )

    return output, errors


def select_liquid_symbols(
    symbols: list[str],
    *,
    target_size: int = 1500,
    minimum_price: float = 2.0,
    minimum_dollar_volume: float = 2_000_000,
) -> tuple[
    list[str],
    dict[str, SnapshotRecord],
    list[dict[str, str]],
]:
    snapshots, errors = get_bulk_snapshots(symbols)

    eligible = [
        record
        for record in snapshots.values()
        if record.latest_price >= minimum_price
        and record.dollar_volume >= minimum_dollar_volume
    ]

    eligible.sort(
        key=lambda record: record.dollar_volume,
        reverse=True,
    )

    selected = eligible[:target_size]

    return (
        [record.ticker for record in selected],
        {record.ticker: record for record in selected},
        errors,
    )


def get_bulk_daily_bars(
    symbols: list[str],
    *,
    lookback_days: int = 420,
    batch_size: int = 50,
) -> tuple[
    dict[str, pd.DataFrame],
    list[dict[str, str]],
]:
    client = _client()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)

    output: dict[str, pd.DataFrame] = {}
    errors: list[dict[str, str]] = []

    for batch in chunks(symbols, batch_size):
        try:
            request = StockBarsRequest(
                symbol_or_symbols=batch,
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
                adjustment="all",
                feed=DataFeed.IEX,
            )
            frame = client.get_stock_bars(request).df

            if frame.empty or not isinstance(
                frame.index,
                pd.MultiIndex,
            ):
                continue

            available = set(
                frame.index.get_level_values(0)
            )

            for symbol in batch:
                if symbol not in available:
                    continue

                bars = frame.xs(symbol).reset_index()
                bars = bars.sort_values(
                    "timestamp"
                ).reset_index(drop=True)

                for column in [
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ]:
                    bars[column] = pd.to_numeric(
                        bars[column],
                        errors="coerce",
                    )

                bars = bars.dropna(
                    subset=[
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                    ]
                )

                if len(bars) >= 60:
                    output[symbol] = bars

        except Exception as exc:
            for symbol in batch:
                errors.append(
                    {"ticker": symbol, "error": str(exc)}
                )

    return output, errors
