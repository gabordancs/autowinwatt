from __future__ import annotations

from pathlib import Path
import time

from winwatt_automation.domain.results import EvidenceItem, OperationResult
from winwatt_automation.domain.room import RoomInput
from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.runtime_mapping.room_deep_explorer import _activate_rooms_catalog_fast, _create_sandbox_room, _room_list_item, open_sandbox_building

from .verification_service import VerificationService
from .winwatt_service import WinWattService


class RoomService:
    """Deterministic, semantic room workflow backed by verified runtime routes."""

    def __init__(self, winwatt: WinWattService | None = None, verification: VerificationService | None = None) -> None:
        self._winwatt = winwatt or WinWattService()
        self._verification = verification or VerificationService()

    def create_sandbox(self, source_project: Path, sandbox_project: Path) -> Path:
        return self._winwatt.create_sandbox(source_project, sandbox_project)

    def _open_rooms(self, project_path: Path) -> None:
        self._winwatt.open_project(project_path)
        _activate_rooms_catalog_fast(get_main_window())

    def _ensure_building(self, project_path: Path) -> None:
        """Rooms belong to a building; create the verified sandbox parent first."""
        building = open_sandbox_building(project_path=str(project_path))
        building.set_focus()
        from pywinauto import keyboard
        keyboard.send_keys("{ENTER}")
        self._winwatt.save_project()

    def create_room(self, room: RoomInput, project_path: Path) -> EvidenceItem:
        self._open_rooms(project_path)
        main = get_main_window()
        if _room_list_item(main, room.name) is None:
            _create_sandbox_room(main, room.name)
        self._winwatt.save_project()
        warnings = [field for field, value in (("area_m2", room.area_m2), ("height_m", room.height_m), ("temperature_c", room.temperature_c)) if value is not None]
        return EvidenceItem(kind="room_created", message=f"Room {room.name!r} is present and project was saved", data={"name": room.name, "unsupported_requested_fields": warnings})

    def create_rooms(self, rooms: list[RoomInput], project_path: Path) -> list[EvidenceItem]:
        # Keep one WinWatt session for a batch. Restarting between records can
        # race the legacy application's asynchronous project save and lose an
        # otherwise correctly created row before the next room is added.
        self._ensure_building(project_path)
        self._open_rooms(project_path)
        main = get_main_window()
        result: list[EvidenceItem] = []
        for room in rooms:
            if _room_list_item(main, room.name) is None:
                _create_sandbox_room(main, room.name)
            unsupported = [field for field, value in (("area_m2", room.area_m2), ("height_m", room.height_m), ("temperature_c", room.temperature_c)) if value is not None]
            result.append(EvidenceItem(kind="room_created", message=f"Room {room.name!r} is present and project was saved", data={"name": room.name, "unsupported_requested_fields": unsupported}))
            main = get_main_window()
        self._winwatt.save_project()
        return result

    def list_rooms(self, project_path: Path) -> list[str]:
        self._open_rooms(project_path)
        # The Helyiségek MDI child is created asynchronously after the native
        # menu command.  Reading it immediately produced a false empty list
        # after a restart, so wait for its UIA subtree to become observable.
        deadline = time.monotonic() + 5.0
        while True:
            names = sorted({item.window_text().strip() for item in get_main_window().descendants(control_type="ListItem") if item.window_text().strip()})
            if names or time.monotonic() >= deadline:
                return names
            time.sleep(0.15)

    def read_room(self, name: str, project_path: Path) -> str | None:
        return next((item for item in self.list_rooms(project_path) if item.casefold() == name.casefold()), None)

    def verify_rooms(self, expected: list[RoomInput], project_path: Path) -> tuple[bool, list[EvidenceItem]]:
        return self._verification.verify_rooms(expected, self.list_rooms(project_path))

    def prepare_rooms(self, rooms: list[RoomInput], project_path: Path) -> OperationResult:
        evidence: list[EvidenceItem] = []
        warnings: list[str] = []
        completed = 0
        try:
            evidence.extend(self.create_rooms(rooms, project_path))
            completed = len(rooms)
            for room in rooms:
                unsupported = [key for key, value in room.model_dump().items() if key != "name" and value is not None]
                if unsupported:
                    warnings.append(f"{room.name}: not yet verified for UI writing: {', '.join(unsupported)}")
            self._winwatt.save_project()
            self._winwatt.close_project_gracefully()
            verified, verification_evidence = self.verify_rooms(rooms, project_path)
            evidence.extend(verification_evidence)
            return OperationResult(success=verified, requested=len(rooms), completed=completed, verified=verified, warnings=warnings, evidence=evidence)
        except Exception as exc:
            return OperationResult(success=False, requested=len(rooms), completed=completed, verified=False, warnings=warnings, errors=[str(exc)], evidence=evidence)
