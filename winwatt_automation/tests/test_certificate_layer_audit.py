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
