from __future__ import annotations

from pathlib import Path

from winwatt_automation.research.demonstrations import (
    DemonstrationControl, DemonstrationGuide, DemonstrationStep, DemonstrationStore, UIDemonstration, infer_manual_transition,
)
from winwatt_automation.research.ui_exploration import ControlSummary, WindowSummary
from winwatt_automation.runtime_mapping.state_fingerprints import semantic_state_fingerprint


def _state(raw: str, controls: list[ControlSummary]) -> WindowSummary:
    return WindowSummary(identity="session-window", title="sandbox title", class_name="TMainForm", state_fingerprint=raw, controls=controls)


def _demo(source: WindowSummary, *, observed: DemonstrationControl | None) -> UIDemonstration:
    return UIDemonstration(
        name="structure_creation", target="structure_creation", created_at="now", source_project="sandbox.wwp",
        steps=[DemonstrationStep(
            step_index=1, timestamp="now", raw_state_fingerprint=source.state_fingerprint,
            semantic_state_fingerprint=semantic_state_fingerprint(source), active_mdi_title="Szerkezetek",
            window_identity="recorded-window", window_class="TMainForm", source_state="before", target_state="after",
            semantic_state_delta=True, action_type="manual_observed" if observed else "ambiguous_manual_transition",
            observed_control=observed,
            candidate_controls=[] if observed else [DemonstrationControl(None, "MenuItem", None, None, 1)],
        )],
        terminal_state={"semantic_state_fingerprint": semantic_state_fingerprint(source), "active_mdi_title": "Szerkezetek"},
    )


def test_demonstration_round_trip_and_ambiguous_transition(tmp_path: Path) -> None:
    state = _state("raw", [])
    demo = _demo(state, observed=None)
    store = DemonstrationStore(tmp_path)
    store.save(demo)
    loaded = store.load("structure_creation")
    assert loaded.provenance == "human_demonstration"
    assert loaded.steps[0].action_type == "ambiguous_manual_transition"
    assert loaded.steps[0].observed_control is None


def test_matching_demo_prioritizes_relevant_control_without_runtime_identity_match() -> None:
    elem = ControlSummary(identity="old-elem", caption="Elem", control_type="MenuItem", class_name="TMenuItem", enabled=True, parent_identity="old-parent", ordinal=4)
    source = _state("recorded", [elem])
    demo = _demo(source, observed=DemonstrationControl("old-elem", "MenuItem", "Elem", "old-parent", 4))
    runtime_elem = ControlSummary(identity="new-elem", caption="Elem", control_type="MenuItem", class_name="TMenuItem", enabled=True, parent_identity="old-parent", ordinal=4)
    small = ControlSummary(identity="small", caption="Kis méret", control_type="Button", class_name="TButton", enabled=True)
    decisions = DemonstrationGuide(demo).decisions(_state("different-raw", [runtime_elem, small]), "Szerkezetek", [small, runtime_elem])
    by_id = {item["control_identity"]: item for item in decisions}
    assert by_id["new-elem"]["guidance_score"] > by_id["small"]["guidance_score"]


def test_non_matching_demo_keeps_bfs_tie_order() -> None:
    source = _state("recorded", [ControlSummary(identity="elem", caption="Elem", control_type="MenuItem", class_name="TMenuItem", enabled=True)])
    demo = _demo(source, observed=DemonstrationControl("elem", "MenuItem", "Elem", None, None))
    first = ControlSummary(identity="first", caption="Más", control_type="Button", class_name="TButton", enabled=True)
    second = ControlSummary(identity="second", caption="Másik", control_type="Button", class_name="TButton", enabled=True)
    decisions = DemonstrationGuide(demo).decisions(_state("other", [first, second]), None, [first, second])
    assert [item["control_identity"] for item in sorted(decisions, key=lambda item: -item["final_priority"])] == ["first", "second"]


def test_terminal_match_is_only_a_target_candidate() -> None:
    state = _state("raw", [])
    guide = DemonstrationGuide(_demo(state, observed=None))
    assert guide.target_candidate(state, "Szerkezetek")
    assert guide.demonstration.provenance != "verified"


def test_inference_allows_empty_note_and_records_unambiguous_captionless_control() -> None:
    anonymous = ControlSummary(identity="owner-drawn", caption="", control_type="MenuItem", class_name="TMenuItem", enabled=True, parent_identity="parent", ordinal=2)
    previous = _state("before", [anonymous])
    current = _state("after", [])
    kind, confidence, selected, candidates = infer_manual_transition(previous, current)
    assert kind == "inferred_manual_transition"
    assert confidence == "high"
    assert selected is not None and selected.caption is None
    assert candidates[0].ordinal == 2


def test_ambiguous_transition_is_stored_and_guides_by_context() -> None:
    first = ControlSummary(identity="one", caption="", control_type="MenuItem", class_name="TMenuItem", enabled=True, parent_identity="parent", ordinal=1)
    second = ControlSummary(identity="two", caption="", control_type="MenuItem", class_name="TMenuItem", enabled=True, parent_identity="parent", ordinal=2)
    source = _state("before", [first, second])
    demo = _demo(source, observed=None)
    demo.steps[0].candidate_controls = [DemonstrationControl(None, "MenuItem", None, "parent", 2)]
    decisions = DemonstrationGuide(demo).decisions(source, "Szerkezetek", [first, second])
    by_id = {item["control_identity"]: item for item in decisions}
    assert by_id["two"]["guidance_score"] > by_id["one"]["guidance_score"]


def test_legacy_demonstration_json_migrates_to_v2_fields(tmp_path: Path) -> None:
    path = tmp_path / "legacy.json"
    path.write_text('{"name":"legacy","target":"x","created_at":"now","source_project":"x","terminal_state":{},"steps":[{"step_index":1,"timestamp":"now","raw_state_fingerprint":"after","semantic_state_fingerprint":"semantic","active_mdi_title":null,"window_identity":"w","window_class":"TMainForm","source_state":"before","target_state":"after","semantic_state_delta":true,"action_type":"ambiguous_manual_transition"}]}', encoding="utf-8")
    loaded = DemonstrationStore(tmp_path).load("legacy")
    assert loaded.steps[0].target_raw_fingerprint == "after"
    assert loaded.steps[0].transition_type == "ambiguous_manual_transition"
