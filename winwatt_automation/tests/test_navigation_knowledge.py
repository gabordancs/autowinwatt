from __future__ import annotations

import json
from pathlib import Path

from winwatt_automation.navigation.importer import import_legacy_navigation
from winwatt_automation.navigation.models import NavigationControlSummary
from winwatt_automation.navigation.store import NavigationKnowledgeStore


def _state(store: NavigationKnowledgeStore, fingerprint: str, title: str, source: str = "test"):
    return store.upsert_state(
        fingerprint, "TTest", title,
        [NavigationControlSummary(identity=f"{fingerprint}-button", caption=title, control_type="Button", enabled=True)],
        source, semantic_context=title,
    )


def test_persistence_across_store_instances(tmp_path: Path) -> None:
    path = tmp_path / "navigation.json"
    store = NavigationKnowledgeStore(path)
    source, target = _state(store, "room-main", "Room main"), _state(store, "room-detail", "Room detail")
    store.upsert_transition(source.id, "activate_control", target.id, action_identity="open-room", expected_state=target.fingerprint, status="verified")

    restored = NavigationKnowledgeStore(path)
    route = restored.route(source.id, target.id)
    assert route is not None
    assert route.transitions[0].status == "verified"


def test_fingerprint_deduplicates_and_retains_provenance(tmp_path: Path) -> None:
    store = NavigationKnowledgeStore(tmp_path / "navigation.json")
    first = _state(store, "same", "Mapped state", "runtime_mapper")
    second = _state(store, "same", "Mapped state", "unified_exploration")
    assert first.id == second.id
    sources = {ref.data["source"] for ref in store.states() if ref.id == first.id for ref in ref.provenance}
    assert {"runtime_mapper", "unified_exploration"}.issubset(sources)


def test_verified_route_beats_shorter_observed_route(tmp_path: Path) -> None:
    store = NavigationKnowledgeStore(tmp_path / "navigation.json")
    a, b, c = _state(store, "a", "HVAC main"), _state(store, "b", "HVAC detail"), _state(store, "c", "HVAC menu")
    store.upsert_transition(a.id, "activate_control", b.id, action_identity="direct", expected_state="b", status="observed")
    store.upsert_transition(a.id, "activate_control", c.id, action_identity="menu", expected_state="c", status="verified")
    store.upsert_transition(c.id, "activate_control", b.id, action_identity="detail", expected_state="b", status="verified")
    route = store.route(a.id, b.id)
    assert route is not None
    assert [edge.action_identity for edge in route.transitions] == ["menu", "detail"]


def test_expected_state_mismatch_marks_route_stale(tmp_path: Path) -> None:
    store = NavigationKnowledgeStore(tmp_path / "navigation.json")
    a, b = _state(store, "a", "Main"), _state(store, "b", "Dialog")
    edge = store.upsert_transition(a.id, "activate_control", b.id, action_identity="open", expected_state="b", status="verified")
    assert store.mark_replay(edge.id, "unexpected") is False
    assert next(item for item in store.transitions() if item.id == edge.id).status == "stale"
    assert store.route(a.id, b.id) is None


def test_executable_route_bypasses_planner_and_excludes_observed(tmp_path: Path) -> None:
    store = NavigationKnowledgeStore(tmp_path / "navigation.json")
    a, b = _state(store, "test-main", "Structure main"), _state(store, "test-catalog", "Structure catalog")
    observed = store.upsert_transition(a.id, "activate_control", b.id, action_identity="unsafe-observed", semantic_action="structure catalog", expected_state="catalog", status="observed")
    assert store.executable_route("open structure catalog", "test-main") is None
    edge = store.upsert_transition(a.id, "activate_control", b.id, action_identity="safe-route", semantic_action="structure catalog", expected_state="catalog", status="replayed")
    route = store.executable_route("open structure catalog", "test-main")
    assert route is not None
    assert route.source == "persistent_navigation_knowledge"
    assert route.transitions[0].transition_id == edge.id
    assert route.transitions[0].transition_id != observed.id


def test_stale_edge_is_not_an_executable_route(tmp_path: Path) -> None:
    store = NavigationKnowledgeStore(tmp_path / "navigation.json")
    a, b = _state(store, "main", "HVAC main"), _state(store, "detail", "HVAC detail")
    edge = store.upsert_transition(a.id, "activate_control", b.id, action_identity="open", semantic_action="hvac detail", expected_state="detail", status="replayed")
    assert store.mark_replay(edge.id, "wrong") is False
    assert store.executable_route("HVAC detail", "main") is None


def test_session_local_exclusion_prevents_reselecting_unexecutable_edge(tmp_path: Path) -> None:
    store = NavigationKnowledgeStore(tmp_path / "navigation.json")
    a, b = _state(store, "route-main", "Route main"), _state(store, "route-target", "Route target")
    edge = store.upsert_transition(a.id, "native_menu_ordinal", b.id, capability="catalog.fake.open", semantic_action="catalog fake", expected_state="route-target", status="verified")
    assert store.executable_route("catalog fake", "route-main").transitions[0].transition_id == edge.id
    assert store.executable_route("catalog fake", "route-main", exclude_transition_ids={edge.id}) is None


def test_captionless_observed_transition_persists_and_replays_by_identity(tmp_path: Path) -> None:
    store = NavigationKnowledgeStore(tmp_path / "navigation.json")
    source = store.upsert_state("anonymous-popup", "TPopup", "", [
        NavigationControlSummary(identity="anonymous-menu-1", caption="", control_type="MenuItem", enabled=True),
    ], "sandbox_effect_probe")
    target = _state(store, "anonymous-result", "Observed dialog")
    edge = store.upsert_transition(source.id, "activate_control", target.id, action_identity="anonymous-menu-1", semantic_action="effect-based anonymous menu exploration", expected_state=target.fingerprint, status="observed")
    assert store.mark_replay(edge.id, target.fingerprint) is True
    restored = NavigationKnowledgeStore(tmp_path / "navigation.json")
    route = restored.executable_route("anonymous menu exploration", "anonymous-popup")
    assert route is not None
    assert route.transitions[0].action_identity == "anonymous-menu-1"


def test_legacy_import_is_observed_and_reports_real_artifacts(tmp_path: Path) -> None:
    root = tmp_path
    state_path = root / "data" / "runtime_maps" / "unified_exploration" / "hvac_state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"state_id": "hvac", "active_mdi_title": "HVAC", "snapshot": {"class_name": "THvac", "title": "HVAC", "controls": [{"identity": "hvac-tab", "caption": "Cooling", "control_type": "TabItem", "enabled": True}]}}), encoding="utf-8")
    session_path = root / "data" / "runtime_maps" / "research_sessions" / "research_session.json"
    session_path.parent.mkdir(parents=True)
    session_path.write_text(json.dumps({"iterations": [{"selected_action": {"semantic_context": "hvac"}, "observations": [{"before": {"state_fingerprint": "hvac-main", "class_name": "TMain", "title": "HVAC main"}, "after": {"state_fingerprint": "hvac-detail", "class_name": "THvac", "title": "HVAC detail"}, "executed_action": {"action_type": "activate_control", "identity": "open-hvac"}}]}]}), encoding="utf-8")
    store = NavigationKnowledgeStore(root / "navigation.json")
    report = import_legacy_navigation(root, store)
    assert report.source_files_scanned == 2
    assert report.states_imported >= 3
    assert report.transitions_imported == 1
    assert any(edge.status == "observed" for edge in store.transitions())
