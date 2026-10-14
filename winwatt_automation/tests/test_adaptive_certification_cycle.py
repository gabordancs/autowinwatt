from __future__ import annotations

import json
from pathlib import Path

import pytest

from winwatt_automation.certificates.adaptive_cycle import (
    acquire_ui_lease,
    initialize_cycle,
    next_action,
    record_gap,
    record_gap_result,
    release_ui_lease,
)


def _cycle(tmp_path: Path) -> Path:
    project = tmp_path / "project.wwp"
    checkpoint = tmp_path / "checkpoint.json"
    project.write_bytes(b"wwp")
    checkpoint.write_text("{}", encoding="utf-8")
    workspace = tmp_path / "cycle"
    initialize_cycle(
        workspace, certificate_id="10479210", profile_id="profile",
        project=project, reconstruction_checkpoint=checkpoint,
    )
    return workspace


def test_ui_gap_routes_mapping_then_verification_then_reconstruction(tmp_path: Path) -> None:
    workspace = _cycle(tmp_path)
    state = record_gap(workspace, {
        "gap_id": "pdf-export",
        "kind": "ui_gap",
        "stage": "calculation_pdf",
        "operation": "save_rtf",
        "summary": "Save dialog accepted a path but produced no file.",
        "evidence": ["report.json"],
        "expected_postconditions": ["non-empty RTF", "source hash unchanged"],
        "mapping_budget": {"max_actions": 12, "max_depth": 4},
    })
    assert next_action(state)["action"] == "run_bounded_targeted_mapping"
    state = record_gap_result(workspace, gap_id="pdf-export", result="observed", evidence=["mapping.json"])
    assert next_action(state)["action"] == "run_save_reopen_readback_verification"
    state = record_gap_result(workspace, gap_id="pdf-export", result="verified", evidence=["roundtrip.json"])
    assert next_action(state)["action"] == "run_reconstruction_until_checkpoint_or_gap"


def test_input_gap_can_never_be_resolved_by_mapping(tmp_path: Path) -> None:
    workspace = _cycle(tmp_path)
    state = record_gap(workspace, {
        "gap_id": "material",
        "kind": "input_gap",
        "stage": "envelope",
        "operation": "select_material",
        "summary": "No source-backed material decision.",
        "evidence": ["source.pdf"],
        "expected_postconditions": ["human-approved catalog match"],
    })
    assert next_action(state)["action"] == "request_engineering_input_without_assumption"
    with pytest.raises(ValueError, match="cannot be resolved by UI mapping"):
        record_gap_result(workspace, gap_id="material", result="observed", evidence=[])


def test_ui_lease_prevents_two_winwatt_workers(tmp_path: Path) -> None:
    workspace = _cycle(tmp_path)
    acquire_ui_lease(workspace, owner="reconstruction", pid=123)
    with pytest.raises(RuntimeError, match="already held"):
        acquire_ui_lease(workspace, owner="mapping", pid=456)
    state = release_ui_lease(workspace, owner="reconstruction")
    assert state["ui_lease"] is None


def test_project_hash_change_blocks_new_gap(tmp_path: Path) -> None:
    workspace = _cycle(tmp_path)
    state = json.loads((workspace / "cycle_state.json").read_text(encoding="utf-8"))
    Path(state["project"]["path"]).write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="hash changed"):
        record_gap(workspace, {
            "gap_id": "x", "kind": "ui_gap", "stage": "x", "operation": "x",
            "summary": "x", "evidence": [], "expected_postconditions": ["x"],
            "mapping_budget": {"max_actions": 1, "max_depth": 1},
        })
