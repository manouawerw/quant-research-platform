from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from analysis import (
    build_technical_summary,
    calculate_indicators,
    validate_indicators,
)
from market_data import get_stock_data
from price_zones import build_price_plan
from relative_strength import (
    calculate_relative_strength,
    detect_market_regime,
)
from scoring import build_stock_score


@dataclass(frozen=True)
class WatchlistResult:
    ticker: str
    scanned_at: datetime
    latest_price: float
    daily_change_pct: float
    technical_score: int
    score_confidence: int
    relative_strength_score: int
    relative_strength_trend: str
    market_regime: str
    trend: str
    setup_type: str
    setup_status: str
    entry_low: float
    entry_high: float
    breakout_entry_low: float
    breakout_entry_high: float
    invalidation: float
    target_1_low: float
    target_1_high: float
    target_2_low: float
    target_2_high: float
    risk_reward_1: float | None
    risk_reward_2: float | None
    price_plan_confidence: int
    relative_volume: float
    rsi_14: float
    volatility_20_pct: float
    attention_score: int
    attention_reason: str
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_attention_score(
    *,
    technical_score: int,
    relative_strength_score: int,
    price_plan_confidence: int,
    setup_status: str,
    market_regime: str,
    relative_volume: float,
) -> tuple[int, str]:
    score = round(
        technical_score * 0.35
        + relative_strength_score * 0.25
        + price_plan_confidence * 0.25
    )

    reasons: list[str] = []

    if setup_status == "PULLBACK ZONE":
        score += 10
        reasons.append("price is inside the pullback range")
    elif setup_status == "BREAKOUT ZONE":
        score += 10
        reasons.append("price is inside the breakout range")
    elif setup_status in {"NO VALID SETUP", "INVALIDATED"}:
        score -= 20
        reasons.append("the price-plan engine found no valid setup")

    if market_regime.lower() in {"bullish", "neutral-to-bullish"}:
        score += 5
        reasons.append("the market regime is supportive")
    elif market_regime.lower() in {"bearish", "neutral-to-bearish"}:
        score -= 8
        reasons.append("the market regime is unfavorable")

    if relative_volume >= 1.5:
        score += 5
        reasons.append("relative volume is elevated")

    score = int(max(0, min(100, score)))

    if not reasons:
        reasons.append("the score reflects the combined technical context")

    return score, "; ".join(reasons).capitalize() + "."


def scan_ticker(
    *,
    ticker: str,
    benchmark: str = "SPY",
    benchmark_bars: pd.DataFrame | None = None,
) -> WatchlistResult:
    symbol = ticker.strip().upper()

    latest_price, bars = get_stock_data(symbol)
    bars = calculate_indicators(bars)
    latest = bars.iloc[-1]
    validate_indicators(latest)

    if benchmark_bars is None:
        _, benchmark_bars = get_stock_data(benchmark)

    previous_close = float(bars.iloc[-2]["close"])
    daily_change_pct = (
        (latest_price - previous_close) / previous_close * 100
    )

    relative_summary, _ = calculate_relative_strength(
        stock_bars=bars,
        benchmark_bars=benchmark_bars,
        benchmark=benchmark,
    )
    market_regime = detect_market_regime(benchmark_bars)

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

    price_plan = build_price_plan(
        bars=bars,
        latest_price=latest_price,
        trend=preliminary_summary.trend,
        technical_score=preliminary_score.overall_score,
        relative_strength_score=relative_summary.score,
        market_regime=market_regime.label,
    )

    stock_score = build_stock_score(
        latest=latest,
        risk_reward=price_plan.risk_reward_1,
    )

    attention_score, attention_reason = calculate_attention_score(
        technical_score=stock_score.overall_score,
        relative_strength_score=relative_summary.score,
        price_plan_confidence=price_plan.confidence,
        setup_status=price_plan.setup_status,
        market_regime=market_regime.label,
        relative_volume=float(latest["relative_volume"]),
    )

    return WatchlistResult(
        ticker=symbol,
        scanned_at=datetime.now(timezone.utc),
        latest_price=latest_price,
        daily_change_pct=daily_change_pct,
        technical_score=stock_score.overall_score,
        score_confidence=stock_score.confidence,
        relative_strength_score=relative_summary.score,
        relative_strength_trend=relative_summary.ratio_trend,
        market_regime=market_regime.label,
        trend=preliminary_summary.trend,
        setup_type=price_plan.setup_type,
        setup_status=price_plan.setup_status,
        entry_low=price_plan.entry_low,
        entry_high=price_plan.entry_high,
        breakout_entry_low=price_plan.breakout_entry_low,
        breakout_entry_high=price_plan.breakout_entry_high,
        invalidation=price_plan.invalidation,
        target_1_low=price_plan.target_1_low,
        target_1_high=price_plan.target_1_high,
        target_2_low=price_plan.target_2_low,
        target_2_high=price_plan.target_2_high,
        risk_reward_1=price_plan.risk_reward_1,
        risk_reward_2=price_plan.risk_reward_2,
        price_plan_confidence=price_plan.confidence,
        relative_volume=float(latest["relative_volume"]),
        rsi_14=float(latest["rsi_14"]),
        volatility_20_pct=float(latest["volatility_20"]) * 100,
        attention_score=attention_score,
        attention_reason=attention_reason,
        warnings=price_plan.warnings,
    )


def scan_watchlist(
    tickers: list[str],
    *,
    benchmark: str = "SPY",
) -> tuple[list[WatchlistResult], list[dict[str, str]]]:
    cleaned = list(
        dict.fromkeys(
            ticker.strip().upper()
            for ticker in tickers
            if ticker.strip()
        )
    )

    if not cleaned:
        return [], []

    _, benchmark_bars = get_stock_data(benchmark)

    results: list[WatchlistResult] = []
    errors: list[dict[str, str]] = []

    for ticker in cleaned:
        try:
            result = scan_ticker(
                ticker=ticker,
                benchmark=benchmark,
                benchmark_bars=benchmark_bars,
            )
            results.append(result)
        except Exception as exc:
            errors.append(
                {
                    "ticker": ticker,
                    "error": str(exc),
                }
            )

    results.sort(
        key=lambda item: (
            item.attention_score,
            item.technical_score,
            item.relative_strength_score,
        ),
        reverse=True,
    )

    return results, errors
