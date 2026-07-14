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
    get_latest_watchlist_snapshot,
    get_recent_analyses,
    initialize_database,
    save_ai_report,
    save_analysis,
    save_watchlist_snapshot,
)
from market_data import get_stock_data
from price_zones import build_price_plan
from relative_strength import (
    calculate_relative_strength,
    detect_market_regime,
)
from scoring import build_stock_score
from watchlist_scanner import scan_watchlist


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
        "watchlist_text": (
            "MU,AMD,NVDA,AAPL,MSFT,GOOGL,META,AMZN,TSM,AVGO"
        ),
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


def save_scanner_results(
    database_engine,
    results,
    benchmark: str,
) -> str:
    scan_group = datetime.now(timezone.utc).isoformat()

    for result in results:
        save_watchlist_snapshot(
            database_engine,
            result=result.to_dict(),
            benchmark=benchmark,
            scan_group=scan_group,
        )

    return scan_group


def render_watchlist_page(database_engine) -> None:
    st.header("Watchlist Scanner")
    st.caption(
        "Scan multiple tickers, rank attention priority and identify "
        "pullback, breakout, wait and invalidated setups."
    )

    benchmark = st.selectbox(
        "Scanner benchmark",
        options=["SPY", "QQQ"],
        key="scanner_benchmark",
    )

    watchlist_text = st.text_area(
        "Tickers separated by commas",
        value=st.session_state.watchlist_text,
        height=100,
    )

    st.session_state.watchlist_text = watchlist_text

    scan_clicked = st.button(
        "Run watchlist scan",
        type="primary",
        use_container_width=True,
    )

    if scan_clicked:
        tickers = [
            ticker.strip().upper()
            for ticker in watchlist_text.split(",")
            if ticker.strip()
        ]

        if len(tickers) > 50:
            st.error(
                "Keep the manual scanner to 50 tickers or fewer for now."
            )
            return

        with st.spinner(
            f"Scanning {len(tickers)} tickers against {benchmark}..."
        ):
            results, errors = scan_watchlist(
                tickers,
                benchmark=benchmark,
            )

            if results:
                save_scanner_results(
                    database_engine,
                    results,
                    benchmark,
                )

            if errors:
                with st.expander(
                    f"Scanner errors ({len(errors)})"
                ):
                    st.dataframe(
                        pd.DataFrame(errors),
                        use_container_width=True,
                        hide_index=True,
                    )

    snapshots = get_latest_watchlist_snapshot(
        database_engine,
        limit=100,
    )

    if not snapshots:
        st.info(
            "No saved watchlist scan exists yet. Run the scanner above."
        )
        return

    scan_time = snapshots[0]["scanned_at"]

    st.success(
        f"Showing the latest saved scan from {scan_time}."
    )

    table = pd.DataFrame(snapshots)

    table["Entry range"] = table.apply(
        lambda row: format_range(
            row["entry_low"],
            row["entry_high"],
        ),
        axis=1,
    )

    table["Breakout range"] = table.apply(
        lambda row: format_range(
            row["breakout_entry_low"],
            row["breakout_entry_high"],
        ),
        axis=1,
    )

    table["Target 1"] = table.apply(
        lambda row: format_range(
            row["target_1_low"],
            row["target_1_high"],
        ),
        axis=1,
    )

    table["RR 1"] = table["risk_reward_1"].apply(
        lambda value: (
            f"{value:.2f}:1"
            if pd.notna(value)
            else "N/A"
        )
    )

    display_columns = [
        "ticker",
        "attention_score",
        "technical_score",
        "relative_strength_score",
        "latest_price",
        "daily_change_pct",
        "setup_status",
        "Entry range",
        "Breakout range",
        "Target 1",
        "RR 1",
        "price_plan_confidence",
        "market_regime",
        "attention_reason",
    ]

    st.dataframe(
        table[display_columns],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Highest-priority names")

    for row in snapshots[:10]:
        with st.expander(
            f"{row['ticker']} — attention {row['attention_score']}/100 "
            f"— {row['setup_status']}"
        ):
            m1, m2, m3, m4 = st.columns(4)

            m1.metric(
                "Latest price",
                f"${row['latest_price']:,.2f}",
                f"{row['daily_change_pct']:+.2f}%",
            )

            m2.metric(
                "Technical",
                f"{row['technical_score']}/100",
            )

            m3.metric(
                "Relative strength",
                f"{row['relative_strength_score']}/100",
                row["relative_strength_trend"],
            )

            m4.metric(
                "Price-plan confidence",
                f"{row['price_plan_confidence']}/100",
            )

            st.write(row["attention_reason"])

            c1, c2 = st.columns(2)

            with c1:
                st.info(
                    "**Pullback range**\n\n"
                    + format_range(
                        row["entry_low"],
                        row["entry_high"],
                    )
                )

                st.warning(
                    "**Invalidation**\n\n"
                    f"${row['invalidation']:,.2f}"
                )

            with c2:
                st.info(
                    "**Breakout range**\n\n"
                    + format_range(
                        row["breakout_entry_low"],
                        row["breakout_entry_high"],
                    )
                )

                st.info(
                    "**Target 1**\n\n"
                    + format_range(
                        row["target_1_low"],
                        row["target_1_high"],
                    )
                )

            warnings = row.get("warnings", [])

            if warnings:
                st.markdown("**Warnings**")
                for warning in warnings:
                    st.write(f"• {warning}")


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

    fallback_zones = {
        "support_low": float(latest["low_20"]),
        "support_high": float(latest["sma_20"]),
        "resistance_low": float(latest["high_20"]),
        "resistance_high": float(latest["high_50"]),
        "pullback_entry_low": float(latest["low_20"]),
        "pullback_entry_high": float(latest["sma_20"]),
        "breakout_entry_low": float(latest["high_20"]),
        "breakout_entry_high": float(latest["high_50"]),
        "invalidation_level": (
            float(latest["low_20"]) - float(latest["atr_14"])
        ),
        "profit_zone_1_low": (
            latest_price + float(latest["atr_14"])
        ),
        "profit_zone_1_high": (
            latest_price + float(latest["atr_14"]) * 1.25
        ),
        "profit_zone_2_low": (
            latest_price + float(latest["atr_14"]) * 1.75
        ),
        "profit_zone_2_high": (
            latest_price + float(latest["atr_14"]) * 2.25
        ),
    }

    preliminary_summary = build_technical_summary(
        latest=latest,
        latest_price=latest_price,
        zones=fallback_zones,
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


def render_single_stock_page(database_engine) -> None:
    with st.sidebar:
        st.header("Single-stock research")

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

    if analyze_submitted:
        try:
            with st.spinner(
                f"Loading and analyzing {ticker_input}..."
            ):
                bundle = run_analysis(
                    ticker=ticker_input,
                    benchmark=benchmark_input,
                    database_engine=database_engine,
                )

            st.session_state.analysis_bundle = bundle
            st.session_state.analysis_ready = True
            st.session_state.active_ticker = ticker_input
            st.session_state.active_benchmark = benchmark_input
            st.session_state.last_saved_analysis_id = bundle[
                "analysis_id"
            ]
            st.session_state.latest_report = get_latest_ai_report(
                database_engine,
                ticker_input,
            )
            st.session_state.report_message = None

        except Exception as exc:
            st.error(
                f"Unable to analyze {ticker_input}: {exc}"
            )

    if not st.session_state.analysis_ready:
        st.info(
            "Enter a ticker in the sidebar and select **Analyze stock**."
        )
        return

    bundle = st.session_state.analysis_bundle

    ticker = bundle["ticker"]
    benchmark = bundle["benchmark"]
    latest_price = bundle["latest_price"]
    bars = bundle["bars"]
    daily_change_pct = bundle["daily_change_pct"]
    zones = bundle["zones"]
    price_plan = bundle["price_plan"]
    stock_score = bundle["stock_score"]
    relative_summary = bundle["relative_summary"]
    relative_frame = bundle["relative_frame"]
    market_regime = bundle["market_regime"]

    st.header(f"{ticker} research")

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
        "Setup status",
        price_plan.setup_status,
        f"confidence {price_plan.confidence}/100",
    )

    st.subheader("Model-generated price plan")

    left, right = st.columns(2)

    with left:
        st.info(
            "**Preferred pullback range**\n\n"
            + format_range(
                price_plan.entry_low,
                price_plan.entry_high,
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

    st.warning(
        "These are model-generated research ranges, not guaranteed "
        "buy or sell prices."
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

    chart_1, chart_2 = st.columns(2)

    with chart_1:
        st.plotly_chart(
            create_volume_chart(ticker, bars),
            use_container_width=True,
        )
        st.plotly_chart(
            create_rsi_chart(ticker, bars),
            use_container_width=True,
        )

    with chart_2:
        st.plotly_chart(
            create_macd_chart(ticker, bars),
            use_container_width=True,
        )

    st.subheader("AI research report")

    reports_today = count_ai_reports_today(database_engine)

    generate_clicked = st.button(
        "Generate new AI research report",
        type="primary",
        disabled=reports_today >= MAX_AI_REPORTS_PER_DAY,
        key=f"report_{ticker}_{benchmark}",
    )

    if generate_clicked:
        try:
            with st.spinner(
                "Collecting evidence and generating the report..."
            ):
                generated = generate_research_report(
                    ticker=ticker,
                    company_context=bundle["company_context"],
                    technical_context=bundle["technical_context"],
                )

                report_id = save_ai_report(
                    database_engine,
                    ticker=ticker,
                    trigger_type="manual",
                    technical_score=stock_score.overall_score,
                    relative_strength_score=relative_summary.score,
                    market_regime=market_regime.label,
                    model=generated.model,
                    report_markdown=generated.report_markdown,
                    sources=generated.sources,
                    search_queries=generated.search_queries,
                    cache_hours=REPORT_CACHE_HOURS,
                )

                st.session_state.latest_report = (
                    get_latest_ai_report(
                        database_engine,
                        ticker,
                    )
                )

                st.success(
                    f"AI report saved as record #{report_id}."
                )

        except Exception as exc:
            st.error(
                f"Unable to generate AI report: {exc}"
            )

    if st.session_state.latest_report:
        display_ai_report(
            st.session_state.latest_report
        )

    history = get_recent_analyses(
        database_engine,
        ticker=ticker,
        limit=20,
    )

    if history:
        st.subheader("Saved analysis history")
        st.dataframe(
            pd.DataFrame(history),
            use_container_width=True,
            hide_index=True,
        )


initialize_session_state()
database_engine = get_db_engine()

st.title("📈 Quant Research Platform")

page = st.sidebar.radio(
    "Page",
    options=[
        "Watchlist Scanner",
        "Single-Stock Research",
    ],
)

if page == "Watchlist Scanner":
    render_watchlist_page(database_engine)
else:
    render_single_stock_page(database_engine)
