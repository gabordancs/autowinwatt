from __future__ import annotations

import json
from pathlib import Path

from winwatt_automation.knowledge.global_mapping import (
    GlobalMappingStore, LegacyMappingImporter, STATUS_KNOWN, STATUS_PARTIAL, STATUS_STALE,
)


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_imports_legacy_states_transitions_navigation_and_demonstration(tmp_path: Path) -> None:
    _write(tmp_path / "data/runtime_maps/run/states.json", [{"fingerprint": "raw-a", "semantic_state_fingerprint": "semantic-a", "window_class": "TMainForm", "controls": []}])
    _write(tmp_path / "data/runtime_maps/run/transitions.json", [{"from_state": "raw-a", "from_semantic_state": "semantic-a", "to_state": "raw-b", "to_semantic_state": "semantic-b", "action_identity": "elem", "control_type": "MenuItem", "success": True}])
    _write(tmp_path / "data/knowledge/navigation_knowledge.json", {"states": {}, "transitions": {}})
    _write(tmp_path / "data/knowledge/demonstrations/demo.json", {"name": "demo", "target": "x", "steps": []})
    store = GlobalMappingStore(tmp_path / "data/knowledge/global_mapping")
    result = LegacyMappingImporter(project_root=tmp_path, store=store).import_existing()
    assert result["states_imported"] >= 1
    assert result["transitions_imported"] == 1
    assert result["demonstrations_imported"] == 1
    assert any(item["kind"] == "observed_mapping" for item in store.data["provenance"].values())
    assert not (tmp_path / "data/knowledge/global_mapping/provenance.json").read_text(encoding="utf-8").find("verified") >= 0


def test_duplicate_artifact_is_idempotent(tmp_path: Path) -> None:
    _write(tmp_path / "data/runtime_maps/run/states.json", [{"fingerprint": "raw", "semantic_state_fingerprint": "semantic", "window_class": "TMainForm"}])
    _write(tmp_path / "data/knowledge/navigation_knowledge.json", {"states": {}, "transitions": {}})
    store = GlobalMappingStore(tmp_path / "store")
    importer = LegacyMappingImporter(project_root=tmp_path, store=store)
    importer.import_existing(); first = len(store.data["states"])
    again = importer.import_existing()
    assert len(store.data["states"]) == first
    assert again["states_imported"] == 0


def test_equivalent_semantic_states_merge_and_keep_provenance(tmp_path: Path) -> None:
    store = GlobalMappingStore(tmp_path / "store")
    one = store.merge_state({"fingerprint": "raw-one", "semantic_state_fingerprint": "semantic", "window_class": "TMainForm"}, artifact=tmp_path / "one.json")
    two = store.merge_state({"fingerprint": "raw-two", "semantic_state_fingerprint": "semantic", "window_class": "TMainForm"}, artifact=tmp_path / "two.json", provenance="manual")
    assert one == two
    state = store.data["states"][one]
    assert set(state["raw_fingerprints"]) == {"raw-one", "raw-two"}
    assert len(state["provenances"]) == 2


def test_frontier_excludes_known_but_keeps_partial_and_stale_as_hint(tmp_path: Path) -> None:
    store = GlobalMappingStore(tmp_path / "store")
    known = store.merge_state({"fingerprint": "k", "semantic_state_fingerprint": "k", "window_class": "T"}, artifact=tmp_path / "a")
    partial = store.merge_state({"fingerprint": "p", "semantic_state_fingerprint": "p", "window_class": "T"}, artifact=tmp_path / "a")
    stale = store.merge_state({"fingerprint": "s", "semantic_state_fingerprint": "s", "window_class": "T"}, artifact=tmp_path / "a")
    store.data["exploration_status"][known]["status"] = STATUS_KNOWN
    store.data["exploration_status"][partial]["status"] = STATUS_PARTIAL
    store.data["exploration_status"][stale]["status"] = STATUS_STALE
    assert [item["state"] for item in store.useful_frontier()] == [partial]


def test_conflicting_targets_preserve_both_evidence(tmp_path: Path) -> None:
    store = GlobalMappingStore(tmp_path / "store")
    source = store.merge_state({"fingerprint": "a", "semantic_state_fingerprint": "a", "window_class": "T"}, artifact=tmp_path / "a")
    left = store.merge_state({"fingerprint": "b", "semantic_state_fingerprint": "b", "window_class": "T"}, artifact=tmp_path / "a")
    right = store.merge_state({"fingerprint": "c", "semantic_state_fingerprint": "c", "window_class": "T"}, artifact=tmp_path / "b")
    edge = {"action_identity": "x", "control_type": "MenuItem", "success": True}
    store.merge_transition(edge, artifact=tmp_path / "a", source_id=source, target_id=left)
    store.merge_transition(edge, artifact=tmp_path / "b", source_id=source, target_id=right)
    assert len(store.data["transitions"]) == 2
    assert store.data["conflicts"]


def test_known_global_edge_is_not_frontier_but_unknown_sibling_is(tmp_path: Path) -> None:
    class Control:
        def __init__(self, identity, caption):
            self.identity = identity; self.caption = caption; self.control_type = "MenuItem"; self.parent_identity = "parent"; self.ordinal = 1
    store = GlobalMappingStore(tmp_path / "store")
    source = store.merge_state({"fingerprint": "raw", "semantic_state_fingerprint": "semantic", "window_class": "TMainForm"}, artifact=tmp_path / "a")
    target = store.merge_state({"fingerprint": "target", "semantic_state_fingerprint": "target", "window_class": "TMainForm"}, artifact=tmp_path / "a")
    store.merge_transition({"action_identity": "known", "caption": "Elem", "control_type": "MenuItem", "parent_identity": "parent", "ordinal": 1, "success": True}, artifact=tmp_path / "a", source_id=source, target_id=target)
    assert store.known_action(semantic_fingerprint="semantic", window_class="TMainForm", control=Control("known", "Elem"))
    assert not store.known_action(semantic_fingerprint="semantic", window_class="TMainForm", control=Control("unknown", "Más"))
