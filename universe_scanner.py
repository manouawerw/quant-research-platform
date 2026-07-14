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
from bulk_market_data import (
    SnapshotRecord,
    get_bulk_daily_bars,
    select_liquid_symbols,
)
from cad_cdr import convert_price_plan_to_cdr
from price_zones import build_price_plan
from relative_strength import (
    calculate_relative_strength,
    detect_market_regime,
)
from scoring import build_stock_score
from universe import UniverseMember


@dataclass(frozen=True)
class UniverseResult:
    ticker: str
    company_name: str
    sector: str
    sub_industry: str
    exchange: str
    universe_name: str
    scanned_at: datetime
    latest_price: float
    daily_change_pct: float
    dollar_volume: float
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
    price_plan_confidence: int
    attention_score: int
    attention_reason: str
    cdr_available: bool
    cdr_symbol: str | None
    cdr_price_cad: float | None
    cdr_pullback_low_cad: float | None
    cdr_pullback_high_cad: float | None
    cdr_breakout_low_cad: float | None
    cdr_breakout_high_cad: float | None
    cdr_invalidation_cad: float | None
    cdr_target_1_low_cad: float | None
    cdr_target_1_high_cad: float | None
    cdr_warning: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _fallback_zones(
    latest: pd.Series,
    latest_price: float,
) -> dict[str, float]:
    atr = float(latest["atr_14"])

    return {
        "support_low": float(latest["low_20"]),
        "support_high": float(latest["sma_20"]),
        "resistance_low": float(latest["high_20"]),
        "resistance_high": float(latest["high_50"]),
        "pullback_entry_low": float(latest["low_20"]),
        "pullback_entry_high": float(latest["sma_20"]),
        "breakout_entry_low": float(latest["high_20"]),
        "breakout_entry_high": float(latest["high_50"]),
        "invalidation_level": float(latest["low_20"]) - atr,
        "profit_zone_1_low": latest_price + atr,
        "profit_zone_1_high": latest_price + atr * 1.25,
        "profit_zone_2_low": latest_price + atr * 1.75,
        "profit_zone_2_high": latest_price + atr * 2.25,
    }


def _attention_score(
    *,
    technical_score: int,
    relative_strength_score: int,
    plan_confidence: int,
    setup_status: str,
    market_regime: str,
) -> tuple[int, str]:
    score = round(
        technical_score * 0.40
        + relative_strength_score * 0.30
        + plan_confidence * 0.30
    )

    reasons: list[str] = []

    if setup_status in {
        "PULLBACK ZONE",
        "BREAKOUT ZONE",
    }:
        score += 8
        reasons.append(f"active {setup_status.lower()}")
    elif setup_status in {
        "NO VALID SETUP",
        "INVALIDATED",
    }:
        score -= 20
        reasons.append("no valid active setup")

    if market_regime.lower() in {
        "bullish",
        "neutral-to-bullish",
    }:
        score += 4
        reasons.append("supportive market regime")

    score = int(max(0, min(100, score)))

    return (
        score,
        (
            "; ".join(reasons).capitalize() + "."
            if reasons
            else "Combined technical and relative-strength ranking."
        ),
    )


def scan_universe(
    members: list[UniverseMember],
    *,
    benchmark: str = "SPY",
    target_size: int = 1500,
    minimum_price: float = 2.0,
    minimum_dollar_volume: float = 2_000_000,
    include_cdr_for_top: int = 25,
) -> tuple[
    list[UniverseResult],
    list[dict[str, str]],
]:
    member_lookup = {
        member.ticker: member
        for member in members
    }

    candidate_symbols = list(member_lookup)

    if len(candidate_symbols) > target_size + 100:
        (
            selected_symbols,
            snapshots,
            snapshot_errors,
        ) = select_liquid_symbols(
            candidate_symbols,
            target_size=target_size,
            minimum_price=minimum_price,
            minimum_dollar_volume=minimum_dollar_volume,
        )
    else:
        selected_symbols = candidate_symbols
        snapshots = {}
        snapshot_errors = []

    required_symbols = list(
        dict.fromkeys(selected_symbols + [benchmark])
    )
    history, history_errors = get_bulk_daily_bars(
        required_symbols
    )

    benchmark_bars = history.get(benchmark)

    if benchmark_bars is None:
        raise RuntimeError(
            f"Benchmark history was not returned for {benchmark}."
        )

    market_regime = detect_market_regime(
        benchmark_bars
    )

    preliminary: list[
        tuple[UniverseMember, dict[str, Any]]
    ] = []
    errors = snapshot_errors + history_errors

    for symbol in selected_symbols:
        member = member_lookup.get(symbol)
        bars = history.get(symbol)

        if member is None or bars is None:
            continue

        try:
            bars = calculate_indicators(bars)
            latest = bars.iloc[-1]
            validate_indicators(latest)

            snapshot = snapshots.get(symbol)

            latest_price = (
                snapshot.latest_price
                if snapshot is not None
                else float(latest["close"])
            )
            previous_close = float(
                bars.iloc[-2]["close"]
            )
            daily_change_pct = (
                snapshot.daily_change_pct
                if snapshot is not None
                and snapshot.daily_change_pct is not None
                else (
                    latest_price / previous_close - 1
                )
                * 100
            )
            dollar_volume = (
                snapshot.dollar_volume
                if snapshot is not None
                else latest_price
                * float(latest["volume"])
            )

            relative_summary, _ = (
                calculate_relative_strength(
                    stock_bars=bars,
                    benchmark_bars=benchmark_bars,
                    benchmark=benchmark,
                )
            )

            fallback = _fallback_zones(
                latest,
                latest_price,
            )
            preliminary_summary = (
                build_technical_summary(
                    latest=latest,
                    latest_price=latest_price,
                    zones=fallback,
                    risk_reward=None,
                )
            )
            preliminary_score = build_stock_score(
                latest=latest,
                risk_reward=None,
            )

            plan = build_price_plan(
                bars=bars,
                latest_price=latest_price,
                trend=preliminary_summary.trend,
                technical_score=(
                    preliminary_score.overall_score
                ),
                relative_strength_score=(
                    relative_summary.score
                ),
                market_regime=market_regime.label,
            )

            score = build_stock_score(
                latest=latest,
                risk_reward=plan.risk_reward_1,
            )

            attention, reason = _attention_score(
                technical_score=score.overall_score,
                relative_strength_score=(
                    relative_summary.score
                ),
                plan_confidence=plan.confidence,
                setup_status=plan.setup_status,
                market_regime=market_regime.label,
            )

            preliminary.append(
                (
                    member,
                    {
                        "latest_price": latest_price,
                        "daily_change_pct": (
                            daily_change_pct
                        ),
                        "dollar_volume": dollar_volume,
                        "relative": relative_summary,
                        "plan": plan,
                        "score": score,
                        "trend": (
                            preliminary_summary.trend
                        ),
                        "attention": attention,
                        "reason": reason,
                    },
                )
            )

        except Exception as exc:
            errors.append(
                {
                    "ticker": symbol,
                    "error": str(exc),
                }
            )

    preliminary.sort(
        key=lambda item: (
            item[1]["attention"],
            item[1]["score"].overall_score,
            item[1]["relative"].score,
            item[1]["dollar_volume"],
        ),
        reverse=True,
    )

    results: list[UniverseResult] = []

    for rank, (member, data) in enumerate(
        preliminary
    ):
        cdr = None

        if rank < include_cdr_for_top:
            cdr = convert_price_plan_to_cdr(
                underlying_ticker=member.ticker,
                underlying_price_usd=(
                    data["latest_price"]
                ),
                price_plan=data["plan"],
            )

        plan = data["plan"]
        relative = data["relative"]
        score = data["score"]

        results.append(
            UniverseResult(
                ticker=member.ticker,
                company_name=member.company_name,
                sector=member.sector,
                sub_industry=member.sub_industry,
                exchange=member.exchange,
                universe_name=member.universe_name,
                scanned_at=datetime.now(
                    timezone.utc
                ),
                latest_price=data["latest_price"],
                daily_change_pct=(
                    data["daily_change_pct"]
                ),
                dollar_volume=data["dollar_volume"],
                technical_score=score.overall_score,
                score_confidence=score.confidence,
                relative_strength_score=(
                    relative.score
                ),
                relative_strength_trend=(
                    relative.ratio_trend
                ),
                market_regime=market_regime.label,
                trend=data["trend"],
                setup_type=plan.setup_type,
                setup_status=plan.setup_status,
                entry_low=plan.entry_low,
                entry_high=plan.entry_high,
                breakout_entry_low=(
                    plan.breakout_entry_low
                ),
                breakout_entry_high=(
                    plan.breakout_entry_high
                ),
                invalidation=plan.invalidation,
                target_1_low=plan.target_1_low,
                target_1_high=plan.target_1_high,
                target_2_low=plan.target_2_low,
                target_2_high=plan.target_2_high,
                risk_reward_1=plan.risk_reward_1,
                price_plan_confidence=(
                    plan.confidence
                ),
                attention_score=data["attention"],
                attention_reason=data["reason"],
                cdr_available=cdr is not None,
                cdr_symbol=(
                    cdr.cdr_symbol
                    if cdr
                    else None
                ),
                cdr_price_cad=(
                    cdr.cdr_price_cad
                    if cdr
                    else None
                ),
                cdr_pullback_low_cad=(
                    cdr.pullback_low_cad
                    if cdr
                    else None
                ),
                cdr_pullback_high_cad=(
                    cdr.pullback_high_cad
                    if cdr
                    else None
                ),
                cdr_breakout_low_cad=(
                    cdr.breakout_low_cad
                    if cdr
                    else None
                ),
                cdr_breakout_high_cad=(
                    cdr.breakout_high_cad
                    if cdr
                    else None
                ),
                cdr_invalidation_cad=(
                    cdr.invalidation_cad
                    if cdr
                    else None
                ),
                cdr_target_1_low_cad=(
                    cdr.target_1_low_cad
                    if cdr
                    else None
                ),
                cdr_target_1_high_cad=(
                    cdr.target_1_high_cad
                    if cdr
                    else None
                ),
                cdr_warning=(
                    cdr.warning
                    if cdr
                    else None
                ),
            )
        )

    return results, errors
