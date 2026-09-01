from pathlib import Path

import pytest
from pydantic import ValidationError

from winwatt_automation.domain.project import PrepareRoomsInput
from winwatt_automation.domain.room import RoomInput
from winwatt_automation.services.verification_service import VerificationService


def test_room_input_is_ui_independent_and_normalizes_name() -> None:
    room = RoomInput(name="  Nappali  ", area_m2=28.4, height_m=2.7)
    assert room.name == "Nappali"
    assert "handle" not in room.model_dump()


def test_prepare_rooms_rejects_duplicate_names() -> None:
    with pytest.raises(ValidationError):
        PrepareRoomsInput(project_path=Path("project.wwp"), rooms=[RoomInput(name="A"), RoomInput(name="a")])


def test_verification_compares_names_case_insensitively() -> None:
    verified, evidence = VerificationService().verify_rooms([RoomInput(name="Nappali")], ["nappali", "Háló"])
    assert verified is True
    assert evidence[0].data["actual"] == "nappali"
