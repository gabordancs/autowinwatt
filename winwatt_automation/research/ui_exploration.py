"""Sandbox-only, identity-based UI exploration for research sessions."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from winwatt_automation.knowledge.models import EvidenceRef


AllowedControl = Literal["Button", "TabItem", "ListItem", "ComboBox", "TreeItem"]
SafetyClass = Literal["read_only", "safe_navigation", "commit_candidate", "blocked"]


class ControlSummary(BaseModel):
    identity: str
    caption: str
    control_type: str
    class_name: str
    enabled: bool


class WindowSummary(BaseModel):
    identity: str
    title: str
    class_name: str
    controls: list[ControlSummary] = Field(default_factory=list)


class ExplorationAction(BaseModel):
    action_id: str
    iteration: int
    window_before: WindowSummary
    selected_control: str | None = None
    action_type: Literal["inspect_window", "activate_control", "select_list_item", "inspect_dialog", "go_back", "compare_ui_state"]
    safety_class: SafetyClass
    state_before: WindowSummary
    state_after: WindowSummary | None = None
    windows_opened: list[str] = Field(default_factory=list)
    controls_added: list[str] = Field(default_factory=list)
    controls_removed: list[str] = Field(default_factory=list)
    success: bool
    failure: str | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class UIExplorer(Protocol):
    def inspect_window(self) -> WindowSummary: ...
    def activate_control(self, identity: str, iteration: int) -> ExplorationAction: ...
    def go_back(self, iteration: int) -> ExplorationAction: ...


class SandboxUIExplorer:
    """Live adapter. Callers cannot submit coordinates, keys, or executable code."""
    _allowed_types = {"Button", "TabItem", "ListItem", "ComboBox", "TreeItem"}
    _blocked_words = {"torol", "delete", "licenc", "license", "beallitas", "settings", "registry", "megnyitas", "open"}
    _commit_words = {"ok", "apply", "save", "ment", "felvesz", "uj", "masol"}

    def __init__(self, window: Any, sandbox_project: Path) -> None:
        if "sandbox" not in {part.casefold() for part in sandbox_project.resolve().parts}:
            raise ValueError("UI exploration is permitted only for an explicit sandbox path")
        self.window = window
        self.sandbox_project = sandbox_project.resolve()

    @staticmethod
    def _identity(item: Any) -> str:
        raw = f"{item.element_info.control_type}|{item.class_name()}|{item.window_text()}|{item.element_info.automation_id}"
        return sha1(raw.encode("utf-8", "ignore")).hexdigest()[:16]

    def _summary(self, window: Any) -> WindowSummary:
        controls: list[ControlSummary] = []
        for item in window.descendants():
            try:
                if item.is_visible() and item.element_info.control_type in self._allowed_types | {"Edit"}:
                    controls.append(ControlSummary(identity=self._identity(item), caption=item.window_text(), control_type=item.element_info.control_type, class_name=item.class_name(), enabled=bool(item.is_enabled())))
            except Exception:
                continue
        return WindowSummary(identity=self._identity(window), title=window.window_text(), class_name=window.class_name(), controls=controls[:200])

    def inspect_window(self) -> WindowSummary:
        return self._summary(self.window)

    def _safety(self, control: ControlSummary) -> SafetyClass:
        text = control.caption.casefold()
        if any(word in text for word in self._blocked_words):
            return "blocked"
        if any(word in text for word in self._commit_words):
            return "commit_candidate"
        return "safe_navigation"

    def activate_control(self, identity: str, iteration: int) -> ExplorationAction:
        before = self.inspect_window()
        control = next((item for item in before.controls if item.identity == identity), None)
        if control is None:
            return self._result(before, identity, "activate_control", "blocked", False, "unknown discovered control identity")
        safety = self._safety(control)
        if control.control_type not in self._allowed_types or not control.enabled or safety in {"blocked", "commit_candidate"}:
            return self._result(before, identity, "activate_control", safety, False, "control is not auto-activatable in exploration v0")
        live = next((item for item in self.window.descendants() if self._identity(item) == identity), None)
        if live is None:
            return self._result(before, identity, "activate_control", safety, False, "control disappeared before activation")
        try:
            live.click_input()
            after = self._summary(self.window)
            return self._result(before, identity, "activate_control", safety, True, after=after)
        except Exception as exc:
            return self._result(before, identity, "activate_control", safety, False, str(exc))

    def go_back(self, iteration: int) -> ExplorationAction:
        from pywinauto import keyboard
        before = self.inspect_window()
        try:
            self.window.set_focus(); keyboard.send_keys("{ESC}")
            return self._result(before, None, "go_back", "safe_navigation", True, after=self._summary(self.window))
        except Exception as exc:
            return self._result(before, None, "go_back", "safe_navigation", False, str(exc))

    @staticmethod
    def _result(before: WindowSummary, selected: str | None, kind: str, safety: SafetyClass, success: bool, failure: str | None = None, after: WindowSummary | None = None) -> ExplorationAction:
        before_ids = {item.identity for item in before.controls}; after_ids = {item.identity for item in (after.controls if after else [])}
        return ExplorationAction(action_id=f"uia_{uuid4().hex}", iteration=0, window_before=before, selected_control=selected, action_type=kind, safety_class=safety, state_before=before, state_after=after, controls_added=sorted(after_ids-before_ids), controls_removed=sorted(before_ids-after_ids), success=success, failure=failure, evidence_refs=[EvidenceRef(kind="ui_exploration", description=kind, deterministic=False, data={"sandbox": True, "timestamp": datetime.now(timezone.utc).isoformat()})])
