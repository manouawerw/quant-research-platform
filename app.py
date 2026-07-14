import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame


st.set_page_config(
    page_title="Quant Research Platform",
    page_icon="📈",
    layout="wide",
)


@st.cache_resource
def get_alpaca_client() -> StockHistoricalDataClient:
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        raise RuntimeError(
            "Alpaca credentials are missing from Railway Variables."
        )

    return StockHistoricalDataClient(api_key, secret_key)


def get_stock_data(ticker: str) -> tuple[float, pd.DataFrame]:
    client = get_alpaca_client()

    latest_request = StockLatestTradeRequest(
        symbol_or_symbols=ticker,
        feed=DataFeed.IEX,
    )
    latest_trade = client.get_stock_latest_trade(latest_request)

    if ticker not in latest_trade:
        raise ValueError(f"No recent trade was returned for {ticker}.")

    latest_price = float(latest_trade[ticker].price)

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=180)

    bars_request = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame.Day,
        start=start_time,
        end=end_time,
        adjustment="all",
        feed=DataFeed.IEX,
    )

    bars = client.get_stock_bars(bars_request).df

    if bars.empty:
        raise ValueError(f"No historical data was returned for {ticker}.")

    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(ticker)

    return latest_price, bars.reset_index()


st.title("📈 Quant Research Platform")
st.caption("Cloud-based stock research prototype")

ticker = st.text_input(
    "Enter a U.S. stock ticker",
    value="MU",
    max_chars=10,
).strip().upper()

if st.button("Analyze", type="primary"):
    try:
        with st.spinner(f"Loading IEX market data for {ticker}..."):
            latest_price, bars = get_stock_data(ticker)

        if len(bars) < 2:
            raise ValueError("Not enough historical bars were returned.")

        previous_close = float(bars.iloc[-2]["close"])
        daily_change = latest_price - previous_close
        daily_change_pct = daily_change / previous_close * 100

        latest_bar = bars.iloc[-1]

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "Latest IEX price",
            f"${latest_price:,.2f}",
            f"{daily_change_pct:+.2f}%",
        )
        col2.metric("Previous close", f"${previous_close:,.2f}")
        col3.metric("Latest daily high", f"${latest_bar['high']:,.2f}")
        col4.metric("Latest IEX volume", f"{int(latest_bar['volume']):,}")

        chart = go.Figure(
            data=[
                go.Candlestick(
                    x=bars["timestamp"],
                    open=bars["open"],
                    high=bars["high"],
                    low=bars["low"],
                    close=bars["close"],
                    name=ticker,
                )
            ]
        )

        chart.update_layout(
            title=f"{ticker} daily candlestick chart",
            xaxis_title="Date",
            yaxis_title="Price (USD)",
            xaxis_rangeslider_visible=False,
            height=600,
        )

        st.plotly_chart(chart, use_container_width=True)

        st.subheader("Recent daily bars")
        st.dataframe(
            bars[
                ["timestamp", "open", "high", "low", "close", "volume"]
            ].tail(20),
            use_container_width=True,
            hide_index=True,
        )

        st.info(
            "This prototype uses Alpaca's IEX feed. IEX volume and prices "
            "represent that feed rather than the full consolidated U.S. market."
        )

    except Exception as exc:
        st.error(f"Unable to analyze {ticker}: {exc}")
