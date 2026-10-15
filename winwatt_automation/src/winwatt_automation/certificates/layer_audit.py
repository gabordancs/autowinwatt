"""Traceable local material audit for reviewed certificate layers."""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from .materials import (
    PHYSICAL_PROPERTY_FIELDS,
    find_materials_by_exact_name,
    find_materials_by_properties,
    load_catalog,
    material_agrees_with_supplied_properties,
    match_material,
    normalize_material_name,
)

def audit_layers(model_path: Path, catalog_path: Path, target: Path) -> dict:
    model = json.loads(model_path.read_text(encoding="utf-8")); catalog = load_catalog(catalog_path)
    rows = []
    for layer in model.get("layers", []):
        supplied_properties = {
            key: layer.get(key) for key in PHYSICAL_PROPERTY_FIELDS
            if layer.get(key) is not None
        }
        property_matches = find_materials_by_properties(
            catalog,
            lambda_wmk=layer.get("lambda_wmk"),
            density_kgm3=layer.get("density_kgm3"),
            heat_capacity_kjkgk=layer.get("heat_capacity_kjkgk"),
        )
        exact_name_matches = find_materials_by_exact_name(catalog, layer["name"])
        approval = layer.get("material_approval") if layer.get("reviewed") is True else None
        if approval:
            approved_id = str(approval.get("catalog_material_id") or "")
            approved_name = str(approval.get("catalog_material_name") or "")
            selected = next(
                (item for item in catalog if str(item.material_id or "") == approved_id), None
            )
            property_ids = {str(item.material_id or "") for item in property_matches}
            unique_exact_name_agreement = (
                len(exact_name_matches) == 1
                and str(exact_name_matches[0].material_id or "") == approved_id
                and material_agrees_with_supplied_properties(
                    exact_name_matches[0],
                    lambda_wmk=layer.get("lambda_wmk"),
                    density_kgm3=layer.get("density_kgm3"),
                    heat_capacity_kjkgk=layer.get("heat_capacity_kjkgk"),
                )
            )
            valid = (
                approval.get("approved") is True
                and selected is not None
                and selected.name == approved_name
                and (approved_id in property_ids or unique_exact_name_agreement)
            )
            decision_data = {
                "source_name": layer["name"],
                "status": "catalog" if valid else "review",
                "candidate": selected.model_dump(mode="json") if selected else None,
                "reason": (
                    "Ember által jóváhagyott, minden megadott fizikai tulajdonságban "
                    "egyező számítási katalógusmegfelelő; az eredeti anyagnév megmarad."
                    if valid else
                    "A rögzített emberi jóváhagyás nem igazolható a katalógus és a "
                    "megadott fizikai tulajdonságok alapján."
                ),
                "confidence": 1.0 if valid else 0.0,
                "decision_mode": (
                    "human_approved_exact_name_and_supplied_physics"
                    if valid and unique_exact_name_agreement
                    else "human_approved_property_equivalence"
                ),
            }
        else:
            decision = match_material(layer["name"], catalog, lambda_wmk=layer.get("lambda_wmk"), density_kgm3=layer.get("density_kgm3"), heat_capacity_kjkgk=layer.get("heat_capacity_kjkgk"), family=layer.get("type"))
            decision_data = decision.model_dump(mode="json")
        source_data = {key: layer.get(key) for key in ("structure", "name", "sequence", "thickness_cm", "lambda_wmk", "density_kgm3", "heat_capacity_kjkgk", "r")}
        rows.append({
            "source": source_data,
            "decision": decision_data,
            "property_search": {
                "semantics": "calculation_property_equivalence_only",
                "relative_tolerance": 0.001,
                "supplied_properties": supplied_properties,
                "match_count": len(property_matches),
                "unique": len(property_matches) == 1,
                "matches": [item.model_dump(mode="json") for item in property_matches],
            },
            "exact_name_search": {
                "match_count": len(exact_name_matches),
                "unique": len(exact_name_matches) == 1,
                "matches": [item.model_dump(mode="json") for item in exact_name_matches],
            },
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
                "human_approval": approval,
            },
        })
    payload = {"source_model": str(model_path), "catalog": str(catalog_path), "catalog_material_count": len(catalog), "summary": dict(Counter(row["decision"]["status"] for row in rows)), "layers": rows}
    target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return payload
