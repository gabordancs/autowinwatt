from __future__ import annotations

from copy import deepcopy

import pytest

from winwatt_automation.certificates.canonical_handoff import build_core_handoff


def _model() -> dict:
    source = {"kind": "pdf", "page": 2}
    return {
        "schema": "autowinwatt-reviewed-certificate-model/candidate-v1",
        "project": {"name": "P", "heated_area_m2": 10, "heated_volume_m3": 25},
        "buildings": [{"id": "B1", "name": "Building"}],
        "rooms": [{
            "name": "R1", "building": "B1", "area_m2": 10, "height_m": 2.5,
            "volume_m3": 25, "temperature_c": 20, "reviewed": True,
            "review_basis": {"accepted": True, "owner": "human_user"},
        }],
        "structures": [{
            "name": "Wall", "type": "külső fal", "u_effective": 0.5,
            "source": source, "reviewed": True,
        }],
        "layers": [{
            "structure": "Wall", "sequence": 1, "name": "Brick",
            "thickness_cm": 30, "lambda_wmk": 0.7, "source": source,
        }],
        "boundaries": [{
            "name": "Wall 1", "room": "R1", "structure": "Wall",
            "winwatt_type": "külső fal", "x_m": 4, "y_m": 2.5,
            "area_m2": 10, "azimuth_deg": 90, "source": {"kind": "pdf", "page": 4},
        }],
        "systems": [{
            "name": "Heater", "type": "heating", "served_area_m2": 10,
            "source": {"kind": "pdf", "page": 5}, "reviewed": False,
        }],
        "reconstruction": {"source_pdf_sha256": "a" * 64},
    }


def test_build_core_handoff_maps_entities_without_inventing_geometry() -> None:
    handoff = build_core_handoff(_model())

    records = handoff["core_records"]
    assert records["core_geometries"] == []
    assert len(records["core_spaces"]) == 1
    assert len(records["core_assemblies"]) == 1
    assert len(records["core_assembly_layers"]) == 1
    assert len(records["core_elements"]) == 1
    assert len(records["core_space_elements"]) == 1
    assert handoff["extensions"]["systems"][0]["name"] == "Heater"
    assert handoff["coverage"]["engineering_values_inferred"] is False
    assert {gap["code"] for gap in handoff["coverage"]["gaps"]} >= {
        "systems_not_in_magyar_mentor_core",
        "no_plan_geometry_in_source_pdf",
    }


def test_build_core_handoff_is_deterministic() -> None:
    first = build_core_handoff(_model())
    second = build_core_handoff(deepcopy(_model()))
    assert first == second


def test_build_core_handoff_rejects_unknown_boundary_reference() -> None:
    model = _model()
    model["boundaries"][0]["room"] = "missing"
    with pytest.raises(ValueError, match="unresolved room or structure"):
        build_core_handoff(model)
