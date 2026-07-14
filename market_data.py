from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY


def _get_client() -> StockHistoricalDataClient:
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        raise RuntimeError(
            "Alpaca credentials are missing. Add ALPACA_API_KEY and "
            "ALPACA_SECRET_KEY to your environment."
        )

    return StockHistoricalDataClient(
        api_key=ALPACA_API_KEY,
        secret_key=ALPACA_SECRET_KEY,
    )


def get_stock_data(
    ticker: str,
    lookback_days: int = 400,
) -> tuple[float, pd.DataFrame]:
    """
    Return the latest IEX trade and daily OHLCV bars.

    The free IEX feed is used deliberately so the app works with
    Alpaca paper accounts that do not include recent SIP data.
    """
    symbol = ticker.strip().upper()
    if not symbol:
        raise ValueError("Ticker cannot be empty.")

    client = _get_client()

    latest_trade_request = StockLatestTradeRequest(
        symbol_or_symbols=symbol,
        feed=DataFeed.IEX,
    )
    latest_trades = client.get_stock_latest_trade(latest_trade_request)

    if symbol not in latest_trades:
        raise ValueError(f"No recent IEX trade was returned for {symbol}.")

    latest_price = float(latest_trades[symbol].price)

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=lookback_days)

    bars_request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start_time,
        end=end_time,
        adjustment="all",
        feed=DataFeed.IEX,
    )
    bars = client.get_stock_bars(bars_request).df

    if bars.empty:
        raise ValueError(f"No historical data was returned for {symbol}.")

    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(symbol)

    bars = bars.reset_index().sort_values("timestamp").reset_index(drop=True)

    required = ["open", "high", "low", "close", "volume"]
    for column in required:
        bars[column] = pd.to_numeric(bars[column], errors="coerce")

    bars = bars.dropna(subset=required)

    if len(bars) < 60:
        raise ValueError(
            f"Only {len(bars)} daily bars were returned. At least 60 are required."
        )

    return latest_price, bars
