"""Deterministic, sandbox-only deep mapper for the global Szerkezetek catalog.

This is bootstrap knowledge acquisition, intentionally separate from the
research orchestrator and from any semantic-capability promotion.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from winwatt_automation.knowledge.models import EvidenceRef
from winwatt_automation.navigation.models import NavigationControlSummary
from winwatt_automation.navigation.store import NavigationKnowledgeStore
from winwatt_automation.research.ui_exploration import SandboxUIExplorer, WindowSummary


SAFE_NAVIGATION_TYPES = {"MenuItem", "TabItem", "TreeItem", "ListItem", "ComboBox"}


def actionable_fingerprint(snapshot: WindowSummary) -> str:
    values = sorted(f"{item.control_type}:{item.identity}:{item.enabled}" for item in snapshot.controls if item.control_type in SAFE_NAVIGATION_TYPES | {"Edit", "Button"})
    return hashlib.sha1("|".join(values).encode()).hexdigest()[:16]


def _control_record(item: Any, state: WindowSummary) -> dict[str, Any]:
    return {"state_fingerprint": state.state_fingerprint, "identity": item.identity, "caption": item.caption or None, "control_type": item.control_type, "class_name": item.class_name, "parent_identity": item.parent_identity, "ordinal": item.ordinal, "enabled": item.enabled, "value": item.caption or None}


class StructureCatalogDeepMapper:
    """Bounded deterministic mapper; mutation workflows are not executed."""

    def __init__(self, *, source_project: Path, output_dir: Path, max_actions: int = 30, import_navigation: bool = True, focus_creation: bool = False, probe_input: bool = False, commit_creation: bool = False, existing_item: str | None = None) -> None:
        self.source_project, self.output_dir = source_project.resolve(), output_dir.resolve()
        self.max_actions, self.import_navigation = max_actions, import_navigation
        self.focus_creation = focus_creation
        self.probe_input = probe_input
        self.commit_creation = commit_creation
        self.existing_item = existing_item
        self.states: dict[str, dict[str, Any]] = {}
        self.controls: list[dict[str, Any]] = []
        self.transitions: list[dict[str, Any]] = []
        self.effects: list[dict[str, Any]] = []

    def _record_state(self, snapshot: WindowSummary, *, source: str) -> dict[str, Any]:
        record = {"raw_fingerprint": snapshot.state_fingerprint, "actionable_fingerprint": actionable_fingerprint(snapshot), "window_identity": snapshot.identity, "window_title": snapshot.title, "window_class": snapshot.class_name, "control_count": len(snapshot.controls), "source": source, "captured_at": datetime.now(timezone.utc).isoformat()}
        self.states.setdefault(snapshot.state_fingerprint, record)
        self.controls.extend(_control_record(item, snapshot) for item in snapshot.controls)
        return record

    def _write(self, result: dict[str, Any]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for name, value in (("states.json", list(self.states.values())), ("controls.json", self.controls), ("transitions.json", self.transitions), ("effects.json", self.effects), ("mapping_result.json", result)):
            (self.output_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    def _checkpoint(self, *, status: str = "running") -> None:
        self._write({"run_id": self.output_dir.name, "scope": "global_structure_catalog", "status": status, "states": len(self.states), "controls": len(self.controls), "transitions": len(self.transitions), "updated_at": datetime.now(timezone.utc).isoformat()})

    @staticmethod
    def _secondary_window_inventory(process_id: int) -> list[dict[str, Any]]:
        """Read-only inventory of dialogs opened by an explicit sandbox commit."""
        from pywinauto import Desktop
        result: list[dict[str, Any]] = []
        for window in Desktop(backend="uia").windows(top_level_only=True):
            try:
                if window.process_id() != process_id or not window.is_visible() or window.class_name() == "TMainForm":
                    continue
                controls = []
                for item in window.descendants():
                    if item.is_visible() and item.element_info.control_type in {"Button", "Edit", "ListItem", "TreeItem", "ComboBox", "TabItem", "CheckBox", "RadioButton"}:
                        controls.append({"caption": item.window_text() or None, "control_type": item.element_info.control_type, "class_name": item.class_name(), "enabled": bool(item.is_enabled())})
                result.append({"title": window.window_text(), "class_name": window.class_name(), "handle": int(window.handle), "controls": controls})
            except Exception:
                continue
        return result

    def run(self) -> dict[str, Any]:
        from winwatt_automation.live_ui.app_connector import get_main_window
        from winwatt_automation.runtime_mapping.mdi_state_model import activate_structures_catalog_native, active_mdi_title
        from winwatt_automation.services.winwatt_service import WinWattService

        sandbox = self.output_dir / "sandbox" / self.source_project.name
        service = WinWattService(); service.create_sandbox(self.source_project, sandbox); service.open_project(sandbox)
        explorer = SandboxUIExplorer(get_main_window(), sandbox)
        if not activate_structures_catalog_native() or active_mdi_title() != "Szerkezetek":
            raise RuntimeError("verified catalog.structure.open did not reach Szerkezetek")
        root = explorer.inspect_window(); self._record_state(root, source="verified_catalog_structure_open"); self._checkpoint()
        actions = 0
        if self.existing_item:
            # This is selection only.  It starts a separate deep-mapping pass
            # from a persisted sandbox object without guessing a detail route.
            selected = next((x for x in root.controls if x.control_type == "ListItem" and x.caption == self.existing_item and x.enabled), None)
            if selected is None:
                raise RuntimeError(f"Persisted sandbox structure was not found: {self.existing_item!r}")
            before = root
            probe = explorer.activate_control(selected.identity, 1)
            root = probe.state_after or explorer.inspect_window()
            self._record_state(root, source="existing_structure_selected")
            self.transitions.append({"from_state": before.state_fingerprint, "action_kind": "activate_control", "control_identity": selected.identity, "control_type": selected.control_type, "caption": selected.caption, "parent_identity": selected.parent_identity, "ordinal": selected.ordinal, "to_state": root.state_fingerprint, "state_diff": {"controls_added": probe.controls_added, "controls_removed": probe.controls_removed}, "reversible": True, "mutation_risk": probe.safety_class, "evidence_kind": "mapping_observed", "success": probe.success, "failure": probe.failure})
            self.effects.append({"from_state": before.state_fingerprint, "control_identity": selected.identity, "to_state": root.state_fingerprint, "effect": "existing_structure_selected", "evidence_kind": "mapping_observed"})
            self._checkpoint(); actions = 1
        if self.focus_creation:
            # The only named catalog action needed for this bounded study.
            # The following owner-drawn child stays anonymous and is selected
            # by observed identity/effect, never by a hardcoded caption.
            item = next((x for x in root.controls if x.control_type == "MenuItem" and x.caption == "Elem" and x.enabled), None)
            if item is not None:
                before = explorer.inspect_window(); probe = explorer.activate_control(item.identity, 1); after = probe.state_after or explorer.inspect_window()
                self._record_state(after, source="creation_focus_element_menu")
                self.transitions.append({"from_state": before.state_fingerprint, "action_kind": "activate_control", "control_identity": item.identity, "control_type": item.control_type, "caption": item.caption, "parent_identity": item.parent_identity, "ordinal": item.ordinal, "to_state": after.state_fingerprint, "state_diff": {"controls_added": probe.controls_added, "controls_removed": probe.controls_removed}, "reversible": True, "mutation_risk": probe.safety_class, "evidence_kind": "mapping_observed", "success": probe.success, "failure": probe.failure}); self._checkpoint(); actions = 1
                candidate = next((x for x in after.controls if x.control_type == "MenuItem" and not x.caption and x.enabled), None)
                if candidate is not None and actions < self.max_actions:
                    before = after; probe = explorer.activate_control(candidate.identity, 2); after = probe.state_after or explorer.inspect_window()
                    self._record_state(after, source="creation_focus_anonymous_candidate")
                    self.transitions.append({"from_state": before.state_fingerprint, "action_kind": "activate_control", "control_identity": candidate.identity, "control_type": candidate.control_type, "caption": None, "parent_identity": candidate.parent_identity, "ordinal": candidate.ordinal, "to_state": after.state_fingerprint, "state_diff": {"controls_added": probe.controls_added, "controls_removed": probe.controls_removed}, "reversible": True, "mutation_risk": probe.safety_class, "evidence_kind": "mapping_observed", "success": probe.success, "failure": probe.failure})
                    self.effects.append({"from_state": before.state_fingerprint, "control_identity": candidate.identity, "to_state": after.state_fingerprint, "effect": "input_frontier" if any(x.control_type == "Edit" and x.enabled for x in after.controls) else "state_changed", "evidence_kind": "mapping_observed"}); self._checkpoint()
                    if self.probe_input:
                        edit = next((x for x in after.controls if x.control_type == "Edit" and x.enabled), None)
                        if edit is not None:
                            value = f"AI_TEST_{self.output_dir.name}"
                            before = after; probe = explorer.set_control_value(edit.identity, value, 3); after = probe.state_after or explorer.inspect_window()
                            self._record_state(after, source="creation_focus_dummy_input")
                            self.transitions.append({"from_state": before.state_fingerprint, "action_kind": "set_control_value", "control_identity": edit.identity, "control_type": "Edit", "caption": None, "parent_identity": edit.parent_identity, "ordinal": edit.ordinal, "to_state": after.state_fingerprint, "state_diff": {"controls_added": probe.controls_added, "controls_removed": probe.controls_removed}, "reversible": True, "mutation_risk": "sandbox_dummy_input", "evidence_kind": "mapping_observed", "success": probe.success, "failure": probe.failure})
                            self.effects.append({"from_state": before.state_fingerprint, "control_identity": edit.identity, "to_state": after.state_fingerprint, "effect": "dummy_input_readback", "evidence": [ref.model_dump(mode="json") for ref in probe.evidence_refs]}); self._checkpoint()
                            if self.commit_creation and probe.success:
                                # Commit is deliberately a separate, explicit sandbox
                                # experiment.  The target remains identity-based: no
                                # coordinate or fixed dialog layout is assumed.
                                ok = next((x for x in after.controls if x.control_type == "Button" and x.enabled and explorer._safety(x) == "commit_candidate"), None)
                                if ok is not None:
                                    before = after; commit = explorer.commit_observed_control(ok.identity, 4, sandbox_experiment=True); after = commit.state_after or explorer.inspect_window()
                                    self._record_state(after, source="creation_focus_commit")
                                    self.transitions.append({"from_state": before.state_fingerprint, "action_kind": "commit_observed_control", "control_identity": ok.identity, "control_type": "Button", "caption": ok.caption or None, "parent_identity": ok.parent_identity, "ordinal": ok.ordinal, "to_state": after.state_fingerprint, "state_diff": {"controls_added": commit.controls_added, "controls_removed": commit.controls_removed}, "reversible": False, "mutation_risk": "sandbox_commit", "evidence_kind": "sandbox_experiment", "success": commit.success, "failure": commit.failure})
                                    self.effects.append({"from_state": before.state_fingerprint, "control_identity": ok.identity, "to_state": after.state_fingerprint, "effect": "creation_commit", "evidence": [ref.model_dump(mode="json") for ref in commit.evidence_refs]}); self._checkpoint()
                                    if commit.success:
                                        service.save_project()
                                        self.effects.append({"from_state": after.state_fingerprint, "control_identity": None, "to_state": after.state_fingerprint, "effect": "sandbox_project_saved", "evidence_kind": "sandbox_experiment"}); self._checkpoint()
                                        dialogs = self._secondary_window_inventory(int(explorer.window.process_id()))
                                        self.effects.append({"from_state": after.state_fingerprint, "control_identity": None, "to_state": after.state_fingerprint, "effect": "post_creation_secondary_window_inventory", "evidence_kind": "mapping_observed", "dialogs": dialogs})
                                        self._checkpoint()
        # Level 2: one deterministic reversible probe for every currently
        # observed safe navigation identity. Each action is always followed by
        # a UI diff and Esc reset; commit candidates are blocked by explorer.
        for item in ([] if self.focus_creation else list(root.controls)):
            if actions >= self.max_actions or item.control_type not in SAFE_NAVIGATION_TYPES or not item.enabled:
                continue
            before = explorer.inspect_window()
            probe = explorer.activate_control(item.identity, actions + 1)
            after = probe.state_after or explorer.inspect_window()
            changed = before.state_fingerprint != after.state_fingerprint
            self._record_state(after, source="reversible_navigation_probe")
            transition = {"from_state": before.state_fingerprint, "action_kind": "activate_control", "control_identity": item.identity, "control_type": item.control_type, "caption": item.caption or None, "parent_identity": item.parent_identity, "ordinal": item.ordinal, "to_state": after.state_fingerprint, "state_diff": {"controls_added": probe.controls_added, "controls_removed": probe.controls_removed, "fingerprint_changed": changed}, "reversible": True, "mutation_risk": probe.safety_class, "evidence_kind": "mapping_observed", "success": probe.success, "failure": probe.failure}
            self.transitions.append(transition)
            self.effects.append({"from_state": before.state_fingerprint, "control_identity": item.identity, "to_state": after.state_fingerprint, "effect": "state_changed" if changed else "no_state_change", "evidence": [ref.model_dump(mode="json") for ref in probe.evidence_refs]})
            self._checkpoint()
            actions += 1
            if changed:
                explorer.go_back(actions)
                time.sleep(0.15)
        imported = 0
        if self.import_navigation:
            store = NavigationKnowledgeStore()
            for state in self.states.values():
                store.upsert_state(state["raw_fingerprint"], state["window_class"], state["window_title"], [], "structure_catalog_deep_mapper", semantic_context="catalog.structure")
            for edge in self.transitions:
                if not edge["success"]:
                    continue
                source = store.upsert_state(edge["from_state"], "unknown", "structure catalog", [], "structure_catalog_deep_mapper")
                target = store.upsert_state(edge["to_state"], "unknown", "structure catalog", [], "structure_catalog_deep_mapper")
                store.upsert_transition(source.id, "activate_control", target.id, action_identity=edge["control_identity"], semantic_action="structure catalog mapped navigation", expected_state=edge["to_state"], status="observed", evidence=EvidenceRef(kind="structure_catalog_mapping", description="Deterministic sandbox mapping observation", deterministic=False, data={"reversible": True}))
                imported += 1
        result = {"run_id": self.output_dir.name, "scope": "global_structure_catalog", "status": "complete", "states": len(self.states), "controls": len(self.controls), "transitions": len(self.transitions), "observed_navigation_imports": imported, "mutation_workflows": {"creation": "sandbox_committed" if self.commit_creation else ("sandbox_input_probed" if self.probe_input else "not_executed_requires_explicit_experiment"), "editing": "not_executed", "copy": "not_executed", "delete": "forbidden"}, "created_at": datetime.now(timezone.utc).isoformat()}
        self._write(result)
        return result
