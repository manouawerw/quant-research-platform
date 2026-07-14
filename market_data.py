from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY

client = StockHistoricalDataClient(
    ALPACA_API_KEY,
    ALPACA_SECRET_KEY
)


def get_daily_bars(symbol, start, end):
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
    )

    bars = client.get_stock_bars(request)

    return bars.df


def get_latest_quote(symbol):
    request = StockLatestQuoteRequest(
        symbol_or_symbols=symbol
    )

    return client.get_stock_latest_quote(request)