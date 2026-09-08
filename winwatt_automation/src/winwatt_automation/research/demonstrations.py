"""Human UI demonstrations: guidance evidence, never executable authority."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from winwatt_automation.runtime_mapping.state_fingerprints import semantic_state_fingerprint


@dataclass
class DemonstrationControl:
    identity: str | None
    control_type: str
    caption: str | None
    parent_identity: str | None
    ordinal: int | None


@dataclass
class DemonstrationStep:
    step_index: int
    timestamp: str
    raw_state_fingerprint: str
    semantic_state_fingerprint: str
    active_mdi_title: str | None
    window_identity: str
    window_class: str
    source_state: str | None
    target_state: str
    semantic_state_delta: bool
    action_type: str
    observed_control: DemonstrationControl | None = None
    candidate_controls: list[DemonstrationControl] = field(default_factory=list)
    # v2 recorder fields.  The older target-oriented fields above remain so
    # existing demonstration JSON continues to load unchanged.
    source_raw_fingerprint: str | None = None
    source_semantic_fingerprint: str | None = None
    target_raw_fingerprint: str | None = None
    target_semantic_fingerprint: str | None = None
    transition_type: str | None = None
    confidence: str = "low"
    selected_candidate_if_unambiguous: DemonstrationControl | None = None
    active_mdi_before: str | None = None
    active_mdi_after: str | None = None
    human_note: str | None = None
    provenance: str = "human_demonstration"


@dataclass
class UIDemonstration:
    name: str
    target: str
    created_at: str
    source_project: str
    steps: list[DemonstrationStep]
    terminal_state: dict[str, Any]
    notes: str | None = None
    provenance: str = "human_demonstration"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UIDemonstration":
        steps = []
        for raw in data.get("steps", []):
            observed = raw.get("observed_control")
            selected = raw.get("selected_candidate_if_unambiguous")
            candidates = raw.get("candidate_controls") or []
            migrated = dict(raw)
            migrated.setdefault("source_raw_fingerprint", raw.get("source_state"))
            migrated.setdefault("source_semantic_fingerprint", None)
            migrated.setdefault("target_raw_fingerprint", raw.get("target_state") or raw.get("raw_state_fingerprint"))
            migrated.setdefault("target_semantic_fingerprint", raw.get("semantic_state_fingerprint"))
            migrated.setdefault("transition_type", raw.get("action_type", "ambiguous_manual_transition"))
            migrated.setdefault("selected_candidate_if_unambiguous", observed)
            migrated.setdefault("active_mdi_before", None)
            migrated.setdefault("active_mdi_after", raw.get("active_mdi_title"))
            migrated.setdefault("human_note", None)
            migrated.setdefault("provenance", data.get("provenance", "human_demonstration"))
            steps.append(DemonstrationStep(
                **{key: value for key, value in migrated.items() if key not in {"observed_control", "candidate_controls", "selected_candidate_if_unambiguous"}},
                observed_control=DemonstrationControl(**observed) if observed else None,
                candidate_controls=[DemonstrationControl(**item) for item in candidates],
                selected_candidate_if_unambiguous=DemonstrationControl(**selected) if selected else (DemonstrationControl(**observed) if observed else None),
            ))
        return cls(
            name=data["name"], target=data["target"], created_at=data["created_at"], source_project=data["source_project"],
            steps=steps, terminal_state=dict(data.get("terminal_state") or {}), notes=data.get("notes"),
            provenance=data.get("provenance", "human_demonstration"),
        )


class DemonstrationStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def save(self, demonstration: UIDemonstration) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{demonstration.name}.json"
        path.write_text(json.dumps(demonstration.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def load(self, name: str) -> UIDemonstration:
        path = self.directory / f"{name}.json"
        return UIDemonstration.from_dict(json.loads(path.read_text(encoding="utf-8")))


def control_from_summary(control: Any) -> DemonstrationControl:
    return DemonstrationControl(
        identity=control.identity, control_type=control.control_type, caption=control.caption or None,
        parent_identity=control.parent_identity, ordinal=control.ordinal,
    )


def infer_manual_transition(previous: Any, current: Any) -> tuple[str, str, DemonstrationControl | None, list[DemonstrationControl]]:
    """Infer only evidence-supported manual actions from two inventories.

    A disappearing single source control is strong evidence for menu/popup
    activation.  Everything else stays explicitly ambiguous; this deliberately
    avoids inventing captions for owner-drawn controls.
    """
    current_ids = {item.identity for item in current.controls}
    changed = [item for item in previous.controls if item.identity not in current_ids]
    if len(changed) == 1:
        selected = control_from_summary(changed[0])
        return "inferred_manual_transition", "high", selected, [selected]
    candidates = changed[:20]
    if not candidates:
        # An expanded tree or changing selection can preserve the clicked
        # identity.  Preserve only bounded, non-authoritative candidates.
        candidates = [item for item in previous.controls if item.enabled and item.control_type in {"MenuItem", "Button", "TabItem", "TreeItem", "ListItem", "ComboBox"}][:20]
    return "ambiguous_manual_transition", "low", None, [control_from_summary(item) for item in candidates]


def state_features(state: Any, active_mdi: str | None) -> dict[str, Any]:
    return {
        "raw_state_fingerprint": state.state_fingerprint,
        "semantic_state_fingerprint": semantic_state_fingerprint(state),
        "window_identity": state.identity,
        "window_class": state.class_name,
        "active_mdi_title": active_mdi,
        "controls": [control_from_summary(item) for item in state.controls],
    }


class DemonstrationGuide:
    """Scores candidates; it never changes what the safety layer may invoke."""
    def __init__(self, demonstration: UIDemonstration) -> None:
        self.demonstration = demonstration

    def _state_score(self, state: Any, active_mdi: str | None, step: DemonstrationStep) -> tuple[int, list[str]]:
        score, matched = 0, []
        semantic = semantic_state_fingerprint(state)
        expected_semantic = step.source_semantic_fingerprint or step.semantic_state_fingerprint
        if semantic == expected_semantic:
            score += 100; matched.append("semantic_state_fingerprint")
        if state.class_name == step.window_class:
            score += 15; matched.append("window_class")
        expected_mdi = step.active_mdi_before or step.active_mdi_title
        if active_mdi and expected_mdi and active_mdi == expected_mdi:
            score += 20; matched.append("active_mdi_title")
        return score, matched

    @staticmethod
    def _control_score(control: Any, expected: DemonstrationControl) -> tuple[int, list[str]]:
        score, matched = 0, []
        if control.control_type == expected.control_type:
            score += 20; matched.append("control_type")
        if expected.caption and control.caption == expected.caption:
            score += 100; matched.append("caption")
        if expected.parent_identity and control.parent_identity == expected.parent_identity:
            score += 15; matched.append("parent_context")
        if expected.ordinal is not None and control.ordinal == expected.ordinal:
            score += 10; matched.append("ordinal")
        return score, matched

    def decisions(self, state: Any, active_mdi: str | None, controls: list[Any]) -> list[dict[str, Any]]:
        decisions: list[dict[str, Any]] = []
        for bfs_index, control in enumerate(controls):
            best_score, best_step, matched = 0, None, []
            for step in self.demonstration.steps:
                expected_controls = ([step.observed_control] if step.observed_control else []) + list(step.candidate_controls)
                if not expected_controls:
                    continue
                state_score, state_match = self._state_score(state, active_mdi, step)
                control_score, control_match = max((self._control_score(control, expected) for expected in expected_controls), default=(0, []), key=lambda value: value[0])
                # Ambiguous human evidence is weaker than a selected control,
                # yet useful for owner-drawn contexts when type/ordinal agree.
                if step.observed_control is None:
                    control_score //= 2
                score = state_score + control_score
                if score > best_score:
                    best_score, best_step, matched = score, step.step_index, state_match + control_match
            decisions.append({
                "control_identity": control.identity,
                "base_bfs_priority": bfs_index,
                "guidance_score": best_score,
                "matched_demo_step": best_step,
                "matched_features": matched,
                "final_priority": best_score * 1000 - bfs_index,
            })
        return decisions

    def target_candidate(self, state: Any, active_mdi: str | None) -> bool:
        terminal = self.demonstration.terminal_state
        return bool(
            terminal.get("semantic_state_fingerprint") == semantic_state_fingerprint(state)
            and (not terminal.get("active_mdi_title") or terminal.get("active_mdi_title") == active_mdi)
        )


def new_demonstration(*, name: str, target: str, source_project: Path, terminal: dict[str, Any], steps: list[DemonstrationStep], notes: str | None = None) -> UIDemonstration:
    return UIDemonstration(name=name, target=target, created_at=datetime.now(timezone.utc).isoformat(), source_project=str(source_project), steps=steps, terminal_state=terminal, notes=notes)
