"""Traceable local material audit for reviewed certificate layers."""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from .materials import load_catalog, match_material

def audit_layers(model_path: Path, catalog_path: Path, target: Path) -> dict:
    model = json.loads(model_path.read_text(encoding="utf-8")); catalog = load_catalog(catalog_path)
    rows = []
    for layer in model.get("layers", []):
        decision = match_material(layer["name"], catalog, lambda_wmk=layer.get("lambda_wmk"), density_kgm3=layer.get("density_kgm3"), heat_capacity_kjkgk=layer.get("heat_capacity_kjkgk"), family=layer.get("type"))
        rows.append({"source": {key: layer.get(key) for key in ("structure", "name", "sequence", "thickness_cm", "lambda_wmk", "density_kgm3", "heat_capacity_kjkgk", "r")}, "decision": decision.model_dump(mode="json"), "source_reference": "reviewed certificate geometry model"})
    payload = {"source_model": str(model_path), "catalog": str(catalog_path), "catalog_material_count": len(catalog), "summary": dict(Counter(row["decision"]["status"] for row in rows)), "layers": rows}
    target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return payload
