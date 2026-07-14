from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlparse

from .evidence_models import EvidenceClaim, SourceRecord
from .http_client import ResearchHTTPClient


def _id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:14]}"


def configured_company_sources(
    ticker: str,
) -> tuple[list[SourceRecord], list[EvidenceClaim]]:
    """
    Reads optional official investor-relations URLs from COMPANY_IR_URLS_JSON.

    Example:
    COMPANY_IR_URLS_JSON={"MU":["https://investors.micron.com/"]}
    """
    raw = os.getenv("COMPANY_IR_URLS_JSON", "{}")

    try:
        mapping = json.loads(raw)
    except json.JSONDecodeError:
        mapping = {}

    urls = mapping.get(ticker.upper(), [])
    if isinstance(urls, str):
        urls = [urls]

    sources: list[SourceRecord] = []
    claims: list[EvidenceClaim] = []
    retrieved = datetime.now(timezone.utc)

    for url in urls:
        domain = urlparse(url).netloc
        source_id = _id("ir", url)

        sources.append(
            SourceRecord(
                source_id=source_id,
                title=f"{ticker.upper()} investor-relations source",
                url=url,
                publisher=domain or ticker.upper(),
                published_at=None,
                retrieved_at=retrieved,
                source_tier=1,
                source_type="Investor Relations",
                official=True,
            )
        )

        claims.append(
            EvidenceClaim(
                claim_id=_id("claim", source_id),
                kind="company_release",
                claim=(
                    f"Official investor-relations source configured for "
                    f"{ticker.upper()}."
                ),
                source_ids=[source_id],
                reliability=0.95,
                materiality=0.5,
                freshness_score=0.5,
                tags=["investor-relations", "configured-source"],
            )
        )

    return sources, claims
