from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from database import (
    get_database_engine,
    initialize_database,
)
from universe import fetch_universe
from universe_database import (
    get_latest_universe_scan,
    initialize_universe_tables,
    save_universe_scan,
)
from universe_scanner import scan_universe


st.set_page_config(
    page_title="Opportunity Scanner",
    page_icon="🔎",
    layout="wide",
)


@st.cache_resource
def database_engine():
    engine = get_database_engine()
    initialize_database(engine)
    initialize_universe_tables(engine)
    return engine


def money_range(low, high, currency="$"):
    if pd.isna(low) or pd.isna(high):
        return "—"

    return (
        f"{currency}{low:,.2f} – "
        f"{currency}{high:,.2f}"
    )


engine = database_engine()

st.title("🔎 U.S. Opportunity Scanner")
st.caption(
    "Scan the current S&P 500 or prefilter the broader U.S. market "
    "to the 1,500 most liquid common equities. Python ranks every "
    "name; Gemini is not called for the full universe."
)

row_1 = st.columns(4)

with row_1[0]:
    universe_name = st.selectbox(
        "Universe",
        ["US Liquid 1500", "S&P 500"],
    )

with row_1[1]:
    benchmark = st.selectbox(
        "Benchmark",
        ["SPY", "QQQ"],
    )

with row_1[2]:
    target_size = st.number_input(
        "Target universe size",
        min_value=100,
        max_value=2000,
        value=1500,
        step=100,
        disabled=(
            universe_name == "S&P 500"
        ),
    )

with row_1[3]:
    cdr_top_n = st.number_input(
        "Check CDRs for top N",
        min_value=0,
        max_value=50,
        value=25,
        step=5,
    )

row_2 = st.columns(3)

with row_2[0]:
    minimum_price = st.number_input(
        "Minimum share price (USD)",
        min_value=0.0,
        value=2.0,
        step=1.0,
    )

with row_2[1]:
    minimum_dollar_volume = st.number_input(
        "Minimum daily dollar volume",
        min_value=0,
        value=2_000_000,
        step=1_000_000,
    )

with row_2[2]:
    run_scan = st.button(
        "Run universe scan",
        type="primary",
        use_container_width=True,
    )

if run_scan:
    with st.spinner(
        "Fetching current symbols, ranking liquidity, downloading "
        "daily history in batches and scoring the universe..."
    ):
        members = fetch_universe(
            universe_name,
            force_refresh=True,
        )

        effective_size = (
            len(members)
            if universe_name == "S&P 500"
            else int(target_size)
        )

        results, errors = scan_universe(
            members,
            benchmark=benchmark,
            target_size=effective_size,
            minimum_price=float(
                minimum_price
            ),
            minimum_dollar_volume=float(
                minimum_dollar_volume
            ),
            include_cdr_for_top=int(
                cdr_top_n
            ),
        )

        if results:
            scan_group = (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )

            save_universe_scan(
                engine,
                scan_group=scan_group,
                results=[
                    result.to_dict()
                    for result in results
                ],
            )

            st.success(
                f"Saved {len(results)} ranked securities."
            )

        if errors:
            with st.expander(
                f"Scan warnings ({len(errors)})"
            ):
                st.dataframe(
                    pd.DataFrame(errors),
                    use_container_width=True,
                    hide_index=True,
                )

rows = get_latest_universe_scan(
    engine,
    limit=2000,
)

if not rows:
    st.info(
        "No scan exists yet. Run one above or start the Railway worker."
    )
    st.stop()

frame = pd.DataFrame(rows)

st.success(
    f"Latest saved scan: {frame.iloc[0]['scanned_at']} "
    f"— {len(frame)} securities ranked."
)

filters = st.columns(5)

with filters[0]:
    minimum_attention = st.slider(
        "Minimum attention",
        0,
        100,
        60,
    )

with filters[1]:
    setup = st.selectbox(
        "Setup",
        [
            "All",
            "PULLBACK ZONE",
            "BREAKOUT ZONE",
            "WAIT",
            "NO VALID SETUP",
            "INVALIDATED",
        ],
    )

with filters[2]:
    minimum_rr = st.number_input(
        "Minimum reward/risk",
        min_value=0.0,
        value=1.5,
        step=0.25,
    )

with filters[3]:
    cad_only = st.checkbox(
        "Only mapped CDRs",
        value=False,
    )

with filters[4]:
    show_top = st.selectbox(
        "Show top",
        [10, 25, 50, 100, 250, 500],
        index=2,
    )

filtered = frame[
    frame["attention_score"]
    >= minimum_attention
].copy()

if setup != "All":
    filtered = filtered[
        filtered["setup_status"] == setup
    ]

filtered = filtered[
    filtered["risk_reward_1"].fillna(0)
    >= minimum_rr
]

if cad_only:
    filtered = filtered[
        filtered["cdr_available"] == True  # noqa: E712
    ]

filtered = filtered.head(show_top)

filtered["US pullback"] = filtered.apply(
    lambda row: money_range(
        row["entry_low"],
        row["entry_high"],
        "US$",
    ),
    axis=1,
)

filtered["CAD CDR pullback"] = (
    filtered.apply(
        lambda row: money_range(
            row["cdr_pullback_low_cad"],
            row["cdr_pullback_high_cad"],
            "C$",
        ),
        axis=1,
    )
)

display_columns = [
    "ticker",
    "company_name",
    "attention_score",
    "technical_score",
    "relative_strength_score",
    "setup_status",
    "latest_price",
    "daily_change_pct",
    "risk_reward_1",
    "US pullback",
    "cdr_symbol",
    "cdr_price_cad",
    "CAD CDR pullback",
]

st.dataframe(
    filtered[display_columns],
    use_container_width=True,
    hide_index=True,
)

st.subheader("Top-ranked details")

for _, row in filtered.head(20).iterrows():
    with st.expander(
        f"{row['ticker']} — {row['company_name']} — "
        f"{row['attention_score']}/100 — "
        f"{row['setup_status']}"
    ):
        metrics = st.columns(4)

        metrics[0].metric(
            "Underlying price",
            f"US${row['latest_price']:,.2f}",
            f"{row['daily_change_pct']:+.2f}%",
        )
        metrics[1].metric(
            "Technical",
            f"{row['technical_score']}/100",
        )
        metrics[2].metric(
            "Relative strength",
            f"{row['relative_strength_score']}/100",
            row["relative_strength_trend"],
        )
        metrics[3].metric(
            "Plan confidence",
            f"{row['price_plan_confidence']}/100",
            "rules score",
        )

        st.write(
            row["attention_reason"]
        )

        left, right = st.columns(2)

        with left:
            st.info(
                "**Underlying pullback**\n\n"
                + money_range(
                    row["entry_low"],
                    row["entry_high"],
                    "US$",
                )
            )
            st.warning(
                "**Underlying invalidation**\n\n"
                f"US${row['invalidation']:,.2f}"
            )

        with right:
            st.info(
                "**Underlying breakout**\n\n"
                + money_range(
                    row[
                        "breakout_entry_low"
                    ],
                    row[
                        "breakout_entry_high"
                    ],
                    "US$",
                )
            )
            st.info(
                "**Underlying target 1**\n\n"
                + money_range(
                    row["target_1_low"],
                    row["target_1_high"],
                    "US$",
                )
            )

        if row["cdr_available"]:
            st.markdown(
                "#### Canadian CAD-hedged CDR"
            )

            cdr_metrics = st.columns(3)

            cdr_metrics[0].metric(
                "CDR symbol",
                row["cdr_symbol"],
            )
            cdr_metrics[1].metric(
                "Latest CDR quote",
                f"C${row['cdr_price_cad']:,.2f}",
            )
            cdr_metrics[2].metric(
                "Approx. invalidation",
                f"C${row['cdr_invalidation_cad']:,.2f}",
            )

            st.info(
                "**Approximate CDR pullback**\n\n"
                + money_range(
                    row[
                        "cdr_pullback_low_cad"
                    ],
                    row[
                        "cdr_pullback_high_cad"
                    ],
                    "C$",
                )
            )
            st.warning(
                row["cdr_warning"]
            )

st.caption(
    "The broad universe comes from Nasdaq Trader's current all-issues "
    "directory, then is filtered to common-equity candidates and ranked "
    "by current dollar volume before historical analysis. CDR ranges use "
    "an observed CDR/underlying ratio and remain approximate."
)
