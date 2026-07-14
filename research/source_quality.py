from __future__ import annotations

from urllib.parse import urlparse

from .evidence_models import SourceRecord


def source_authority_score(source: SourceRecord) -> float:
    tier_scores = {
        1: 1.0,
        2: 0.85,
        3: 0.7,
        4: 0.45,
        5: 0.25,
    }

    score = tier_scores[source.source_tier]

    if source.official:
        score = min(1.0, score + 0.05)

    return score


def deduplicate_sources(
    sources: list[SourceRecord],
) -> list[SourceRecord]:
    result: list[SourceRecord] = []
    seen: set[str] = set()

    for source in sources:
        normalized = source.url.rstrip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(source)

    return result
