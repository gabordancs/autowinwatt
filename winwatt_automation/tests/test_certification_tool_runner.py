from pathlib import Path

import pytest

from winwatt_automation.agent.capabilities import CertificationToolRegistry
from winwatt_automation.scripts.certification_tool_runner import (
    build_handler_arguments,
    parse_parameters,
)


PROFILE = "winwatt_8c137b67c0a2214bb91aeae8"


def test_parse_parameters_rejects_ambiguous_values() -> None:
    assert parse_parameters(["name=Teszt", "expected_zone=Zóna"]) == {
        "name": "Teszt", "expected_zone": "Zóna",
    }
    with pytest.raises(ValueError, match="duplicate"):
        parse_parameters(["name=A", "name=B"])
    with pytest.raises(ValueError, match="KEY=VALUE"):
        parse_parameters(["name"])


def test_heating_adapter_requires_semantic_parameters(tmp_path: Path) -> None:
    tool = CertificationToolRegistry.load().require_executable(
        "winwatt.building.system.heating.create_roundtrip", profile_id=PROFILE
    )
    arguments = build_handler_arguments(
        tool=tool, profile=tmp_path / "profile.json", source=tmp_path / "source.wwp",
        output=tmp_path / "out", parameters={"name": "Fűtés", "expected_zone": "Zóna"},
    )
    assert arguments[-4:] == ["--name", "Fűtés", "--expected-zone", "Zóna"]

    with pytest.raises(ValueError, match="missing parameters"):
        build_handler_arguments(
            tool=tool, profile=tmp_path / "profile.json", source=tmp_path / "source.wwp",
            output=tmp_path / "out", parameters={"name": "Fűtés"},
        )


def test_water_heating_adapter_uses_unique_name(tmp_path: Path) -> None:
    tool = CertificationToolRegistry.load().require_executable(
        "winwatt.building.system.water_heating.create_roundtrip", profile_id=PROFILE
    )
    arguments = build_handler_arguments(
        tool=tool, profile=tmp_path / "profile.json", source=tmp_path / "source.wwp",
        output=tmp_path / "out", parameters={"name": "HMV"},
    )
    assert arguments[-2:] == ["--name", "HMV"]


@pytest.mark.parametrize("kind", ["airing", "cooling"])
def test_airing_and_cooling_adapters_bind_system_kind(tmp_path: Path, kind: str) -> None:
    tool = CertificationToolRegistry.load().require_executable(
        f"winwatt.building.system.{kind}.create_roundtrip", profile_id=PROFILE
    )
    arguments = build_handler_arguments(
        tool=tool, profile=tmp_path / "profile.json", source=tmp_path / "source.wwp",
        output=tmp_path / "out", parameters={"name": "Rendszer"},
    )
    assert arguments[-4:] == ["--system", kind, "--name", "Rendszer"]


def test_calculation_result_adapter_needs_no_semantic_parameters(tmp_path: Path) -> None:
    tool = CertificationToolRegistry.load().require_executable(
        "winwatt.building.calculation.result_roundtrip", profile_id=PROFILE
    )
    arguments = build_handler_arguments(
        tool=tool, profile=tmp_path / "profile.json", source=tmp_path / "source.wwp",
        output=tmp_path / "out", parameters={},
    )
    assert arguments == [
        "--profile", str(tmp_path / "profile.json"),
        "--source", str(tmp_path / "source.wwp"),
        "--output", str(tmp_path / "out"),
    ]


def test_et_xml_export_adapter_requires_building_name(tmp_path: Path) -> None:
    tool = CertificationToolRegistry.load().require_executable(
        "winwatt.certificate.et_xml.export", profile_id=PROFILE
    )
    arguments = build_handler_arguments(
        tool=tool, profile=tmp_path / "profile.json", source=tmp_path / "source.wwp",
        output=tmp_path / "out", parameters={"building_name": "Tesztépület"},
    )
    assert arguments[-2:] == ["--building-name", "Tesztépület"]
    with pytest.raises(ValueError, match="missing parameters"):
        build_handler_arguments(
            tool=tool, profile=tmp_path / "profile.json", source=tmp_path / "source.wwp",
            output=tmp_path / "out", parameters={},
        )


def test_orientation_adapter_forces_focused_roundtrip(tmp_path: Path) -> None:
    tool = CertificationToolRegistry.load().require_executable(
        "winwatt.building.orientation.roundtrip", profile_id=PROFILE
    )
    arguments = build_handler_arguments(
        tool=tool, profile=tmp_path / "profile.json", source=tmp_path / "source.wwp",
        output=tmp_path / "out", parameters={"angle": "42"},
    )
    assert "--skip-mode-survey" in arguments
    assert arguments[-2:] == ["--angle", "42"]
    with pytest.raises(ValueError):
        build_handler_arguments(
            tool=tool, profile=tmp_path / "profile.json", source=tmp_path / "source.wwp",
            output=tmp_path / "out", parameters={"angle": "42.5"},
        )


def test_envelope_tool_adapters_use_semantic_parameters(tmp_path: Path) -> None:
    registry = CertificationToolRegistry.load()
    common = {
        "profile": tmp_path / "profile.json", "source": tmp_path / "source.wwp",
        "output": tmp_path / "out",
    }
    room = registry.require_executable(
        "winwatt.building.room.create_roundtrip", profile_id=PROFILE
    )
    assert build_handler_arguments(
        tool=room, parameters={"name": "Szoba"}, **common,
    )[-2:] == ["--name", "Szoba"]

    structure = registry.require_executable(
        "winwatt.building.structure.layered.create_roundtrip", profile_id=PROFILE
    )
    structure_args = build_handler_arguments(
        tool=structure,
        parameters={
            "template_xml": str(tmp_path / "template.xml"),
            "name": "Fal", "layer_name": "Gyapot", "thickness_cm": "10",
        }, **common,
    )
    assert structure_args[-8:] == [
        "--template-xml", str(tmp_path / "template.xml"), "--name", "Fal",
        "--layer-name", "Gyapot", "--thickness-cm", "10.0",
    ]

    boundary = registry.require_executable(
        "winwatt.building.room.boundary.assign_roundtrip", profile_id=PROFILE
    )
    assert build_handler_arguments(
        tool=boundary,
        parameters={"room_name": "Szoba", "structure_reference": "Külső fal"}, **common,
    )[-4:] == [
        "--room-name", "Szoba", "--structure-reference", "Külső fal",
    ]


def test_offline_preflight_adapter_does_not_require_wwp_source(tmp_path: Path) -> None:
    tool = CertificationToolRegistry.load().require_executable(
        "winwatt.certificate.preflight", profile_id=PROFILE
    )
    arguments = build_handler_arguments(
        tool=tool, profile=tmp_path / "profile.json", source=None,
        output=tmp_path / "out", parameters={
            "model": str(tmp_path / "model.json"), "scope": "envelope",
        },
    )
    assert arguments == [
        "--output", str(tmp_path / "out"),
        "--model", str(tmp_path / "model.json"), "--scope", "envelope",
    ]


def test_campaign_summary_adapter_is_local_file_tool(tmp_path: Path) -> None:
    tool = CertificationToolRegistry.load().require_executable(
        "winwatt.mapping.campaign.summarize", profile_id=PROFILE
    )
    arguments = build_handler_arguments(
        tool=tool, profile=tmp_path / "profile.json", source=None,
        output=tmp_path / "out", parameters={"campaign": str(tmp_path / "campaign")},
    )
    assert arguments == [
        "--output", str(tmp_path / "out"),
        "--campaign", str(tmp_path / "campaign"),
    ]


def test_webwatt_intake_adapter_uses_local_input(tmp_path: Path) -> None:
    tool = CertificationToolRegistry.load().require_executable(
        "webwatt.certificate.intake.local", profile_id=PROFILE
    )
    arguments = build_handler_arguments(
        tool=tool, profile=tmp_path / "profile.json", source=None,
        output=tmp_path / "out", parameters={"input_file": str(tmp_path / "source.xml")},
    )
    assert arguments == [
        "--output", str(tmp_path / "out"),
        "--input-file", str(tmp_path / "source.xml"),
    ]
