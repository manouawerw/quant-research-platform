from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from google import genai
from google.genai import types

from .evidence_models import EvidencePackage


@dataclass(frozen=True)
class GeneratedEvidenceReport:
    ticker: str
    generated_at: datetime
    model: str
    report_markdown: str
    sources: list[dict[str, str]]
    search_queries: list[str]


def _create_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    return genai.Client(api_key=api_key)


def _compact_package(package: EvidencePackage) -> dict:
    """
    Keep the prompt bounded while preserving the strongest evidence.

    Official and high-quality sources are prioritized. News headline
    metadata is limited because it is weaker than primary-source evidence.
    """
    official_source_ids = {
        source.source_id
        for source in package.sources
        if source.official or source.source_tier <= 2
    }

    priority_claims = [
        claim
        for claim in package.claims
        if any(
            source_id in official_source_ids
            for source_id in claim.source_ids
        )
    ]

    news_claims = [
        claim
        for claim in package.claims
        if claim.kind == "news"
    ][:15]

    selected_claims = priority_claims[:70] + news_claims

    selected_source_ids = {
        source_id
        for claim in selected_claims
        for source_id in claim.source_ids
    }

    selected_sources = [
        source
        for source in package.sources
        if source.source_id in selected_source_ids
    ]

    return {
        "ticker": package.ticker,
        "company_name": package.company_name,
        "generated_at": package.generated_at.isoformat(),
        "quality": package.quality.model_dump(),
        "conflicts": [
            conflict.model_dump()
            for conflict in package.conflicts
        ],
        "technical_context": package.technical_context,
        "macro_context": package.macro_context,
        "sources": [
            source.model_dump(mode="json")
            for source in selected_sources
        ],
        "claims": [
            claim.model_dump(mode="json")
            for claim in selected_claims
        ],
    }


def generate_evidence_grounded_report(
    package: EvidencePackage,
) -> GeneratedEvidenceReport:
    model = os.getenv(
        "GEMINI_MODEL",
        "gemini-3-flash-preview",
    )

    evidence = _compact_package(package)

    prompt = f"""
Prepare an evidence-grounded equity research report for {package.ticker}.

Use only the evidence package below. Do not browse, invent, or silently fill
missing facts. Every factual statement must include one or more source IDs in
square brackets, such as [sec_abcd1234]. Claims based only on news headlines
must be labelled as unverified headline evidence. Clearly separate facts from
interpretation.

Do not provide personalized financial advice or guarantee returns. Do not
output a direct instruction to buy or sell.

Required Markdown sections:
# Executive Summary
# Evidence Quality
# Recent Official Filings
# Financial Performance and Balance Sheet
# Company and Industry Developments
# News and Event Signals
# Technical and Market Context
# Bull Case
# Base Case
# Bear Case
# Key Risks and Contradictions
# Key Levels and Thesis Invalidation
# What to Monitor Next
# Conclusion

In Evidence Quality, report coverage, primary-source coverage, freshness,
corroboration, overall confidence, contradictions, and missing data.

For financial comparisons, verify periods and units. Do not interpret two
different fiscal periods as directly comparable without saying so. When
evidence conflicts, show the conflict instead of choosing a convenient value.

Evidence package:
{json.dumps(evidence, indent=2, default=str)}
""".strip()

    client = _create_client()

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.15,
                max_output_tokens=4000,
            ),
        )
    finally:
        close_method = getattr(client, "close", None)
        if callable(close_method):
            close_method()

    report = (response.text or "").strip()

    if not report:
        raise RuntimeError("Gemini returned an empty report.")

    sources = [
        {
            "title": source.title,
            "url": source.url,
            "source_id": source.source_id,
            "publisher": source.publisher,
        }
        for source in package.sources
    ]

    return GeneratedEvidenceReport(
        ticker=package.ticker,
        generated_at=datetime.now(timezone.utc),
        model=model,
        report_markdown=report,
        sources=sources,
        search_queries=[],
    )
