from pathlib import Path

import pytest

from winwatt_automation.agent.capabilities import CertificationToolRegistry


PROFILE = "winwatt_8c137b67c0a2214bb91aeae8"


def test_default_registry_exposes_only_roundtrip_verified_tools_to_agent() -> None:
    registry = CertificationToolRegistry.load()

    exposed = registry.agent_view(profile_id=PROFILE)

    assert {item["tool_id"] for item in exposed} == {
        "winwatt.building.room.create_roundtrip",
        "winwatt.building.structure.layered.create_roundtrip",
        "winwatt.building.structure.reviewed_handoff.roundtrip",
        "winwatt.building.room.boundary.assign_roundtrip",
        "winwatt.building.orientation.roundtrip",
        "winwatt.building.system.lighting.create_roundtrip",
        "winwatt.building.zone.heated.roundtrip",
        "winwatt.building.system.heating.create_roundtrip",
        "winwatt.building.system.water_heating.create_roundtrip",
        "winwatt.building.system.airing.create_roundtrip",
        "winwatt.building.system.cooling.create_roundtrip",
        "winwatt.building.calculation.result_roundtrip",
        "winwatt.certificate.et_xml.export",
        "winwatt.certificate.preflight",
        "winwatt.mapping.campaign.summarize",
        "webwatt.certificate.intake.local",
    }
    assert all(item["executable"] for item in exposed)


def test_observed_dialog_inventory_cannot_be_executed() -> None:
    registry = CertificationToolRegistry.load()

    with pytest.raises(PermissionError, match="not verified"):
        registry.require_executable(
            "winwatt.building.system.dialogs.inventory", profile_id=PROFILE
        )


def test_verified_tool_is_bound_to_known_profile() -> None:
    registry = CertificationToolRegistry.load()

    tool = registry.require_executable(
        "winwatt.building.orientation.roundtrip", profile_id=PROFILE
    )
    assert tool.handler == "winwatt_automation.scripts.probe_building_energy_modes"

    with pytest.raises(PermissionError, match="not verified for profile"):
        registry.require_executable(
            "winwatt.building.orientation.roundtrip", profile_id="unknown_profile"
        )


def test_all_registry_evidence_paths_exist() -> None:
    registry = CertificationToolRegistry.load()
    package_root = Path(__file__).resolve().parents[1]

    for tool in registry.list():
        for evidence in tool.evidence:
            assert (package_root / evidence.path).is_file(), evidence.path
