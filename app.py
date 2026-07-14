from __future__ import annotations

import pandas as pd
import streamlit as st

from analysis import (
    build_technical_summary,
    calculate_indicators,
    calculate_risk_reward,
    calculate_zones,
    validate_indicators,
)
from charts import (
    create_macd_chart,
    create_price_chart,
    create_rsi_chart,
    create_volume_chart,
)
from database import (
    get_database_engine,
    get_recent_analyses,
    initialize_database,
    save_analysis,
)
from market_data import get_stock_data


st.set_page_config(
    page_title="Quant Research Platform",
    page_icon="📈",
    layout="wide",
)


@st.cache_resource
def get_db_engine():
    engine = get_database_engine()
    initialize_database(engine)
    return engine


@st.cache_data(ttl=60)
def load_market_data(ticker: str):
    return get_stock_data(ticker)


def score_label(score: int) -> str:
    if score >= 85:
        return "Strong"
    if score >= 70:
        return "Positive"
    if score >= 55:
        return "Neutral"
    if score >= 40:
        return "Weak"
    return "Very weak"


def format_range(low: float, high: float) -> str:
    return f"${low:,.2f} – ${high:,.2f}"


st.title("📈 Quant Research Platform")
st.caption(
    "Cloud-based stock research with live IEX data, technical scoring, "
    "price zones, and PostgreSQL history."
)

with st.sidebar:
    st.header("Research controls")
    ticker = st.text_input(
        "Ticker",
        value="MU",
        max_chars=10,
    ).strip().upper()
    analyze = st.button("Analyze stock", type="primary", use_container_width=True)

    st.divider()
    st.caption(
        "Current version: technical-v2\n\n"
        "Data feed: Alpaca IEX\n\n"
        "Execution: disabled"
    )

if not analyze:
    st.info("Enter a ticker in the sidebar and select **Analyze stock**.")
    st.stop()

if not ticker or not ticker.replace(".", "").replace("-", "").isalnum():
    st.error("Enter a valid ticker symbol.")
    st.stop()

try:
    with st.spinner(f"Loading and analyzing {ticker}..."):
        latest_price, bars = load_market_data(ticker)
        bars = calculate_indicators(bars)
        latest = bars.iloc[-1]
        validate_indicators(latest)

        previous_close = float(bars.iloc[-2]["close"])
        daily_change_pct = (latest_price - previous_close) / previous_close * 100

        zones = calculate_zones(latest, latest_price)
        risk_reward = calculate_risk_reward(
            entry_price=zones["pullback_entry_high"],
            target_price=zones["profit_zone_1_high"],
            invalidation_price=zones["invalidation_level"],
        )
        summary = build_technical_summary(
            latest=latest,
            latest_price=latest_price,
            zones=zones,
            risk_reward=risk_reward,
        )

    st.subheader(f"{ticker} overview")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Latest IEX price", f"${latest_price:,.2f}", f"{daily_change_pct:+.2f}%")
    c2.metric("Technical score", f"{summary.technical_score}/100", score_label(summary.technical_score))
    c3.metric("Confidence", f"{summary.confidence}%")
    c4.metric("Setup status", summary.setup_status)

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Trend", summary.trend)
    c6.metric("RSI (14)", f"{float(latest['rsi_14']):.1f}", summary.rsi_status)
    c7.metric("ATR (14)", f"${float(latest['atr_14']):,.2f}")
    c8.metric("Relative volume", f"{float(latest['relative_volume']):.2f}×")

    st.subheader("Score breakdown")
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Trend", f"{summary.trend_score}/100")
    s2.metric("Momentum", f"{summary.momentum_score}/100")
    s3.metric("Volume", f"{summary.volume_score}/100")
    s4.metric("Risk quality", f"{summary.risk_score}/100")
    s5.metric("Reward/risk", f"{summary.reward_risk_score}/100")

    st.subheader("Trade-planning zones")
    left, right = st.columns(2)

    with left:
        st.info(
            f"**Pullback entry**\n\n{format_range(zones['pullback_entry_low'], zones['pullback_entry_high'])}"
        )
        st.info(
            f"**Support**\n\n{format_range(zones['support_low'], zones['support_high'])}"
        )
        st.warning(
            f"**Invalidation**\n\n${zones['invalidation_level']:,.2f}"
        )

    with right:
        st.info(
            f"**Breakout entry**\n\n{format_range(zones['breakout_entry_low'], zones['breakout_entry_high'])}"
        )
        st.info(
            f"**Profit zone 1**\n\n{format_range(zones['profit_zone_1_low'], zones['profit_zone_1_high'])}"
        )
        st.info(
            f"**Profit zone 2**\n\n{format_range(zones['profit_zone_2_low'], zones['profit_zone_2_high'])}"
        )

    if risk_reward is not None:
        st.metric("Estimated first-target reward/risk", f"{risk_reward:.2f}:1")

    st.subheader("Technical reasoning")
    for reason in summary.reasoning:
        st.write(f"• {reason}")

    st.warning(
        "These levels are preliminary mathematical zones derived from daily "
        "ATR, moving averages, and rolling highs/lows. They are not a guarantee "
        "and are not yet produced by the future forecasting model."
    )

    st.plotly_chart(
        create_price_chart(ticker, bars, zones),
        use_container_width=True,
    )

    chart_col_1, chart_col_2 = st.columns(2)
    with chart_col_1:
        st.plotly_chart(
            create_volume_chart(ticker, bars),
            use_container_width=True,
        )
        st.plotly_chart(
            create_rsi_chart(ticker, bars),
            use_container_width=True,
        )

    with chart_col_2:
        st.plotly_chart(
            create_macd_chart(ticker, bars),
            use_container_width=True,
        )

        st.subheader("Latest indicator values")
        st.dataframe(
            pd.DataFrame(
                {
                    "Metric": [
                        "20-day SMA",
                        "50-day SMA",
                        "MACD",
                        "MACD signal",
                        "Annualized volatility",
                    ],
                    "Value": [
                        f"${float(latest['sma_20']):,.2f}",
                        f"${float(latest['sma_50']):,.2f}",
                        f"{float(latest['macd']):,.2f}",
                        f"{float(latest['macd_signal']):,.2f}",
                        f"{float(latest['volatility_20']) * 100:.1f}%",
                    ],
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Recent daily bars")
    recent = bars[
        [
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
    ].tail(20).copy()
    recent["timestamp"] = recent["timestamp"].astype(str)
    st.dataframe(recent, use_container_width=True, hide_index=True)

    database_engine = get_db_engine()
    analysis_id = save_analysis(
        database_engine,
        ticker=ticker,
        latest_price=latest_price,
        previous_close=previous_close,
        daily_change_pct=daily_change_pct,
        trend=summary.trend,
        setup_status=summary.setup_status,
        technical_score=summary.technical_score,
        confidence=summary.confidence,
        latest=latest,
        zones=zones,
        risk_reward=risk_reward,
    )

    st.subheader("Saved analysis history")
    history = get_recent_analyses(database_engine, ticker=ticker, limit=20)

    if history:
        history_df = pd.DataFrame(history)
        columns = [
            "analyzed_at",
            "latest_price",
            "daily_change_pct",
            "technical_score",
            "confidence",
            "trend",
            "setup_status",
            "rsi_14",
            "atr_14",
            "relative_volume",
            "model_version",
        ]
        st.dataframe(
            history_df[columns],
            use_container_width=True,
            hide_index=True,
        )
        st.success(f"Analysis saved as database record #{analysis_id}.")
    else:
        st.info("No saved analyses exist for this ticker yet.")

    st.caption(
        "Market data is supplied through Alpaca's IEX feed. IEX price and "
        "volume may differ from consolidated U.S. market data. Real order "
        "execution remains disabled."
    )

except Exception as exc:
    st.error(f"Unable to analyze {ticker}: {exc}")
    st.exception(exc)
