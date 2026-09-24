"""Use the local WinWatt material catalogue before proposing any new material."""
from __future__ import annotations

from pathlib import Path

from winwatt_automation.certificates.materials import load_catalog, match_by_name


def resolve_layers(layers: list[dict], catalog_xml: Path | None) -> tuple[list[dict], list[dict], list[str]]:
    if catalog_xml is None:
        return layers, [], ["No local material catalogue supplied; layer material assignment remains unresolved."] if layers else []
    catalog=load_catalog(catalog_xml)
    decisions=[]; warnings=[]; resolved=[]
    for layer in layers:
        decision=match_by_name(str(layer["name"]),catalog)
        record=decision.model_dump(mode="json")
        record["structure"]=layer["structure"]; record["sequence"]=layer["sequence"]
        decisions.append(record)
        enriched=dict(layer)
        if decision.status=="catalog" and decision.candidate:
            enriched.update({"catalog_material_id":decision.candidate.material_id,"density_kgm3":decision.candidate.density_kgm3,"lambda_wmk":decision.candidate.lambda_wmk,"heat_capacity_kjkgk":decision.candidate.heat_capacity_kjkgk})
        elif decision.status=="review":
            warnings.append(f"layer {layer['structure']}/{layer['sequence']} {layer['name']}: {decision.reason}")
        resolved.append(enriched)
    return resolved,decisions,warnings
