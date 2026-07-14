from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from .evidence_models import (
    ConflictRecord,
    EvidenceClaim,
    EvidenceQuality,
    SourceRecord,
)
from .source_quality import source_authority_score


def detect_conflicts(
    claims: list[EvidenceClaim],
) -> list[ConflictRecord]:
    """
    Conservative starter conflict detector.

    It flags multiple numeric values for the same fact tag and period.
    It does not decide which value is correct.
    """
    buckets: dict[tuple[str, str], list[EvidenceClaim]] = defaultdict(list)

    for claim in claims:
        if not isinstance(claim.value, (int, float)) or not claim.period:
            continue

        fact_tags = [
            tag
            for tag in claim.tags
            if tag not in {"SEC", "XBRL", "10-K", "10-Q", "8-K"}
        ]

        if not fact_tags:
            continue

        buckets[(fact_tags[-1], claim.period)].append(claim)

    conflicts: list[ConflictRecord] = []

    for (topic, period), group in buckets.items():
        values = {round(float(claim.value), 8) for claim in group}

        if len(values) > 1:
            conflicts.append(
                ConflictRecord(
                    topic=f"{topic} for {period}",
                    claim_ids=[claim.claim_id for claim in group],
                    explanation=(
                        "Multiple distinct numeric values were collected for "
                        "the same topic and period. Review units and filing "
                        "context before drawing a conclusion."
                    ),
                    severity="medium",
                )
            )

    return conflicts


def calculate_quality(
    sources: list[SourceRecord],
    claims: list[EvidenceClaim],
    *,
    missing_data: list[str] | None = None,
) -> EvidenceQuality:
    missing = list(missing_data or [])

    if not sources or not claims:
        return EvidenceQuality(
            evidence_coverage=0,
            primary_source_coverage=0,
            freshness=0,
            corroboration=0,
            confidence=0,
            missing_data=missing,
        )

    primary_claims = 0
    freshness_values: list[float] = []
    authority_values: list[float] = []
    source_lookup = {source.source_id: source for source in sources}

    for claim in claims:
        freshness_values.append(claim.freshness_score)

        linked_sources = [
            source_lookup[source_id]
            for source_id in claim.source_ids
            if source_id in source_lookup
        ]

        if linked_sources:
            authority_values.append(
                max(source_authority_score(source) for source in linked_sources)
            )

        if any(source.official for source in linked_sources):
            primary_claims += 1

    coverage = min(100, round(len(claims) / 40 * 100))
    primary = round(primary_claims / len(claims) * 100)
    freshness = round(
        sum(freshness_values) / len(freshness_values) * 100
    )
    authority = (
        round(sum(authority_values) / len(authority_values) * 100)
        if authority_values
        else 0
    )

    unique_publishers = len({source.publisher for source in sources})
    corroboration = min(100, 25 + unique_publishers * 10)

    confidence = round(
        coverage * 0.20
        + primary * 0.30
        + freshness * 0.20
        + authority * 0.20
        + corroboration * 0.10
    )

    return EvidenceQuality(
        evidence_coverage=coverage,
        primary_source_coverage=primary,
        freshness=freshness,
        corroboration=corroboration,
        confidence=max(0, min(100, confidence)),
        missing_data=missing,
    )
