from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class RelativeStrengthSummary:
    benchmark: str
    stock_return_20d: float
    benchmark_return_20d: float
    excess_return_20d: float
    stock_return_60d: float
    benchmark_return_60d: float
    excess_return_60d: float
    ratio_trend: str
    score: int


@dataclass(frozen=True)
class MarketRegime:
    label: str
    score: int
    explanation: str
    benchmark_price: float
    sma_50: float
    sma_200: float
    return_20d: float


def _period_return(series: pd.Series, periods: int) -> float:
    if len(series) <= periods:
        raise ValueError(
            f"At least {periods + 1} observations are required."
        )

    start = float(series.iloc[-periods - 1])
    end = float(series.iloc[-1])

    if start == 0:
        raise ValueError("Cannot calculate return from a zero starting value.")

    return (end / start - 1) * 100


def build_relative_strength_frame(
    stock_bars: pd.DataFrame,
    benchmark_bars: pd.DataFrame,
) -> pd.DataFrame:
    stock = stock_bars[["timestamp", "close"]].copy()
    benchmark = benchmark_bars[["timestamp", "close"]].copy()

    stock["date"] = pd.to_datetime(stock["timestamp"]).dt.date
    benchmark["date"] = pd.to_datetime(benchmark["timestamp"]).dt.date

    stock = stock.rename(columns={"close": "stock_close"})
    benchmark = benchmark.rename(columns={"close": "benchmark_close"})

    merged = stock[["date", "stock_close"]].merge(
        benchmark[["date", "benchmark_close"]],
        on="date",
        how="inner",
    )

    if len(merged) < 61:
        raise ValueError(
            "Not enough overlapping stock and benchmark history."
        )

    merged["relative_ratio"] = (
        merged["stock_close"] / merged["benchmark_close"]
    )

    first_ratio = float(merged["relative_ratio"].iloc[0])

    merged["relative_ratio_index"] = (
        merged["relative_ratio"] / first_ratio * 100
    )

    merged["relative_ratio_sma_20"] = (
        merged["relative_ratio_index"].rolling(20).mean()
    )

    return merged


def calculate_relative_strength(
    stock_bars: pd.DataFrame,
    benchmark_bars: pd.DataFrame,
    benchmark: str = "SPY",
) -> tuple[RelativeStrengthSummary, pd.DataFrame]:
    frame = build_relative_strength_frame(
        stock_bars=stock_bars,
        benchmark_bars=benchmark_bars,
    )

    stock_return_20d = _period_return(frame["stock_close"], 20)
    benchmark_return_20d = _period_return(
        frame["benchmark_close"],
        20,
    )

    stock_return_60d = _period_return(frame["stock_close"], 60)
    benchmark_return_60d = _period_return(
        frame["benchmark_close"],
        60,
    )

    excess_20d = stock_return_20d - benchmark_return_20d
    excess_60d = stock_return_60d - benchmark_return_60d

    latest_ratio = float(frame["relative_ratio_index"].iloc[-1])
    latest_ratio_sma = float(frame["relative_ratio_sma_20"].iloc[-1])

    if latest_ratio > latest_ratio_sma and excess_20d > 0:
        ratio_trend = "Outperforming"
    elif latest_ratio < latest_ratio_sma and excess_20d < 0:
        ratio_trend = "Underperforming"
    else:
        ratio_trend = "Mixed"

    score = 50
    score += max(-20, min(20, excess_20d * 2))
    score += max(-20, min(20, excess_60d))
    score += 10 if latest_ratio > latest_ratio_sma else -10
    score = int(round(max(0, min(100, score))))

    summary = RelativeStrengthSummary(
        benchmark=benchmark,
        stock_return_20d=stock_return_20d,
        benchmark_return_20d=benchmark_return_20d,
        excess_return_20d=excess_20d,
        stock_return_60d=stock_return_60d,
        benchmark_return_60d=benchmark_return_60d,
        excess_return_60d=excess_60d,
        ratio_trend=ratio_trend,
        score=score,
    )

    return summary, frame


def detect_market_regime(
    benchmark_bars: pd.DataFrame,
) -> MarketRegime:
    df = benchmark_bars.copy().sort_values("timestamp").reset_index(drop=True)

    if len(df) < 200:
        raise ValueError(
            "At least 200 benchmark bars are required for regime detection."
        )

    df["sma_50"] = df["close"].rolling(50).mean()
    df["sma_200"] = df["close"].rolling(200).mean()

    latest = df.iloc[-1]

    price = float(latest["close"])
    sma_50 = float(latest["sma_50"])
    sma_200 = float(latest["sma_200"])
    return_20d = _period_return(df["close"], 20)

    if price > sma_50 > sma_200 and return_20d > 0:
        label = "Bullish"
        score = 90
        explanation = (
            "SPY is above both its 50-day and 200-day moving averages, "
            "with positive 20-day momentum."
        )
    elif price < sma_50 < sma_200 and return_20d < 0:
        label = "Bearish"
        score = 25
        explanation = (
            "SPY is below both its 50-day and 200-day moving averages, "
            "with negative 20-day momentum."
        )
    elif price > sma_200:
        label = "Neutral-to-bullish"
        score = 65
        explanation = (
            "SPY remains above its 200-day moving average, but shorter-term "
            "trend confirmation is mixed."
        )
    elif price < sma_200:
        label = "Neutral-to-bearish"
        score = 40
        explanation = (
            "SPY is below its 200-day moving average, while shorter-term "
            "signals remain mixed."
        )
    else:
        label = "Mixed"
        score = 50
        explanation = "SPY trend signals are mixed."

    return MarketRegime(
        label=label,
        score=score,
        explanation=explanation,
        benchmark_price=price,
        sma_50=sma_50,
        sma_200=sma_200,
        return_20d=return_20d,
    )
