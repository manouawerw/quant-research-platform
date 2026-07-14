from __future__ import annotations

import io
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import pandas as pd
import requests


UniverseName = Literal["US Liquid 1500", "S&P 500"]

NASDAQ_TRADED_URL = (
    "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt"
)
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

CACHE_DIR = Path("data/universe_cache")
CACHE_HOURS = 24


@dataclass(frozen=True)
class UniverseMember:
    ticker: str
    company_name: str
    sector: str
    sub_industry: str
    exchange: str
    universe_name: str
    source: str
    retrieved_at: str


def normalize_alpaca_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(".", "-")


def _cache_path(name: str) -> Path:
    safe = name.lower().replace("&", "and").replace(" ", "_")
    return CACHE_DIR / f"{safe}.json"


def _cache_is_fresh(path: Path) -> bool:
    if not path.exists():
        return False

    modified = datetime.fromtimestamp(
        path.stat().st_mtime,
        tz=timezone.utc,
    )
    return (
        datetime.now(timezone.utc) - modified
        < timedelta(hours=CACHE_HOURS)
    )


def _read_cache(path: Path) -> list[UniverseMember]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [UniverseMember(**item) for item in data]


def _write_cache(
    path: Path,
    members: list[UniverseMember],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [asdict(member) for member in members],
            indent=2,
        ),
        encoding="utf-8",
    )


def _looks_like_common_equity(
    security_name: str,
    *,
    etf_flag: str,
    test_issue: str,
) -> bool:
    name = security_name.lower()

    if etf_flag == "Y" or test_issue == "Y":
        return False

    blocked_terms = (
        "warrant",
        "right",
        "unit",
        "preferred",
        "depositary share",
        "notes due",
        "bond",
        "debenture",
        "etf",
        "etn",
        "fund",
        "index",
        "acquisition corp",
        "acquisition company",
    )

    if any(term in name for term in blocked_terms):
        return False

    allowed_terms = (
        "common stock",
        "common shares",
        "ordinary shares",
        "ordinary share",
        "class a",
        "class b",
        "class c",
        "american depositary shares",
        "ads",
    )

    return any(term in name for term in allowed_terms)


def fetch_us_listed_candidates(
    *,
    force_refresh: bool = False,
) -> list[UniverseMember]:
    """
    Load current U.S.-listed common-equity candidates from Nasdaq Trader's
    official all-issues symbol directory.

    Liquidity ranking happens later from current snapshots, so this function
    intentionally returns more than 1,500 candidates.
    """
    name = "US Liquid 1500"
    cache = _cache_path(name)

    if not force_refresh and _cache_is_fresh(cache):
        return _read_cache(cache)

    response = requests.get(
        NASDAQ_TRADED_URL,
        timeout=30,
        headers={
            "User-Agent": (
                "QuantResearchPlatform/1.0 "
                "(market research application)"
            )
        },
    )
    response.raise_for_status()

    frame = pd.read_csv(
        io.StringIO(response.text),
        sep="|",
        dtype=str,
    )

    frame = frame[
        frame["Nasdaq Traded"].eq("Y")
        & frame["Test Issue"].eq("N")
    ].copy()

    retrieved_at = datetime.now(timezone.utc).isoformat()
    members: list[UniverseMember] = []

    for _, row in frame.iterrows():
        symbol = str(row.get("Symbol") or "").strip()
        name_value = str(row.get("Security Name") or "").strip()

        if not symbol or not name_value:
            continue

        if not _looks_like_common_equity(
            name_value,
            etf_flag=str(row.get("ETF") or "N"),
            test_issue=str(row.get("Test Issue") or "N"),
        ):
            continue

        members.append(
            UniverseMember(
                ticker=normalize_alpaca_symbol(symbol),
                company_name=name_value,
                sector="Unclassified",
                sub_industry="Unclassified",
                exchange=str(row.get("Listing Exchange") or "Unknown"),
                universe_name=name,
                source=NASDAQ_TRADED_URL,
                retrieved_at=retrieved_at,
            )
        )

    members = list(
        {member.ticker: member for member in members}.values()
    )
    members.sort(key=lambda member: member.ticker)
    _write_cache(cache, members)
    return members


def fetch_sp500_universe(
    *,
    force_refresh: bool = False,
) -> list[UniverseMember]:
    """
    Load the current S&P 500 table.

    io.StringIO fixes the previous pandas bug where raw HTML was interpreted
    as a filesystem path.
    """
    name = "S&P 500"
    cache = _cache_path(name)

    if not force_refresh and _cache_is_fresh(cache):
        return _read_cache(cache)

    response = requests.get(
        SP500_URL,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 QuantResearchPlatform/1.0"},
    )
    response.raise_for_status()

    tables = pd.read_html(io.StringIO(response.text))

    if not tables:
        raise RuntimeError("No S&P 500 table was found.")

    frame = tables[0]
    retrieved_at = datetime.now(timezone.utc).isoformat()

    members = [
        UniverseMember(
            ticker=normalize_alpaca_symbol(str(row["Symbol"])),
            company_name=str(row["Security"]),
            sector=str(row["GICS Sector"]),
            sub_industry=str(row["GICS Sub-Industry"]),
            exchange="S&P 500 constituent",
            universe_name=name,
            source=SP500_URL,
            retrieved_at=retrieved_at,
        )
        for _, row in frame.iterrows()
    ]

    members = list(
        {member.ticker: member for member in members}.values()
    )
    members.sort(key=lambda member: member.ticker)
    _write_cache(cache, members)
    return members


def fetch_universe(
    universe_name: UniverseName,
    *,
    force_refresh: bool = False,
) -> list[UniverseMember]:
    if universe_name == "US Liquid 1500":
        return fetch_us_listed_candidates(
            force_refresh=force_refresh
        )

    if universe_name == "S&P 500":
        return fetch_sp500_universe(
            force_refresh=force_refresh
        )

    raise ValueError(f"Unknown universe: {universe_name}")
