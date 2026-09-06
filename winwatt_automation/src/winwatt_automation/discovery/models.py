from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from winwatt_automation.knowledge.models import EvidenceRef, KnowledgeStatus


class DiscoveryGoal(BaseModel):
    semantic_scope: str = "room.boundary.structure_type"
    operation: Literal["enumerate_room_boundary_structure_types"]
    source_project: str
    room_name: str = "Discovery room"
    max_ui_actions: int = Field(default=24, ge=1, le=80)
    max_seconds: int = Field(default=90, ge=5, le=300)
    safety_constraints: list[str] = Field(default_factory=lambda: [
        "sandbox_only", "no_project_settings", "no_irreversible_dialogs", "no_save_outside_sandbox",
    ])

    model_config = {"extra": "forbid"}


class DiscoveryObservation(BaseModel):
    window_context: str
    control_identity: str
    caption: str
    control_type: str
    parent_path: list[str] = Field(default_factory=list)
    state_before: dict[str, Any] = Field(default_factory=dict)
    action: str
    state_after: dict[str, Any] = Field(default_factory=dict)
    screenshot_reference: str | None = None
    timestamp: datetime

    model_config = {"extra": "forbid"}


class DiscoveryEvidence(BaseModel):
    evidence_id: str
    session_id: str
    observation: DiscoveryObservation
    deterministic: Literal[False] = False

    model_config = {"extra": "forbid"}

    def as_evidence_ref(self) -> EvidenceRef:
        return EvidenceRef(
            kind="discovery", description=f"Sandbox UI discovery: {self.observation.caption}", deterministic=False,
            data={"discovery_evidence_id": self.evidence_id, "session_id": self.session_id, "observation": self.observation.model_dump(mode="json")},
        )


class CandidateCapability(BaseModel):
    candidate_id: str
    proposed_concept: str
    proposed_operation: str
    related_ui_controls: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    status: Literal[KnowledgeStatus.HYPOTHESIS] = KnowledgeStatus.HYPOTHESIS

    model_config = {"extra": "forbid"}


class StructureReferenceCandidate(BaseModel):
    """A concrete entry from the boundary-structure catalogue, never a kind by itself."""

    reference_id: str
    display_name: str
    source_control: str
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    detail_window_class: str | None = None
    detail_layout_fingerprint: str | None = None
    explicit_kind_value: str | None = None
    status: Literal[KnowledgeStatus.HYPOTHESIS] = KnowledgeStatus.HYPOTHESIS

    model_config = {"extra": "forbid"}


class StructureKindCandidate(BaseModel):
    """A non-verified grouping inferred from UI detail evidence, not from captions alone."""

    proposed_kind: str
    member_structure_references: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    classification_basis: str
    status: Literal[KnowledgeStatus.HYPOTHESIS] = KnowledgeStatus.HYPOTHESIS

    model_config = {"extra": "forbid"}


class StructureClassificationGoal(BaseModel):
    semantic_scope: str = "room.boundary.structure_reference"
    operation: Literal["classify_room_boundary_structures"] = "classify_room_boundary_structures"
    source_project: str
    room_name: str = "Discovery room"
    representative_captions: list[str] = Field(default_factory=list, max_length=6)
    max_representatives: int = Field(default=6, ge=1, le=6)
    max_ui_actions: int = Field(default=40, ge=1, le=40)
    max_seconds: int = Field(default=180, ge=5, le=180)
    safety_constraints: list[str] = Field(default_factory=lambda: [
        "sandbox_only", "no_project_settings", "no_irreversible_dialogs", "no_save_outside_sandbox",
        "cancel_or_reset_after_observation", "never_promote_discovery_to_verified",
    ])

    model_config = {"extra": "forbid"}


class DiscoveryResult(BaseModel):
    session_id: str
    goal: DiscoveryGoal
    sandbox_project: str
    visited_windows: list[str] = Field(default_factory=list)
    observations: list[DiscoveryObservation] = Field(default_factory=list)
    evidence: list[DiscoveryEvidence] = Field(default_factory=list)
    candidates: list[CandidateCapability] = Field(default_factory=list)
    stopped_reason: str
    errors: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class StructureClassificationResult(BaseModel):
    session_id: str
    goal: StructureClassificationGoal
    sandbox_project: str
    catalog_references_count: int = 0
    selected_representatives: list[str] = Field(default_factory=list)
    visited_windows: list[str] = Field(default_factory=list)
    observations: list[DiscoveryObservation] = Field(default_factory=list)
    evidence: list[DiscoveryEvidence] = Field(default_factory=list)
    structure_references: list[StructureReferenceCandidate] = Field(default_factory=list)
    structure_kinds: list[StructureKindCandidate] = Field(default_factory=list)
    workflow_summary: dict[str, Any] = Field(default_factory=dict)
    stopped_reason: str
    errors: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}
