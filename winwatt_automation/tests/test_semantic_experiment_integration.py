from __future__ import annotations

import json
from pathlib import Path

from winwatt_automation.domain.results import EvidenceItem, OperationResult
from winwatt_automation.experiments import ExperimentRunner
from winwatt_automation.knowledge import ExperimentSpec, Hypothesis, KnowledgeStatus, KnowledgeStore


class _Workflow:
    def create_sandbox(self, source_project: Path, sandbox_project: Path) -> Path:
        sandbox_project.parent.mkdir(parents=True, exist_ok=True)
        sandbox_project.write_bytes(source_project.read_bytes())
        return sandbox_project

    def read_room(self, name: str, project_path: Path) -> str | None:
        return None

    def prepare_rooms(self, rooms: list[object], project_path: Path) -> OperationResult:
        room = rooms[0]
        return OperationResult(success=True, requested=1, completed=1, verified=True, evidence=[
            EvidenceItem(kind="project_saved", message="Saved through WinWatt Save-As", data={}),
            EvidenceItem(kind="room_values", message="read after reopen", data={"actual": {"area_m2": room.area_m2}}),
        ])


def test_mapping_capability_to_experiment_to_verified_knowledge(tmp_path: Path) -> None:
    capabilities = tmp_path / "room_capabilities.json"
    capabilities.write_text(json.dumps({"room.area_m2": {
        "ui_read": "verified", "ui_write": "verified", "roundtrip_verified": True, "preferred": "ui", "evidence": "mapping.json",
    }}), encoding="utf-8")
    store = KnowledgeStore(tmp_path / "knowledge.json", capabilities)
    source = tmp_path / "source.wwp"
    source.write_bytes(b"project")
    spec = ExperimentSpec.model_validate({
        "hypothesis_id": "hyp_room_area", "target_capability": "room.area_m2",
        "change": {"entity": "MVP Nappali", "from": 28.4, "to": 31.7},
        "observe": ["ui_readback", "save_reopen"],
    })
    store.store_hypothesis(Hypothesis(hypothesis_id=spec.hypothesis_id, target_capability=spec.target_capability, semantic_guess="room area"))
    result = ExperimentRunner(_Workflow(), tmp_path / "runs").run(spec, source)
    store.store_experiment_result(result)
    concept = store.promote_to_verified("room.area_m2", result)
    assert result.roundtrip_verified
    assert concept.status is KnowledgeStatus.VERIFIED
    assert store.get_state_evidence("room.area_m2")
    assert store.get_transition_evidence("room.area_m2")
