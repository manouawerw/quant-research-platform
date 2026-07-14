from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf


MAPPING_PATH = Path("data/cdr_underlyings.csv")


@dataclass(frozen=True)
class CDRMapping:
    underlying_ticker: str
    cdr_symbol: str
    exchange_suffix: str
    company_name: str
    hedged: bool
    official_directory_url: str


@dataclass(frozen=True)
class CADPricePlan:
    underlying_ticker: str
    cdr_symbol: str
    cdr_price_cad: float
    observed_price_ratio: float
    pullback_low_cad: float
    pullback_high_cad: float
    breakout_low_cad: float
    breakout_high_cad: float
    invalidation_cad: float
    target_1_low_cad: float
    target_1_high_cad: float
    target_2_low_cad: float
    target_2_high_cad: float
    data_source: str
    warning: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_cdr_mappings() -> dict[str, CDRMapping]:
    if not MAPPING_PATH.exists():
        return {}

    mappings: dict[str, CDRMapping] = {}

    with MAPPING_PATH.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        for row in csv.DictReader(handle):
            mapping = CDRMapping(
                underlying_ticker=row["underlying_ticker"].upper(),
                cdr_symbol=row["cdr_symbol"].upper(),
                exchange_suffix=row.get("exchange_suffix", ".TO"),
                company_name=row.get("company_name", ""),
                hedged=row.get("hedged", "true").lower() == "true",
                official_directory_url=row.get(
                    "official_directory_url",
                    "https://cdr.cibc.com/",
                ),
            )
            mappings[mapping.underlying_ticker] = mapping

    return mappings


def get_mapping(underlying_ticker: str) -> CDRMapping | None:
    normalized = underlying_ticker.upper().replace("-", ".")
    return load_cdr_mappings().get(normalized)


def _quote_candidates(mapping: CDRMapping) -> list[str]:
    base = mapping.cdr_symbol
    preferred = mapping.exchange_suffix

    candidates = [
        f"{base}{preferred}",
        f"{base}.TO",
        f"{base}.NE",
    ]

    return list(dict.fromkeys(candidates))


def get_latest_cdr_price(
    mapping: CDRMapping,
) -> tuple[str, float] | None:
    """
    Uses Yahoo Finance only as a free quote fallback.

    Verify the symbol and executable quote with the user's Canadian broker
    before relying on it.
    """
    for yahoo_symbol in _quote_candidates(mapping):
        try:
            history = yf.Ticker(yahoo_symbol).history(period="5d")
            if history.empty:
                continue

            close = history["Close"].dropna()
            if close.empty:
                continue

            return yahoo_symbol, float(close.iloc[-1])
        except Exception:
            continue

    return None


def convert_price_plan_to_cdr(
    *,
    underlying_ticker: str,
    underlying_price_usd: float,
    price_plan: Any,
) -> CADPricePlan | None:
    """
    Convert underlying model levels using the live observed CDR/underlying
    price ratio.

    This is NOT a USD/CAD conversion. CDRs represent fractional ownership and
    use a notional currency hedge. The observed ratio can change over time.
    """
    mapping = get_mapping(underlying_ticker)

    if mapping is None or underlying_price_usd <= 0:
        return None

    quote = get_latest_cdr_price(mapping)
    if quote is None:
        return None

    yahoo_symbol, cdr_price = quote
    ratio = cdr_price / underlying_price_usd

    def scale(value: float) -> float:
        return float(value) * ratio

    return CADPricePlan(
        underlying_ticker=underlying_ticker.upper(),
        cdr_symbol=yahoo_symbol,
        cdr_price_cad=cdr_price,
        observed_price_ratio=ratio,
        pullback_low_cad=scale(price_plan.entry_low),
        pullback_high_cad=scale(price_plan.entry_high),
        breakout_low_cad=scale(price_plan.breakout_entry_low),
        breakout_high_cad=scale(price_plan.breakout_entry_high),
        invalidation_cad=scale(price_plan.invalidation),
        target_1_low_cad=scale(price_plan.target_1_low),
        target_1_high_cad=scale(price_plan.target_1_high),
        target_2_low_cad=scale(price_plan.target_2_low),
        target_2_high_cad=scale(price_plan.target_2_high),
        data_source="Yahoo Finance delayed quote + observed CDR ratio",
        warning=(
            "Approximate CAD-hedged ranges. The CDR ratio changes over time, "
            "quotes may be delayed, and execution prices must be verified "
            "with your Canadian broker."
        ),
    )
