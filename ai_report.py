from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from research import (
    build_evidence_package,
    generate_evidence_grounded_report,
)


@dataclass(frozen=True)
class ResearchReport:
    ticker: str
    generated_at: datetime
    model: str
    report_markdown: str
    sources: list[dict[str, str]]
    search_queries: list[str]


def generate_research_report(
    *,
    ticker: str,
    company_context: dict[str, Any],
    technical_context: dict[str, Any],
) -> ResearchReport:
    package = build_evidence_package(
        ticker=ticker,
        technical_context={
            **technical_context,
            "company_context": company_context,
        },
        include_news=True,
        include_macro=True,
    )

    generated = generate_evidence_grounded_report(package)

    return ResearchReport(
        ticker=generated.ticker,
        generated_at=generated.generated_at,
        model=generated.model,
        report_markdown=generated.report_markdown,
        sources=generated.sources,
        search_queries=generated.search_queries,
    )
