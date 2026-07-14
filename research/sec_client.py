from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

from .evidence_models import EvidenceClaim, SourceRecord
from .http_client import ResearchHTTPClient


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

IMPORTANT_FORMS = {"10-K", "10-Q", "8-K", "20-F", "6-K", "4"}

COMMON_FACTS = {
    "Revenues": ("Revenue", "USD"),
    "RevenueFromContractWithCustomerExcludingAssessedTax": ("Revenue", "USD"),
    "GrossProfit": ("Gross profit", "USD"),
    "OperatingIncomeLoss": ("Operating income", "USD"),
    "NetIncomeLoss": ("Net income", "USD"),
    "EarningsPerShareDiluted": ("Diluted EPS", "USD/shares"),
    "CashAndCashEquivalentsAtCarryingValue": ("Cash and cash equivalents", "USD"),
    "LongTermDebtCurrent": ("Current long-term debt", "USD"),
    "LongTermDebtNoncurrent": ("Long-term debt", "USD"),
    "StockholdersEquity": ("Stockholders' equity", "USD"),
    "NetCashProvidedByUsedInOperatingActivities": ("Operating cash flow", "USD"),
    "PaymentsToAcquirePropertyPlantAndEquipment": ("Capital expenditure", "USD"),
    "InventoryNet": ("Inventory", "USD"),
}


def _source_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:14]
    return f"{prefix}_{digest}"


class SECClient:
    def __init__(self) -> None:
        user_agent = os.getenv(
            "SEC_USER_AGENT",
            "QuantResearchPlatform research@example.com",
        )
        self.http = ResearchHTTPClient(
            user_agent=user_agent,
            minimum_interval_seconds=0.2,
        )

    def ticker_record(self, ticker: str) -> dict[str, Any]:
        data = self.http.get_json(SEC_TICKERS_URL)
        symbol = ticker.upper()

        for record in data.values():
            if str(record.get("ticker", "")).upper() == symbol:
                return record

        raise ValueError(f"SEC CIK not found for ticker {symbol}.")

    def company_identity(self, ticker: str) -> tuple[str, str]:
        record = self.ticker_record(ticker)
        cik = str(record["cik_str"]).zfill(10)
        return cik, str(record.get("title") or ticker.upper())

    def recent_filings(
        self,
        ticker: str,
        *,
        limit: int = 20,
    ) -> tuple[list[SourceRecord], list[EvidenceClaim]]:
        cik, company_name = self.company_identity(ticker)
        payload = self.http.get_json(
            SEC_SUBMISSIONS_URL.format(cik=cik)
        )

        recent = payload.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        primary_documents = recent.get("primaryDocument", [])
        report_dates = recent.get("reportDate", [])

        sources: list[SourceRecord] = []
        claims: list[EvidenceClaim] = []
        retrieved = datetime.now(timezone.utc)

        for index, form in enumerate(forms):
            if form not in IMPORTANT_FORMS:
                continue

            accession = accession_numbers[index]
            accession_compact = accession.replace("-", "")
            cik_unpadded = str(int(cik))
            document = primary_documents[index]
            url = (
                f"{SEC_ARCHIVES_BASE}/{cik_unpadded}/"
                f"{accession_compact}/{document}"
            )
            filing_date = filing_dates[index]
            report_date = report_dates[index] or None
            source_id = _source_id("sec", url)

            published = datetime.fromisoformat(
                f"{filing_date}T00:00:00+00:00"
            )

            sources.append(
                SourceRecord(
                    source_id=source_id,
                    title=f"{company_name} {form} filed {filing_date}",
                    url=url,
                    publisher="U.S. Securities and Exchange Commission",
                    published_at=published,
                    retrieved_at=retrieved,
                    source_tier=1,
                    source_type=form,
                    official=True,
                )
            )

            claims.append(
                EvidenceClaim(
                    claim_id=_source_id("claim", f"{form}{accession}"),
                    kind="filing",
                    claim=(
                        f"{company_name} filed Form {form} on {filing_date}"
                        + (
                            f" for the period ended {report_date}."
                            if report_date
                            else "."
                        )
                    ),
                    period=report_date,
                    source_ids=[source_id],
                    reliability=1.0,
                    materiality=0.8 if form in {"10-K", "10-Q", "8-K"} else 0.5,
                    freshness_score=1.0,
                    tags=["SEC", form],
                )
            )

            if len(sources) >= limit:
                break

        return sources, claims

    def company_facts(
        self,
        ticker: str,
        *,
        facts_per_metric: int = 4,
    ) -> tuple[list[SourceRecord], list[EvidenceClaim]]:
        cik, company_name = self.company_identity(ticker)
        payload = self.http.get_json(
            SEC_FACTS_URL.format(cik=cik)
        )

        companyfacts_url = SEC_FACTS_URL.format(cik=cik)
        source_id = _source_id("secfacts", companyfacts_url)
        retrieved = datetime.now(timezone.utc)

        source = SourceRecord(
            source_id=source_id,
            title=f"{company_name} SEC XBRL Company Facts",
            url=companyfacts_url,
            publisher="U.S. Securities and Exchange Commission",
            published_at=None,
            retrieved_at=retrieved,
            source_tier=1,
            source_type="SEC Company Facts",
            official=True,
        )

        us_gaap = payload.get("facts", {}).get("us-gaap", {})
        claims: list[EvidenceClaim] = []

        for fact_name, (label, preferred_unit) in COMMON_FACTS.items():
            fact = us_gaap.get(fact_name)
            if not fact:
                continue

            units = fact.get("units", {})
            observations = (
                units.get(preferred_unit)
                or units.get("USD")
                or units.get("USD/shares")
                or next(iter(units.values()), [])
            )

            valid = [
                item
                for item in observations
                if item.get("val") is not None
                and item.get("filed")
                and item.get("form") in {"10-K", "10-Q", "20-F", "6-K"}
            ]
            valid.sort(
                key=lambda item: (
                    item.get("filed", ""),
                    item.get("end", ""),
                ),
                reverse=True,
            )

            seen_periods: set[tuple[str, str, str]] = set()

            for item in valid:
                key = (
                    str(item.get("end")),
                    str(item.get("form")),
                    str(item.get("fp")),
                )
                if key in seen_periods:
                    continue
                seen_periods.add(key)

                period = str(item.get("end") or "")
                form = str(item.get("form") or "")
                fiscal_period = str(item.get("fp") or "")
                value = item["val"]
                unit = preferred_unit if preferred_unit in units else (
                    "USD/shares" if "USD/shares" in units else "USD"
                )

                claims.append(
                    EvidenceClaim(
                        claim_id=_source_id(
                            "fact",
                            f"{ticker}{fact_name}{period}{form}{value}",
                        ),
                        kind="financial_fact",
                        claim=(
                            f"{label} reported for period ending {period} "
                            f"({form}, {fiscal_period}) was {value} {unit}."
                        ),
                        value=float(value),
                        unit=unit,
                        period=period,
                        source_ids=[source_id],
                        reliability=0.98,
                        materiality=0.75,
                        freshness_score=0.9,
                        tags=["SEC", "XBRL", fact_name, form],
                    )
                )

                if len(seen_periods) >= facts_per_metric:
                    break

        return [source], claims
