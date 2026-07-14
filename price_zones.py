from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import pandas as pd


SetupType = Literal["pullback", "breakout", "none"]
SetupStatus = Literal[
    "PULLBACK ZONE",
    "BREAKOUT ZONE",
    "WAIT",
    "NO VALID SETUP",
    "INVALIDATED",
]


@dataclass(frozen=True)
class PricePlan:
    setup_type: SetupType
    setup_status: SetupStatus
    entry_low: float
    entry_high: float
    breakout_entry_low: float
    breakout_entry_high: float
    support_low: float
    support_high: float
    resistance_low: float
    resistance_high: float
    invalidation: float
    target_1_low: float
    target_1_high: float
    target_2_low: float
    target_2_high: float
    risk_reward_1: float | None
    risk_reward_2: float | None
    confidence: int
    reasons: list[str]
    warnings: list[str]

    def as_legacy_zones(self) -> dict[str, float]:
        """
        Preserve compatibility with charts.py, database.py and older app code.
        """
        return {
            "support_low": self.support_low,
            "support_high": self.support_high,
            "resistance_low": self.resistance_low,
            "resistance_high": self.resistance_high,
            "pullback_entry_low": self.entry_low,
            "pullback_entry_high": self.entry_high,
            "breakout_entry_low": self.breakout_entry_low,
            "breakout_entry_high": self.breakout_entry_high,
            "invalidation_level": self.invalidation,
            "profit_zone_1_low": self.target_1_low,
            "profit_zone_1_high": self.target_1_high,
            "profit_zone_2_low": self.target_2_low,
            "profit_zone_2_high": self.target_2_high,
        }

    def as_dict(self) -> dict:
        data = asdict(self)
        data["legacy_zones"] = self.as_legacy_zones()
        return data


def _nearest_below(values: list[float], price: float) -> float:
    valid = [value for value in values if pd.notna(value) and value <= price]
    return max(valid) if valid else price


def _nearest_above(values: list[float], price: float) -> float:
    valid = [value for value in values if pd.notna(value) and value >= price]
    return min(valid) if valid else price


def _safe_rr(entry: float, target: float, invalidation: float) -> float | None:
    risk = entry - invalidation
    reward = target - entry

    if risk <= 0 or reward <= 0:
        return None

    return reward / risk


def _swing_levels(bars: pd.DataFrame) -> tuple[float, float, float, float]:
    recent_20 = bars.tail(20)
    recent_60 = bars.tail(60)

    swing_low_20 = float(recent_20["low"].min())
    swing_high_20 = float(recent_20["high"].max())
    swing_low_60 = float(recent_60["low"].min())
    swing_high_60 = float(recent_60["high"].max())

    return swing_low_20, swing_high_20, swing_low_60, swing_high_60


def build_price_plan(
    *,
    bars: pd.DataFrame,
    latest_price: float,
    trend: str,
    technical_score: int,
    relative_strength_score: int,
    market_regime: str,
) -> PricePlan:
    """
    Build transparent model-generated price ranges.

    This engine is intentionally conservative:
    - It may return NO VALID SETUP.
    - Pullback and breakout setups are evaluated separately.
    - Confidence is a rules score, not a calibrated probability.
    """
    if len(bars) < 60:
        raise ValueError("At least 60 daily bars are required.")

    latest = bars.iloc[-1]

    atr = float(latest["atr_14"])
    sma_20 = float(latest["sma_20"])
    sma_50 = float(latest["sma_50"])
    bollinger_lower = float(latest["bollinger_lower"])
    bollinger_upper = float(latest["bollinger_upper"])
    rsi = float(latest["rsi_14"])
    relative_volume = float(latest["relative_volume"])
    volatility = float(latest["volatility_20"])
    macd = float(latest["macd"])
    macd_signal = float(latest["macd_signal"])

    swing_low_20, swing_high_20, swing_low_60, swing_high_60 = (
        _swing_levels(bars)
    )

    bullish_structure = (
        "bullish" in trend.lower()
        or (latest_price > sma_50 and sma_20 >= sma_50)
    )

    support_center = _nearest_below(
        [
            sma_20,
            sma_50,
            bollinger_lower,
            swing_low_20,
            swing_low_60,
            latest_price - atr,
        ],
        latest_price,
    )

    resistance_center = _nearest_above(
        [
            bollinger_upper,
            swing_high_20,
            swing_high_60,
            latest_price + atr,
        ],
        latest_price,
    )

    support_buffer = max(atr * 0.22, latest_price * 0.004)
    resistance_buffer = max(atr * 0.18, latest_price * 0.003)

    support_low = support_center - support_buffer
    support_high = support_center + support_buffer

    resistance_low = resistance_center - resistance_buffer
    resistance_high = resistance_center + resistance_buffer

    pullback_entry_low = support_low
    pullback_entry_high = min(
        support_high,
        latest_price + atr * 0.05,
    )

    breakout_confirmation = max(
        atr * 0.12,
        resistance_center * 0.0025,
    )

    breakout_entry_low = resistance_high
    breakout_entry_high = resistance_high + breakout_confirmation

    invalidation_candidates = [
        support_low - atr * 0.45,
        swing_low_20 - atr * 0.15,
        sma_50 - atr * 0.65,
    ]
    invalidation = min(invalidation_candidates)

    target_1_center = max(
        resistance_center,
        latest_price + atr * 1.10,
    )
    target_1_low = target_1_center - atr * 0.15
    target_1_high = target_1_center + atr * 0.20

    measured_move = max(
        resistance_center - support_center,
        atr * 1.75,
    )
    target_2_center = max(
        target_1_high + atr * 0.55,
        breakout_entry_low + measured_move,
    )
    target_2_low = target_2_center - atr * 0.20
    target_2_high = target_2_center + atr * 0.25

    rr_1 = _safe_rr(
        pullback_entry_high,
        target_1_low,
        invalidation,
    )
    rr_2 = _safe_rr(
        pullback_entry_high,
        target_2_low,
        invalidation,
    )

    reasons: list[str] = []
    warnings: list[str] = []

    if bullish_structure:
        reasons.append("The intermediate price structure remains constructive.")
    else:
        warnings.append("The intermediate trend is not clearly bullish.")

    if latest_price > sma_50:
        reasons.append("Price remains above the 50-day moving average.")
    else:
        warnings.append("Price is below the 50-day moving average.")

    if macd > macd_signal:
        reasons.append("MACD is above its signal line.")
    else:
        warnings.append("MACD momentum is below its signal line.")

    if 42 <= rsi <= 68:
        reasons.append("RSI is within a non-extreme range.")
    elif rsi > 72:
        warnings.append("RSI is elevated, increasing pullback risk.")
    elif rsi < 35:
        warnings.append("RSI is weak, so support may not hold.")

    if relative_volume >= 1:
        reasons.append("Volume participation is at or above average.")
    else:
        warnings.append("Volume participation is below average.")

    if relative_strength_score >= 70:
        reasons.append("Relative strength is supportive.")
    elif relative_strength_score < 45:
        warnings.append("Relative strength is weak.")

    if market_regime.lower() in {"bullish", "neutral-to-bullish"}:
        reasons.append("The broader market regime is supportive.")
    elif market_regime.lower() in {"bearish", "neutral-to-bearish"}:
        warnings.append("The broader market regime is unfavorable.")

    if volatility > 0.75:
        warnings.append("Annualized volatility is extremely high.")
    elif volatility > 0.50:
        warnings.append("Annualized volatility is elevated.")

    if rr_1 is None or rr_1 < 1.5:
        warnings.append("First-target reward/risk is below 1.5:1.")
    else:
        reasons.append(
            f"First-target reward/risk is approximately {rr_1:.2f}:1."
        )

    within_pullback = (
        pullback_entry_low <= latest_price <= pullback_entry_high
    )
    within_breakout = (
        breakout_entry_low <= latest_price <= breakout_entry_high
    )

    if latest_price < invalidation:
        setup_type: SetupType = "none"
        setup_status: SetupStatus = "INVALIDATED"
    elif within_pullback and bullish_structure and (rr_1 or 0) >= 1.5:
        setup_type = "pullback"
        setup_status = "PULLBACK ZONE"
    elif within_breakout and relative_volume >= 1.15:
        setup_type = "breakout"
        setup_status = "BREAKOUT ZONE"
    elif (
        not bullish_structure
        or technical_score < 45
        or (rr_1 is not None and rr_1 < 1.0)
    ):
        setup_type = "none"
        setup_status = "NO VALID SETUP"
    else:
        setup_type = "pullback" if latest_price < resistance_low else "breakout"
        setup_status = "WAIT"

    confidence = 45
    confidence += 10 if bullish_structure else -10
    confidence += 10 if technical_score >= 70 else -5 if technical_score < 45 else 0
    confidence += 10 if relative_strength_score >= 70 else -8 if relative_strength_score < 45 else 0
    confidence += 8 if market_regime.lower() in {"bullish", "neutral-to-bullish"} else -8
    confidence += 8 if macd > macd_signal else -5
    confidence += 6 if relative_volume >= 1 else -3
    confidence += 8 if rr_1 is not None and rr_1 >= 2 else -6 if rr_1 is not None and rr_1 < 1.5 else 0
    confidence -= 10 if volatility > 0.75 else 5 if volatility > 0.50 else 0
    confidence = int(max(20, min(90, confidence)))

    return PricePlan(
        setup_type=setup_type,
        setup_status=setup_status,
        entry_low=pullback_entry_low,
        entry_high=pullback_entry_high,
        breakout_entry_low=breakout_entry_low,
        breakout_entry_high=breakout_entry_high,
        support_low=support_low,
        support_high=support_high,
        resistance_low=resistance_low,
        resistance_high=resistance_high,
        invalidation=invalidation,
        target_1_low=target_1_low,
        target_1_high=target_1_high,
        target_2_low=target_2_low,
        target_2_high=target_2_high,
        risk_reward_1=rr_1,
        risk_reward_2=rr_2,
        confidence=confidence,
        reasons=reasons,
        warnings=warnings,
    )
