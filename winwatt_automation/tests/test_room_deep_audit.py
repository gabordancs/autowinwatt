import json

from winwatt_automation.runtime_mapping.room_deep_audit import audit_room_graph


def test_audit_reports_missing_evidence_and_pending_edge(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    graph = {
        "complete": False,
        "queue_size": 1,
        "states": [{"state_id": "state_1", "controls": [{}], "native_menu": [], "diff_from_parent": {}}],
        "edges": [{"from": "state_1", "to": "pending"}],
        "failures": [],
    }
    (run_dir / "graph.checkpoint.json").write_text(json.dumps(graph), encoding="utf-8")
    result = audit_room_graph(run_dir)
    assert result["evidence_complete"] is False
    assert len(result["pending_edges"]) == 1
    assert (run_dir / "audit.json").exists()
