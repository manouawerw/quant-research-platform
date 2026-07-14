from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse

from .evidence_models import EvidenceClaim, SourceRecord
from .http_client import ResearchHTTPClient


GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

TIER_2_DOMAINS = {
    "reuters.com",
    "apnews.com",
    "ft.com",
    "wsj.com",
    "cnbc.com",
    "bloomberg.com",
    "theglobeandmail.com",
}
TIER_3_DOMAINS = {
    "marketwatch.com",
    "barrons.com",
    "investing.com",
    "seekingalpha.com",
    "techcrunch.com",
    "tomshardware.com",
}


def _id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:14]}"


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _tier(domain: str) -> int:
    if any(domain == item or domain.endswith(f".{item}") for item in TIER_2_DOMAINS):
        return 2
    if any(domain == item or domain.endswith(f".{item}") for item in TIER_3_DOMAINS):
        return 3
    return 4


def _parse_seen_date(value: str | None) -> datetime | None:
    if not value:
        return None

    formats = [
        "%Y%m%dT%H%M%SZ",
        "%Y%m%d%H%M%S",
        "%Y-%m-%dT%H:%M:%SZ",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue

    return None


class GDELTNewsClient:
    def __init__(self) -> None:
        self.http = ResearchHTTPClient(
            user_agent="QuantResearchPlatform/1.0",
            minimum_interval_seconds=0.5,
        )

    def search(
        self,
        *,
        ticker: str,
        company_name: str | None,
        max_records: int = 25,
        timespan: str = "7d",
    ) -> tuple[list[SourceRecord], list[EvidenceClaim]]:
        query_parts = [f'"{ticker.upper()}"']

        if company_name:
            query_parts.append(f'"{company_name}"')

        query = " OR ".join(query_parts)

        payload = self.http.get_json(
            GDELT_DOC_URL,
            params={
                "query": query,
                "mode": "artlist",
                "maxrecords": max_records,
                "format": "json",
                "sort": "hybridrel",
                "timespan": timespan,
            },
        )

        articles = payload.get("articles", [])
        sources: list[SourceRecord] = []
        claims: list[EvidenceClaim] = []
        retrieved = datetime.now(timezone.utc)
        seen_urls: set[str] = set()

        for article in articles:
            url = str(article.get("url") or "")
            title = str(article.get("title") or "").strip()

            if not url or not title or url in seen_urls:
                continue

            seen_urls.add(url)
            domain = _domain(url)
            source_id = _id("news", url)
            published = _parse_seen_date(
                article.get("seendate")
                or article.get("date")
            )

            source = SourceRecord(
                source_id=source_id,
                title=title,
                url=url,
                publisher=domain or "Unknown publisher",
                published_at=published,
                retrieved_at=retrieved,
                source_tier=_tier(domain),
                source_type="News metadata",
                official=False,
            )
            sources.append(source)

            claims.append(
                EvidenceClaim(
                    claim_id=_id("headline", url),
                    kind="news",
                    claim=(
                        f"News headline: {title}. "
                        "This is discovery metadata and has not been "
                        "independently verified from the full article."
                    ),
                    source_ids=[source_id],
                    reliability=0.45 if source.source_tier >= 4 else 0.7,
                    materiality=0.5,
                    freshness_score=0.95 if published else 0.7,
                    interpretation=False,
                    tags=["news-headline", domain],
                )
            )

        return sources, claims
