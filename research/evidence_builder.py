from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .company_sources import configured_company_sources
from .evidence_models import EvidencePackage
from .evidence_validator import calculate_quality, detect_conflicts
from .fundamentals import summarize_fundamentals
from .macro_client import FREDClient
from .news_client import GDELTNewsClient
from .sec_client import SECClient
from .source_quality import deduplicate_sources


def build_evidence_package(
    *,
    ticker: str,
    technical_context: dict[str, Any],
    include_news: bool = True,
    include_macro: bool = True,
) -> EvidencePackage:
    symbol = ticker.upper()
    sec = SECClient()

    missing: list[str] = []
    sources = []
    claims = []

    try:
        cik, company_name = sec.company_identity(symbol)
    except Exception as exc:
        cik = None
        company_name = None
        missing.append(f"SEC company identity unavailable: {exc}")

    if cik:
        try:
            filing_sources, filing_claims = sec.recent_filings(
                symbol,
                limit=20,
            )
            sources.extend(filing_sources)
            claims.extend(filing_claims)
        except Exception as exc:
            missing.append(f"Recent SEC filings unavailable: {exc}")

        try:
            fact_sources, fact_claims = sec.company_facts(symbol)
            sources.extend(fact_sources)
            claims.extend(fact_claims)
        except Exception as exc:
            missing.append(f"SEC company facts unavailable: {exc}")

    ir_sources, ir_claims = configured_company_sources(symbol)
    sources.extend(ir_sources)
    claims.extend(ir_claims)

    if not ir_sources:
        missing.append(
            "No company investor-relations URL is configured."
        )

    if include_news:
        try:
            news_sources, news_claims = GDELTNewsClient().search(
                ticker=symbol,
                company_name=company_name,
                max_records=25,
                timespan="7d",
            )
            sources.extend(news_sources)
            claims.extend(news_claims)
        except Exception as exc:
            missing.append(f"News discovery unavailable: {exc}")

    macro_context: dict[str, Any] = {}
    if include_macro:
        try:
            macro_context = FREDClient().snapshot()
            if not macro_context.get("available"):
                missing.append(str(macro_context.get("message")))
        except Exception as exc:
            missing.append(f"Macro data unavailable: {exc}")

    sources = deduplicate_sources(sources)
    conflicts = detect_conflicts(claims)
    quality = calculate_quality(
        sources,
        claims,
        missing_data=missing,
    )

    technical_context = dict(technical_context)
    technical_context["fundamental_summary"] = summarize_fundamentals(
        claims
    )

    return EvidencePackage(
        ticker=symbol,
        company_name=company_name,
        cik=cik,
        generated_at=datetime.now(timezone.utc),
        sources=sources,
        claims=claims,
        conflicts=conflicts,
        quality=quality,
        technical_context=technical_context,
        macro_context=macro_context,
    )
