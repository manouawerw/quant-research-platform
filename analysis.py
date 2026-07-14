from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TechnicalSummary:
    trend: str
    rsi_status: str
    setup_status: str
    technical_score: int
    risk_score: int
    momentum_score: int
    trend_score: int
    volume_score: int
    reward_risk_score: int
    confidence: int
    reasoning: list[str]


def calculate_indicators(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy().sort_values("timestamp").reset_index(drop=True)

    df["sma_20"] = df["close"].rolling(20).mean()
    df["sma_50"] = df["close"].rolling(50).mean()
    df["ema_12"] = df["close"].ewm(span=12, adjust=False).mean()
    df["ema_26"] = df["close"].ewm(span=26, adjust=False).mean()

    df["macd"] = df["ema_12"] - df["ema_26"]
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_histogram"] = df["macd"] - df["macd_signal"]

    previous_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr_14"] = true_range.rolling(14).mean()

    delta = df["close"].diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    avg_gain = gains.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = losses.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    df["rsi_14"] = 100 - (100 / (1 + rs))
    df.loc[(avg_loss == 0) & (avg_gain > 0), "rsi_14"] = 100

    df["high_20"] = df["high"].rolling(20).max()
    df["low_20"] = df["low"].rolling(20).min()
    df["high_50"] = df["high"].rolling(50).max()
    df["low_50"] = df["low"].rolling(50).min()

    df["daily_return"] = df["close"].pct_change()
    df["volatility_20"] = df["daily_return"].rolling(20).std() * (252 ** 0.5)

    df["average_volume_20"] = df["volume"].rolling(20).mean()
    df["relative_volume"] = df["volume"] / df["average_volume_20"]

    std_20 = df["close"].rolling(20).std()
    df["bollinger_upper"] = df["sma_20"] + 2 * std_20
    df["bollinger_lower"] = df["sma_20"] - 2 * std_20

    return df


def validate_indicators(latest: pd.Series) -> None:
    required = [
        "sma_20",
        "sma_50",
        "atr_14",
        "rsi_14",
        "high_20",
        "low_20",
        "volatility_20",
        "relative_volume",
        "macd",
        "macd_signal",
    ]
    missing = [name for name in required if pd.isna(latest[name])]
    if missing:
        raise ValueError(
            "Not enough history to calculate: " + ", ".join(missing)
        )


def classify_trend(latest: pd.Series) -> str:
    close = float(latest["close"])
    sma_20 = float(latest["sma_20"])
    sma_50 = float(latest["sma_50"])
    macd = float(latest["macd"])
    signal = float(latest["macd_signal"])

    if close > sma_20 > sma_50 and macd > signal:
        return "Bullish"
    if close < sma_20 < sma_50 and macd < signal:
        return "Bearish"
    if close > sma_20 > sma_50:
        return "Moderately bullish"
    if close < sma_20 < sma_50:
        return "Moderately bearish"
    return "Mixed"


def classify_rsi(rsi: float) -> str:
    if rsi >= 70:
        return "Overbought"
    if rsi <= 30:
        return "Oversold"
    if rsi >= 55:
        return "Positive momentum"
    if rsi <= 45:
        return "Negative momentum"
    return "Neutral"


def calculate_zones(
    latest: pd.Series,
    latest_price: float,
) -> dict[str, float]:
    atr = float(latest["atr_14"])
    sma_20 = float(latest["sma_20"])
    sma_50 = float(latest["sma_50"])
    low_20 = float(latest["low_20"])
    high_20 = float(latest["high_20"])
    high_50 = float(latest["high_50"])

    supports = [
        value
        for value in [latest_price - atr, sma_20, sma_50, low_20]
        if value <= latest_price
    ]
    resistances = [
        value
        for value in [latest_price + atr, high_20, high_50]
        if value >= latest_price
    ]

    support_center = max(supports) if supports else latest_price - atr
    resistance_center = min(resistances) if resistances else latest_price + atr
    tolerance = atr * 0.20

    support_low = support_center - tolerance
    support_high = support_center + tolerance
    resistance_low = resistance_center - tolerance
    resistance_high = resistance_center + tolerance

    return {
        "support_low": support_low,
        "support_high": support_high,
        "resistance_low": resistance_low,
        "resistance_high": resistance_high,
        "pullback_entry_low": support_low,
        "pullback_entry_high": support_high,
        "breakout_entry_low": resistance_high,
        "breakout_entry_high": resistance_high + atr * 0.20,
        "invalidation_level": support_low - atr * 0.50,
        "profit_zone_1_low": latest_price + atr,
        "profit_zone_1_high": latest_price + atr * 1.25,
        "profit_zone_2_low": latest_price + atr * 1.75,
        "profit_zone_2_high": latest_price + atr * 2.25,
    }


def calculate_risk_reward(
    entry_price: float,
    target_price: float,
    invalidation_price: float,
) -> float | None:
    reward = target_price - entry_price
    risk = entry_price - invalidation_price
    if risk <= 0:
        return None
    return reward / risk


def determine_status(
    latest_price: float,
    zones: dict[str, float],
    trend: str,
) -> str:
    if zones["pullback_entry_low"] <= latest_price <= zones["pullback_entry_high"]:
        return "PULLBACK ZONE REACHED" if "bullish" in trend.lower() else "AT SUPPORT"
    if zones["breakout_entry_low"] <= latest_price <= zones["breakout_entry_high"]:
        return "BREAKOUT ZONE"
    if latest_price < zones["invalidation_level"]:
        return "TECHNICAL SETUP INVALIDATED"
    return "WAIT"


def build_technical_summary(
    latest: pd.Series,
    latest_price: float,
    zones: dict[str, float],
    risk_reward: float | None,
) -> TechnicalSummary:
    trend = classify_trend(latest)
    rsi = float(latest["rsi_14"])
    rsi_status = classify_rsi(rsi)
    setup_status = determine_status(latest_price, zones, trend)

    close = float(latest["close"])
    sma_20 = float(latest["sma_20"])
    sma_50 = float(latest["sma_50"])
    macd = float(latest["macd"])
    signal = float(latest["macd_signal"])
    rel_volume = float(latest["relative_volume"])
    volatility = float(latest["volatility_20"])

    trend_score = 0
    trend_score += 35 if close > sma_20 else 10
    trend_score += 35 if sma_20 > sma_50 else 10
    trend_score += 30 if macd > signal else 10
    trend_score = min(trend_score, 100)

    momentum_score = 80 if 50 <= rsi <= 65 else 65 if 40 <= rsi < 70 else 40
    if macd > signal:
        momentum_score = min(momentum_score + 10, 100)

    volume_score = 85 if rel_volume >= 1.5 else 70 if rel_volume >= 1.0 else 50

    risk_score = 80 if volatility < 0.35 else 65 if volatility < 0.55 else 45
    if rsi >= 75:
        risk_score -= 15
    risk_score = max(0, min(risk_score, 100))

    if risk_reward is None:
        reward_risk_score = 40
    elif risk_reward >= 3:
        reward_risk_score = 95
    elif risk_reward >= 2:
        reward_risk_score = 80
    elif risk_reward >= 1.5:
        reward_risk_score = 65
    else:
        reward_risk_score = 40

    technical_score = round(
        trend_score * 0.30
        + momentum_score * 0.20
        + volume_score * 0.15
        + risk_score * 0.15
        + reward_risk_score * 0.20
    )

    confidence = min(95, max(40, round(technical_score * 0.9)))

    reasoning: list[str] = []
    reasoning.append(
        "Price is above the 20-day moving average."
        if close > sma_20
        else "Price is below the 20-day moving average."
    )
    reasoning.append(
        "The 20-day moving average is above the 50-day moving average."
        if sma_20 > sma_50
        else "The 20-day moving average is not above the 50-day moving average."
    )
    reasoning.append(
        "MACD is above its signal line."
        if macd > signal
        else "MACD is below its signal line."
    )
    reasoning.append(f"RSI is {rsi:.1f}, classified as {rsi_status.lower()}.")
    reasoning.append(f"Relative volume is {rel_volume:.2f}× its 20-day average.")
    if risk_reward is not None:
        reasoning.append(f"Estimated first-target reward/risk is {risk_reward:.2f}:1.")

    return TechnicalSummary(
        trend=trend,
        rsi_status=rsi_status,
        setup_status=setup_status,
        technical_score=technical_score,
        risk_score=risk_score,
        momentum_score=momentum_score,
        trend_score=trend_score,
        volume_score=volume_score,
        reward_risk_score=reward_risk_score,
        confidence=confidence,
        reasoning=reasoning,
    )
