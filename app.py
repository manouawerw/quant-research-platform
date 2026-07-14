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
    create_relative_strength_chart,
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
from relative_strength import (
    calculate_relative_strength,
    detect_market_regime,
)
from scoring import build_stock_score


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


def format_range(low: float, high: float) -> str:
    return f"${low:,.2f} – ${high:,.2f}"


st.title("📈 Quant Research Platform")
st.caption(
    "Live IEX data, weighted technical scoring, relative strength, "
    "market regime, charts, and PostgreSQL history."
)

with st.sidebar:
    st.header("Research controls")

    ticker = st.text_input(
        "Ticker",
        value="MU",
        max_chars=10,
    ).strip().upper()

    benchmark = st.selectbox(
        "Benchmark",
        options=["SPY", "QQQ"],
        index=0,
    )

    analyze = st.button(
        "Analyze stock",
        type="primary",
        use_container_width=True,
    )

    st.divider()

    st.caption(
        "Current model: technical-v3\n\n"
        "Data feed: Alpaca IEX\n\n"
        "Real execution: disabled"
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
        _, benchmark_bars = load_market_data(benchmark)

        bars = calculate_indicators(bars)
        latest = bars.iloc[-1]
        validate_indicators(latest)

        previous_close = float(bars.iloc[-2]["close"])
        daily_change_pct = (
            (latest_price - previous_close) / previous_close * 100
        )

        zones = calculate_zones(
            latest=latest,
            latest_price=latest_price,
        )

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

        stock_score = build_stock_score(
            latest=latest,
            risk_reward=risk_reward,
        )

        relative_summary, relative_frame = calculate_relative_strength(
            stock_bars=bars,
            benchmark_bars=benchmark_bars,
            benchmark=benchmark,
        )

        market_regime = detect_market_regime(benchmark_bars)

    st.subheader(f"{ticker} overview")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Latest IEX price",
        f"${latest_price:,.2f}",
        f"{daily_change_pct:+.2f}%",
    )

    c2.metric(
        "Technical score",
        f"{stock_score.overall_score}/100",
        stock_score.classification,
    )

    c3.metric(
        f"Relative strength vs {benchmark}",
        f"{relative_summary.score}/100",
        relative_summary.ratio_trend,
    )

    c4.metric(
        "Market regime",
        market_regime.label,
        f"{market_regime.score}/100",
    )

    c5, c6, c7, c8 = st.columns(4)

    c5.metric("Trend", summary.trend)

    c6.metric(
        "RSI (14)",
        f"{float(latest['rsi_14']):.1f}",
        summary.rsi_status,
    )

    c7.metric(
        "ATR (14)",
        f"${float(latest['atr_14']):,.2f}",
    )

    c8.metric(
        "Relative volume",
        f"{float(latest['relative_volume']):.2f}×",
    )

    st.subheader("Market context")

    context_1, context_2, context_3, context_4 = st.columns(4)

    context_1.metric(
        f"{ticker} 20-day return",
        f"{relative_summary.stock_return_20d:+.2f}%",
    )

    context_2.metric(
        f"{benchmark} 20-day return",
        f"{relative_summary.benchmark_return_20d:+.2f}%",
    )

    context_3.metric(
        "20-day excess return",
        f"{relative_summary.excess_return_20d:+.2f}%",
    )

    context_4.metric(
        "60-day excess return",
        f"{relative_summary.excess_return_60d:+.2f}%",
    )

    st.info(market_regime.explanation)

    st.subheader("Score breakdown")

    score_columns = st.columns(len(stock_score.components))

    for column, component in zip(
        score_columns,
        stock_score.components,
    ):
        column.metric(
            component.name,
            f"{component.score}/100",
        )

    support_col, risk_col = st.columns(2)

    with support_col:
        st.markdown("#### Supporting factors")

        if stock_score.bullish_factors:
            for factor in stock_score.bullish_factors:
                st.success(factor)
        else:
            st.info(
                "No strongly supportive technical factors were detected."
            )

    with risk_col:
        st.markdown("#### Risk factors")

        if stock_score.bearish_factors:
            for factor in stock_score.bearish_factors:
                st.warning(factor)
        else:
            st.info(
                "No severely weak technical factors were detected."
            )

    st.subheader("Trade-planning zones")

    left, right = st.columns(2)

    with left:
        st.info(
            "**Pullback entry**\n\n"
            + format_range(
                zones["pullback_entry_low"],
                zones["pullback_entry_high"],
            )
        )

        st.info(
            "**Support**\n\n"
            + format_range(
                zones["support_low"],
                zones["support_high"],
            )
        )

        st.warning(
            "**Invalidation**\n\n"
            f"${zones['invalidation_level']:,.2f}"
        )

    with right:
        st.info(
            "**Breakout entry**\n\n"
            + format_range(
                zones["breakout_entry_low"],
                zones["breakout_entry_high"],
            )
        )

        st.info(
            "**Profit zone 1**\n\n"
            + format_range(
                zones["profit_zone_1_low"],
                zones["profit_zone_1_high"],
            )
        )

        st.info(
            "**Profit zone 2**\n\n"
            + format_range(
                zones["profit_zone_2_low"],
                zones["profit_zone_2_high"],
            )
        )

    if risk_reward is not None:
        st.metric(
            "Estimated first-target reward/risk",
            f"{risk_reward:.2f}:1",
        )

    st.subheader("Technical reasoning")

    for component in stock_score.components:
        st.markdown(
            f"**{component.name}:** {component.explanation}"
        )

    st.warning(
        "These scores and levels are preliminary research estimates. "
        "They are not guarantees and are not financial advice."
    )

    st.plotly_chart(
        create_price_chart(
            ticker=ticker,
            bars=bars,
            zones=zones,
        ),
        use_container_width=True,
    )

    st.plotly_chart(
        create_relative_strength_chart(
            ticker=ticker,
            benchmark=benchmark,
            relative_frame=relative_frame,
        ),
        use_container_width=True,
    )

    chart_col_1, chart_col_2 = st.columns(2)

    with chart_col_1:
        st.plotly_chart(
            create_volume_chart(
                ticker=ticker,
                bars=bars,
            ),
            use_container_width=True,
        )

        st.plotly_chart(
            create_rsi_chart(
                ticker=ticker,
                bars=bars,
            ),
            use_container_width=True,
        )

    with chart_col_2:
        st.plotly_chart(
            create_macd_chart(
                ticker=ticker,
                bars=bars,
            ),
            use_container_width=True,
        )

        st.subheader("Latest indicator values")

        indicator_table = pd.DataFrame(
            {
                "Metric": [
                    "20-day SMA",
                    "50-day SMA",
                    "MACD",
                    "MACD signal",
                    "Annualized volatility",
                    "Relative volume",
                    f"Relative strength vs {benchmark}",
                ],
                "Value": [
                    f"${float(latest['sma_20']):,.2f}",
                    f"${float(latest['sma_50']):,.2f}",
                    f"{float(latest['macd']):,.2f}",
                    f"{float(latest['macd_signal']):,.2f}",
                    f"{float(latest['volatility_20']) * 100:.1f}%",
                    f"{float(latest['relative_volume']):.2f}×",
                    f"{relative_summary.score}/100",
                ],
            }
        )

        st.dataframe(
            indicator_table,
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

    st.dataframe(
        recent,
        use_container_width=True,
        hide_index=True,
    )

    database_engine = get_db_engine()

    analysis_id = save_analysis(
        database_engine,
        ticker=ticker,
        latest_price=latest_price,
        previous_close=previous_close,
        daily_change_pct=daily_change_pct,
        trend=summary.trend,
        setup_status=summary.setup_status,
        technical_score=stock_score.overall_score,
        confidence=stock_score.confidence,
        latest=latest,
        zones=zones,
        risk_reward=risk_reward,
    )

    st.subheader("Saved analysis history")

    history = get_recent_analyses(
        database_engine,
        ticker=ticker,
        limit=20,
    )

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

        st.success(
            f"Analysis saved as database record #{analysis_id}."
        )

    st.caption(
        "Market data is supplied through Alpaca's IEX feed. IEX price and "
        "volume may differ from consolidated U.S. market data. Real order "
        "execution remains disabled."
    )

except Exception as exc:
    st.error(
        f"Unable to analyze {ticker}: {exc}"
    )
    st.exception(exc)
