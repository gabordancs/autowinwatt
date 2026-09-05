"""Bounded autonomous research orchestration over existing safe components.

This module deliberately has no raw UIA, mouse, keyboard or coordinate API.
It selects only named actions implemented by the planner/manual/discovery/
experiment boundaries and records why an unsupported next action cannot run.
"""
from __future__ import annotations

import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from winwatt_automation.discovery.models import DiscoveryGoal
from winwatt_automation.discovery.runner import ResearchDiscoveryRunner
from winwatt_automation.experiments.runner import ExperimentRunner
from winwatt_automation.knowledge.models import EvidenceRef, Hypothesis
from winwatt_automation.knowledge.store import KnowledgeStore
from winwatt_automation.navigation.models import NavigationControlSummary
from winwatt_automation.navigation.store import NavigationKnowledgeStore
from winwatt_automation.planner.models import ResearchPlan
from winwatt_automation.planner.models import RecentDiscoveredControl, RecentResearchStep
from winwatt_automation.planner.planner import ResearchPlanValidationError, ResearchPlanner
from winwatt_automation.research.ui_readiness import recover_transient_ui_readiness, wait_for_ui_ready


ActionKind = Literal[
    "search_manual", "inspect_ui", "enumerate_controls", "enumerate_items", "inspect_dialog",
    "compare_ui_states", "run_discovery", "run_supported_experiment", "save_reopen_verify",
    "create_hypothesis", "ask_human", "stop",
    "activate_control", "select_list_item", "go_back",
    "set_control_value",
    "open_known_navigation",
]
Outcome = Literal["verified", "partially_learned", "blocked", "human_input_required", "budget_exhausted", "stalled_no_progress"]


class ResearchBudget(BaseModel):
    max_iterations: int = Field(default=12, ge=1, le=12)
    max_ui_actions: int = Field(default=120, ge=1, le=120)
    # This is only a runaway-process circuit breaker. Normal research is
    # bounded by progress/action/iteration safety rules, not a short clock.
    max_seconds: int = Field(default=1800, ge=60, le=1800)
    max_committing_experiments: int = Field(default=3, ge=0, le=3)
    max_no_progress_iterations: int = Field(default=3, ge=1, le=6)
    max_frontier_replans: int = Field(default=3, ge=1, le=6)
    provider_timeout_seconds: float = Field(default=180.0, ge=10.0, le=300.0)


class ResearchAction(BaseModel):
    kind: ActionKind
    semantic_context: str
    reasoning_summary: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    action_source: Literal["persistent_navigation_knowledge", "planner", "deterministic_bootstrap", "human"] = "planner"


class CapabilityGap(BaseModel):
    semantic_context: str
    missing_primitive: str
    reason: str
    suggested_evidence: list[str] = Field(default_factory=list)


class UIStateCatalogRecord(BaseModel):
    """Session-local catalog of a post-action UI state."""
    state_fingerprint: str
    window: str
    title: str
    discovered_controls: list[RecentDiscoveredControl] = Field(default_factory=list)
    inspected_at: datetime
    iteration: int
    source_action: str
    known: bool = False


def catalog_new_ui_state(
    registry: dict[str, UIStateCatalogRecord], snapshot: Any, *, iteration: int,
    source_action: str, semantic_context: str, context: str | None = None,
) -> tuple[bool, RecentResearchStep]:
    """Catalog a result state once; reusable by every navigation family."""
    fingerprint = str(snapshot.state_fingerprint)
    controls = [RecentDiscoveredControl(identity=item.identity, caption=item.caption, control_type=item.control_type, enabled=item.enabled) for item in snapshot.controls[:200]]
    known = fingerprint in registry
    if not known:
        registry[fingerprint] = UIStateCatalogRecord(
            state_fingerprint=fingerprint, window=context or snapshot.class_name, title=snapshot.title,
            discovered_controls=controls, inspected_at=datetime.now(timezone.utc), iteration=iteration,
            source_action=source_action,
        )
    return (not known, RecentResearchStep(
        action="auto_inspect", semantic_context=semantic_context, resulting_window=context or snapshot.class_name,
        state_fingerprint=fingerprint, discovered_controls=controls, state_change=not known,
    ))


def select_safe_anonymous_control(
    trace: list[RecentResearchStep], attempted: set[tuple[str, str]],
) -> RecentDiscoveredControl | None:
    """Pick one bounded sandbox probe from *observed* anonymous controls.

    This deliberately knows nothing about a WinWatt caption, menu ordinal, or
    workflow.  It only turns an already observed, enabled MenuItem with no
    accessible name into a single effect-based research probe.  The explorer
    performs the final live safety check and sandbox enforcement.
    """
    if not trace:
        return None
    latest = trace[-1]
    for control in latest.discovered_controls:
        key = (latest.state_fingerprint or "", control.identity)
        if (
            not control.caption
            and control.enabled
            and control.control_type == "MenuItem"
            and key not in attempted
        ):
            return control
    return None


class ResearchIteration(BaseModel):
    index: int
    current_goal: str
    selected_action: ResearchAction
    observations: list[dict[str, Any]] = Field(default_factory=list)
    evidence_created: list[EvidenceRef] = Field(default_factory=list)
    hypotheses_created: list[str] = Field(default_factory=list)
    capabilities_learned: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    remaining_unknowns: list[str] = Field(default_factory=list)
    capability_gap: CapabilityGap | None = None
    route_replay: dict[str, Any] | None = None


class ResearchSessionResult(BaseModel):
    session_id: str
    requested_goal: str
    outcome: Outcome
    iterations: list[ResearchIteration] = Field(default_factory=list)
    actions_taken: list[ResearchAction] = Field(default_factory=list)
    windows_visited: list[str] = Field(default_factory=list)
    evidence_created: list[EvidenceRef] = Field(default_factory=list)
    hypotheses_created: list[str] = Field(default_factory=list)
    capabilities_verified: list[str] = Field(default_factory=list)
    capabilities_rejected: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    final_summary: str
    started_at: datetime
    finished_at: datetime
    current_frontier_state: str | None = None
    explored_actions: list[str] = Field(default_factory=list)
    blocked_branches: list[str] = Field(default_factory=list)
    last_progress_iteration: int | None = None
    last_progress_reason: str | None = None


class ResearchOrchestrator:
    """Replan after every bounded action and fail closed at unsupported boundaries."""

    def __init__(
        self, planner: ResearchPlanner, store: KnowledgeStore, discovery_factory: Callable[[], ResearchDiscoveryRunner],
        experiment_runner: ExperimentRunner | None = None,
    ) -> None:
        self.planner = planner
        self.store = store
        self.discovery_factory = discovery_factory
        self.experiment_runner = experiment_runner

    @staticmethod
    def _action_for(plan: ResearchPlan) -> ResearchAction:
        if plan.ui_action is not None:
            parameters = {}
            if plan.ui_action.identity:
                parameters["identity"] = plan.ui_action.identity
            if plan.ui_action.value:
                parameters["value"] = plan.ui_action.value
            if plan.ui_action.capability:
                parameters["capability"] = plan.ui_action.capability
            return ResearchAction(kind=plan.ui_action.kind, semantic_context=plan.interpreted_scope, reasoning_summary="Planner-selected safe UI action", parameters=parameters)
        mapping: dict[str, ActionKind] = {
            "documentation_research": "search_manual", "capability_enumeration": "run_discovery",
            "experiment": "run_supported_experiment", "human_question": "ask_human", "unsupported": "stop",
        }
        return ResearchAction(kind=mapping[plan.research_step_type], semantic_context=plan.interpreted_scope, reasoning_summary=plan.reasoning_summary)

    def run(self, goal: str, *, source_project: Path, output_dir: Path, budget: ResearchBudget | None = None, human_hints: list[str] | None = None) -> ResearchSessionResult:
        budget = budget or ResearchBudget()
        started = datetime.now(timezone.utc)
        tick = time.monotonic()
        session_id = f"research_{uuid4().hex}"
        iterations: list[ResearchIteration] = []
        actions: list[ResearchAction] = []
        evidence: list[EvidenceRef] = []
        windows: list[str] = []
        hypotheses: list[str] = []
        verified: list[str] = []
        unresolved: list[str] = []
        recent_trace: list[RecentResearchStep] = []
        state_registry: dict[str, UIStateCatalogRecord] = {}
        navigation_store = NavigationKnowledgeStore()
        explorer = None
        seen_actions: set[tuple[str, str]] = set()
        attempted_anonymous_controls: set[tuple[str, str]] = set()
        blocked_persistent_transitions: set[str] = set()
        blocked_branches: set[str] = set()
        explored_effects: set[tuple[str, str, str]] = set()
        no_progress_count = 0
        last_progress_iteration: int | None = None
        last_progress_reason: str | None = None
        current_frontier: str | None = None
        outcome: Outcome = "budget_exhausted"
        summary = "Research budget exhausted before a conclusive result."

        def ensure_explorer() -> Any:
            nonlocal explorer
            if explorer is None:
                from winwatt_automation.live_ui.app_connector import get_main_window
                from winwatt_automation.research.ui_exploration import SandboxUIExplorer
                from winwatt_automation.services.winwatt_service import WinWattService
                sandbox = output_dir / session_id / "sandbox" / source_project.name
                service = WinWattService()
                service.create_sandbox(source_project, sandbox)
                service.open_project(sandbox)
                explorer = SandboxUIExplorer(get_main_window(), sandbox)
            return explorer

        def catalog_post_action_state(snapshot: Any, *, source_action: ResearchAction, iteration: ResearchIteration, context: str | None = None) -> bool:
            """Invariant: a new result state is inspected before replanning."""
            triggered, step = catalog_new_ui_state(
                state_registry, snapshot, iteration=iteration.index, source_action=source_action.kind,
                semantic_context=source_action.semantic_context, context=context,
            )
            step.recently_activated_control = source_action.parameters.get("identity") or source_action.parameters.get("capability")
            if triggered:
                recent_trace.append(step)
            iteration.observations.append({
                "post_action_state": {
                    "state_fingerprint": step.state_fingerprint, "window": context or snapshot.class_name,
                    "title": snapshot.title, "known": not triggered, "auto_inspect_triggered": triggered,
                    "discovered_control_count": len(step.discovered_controls), "source_action": source_action.kind,
                }
            })
            return triggered

        def persist_navigation_transition(before: Any, after: Any, action: ResearchAction, *, context: str | None = None, deterministic: bool = False) -> bool:
            """Persist only an actually executed before → action → after edge."""
            to_controls = [NavigationControlSummary(identity=item.identity, caption=item.caption, control_type=item.control_type, enabled=item.enabled) for item in after.controls]
            from_controls = [NavigationControlSummary(identity=item.identity, caption=item.caption, control_type=item.control_type, enabled=item.enabled) for item in before.controls]
            source = navigation_store.upsert_state(before.state_fingerprint, before.class_name, before.title, from_controls, "research_session")
            target = navigation_store.upsert_state(after.state_fingerprint, after.class_name, after.title, to_controls, "research_session", mdi_title=context, semantic_context=action.semantic_context)
            transition = navigation_store.upsert_transition(
                source.id, action.kind, target.id,
                action_identity=action.parameters.get("identity"), capability=action.parameters.get("capability"),
                semantic_action=action.semantic_context, expected_state=after.state_fingerprint,
                status="verified" if deterministic else "observed",
                evidence=EvidenceRef(kind="research_ui_transition", description="Executed UI action produced observed result state", deterministic=deterministic),
            )
            return navigation_store.mark_replay(transition.id, after.state_fingerprint)

        def progress(iteration: ResearchIteration, reason: str, *, frontier: str | None = None) -> None:
            """Record a meaningful novelty; a slow successful step is valid progress."""
            nonlocal no_progress_count, last_progress_iteration, last_progress_reason, current_frontier
            no_progress_count = 0
            last_progress_iteration, last_progress_reason = iteration.index, reason
            if frontier:
                current_frontier = frontier
            iteration.observations.append({"progress": {"meaningful": True, "reason": reason, "last_progress_iteration": iteration.index}})

        def no_progress(iteration: ResearchIteration, state: str | None, action: ResearchAction, effect: str = "unchanged") -> bool:
            """Stop quickly only when the frontier is demonstrably no longer changing."""
            nonlocal no_progress_count, outcome, summary, current_frontier
            current_frontier = state or current_frontier
            signature = (state or "", action.kind, f"{action.parameters.get('identity') or action.parameters.get('capability') or ''}:{effect}")
            repeated = signature in explored_effects
            explored_effects.add(signature)
            no_progress_count += 1
            iteration.observations.append({"progress": {"meaningful": False, "same_state_count": no_progress_count, "repeated_action": repeated, "frontier": state, "effect": effect, "last_progress_iteration": last_progress_iteration, "last_progress_reason": last_progress_reason}})
            if no_progress_count >= budget.max_no_progress_iterations:
                blocked_branches.add("|".join(signature))
                iteration.failures.append("stalled_no_progress")
                outcome = "stalled_no_progress"
                summary = f"stalled_no_progress: {no_progress_count} consecutive iterations at an unchanged frontier."
                return True
            return False

        for index in range(1, budget.max_iterations + 1):
            if time.monotonic() - tick >= budget.max_seconds:
                unresolved.append("Emergency runaway-process deadline exhausted")
                outcome, summary = "blocked", "emergency_deadline_exceeded: normal stopping is progress-based."
                break
            # Known path -> program replays. Unknown frontier -> planner reasons.
            # An initial probe is needed only to bind the persisted route to the
            # current sandbox state; it is not an LLM decision.
            replayable_exists = any(edge.status in {"verified", "replayed"} for edge in navigation_store.transitions())
            # The sole normal state-acquisition path. No planner call may
            # precede it, even where no persistent route exists.
            readiness, current_snapshot = wait_for_ui_ready(ensure_explorer())
            recovery_audit = None
            if not readiness.ready and readiness.reason == "ui_not_ready:unstable":
                readiness, current_snapshot, recovery = recover_transient_ui_readiness(ensure_explorer())
                recovery_audit = recovery.model_dump(mode="json")
            if not readiness.ready or current_snapshot is None:
                action = ResearchAction(kind="stop", semantic_context="ui readiness", reasoning_summary="UI readiness gate blocked navigation", action_source="deterministic_bootstrap")
                iteration = ResearchIteration(index=index, current_goal=goal, selected_action=action, failures=[readiness.reason])
                iteration.observations.append({"iteration_start": {"ui_readiness_entered": True, "ui_readiness_ready": False, "ui_readiness_reason": readiness.reason, "persistent_route_lookup_attempted": False, "planner_called": False, "recovery": recovery_audit, "action_preceding_instability": recent_trace[-1].action if recent_trace else None}})
                iterations.append(iteration); actions.append(action)
                outcome, summary = "blocked", ("ui_readiness_recovery_exhausted" if recovery_audit else "ui_not_ready") + ": no stable non-empty UIA state; planner was not called."
                break
            if recovery_audit:
                # Recovery is deliberately not an iteration/action/progress;
                # it only restores a stable snapshot of the same frontier.
                current_frontier = current_snapshot.state_fingerprint
            if replayable_exists:
                    # A freshly opened Delphi MDI main form can expose an
                    # empty transient UIA tree for a moment.  Bind replay to
                    # the settled state, not that startup transient.
                    route = navigation_store.executable_route(goal, current_snapshot.state_fingerprint, exclude_transition_ids=blocked_persistent_transitions)
                    if route is not None:
                        edge = route.transitions[0]
                        # Navigation transports are executor-private. The
                        # orchestrator vocabulary carries only the semantic
                        # capability, never e.g. ``native_menu_ordinal``.
                        research_kind: ActionKind = edge.action_kind if edge.action_kind in {"activate_control", "select_list_item"} else "open_known_navigation"
                        action = ResearchAction(
                            kind=research_kind, semantic_context=edge.capability or edge.action_kind,
                            reasoning_summary="Deterministic replay of persistent navigation evidence",
                            parameters={key: value for key, value in {"identity": edge.action_identity, "capability": edge.capability, "transition_id": edge.transition_id}.items() if value},
                            action_source="persistent_navigation_knowledge",
                        )
                        iteration = ResearchIteration(index=index, current_goal=goal, selected_action=action)
                        before = current_snapshot
                        if edge.action_kind in {"activate_control", "select_list_item"} and edge.action_identity:
                            executed = explorer.activate_control(edge.action_identity, index)
                        elif edge.action_kind in {"open_known_navigation", "native_menu_ordinal"} and edge.capability == "catalog.structure.open":
                            from winwatt_automation.runtime_mapping.mdi_state_model import activate_structures_catalog_native
                            from winwatt_automation.runtime_mapping.mdi_state_model import active_mdi_title
                            activate_structures_catalog_native()
                            executed = None
                        else:
                            iteration.failures.append("Persistent route has no registered safe executor.")
                            blocked_persistent_transitions.add(edge.transition_id)
                            iteration.observations.append({"persistent_route_blocked": {"transition_id": edge.transition_id, "reason": "no_registered_safe_executor", "stale": False}})
                            iterations.append(iteration); actions.append(action)
                            continue
                        after = explorer.inspect_window()
                        expected_postcondition = next((ref.data.get("expected_postcondition") for ref in edge.evidence_refs if ref.data.get("expected_postcondition")), None)
                        observed_postcondition = None
                        verification_kind = "state_fingerprint"
                        if edge.action_kind == "native_menu_ordinal" and expected_postcondition is not None:
                            verification_kind = "semantic_postcondition"
                            observed_postcondition = {"active_mdi_title": active_mdi_title()}
                            runtime_match = observed_postcondition == expected_postcondition
                            navigation_store.mark_semantic_replay(edge.transition_id, runtime_match)
                        else:
                            runtime_match = after.state_fingerprint == edge.expected_state
                            navigation_store.mark_replay(edge.transition_id, after.state_fingerprint)
                        iteration.route_replay = {
                            "source": "persistent_navigation_knowledge", "route_id": route.route_id,
                            "transition_id": edge.transition_id, "retrieval_score": route.goal_relevance,
                            "status_before": edge.status, "from_state": before.state_fingerprint,
                            "expected_state": edge.expected_state, "observed_state": after.state_fingerprint,
                            "verification_kind": verification_kind, "expected_postcondition": expected_postcondition,
                            "observed_postcondition": observed_postcondition,
                            "runtime_match": runtime_match,
                            "status_after": next(item.status for item in navigation_store.transitions() if item.id == edge.transition_id),
                        }
                        iteration.observations.append({"before": before.model_dump(mode="json"), "after": after.model_dump(mode="json"), "action_source": action.action_source})
                        if runtime_match:
                            was_new = catalog_post_action_state(after, source_action=action, iteration=iteration)
                            progress(iteration, "known_transition_replayed_to_new_frontier" if was_new else "known_transition_replayed", frontier=after.state_fingerprint)
                            actions.append(action); iterations.append(iteration); evidence.extend(iteration.evidence_created)
                            continue
                        iteration.failures.append("Persistent route mismatch; edge marked stale and replay aborted.")
                        actions.append(action); iterations.append(iteration); evidence.extend(iteration.evidence_created)
                        # Current observed state becomes the safe frontier for the next planner cycle.
                        recent_trace.append(RecentResearchStep(action="route_stale", semantic_context=action.semantic_context, resulting_window=after.class_name, state_fingerprint=after.state_fingerprint, state_change=True))
            try:
                planned = self._timed_step("planner/provider call", budget.provider_timeout_seconds, lambda: self.planner.plan(goal, human_hints, recent_trace[-4:])).plan
            except TimeoutError as exc:
                action = ResearchAction(kind="stop", semantic_context=goal, reasoning_summary="Provider call timed out")
                iteration = ResearchIteration(index=index, current_goal=goal, selected_action=action, failures=["provider_timeout", str(exc)])
                iterations.append(iteration); actions.append(action)
                outcome, summary = "blocked", "provider_timeout: planner did not return before its independent timeout."
                break
            except RuntimeError as exc:
                # A missing optional LLM provider must not force unsafe desktop
                # fallback. Use the smallest existing, controlled discovery
                # action and preserve the provider gap in the audit.
                planned = ResearchPlan(
                    goal=goal, interpreted_scope=goal, known_verified=[], manual_supported=[], hypotheses=[],
                    unknowns=["LLM planner unavailable", "structure-creation UI route is not yet discovered"],
                    recommended_next_target="room.boundary.structure_reference", reasoning_summary=f"Deterministic fallback after planner unavailability: {exc}",
                    research_step_type="capability_enumeration",
                )
            except ResearchPlanValidationError as exc:
                gap = CapabilityGap(semantic_context=goal, missing_primitive="validated_research_plan", reason=str(exc), suggested_evidence=["Correct the fail-closed planner output before UI execution."])
                action = ResearchAction(kind="stop", semantic_context=goal, reasoning_summary="Planner validation failed")
                iteration = ResearchIteration(index=index, current_goal=goal, selected_action=action, failures=[str(exc)], capability_gap=gap)
                iterations.append(iteration); actions.append(action); unresolved.append(gap.reason)
                outcome, summary = "blocked", "Planner output failed deterministic validation; no UI action was attempted."
                break
            action = self._action_for(planned)
            # A blank owner-drawn label is insufficient reason to ask a human
            # or abandon research.  On an observed sandbox frontier, prefer a
            # single identity-based, effect-only probe to an unrelated legacy
            # discovery routine.  Its meaning is learned from the UI diff;
            # it never becomes verified merely because it changed state.
            anonymous = select_safe_anonymous_control(recent_trace, attempted_anonymous_controls)
            if action.kind == "run_discovery" and anonymous is not None:
                action = ResearchAction(
                    kind="activate_control",
                    semantic_context=action.semantic_context,
                    reasoning_summary="Bounded effect-based exploration of an observed anonymous sandbox control",
                    parameters={"identity": anonymous.identity, "anonymous_effect_probe": True},
                    action_source="deterministic_bootstrap",
                )
            global_structure_target = any("jegyz" in item.casefold() and "szerkezet" in item.casefold() for item in (human_hints or []))
            if global_structure_target and action.kind == "run_discovery" and not recent_trace:
                # The only current special discovery is declared scope
                # room.boundary.assignment, so it is irrelevant here.
                action = ResearchAction(kind="inspect_ui", semantic_context="global structure catalog / structure creation", reasoning_summary="Human navigation target requires main-window inspection before any scoped discovery.")
            elif global_structure_target and action.kind == "run_discovery" and recent_trace:
                # Legacy room-boundary discovery has the wrong declared scope
                # for a global catalogue frontier. It is rejected below by
                # the general, bounded frontier-replanning policy.
                pass
            # Revalidate deterministic probes as well as provider-selected
            # actions.  The only authority for an anonymous identity is the
            # current session's observed UI trace.
            def rejection_reason(candidate: ResearchAction) -> str | None:
                controls = [item for step in recent_trace for item in step.discovered_controls]
                if candidate.kind in {"activate_control", "select_list_item", "set_control_value"}:
                    match = next((item for item in controls if item.identity == candidate.parameters.get("identity")), None)
                    valid_input = candidate.kind != "set_control_value" or (match is not None and match.control_type == "Edit" and str(candidate.parameters.get("value", "")).startswith("AI_TEST_"))
                    if match is None or not match.enabled or match.control_type not in {"Button", "TabItem", "ListItem", "ComboBox", "TreeItem", "MenuItem", "Edit"} or not valid_input:
                        return "identity_not_observed_enabled_or_allowed"
                if global_structure_target and recent_trace and candidate.kind == "run_discovery":
                    return "irrelevant_scoped_discovery_at_current_frontier"
                return None

            frontier = current_snapshot.state_fingerprint
            rejected_here: set[str] = set()
            for replan_attempt in range(budget.max_frontier_replans + 1):
                reason = rejection_reason(action)
                action_key = f"{action.kind}:{action.parameters.get('identity') or action.parameters.get('capability') or ''}"
                if reason is None and action_key not in rejected_here:
                    break
                rejected_here.add(action_key)
                blocked_branches.add(f"{frontier}|{action_key}|{reason or 'repeated_rejected_action'}")
                if replan_attempt >= budget.max_frontier_replans:
                    iteration = ResearchIteration(index=index, current_goal=goal, selected_action=ResearchAction(kind="stop", semantic_context=action.semantic_context, reasoning_summary="stalled_no_valid_action"), failures=["stalled_no_valid_action"], remaining_unknowns=planned.unknowns)
                    iteration.observations.append({"frontier": {"state_fingerprint": frontier, "rejected_actions": sorted(rejected_here), "replan_attempts": replan_attempt, "reason": reason}})
                    iterations.append(iteration); actions.append(iteration.selected_action)
                    outcome, summary = "stalled_no_progress", "stalled_no_valid_action: bounded frontier replans produced no valid action."
                    break
                feedback = f"Deterministic frontier feedback: your action {action_key!r} was rejected because {reason or 'it was already rejected at this unchanged frontier'}. Choose a different exact observed safe action; rejected_actions={sorted(rejected_here)}."
                try:
                    planned = self._timed_step("planner/provider frontier replan", budget.provider_timeout_seconds, lambda: self.planner.plan(goal, (human_hints or []) + [feedback], recent_trace[-4:])).plan
                    action = self._action_for(planned)
                except TimeoutError as exc:
                    iteration = ResearchIteration(index=index, current_goal=goal, selected_action=ResearchAction(kind="stop", semantic_context=goal, reasoning_summary="Provider frontier replan timed out"), failures=["provider_timeout", str(exc)])
                    iterations.append(iteration); actions.append(iteration.selected_action)
                    outcome, summary = "blocked", "provider_timeout: frontier replan did not return."
                    break
            else:
                continue
            if outcome in {"blocked", "stalled_no_progress"} and iterations and iterations[-1].index == index:
                break
            if recent_trace and action.kind == "inspect_ui" and recent_trace[-1].action == "inspect_ui" and recent_trace[-1].discovered_controls:
                gap = CapabilityGap(semantic_context=action.semantic_context, missing_primitive="planner_stuck", reason="inspect_ui was already executed on this unchanged state and produced actionable discovered controls.", suggested_evidence=["Choose a different safe action using only identities from the recent observation."])
                iteration = ResearchIteration(index=index, current_goal=goal, selected_action=ResearchAction(kind="stop", semantic_context=action.semantic_context, reasoning_summary="Repeated unchanged inspection rejected"), remaining_unknowns=planned.unknowns, capability_gap=gap)
                iterations.append(iteration); actions.append(iteration.selected_action); unresolved.append(gap.reason)
                outcome, summary = "partially_learned", "Repeated inspect on unchanged state was rejected deterministically."
                break
            signature = (current_snapshot.state_fingerprint, f"{action.kind}:{action.parameters.get('identity') or action.parameters.get('capability') or planned.recommended_next_target}")
            if signature in seen_actions:
                gap = CapabilityGap(semantic_context=planned.interpreted_scope, missing_primitive="next_distinct_research_action", reason="Planner repeated the same bounded action after new evidence.", suggested_evidence=["Add a controlled discovery primitive for the identified UI gap."])
                iteration = ResearchIteration(index=index, current_goal=goal, selected_action=ResearchAction(kind="stop", semantic_context=action.semantic_context, reasoning_summary="Repeated action guard"), remaining_unknowns=planned.unknowns, capability_gap=gap)
                iterations.append(iteration); actions.append(iteration.selected_action); unresolved.extend(planned.unknowns + [gap.reason])
                outcome, summary = "partially_learned", "Bounded evidence was collected; replanning repeated an action, so the session stopped safely."
                break
            seen_actions.add(signature)
            iteration = ResearchIteration(index=index, current_goal=goal, selected_action=action, remaining_unknowns=planned.unknowns)
            actions.append(action)
            if planned.proposed_hypothesis and self.store.get_hypothesis(f"session_{session_id}_{index}") is None:
                hypothesis = Hypothesis(hypothesis_id=f"session_{session_id}_{index}", target_capability=planned.proposed_hypothesis.target_capability, semantic_guess=planned.proposed_hypothesis.semantic_guess, confidence=planned.proposed_hypothesis.confidence)
                self.store.store_hypothesis(hypothesis)
                iteration.hypotheses_created.append(hypothesis.hypothesis_id); hypotheses.append(hypothesis.hypothesis_id)
            if action.kind == "search_manual":
                findings = self.planner.manual_index.search(goal, limit=5)
                iteration.observations.extend(findings)
                iteration.evidence_created.append(EvidenceRef(kind="manual_search", description="Manual search used for research planning", deterministic=False, data={"result_count": len(findings)}))
            elif action.kind == "inspect_ui":
                # Start at the sandbox main window. This is intentionally not a
                # room-boundary route and exposes only an observation snapshot.
                from winwatt_automation.live_ui.app_connector import get_main_window
                from winwatt_automation.research.ui_exploration import SandboxUIExplorer
                from winwatt_automation.services.winwatt_service import WinWattService
                if explorer is None:
                    sandbox = output_dir / session_id / "sandbox" / source_project.name
                    WinWattService().create_sandbox(source_project, sandbox)
                    WinWattService().open_project(sandbox)
                    explorer = SandboxUIExplorer(get_main_window(), sandbox)
                snapshot = current_snapshot
                iteration.observations.append(snapshot.model_dump(mode="json"))
                iteration.evidence_created.append(EvidenceRef(kind="ui_exploration", description="Inspected sandbox WinWatt main window", deterministic=False, data={"window": snapshot.identity, "title": snapshot.title, "controls": len(snapshot.controls)}))
                windows.append(snapshot.class_name)
                recent_trace.append(RecentResearchStep(
                    action="inspect_ui", semantic_context=action.semantic_context, resulting_window=snapshot.class_name,
                    discovered_controls=[RecentDiscoveredControl(identity=item.identity, caption=item.caption, control_type=item.control_type, enabled=item.enabled) for item in snapshot.controls[:40]],
                    state_change=True, state_fingerprint=snapshot.state_fingerprint,
                ))
                state_registry.setdefault(snapshot.state_fingerprint, UIStateCatalogRecord(
                    state_fingerprint=snapshot.state_fingerprint, window=snapshot.class_name, title=snapshot.title,
                    discovered_controls=recent_trace[-1].discovered_controls, inspected_at=datetime.now(timezone.utc),
                    iteration=index, source_action="inspect_ui",
                ))
                if snapshot.state_fingerprint != current_frontier:
                    progress(iteration, "new_ui_state_inspected", frontier=snapshot.state_fingerprint)
                elif no_progress(iteration, snapshot.state_fingerprint, action):
                    iterations.append(iteration); break
            elif action.kind == "open_known_navigation":
                capability = action.parameters.get("capability")
                available_navigation = self.planner.navigation_store.retrieve(goal, semantic_context=action.semantic_context).known_safe_navigation_capabilities
                if capability not in available_navigation:
                    raise RuntimeError("Unknown or unapproved navigation capability")
                if capability != "catalog.structure.open":
                    raise RuntimeError("No deterministic executor is registered for the retrieved navigation capability")
                from winwatt_automation.runtime_mapping.mdi_state_model import activate_structures_catalog_native, capture_active_mdi_state
                from winwatt_automation.live_ui.app_connector import get_main_window
                from winwatt_automation.research.ui_exploration import SandboxUIExplorer
                from winwatt_automation.services.winwatt_service import WinWattService
                # This semantic navigation action is self-contained: unlike an
                # identity action it may be the first selected action, so it
                # must establish its own disposable WinWatt session first.
                if explorer is None:
                    sandbox = output_dir / session_id / "sandbox" / source_project.name
                    service = WinWattService()
                    service.create_sandbox(source_project, sandbox)
                    service.open_project(sandbox)
                    explorer = SandboxUIExplorer(get_main_window(), sandbox)
                before_navigation = explorer.inspect_window()
                opened = activate_structures_catalog_native()
                state = capture_active_mdi_state(output_dir=(output_dir / session_id / "mdi_states").resolve())
                iteration.observations.append({"navigation": opened, "before_state_fingerprint": before_navigation.state_fingerprint, "state_id": state["state_id"], "active_mdi_title": state["active_mdi_title"]})
                iteration.evidence_created.append(EvidenceRef(kind="native_catalog_navigation", description="Opened mapped Szerkezetek catalogue and verified active MDI title", deterministic=True, data=opened))
                windows.append(state["active_mdi_title"])
                # General post-action observation: the navigation result is
                # catalogued now, before the next planner call.
                after_navigation = explorer.inspect_window()
                replay_ok = persist_navigation_transition(before_navigation, after_navigation, action, context=state["active_mdi_title"], deterministic=True)
                if not replay_ok:
                    iteration.failures.append("Navigation replay expected-state mismatch; route marked stale and replay stopped.")
                    outcome, summary = "partially_learned", "Known navigation route mismatched its expected state and was marked stale."
                    iterations.append(iteration)
                    break
                catalog_post_action_state(after_navigation, source_action=action, iteration=iteration, context=state["active_mdi_title"])
                progress(iteration, "known_navigation_replayed", frontier=after_navigation.state_fingerprint)
            elif action.kind in {"activate_control", "select_list_item", "set_control_value"}:
                if explorer is None:
                    raise RuntimeError("identity action requested before a sandbox UI inspection")
                before = explorer.inspect_window()
                if action.parameters.get("anonymous_effect_probe"):
                    attempted_anonymous_controls.add((before.state_fingerprint, action.parameters["identity"]))
                executed = (explorer.set_control_value(action.parameters["identity"], action.parameters["value"], index)
                            if action.kind == "set_control_value"
                            else explorer.activate_control(action.parameters["identity"], index))
                after = explorer.inspect_window()
                iteration.observations.append({"before": before.model_dump(mode="json"), "after": after.model_dump(mode="json"), "executed_action": executed.model_dump(mode="json")})
                iteration.evidence_created.extend(executed.evidence_refs)
                changed = before.identity != after.identity or {item.identity for item in before.controls} != {item.identity for item in after.controls}
                if changed:
                    persist_navigation_transition(before, after, action, context=action.semantic_context)
                    catalog_post_action_state(after, source_action=action, iteration=iteration)
                    progress(iteration, "new_control_effect_observed", frontier=after.state_fingerprint)
                else:
                    recent_trace.append(RecentResearchStep(action=action.kind, semantic_context=action.semantic_context, resulting_window=after.class_name, state_fingerprint=after.state_fingerprint, discovered_controls=[RecentDiscoveredControl(identity=item.identity, caption=item.caption, control_type=item.control_type, enabled=item.enabled) for item in after.controls[:40]], state_change=False, failures=[executed.failure] if executed.failure else []))
                    if no_progress(iteration, after.state_fingerprint, action):
                        iterations.append(iteration); break
            elif action.kind == "run_discovery":
                runner = self.discovery_factory()
                discovery = runner.run(DiscoveryGoal(operation="enumerate_room_boundary_structure_types", source_project=str(source_project), room_name="Research sandbox room", max_ui_actions=min(24, budget.max_ui_actions), max_seconds=min(180, budget.max_seconds)))
                iteration.observations.append({"session_id": discovery.session_id, "stopped_reason": discovery.stopped_reason, "candidate_count": len(discovery.candidates)})
                iteration.evidence_created.extend(item.as_evidence_ref() for item in discovery.evidence)
                windows.extend(discovery.visited_windows)
                if discovery.errors:
                    iteration.failures.extend(discovery.errors)
                if iteration.evidence_created:
                    progress(iteration, "new_discovery_evidence")
                elif no_progress(iteration, current_snapshot.state_fingerprint, action):
                    iterations.append(iteration); break
            elif action.kind == "run_supported_experiment":
                if self.experiment_runner is None or planned.proposed_experiment is None or planned.proposed_experiment.spec is None:
                    iteration.capability_gap = CapabilityGap(semantic_context=action.semantic_context, missing_primitive="approved_experiment_handler", reason="Planner requested an experiment without an executable safe handler.", suggested_evidence=["Add a semantic handler; never expose raw UI actions."])
                else:
                    result = self.experiment_runner.run(planned.proposed_experiment.spec, source_project)
                    self.store.store_experiment_result(result)
                    iteration.evidence_created.extend(result.evidence)
                    if result.success:
                        self.store.promote_to_verified(result.target_capability, result)
                        iteration.capabilities_learned.append(result.target_capability); verified.append(result.target_capability)
                        outcome, summary = "verified", f"Verified {result.target_capability} through save/reopen/readback."
                        iterations.append(iteration); evidence.extend(iteration.evidence_created); break
                    iteration.failures.extend(result.errors)
            elif action.kind == "ask_human":
                outcome, summary = "human_input_required", planned.human_question or "The planner requires human input."
                iterations.append(iteration); break
            else:
                iteration.capability_gap = CapabilityGap(semantic_context=action.semantic_context, missing_primitive="controlled_ui_discovery_for_requested_scope", reason="No registered bounded discovery operation can inspect the requested creation workflow.", suggested_evidence=["Discover the owning catalogue/dialog and its non-committing controls."])
                outcome, summary = "partially_learned", "A required controlled discovery primitive is not implemented; no raw UI action was attempted."
                unresolved.append(iteration.capability_gap.reason)
                iterations.append(iteration); break
            evidence.extend(iteration.evidence_created)
            iterations.append(iteration)
        else:
            unresolved.append("Maximum planner iterations reached")
        return ResearchSessionResult(session_id=session_id, requested_goal=goal, outcome=outcome, iterations=iterations, actions_taken=actions, windows_visited=list(dict.fromkeys(windows)), evidence_created=evidence, hypotheses_created=hypotheses, capabilities_verified=verified, capabilities_rejected=[], unresolved_questions=list(dict.fromkeys(unresolved)), final_summary=summary, started_at=started, finished_at=datetime.now(timezone.utc), current_frontier_state=current_frontier, explored_actions=sorted(f"{state}:{action}" for state, action in seen_actions), blocked_branches=sorted(blocked_branches), last_progress_iteration=last_progress_iteration, last_progress_reason=last_progress_reason)

    @staticmethod
    def _timed_step(name: str, timeout_seconds: float, operation: Callable[[], Any]) -> Any:
        """Bound a blocking provider/UI call without granting it new capabilities."""
        result: dict[str, Any] = {}
        failure: dict[str, BaseException] = {}
        def invoke() -> None:
            try:
                result["value"] = operation()
            except BaseException as exc:  # returned on the calling thread
                failure["error"] = exc
        # UIA/provider libraries cannot reliably be cancelled mid-call.  A
        # daemon worker lets the orchestrator stop and flush its audit without
        # waiting for that uncooperative operation at Python-process exit.
        worker = threading.Thread(target=invoke, name="winwatt-research-step", daemon=True)
        worker.start(); worker.join(timeout_seconds)
        if worker.is_alive():
            raise TimeoutError(f"{name} timed out after {timeout_seconds:.1f}s")
        if "error" in failure:
            raise failure["error"]
        return result.get("value")

    def run_identity_loop_check(
        self,
        goal: str,
        *,
        source_project: Path,
        output_dir: Path,
        human_hints: list[str],
        on_iteration: Callable[[dict[str, Any]], None],
        max_seconds: int = 120,
        planner_timeout_seconds: float = 25.0,
        ui_timeout_seconds: float = 18.0,
    ) -> dict[str, Any]:
        """Small live proof of the ordinary plan → validate → execute → observe loop.

        It deliberately permits only generic identity actions and four planner
        cycles.  It shares the production planner, identity validator and
        ``SandboxUIExplorer`` rather than invoking the CLI as a black box.
        """
        from winwatt_automation.live_ui.app_connector import get_main_window
        from winwatt_automation.research.ui_exploration import SandboxUIExplorer
        from winwatt_automation.services.winwatt_service import WinWattService

        session_id = f"identity_loop_{uuid4().hex}"
        started_tick = time.monotonic()
        explorer: SandboxUIExplorer | None = None
        trace: list[RecentResearchStep] = []
        last_snapshot: Any = None
        records: list[dict[str, Any]] = []
        status = "completed"
        stop_reason: str | None = None

        def flush(record: dict[str, Any]) -> None:
            records.append(record)
            on_iteration({"session_id": session_id, "status": "running", "iterations": records, "updated_at": datetime.now(timezone.utc).isoformat()})

        def start_and_inspect() -> Any:
            nonlocal explorer
            # A prior timed-out check may already have completed the normal
            # sandbox launch in its daemon worker. Reuse only that visible
            # sandbox process; never attach to an arbitrary project.
            try:
                existing = get_main_window()
                title = existing.window_text().casefold()
                # WinWatt truncates long project titles before the literal
                # ``sandbox`` directory. The session-owned output prefix is
                # still a deterministic proof that this is our disposable
                # identity-loop project, never a user project.
                if "\\runtime_maps\\research_sessions\\identity_loop_" in title:
                    explorer = SandboxUIExplorer(existing, output_dir / "reused" / "sandbox" / source_project.name)
                    return explorer.inspect_window()
            except Exception:
                pass
            sandbox = output_dir / session_id / "sandbox" / source_project.name
            service = WinWattService()
            service.create_sandbox(source_project, sandbox)
            service.open_project(sandbox)
            explorer = SandboxUIExplorer(get_main_window(), sandbox)
            return explorer.inspect_window()

        for index in range(1, 5):
            record: dict[str, Any] = {
                "session_id": session_id, "iteration": index,
                "current_window": last_snapshot.class_name if last_snapshot else None,
                "before_state_fingerprint": last_snapshot.state_fingerprint if last_snapshot else None,
                "discovered_controls": [item.model_dump(mode="json") for item in (last_snapshot.controls if last_snapshot else [])],
                "actionable_controls": [], "proposed_action": None, "validated_action": None,
                "executed_action": None, "after_state_fingerprint": None,
                "resulting_window": None, "state_changed": False, "error": None,
            }
            if time.monotonic() - started_tick >= max_seconds:
                record["error"] = f"hard deadline exceeded before iteration {index}"
                flush(record); status = "stopped"; stop_reason = record["error"]; break
            try:
                planner_result = self._timed_step(
                    "planner/provider call", planner_timeout_seconds,
                    lambda: self.planner.plan(goal, human_hints, trace[-4:]),
                )
                context = planner_result.audit.context
                record["actionable_controls"] = [item.model_dump(mode="json") for item in context.actionable_controls]
                proposed = self._action_for(planner_result.plan)
                record["proposed_action"] = proposed.model_dump(mode="json")

                # Generic bootstrap only: without an observation no identity is
                # valid.  Subsequent actions remain planner-selected.
                action = proposed
                if not trace and action.kind != "inspect_ui":
                    action = ResearchAction(kind="inspect_ui", semantic_context="main navigation", reasoning_summary="Initial live UI observation required before an identity action.")
                if trace and action.kind not in {"activate_control", "select_list_item", "inspect_ui", "go_back", "compare_ui_states"}:
                    raise RuntimeError("planner selected an out-of-scope discovery action while live actionable controls are available")
                if action.kind in {"activate_control", "select_list_item"}:
                    identity = action.parameters.get("identity")
                    current = {item.identity: item for item in trace[-1].discovered_controls}
                    control = current.get(identity)
                    if control is None or not control.enabled or control.control_type not in {"Button", "TabItem", "ListItem", "ComboBox", "TreeItem", "MenuItem"}:
                        raise RuntimeError(f"identity validator rejected {identity!r}: not enabled/current/allowlisted")
                if trace and action.kind == "inspect_ui" and trace[-1].action == "inspect_ui" and trace[-1].discovered_controls:
                    raise RuntimeError("repeated inspect_ui on unchanged actionable state")
                record["validated_action"] = action.model_dump(mode="json")

                if action.kind == "inspect_ui":
                    snapshot = self._timed_step("inspect_ui", ui_timeout_seconds, start_and_inspect if explorer is None else explorer.inspect_window)
                    last_snapshot = snapshot
                    record["executed_action"] = action.model_dump(mode="json")
                    record["after_state_fingerprint"] = snapshot.state_fingerprint
                    record["resulting_window"] = snapshot.class_name
                    record["state_changed"] = True
                    trace.append(RecentResearchStep(action="inspect_ui", semantic_context=action.semantic_context, resulting_window=snapshot.class_name, state_fingerprint=snapshot.state_fingerprint, discovered_controls=[RecentDiscoveredControl(identity=item.identity, caption=item.caption, control_type=item.control_type, enabled=item.enabled) for item in snapshot.controls]))
                elif action.kind in {"activate_control", "select_list_item"}:
                    if explorer is None:
                        raise RuntimeError("identity action requested before sandbox explorer exists")
                    before = self._timed_step("pre-action inspect", ui_timeout_seconds, explorer.inspect_window)
                    record["current_window"] = before.class_name
                    record["before_state_fingerprint"] = before.state_fingerprint
                    executed = self._timed_step("activate_control", ui_timeout_seconds, lambda: explorer.activate_control(action.parameters["identity"], index))
                    if not executed.success:
                        raise RuntimeError(executed.failure or "activate_control failed")
                    after = self._timed_step("post-action inspect", ui_timeout_seconds, explorer.inspect_window)
                    last_snapshot = after
                    record["executed_action"] = action.model_dump(mode="json")
                    record["after_state_fingerprint"] = after.state_fingerprint
                    record["resulting_window"] = after.class_name
                    record["state_changed"] = before.state_fingerprint != after.state_fingerprint
                    trace.append(RecentResearchStep(action=action.kind, semantic_context=action.semantic_context, resulting_window=after.class_name, state_fingerprint=after.state_fingerprint, recently_activated_control=action.parameters["identity"], discovered_controls=[RecentDiscoveredControl(identity=item.identity, caption=item.caption, control_type=item.control_type, enabled=item.enabled) for item in after.controls], state_change=record["state_changed"]))
                else:
                    raise RuntimeError(f"identity loop does not permit action {action.kind}")
                flush(record)
            except Exception as exc:
                record["error"] = str(exc)
                flush(record)
                status = "stopped"; stop_reason = str(exc)
                break
        else:
            status = "completed"
        payload = {"session_id": session_id, "status": status, "stop_reason": stop_reason, "total_runtime_seconds": round(time.monotonic() - started_tick, 3), "iterations": records}
        on_iteration(payload)
        return payload
