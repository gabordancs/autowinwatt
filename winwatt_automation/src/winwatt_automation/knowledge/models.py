from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class KnowledgeStatus(StrEnum):
    UNKNOWN = "unknown"
    HYPOTHESIS = "hypothesis"
    EXPERIMENTED = "experimented"
    VERIFIED = "verified"
    REJECTED = "rejected"


class EvidenceRef(BaseModel):
    """A compact, serialisable reference to an observation or verification."""

    kind: str = Field(min_length=1)
    path: str | None = None
    description: str = ""
    deterministic: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class SemanticConcept(BaseModel):
    concept: str = Field(min_length=1)
    entity: str = Field(min_length=1)
    data_type: str = Field(min_length=1)
    unit: str | None = None
    status: KnowledgeStatus = KnowledgeStatus.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class SemanticCapability(BaseModel):
    capability: str = Field(min_length=1)
    preferred_transport: str | None = None
    ui_read: str = "unknown"
    ui_write: str = "unknown"
    roundtrip_verified: bool = False
    status: KnowledgeStatus = KnowledgeStatus.UNKNOWN
    evidence: list[EvidenceRef] = Field(default_factory=list)


class Hypothesis(BaseModel):
    hypothesis_id: str = Field(min_length=1)
    target_capability: str = Field(min_length=1)
    semantic_guess: str = Field(min_length=1)
    status: KnowledgeStatus = KnowledgeStatus.HYPOTHESIS
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    experiment_ids: list[str] = Field(default_factory=list)
    research_evidence_ids: list[str] = Field(default_factory=list)


class ExperimentChange(BaseModel):
    """Semantic change request. It intentionally has no UI coordinate/key fields."""

    entity: str = Field(min_length=1)
    from_value: float | str | None = Field(default=None, alias="from")
    to_value: float | str = Field(alias="to")

    model_config = {"populate_by_name": True, "extra": "forbid"}


class ExperimentSpec(BaseModel):
    hypothesis_id: str = Field(min_length=1)
    target_capability: str = Field(min_length=1)
    change: ExperimentChange
    observe: list[str] = Field(min_length=1)
    source_project: str | None = None

    model_config = {"extra": "forbid"}

    @field_validator("observe")
    @classmethod
    def known_observations_only(cls, values: list[str]) -> list[str]:
        allowed = {"ui_readback", "save_reopen"}
        unknown = set(values).difference(allowed)
        if unknown:
            raise ValueError(f"unsupported observation requests: {sorted(unknown)}")
        return values


class ExperimentResult(BaseModel):
    experiment_id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    target_capability: str = Field(min_length=1)
    success: bool
    expected: float | str | None = None
    actual: float | str | None = None
    roundtrip_verified: bool = False
    sandbox_project: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class AssignExistingBoundaryStructureInput(BaseModel):
    """Safe semantic input for a previously discovered catalogue reference."""

    hypothesis_id: str = Field(min_length=1)
    room_identifier: str = Field(min_length=1)
    structure_reference: str = Field(min_length=1)
    expected_kind: str | None = None
    sandbox_project: str
    room_area_m2: float = Field(default=10.0, gt=0)

    model_config = {"extra": "forbid"}

    def as_experiment_spec(self) -> ExperimentSpec:
        return ExperimentSpec(
            hypothesis_id=self.hypothesis_id,
            target_capability="room.boundary.structure_reference.assign_existing",
            change={"entity": self.room_identifier, "to": self.structure_reference},
            observe=["ui_readback", "save_reopen"], source_project=self.sandbox_project,
        )
