"""Sandbox-only identity-based UI exploration; no coordinates or arbitrary keys."""
from __future__ import annotations
from hashlib import sha1
import unicodedata
from typing import Any, Literal
from uuid import uuid4
from pydantic import BaseModel, Field
from loguru import logger
from winwatt_automation.knowledge.models import EvidenceRef

SafetyClass = Literal["read_only", "safe_navigation", "commit_candidate", "blocked"]

class ControlSummary(BaseModel):
    identity: str; caption: str; control_type: str; class_name: str; enabled: bool; caption_source: str = "uia"
    # Owner-drawn Delphi menus can expose no accessible name at all.  These
    # fields make the observed control reproducible without inventing one.
    parent_identity: str | None = None
    ordinal: int | None = None
class WindowSummary(BaseModel):
    identity: str; title: str; class_name: str; state_fingerprint: str = ""; controls: list[ControlSummary] = Field(default_factory=list)
class ExplorationAction(BaseModel):
    action_id: str; iteration: int; window_before: WindowSummary; selected_control: str | None = None
    action_type: str; safety_class: SafetyClass; state_before: WindowSummary; state_after: WindowSummary | None = None
    windows_opened: list[str] = Field(default_factory=list); controls_added: list[str] = Field(default_factory=list); controls_removed: list[str] = Field(default_factory=list)
    success: bool; failure: str | None = None; evidence_refs: list[EvidenceRef] = Field(default_factory=list)

class SandboxUIExplorer:
    allowed = {"Button", "TabItem", "ListItem", "ComboBox", "TreeItem", "MenuItem"}
    blocked = {"torol", "delete", "licenc", "license", "beallitas", "settings", "registry", "megnyitas", "open"}
    commit = {"ok", "apply", "save", "ment", "felvesz", "uj", "masol"}
    def __init__(self, window: Any, sandbox_project: Any) -> None:
        if "sandbox" not in {part.casefold() for part in sandbox_project.resolve().parts}: raise ValueError("sandbox path required")
        self.window = window
        self._native_live: dict[str, Any] = {}
        self._live_by_identity: dict[str, Any] = {}
    def _id(self, item: Any) -> str:
        return sha1(f"{item.element_info.control_type}|{item.class_name()}|{item.window_text()}|{item.element_info.automation_id}".encode()).hexdigest()[:16]
    def _visible_items(self) -> list[Any]:
        items = list(self.window.descendants())
        # Delphi menu popups can be exposed through either UIA or Win32.  Both
        # are read-only discovery sources; identity activation still rechecks
        # the same live collection.
        try:
            from pywinauto import Desktop
            handles: set[int] = set()
            for backend in ("uia", "win32"):
                for popup in Desktop(backend=backend).windows(top_level_only=True):
                    try:
                        handle = popup.handle
                        if handle not in handles and popup.process_id() == self.window.process_id() and popup.is_visible():
                            handles.add(handle); items.append(popup); items.extend(popup.descendants())
                    except Exception:
                        continue
        except Exception:
            pass
        return items
    def inspect_window(self) -> WindowSummary:
        controls=[]
        seen: set[str] = set()
        ordinal_by_parent: dict[str, int] = {}
        self._live_by_identity = {}
        for item in self._visible_items():
            try:
                if item.is_visible() and item.element_info.control_type in self.allowed | {"Edit"}:
                    parent = None
                    try:
                        parent = item.parent()
                    except Exception:
                        pass
                    parent_identity = self._id(parent) if parent is not None else self._id(self.window)
                    ordinal = ordinal_by_parent.get(parent_identity, 0)
                    ordinal_by_parent[parent_identity] = ordinal + 1
                    # UIA frequently assigns equal empty metadata to every
                    # owner-drawn popup row.  The parent + relative position
                    # is observation identity, never a guessed caption.
                    base_identity = self._id(item)
                    caption = item.window_text()
                    # Only owner-drawn menu rows need positional identity.
                    # Treating every unnamed toolbar button as a separate
                    # control would churn the existing main-window state
                    # fingerprint and invalidate proven navigation routes.
                    identity = base_identity if caption or item.element_info.automation_id or item.element_info.control_type != "MenuItem" else sha1(f"{parent_identity}|{item.element_info.control_type}|{item.class_name()}|{ordinal}".encode()).hexdigest()[:16]
                    summary = ControlSummary(identity=identity, caption=caption, control_type=item.element_info.control_type, class_name=item.class_name(), enabled=bool(item.is_enabled()), parent_identity=parent_identity, ordinal=ordinal)
                    if summary.identity not in seen:
                        seen.add(summary.identity); controls.append(summary); self._live_by_identity[summary.identity] = item
            except Exception: pass
        # Owner-drawn Delphi popup rows often have blank UIA names. Reuse the
        # existing read-only Win32 hierarchy and enrich only an unambiguous
        # popup whose native child count matches the visible blank rows.
        blanks = [c for c in controls if c.control_type == "MenuItem" and not c.caption]
        if blanks:
            try:
                from winwatt_automation.live_ui.native_menu import enumerate_native_menu
                native = enumerate_native_menu(self.window)
                groups = [node for node in native.get("items", []) if len(node.get("children", [])) == len(blanks)]
                logger.info("NATIVE_POPUP_ENRICHMENT uia_blank_count={} native_groups={} matching_groups={} tree={}", len(blanks), [(x.get("caption"), x.get("index"), len(x.get("children", []))) for x in native.get("items", [])], [(x.get("caption"), x.get("index")) for x in groups], native)
                if len(groups) == 1:
                    parent = groups[0]
                    live_blanks = [item for item in self._visible_items() if getattr(item.element_info, "control_type", "") == "MenuItem" and not item.window_text()]
                    for position, (summary, node) in enumerate(zip(blanks, parent["children"])):
                        if node.get("caption_reliable") and node.get("caption"):
                            path = f"{parent.get('caption','')}|{node['caption']}|{node.get('index',0)}"
                            stable = sha1(path.encode()).hexdigest()[:16]
                            summary.identity = stable; summary.caption = node["caption"]; summary.caption_source = "native_menu"
                            if position < len(live_blanks): self._native_live[stable] = live_blanks[position]
                else:
                    logger.warning("NATIVE_POPUP_ENRICHMENT_REJECT reason=ambiguous_or_count_mismatch uia_blank_count={} matching_groups={}", len(blanks), len(groups))
            except Exception as exc:
                logger.warning("NATIVE_POPUP_ENRICHMENT_REJECT reason=native_enumeration_error error={}", exc)
        controls = controls[:200]
        fingerprint = sha1("|".join(f"{x.identity}:{x.enabled}" for x in controls).encode()).hexdigest()[:16]
        return WindowSummary(identity=self._id(self.window), title=self.window.window_text(), class_name=self.window.class_name(), state_fingerprint=fingerprint, controls=controls)
    def _safety(self, c: ControlSummary) -> SafetyClass:
        text=unicodedata.normalize("NFKD", c.caption).encode("ascii", "ignore").decode().casefold()
        if any(x in text for x in self.blocked): return "blocked"
        if any(x in text for x in self.commit): return "commit_candidate"
        return "safe_navigation"
    def activate_control(self, identity: str, iteration: int) -> ExplorationAction:
        before=self.inspect_window(); c=next((x for x in before.controls if x.identity==identity),None)
        safety=self._safety(c) if c else "blocked"
        if not c or c.control_type not in self.allowed or not c.enabled or safety in {"blocked","commit_candidate"}:
            return self._result(iteration,before,identity,"activate_control",safety,False,"unknown, blocked, disabled, or commit control")
        live=self._native_live.get(identity) or self._live_by_identity.get(identity)
        if live is None:
            live=next((x for x in self._visible_items() if self._id(x)==identity),None)
        if live is None: return self._result(iteration,before,identity,"activate_control",safety,False,"control disappeared")
        try:
            live.click_input(); return self._result(iteration,before,identity,"activate_control",safety,True,after=self.inspect_window())
        except Exception as exc: return self._result(iteration,before,identity,"activate_control",safety,False,str(exc))
    def set_control_value(self, identity: str, value: str, iteration: int) -> ExplorationAction:
        """Write a disposable probe value to one observed sandbox Edit.

        The caller never receives a raw keyboard primitive: this boundary
        requires an exact current identity, a dummy marker, and a live Edit
        recheck.  The effect, not the guessed field name, is the evidence.
        """
        before = self.inspect_window()
        control = next((item for item in before.controls if item.identity == identity), None)
        if not value.startswith("AI_TEST_"):
            return self._result(iteration, before, identity, "set_control_value", "blocked", False, "only AI_TEST_ sandbox probe values are allowed")
        if not control or control.control_type != "Edit" or not control.enabled:
            return self._result(iteration, before, identity, "set_control_value", "blocked", False, "unknown, disabled, or non-Edit control")
        live = self._live_by_identity.get(identity)
        if live is None:
            return self._result(iteration, before, identity, "set_control_value", "blocked", False, "control disappeared")
        try:
            before_value = live.window_text()
            setter = getattr(live, "set_edit_text", None) or getattr(live, "set_text", None)
            if callable(setter):
                setter(value)
            else:
                typer = getattr(live, "type_keys", None)
                if not callable(typer):
                    return self._result(iteration, before, identity, "set_control_value", "blocked", False, "Edit does not support safe text setting")
                typer("^a{BACKSPACE}", set_foreground=True)
                typer(value, with_spaces=True, set_foreground=True)
            after = self.inspect_window()
            result = self._result(iteration, before, identity, "set_control_value", "safe_navigation", True, after=after)
            result.evidence_refs[0].data.update({"value_before": before_value, "value_after": live.window_text(), "dummy_value": value, "semantic_hypothesis": None})
            return result
        except Exception as exc:
            return self._result(iteration, before, identity, "set_control_value", "blocked", False, str(exc))
    def _result(self,i,before,selected,kind,safety,success,failure=None,after=None):
        b={x.identity for x in before.controls}; a={x.identity for x in (after.controls if after else [])}
        return ExplorationAction(action_id=f"uia_{uuid4().hex}",iteration=i,window_before=before,selected_control=selected,action_type=kind,safety_class=safety,state_before=before,state_after=after,controls_added=sorted(a-b),controls_removed=sorted(b-a),success=success,failure=failure,evidence_refs=[EvidenceRef(kind="ui_exploration",description=kind,deterministic=False,data={"sandbox":True, "source_state": before.state_fingerprint, "target_state": after.state_fingerprint if after else None, "state_changed": bool(after and before.state_fingerprint != after.state_fingerprint), "selected_identity": selected, "control_effect_only": True})])
