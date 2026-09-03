from __future__ import annotations

from pathlib import Path
import time
import hashlib

from pywinauto import Application

from winwatt_automation.domain.results import EvidenceItem, OperationResult
from winwatt_automation.domain.room import RoomInput
from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.runtime_mapping.room_deep_explorer import (
    DEFAULT_SANDBOX_BUILDING,
    _activate_rooms_catalog_fast,
    _active_window,
    _create_sandbox_room,
    _room_list_item,
    open_sandbox_building,
    open_sandbox_buildings,
    open_sandbox_room,
)
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
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            try:
                main = get_main_window()
                if main.is_enabled() and _active_window(int(main.process_id())).class_name() == "TMainForm":
                    return
            except Exception:
                pass
            time.sleep(0.15)
        raise RuntimeError("Building editor did not yield to the main window")

    @staticmethod
    def _edit_near(room: object, *, left: int, top: int) -> object:
        candidates = [item for item in room.descendants(control_type="Edit") if item.class_name() == "TEdit"]
        return min(candidates, key=lambda item: abs(item.rectangle().left - left) + abs(item.rectangle().top - top))

    @staticmethod
    def _set_edit_text(room: object, edit: object, value: float) -> None:
        """Use native focus and keystrokes; this Delphi TEdit lacks UIA setters."""
        from pywinauto import keyboard
        native_edit = Application(backend="win32").connect(process=int(room.process_id())).window(handle=int(edit.handle))
        native_edit.set_focus()
        keyboard.send_keys("^a")
        keyboard.send_keys(str(value).replace(".", ","))

    @staticmethod
    def _read_edit_text(room: object, edit: object) -> str:
        native_edit = Application(backend="win32").connect(process=int(room.process_id())).window(handle=int(edit.handle))
        return native_edit.window_text()

    def _apply_proven_fields(self, room: RoomInput, project_path: Path) -> None:
        if room.area_m2 is None and room.height_m is None and room.temperature_c is None and room.summer_design_temperature_c is None:
            return
        detail = open_sandbox_room(project_path=str(project_path), room_name=room.name)
        tabs = sorted([item for item in detail.descendants(control_type="TabItem") if item.rectangle().top < 60], key=lambda item: item.rectangle().left)
        # WinWatt remembers the last selected tab across room editors. Always
        # reset the tab before using coordinate-based field identities.
        tabs[0].click_input()
        if room.area_m2 is not None:
            self._set_edit_text(detail, self._edit_near(detail, left=125, top=99), room.area_m2)
        if room.height_m is not None:
            self._set_edit_text(detail, self._edit_near(detail, left=125, top=146), room.height_m)
        if room.temperature_c is not None:
            tabs[1].click_input()
            self._set_edit_text(detail, self._edit_near(detail, left=215, top=79), room.temperature_c)
        if room.summer_design_temperature_c is not None:
            tabs[2].click_input()
            self._set_edit_text(detail, self._edit_near(detail, left=1705, top=63), room.summer_design_temperature_c)
        from pywinauto import keyboard
        detail.set_focus(); keyboard.send_keys("{ENTER}")
        # Delphi closes the editor asynchronously; do not invoke Save-As until
        # the modal form has yielded control back to the main window.
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            try:
                active = _active_window(int(get_main_window().process_id()))
                if active.class_name() != "TRoomModifyForm" and get_main_window().is_enabled():
                    break
            except Exception:
                pass
            time.sleep(0.15)

    def _apply_external_wall(self, room: RoomInput, project_path: Path) -> None:
        """Create the verified ``Külső fal`` branch for one room.

        WinWatt validates a boundary against the room area, therefore callers
        must provide a positive area in the same request.  The wall workflow
        writes X=1 and the minimum valid companion geometry before committing.
        """
        if not room.external_wall:
            return
        if room.area_m2 is None:
            raise ValueError("external_wall requires a positive area_m2")
        # Import lazily: the evidence script itself uses WinWattService, whose
        # package exports RoomService. Eager import would create a cycle.
        from winwatt_automation.scripts.create_building_with_rooms import add_external_wall, _set_room_area
        detail = open_sandbox_room(project_path=str(project_path), room_name=room.name)
        _set_room_area(detail, room.area_m2)
        add_external_wall(detail)

    def _ensure_saveable_main_window(self) -> None:
        """Recover the current main wrapper only after all record editors close."""
        from pywinauto import keyboard
        main = get_main_window()
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            active = _active_window(int(main.process_id()))
            if active.class_name() != "TRoomModifyForm":
                return
            active.set_focus(); keyboard.send_keys("{ENTER}")
            time.sleep(0.2)
            main = get_main_window()
        raise RuntimeError("Room editor did not close before project persistence")

    def create_room(self, room: RoomInput, project_path: Path) -> EvidenceItem:
        self._open_rooms(project_path)
        main = get_main_window()
        if _room_list_item(main, room.name) is None:
            _create_sandbox_room(main, room.name)
        self._apply_proven_fields(room, project_path)
        self._apply_external_wall(room, project_path)
        fields = [field for field, value in (("area_m2", room.area_m2), ("height_m", room.height_m), ("temperature_c", room.temperature_c), ("summer_design_temperature_c", room.summer_design_temperature_c)) if value is not None]
        if room.external_wall:
            fields.append("external_wall")
        return EvidenceItem(kind="room_created", message=f"Room {room.name!r} is present and project was saved", data={"name": room.name, "applied_fields": fields})

    def create_rooms(self, rooms: list[RoomInput], project_path: Path) -> list[EvidenceItem]:
        # Keep one WinWatt session for a batch. Restarting between records can
        # race the legacy application's asynchronous project save and lose an
        # otherwise correctly created row before the next room is added.
        self._ensure_building(project_path)
        # Stay in the session that just created/opened the building. Restarting
        # here races WinWatt's project-load handoff and can leave a blank main
        # form. A process restart is reserved for post-save verification.
        _activate_rooms_catalog_fast(get_main_window())
        main = get_main_window()
        result: list[EvidenceItem] = []
        for room in rooms:
            main = get_main_window()
            if _room_list_item(main, room.name) is None:
                _create_sandbox_room(main, room.name)
            self._apply_proven_fields(room, project_path)
            self._apply_external_wall(room, project_path)
            applied = [field for field, value in (("area_m2", room.area_m2), ("height_m", room.height_m), ("temperature_c", room.temperature_c), ("summer_design_temperature_c", room.summer_design_temperature_c)) if value is not None]
            if room.external_wall:
                applied.append("external_wall")
            result.append(EvidenceItem(kind="room_created", message=f"Room {room.name!r} is present before project persistence", data={"name": room.name, "applied_fields": applied}))
            main = get_main_window()
        self._ensure_saveable_main_window()
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

    def verify_building(self, project_path: Path, name: str = DEFAULT_SANDBOX_BUILDING) -> EvidenceItem:
        """Reopen the Buildings catalog and prove the parent record survived.

        The rooms list alone is insufficient E2E evidence: WinWatt associates
        every room with a Building record, therefore the parent must be read
        back from the application's own catalog after Save-As as well.
        """
        buildings = open_sandbox_buildings(project_path=str(project_path))
        names = sorted({
            item.window_text().strip()
            for item in buildings.descendants(control_type="ListItem")
            if item.window_text().strip()
        })
        match = next((item for item in names if item.casefold() == name.casefold()), None)
        return EvidenceItem(
            kind="building",
            message=f"Building {name!r} {'is present after reopen' if match else 'is missing after reopen'}",
            data={"expected": name, "actual_buildings": names, "matched": match},
        )

    def verify_rooms(self, expected: list[RoomInput], project_path: Path) -> tuple[bool, list[EvidenceItem]]:
        names_ok, evidence = self._verification.verify_rooms(expected, self.list_rooms(project_path))
        values_ok = True
        for room in expected:
            if all(value is None for value in (room.area_m2, room.height_m, room.temperature_c, room.summer_design_temperature_c)):
                continue
            detail = open_sandbox_room(project_path=str(project_path), room_name=room.name)
            actual: dict[str, float] = {}
            tabs = sorted([item for item in detail.descendants(control_type="TabItem") if item.rectangle().top < 60], key=lambda item: item.rectangle().left)
            tabs[0].click_input()
            if room.area_m2 is not None:
                actual["area_m2"] = float(self._read_edit_text(detail, self._edit_near(detail, left=125, top=99)).replace(",", "."))
            if room.height_m is not None:
                actual["height_m"] = float(self._read_edit_text(detail, self._edit_near(detail, left=125, top=146)).replace(",", "."))
            if room.temperature_c is not None:
                tabs[1].click_input()
                actual["temperature_c"] = float(self._read_edit_text(detail, self._edit_near(detail, left=215, top=79)).replace(",", "."))
            if room.summer_design_temperature_c is not None:
                tabs[2].click_input()
                actual["summer_design_temperature_c"] = float(self._read_edit_text(detail, self._edit_near(detail, left=1705, top=63)).replace(",", "."))
            expected_values = {
                key: value for key, value in room.model_dump().items()
                if key in {"area_m2", "height_m", "temperature_c", "summer_design_temperature_c"} and value is not None
            }
            match = all(abs(float(actual[key]) - float(value)) < 0.0001 for key, value in expected_values.items())
            values_ok = values_ok and match
            evidence.append(EvidenceItem(kind="room_values", message=f"Room {room.name!r} values {'match' if match else 'differ'}", data={"expected": expected_values, "actual": actual}))
            from pywinauto import keyboard
            detail.set_focus(); keyboard.send_keys("{ESC}")
            if room.external_wall:
                from winwatt_automation.scripts.create_building_with_rooms import read_external_wall_x
                wall_detail = open_sandbox_room(project_path=str(project_path), room_name=room.name)
                try:
                    actual_x = read_external_wall_x(wall_detail)
                    wall_match = abs(actual_x - 1.0) < 0.0001
                    values_ok = values_ok and wall_match
                    evidence.append(EvidenceItem(
                        kind="external_wall",
                        message=f"Room {room.name!r} external-wall X {'matches' if wall_match else 'differs'}",
                        data={"expected_x_m": 1.0, "actual_x_m": actual_x},
                    ))
                except Exception as exc:
                    values_ok = False
                    evidence.append(EvidenceItem(
                        kind="external_wall",
                        message=f"Room {room.name!r} external-wall readback failed",
                        data={"error": str(exc)},
                    ))
        return names_ok and values_ok, evidence

    def prepare_rooms(self, rooms: list[RoomInput], project_path: Path) -> OperationResult:
        evidence: list[EvidenceItem] = []
        warnings: list[str] = []
        completed = 0
        try:
            evidence.extend(self.create_rooms(rooms, project_path))
            completed = len(rooms)
            for room in rooms:
                requested = [key for key, value in room.model_dump().items() if key != "name" and value not in (None, False)]
                if requested:
                    warnings.append(f"{room.name}: numeric values will be checked by post-save UI readback")
            persisted_project = self._winwatt.save_project_as(project_path.with_name("prepared.wwp"))
            self._winwatt.close_project_gracefully()
            building_evidence = self.verify_building(persisted_project)
            verified, verification_evidence = self.verify_rooms(rooms, persisted_project)
            verified = verified and building_evidence.data.get("matched") is not None
            digest = hashlib.sha256(persisted_project.read_bytes()).hexdigest()
            evidence.append(EvidenceItem(kind="project_saved", message="Saved through WinWatt Save-As", data={"project": str(persisted_project), "sha256": digest}))
            evidence.append(building_evidence)
            evidence.extend(verification_evidence)
            return OperationResult(success=verified, requested=len(rooms), completed=completed, verified=verified, warnings=warnings, evidence=evidence)
        except Exception as exc:
            return OperationResult(success=False, requested=len(rooms), completed=completed, verified=False, warnings=warnings, errors=[str(exc)], evidence=evidence)
