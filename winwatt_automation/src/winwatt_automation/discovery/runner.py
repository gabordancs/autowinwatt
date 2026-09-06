from __future__ import annotations

import ctypes
import hashlib
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from pywinauto import Application, keyboard

from winwatt_automation.discovery.models import (
    CandidateCapability, DiscoveryEvidence, DiscoveryGoal, DiscoveryObservation, DiscoveryResult,
    StructureClassificationGoal, StructureClassificationResult, StructureKindCandidate,
    StructureReferenceCandidate,
)
from winwatt_automation.runtime_mapping.room_deep_explorer import _active_window, open_sandbox_room
from winwatt_automation.scripts.create_building_with_rooms import _find_visible, _wait_window
from winwatt_automation.services.room_service import RoomService


def _plain(value: str) -> str:
    try:
        value = value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _plain(value)).strip("_") or "unlabeled"


def _window_context(window: Any) -> str:
    method = getattr(window, "class_name", None)
    return method() if callable(method) else str(window)


def _layout_fingerprint(detail: dict[str, Any]) -> str | None:
    """Stable, non-semantic UI shape. Dynamic captions/values must not split one form."""
    window_class = detail.get("window_class")
    controls = detail.get("controls", [])
    if not window_class:
        return None
    shape = sorted(
        f"{item.get('control_type')}|{item.get('class')}|{bool(item.get('enabled'))}"
        for item in controls if item.get("control_type") or item.get("class")
    )
    digest = hashlib.sha1("\n".join(shape).encode("utf-8")).hexdigest()[:12]
    return f"{window_class}:{digest}"


def _explicit_kind_value(detail: dict[str, Any]) -> str | None:
    """Use an explicit labelled type/category value if the native detail form exposes one."""
    controls = detail.get("controls", [])
    for index, item in enumerate(controls[:-1]):
        label = _plain(str(item.get("caption", "")))
        if item.get("control_type") in {"Text", "Static"} and any(token in label for token in ("tipus", "kategoria", "category", "type")):
            value = str(controls[index + 1].get("caption", "")).strip()
            if value:
                return value
    return None


def _representative_captions(captions: list[str], maximum: int) -> list[str]:
    """Select name-variant pairs for comparison, without treating names as semantic kinds."""
    def family(value: str) -> str:
        normalized = _slug(value)
        normalized = re.sub(r"_(szig|szigetelt|uj|kie[g]?|fa|muanyag)(?:_|$).*", "", normalized)
        normalized = re.sub(r"\d+$", "", normalized)
        return normalized or _slug(value)

    selected: list[str] = []
    families: dict[str, list[str]] = {}
    for caption in captions:
        families.setdefault(family(caption), []).append(caption)
    # First spend budget on same-family pairs. This tests the user's key question
    # (e.g. a base reference and its insulated variant) but does not classify by name.
    for members in families.values():
        if len(members) > 1:
            for member in members[:2]:
                if len(selected) < maximum and member not in selected:
                    selected.append(member)
    remaining = [caption for caption in captions if caption not in selected]
    while remaining and len(selected) < maximum:
        if not selected:
            selected.append(remaining.pop(0))
            continue
        selected_tokens = set().union(*[set(_slug(value).split("_")) for value in selected])
        best = max(
            remaining,
            key=lambda value: len(set(_slug(value).split("_")) - selected_tokens),
        )
        selected.append(best)
        remaining.remove(best)
    return selected[:maximum]


class DiscoveryUI(Protocol):
    def prepare_sandbox(self, source_project: Path, session_id: str) -> Path: ...
    def open_boundary_selector(self, sandbox_project: Path, room_name: str) -> Any: ...
    def visible_library_types(self, selector: Any) -> list[str]: ...
    def inspect_type(self, selector: Any, caption: str) -> tuple[dict[str, Any], dict[str, Any], str | None]: ...
    def close_selector(self, selector: Any) -> None: ...


class LiveRoomBoundaryDiscoveryUI:
    """Small adapter over the previously mapped Room/Boundary UIA routes."""

    def __init__(self, output_root: Path, rooms: RoomService | None = None) -> None:
        self.output_root = output_root
        self.rooms = rooms or RoomService()

    def prepare_sandbox(self, source_project: Path, session_id: str) -> Path:
        target = (self.output_root / session_id / "sandbox" / source_project.name).resolve()
        return self.rooms.create_sandbox(source_project, target)

    def open_boundary_selector(self, sandbox_project: Path, room_name: str) -> Any:
        room = open_sandbox_room(project_path=str(sandbox_project), room_name=room_name)
        button = _find_visible(room, "Button", "Szerkezetek...")
        button.click_input()
        return _wait_window(int(room.process_id()), {"TSelectBoundarisForm"})

    @staticmethod
    def _library(selector: Any) -> tuple[Any, list[Any]]:
        native = Application(backend="win32").connect(process=int(selector.process_id())).window(handle=int(selector.handle))
        lists = [item for item in native.descendants() if item.class_name() == "TListViewWithHeader"]
        library = max(lists, key=lambda item: item.rectangle().top)
        rows = sorted(
            [item for item in selector.descendants(control_type="ListItem") if item.is_visible() and item.rectangle().top >= library.rectangle().top],
            key=lambda item: item.rectangle().top,
        )
        return library, rows

    @staticmethod
    def _snapshot(window: Any) -> dict[str, Any]:
        controls = []
        for item in window.descendants():
            try:
                if not item.is_visible():
                    continue
                controls.append({
                    "caption": item.window_text(), "control_type": item.element_info.control_type,
                    "class": item.class_name(), "enabled": bool(item.is_enabled()),
                })
            except Exception:
                continue
        return {"window_class": window.class_name(), "controls": controls[:160]}

    def visible_library_types(self, selector: Any) -> list[str]:
        _find_visible(selector, "TreeItem", "Szerkezetek").click_input()
        time.sleep(0.15)
        _find_visible(selector, "TreeItem", "Határoló szerkezetek").click_input()
        time.sleep(0.3)
        _, rows = self._library(selector)
        return list(dict.fromkeys(item.window_text().strip() for item in rows if item.window_text().strip()))

    def inspect_type(self, selector: Any, caption: str) -> tuple[dict[str, Any], dict[str, Any], str | None]:
        before = self._snapshot(selector)
        library, rows = self._library(selector)
        index = next((i for i, item in enumerate(rows) if item.window_text().strip() == caption), None)
        if index is None:
            raise LookupError(f"catalog caption disappeared: {caption!r}")
        height = max(1, (rows[1].rectangle().top - rows[0].rectangle().top) if len(rows) > 1 else 24)
        library.click_input(coords=(30, index * height + height // 2))
        selected = ctypes.windll.user32.SendMessageW(int(library.handle), 0x100C, -1, 2)
        if selected != index:
            raise RuntimeError(f"controlled catalog selection failed for {caption!r}")
        after_selection = self._snapshot(selector)
        add = _find_visible(selector, "Button", "Felvesz...")
        if not add.is_enabled():
            return before, after_selection, None
        add.click_input()
        detail = _active_window(int(selector.process_id()))
        if detail.class_name() == selector.class_name():
            return before, after_selection, None
        detail_snapshot = self._snapshot(detail)
        # Never commit an insertion during discovery; ESC returns to selector.
        detail.set_focus(); keyboard.send_keys("{ESC}")
        _wait_window(int(selector.process_id()), {"TSelectBoundarisForm"})
        return before, {"selection": after_selection, "detail": detail_snapshot}, detail.class_name()

    def close_selector(self, selector: Any) -> None:
        selector.set_focus(); keyboard.send_keys("{ESC}")


class ResearchDiscoveryRunner:
    """Bounded discovery runner; it exposes no raw desktop primitive to callers."""

    def __init__(self, ui: DiscoveryUI, store: Any | None = None) -> None:
        self.ui = ui
        self.store = store

    def run(self, goal: DiscoveryGoal) -> DiscoveryResult:
        if goal.operation != "enumerate_room_boundary_structure_types":
            raise ValueError(f"unsupported controlled discovery operation: {goal.operation}")
        session_id = f"discovery_{uuid4().hex}"
        started = time.monotonic()
        actions = 0
        observations: list[DiscoveryObservation] = []
        evidence: list[DiscoveryEvidence] = []
        candidates: list[CandidateCapability] = []
        visited: list[str] = []
        errors: list[str] = []
        stopped = "completed"
        source = Path(goal.source_project).resolve()
        sandbox = self.ui.prepare_sandbox(source, session_id)
        selector: Any | None = None

        def record(*, caption: str, control_type: str, action: str, before: dict[str, Any], after: dict[str, Any], context: str) -> DiscoveryEvidence:
            observation = DiscoveryObservation(
                window_context=context, control_identity=f"{context}:{_slug(caption)}", caption=caption,
                control_type=control_type, parent_path=["Room", "Határoló szerkezetek"], state_before=before,
                action=action, state_after=after, timestamp=datetime.now(timezone.utc),
            )
            observations.append(observation)
            item = DiscoveryEvidence(evidence_id=f"disc_{uuid4().hex}", session_id=session_id, observation=observation)
            evidence.append(item)
            if self.store:
                self.store.store_discovery_evidence(item)
            return item

        try:
            selector = self.ui.open_boundary_selector(sandbox, goal.room_name)
            selector_context = _window_context(selector)
            visited.extend(["TRoomModifyForm", selector_context])
            before_catalog = {"window_class": selector_context}
            types = self.ui.visible_library_types(selector)
            actions += 3
            catalog_evidence = record(caption="Határoló szerkezetek", control_type="TreeItem", action="open_boundary_catalog", before=before_catalog, after={"catalog_items": types}, context=selector_context)
            # Enumeration itself is meaningful discovery. Persist candidates immediately;
            # a later detail observation can enrich but never verify them.
            by_caption: dict[str, CandidateCapability] = {}
            for caption in types:
                candidate = CandidateCapability(
                    candidate_id=f"candidate_{session_id}_{_slug(caption)}",
                    proposed_concept=f"room.boundary.structure_type.{_slug(caption)}",
                    proposed_operation="select_and_inspect_uncommitted_boundary_type",
                    related_ui_controls=[caption, "Szerkezetek...", "Felvesz..."], confidence=0.35,
                    evidence_refs=[catalog_evidence.as_evidence_ref()],
                )
                candidates.append(candidate)
                by_caption[caption] = candidate
                if self.store:
                    self.store.store_candidate_capability(candidate)
            for caption in types:
                if actions + 2 > goal.max_ui_actions:
                    stopped = "max_ui_actions"
                    break
                if time.monotonic() - started >= goal.max_seconds:
                    stopped = "max_seconds"
                    break
                try:
                    before, after, detail_class = self.ui.inspect_type(selector, caption)
                    actions += 2
                    if detail_class:
                        visited.append(detail_class)
                    item = record(caption=caption, control_type="ListItem", action="select_then_open_uncommitted_detail", before=before, after=after, context=selector_context)
                    candidate = CandidateCapability(
                        candidate_id=f"candidate_{session_id}_{_slug(caption)}",
                        proposed_concept=f"room.boundary.structure_type.{_slug(caption)}",
                        proposed_operation="select_and_inspect_uncommitted_boundary_type",
                        related_ui_controls=[caption, "Szerkezetek...", "Felvesz..."], confidence=0.55 if detail_class else 0.4,
                        evidence_refs=[item.as_evidence_ref()],
                    )
                    candidates[candidates.index(by_caption[caption])] = candidate
                    by_caption[caption] = candidate
                    if self.store:
                        self.store.store_candidate_capability(candidate)
                except Exception as exc:
                    errors.append(f"{caption}: {type(exc).__name__}: {exc}")
        except Exception as exc:
            stopped = "blocked_before_catalog"
            errors.append(f"open_boundary_selector: {type(exc).__name__}: {exc}")
        finally:
            if selector is not None:
                try:
                    self.ui.close_selector(selector)
                except Exception as exc:
                    errors.append(f"close_selector: {type(exc).__name__}: {exc}")
        return DiscoveryResult(
            session_id=session_id, goal=goal, sandbox_project=str(sandbox), visited_windows=list(dict.fromkeys(visited)),
            observations=observations, evidence=evidence, candidates=candidates, stopped_reason=stopped, errors=errors,
        )

    def classify_room_boundary_structures(self, goal: StructureClassificationGoal) -> StructureClassificationResult:
        """Inspect a bounded sample of catalogue references and infer only evidence-backed groups.

        This is deliberately separate from executable semantic capabilities.  It may open a
        detail dialog, then always escapes back to the selector; it neither saves nor commits.
        """
        session_id = f"structure_classification_{uuid4().hex}"
        started = time.monotonic()
        actions = 0
        observations: list[DiscoveryObservation] = []
        evidence: list[DiscoveryEvidence] = []
        references: list[StructureReferenceCandidate] = []
        visited: list[str] = []
        errors: list[str] = []
        stopped = "completed"
        source = Path(goal.source_project).resolve()
        sandbox = self.ui.prepare_sandbox(source, session_id)
        selector: Any | None = None
        workflow_summary: dict[str, Any] = {
            "committed": False,
            "reset": "ESC closes detail and selector; sandbox is discarded",
            "steps": [],
        }

        def record(*, caption: str, action: str, before: dict[str, Any], after: dict[str, Any], context: str, control_type: str = "ListItem") -> DiscoveryEvidence:
            observation = DiscoveryObservation(
                window_context=context, control_identity=f"{context}:{_slug(caption)}", caption=caption,
                control_type=control_type, parent_path=["Room", "Határoló szerkezetek"], state_before=before,
                action=action, state_after=after, timestamp=datetime.now(timezone.utc),
            )
            observations.append(observation)
            item = DiscoveryEvidence(evidence_id=f"disc_{uuid4().hex}", session_id=session_id, observation=observation)
            evidence.append(item)
            if self.store:
                self.store.store_discovery_evidence(item)
            return item

        try:
            selector = self.ui.open_boundary_selector(sandbox, goal.room_name)
            selector_context = _window_context(selector)
            visited.extend(["TRoomModifyForm", selector_context])
            catalog = self.ui.visible_library_types(selector)
            actions += 3
            catalog_evidence = record(
                caption="Határoló szerkezetek", action="open_boundary_catalog",
                before={"window_class": selector_context}, after={"catalog_items": catalog},
                context=selector_context, control_type="TreeItem",
            )
            if goal.representative_captions:
                unknown = [caption for caption in goal.representative_captions if caption not in catalog]
                if unknown:
                    raise ValueError(f"requested representative captions are not in the observed catalog: {unknown}")
                sample = list(dict.fromkeys(goal.representative_captions))[:goal.max_representatives]
            else:
                sample = _representative_captions(catalog, goal.max_representatives)
            workflow_summary["catalog_to_detail"] = "select reference → Felvesz... → detail dialog → ESC → selector restored"
            workflow_summary["steps"].append("opened_catalog")
            for caption in sample:
                if actions + 2 > goal.max_ui_actions:
                    stopped = "max_ui_actions"
                    break
                if time.monotonic() - started >= goal.max_seconds:
                    stopped = "max_seconds"
                    break
                try:
                    before, after, detail_class = self.ui.inspect_type(selector, caption)
                    actions += 2
                    detail = after.get("detail", {}) if isinstance(after, dict) else {}
                    fingerprint = _layout_fingerprint(detail)
                    explicit_kind = _explicit_kind_value(detail)
                    if detail_class:
                        visited.append(detail_class)
                    item = record(
                        caption=caption, action="select_reference_open_detail_then_cancel",
                        before=before, after=after, context=selector_context,
                    )
                    reference = StructureReferenceCandidate(
                        reference_id=f"structure_reference_{session_id}_{_slug(caption)}",
                        display_name=caption, source_control=f"{selector_context}:TListViewWithHeader",
                        evidence_refs=[catalog_evidence.as_evidence_ref(), item.as_evidence_ref()],
                        detail_window_class=detail_class or detail.get("window_class"), detail_layout_fingerprint=fingerprint,
                        explicit_kind_value=explicit_kind,
                    )
                    references.append(reference)
                    if self.store:
                        self.store.store_structure_reference_candidate(reference)
                    workflow_summary["steps"].append(f"inspected:{caption}")
                except Exception as exc:
                    errors.append(f"{caption}: {type(exc).__name__}: {exc}")
            kinds = self._group_structure_kinds(references)
            for kind in kinds:
                if self.store:
                    self.store.store_structure_kind_candidate(kind)
        except Exception as exc:
            stopped = "blocked_before_catalog"
            errors.append(f"open_boundary_selector: {type(exc).__name__}: {exc}")
            catalog = []
            sample = []
            kinds = []
        finally:
            if selector is not None:
                try:
                    self.ui.close_selector(selector)
                    workflow_summary["steps"].append("cancelled_selector")
                except Exception as exc:
                    errors.append(f"close_selector: {type(exc).__name__}: {exc}")
        return StructureClassificationResult(
            session_id=session_id, goal=goal, sandbox_project=str(sandbox), catalog_references_count=len(catalog),
            selected_representatives=sample, visited_windows=list(dict.fromkeys(visited)), observations=observations,
            evidence=evidence, structure_references=references, structure_kinds=kinds,
            workflow_summary=workflow_summary, stopped_reason=stopped, errors=errors,
        )

    @staticmethod
    def _group_structure_kinds(references: list[StructureReferenceCandidate]) -> list[StructureKindCandidate]:
        """Group by explicit UI type, otherwise by identical native detail layout.

        No display-name token is used to infer membership.  A singleton fingerprint is still
        recorded as a low-confidence candidate so later sampling can merge or reject it.
        """
        groups: dict[tuple[str, str], list[StructureReferenceCandidate]] = {}
        for reference in references:
            if reference.explicit_kind_value:
                key = ("explicit_kind", _slug(reference.explicit_kind_value))
            elif reference.detail_layout_fingerprint:
                key = ("detail_layout", reference.detail_layout_fingerprint)
            else:
                key = ("insufficient_detail", reference.reference_id)
            groups.setdefault(key, []).append(reference)
        result: list[StructureKindCandidate] = []
        for (basis, key), members in groups.items():
            if basis == "explicit_kind":
                proposed_kind = f"room.boundary.structure_kind.{key}"
                confidence = 0.8 if len(members) > 1 else 0.65
                description = "explicit UI type/category field"
            elif basis == "detail_layout":
                proposed_kind = f"room.boundary.structure_kind.detail_layout_{key.rsplit(':', 1)[-1]}"
                confidence = 0.7 if len(members) > 1 else 0.4
                description = "same native detail form class and control-layout fingerprint"
            else:
                proposed_kind = f"room.boundary.structure_kind.unclassified_{_slug(members[0].display_name)}"
                confidence = 0.15
                description = "insufficient detail UI evidence; no name-based grouping applied"
            refs = [item.reference_id for item in members]
            evidence_refs = [evidence for item in members for evidence in item.evidence_refs]
            result.append(StructureKindCandidate(
                proposed_kind=proposed_kind, member_structure_references=refs, evidence_refs=evidence_refs,
                confidence=confidence, classification_basis=description,
            ))
        return result
