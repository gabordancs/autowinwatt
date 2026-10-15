"""Prepare traceable WinWatt catalogue approvals for PDF-derived OENY layers.

The worker is deliberately fail-closed.  It accepts a layer only when either
the normalized catalogue name is unique and every supplied physical property
agrees, or the complete supplied physical-property tuple has one unique match.
It never fills a physical property that is absent from the source PDF.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

from winwatt_automation.certificates.materials import (
    PHYSICAL_PROPERTY_FIELDS,
    find_materials_by_exact_name,
    find_materials_by_properties,
    load_catalog,
    material_agrees_with_supplied_properties,
)


def prepare(
    model: dict[str, Any],
    decisions: dict[str, Any],
    catalog: list[Any],
    *,
    owner: str,
    authorization: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    approvals: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for layer in model.get("layers", []):
        exact = find_materials_by_exact_name(catalog, layer["name"])
        property_matches = find_materials_by_properties(
            catalog,
            lambda_wmk=layer.get("lambda_wmk"),
            density_kgm3=layer.get("density_kgm3"),
            heat_capacity_kjkgk=layer.get("heat_capacity_kjkgk"),
        )
        candidate = None
        mode = None
        if len(exact) == 1 and material_agrees_with_supplied_properties(
            exact[0],
            lambda_wmk=layer.get("lambda_wmk"),
            density_kgm3=layer.get("density_kgm3"),
            heat_capacity_kjkgk=layer.get("heat_capacity_kjkgk"),
        ):
            candidate = exact[0]
            mode = "unique_exact_name_with_supplied_physics_agreement"
        elif len(property_matches) == 1 and all(
            layer.get(key) is not None for key in PHYSICAL_PROPERTY_FIELDS
        ):
            candidate = property_matches[0]
            mode = "unique_complete_physical_property_tuple"

        row = {
            "structure": layer.get("structure"),
            "sequence": layer.get("sequence"),
            "source_name": layer.get("name"),
            "exact_name_match_count": len(exact),
            "physical_property_match_count": len(property_matches),
            "decision_mode": mode or "unresolved",
            "catalog_material_id": candidate.material_id if candidate else None,
            "catalog_material_name": candidate.name if candidate else None,
        }
        rows.append(row)
        if candidate is None:
            continue
        supplied = {
            key: layer.get(key) for key in PHYSICAL_PROPERTY_FIELDS
            if layer.get(key) is not None
        }
        approvals.append({
            "structure": str(layer["structure"]),
            "sequence": int(layer["sequence"]),
            "source_name": str(layer["name"]),
            "catalog_material_id": str(candidate.material_id),
            "catalog_material_name": str(candidate.name),
            "approval_basis": (
                f"{mode}; source-supplied physical properties: {supplied}. "
                "No missing physical property was inferred."
            ),
            "use_semantics": "calculation_property_equivalence_only",
            "preserve_source_name": True,
            "approved": True,
            "owner": owner,
            "authorization": authorization,
            "date": date.today().isoformat(),
        })

    output = deepcopy(decisions)
    output["material_approvals"] = approvals
    unresolved = [row for row in rows if row["decision_mode"] == "unresolved"]
    report = {
        "schema": "autowinwatt-material-approval-preparation/v1",
        "status": "ready" if not unresolved else "review_required",
        "layer_count": len(rows),
        "approval_count": len(approvals),
        "unresolved_count": len(unresolved),
        "llm_used": False,
        "policy": (
            "unique exact normalized name plus agreement of all supplied physical "
            "properties, or unique match of the complete physical-property tuple"
        ),
        "authorization": authorization,
        "layers": rows,
    }
    return output, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--decisions", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--authorization", required=True)
    args = parser.parse_args()
    for target in (args.output, args.report):
        if target.exists():
            raise FileExistsError(f"output must be new: {target}")
    model = json.loads(args.model.resolve(strict=True).read_text(encoding="utf-8"))
    decisions = json.loads(args.decisions.resolve(strict=True).read_text(encoding="utf-8"))
    enriched, report = prepare(
        model,
        decisions,
        load_catalog(args.catalog.resolve(strict=True)),
        owner=args.owner,
        authorization=args.authorization,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(enriched, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "layer_count", "approval_count", "unresolved_count", "llm_used")}))
    return 0 if report["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
