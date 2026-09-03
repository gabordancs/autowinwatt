from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from winwatt_automation.domain.results import OperationResult
from winwatt_automation.domain.room import RoomInput
from winwatt_automation.knowledge.models import EvidenceRef, ExperimentResult, ExperimentSpec
from winwatt_automation.services.room_service import RoomService


class RoomWorkflow(Protocol):
    def create_sandbox(self, source_project: Path, sandbox_project: Path) -> Path: ...
    def read_room(self, name: str, project_path: Path) -> str | None: ...
    def prepare_rooms(self, rooms: list[RoomInput], project_path: Path) -> OperationResult: ...


class ExperimentRunner:
    """Run a whitelist of semantic capabilities in a disposable copied project.

    The input never reaches pywinauto.  UI implementation details remain
    encapsulated in the already verified RoomService workflow.
    """

    _KNOWN_ACTIONS = {"room.area_m2"}

    def __init__(self, room_service: RoomWorkflow | None = None, output_dir: Path | None = None) -> None:
        self._rooms = room_service or RoomService()
        package_root = Path(__file__).resolve().parents[3]
        self.output_dir = output_dir or package_root / "data" / "runtime_maps" / "experiments"

    def prepare_sandbox_project(self, source_project: Path) -> Path:
        source = source_project.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Experiment source project does not exist: {source}")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = (self.output_dir / f"experiment_{stamp}_{uuid4().hex[:8]}" / "sandbox" / source.name).resolve()
        if target == source:
            raise ValueError("Experiments must use a copied sandbox project")
        return self._rooms.create_sandbox(source, target)

    def observe_current_state(self, entity: str, sandbox_project: Path, *, read_ui: bool = False) -> EvidenceRef:
        """Record the pre-action state without opening an unnecessary MDI route.

        A v0 area experiment may create its target room, so a name-only
        pre-read does not prove its numeric baseline. The meaningful UI
        observation is the post-save `room_values` readback already performed
        by `RoomService.prepare_rooms`. Callers that already know the entity
        exists may request the conservative name read explicitly.
        """
        actual = self._rooms.read_room(entity, sandbox_project) if read_ui else None
        return EvidenceRef(
            kind="state",
            description="Pre-action sandbox state; numeric proof is collected after save/reopen",
            deterministic=read_ui,
            data={"entity": entity, "actual": actual, "ui_read": read_ui},
        )

    def execute_known_action(self, spec: ExperimentSpec, sandbox_project: Path) -> OperationResult:
        if spec.target_capability not in self._KNOWN_ACTIONS:
            raise ValueError(f"Experiment execution is not approved for capability: {spec.target_capability}")
        if spec.target_capability == "room.area_m2":
            return self._rooms.prepare_rooms(
                [RoomInput(name=spec.change.entity, area_m2=float(spec.change.to_value))],
                sandbox_project,
            )
        raise AssertionError("known capability whitelist was not exhaustive")

    @staticmethod
    def _operation_evidence(operation: OperationResult) -> list[EvidenceRef]:
        return [
            EvidenceRef(
                kind=item.kind,
                description=item.message,
                deterministic=item.kind in {"project_saved", "building", "room_exists", "room_values"},
                data=item.data,
            )
            for item in operation.evidence
        ]

    @staticmethod
    def read_known_values(operation: OperationResult, capability: str) -> float | str | None:
        field = {"room.area_m2": "area_m2"}.get(capability)
        if field is None:
            return None
        for evidence in reversed(operation.evidence):
            if evidence.kind == "room_values":
                actual = evidence.data.get("actual", {})
                if field in actual:
                    return actual[field]
        return None

    @staticmethod
    def compare_expected_actual(expected: float | str, actual: float | str | None) -> bool:
        if actual is None:
            return False
        if isinstance(expected, (float, int)) or isinstance(actual, (float, int)):
            try:
                return abs(float(expected) - float(actual)) < 0.0001
            except (TypeError, ValueError):
                return False
        return expected == actual

    def save_project(self, operation: OperationResult) -> EvidenceRef | None:
        return next((item for item in self._operation_evidence(operation) if item.kind == "project_saved"), None)

    def reopen_project(self, operation: OperationResult) -> EvidenceRef:
        # RoomService.prepare_rooms performs a normal close followed by
        # verification on the saved project.  Keep this explicit primitive so
        # callers do not mistake an in-memory readback for a round trip.
        verified = operation.success and operation.verified and any(item.kind == "project_saved" for item in operation.evidence)
        return EvidenceRef(
            kind="save_reopen",
            description="Save/reopen verification completed by RoomService.prepare_rooms",
            deterministic=verified,
            data={"verified": verified},
        )

    def reset_sandbox(self, sandbox_project: Path) -> EvidenceRef:
        # Artifacts are intentionally preserved for audit/replay.  A new
        # experiment always gets a fresh copy, so no destructive cleanup is
        # required to reset state.
        return EvidenceRef(kind="sandbox_reset", description="Sandbox retained; next run uses a fresh copy", data={"project": str(sandbox_project)})

    def run(self, spec: ExperimentSpec, source_project: Path | None = None) -> ExperimentResult:
        source = source_project or (Path(spec.source_project) if spec.source_project else None)
        if source is None:
            raise ValueError("ExperimentSpec.source_project or source_project argument is required")
        sandbox = self.prepare_sandbox_project(source)
        evidence: list[EvidenceRef] = [self.observe_current_state(spec.change.entity, sandbox)]
        try:
            operation = self.execute_known_action(spec, sandbox)
            evidence.extend(self._operation_evidence(operation))
            save = self.save_project(operation)
            if save:
                evidence.append(save)
            evidence.append(self.reopen_project(operation))
            actual = self.read_known_values(operation, spec.target_capability)
            expected: float | str = (
                float(spec.change.to_value)
                if spec.target_capability == "room.area_m2"
                else spec.change.to_value
            )
            matches = self.compare_expected_actual(expected, actual)
            roundtrip = operation.success and operation.verified and matches and any(item.kind == "project_saved" for item in operation.evidence)
            evidence.append(EvidenceRef(
                kind="verification",
                description="Deterministic expected/actual comparison after save/reopen",
                deterministic=roundtrip,
                data={"expected": expected, "actual": actual, "roundtrip_verified": roundtrip},
            ))
            evidence.append(self.reset_sandbox(sandbox))
            return ExperimentResult(
                experiment_id=f"exp_{uuid4().hex}", hypothesis_id=spec.hypothesis_id,
                target_capability=spec.target_capability, success=roundtrip,
                expected=expected, actual=actual, roundtrip_verified=roundtrip,
                sandbox_project=str(sandbox), evidence=evidence, errors=operation.errors,
            )
        except Exception as exc:
            evidence.append(self.reset_sandbox(sandbox))
            return ExperimentResult(
                experiment_id=f"exp_{uuid4().hex}", hypothesis_id=spec.hypothesis_id,
                target_capability=spec.target_capability, success=False,
                expected=spec.change.to_value, sandbox_project=str(sandbox), evidence=evidence, errors=[str(exc)],
            )
