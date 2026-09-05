from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from winwatt_automation.knowledge.models import EvidenceRef


class ResearchSource(BaseModel):
    id: str = Field(min_length=1)
    type: Literal["manual"] = "manual"
    title: str = Field(min_length=1)
    path: str = Field(min_length=1)
    version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchEvidence(BaseModel):
    """A source claim with provenance; it is explicitly non-deterministic."""

    evidence_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    page: int = Field(gt=0)
    section: str | None = None
    excerpt: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    related_concepts: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    deterministic: Literal[False] = False

    def as_evidence_ref(self) -> EvidenceRef:
        return EvidenceRef(
            kind="research_manual",
            description=self.claim,
            deterministic=False,
            data={
                "research_evidence_id": self.evidence_id,
                "source_id": self.source_id,
                "page": self.page,
                "section": self.section,
                "excerpt": self.excerpt,
                "related_concepts": self.related_concepts,
                "confidence": self.confidence,
            },
        )
