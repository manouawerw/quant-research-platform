from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

from ai_report import generate_research_report
from analysis import (
    build_technical_summary,
    calculate_indicators,
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
    count_ai_reports_today,
    get_database_engine,
    get_latest_ai_report,
    get_recent_analyses,
    initialize_database,
    save_ai_report,
    save_analysis,
)
from market_data import get_stock_data
from price_zones import build_price_plan
from relative_strength import (
    calculate_relative_strength,
    detect_market_regime,
)
from scoring import build_stock_score


AUTO_SCORE_THRESHOLD = 85
AUTO_RELATIVE_STRENGTH_THRESHOLD = 70
MAX_AI_REPORTS_PER_DAY = 10
REPORT_CACHE_HOURS = 12


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


def initialize_session_state() -> None:
    defaults = {
        "analysis_ready": False,
        "analysis_bundle": None,
        "active_ticker": "",
        "active_benchmark": "SPY",
        "latest_report": None,
        "last_saved_analysis_id": None,
        "report_message": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def format_range(low: float, high: float) -> str:
    return f"${low:,.2f} – ${high:,.2f}"


def report_age_label(generated_at: datetime) -> str:
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)

    hours = (
        datetime.now(timezone.utc) - generated_at
    ).total_seconds() / 3600

    if hours < 1:
        return "Fresh"
    if hours < 24:
        return "Recent"
    return "Needs refresh"


def display_ai_report(report: dict[str, Any]) -> None:
    status = report_age_label(report["generated_at"])

    st.markdown(
        f"**Status:** {status}  \n"
        f"**Generated:** {report['generated_at']}  \n"
        f"**Model:** {report['model']}  \n"
        f"**Trigger:** {report['trigger_type']}"
    )

    st.markdown(report["report_markdown"])

    sources = report.get("sources", [])

    if sources:
        st.markdown("### Sources")

        grouped: dict[str, list[dict[str, Any]]] = {}

        for source in sources:
            publisher = source.get("publisher") or "Other sources"
            grouped.setdefault(publisher, []).append(source)

        for publisher, items in grouped.items():
            with st.expander(f"{publisher} ({len(items)})"):
                seen_urls: set[str] = set()

                for source in items:
                    url = source.get("url")
                    title = source.get("title") or url or "Source"

                    if not url or url in seen_urls:
                        continue

                    seen_urls.add(url)
                    st.markdown(f"- [{title}]({url})")


def run_analysis(
    ticker: str,
    benchmark: str,
    database_engine,
) -> dict[str, Any]:
    latest_price, bars = load_market_data(ticker)
    _, benchmark_bars = load_market_data(benchmark)

    bars = calculate_indicators(bars)
    latest = bars.iloc[-1]
    validate_indicators(latest)

    previous_close = float(bars.iloc[-2]["close"])
    daily_change_pct = (
        (latest_price - previous_close) / previous_close * 100
    )

    preliminary_zones = {
        "support_low": float(latest["low_20"]),
        "support_high": float(latest["sma_20"]),
        "resistance_low": float(latest["high_20"]),
        "resistance_high": float(latest["high_50"]),
        "pullback_entry_low": float(latest["low_20"]),
        "pullback_entry_high": float(latest["sma_20"]),
        "breakout_entry_low": float(latest["high_20"]),
        "breakout_entry_high": float(latest["high_50"]),
        "invalidation_level": float(latest["low_20"])
        - float(latest["atr_14"]),
        "profit_zone_1_low": latest_price
        + float(latest["atr_14"]),
        "profit_zone_1_high": latest_price
        + float(latest["atr_14"]) * 1.25,
        "profit_zone_2_low": latest_price
        + float(latest["atr_14"]) * 1.75,
        "profit_zone_2_high": latest_price
        + float(latest["atr_14"]) * 2.25,
    }

    preliminary_summary = build_technical_summary(
        latest=latest,
        latest_price=latest_price,
        zones=preliminary_zones,
        risk_reward=None,
    )

    preliminary_score = build_stock_score(
        latest=latest,
        risk_reward=None,
    )

    relative_summary, relative_frame = calculate_relative_strength(
        stock_bars=bars,
        benchmark_bars=benchmark_bars,
        benchmark=benchmark,
    )

    market_regime = detect_market_regime(benchmark_bars)

    price_plan = build_price_plan(
        bars=bars,
        latest_price=latest_price,
        trend=preliminary_summary.trend,
        technical_score=preliminary_score.overall_score,
        relative_strength_score=relative_summary.score,
        market_regime=market_regime.label,
    )

    zones = price_plan.as_legacy_zones()

    summary = build_technical_summary(
        latest=latest,
        latest_price=latest_price,
        zones=zones,
        risk_reward=price_plan.risk_reward_1,
    )

    stock_score = build_stock_score(
        latest=latest,
        risk_reward=price_plan.risk_reward_1,
    )

    analysis_id = save_analysis(
        database_engine,
        ticker=ticker,
        latest_price=latest_price,
        previous_close=previous_close,
        daily_change_pct=daily_change_pct,
        trend=summary.trend,
        setup_status=price_plan.setup_status,
        technical_score=stock_score.overall_score,
        confidence=stock_score.confidence,
        latest=latest,
        zones=zones,
        risk_reward=price_plan.risk_reward_1,
    )

    technical_context = {
        "latest_price": latest_price,
        "daily_change_pct": daily_change_pct,
        "technical_score": stock_score.overall_score,
        "technical_score_confidence": stock_score.confidence,
        "classification": stock_score.classification,
        "trend": summary.trend,
        "setup_type": price_plan.setup_type,
        "setup_status": price_plan.setup_status,
        "price_plan_confidence": price_plan.confidence,
        "rsi_14": float(latest["rsi_14"]),
        "atr_14": float(latest["atr_14"]),
        "volatility_20_pct": float(latest["volatility_20"]) * 100,
        "relative_volume": float(latest["relative_volume"]),
        "relative_strength_score": relative_summary.score,
        "relative_strength_trend": relative_summary.ratio_trend,
        "stock_return_20d_pct": relative_summary.stock_return_20d,
        "benchmark_return_20d_pct": (
            relative_summary.benchmark_return_20d
        ),
        "excess_return_20d_pct": relative_summary.excess_return_20d,
        "excess_return_60d_pct": relative_summary.excess_return_60d,
        "market_regime": market_regime.label,
        "market_regime_explanation": market_regime.explanation,
        "preferred_pullback_range": [
            price_plan.entry_low,
            price_plan.entry_high,
        ],
        "breakout_confirmation_range": [
            price_plan.breakout_entry_low,
            price_plan.breakout_entry_high,
        ],
        "support_zone": [
            price_plan.support_low,
            price_plan.support_high,
        ],
        "resistance_zone": [
            price_plan.resistance_low,
            price_plan.resistance_high,
        ],
        "invalidation_level": price_plan.invalidation,
        "profit_zone_1": [
            price_plan.target_1_low,
            price_plan.target_1_high,
        ],
        "profit_zone_2": [
            price_plan.target_2_low,
            price_plan.target_2_high,
        ],
        "estimated_risk_reward_1": price_plan.risk_reward_1,
        "estimated_risk_reward_2": price_plan.risk_reward_2,
        "price_plan_reasons": price_plan.reasons,
        "price_plan_warnings": price_plan.warnings,
        "score_components": [
            {
                "name": component.name,
                "score": component.score,
                "explanation": component.explanation,
            }
            for component in stock_score.components
        ],
    }

    return {
        "ticker": ticker,
        "benchmark": benchmark,
        "latest_price": latest_price,
        "bars": bars,
        "latest": latest,
        "daily_change_pct": daily_change_pct,
        "zones": zones,
        "price_plan": price_plan,
        "summary": summary,
        "stock_score": stock_score,
        "relative_summary": relative_summary,
        "relative_frame": relative_frame,
        "market_regime": market_regime,
        "analysis_id": analysis_id,
        "technical_context": technical_context,
        "company_context": {
            "ticker": ticker,
            "benchmark": benchmark,
        },
    }


initialize_session_state()
database_engine = get_db_engine()

st.title("📈 Quant Research Platform")
st.caption(
    "Evidence-grounded research, technical scoring, relative strength, "
    "market regime and transparent price-planning ranges."
)

with st.sidebar:
    st.header("Research controls")

    with st.form("analysis_form"):
        ticker_input = st.text_input(
            "Ticker",
            value=(
                st.session_state.active_ticker
                if st.session_state.active_ticker
                else "MU"
            ),
            max_chars=10,
        ).strip().upper()

        benchmark_input = st.selectbox(
            "Benchmark",
            options=["SPY", "QQQ"],
            index=(
                1
                if st.session_state.active_benchmark == "QQQ"
                else 0
            ),
        )

        analyze_submitted = st.form_submit_button(
            "Analyze stock",
            type="primary",
            use_container_width=True,
        )

    st.divider()

    st.caption(
        f"Auto-report threshold: {AUTO_SCORE_THRESHOLD}\n\n"
        f"Daily AI report cap: {MAX_AI_REPORTS_PER_DAY}\n\n"
        "Real execution: disabled"
    )

if analyze_submitted:
    if (
        not ticker_input
        or not ticker_input.replace(".", "").replace("-", "").isalnum()
    ):
        st.error("Enter a valid ticker symbol.")
    else:
        try:
            with st.spinner(f"Loading and analyzing {ticker_input}..."):
                bundle = run_analysis(
                    ticker=ticker_input,
                    benchmark=benchmark_input,
                    database_engine=database_engine,
                )

            st.session_state.analysis_bundle = bundle
            st.session_state.analysis_ready = True
            st.session_state.active_ticker = ticker_input
            st.session_state.active_benchmark = benchmark_input
            st.session_state.last_saved_analysis_id = bundle["analysis_id"]
            st.session_state.latest_report = get_latest_ai_report(
                database_engine,
                ticker_input,
            )
            st.session_state.report_message = None

        except Exception as exc:
            st.session_state.analysis_ready = False
            st.session_state.analysis_bundle = None
            st.error(f"Unable to analyze {ticker_input}: {exc}")

if not st.session_state.analysis_ready:
    st.info("Enter a ticker in the sidebar and select **Analyze stock**.")
    st.stop()

bundle = st.session_state.analysis_bundle

ticker = bundle["ticker"]
benchmark = bundle["benchmark"]
latest_price = bundle["latest_price"]
bars = bundle["bars"]
latest = bundle["latest"]
daily_change_pct = bundle["daily_change_pct"]
zones = bundle["zones"]
price_plan = bundle["price_plan"]
summary = bundle["summary"]
stock_score = bundle["stock_score"]
relative_summary = bundle["relative_summary"]
relative_frame = bundle["relative_frame"]
market_regime = bundle["market_regime"]

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

st.subheader("Model-generated price plan")

p1, p2, p3, p4 = st.columns(4)

p1.metric(
    "Setup",
    price_plan.setup_status,
    price_plan.setup_type,
)

p2.metric(
    "Price-plan confidence",
    f"{price_plan.confidence}/100",
    "rules score, not probability",
)

p3.metric(
    "Target 1 reward/risk",
    (
        f"{price_plan.risk_reward_1:.2f}:1"
        if price_plan.risk_reward_1 is not None
        else "Unavailable"
    ),
)

p4.metric(
    "Target 2 reward/risk",
    (
        f"{price_plan.risk_reward_2:.2f}:1"
        if price_plan.risk_reward_2 is not None
        else "Unavailable"
    ),
)

left, right = st.columns(2)

with left:
    st.info(
        "**Preferred pullback range**\n\n"
        + format_range(
            price_plan.entry_low,
            price_plan.entry_high,
        )
    )

    st.info(
        "**Support zone**\n\n"
        + format_range(
            price_plan.support_low,
            price_plan.support_high,
        )
    )

    st.warning(
        "**Invalidation level**\n\n"
        f"${price_plan.invalidation:,.2f}"
    )

with right:
    st.info(
        "**Breakout confirmation range**\n\n"
        + format_range(
            price_plan.breakout_entry_low,
            price_plan.breakout_entry_high,
        )
    )

    st.info(
        "**Profit zone 1**\n\n"
        + format_range(
            price_plan.target_1_low,
            price_plan.target_1_high,
        )
    )

    st.info(
        "**Profit zone 2**\n\n"
        + format_range(
            price_plan.target_2_low,
            price_plan.target_2_high,
        )
    )

reason_col, warning_col = st.columns(2)

with reason_col:
    st.markdown("#### Why the setup may work")

    if price_plan.reasons:
        for reason in price_plan.reasons:
            st.success(reason)
    else:
        st.info("No strong supporting conditions were detected.")

with warning_col:
    st.markdown("#### Why the setup may fail")

    if price_plan.warnings:
        for warning in price_plan.warnings:
            st.warning(warning)
    else:
        st.info("No major model warnings were detected.")

st.warning(
    "These are model-generated research ranges, not guaranteed buy or sell "
    "prices. A setup may be marked NO VALID SETUP or WAIT."
)

st.plotly_chart(
    create_price_chart(ticker, bars, zones),
    use_container_width=True,
)

st.plotly_chart(
    create_relative_strength_chart(
        ticker,
        benchmark,
        relative_frame,
    ),
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

st.subheader("AI research report")

reports_today = count_ai_reports_today(database_engine)
fresh_report = get_latest_ai_report(
    database_engine,
    ticker,
    fresh_only=True,
)

if st.session_state.latest_report is None:
    st.session_state.latest_report = (
        fresh_report
        or get_latest_ai_report(
            database_engine,
            ticker,
        )
    )

qualifies_automatically = (
    stock_score.overall_score >= AUTO_SCORE_THRESHOLD
    and relative_summary.score >= AUTO_RELATIVE_STRENGTH_THRESHOLD
    and market_regime.label != "Bearish"
    and price_plan.setup_status not in {"NO VALID SETUP", "INVALIDATED"}
)

automatic_generation_needed = (
    qualifies_automatically
    and fresh_report is None
    and reports_today < MAX_AI_REPORTS_PER_DAY
)

manual_col, usage_col = st.columns([2, 1])

with manual_col:
    generate_report_clicked = st.button(
        "Generate new AI research report",
        type="primary",
        disabled=reports_today >= MAX_AI_REPORTS_PER_DAY,
        key=f"generate_report_{ticker}_{benchmark}",
    )

with usage_col:
    st.metric(
        "AI reports generated today",
        f"{reports_today}/{MAX_AI_REPORTS_PER_DAY}",
    )

trigger_type = None

if generate_report_clicked:
    trigger_type = "manual"
elif automatic_generation_needed:
    trigger_type = "automatic_threshold"

if trigger_type:
    try:
        with st.spinner(
            "Collecting SEC evidence, company facts, news metadata, "
            "macro context and generating the report..."
        ):
            generated = generate_research_report(
                ticker=ticker,
                company_context=bundle["company_context"],
                technical_context=bundle["technical_context"],
            )

            report_id = save_ai_report(
                database_engine,
                ticker=ticker,
                trigger_type=trigger_type,
                technical_score=stock_score.overall_score,
                relative_strength_score=relative_summary.score,
                market_regime=market_regime.label,
                model=generated.model,
                report_markdown=generated.report_markdown,
                sources=generated.sources,
                search_queries=generated.search_queries,
                cache_hours=REPORT_CACHE_HOURS,
            )

            st.session_state.latest_report = get_latest_ai_report(
                database_engine,
                ticker,
            )

            st.session_state.report_message = (
                f"AI research report saved as record #{report_id}."
            )

    except Exception as exc:
        message = str(exc)

        if "429" in message or "RESOURCE_EXHAUSTED" in message:
            st.error(
                "A data source or Gemini quota is temporarily unavailable. "
                "Try again later."
            )
        else:
            st.error(f"Unable to generate AI report: {message}")

if st.session_state.report_message:
    st.success(st.session_state.report_message)

if st.session_state.latest_report:
    display_ai_report(st.session_state.latest_report)
else:
    st.info(
        "No AI research report exists for this ticker yet. "
        "Use the manual button or wait for a qualifying automatic trigger."
    )

st.subheader("Saved technical-analysis history")

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

    st.caption(
        "Latest technical analysis saved as record "
        f"#{st.session_state.last_saved_analysis_id}."
    )
