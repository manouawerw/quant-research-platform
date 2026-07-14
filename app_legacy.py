import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame


# ---------------------------------------------------------
# PAGE CONFIGURATION
# ---------------------------------------------------------

st.set_page_config(
    page_title="Quant Research Platform",
    page_icon="📈",
    layout="wide",
)


# ---------------------------------------------------------
# ALPACA CONNECTION
# ---------------------------------------------------------

@st.cache_resource
def get_alpaca_client() -> StockHistoricalDataClient:
    """Create and cache the Alpaca market-data client."""

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        raise RuntimeError(
            "Alpaca credentials are missing from Railway Variables."
        )

    return StockHistoricalDataClient(
        api_key=api_key,
        secret_key=secret_key,
    )


# ---------------------------------------------------------
# MARKET DATA
# ---------------------------------------------------------

@st.cache_data(ttl=60)
def get_stock_data(ticker: str) -> tuple[float, pd.DataFrame]:
    """
    Retrieve the latest IEX trade and approximately one year
    of daily IEX bars.
    """

    client = get_alpaca_client()

    latest_trade_request = StockLatestTradeRequest(
        symbol_or_symbols=ticker,
        feed=DataFeed.IEX,
    )

    latest_trades = client.get_stock_latest_trade(
        latest_trade_request
    )

    if ticker not in latest_trades:
        raise ValueError(
            f"No recent IEX trade was returned for {ticker}."
        )

    latest_price = float(latest_trades[ticker].price)

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=400)

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
        raise ValueError(
            f"No historical market data was returned for {ticker}."
        )

    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(ticker)

    bars = bars.reset_index()
    bars = bars.sort_values("timestamp").reset_index(drop=True)

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    for column in numeric_columns:
        bars[column] = pd.to_numeric(
            bars[column],
            errors="coerce",
        )

    bars = bars.dropna(
        subset=["open", "high", "low", "close", "volume"]
    )

    return latest_price, bars


# ---------------------------------------------------------
# TECHNICAL INDICATORS
# ---------------------------------------------------------

def calculate_indicators(bars: pd.DataFrame) -> pd.DataFrame:
    """Calculate technical indicators from daily OHLCV data."""

    df = bars.copy()

    # Simple moving averages
    df["sma_20"] = df["close"].rolling(window=20).mean()
    df["sma_50"] = df["close"].rolling(window=50).mean()

    # Exponential moving averages
    df["ema_12"] = df["close"].ewm(
        span=12,
        adjust=False,
    ).mean()

    df["ema_26"] = df["close"].ewm(
        span=26,
        adjust=False,
    ).mean()

    # MACD
    df["macd"] = df["ema_12"] - df["ema_26"]

    df["macd_signal"] = df["macd"].ewm(
        span=9,
        adjust=False,
    ).mean()

    df["macd_histogram"] = (
        df["macd"] - df["macd_signal"]
    )

    # True range and ATR
    previous_close = df["close"].shift(1)

    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df["true_range"] = true_range

    df["atr_14"] = true_range.rolling(
        window=14
    ).mean()

    # RSI using Wilder-style smoothing
    price_change = df["close"].diff()

    gains = price_change.clip(lower=0)
    losses = -price_change.clip(upper=0)

    average_gain = gains.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14,
    ).mean()

    average_loss = losses.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14,
    ).mean()

    safe_average_loss = average_loss.where(
        average_loss != 0
    )

    relative_strength = (
        average_gain / safe_average_loss
    )

    df["rsi_14"] = 100 - (
        100 / (1 + relative_strength)
    )

    # Handle periods with no losses
    df.loc[
        (average_loss == 0) & (average_gain > 0),
        "rsi_14",
    ] = 100

    # Rolling highs and lows
    df["high_20"] = df["high"].rolling(
        window=20
    ).max()

    df["low_20"] = df["low"].rolling(
        window=20
    ).min()

    df["high_50"] = df["high"].rolling(
        window=50
    ).max()

    df["low_50"] = df["low"].rolling(
        window=50
    ).min()

    # Returns and volatility
    df["daily_return"] = df["close"].pct_change()

    df["volatility_20"] = (
        df["daily_return"]
        .rolling(window=20)
        .std()
        * (252 ** 0.5)
    )

    # Average volume and relative volume
    df["average_volume_20"] = (
        df["volume"]
        .rolling(window=20)
        .mean()
    )

    df["relative_volume"] = (
        df["volume"] / df["average_volume_20"]
    )

    # Bollinger Bands
    rolling_std_20 = df["close"].rolling(
        window=20
    ).std()

    df["bollinger_upper"] = (
        df["sma_20"] + 2 * rolling_std_20
    )

    df["bollinger_lower"] = (
        df["sma_20"] - 2 * rolling_std_20
    )

    return df


# ---------------------------------------------------------
# ANALYSIS FUNCTIONS
# ---------------------------------------------------------

def validate_indicators(latest: pd.Series) -> None:
    """Ensure enough history exists for required indicators."""

    required_columns = [
        "sma_20",
        "sma_50",
        "atr_14",
        "rsi_14",
        "high_20",
        "low_20",
        "volatility_20",
        "relative_volume",
    ]

    missing = [
        column
        for column in required_columns
        if pd.isna(latest[column])
    ]

    if missing:
        raise ValueError(
            "Not enough historical data to calculate: "
            + ", ".join(missing)
        )


def classify_trend(latest: pd.Series) -> str:
    """Classify the daily trend."""

    close = float(latest["close"])
    sma_20 = float(latest["sma_20"])
    sma_50 = float(latest["sma_50"])
    macd = float(latest["macd"])
    macd_signal = float(latest["macd_signal"])

    if (
        close > sma_20 > sma_50
        and macd > macd_signal
    ):
        return "Bullish"

    if (
        close < sma_20 < sma_50
        and macd < macd_signal
    ):
        return "Bearish"

    if close > sma_20 and sma_20 > sma_50:
        return "Moderately bullish"

    if close < sma_20 and sma_20 < sma_50:
        return "Moderately bearish"

    return "Mixed"


def classify_rsi(rsi: float) -> str:
    """Provide a basic RSI interpretation."""

    if rsi >= 70:
        return "Overbought"

    if rsi <= 30:
        return "Oversold"

    if rsi >= 55:
        return "Positive momentum"

    if rsi <= 45:
        return "Negative momentum"

    return "Neutral"


def calculate_zones(
    latest: pd.Series,
    latest_price: float,
) -> dict[str, float]:
    """
    Produce preliminary ATR-based support, resistance,
    entry, invalidation, and profit zones.
    """

    atr = float(latest["atr_14"])
    rolling_low = float(latest["low_20"])
    rolling_high = float(latest["high_20"])
    sma_20 = float(latest["sma_20"])
    sma_50 = float(latest["sma_50"])

    support_candidates = [
        latest_price - atr,
        rolling_low,
        sma_20,
        sma_50,
    ]

    support_candidates = [
        value
        for value in support_candidates
        if value <= latest_price
    ]

    if support_candidates:
        support_center = max(support_candidates)
    else:
        support_center = latest_price - atr

    resistance_candidates = [
        latest_price + atr,
        rolling_high,
        float(latest["high_50"]),
    ]

    resistance_candidates = [
        value
        for value in resistance_candidates
        if value >= latest_price
    ]

    if resistance_candidates:
        resistance_center = min(resistance_candidates)
    else:
        resistance_center = latest_price + atr

    support_tolerance = atr * 0.20
    resistance_tolerance = atr * 0.20

    support_low = support_center - support_tolerance
    support_high = support_center + support_tolerance

    resistance_low = (
        resistance_center - resistance_tolerance
    )

    resistance_high = (
        resistance_center + resistance_tolerance
    )

    pullback_entry_low = support_low
    pullback_entry_high = support_high

    breakout_entry_low = resistance_high
    breakout_entry_high = (
        resistance_high + atr * 0.20
    )

    invalidation_level = support_low - atr * 0.50

    profit_zone_1_low = latest_price + atr
    profit_zone_1_high = latest_price + atr * 1.25

    profit_zone_2_low = latest_price + atr * 1.75
    profit_zone_2_high = latest_price + atr * 2.25

    return {
        "support_low": support_low,
        "support_high": support_high,
        "resistance_low": resistance_low,
        "resistance_high": resistance_high,
        "pullback_entry_low": pullback_entry_low,
        "pullback_entry_high": pullback_entry_high,
        "breakout_entry_low": breakout_entry_low,
        "breakout_entry_high": breakout_entry_high,
        "invalidation_level": invalidation_level,
        "profit_zone_1_low": profit_zone_1_low,
        "profit_zone_1_high": profit_zone_1_high,
        "profit_zone_2_low": profit_zone_2_low,
        "profit_zone_2_high": profit_zone_2_high,
    }


def determine_status(
    latest_price: float,
    zones: dict[str, float],
    trend: str,
) -> str:
    """Determine a preliminary technical setup status."""

    if (
        zones["pullback_entry_low"]
        <= latest_price
        <= zones["pullback_entry_high"]
    ):
        if "bullish" in trend.lower():
            return "PULLBACK ZONE REACHED"

        return "AT SUPPORT"

    if (
        zones["breakout_entry_low"]
        <= latest_price
        <= zones["breakout_entry_high"]
    ):
        return "BREAKOUT ZONE"

    if latest_price < zones["invalidation_level"]:
        return "TECHNICAL SETUP INVALIDATED"

    return "WAIT"


def calculate_risk_reward(
    entry_price: float,
    target_price: float,
    invalidation_price: float,
) -> float | None:
    """Calculate estimated reward-to-risk ratio."""

    estimated_reward = target_price - entry_price
    estimated_risk = entry_price - invalidation_price

    if estimated_risk <= 0:
        return None

    return estimated_reward / estimated_risk


# ---------------------------------------------------------
# CHARTS
# ---------------------------------------------------------

def create_price_chart(
    ticker: str,
    bars: pd.DataFrame,
    zones: dict[str, float],
) -> go.Figure:
    """Create the daily candlestick chart."""

    chart = go.Figure()

    chart.add_trace(
        go.Candlestick(
            x=bars["timestamp"],
            open=bars["open"],
            high=bars["high"],
            low=bars["low"],
            close=bars["close"],
            name=ticker,
        )
    )

    chart.add_trace(
        go.Scatter(
            x=bars["timestamp"],
            y=bars["sma_20"],
            mode="lines",
            name="20-day SMA",
        )
    )

    chart.add_trace(
        go.Scatter(
            x=bars["timestamp"],
            y=bars["sma_50"],
            mode="lines",
            name="50-day SMA",
        )
    )

    chart.add_trace(
        go.Scatter(
            x=bars["timestamp"],
            y=bars["bollinger_upper"],
            mode="lines",
            name="Upper Bollinger Band",
            line={"dash": "dot"},
        )
    )

    chart.add_trace(
        go.Scatter(
            x=bars["timestamp"],
            y=bars["bollinger_lower"],
            mode="lines",
            name="Lower Bollinger Band",
            line={"dash": "dot"},
        )
    )

    chart.add_hrect(
        y0=zones["support_low"],
        y1=zones["support_high"],
        opacity=0.15,
        line_width=0,
        annotation_text="Support / pullback zone",
        annotation_position="bottom right",
    )

    chart.add_hrect(
        y0=zones["resistance_low"],
        y1=zones["resistance_high"],
        opacity=0.15,
        line_width=0,
        annotation_text="Resistance zone",
        annotation_position="top right",
    )

    chart.add_hline(
        y=zones["invalidation_level"],
        line_dash="dash",
        annotation_text="Invalidation",
        annotation_position="bottom left",
    )

    chart.update_layout(
        title=f"{ticker} daily technical chart",
        xaxis_title="Date",
        yaxis_title="Price (USD)",
        xaxis_rangeslider_visible=False,
        height=700,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
        },
    )

    return chart


def create_volume_chart(
    ticker: str,
    bars: pd.DataFrame,
) -> go.Figure:
    """Create a daily volume chart."""

    chart = go.Figure()

    chart.add_trace(
        go.Bar(
            x=bars["timestamp"],
            y=bars["volume"],
            name="Daily IEX volume",
        )
    )

    chart.add_trace(
        go.Scatter(
            x=bars["timestamp"],
            y=bars["average_volume_20"],
            mode="lines",
            name="20-day average volume",
        )
    )

    chart.update_layout(
        title=f"{ticker} volume",
        xaxis_title="Date",
        yaxis_title="IEX Volume",
        height=350,
    )

    return chart


def create_macd_chart(
    ticker: str,
    bars: pd.DataFrame,
) -> go.Figure:
    """Create a MACD chart."""

    chart = go.Figure()

    chart.add_trace(
        go.Scatter(
            x=bars["timestamp"],
            y=bars["macd"],
            mode="lines",
            name="MACD",
        )
    )

    chart.add_trace(
        go.Scatter(
            x=bars["timestamp"],
            y=bars["macd_signal"],
            mode="lines",
            name="Signal",
        )
    )

    chart.add_trace(
        go.Bar(
            x=bars["timestamp"],
            y=bars["macd_histogram"],
            name="Histogram",
        )
    )

    chart.update_layout(
        title=f"{ticker} MACD",
        xaxis_title="Date",
        height=350,
    )

    return chart


# ---------------------------------------------------------
# STREAMLIT INTERFACE
# ---------------------------------------------------------

st.title("📈 Quant Research Platform")
st.caption(
    "Cloud-based, evidence-grounded stock research prototype"
)

ticker = st.text_input(
    "Enter a U.S. stock ticker",
    value="MU",
    max_chars=10,
).strip().upper()

analyze_button = st.button(
    "Analyze",
    type="primary",
)

if analyze_button:
    if not ticker:
        st.error("Enter a stock ticker.")

    elif not ticker.replace(".", "").replace("-", "").isalnum():
        st.error("Enter a valid stock ticker.")

    else:
        try:
            with st.spinner(
                f"Loading IEX market data and analyzing {ticker}..."
            ):
                latest_price, bars = get_stock_data(ticker)

                if len(bars) < 60:
                    raise ValueError(
                        "At least 60 daily bars are required "
                        "for this analysis."
                    )

                bars = calculate_indicators(bars)

                latest = bars.iloc[-1]
                validate_indicators(latest)

                previous_close = float(
                    bars.iloc[-2]["close"]
                )

                daily_change = (
                    latest_price - previous_close
                )

                daily_change_pct = (
                    daily_change / previous_close * 100
                )

                trend = classify_trend(latest)

                rsi_value = float(latest["rsi_14"])
                rsi_status = classify_rsi(rsi_value)

                zones = calculate_zones(
                    latest=latest,
                    latest_price=latest_price,
                )

                setup_status = determine_status(
                    latest_price=latest_price,
                    zones=zones,
                    trend=trend,
                )

                risk_reward = calculate_risk_reward(
                    entry_price=zones[
                        "pullback_entry_high"
                    ],
                    target_price=zones[
                        "profit_zone_1_high"
                    ],
                    invalidation_price=zones[
                        "invalidation_level"
                    ],
                )

            st.subheader(f"{ticker} market snapshot")

            metric_1, metric_2, metric_3, metric_4 = st.columns(4)

            metric_1.metric(
                "Latest IEX price",
                f"${latest_price:,.2f}",
                f"{daily_change_pct:+.2f}%",
            )

            metric_2.metric(
                "Previous close",
                f"${previous_close:,.2f}",
            )

            metric_3.metric(
                "Latest daily high",
                f"${float(latest['high']):,.2f}",
            )

            metric_4.metric(
                "Latest IEX volume",
                f"{int(latest['volume']):,}",
            )

            st.subheader("Technical snapshot")

            tech_1, tech_2, tech_3, tech_4 = st.columns(4)

            tech_1.metric(
                "Daily trend",
                trend,
            )

            tech_2.metric(
                "RSI (14)",
                f"{rsi_value:.1f}",
                rsi_status,
            )

            tech_3.metric(
                "ATR (14)",
                f"${float(latest['atr_14']):,.2f}",
            )

            tech_4.metric(
                "Annualized volatility",
                f"{float(latest['volatility_20']) * 100:.1f}%",
            )

            tech_5, tech_6, tech_7, tech_8 = st.columns(4)

            tech_5.metric(
                "20-day SMA",
                f"${float(latest['sma_20']):,.2f}",
            )

            tech_6.metric(
                "50-day SMA",
                f"${float(latest['sma_50']):,.2f}",
            )

            tech_7.metric(
                "Relative volume",
                f"{float(latest['relative_volume']):.2f}×",
            )

            tech_8.metric(
                "Setup status",
                setup_status,
            )

            st.subheader("Preliminary price zones")

            zone_1, zone_2 = st.columns(2)

            with zone_1:
                st.info(
                    "**Pullback entry zone**\n\n"
                    f"${zones['pullback_entry_low']:,.2f}"
                    " – "
                    f"${zones['pullback_entry_high']:,.2f}"
                )

                st.info(
                    "**Support zone**\n\n"
                    f"${zones['support_low']:,.2f}"
                    " – "
                    f"${zones['support_high']:,.2f}"
                )

                st.warning(
                    "**Invalidation level**\n\n"
                    f"${zones['invalidation_level']:,.2f}"
                )

            with zone_2:
                st.info(
                    "**Breakout entry zone**\n\n"
                    f"${zones['breakout_entry_low']:,.2f}"
                    " – "
                    f"${zones['breakout_entry_high']:,.2f}"
                )

                st.info(
                    "**Profit zone 1**\n\n"
                    f"${zones['profit_zone_1_low']:,.2f}"
                    " – "
                    f"${zones['profit_zone_1_high']:,.2f}"
                )

                st.info(
                    "**Profit zone 2**\n\n"
                    f"${zones['profit_zone_2_low']:,.2f}"
                    " – "
                    f"${zones['profit_zone_2_high']:,.2f}"
                )

            if risk_reward is not None:
                st.metric(
                    "Estimated first-target reward/risk",
                    f"{risk_reward:.2f}:1",
                )

            st.warning(
                "These are preliminary mathematical zones based on "
                "daily ATR, moving averages, and rolling highs/lows. "
                "They are not yet generated by the final forecasting "
                "model and should not be treated as financial advice."
            )

            price_chart = create_price_chart(
                ticker=ticker,
                bars=bars,
                zones=zones,
            )

            st.plotly_chart(
                price_chart,
                use_container_width=True,
            )

            chart_column_1, chart_column_2 = st.columns(2)

            with chart_column_1:
                volume_chart = create_volume_chart(
                    ticker=ticker,
                    bars=bars,
                )

                st.plotly_chart(
                    volume_chart,
                    use_container_width=True,
                )

            with chart_column_2:
                macd_chart = create_macd_chart(
                    ticker=ticker,
                    bars=bars,
                )

                st.plotly_chart(
                    macd_chart,
                    use_container_width=True,
                )

            st.subheader("Recent daily bars")

            display_columns = [
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "sma_20",
                "sma_50",
                "atr_14",
                "rsi_14",
                "relative_volume",
            ]

            recent_data = bars[
                display_columns
            ].tail(20).copy()

            recent_data["timestamp"] = (
                recent_data["timestamp"]
                .astype(str)
            )

            st.dataframe(
                recent_data,
                use_container_width=True,
                hide_index=True,
            )

            st.caption(
                "Market data is supplied through Alpaca's IEX "
                "feed. IEX prices and volume may differ from the "
                "full consolidated U.S. market. This application "
                "does not place real trades."
            )

        except Exception as exc:
            st.error(
                f"Unable to analyze {ticker}: {exc}"
            )
