from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from winwatt_automation.knowledge.models import ExperimentSpec, KnowledgeStatus
from winwatt_automation.navigation.models import NavigationContextSummary


class ContextConcept(BaseModel):
    concept: str
    status: KnowledgeStatus
    confidence: float
    evidence_kinds: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class ManualFinding(BaseModel):
    source_id: str
    page: int = Field(gt=0)
    section: str | None = None
    excerpt: str
    related_concepts: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class HumanResearchHint(BaseModel):
    text: str = Field(min_length=1)
    provenance: Literal["human"] = "human"
    verified: Literal[False] = False

    model_config = {"extra": "forbid"}


class NavigationalResearchTarget(BaseModel):
    source: Literal["human_hint"] = "human_hint"
    path_hint: list[str] = Field(default_factory=list)
    target_semantics: str
    verified: Literal[False] = False

    model_config = {"extra": "forbid"}

class RecentDiscoveredControl(BaseModel):
    identity: str; caption: str; control_type: str; enabled: bool
    model_config = {"extra": "forbid"}
class RecentResearchStep(BaseModel):
    action: str; semantic_context: str; resulting_window: str | None = None
    discovered_controls: list[RecentDiscoveredControl] = Field(default_factory=list)
    state_change: bool = False; failures: list[str] = Field(default_factory=list)
    state_fingerprint: str | None = None
    recently_activated_control: str | None = None
    model_config = {"extra": "forbid"}


class ResearchContext(BaseModel):
    goal: str = Field(min_length=1)
    verified_concepts: list[ContextConcept] = Field(default_factory=list)
    hypotheses: list[ContextConcept] = Field(default_factory=list)
    rejected_hypotheses: list[ContextConcept] = Field(default_factory=list)
    relevant_capabilities: list[ContextConcept] = Field(default_factory=list)
    manual_evidence: list[ManualFinding] = Field(default_factory=list)
    previous_experiments: list[str] = Field(default_factory=list)
    known_safe_experiment_handlers: list[str] = Field(default_factory=list)
    human_hints: list[HumanResearchHint] = Field(default_factory=list)
    navigational_targets: list[NavigationalResearchTarget] = Field(default_factory=list)
    recent_research_trace: list[RecentResearchStep] = Field(default_factory=list)
    # These are an explicit, bounded projection of the last UI observation.
    # They make observed identities available to strict structured output
    # without exposing a raw UIA or coordinate primitive.
    current_window: str | None = None
    current_state_fingerprint: str | None = None
    recently_activated_control: str | None = None
    actionable_controls: list[RecentDiscoveredControl] = Field(default_factory=list)
    known_safe_navigation_capabilities: list[str] = Field(default_factory=list)
    navigation_knowledge: NavigationContextSummary = Field(default_factory=NavigationContextSummary)

    model_config = {"extra": "forbid"}


class ProposedHypothesis(BaseModel):
    target_capability: str = Field(min_length=1)
    semantic_guess: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    model_config = {"extra": "forbid"}


class ProposedExperiment(BaseModel):
    experiment_status: Literal["supported", "unsupported"]
    reason: str = Field(min_length=1)
    missing_capability: str | None = None
    spec: ExperimentSpec | None = None

    model_config = {"extra": "forbid"}


class CapabilityDiscovery(BaseModel):
    """Documentation-supported candidates, never runtime verification."""

    boundary_types: list[str] = Field(default_factory=list)
    workflows: list[str] = Field(default_factory=list)
    common_fields: list[str] = Field(default_factory=list)
    type_specific_fields: dict[str, list[str]] = Field(default_factory=dict)
    capability_candidates: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class ResearchPlan(BaseModel):
    """Validated LLM output. No field can express a verified state transition."""

    goal: str = Field(min_length=1)
    interpreted_scope: str = Field(min_length=1)
    known_verified: list[str] = Field(default_factory=list)
    manual_supported: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    recommended_next_target: str = Field(min_length=1)
    reasoning_summary: str = Field(min_length=1)
    research_step_type: Literal["documentation_research", "capability_enumeration", "experiment", "human_question", "unsupported"]
    discovery: CapabilityDiscovery | None = None
    proposed_hypothesis: ProposedHypothesis | None = None
    proposed_experiment: ProposedExperiment | None = None
    needs_human_input: bool = False
    human_question: str | None = None
    ui_action: "CandidateUIAction | None" = None

    model_config = {"extra": "forbid"}


class CandidateExperimentSpec(BaseModel):
    """LLM-facing proposal; no candidate ever reaches the automation runner."""

    hypothesis_id: str = ""
    target_capability: str = ""
    change: "CandidateExperimentChange" = Field(default_factory=lambda: CandidateExperimentChange())
    observe: list[str] = Field(default_factory=list)
    source_project: str | None = None

    model_config = {"extra": "forbid"}


class CandidateExperimentChange(BaseModel):
    entity: str = ""
    from_value: float | str | None = Field(default=None, alias="from")
    to_value: float | str | None = Field(default=None, alias="to")

    model_config = {"populate_by_name": True, "extra": "forbid"}


class CandidateTypeSpecificFields(BaseModel):
    structure_type: str
    fields: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class CandidateCapabilityDiscovery(BaseModel):
    boundary_types: list[str] = Field(default_factory=list)
    workflows: list[str] = Field(default_factory=list)
    common_fields: list[str] = Field(default_factory=list)
    type_specific_fields: list[CandidateTypeSpecificFields] = Field(default_factory=list)
    capability_candidates: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class CandidateProposedExperiment(BaseModel):
    experiment_status: str = "unsupported"
    reason: str = ""
    missing_capability: str | None = None
    spec: CandidateExperimentSpec | None = None

    model_config = {"extra": "forbid"}


class CandidateResearchPlan(BaseModel):
    """Provider-facing schema. Conversion to ResearchPlan is deterministic and fail-closed."""

    goal: str = Field(min_length=1)
    interpreted_scope: str = Field(min_length=1)
    known_verified: list[str] = Field(default_factory=list)
    manual_supported: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    recommended_next_target: str = Field(min_length=1)
    reasoning_summary: str = Field(min_length=1)
    research_step_type: str = "unsupported"
    discovery: CandidateCapabilityDiscovery | None = None
    proposed_hypothesis: ProposedHypothesis | None = None
    proposed_experiment: CandidateProposedExperiment | None = None
    needs_human_input: bool = False
    human_question: str | None = None
    ui_action: "CandidateUIAction | None" = None

    model_config = {"extra": "forbid"}


class CandidateUIAction(BaseModel):
    kind: Literal["inspect_ui", "activate_control", "select_list_item", "set_control_value", "go_back", "compare_ui_state", "open_known_navigation"]
    identity: str | None = None
    value: str | None = None
    capability: str | None = None
    model_config = {"extra": "forbid"}


class PlannerAudit(BaseModel):
    prompt_version: str
    instructions: str
    provider: str
    model: str
    context: ResearchContext
    raw_response: dict

    model_config = {"extra": "forbid"}


class PlannerResult(BaseModel):
    plan: ResearchPlan
    audit: PlannerAudit

    model_config = {"extra": "forbid"}


class PlannerValidationFailure(BaseModel):
    """Secret-free diagnostic artifact for a deliberately rejected LLM plan."""

    validation_error: str
    parsed_candidate_plan: CandidateResearchPlan
    parsed_plan: ResearchPlan | None = None
    audit: PlannerAudit
    dry_run: Literal[True] = True

    model_config = {"extra": "forbid"}
