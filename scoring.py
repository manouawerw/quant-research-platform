from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    score: int
    weight: float
    explanation: str


@dataclass(frozen=True)
class StockScore:
    overall_score: int
    classification: str
    confidence: int
    components: list[ScoreComponent]
    bullish_factors: list[str]
    bearish_factors: list[str]


def clamp(value: float, minimum: int = 0, maximum: int = 100) -> int:
    """Restrict a score to the 0–100 range."""
    return int(round(max(minimum, min(maximum, value))))


def classify_score(score: int) -> str:
    """Convert a numerical score into a research classification."""
    if score >= 85:
        return "Very strong technical setup"

    if score >= 70:
        return "Positive technical setup"

    if score >= 55:
        return "Neutral-to-positive setup"

    if score >= 40:
        return "Weak technical setup"

    return "Very weak technical setup"


def calculate_trend_score(latest: pd.Series) -> ScoreComponent:
    close = float(latest["close"])
    sma_20 = float(latest["sma_20"])
    sma_50 = float(latest["sma_50"])
    macd = float(latest["macd"])
    macd_signal = float(latest["macd_signal"])

    score = 0
    reasons: list[str] = []

    if close > sma_20:
        score += 30
        reasons.append("price is above the 20-day moving average")
    else:
        score += 10
        reasons.append("price is below the 20-day moving average")

    if sma_20 > sma_50:
        score += 35
        reasons.append("the 20-day average is above the 50-day average")
    else:
        score += 10
        reasons.append("the 20-day average is below the 50-day average")

    if macd > macd_signal:
        score += 35
        reasons.append("MACD is above its signal line")
    else:
        score += 10
        reasons.append("MACD is below its signal line")

    return ScoreComponent(
        name="Trend",
        score=clamp(score),
        weight=0.30,
        explanation="; ".join(reasons).capitalize() + ".",
    )


def calculate_momentum_score(latest: pd.Series) -> ScoreComponent:
    rsi = float(latest["rsi_14"])
    macd_histogram = float(latest["macd_histogram"])

    if 50 <= rsi <= 65:
        score = 85
        explanation = "RSI shows healthy positive momentum without being extended."

    elif 40 <= rsi < 50:
        score = 65
        explanation = "RSI is neutral and momentum has not fully strengthened."

    elif 65 < rsi < 75:
        score = 70
        explanation = "Momentum is strong, although RSI is becoming elevated."

    elif rsi >= 75:
        score = 40
        explanation = "RSI is highly elevated and short-term pullback risk is higher."

    elif 30 <= rsi < 40:
        score = 45
        explanation = "RSI shows weak momentum."

    else:
        score = 35
        explanation = "RSI is deeply oversold and price behavior may be unstable."

    if macd_histogram > 0:
        score += 10
        explanation += " MACD momentum is positive."

    else:
        score -= 10
        explanation += " MACD momentum is negative."

    return ScoreComponent(
        name="Momentum",
        score=clamp(score),
        weight=0.20,
        explanation=explanation,
    )


def calculate_volume_score(latest: pd.Series) -> ScoreComponent:
    relative_volume = float(latest["relative_volume"])

    if relative_volume >= 2:
        score = 95
        explanation = "Volume is at least twice its 20-day average."

    elif relative_volume >= 1.5:
        score = 85
        explanation = "Volume is meaningfully above its 20-day average."

    elif relative_volume >= 1:
        score = 70
        explanation = "Volume is near or above its 20-day average."

    elif relative_volume >= 0.7:
        score = 55
        explanation = "Volume is moderately below its 20-day average."

    else:
        score = 40
        explanation = "Volume participation is low."

    return ScoreComponent(
        name="Volume",
        score=score,
        weight=0.15,
        explanation=explanation,
    )


def calculate_risk_score(latest: pd.Series) -> ScoreComponent:
    volatility = float(latest["volatility_20"])
    rsi = float(latest["rsi_14"])

    if volatility < 0.25:
        score = 90
        explanation = "Annualized volatility is relatively low."

    elif volatility < 0.40:
        score = 80
        explanation = "Annualized volatility is moderate."

    elif volatility < 0.60:
        score = 60
        explanation = "Annualized volatility is elevated."

    else:
        score = 40
        explanation = "Annualized volatility is very high."

    if rsi >= 75:
        score -= 15
        explanation += " Elevated RSI increases short-term reversal risk."

    return ScoreComponent(
        name="Risk quality",
        score=clamp(score),
        weight=0.15,
        explanation=explanation,
    )


def calculate_reward_risk_score(
    risk_reward: float | None,
) -> ScoreComponent:
    if risk_reward is None:
        return ScoreComponent(
            name="Reward/risk",
            score=35,
            weight=0.20,
            explanation="A valid reward-to-risk ratio could not be calculated.",
        )

    if risk_reward >= 3:
        score = 95
        explanation = "Estimated reward-to-risk is at least 3:1."

    elif risk_reward >= 2:
        score = 80
        explanation = "Estimated reward-to-risk is at least 2:1."

    elif risk_reward >= 1.5:
        score = 65
        explanation = "Estimated reward-to-risk is acceptable but not exceptional."

    elif risk_reward >= 1:
        score = 50
        explanation = "Estimated reward and risk are approximately balanced."

    else:
        score = 30
        explanation = "Estimated downside is larger than the first-target reward."

    return ScoreComponent(
        name="Reward/risk",
        score=score,
        weight=0.20,
        explanation=explanation,
    )


def build_stock_score(
    latest: pd.Series,
    risk_reward: float | None,
) -> StockScore:
    """Build a weighted technical-research score."""

    components = [
        calculate_trend_score(latest),
        calculate_momentum_score(latest),
        calculate_volume_score(latest),
        calculate_risk_score(latest),
        calculate_reward_risk_score(risk_reward),
    ]

    weighted_score = sum(
        component.score * component.weight
        for component in components
    )

    overall_score = clamp(weighted_score)

    bullish_factors = [
        component.explanation
        for component in components
        if component.score >= 70
    ]

    bearish_factors = [
        component.explanation
        for component in components
        if component.score < 50
    ]

    score_dispersion = max(
        component.score for component in components
    ) - min(
        component.score for component in components
    )

    confidence = clamp(
        90 - score_dispersion * 0.35,
        minimum=40,
        maximum=90,
    )

    return StockScore(
        overall_score=overall_score,
        classification=classify_score(overall_score),
        confidence=confidence,
        components=components,
        bullish_factors=bullish_factors,
        bearish_factors=bearish_factors,
    )