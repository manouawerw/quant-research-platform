from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .evidence_models import EvidenceClaim


def _tag_value(claim: EvidenceClaim, tag: str) -> float | None:
    if tag in claim.tags and isinstance(claim.value, (int, float)):
        return float(claim.value)
    return None


def calculate_period_growth(
    claims: Iterable[EvidenceClaim],
    fact_tag: str,
) -> dict[str, float | str] | None:
    matching = [
        claim
        for claim in claims
        if fact_tag in claim.tags
        and isinstance(claim.value, (int, float))
        and claim.period
    ]

    matching.sort(key=lambda claim: str(claim.period), reverse=True)

    if len(matching) < 2:
        return None

    latest, previous = matching[0], matching[1]
    previous_value = float(previous.value)

    if previous_value == 0:
        return None

    growth = (float(latest.value) / previous_value - 1) * 100

    return {
        "fact": fact_tag,
        "latest_period": str(latest.period),
        "previous_period": str(previous.period),
        "latest_value": float(latest.value),
        "previous_value": previous_value,
        "growth_pct": growth,
    }


def summarize_fundamentals(
    claims: list[EvidenceClaim],
) -> dict[str, object]:
    return {
        "revenue_growth": calculate_period_growth(
            claims,
            "RevenueFromContractWithCustomerExcludingAssessedTax",
        )
        or calculate_period_growth(claims, "Revenues"),
        "gross_profit_growth": calculate_period_growth(
            claims,
            "GrossProfit",
        ),
        "operating_income_growth": calculate_period_growth(
            claims,
            "OperatingIncomeLoss",
        ),
        "net_income_growth": calculate_period_growth(
            claims,
            "NetIncomeLoss",
        ),
        "operating_cash_flow_growth": calculate_period_growth(
            claims,
            "NetCashProvidedByUsedInOperatingActivities",
        ),
        "inventory_growth": calculate_period_growth(
            claims,
            "InventoryNet",
        ),
    }
