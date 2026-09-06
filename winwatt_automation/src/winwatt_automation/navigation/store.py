from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Literal
from pathlib import Path

from winwatt_automation.knowledge.models import EvidenceRef

from .models import (
    NavigationContextItem, NavigationContextSummary, NavigationControlSummary,
    ExecutableNavigationRoute, ExecutableNavigationTransition, NavigationRoute, NavigationState, NavigationTransition,
)


class NavigationKnowledgeStore:
    """Atomic, local graph store. Mapper imports are observations, never promotions."""

    def __init__(self, path: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[3]
        self.path = path or root / "data" / "knowledge" / "navigation_knowledge.json"
        self._data = self._load()
        self._batch_depth = 0
        self._dirty = False
        self._seed_explicit_verified_routes()

    @contextmanager
    def batch(self):
        """Coalesce a legacy import into one atomic replace."""
        self._batch_depth += 1
        try:
            yield self
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0 and self._dirty:
                self._dirty = False
                self._save()

    def _commit(self) -> None:
        if self._batch_depth:
            self._dirty = True
        else:
            self._save()

    def _load(self) -> dict:
        if not self.path.is_file():
            return {"schema_version": 1, "states": {}, "transitions": {}}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return {"schema_version": 1, "states": raw.get("states", {}), "transitions": raw.get("transitions", {})}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(self._data, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        # Windows may briefly hold the target while another bounded research
        # session has just flushed its audit.  Retrying preserves atomicity;
        # we never fall back to writing the target in place.
        for attempt in range(8):
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(0.08 * (attempt + 1))

    @staticmethod
    def _id(prefix: str, *parts: str) -> str:
        return f"{prefix}_{hashlib.sha1('|'.join(parts).encode()).hexdigest()[:16]}"

    def _seed_explicit_verified_routes(self) -> None:
        """Migration for a handler already independently runtime-verified."""
        existing = next((key for key, item in self._data["transitions"].items() if item.get("capability") == "catalog.structure.open"), None)
        if existing:
            edge = self._data["transitions"][existing]
            edge["action_kind"] = "native_menu_ordinal"
            edge["semantic_action"] = "catalog.structure.open"
            edge["evidence_refs"] = [EvidenceRef(kind="legacy_verified_native_navigation", description="Semantic action proved by deterministic MDI postcondition", deterministic=True, data={"handler": "runtime_mapping.mdi_state_model.activate_structures_catalog_native", "transport": "native_menu_ordinal", "parent_menu": "Jegyzékek", "ordinal": 2, "expected_postcondition": {"active_mdi_title": "Szerkezetek"}}).model_dump(mode="json")]
            self._commit()
            self._bind_verified_catalog_route_to_canonical_live_main()
            return
        now = datetime.now(timezone.utc)
        main = self.upsert_state("main", "TMainForm", "project main", [], "legacy_verified_navigation")
        structures = self.upsert_state("global structure catalog", "TChildWinForm", "Szerkezetek", [], "legacy_verified_navigation")
        self.upsert_transition(main.id, "native_menu_ordinal", structures.id, capability="catalog.structure.open", semantic_action="catalog.structure.open", status="verified", expected_state=structures.fingerprint, evidence=EvidenceRef(kind="legacy_verified_native_navigation", description="Semantic action proved by deterministic MDI postcondition", deterministic=True, data={"handler": "runtime_mapping.mdi_state_model.activate_structures_catalog_native", "transport": "native_menu_ordinal", "parent_menu": "Jegyzékek", "ordinal": 2, "expected_postcondition": {"active_mdi_title": "Szerkezetek"}}))
        self._bind_verified_catalog_route_to_canonical_live_main()

    def _bind_verified_catalog_route_to_canonical_live_main(self) -> None:
        """Explicit migration binding, not a fuzzy main-window alias rule."""
        canonical = self._data["states"].get(self._id("state", "d9957feca1e1100a"))
        if not canonical:
            return
        state = NavigationState.model_validate(canonical)
        captions = {item.caption for item in state.controls_summary}
        if state.window_class != "TMainForm" or "Jegyzékek" not in captions:
            return
        target = next((item for item in self.states() if item.mdi_title == "Szerkezetek" or item.window_title == "Szerkezetek"), None)
        if target is None:
            target = self.upsert_state("global structure catalog", "TChildWinForm", "Szerkezetek", [], "legacy_verified_navigation", mdi_title="Szerkezetek")
        self.upsert_transition(state.id, "native_menu_ordinal", target.id, capability="catalog.structure.open", semantic_action="catalog.structure.open", expected_state=target.fingerprint, status="verified", evidence=EvidenceRef(kind="rebound_verified_navigation", description="Explicitly rebound to canonical live TMainForm fingerprint using captured class and Jegyzékek control evidence", deterministic=True, data={"canonical_fingerprint": "d9957feca1e1100a", "handler": "runtime_mapping.mdi_state_model.activate_structures_catalog_native", "transport": "native_menu_ordinal", "parent_menu": "Jegyzékek", "ordinal": 2, "expected_postcondition": {"active_mdi_title": "Szerkezetek"}}))

    def states(self) -> list[NavigationState]:
        return [NavigationState.model_validate(value) for value in self._data["states"].values()]

    def has_fingerprint(self, fingerprint: str) -> bool:
        return self._id("state", fingerprint) in self._data["states"]

    def transitions(self) -> list[NavigationTransition]:
        return [NavigationTransition.model_validate(value) for value in self._data["transitions"].values()]

    def upsert_state(self, fingerprint: str, window_class: str, window_title: str, controls: list[NavigationControlSummary], provenance: str, *, mdi_title: str | None = None, semantic_context: str = "") -> NavigationState:
        now = datetime.now(timezone.utc)
        state_id = self._id("state", fingerprint)
        evidence = EvidenceRef(kind="navigation_provenance", description="Navigation state observed", deterministic=False, data={"source": provenance})
        current = self._data["states"].get(state_id)
        if current:
            state = NavigationState.model_validate(current)
            state.last_seen_at = now
            state.controls_summary = controls or state.controls_summary
            state.mdi_title = mdi_title or state.mdi_title
            state.semantic_context = semantic_context or state.semantic_context
            if all(item.data.get("source") != provenance for item in state.provenance): state.provenance.append(evidence)
        else:
            state = NavigationState(id=state_id, fingerprint=fingerprint, window_title=window_title, window_class=window_class, mdi_title=mdi_title, semantic_context=semantic_context, controls_summary=controls, provenance=[evidence], first_seen_at=now, last_seen_at=now)
        self._data["states"][state.id] = state.model_dump(mode="json"); self._commit(); return state

    def upsert_transition(self, from_state_id: str, action_kind: str, to_state_id: str, *, action_identity: str | None = None, capability: str | None = None, semantic_action: str = "", expected_state: str | None = None, status: Literal["observed", "replayed", "verified", "stale", "rejected"] = "observed", evidence: EvidenceRef | None = None) -> NavigationTransition:
        key = self._id("transition", from_state_id, action_kind, action_identity or "", capability or "", to_state_id)
        current = self._data["transitions"].get(key)
        if current:
            transition = NavigationTransition.model_validate(current)
            transition.success_count += 1
            if status == "verified": transition.status = "verified"; transition.last_verified_at = datetime.now(timezone.utc)
            elif transition.status == "observed": transition.status = "replayed"
            if evidence and all(item.description != evidence.description for item in transition.evidence_refs): transition.evidence_refs.append(evidence)
        else:
            transition = NavigationTransition(id=key, from_state_id=from_state_id, action_kind=action_kind, action_identity=action_identity, capability=capability, semantic_action=semantic_action or action_kind, to_state_id=to_state_id, expected_state=expected_state, status=status, replay_count=0, success_count=1, last_verified_at=datetime.now(timezone.utc) if status == "verified" else None, evidence_refs=[evidence] if evidence else [])
        self._data["transitions"][key] = transition.model_dump(mode="json"); self._commit(); return transition

    def mark_replay(self, transition_id: str, actual_fingerprint: str) -> bool:
        transition = NavigationTransition.model_validate(self._data["transitions"][transition_id])
        if transition.expected_state and transition.expected_state != actual_fingerprint:
            transition.status = "stale"; self._data["transitions"][transition_id] = transition.model_dump(mode="json"); self._commit(); return False
        transition.replay_count += 1; transition.success_count += 1
        if transition.status == "observed": transition.status = "replayed"
        self._data["transitions"][transition_id] = transition.model_dump(mode="json"); self._commit(); return True

    def mark_semantic_replay(self, transition_id: str, matched: bool) -> bool:
        transition = NavigationTransition.model_validate(self._data["transitions"][transition_id])
        if not matched:
            transition.status = "stale"
            self._data["transitions"][transition_id] = transition.model_dump(mode="json"); self._commit(); return False
        transition.replay_count += 1; transition.success_count += 1
        self._data["transitions"][transition_id] = transition.model_dump(mode="json"); self._commit(); return True

    def route(self, from_state_id: str, to_state_id: str) -> NavigationRoute | None:
        usable = [item for item in self.transitions() if item.status not in {"stale", "rejected"}]
        costs = {"verified": 1, "replayed": 2, "observed": 5}
        queue: list[tuple[int, list[str], list[NavigationTransition]]] = [(0, [from_state_id], [])]
        best: dict[str, int] = {from_state_id: 0}
        while queue:
            queue.sort(key=lambda item: item[0]); cost, states, edges = queue.pop(0); node = states[-1]
            if node == to_state_id: return NavigationRoute(state_ids=states, transitions=edges, total_cost=cost)
            for edge in [edge for edge in usable if edge.from_state_id == node]:
                next_cost = cost + costs[edge.status]
                if next_cost < best.get(edge.to_state_id, 10**9):
                    best[edge.to_state_id] = next_cost; queue.append((next_cost, states + [edge.to_state_id], edges + [edge]))
        return None

    def executable_route(self, goal: str, current_fingerprint: str, *, exclude_transition_ids: set[str] | None = None) -> ExecutableNavigationRoute | None:
        """Return one deterministic next route segment from the observed state.

        Only verified/replayed transitions are automatic. Observed edges remain
        planner evidence until independently replayed.
        """
        current = next((state for state in self.states() if state.fingerprint == current_fingerprint), None)
        if current is None:
            return None
        goal_terms = {part for part in goal.casefold().replace("_", " ").split() if len(part) > 2}
        state_map = {state.id: state for state in self.states()}
        candidates: list[tuple[int, NavigationTransition, float]] = []
        priority = {"verified": 0, "replayed": 1}
        for edge in self.transitions():
            if edge.id in (exclude_transition_ids or set()):
                continue
            if edge.from_state_id != current.id or edge.status not in priority:
                continue
            target = state_map.get(edge.to_state_id)
            haystack = " ".join([edge.semantic_action, edge.capability or "", target.window_title if target else "", target.semantic_context if target else ""]).casefold()
            # Hungarian inflection makes exact token matching brittle
            # ("szerkezetet" vs "szerkezetjegyzék"). This is retrieval
            # ranking only; replay still requires the exact current state and
            # deterministic expected-state match.
            relevance = 1.0 if not goal_terms else sum((term in haystack or (len(term) >= 7 and term[:7] in haystack)) for term in goal_terms) / len(goal_terms)
            if relevance > 0:
                candidates.append((priority[edge.status], edge, relevance))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], -item[2], item[1].id))
        _, edge, relevance = candidates[0]
        return ExecutableNavigationRoute(
            route_id=self._id("route", current.id, edge.id), goal_relevance=relevance,
            start_state_id=current.id,
            transitions=[ExecutableNavigationTransition(
                transition_id=edge.id, from_state_id=edge.from_state_id, action_kind=edge.action_kind,
                action_identity=edge.action_identity, capability=edge.capability,
                expected_to_state_id=edge.to_state_id, expected_state=edge.expected_state,
                status=edge.status, evidence_refs=edge.evidence_refs,
            )],
        )

    def retrieve(self, goal: str, *, current_state_fingerprint: str | None = None, semantic_context: str = "") -> NavigationContextSummary:
        terms = {item for item in goal.casefold().replace("_", " ").split() if len(item) > 2}
        def relevant(value: str) -> bool: return not terms or any(term in value.casefold() for term in terms)
        states = [item for item in self.states() if relevant(" ".join([item.window_title, item.mdi_title or "", item.semantic_context]))][:8]
        if current_state_fingerprint:
            current = next((item for item in self.states() if item.fingerprint == current_state_fingerprint), None)
            if current is not None and current not in states:
                states.insert(0, current)
        ids = {item.id for item in states}
        transitions = [item for item in self.transitions() if item.status not in {"stale", "rejected"} and (item.from_state_id in ids or item.to_state_id in ids or relevant(item.semantic_action))][:8]
        summaries = []
        state_map = {item.id: item for item in self.states()}
        for item in transitions:
            source = state_map.get(item.from_state_id)
            target = state_map.get(item.to_state_id)
            summaries.append(NavigationContextItem(
                from_context=(source.mdi_title or source.window_title) if source else "project main",
                action=item.capability or item.action_identity or item.action_kind,
                to_context=(target.mdi_title or target.window_title) if target else "unknown",
                status=item.status,
            ))
        return NavigationContextSummary(relevant_states=states, relevant_transitions=summaries, known_safe_navigation_capabilities=sorted({item.capability for item in transitions if item.capability and item.status == "verified"}))
