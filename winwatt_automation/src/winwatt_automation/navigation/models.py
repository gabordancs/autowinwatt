from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from winwatt_automation.knowledge.models import EvidenceRef

NavigationStatus = Literal["observed", "replayed", "verified", "stale", "rejected"]


class NavigationControlSummary(BaseModel):
    identity: str
    caption: str
    control_type: str
    enabled: bool
    model_config = {"extra": "forbid"}


class NavigationState(BaseModel):
    id: str
    fingerprint: str
    window_title: str
    window_class: str
    mdi_title: str | None = None
    semantic_context: str = ""
    controls_summary: list[NavigationControlSummary] = Field(default_factory=list)
    provenance: list[EvidenceRef] = Field(default_factory=list)
    first_seen_at: datetime
    last_seen_at: datetime
    model_config = {"extra": "forbid"}


class NavigationTransition(BaseModel):
    id: str
    from_state_id: str
    action_kind: str
    action_identity: str | None = None
    capability: str | None = None
    semantic_action: str
    to_state_id: str
    expected_state: str | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    status: NavigationStatus = "observed"
    replay_count: int = 0
    success_count: int = 0
    last_verified_at: datetime | None = None
    model_config = {"extra": "forbid"}


class NavigationRoute(BaseModel):
    state_ids: list[str] = Field(default_factory=list)
    transitions: list[NavigationTransition] = Field(default_factory=list)
    total_cost: int = 0
    model_config = {"extra": "forbid"}


class ExecutableNavigationTransition(BaseModel):
    """Internal, evidence-backed replay instruction; never LLM generated."""
    transition_id: str
    from_state_id: str
    action_kind: str
    action_identity: str | None = None
    capability: str | None = None
    expected_to_state_id: str
    expected_state: str | None = None
    status: NavigationStatus
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    model_config = {"extra": "forbid"}


class ExecutableNavigationRoute(BaseModel):
    source: Literal["persistent_navigation_knowledge"] = "persistent_navigation_knowledge"
    route_id: str
    goal_relevance: float = Field(ge=0.0, le=1.0)
    start_state_id: str
    transitions: list[ExecutableNavigationTransition] = Field(default_factory=list)
    model_config = {"extra": "forbid"}


class NavigationContextItem(BaseModel):
    from_context: str
    action: str
    to_context: str
    status: NavigationStatus
    model_config = {"extra": "forbid"}


class NavigationContextSummary(BaseModel):
    relevant_states: list[NavigationState] = Field(default_factory=list)
    relevant_transitions: list[NavigationContextItem] = Field(default_factory=list)
    known_safe_navigation_capabilities: list[str] = Field(default_factory=list)
    model_config = {"extra": "forbid"}
