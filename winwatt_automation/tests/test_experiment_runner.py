from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from winwatt_automation.domain.results import EvidenceItem, OperationResult
from winwatt_automation.experiments import ExperimentRunner
from winwatt_automation.knowledge import ExperimentSpec


class FakeRoomWorkflow:
    def create_sandbox(self, source_project: Path, sandbox_project: Path) -> Path:
        sandbox_project.parent.mkdir(parents=True, exist_ok=True)
        sandbox_project.write_bytes(source_project.read_bytes())
        return sandbox_project

    def read_room(self, name: str, project_path: Path) -> str | None:
        return name

    def prepare_rooms(self, rooms: list[object], project_path: Path) -> OperationResult:
        room = rooms[0]
        return OperationResult(
            success=True, requested=1, completed=1, verified=True,
            evidence=[
                EvidenceItem(kind="project_saved", message="saved", data={"project": str(project_path.with_name("prepared.wwp"))}),
                EvidenceItem(kind="room_values", message="values match", data={"expected": {"area_m2": room.area_m2}, "actual": {"area_m2": room.area_m2}}),
            ],
        )


def test_room_area_vertical_slice_uses_sandbox_and_deterministic_readback(tmp_path: Path) -> None:
    source = tmp_path / "template.wwp"
    source.write_bytes(b"template")
    spec = ExperimentSpec.model_validate({
        "hypothesis_id": "hyp_room_area", "target_capability": "room.area_m2",
        "change": {"entity": "MVP Nappali", "from": 28.4, "to": 31.7},
        "observe": ["ui_readback", "save_reopen"],
    })
    result = ExperimentRunner(FakeRoomWorkflow(), tmp_path / "runs").run(spec, source)
    assert result.success is True
    assert result.expected == 31.7
    assert result.actual == 31.7
    assert result.roundtrip_verified is True
    assert Path(result.sandbox_project).read_bytes() == b"template"
    assert any(item.kind == "verification" and item.deterministic for item in result.evidence)


def test_experiment_spec_rejects_raw_computer_use_fields() -> None:
    with pytest.raises(ValidationError):
        ExperimentSpec.model_validate({
            "hypothesis_id": "h", "target_capability": "room.area_m2",
            "change": {"entity": "room", "to": 1, "coordinates": [10, 20]},
            "observe": ["ui_readback"],
        })


def test_unknown_capability_is_not_executed(tmp_path: Path) -> None:
    source = tmp_path / "template.wwp"
    source.write_bytes(b"template")
    spec = ExperimentSpec.model_validate({
        "hypothesis_id": "h_unknown", "target_capability": "room.unknown",
        "change": {"entity": "room", "to": 1}, "observe": ["ui_readback"],
    })
    result = ExperimentRunner(FakeRoomWorkflow(), tmp_path / "runs").run(spec, source)
    assert result.success is False
    assert "not approved" in result.errors[0]
