from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def create_price_chart(
    ticker: str,
    bars: pd.DataFrame,
    zones: dict[str, float],
) -> go.Figure:
    fig = go.Figure()

    fig.add_trace(
        go.Candlestick(
            x=bars["timestamp"],
            open=bars["open"],
            high=bars["high"],
            low=bars["low"],
            close=bars["close"],
            name=ticker,
        )
    )

    for column, label in [
        ("sma_20", "20-day SMA"),
        ("sma_50", "50-day SMA"),
        ("bollinger_upper", "Upper Bollinger Band"),
        ("bollinger_lower", "Lower Bollinger Band"),
    ]:
        if column in bars.columns:
            fig.add_trace(
                go.Scatter(
                    x=bars["timestamp"],
                    y=bars[column],
                    mode="lines",
                    name=label,
                    line={"dash": "dot"} if "bollinger" in column else None,
                )
            )

    fig.add_hrect(
        y0=zones["support_low"],
        y1=zones["support_high"],
        opacity=0.12,
        line_width=0,
        annotation_text="Support / pullback zone",
        annotation_position="bottom right",
    )
    fig.add_hrect(
        y0=zones["resistance_low"],
        y1=zones["resistance_high"],
        opacity=0.12,
        line_width=0,
        annotation_text="Resistance zone",
        annotation_position="top right",
    )
    fig.add_hline(
        y=zones["invalidation_level"],
        line_dash="dash",
        annotation_text="Invalidation",
        annotation_position="bottom left",
    )

    fig.update_layout(
        title=f"{ticker} Daily Technical Chart",
        xaxis_title="Date",
        yaxis_title="Price (USD)",
        xaxis_rangeslider_visible=False,
        height=720,
        margin={"l": 20, "r": 20, "t": 70, "b": 20},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
        },
    )
    return fig


def create_volume_chart(ticker: str, bars: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=bars["timestamp"],
            y=bars["volume"],
            name="Daily IEX volume",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=bars["timestamp"],
            y=bars["average_volume_20"],
            mode="lines",
            name="20-day average",
        )
    )
    fig.update_layout(
        title=f"{ticker} Volume",
        xaxis_title="Date",
        yaxis_title="Volume",
        height=360,
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
    )
    return fig


def create_macd_chart(ticker: str, bars: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=bars["timestamp"],
            y=bars["macd"],
            mode="lines",
            name="MACD",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=bars["timestamp"],
            y=bars["macd_signal"],
            mode="lines",
            name="Signal",
        )
    )
    fig.add_trace(
        go.Bar(
            x=bars["timestamp"],
            y=bars["macd_histogram"],
            name="Histogram",
        )
    )
    fig.update_layout(
        title=f"{ticker} MACD",
        xaxis_title="Date",
        height=360,
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
    )
    return fig


def create_rsi_chart(ticker: str, bars: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=bars["timestamp"],
            y=bars["rsi_14"],
            mode="lines",
            name="RSI (14)",
        )
    )
    fig.add_hline(y=70, line_dash="dash", annotation_text="Overbought")
    fig.add_hline(y=30, line_dash="dash", annotation_text="Oversold")
    fig.update_layout(
        title=f"{ticker} RSI",
        xaxis_title="Date",
        yaxis_title="RSI",
        yaxis_range=[0, 100],
        height=360,
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
    )
    return fig
