"""Traceable local material audit for reviewed certificate layers."""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from .materials import load_catalog, match_material, normalize_material_name

def audit_layers(model_path: Path, catalog_path: Path, target: Path) -> dict:
    model = json.loads(model_path.read_text(encoding="utf-8")); catalog = load_catalog(catalog_path)
    rows = []
    for layer in model.get("layers", []):
        decision = match_material(layer["name"], catalog, lambda_wmk=layer.get("lambda_wmk"), density_kgm3=layer.get("density_kgm3"), heat_capacity_kjkgk=layer.get("heat_capacity_kjkgk"), family=layer.get("type"))
        decision_data = decision.model_dump(mode="json")
        source_data = {key: layer.get(key) for key in ("structure", "name", "sequence", "thickness_cm", "lambda_wmk", "density_kgm3", "heat_capacity_kjkgk", "r")}
        rows.append({
            "source": source_data,
            "decision": decision_data,
            "source_reference": "reviewed certificate geometry model",
            "trace": {
                "source_document": model.get("project", {}).get("source"),
                "source_element": f"{layer.get('structure', '')} / {layer.get('sequence', '')}",
                "original_value": layer["name"],
                "normalized_value": normalize_material_name(layer["name"]),
                "selected_winwatt_object": decision_data.get("candidate"),
                "confidence": decision_data.get("confidence"),
                "decision_mode": decision_data.get("decision_mode"),
                "reason": decision_data.get("reason"),
            },
        })
    payload = {"source_model": str(model_path), "catalog": str(catalog_path), "catalog_material_count": len(catalog), "summary": dict(Counter(row["decision"]["status"] for row in rows)), "layers": rows}
    target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return payload
