import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from winwatt_automation.certificates.webwatt_handoff import load_webwatt_handoff


def catalog(tmp_path: Path) -> Path:
    path = tmp_path / "materials.xml"
    path.write_text("""<WinWatt32Project><WinWatt32Material><ItemHeader><ItemName>Airrock ND</ItemName><ItemPath>Szigetelés</ItemPath><ID>842</ID></ItemHeader><ThermalCond>0.035</ThermalCond><Density>40</Density><HeatCapacity>1.03</HeatCapacity></WinWatt32Material></WinWatt32Project>""", encoding="utf-8")
    return path


def payload() -> dict:
    return {"schema_version": "webwatt-winwatt-handoff/v1", "project_id": "p-1", "generated_at": "2026-10-05T12:00:00Z", "ready": True, "blockers": [], "layers": [{"candidate_id": "c-1", "layer_reference": "wall:0#claim", "structure_name": "Külső fal", "sequence": 1, "catalog_material_id": "842", "catalog_material_name": "Airrock ND", "catalog_material_path": "Szigetelés", "thickness_mm": 150, "thermal_conductivity": 0.035, "density": 40, "heat_capacity": 1.03, "review": {"status": "edited", "reviewer_id": "u-1", "reviewed_at": "2026-10-05T11:00:00Z"}, "evidence": {"source_file": "layers.pdf", "source_sha256": "a" * 64, "page": 2, "bbox": [0.1, 0.2, 0.4, 0.3]}}]}


def test_loads_only_reviewed_catalog_layer(tmp_path: Path) -> None:
    path = tmp_path / "handoff.json"; path.write_text(json.dumps(payload()), encoding="utf-8")
    package, fragment = load_webwatt_handoff(path, catalog(tmp_path))
    assert package.ready is True
    assert fragment["layers"][0]["catalog_material_id"] == "842"
    assert fragment["layers"][0]["thickness_cm"] == 15


def test_rejects_blockers_and_catalog_mismatch(tmp_path: Path) -> None:
    blocked = payload(); blocked["ready"] = False; blocked["blockers"] = [{"reason": "pending"}]
    path = tmp_path / "blocked.json"; path.write_text(json.dumps(blocked), encoding="utf-8")
    with pytest.raises(ValidationError): load_webwatt_handoff(path, catalog(tmp_path))
    mismatch = payload(); mismatch["layers"][0]["catalog_material_id"] = "999"
    path.write_text(json.dumps(mismatch), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown catalog material"): load_webwatt_handoff(path, catalog(tmp_path))
