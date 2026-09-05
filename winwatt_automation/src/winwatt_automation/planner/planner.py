from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from winwatt_automation.knowledge.models import ExperimentSpec, KnowledgeStatus
from winwatt_automation.knowledge.store import KnowledgeStore
from winwatt_automation.navigation.store import NavigationKnowledgeStore
from winwatt_automation.research.manual_index import ManualIndex

from .models import (
    CandidateResearchPlan, CapabilityDiscovery, ContextConcept, HumanResearchHint, ManualFinding, NavigationalResearchTarget, PlannerAudit, PlannerResult, RecentResearchStep,
    PlannerValidationFailure, ProposedExperiment, ResearchContext, ResearchPlan,
)
from .provider import LLMProvider


PROMPT_VERSION = "research_planner_v0.1"
SYSTEM_PROMPT = """You are a WinWatt research planner. Produce only the supplied structured schema.
You plan from the supplied context and nothing else. VERIFIED means only deterministic runtime
save/reopen/readback evidence. Manual material is documentation, never verification. A hypothesis
is unproven. You must not claim a new verified capability, create UI commands, coordinates, keys,
shell commands, or arbitrary automation. Propose an experiment only when its target is in
known_safe_experiment_handlers and its schema is valid; otherwise mark it unsupported and say why.
Use capability_enumeration for questions about available types, workflows, and fields; it must not
invent an experiment merely because a safe handler exists. Only research_step_type=experiment may
include proposed_experiment. This is a dry-run: do not request execution."""


class ResearchPlanValidationError(ValueError):
    """Fail-closed error that retains a safe diagnostic record for review."""

    def __init__(self, message: str, failure: PlannerValidationFailure) -> None:
        super().__init__(message)
        self.failure = failure


class ResearchPlanner:
    """Retrieval-first planner. It never opens WinWatt or writes KnowledgeStore."""

    def __init__(self, provider: LLMProvider, store: KnowledgeStore, manual_index: ManualIndex, navigation_store: NavigationKnowledgeStore | None = None) -> None:
        self.provider = provider
        self.store = store
        self.manual_index = manual_index
        self.navigation_store = navigation_store or NavigationKnowledgeStore()

    @staticmethod
    def _goal_terms(goal: str) -> list[str]:
        text = goal.casefold()
        terms: list[str] = []
        if "fal" in text or "external" in text:
            terms.append("külső fal")
        if "szerkezet" in text or "fal" in text or "boundary" in text:
            terms.append("határoló szerkezet")
        if not terms:
            stop_words = {"tanuld", "meg", "a", "az", "és", "kezelését", "kutass", "learn", "about", "the"}
            meaningful = [term for term in re.findall(r"\w+", text) if len(term) >= 4 and term not in stop_words]
            if meaningful:
                terms.append(" ".join(meaningful[:3]))
        return list(dict.fromkeys(terms))

    @staticmethod
    def _semantic_needles(goal: str) -> list[str]:
        text = goal.casefold()
        needles = [word for word in re.findall(r"[a-z_]+", text) if len(word) >= 3]
        if "fal" in text or "external" in text:
            needles.extend(["external_wall", "boundary"])
        if "helyis" in text or "room" in text:
            needles.append("room")
        return list(dict.fromkeys(needles))

    def build_context(self, goal: str, human_hints: list[str] | None = None, recent_trace: list[RecentResearchStep] | None = None) -> ResearchContext:
        selected: dict[str, ContextConcept] = {}
        for needle in self._semantic_needles(goal):
            for concept in self.store.search_concepts(needle):
                selected[concept.concept] = ContextConcept(
                    concept=concept.concept, status=concept.status, confidence=concept.confidence,
                    evidence_kinds=sorted({item.kind for item in concept.evidence}),
                )
        manual: list[ManualFinding] = []
        seen: set[tuple[str, int, str]] = set()
        related_by_location: dict[tuple[str, int], set[str]] = {}
        for concept in selected:
            for evidence in self.store.get_concept_research_evidence(concept):
                related_by_location.setdefault((evidence.source_id, evidence.page), set()).update(evidence.related_concepts)
        for query in self._goal_terms(goal):
            for result in self.manual_index.search(query, limit=4):
                key = (result["source_id"], result["page"], result["excerpt"])
                if key not in seen:
                    seen.add(key)
                    manual.append(ManualFinding(
                        source_id=result["source_id"], page=result["page"], section=result.get("heading"), excerpt=result["excerpt"],
                        related_concepts=sorted(related_by_location.get((result["source_id"], result["page"]), set())),
                    ))
        concepts = list(selected.values())
        experiments: list[str] = []
        for concept in concepts:
            for hypothesis in self.store.get_concept_hypotheses(concept.concept):
                experiments.extend(hypothesis.experiment_ids)
        handlers = ["room.area_m2", "room.boundary.external_wall.x_m"]
        trace = (recent_trace or [])[-4:]
        latest = trace[-1] if trace else None
        allowed_types = {"Button", "TabItem", "ListItem", "ComboBox", "TreeItem", "MenuItem", "Edit"}
        actionable = [item for item in (latest.discovered_controls if latest else []) if item.enabled and item.control_type in allowed_types]
        navigation = self.navigation_store.retrieve(goal, current_state_fingerprint=latest.state_fingerprint if latest else None, semantic_context=latest.semantic_context if latest else "")
        return ResearchContext(
            goal=goal,
            verified_concepts=[item for item in concepts if item.status is KnowledgeStatus.VERIFIED],
            hypotheses=[item for item in concepts if item.status is KnowledgeStatus.HYPOTHESIS],
            rejected_hypotheses=[item for item in concepts if item.status is KnowledgeStatus.REJECTED],
            relevant_capabilities=concepts,
            manual_evidence=manual,
            previous_experiments=sorted(set(experiments)),
            known_safe_experiment_handlers=handlers,
            human_hints=[HumanResearchHint(text=item) for item in (human_hints or [])],
            navigational_targets=[NavigationalResearchTarget(path_hint=["Jegyzékek", "Szerkezetek"], target_semantics="global structure catalog / structure creation") for item in (human_hints or []) if "jegyz" in item.casefold() and "szerkezet" in item.casefold()],
            recent_research_trace=trace,
            current_window=latest.resulting_window if latest else None,
            current_state_fingerprint=latest.state_fingerprint if latest else None,
            recently_activated_control=latest.recently_activated_control if latest else None,
            actionable_controls=actionable,
            known_safe_navigation_capabilities=navigation.known_safe_navigation_capabilities,
            navigation_knowledge=navigation,
        )

    def _validate_plan(self, plan: ResearchPlan, context: ResearchContext, goal: str) -> ResearchPlan:
        verified = {item.concept for item in context.verified_concepts}
        hypotheses = {item.concept for item in context.hypotheses}
        invalid_verified_claims = sorted(set(plan.known_verified) - verified)
        if invalid_verified_claims:
            raise ValueError(
                "planner attempted to claim knowledge not verified in the retrieved context; "
                f"retrieved_verified_concepts={sorted(verified)}; "
                f"planner_known_verified={plan.known_verified}; "
                f"invalid_verified_claims={invalid_verified_claims}"
            )
        invalid_hypothesis_claims = sorted(set(plan.hypotheses) - hypotheses)
        if invalid_hypothesis_claims:
            raise ValueError(
                "planner claimed a hypothesis absent from the retrieved context; "
                f"retrieved_hypothesis_concepts={sorted(hypotheses)}; "
                f"planner_hypotheses={plan.hypotheses}; "
                f"invalid_hypothesis_claims={invalid_hypothesis_claims}"
            )
        proposal = plan.proposed_experiment
        if plan.research_step_type == "experiment":
            if proposal is None or proposal.experiment_status != "supported" or proposal.spec is None:
                raise ValueError("experiment research step requires a supported, valid ExperimentSpec")
            if proposal.spec.target_capability not in context.known_safe_experiment_handlers:
                raise ValueError("planner proposed an experiment without an approved semantic handler")
        elif proposal is not None:
            raise ValueError("only an experiment research step may include a proposed experiment")
        return plan

    @staticmethod
    def _candidate_to_plan(candidate: CandidateResearchPlan, requested_goal: str) -> ResearchPlan:
        """Convert LLM output to strict local types before any planner validation.

        Candidate observation strings remain in the candidate/audit unless the existing
        ExperimentSpec schema accepts every one of them.
        """
        try:
            step_type = candidate.research_step_type
            # UI navigation is a planner-facing classification only.  It is
            # executable solely through the separately validated identity
            # action, so it maps to the existing non-experiment plan type.
            if step_type in {"ui_navigation", "ui_action"} and candidate.ui_action is not None:
                step_type = "capability_enumeration"
            if step_type not in {"documentation_research", "capability_enumeration", "experiment", "human_question", "unsupported"}:
                raise ValueError(f"unsupported research_step_type={step_type!r}")
            proposal = None
            if step_type == "experiment":
                candidate_proposal = candidate.proposed_experiment
                if candidate_proposal is None:
                    raise ValueError("experiment research step has no candidate proposed_experiment")
                if candidate_proposal.experiment_status != "supported":
                    raise ValueError(f"experiment research step is not supported: {candidate_proposal.experiment_status!r}")
                if candidate_proposal.spec is None:
                    raise ValueError("experiment research step has no candidate ExperimentSpec")
                try:
                    spec = ExperimentSpec.model_validate(candidate_proposal.spec.model_dump(mode="json", by_alias=True))
                except ValidationError as exc:
                    requested = candidate_proposal.spec.observe
                    raise ValueError(
                        "candidate ExperimentSpec rejected by deterministic allowlist; "
                        f"requested_observe_operations={requested}; errors={exc.errors(include_url=False)}"
                    ) from exc
                proposal = ProposedExperiment(
                    experiment_status="supported", reason=candidate_proposal.reason,
                    missing_capability=candidate_proposal.missing_capability, spec=spec,
                )
            elif candidate.proposed_experiment is not None:
                raise ValueError("non-experiment research step included an irrelevant candidate experiment")
            return ResearchPlan(
                goal=requested_goal, interpreted_scope=candidate.interpreted_scope,
                known_verified=candidate.known_verified, manual_supported=candidate.manual_supported,
                hypotheses=candidate.hypotheses, unknowns=candidate.unknowns,
                recommended_next_target=candidate.recommended_next_target,
                reasoning_summary=candidate.reasoning_summary, research_step_type=step_type,
                discovery=(CapabilityDiscovery(
                    boundary_types=candidate.discovery.boundary_types,
                    workflows=candidate.discovery.workflows,
                    common_fields=candidate.discovery.common_fields,
                    type_specific_fields={item.structure_type: item.fields for item in candidate.discovery.type_specific_fields},
                    capability_candidates=candidate.discovery.capability_candidates,
                ) if candidate.discovery else None), proposed_hypothesis=candidate.proposed_hypothesis,
                proposed_experiment=proposal, needs_human_input=candidate.needs_human_input,
                human_question=candidate.human_question, ui_action=candidate.ui_action,
            )
        except (ValidationError, ValueError) as exc:
            raise ValueError(str(exc)) from exc

    def plan(self, goal: str, human_hints: list[str] | None = None, recent_trace: list[RecentResearchStep] | None = None) -> PlannerResult:
        context = self.build_context(goal, human_hints, recent_trace)
        verified_ids = [item.concept for item in context.verified_concepts]
        hypothesis_ids = [item.concept for item in context.hypotheses]
        instructions = "\n\n".join([
            SYSTEM_PROMPT,
            "KNOWN_VERIFIED: Only copy exact concept identifiers from allowed_verified_concepts. "
            "Never infer that a related or parent concept is verified. For example, verification of "
            "room.boundary.external_wall.x_m does not verify room.boundary.external_wall, "
            "room.boundary.external_wall.dimensions, or any other identifier. known_verified must be "
            "a strict subset of allowed_verified_concepts.",
            "HYPOTHESES: Only copy exact identifiers from allowed_hypothesis_concepts. Do not invent "
            "or rename an existing hypothesis in the hypotheses list; use proposed_hypothesis for a new suggestion.",
            "GOAL: The caller-supplied requested goal is authoritative and immutable. The goal field is "
            "only a non-authoritative echo and will be canonicalized by the caller. Put your natural-language "
            "interpretation only in interpreted_scope.",
            "HUMAN_HINTS are non-verified leads, not facts. Use them only to prioritize inspection; observed UI may contradict them.",
            "RECENT_UI_TRACE contains discovered controls. Do not repeat inspect_ui on an unchanged state. Choose a different safe action from those controls when relevant.",
            "UI ACTIONS: activate_control, select_list_item, and set_control_value may use only an exact identity in actionable_controls. "
            "set_control_value is sandbox-only and only valid for an enabled Edit control. Its value must start with AI_TEST_ and is a dummy probe, never a claimed field meaning. "
            "When actionable_controls contains a control relevant to the human navigation target/current goal, prioritize it over old scoped discovery tools. "
            "Do not invent an identity. inspect_ui has no identity.",
            "KNOWN SAFE NAVIGATION: open_known_navigation may use only an exact capability in "
            "known_safe_navigation_capabilities. It is a sandbox-only, deterministic navigation handler.",
            f"allowed_verified_concepts = {json.dumps(verified_ids, ensure_ascii=False)}",
            f"allowed_hypothesis_concepts = {json.dumps(hypothesis_ids, ensure_ascii=False)}",
            f"available_safe_ui_actions = {json.dumps([item.model_dump(mode='json') for item in context.actionable_controls], ensure_ascii=False)}",
            f"known_safe_navigation_capabilities = {json.dumps(context.known_safe_navigation_capabilities, ensure_ascii=False)}",
            f"relevant_navigation_knowledge = {json.dumps(context.navigation_knowledge.model_dump(mode='json'), ensure_ascii=False)}",
        ])
        input_text = json.dumps({"goal": goal, "research_context": context.model_dump(mode="json")}, ensure_ascii=False)
        candidate, raw = self.provider.generate_structured(
            instructions=instructions, input_text=input_text, response_model=CandidateResearchPlan,
        )
        audit = PlannerAudit(
            prompt_version=PROMPT_VERSION, instructions=instructions, provider=self.provider.provider_name, model=self.provider.model,
            context=context, raw_response=raw,
        )
        try:
            plan = self._candidate_to_plan(candidate, goal)
            plan = self._validate_plan(plan, context, goal)
        except ValueError as exc:
            raise ResearchPlanValidationError(str(exc), PlannerValidationFailure(
                validation_error=str(exc), parsed_candidate_plan=candidate,
                parsed_plan=locals().get("plan"), audit=audit,
            )) from exc
        return PlannerResult(plan=plan, audit=audit)

    @staticmethod
    def save_audit(result: PlannerResult, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def save_failure(failure: PlannerValidationFailure, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(failure.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return path
