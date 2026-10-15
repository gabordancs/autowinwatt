import json
from pathlib import Path

from winwatt_automation.certificates.layer_audit import audit_layers


def test_layer_audit_emits_a_complete_decision_trace(tmp_path: Path) -> None:
    model = {"project": {"source": "source.pdf"}, "layers": [{
        "structure": "Fal", "name": "cementvakolat", "sequence": 1,
        "thickness_cm": 2, "lambda_wmk": 0.72, "density_kgm3": 1700,
        "heat_capacity_kjkgk": 0.88, "r": 0.03,
    }]}
    model_path = tmp_path / "model.json"; model_path.write_text(json.dumps(model), encoding="utf-8")
    catalog_path = tmp_path / "catalog.xml"; catalog_path.write_text("""<WinWatt32Project><WinWatt32Material><ItemHeader><ItemName>cementvakolat</ItemName><ItemPath>Falazat</ItemPath><ID>7</ID></ItemHeader><Density>1700</Density><ThermalCond>0.72</ThermalCond><HeatCapacity>0.88</HeatCapacity></WinWatt32Material></WinWatt32Project>""", encoding="utf-8")
    result = audit_layers(model_path, catalog_path, tmp_path / "audit.json")
    trace = result["layers"][0]["trace"]
    assert trace["original_value"] == "cementvakolat"
    assert trace["normalized_value"] == "cementvakolat"
    assert trace["selected_winwatt_object"]["material_id"] == "7"
    assert trace["decision_mode"] == "catalog_match"
    property_search = result["layers"][0]["property_search"]
    assert property_search["semantics"] == "calculation_property_equivalence_only"
    assert property_search["unique"] is True
    assert property_search["matches"][0]["material_id"] == "7"


def test_layer_audit_accepts_traceable_human_approved_property_equivalence(tmp_path: Path) -> None:
    model = {"project": {"source": "source.pdf"}, "layers": [{
        "structure": "Tető", "name": "gipszkarton", "sequence": 1,
        "thickness_cm": 1.9, "lambda_wmk": 0.24, "density_kgm3": 1000,
        "heat_capacity_kjkgk": 0.84, "reviewed": True,
        "material_approval": {
            "approved": True, "catalog_material_id": "354",
            "catalog_material_name": "tiszta gipszlapok 1", "owner": "human_user",
        },
    }]}
    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(model), encoding="utf-8")
    catalog_path = tmp_path / "catalog.xml"
    catalog_path.write_text(
        """<WinWatt32Project><WinWatt32Material><ItemHeader><ItemName>tiszta gipszlapok 1</ItemName><ID>354</ID></ItemHeader><Density>1000</Density><ThermalCond>0.24</ThermalCond><HeatCapacity>0.84</HeatCapacity></WinWatt32Material></WinWatt32Project>""",
        encoding="utf-8",
    )
    result = audit_layers(model_path, catalog_path, tmp_path / "audit.json")
    row = result["layers"][0]
    assert row["decision"]["status"] == "catalog"
    assert row["decision"]["decision_mode"] == "human_approved_property_equivalence"
    assert row["trace"]["human_approval"]["owner"] == "human_user"


def test_layer_audit_accepts_unique_exact_name_without_inventing_missing_physics(tmp_path: Path) -> None:
    model = {"project": {"source": "source.pdf"}, "layers": [{
        "structure": "Tető", "name": "Mastermax 3 CLASSIC", "sequence": 1,
        "thickness_cm": 0.1, "reviewed": True,
        "material_approval": {
            "approved": True, "catalog_material_id": "950",
            "catalog_material_name": "Mastermax 3 CLASSIC", "owner": "human_user",
        },
    }]}
    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(model), encoding="utf-8")
    catalog_path = tmp_path / "catalog.xml"
    catalog_path.write_text(
        """<WinWatt32Project><WinWatt32Material><ItemHeader><ItemName>Mastermax 3 CLASSIC</ItemName><ID>950</ID></ItemHeader><Density>0</Density><ThermalCond>0</ThermalCond><HeatCapacity>0</HeatCapacity></WinWatt32Material></WinWatt32Project>""",
        encoding="utf-8",
    )
    result = audit_layers(model_path, catalog_path, tmp_path / "audit.json")
    row = result["layers"][0]
    assert row["decision"]["status"] == "catalog"
    assert row["decision"]["decision_mode"] == "human_approved_exact_name_and_supplied_physics"
    assert row["property_search"]["match_count"] == 0
    assert row["exact_name_search"]["unique"] is True
