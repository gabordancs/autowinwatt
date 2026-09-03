"""Explicit Windows/WinWatt E2E regression; never part of normal unit tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(os.environ.get("RUN_WINWATT_E2E") != "1", reason="requires installed WinWatt and an authorized sandbox desktop")
def test_prepare_rooms_e2e() -> None:
    # The repository's outer directory is also named ``winwatt_automation``.
    # Under pytest's legacy import mode it can shadow the src-layout package.
    # Pin this explicit integration test to the executable application code.
    source = Path(__file__).resolve().parents[1] / "src"
    sys.modules.pop("winwatt_automation", None)
    sys.path.insert(0, str(source))
    from winwatt_automation.domain.room import RoomInput
    from winwatt_automation.services.room_service import RoomService
    from winwatt_automation.services.winwatt_service import WinWattService

    root = Path(__file__).resolve().parents[1]
    run = root / "data" / "runtime_maps" / "mvp_e2e"
    sandbox = WinWattService().create_sandbox(root / "tests" / "testwwp.wwp", run / "sandbox" / "testwwp.wwp")
    result = RoomService().prepare_rooms([
        RoomInput(name="E2E room one", area_m2=10, external_wall=True),
        RoomInput(name="E2E room two"),
    ], sandbox)
    assert result.success, result.model_dump_json(indent=2)
