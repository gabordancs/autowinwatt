"""Explicit Windows/WinWatt E2E regression; never part of normal unit tests."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.mark.skipif(os.environ.get("RUN_WINWATT_E2E") != "1", reason="requires installed WinWatt and an authorized sandbox desktop")
def test_prepare_rooms_e2e() -> None:
    from winwatt_automation.domain.room import RoomInput
    from winwatt_automation.services.room_service import RoomService
    from winwatt_automation.services.winwatt_service import WinWattService

    root = Path(__file__).resolve().parents[1]
    run = root / "data" / "runtime_maps" / "mvp_e2e"
    sandbox = WinWattService().create_sandbox(root / "tests" / "testwwp.wwp", run / "sandbox" / "testwwp.wwp")
    result = RoomService().prepare_rooms([RoomInput(name="E2E room one"), RoomInput(name="E2E room two")], sandbox)
    assert result.success, result.model_dump_json(indent=2)
