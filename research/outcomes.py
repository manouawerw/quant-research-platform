from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class OutcomeMetrics:
    return_1d: float | None
    return_5d: float | None
    return_20d: float | None
    maximum_gain_20d: float | None
    maximum_drawdown_20d: float | None
    target_hit: bool | None
    invalidation_hit: bool | None


def _return(entry: float, future: float) -> float:
    return (future / entry - 1) * 100


def calculate_outcome(
    future_bars: pd.DataFrame,
    *,
    entry_price: float,
    target_price: float,
    invalidation_price: float,
) -> OutcomeMetrics:
    bars = future_bars.sort_values("timestamp").reset_index(drop=True)

    def close_return(index: int) -> float | None:
        if len(bars) <= index:
            return None
        return _return(entry_price, float(bars.iloc[index]["close"]))

    window = bars.head(20)

    if window.empty:
        max_gain = None
        max_drawdown = None
        target_hit = None
        invalidation_hit = None
    else:
        max_gain = _return(entry_price, float(window["high"].max()))
        max_drawdown = _return(entry_price, float(window["low"].min()))
        target_hit = bool((window["high"] >= target_price).any())
        invalidation_hit = bool(
            (window["low"] <= invalidation_price).any()
        )

    return OutcomeMetrics(
        return_1d=close_return(0),
        return_5d=close_return(4),
        return_20d=close_return(19),
        maximum_gain_20d=max_gain,
        maximum_drawdown_20d=max_drawdown,
        target_hit=target_hit,
        invalidation_hit=invalidation_hit,
    )
