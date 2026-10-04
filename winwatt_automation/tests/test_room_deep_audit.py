import json

from winwatt_automation.runtime_mapping.room_deep_audit import audit_room_graph


def _write_state_evidence(run_dir, state_id: str) -> None:
    state_dir = run_dir / "states" / state_id
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text("{}", encoding="utf-8")
    (state_dir / "ui.png").write_bytes(b"png")


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


def test_audit_accepts_missing_native_menu_for_modal_room_form(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    state_id = "state_1"
    _write_state_evidence(run_dir, state_id)
    graph = {
        "complete": True,
        "queue_size": 0,
        "states": [{
            "state_id": state_id,
            "window": {"class_name": "TRoomModifyForm"},
            "signature": {"controls": [{}]},
            "native_menu": None,
            "diff_from_parent": {},
        }],
        "edges": [],
        "failures": [],
    }
    (run_dir / "graph.json").write_text(json.dumps(graph), encoding="utf-8")

    result = audit_room_graph(run_dir)

    assert result["evidence_complete"] is True
    assert result["state_evidence"][0]["menu_snapshot_applicable"] is False
    assert result["state_evidence"][0]["menu_evidence_complete"] is True


def test_audit_requires_native_menu_for_main_form(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    state_id = "state_1"
    _write_state_evidence(run_dir, state_id)
    graph = {
        "complete": True,
        "queue_size": 0,
        "states": [{
            "state_id": state_id,
            "window": {"class_name": "TMainForm"},
            "controls": [{}],
            "native_menu": None,
            "diff_from_parent": {},
        }],
        "edges": [],
        "failures": [],
    }
    (run_dir / "graph.json").write_text(json.dumps(graph), encoding="utf-8")

    result = audit_room_graph(run_dir)

    assert result["evidence_complete"] is False
    assert result["state_evidence"][0]["menu_snapshot_applicable"] is True
