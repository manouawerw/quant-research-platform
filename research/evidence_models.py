from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


SourceTier = Literal[1, 2, 3, 4, 5]
EvidenceKind = Literal[
    "filing",
    "financial_fact",
    "company_release",
    "news",
    "macro",
    "technical",
]


class SourceRecord(BaseModel):
    source_id: str
    title: str
    url: str
    publisher: str
    published_at: datetime | None = None
    retrieved_at: datetime
    source_tier: SourceTier
    source_type: str
    official: bool = False


class EvidenceClaim(BaseModel):
    claim_id: str
    kind: EvidenceKind
    claim: str
    value: float | str | bool | None = None
    unit: str | None = None
    period: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    reliability: float = Field(ge=0, le=1)
    materiality: float = Field(ge=0, le=1)
    freshness_score: float = Field(ge=0, le=1)
    interpretation: bool = False
    tags: list[str] = Field(default_factory=list)


class ConflictRecord(BaseModel):
    topic: str
    claim_ids: list[str]
    explanation: str
    severity: Literal["low", "medium", "high"]


class EvidenceQuality(BaseModel):
    evidence_coverage: int = Field(ge=0, le=100)
    primary_source_coverage: int = Field(ge=0, le=100)
    freshness: int = Field(ge=0, le=100)
    corroboration: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    missing_data: list[str] = Field(default_factory=list)


class EvidencePackage(BaseModel):
    ticker: str
    company_name: str | None = None
    cik: str | None = None
    generated_at: datetime
    sources: list[SourceRecord] = Field(default_factory=list)
    claims: list[EvidenceClaim] = Field(default_factory=list)
    conflicts: list[ConflictRecord] = Field(default_factory=list)
    quality: EvidenceQuality
    technical_context: dict[str, Any] = Field(default_factory=dict)
    macro_context: dict[str, Any] = Field(default_factory=dict)
