from pathlib import Path

from winwatt_automation.knowledge.global_mapping import GlobalMappingStore


def test_transition_is_projected_into_ui_control_window_and_operation_graphs(tmp_path: Path) -> None:
    store = GlobalMappingStore(tmp_path / "store")
    source = store.merge_state({"fingerprint": "a", "semantic_state_fingerprint": "a", "window_class": "TMainForm", "window_title": "Catalog"}, artifact=tmp_path / "a")
    target = store.merge_state({"fingerprint": "b", "semantic_state_fingerprint": "b", "window_class": "TEditor", "window_title": "Editor"}, artifact=tmp_path / "a")
    store.merge_transition({"action_identity": "new", "caption": "New", "control_type": "Button", "success": True, "operation": "create"}, artifact=tmp_path / "a", source_id=source, target_id=target)
    assert store.data["ui_state_graph"] and store.data["control_action_graph"]
    assert store.data["window_dialog_graph"]
    assert next(iter(store.data["functional_operation_graph"].values()))["operation"] == "create"
