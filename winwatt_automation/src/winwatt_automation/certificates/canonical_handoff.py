"""Deterministic handoff from the AutoWinWatt review model to shared core entities.

The handoff deliberately does not define a third canonical building model.  It
projects records onto the implemented Magyar Mentor ``core_*`` tables and adds
the field-level provenance envelope required by the ETAI BuildingModel design.
Fields that have no implemented ``core_*`` destination remain explicit
extensions and are reported as coverage gaps.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any


SCHEMA = "autowinwatt-magyar-mentor-core-handoff/v1"
MAGYAR_MENTOR_PROFILE = "core-canonical-model/20260329123000"
ETAI_PROFILE = "BuildingModel/evidence-contract-v1"
_NAMESPACE = uuid.UUID("b1292d45-49bd-56d1-9b05-fc941c6b06e7")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _stable_id(source_hash: str, kind: str, key: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{source_hash}:{kind}:{key}"))


def _element_type(value: str) -> str:
    normalized = value.casefold()
    if "ablak" in normalized or "window" in normalized:
        return "window"
    if "ajtó" in normalized or "ajto" in normalized or "door" in normalized:
        return "door"
    if "tető" in normalized or "teto" in normalized or "roof" in normalized:
        return "roof"
    if "padló" in normalized or "padlo" in normalized or "födém" in normalized or "slab" in normalized:
        return "slab"
    return "wall"


def _element_role(value: str, element_type: str) -> str:
    normalized = value.casefold()
    if element_type in {"window", "door"}:
        return "opening"
    if "talaj" in normalized or "ground" in normalized:
        return "ground"
    if "belső" in normalized or "belso" in normalized or "internal" in normalized:
        return "internal"
    if "szomszéd" in normalized or "szomszed" in normalized or "adjacent" in normalized:
        return "adjacent"
    if element_type == "roof":
        return "overhead"
    return "external"


def build_core_handoff(model: dict[str, Any]) -> dict[str, Any]:
    """Map a reviewed candidate without creating engineering values."""
    source_hash = str(model.get("reconstruction", {}).get("source_pdf_sha256") or "")
    if not source_hash:
        raise ValueError("review model is missing reconstruction.source_pdf_sha256")
    if model.get("schema") != "autowinwatt-reviewed-certificate-model/candidate-v1":
        raise ValueError("unsupported AutoWinWatt review-model schema")

    project = model.get("project") or {}
    project_id = _stable_id(source_hash, "project", str(project.get("name") or "project"))
    evidence: list[dict[str, Any]] = []
    evidence_by_payload: dict[str, str] = {}
    fields: list[dict[str, Any]] = []

    def evidence_ids(source: Any) -> list[str]:
        if not isinstance(source, dict) or not source:
            return []
        payload = dict(source)
        payload.setdefault("document_sha256", source_hash)
        key = _canonical_json(payload)
        evidence_id = evidence_by_payload.get(key)
        if evidence_id is None:
            evidence_id = _stable_id(source_hash, "evidence", key)
            evidence_by_payload[key] = evidence_id
            evidence.append({"id": evidence_id, **payload})
        return [evidence_id]

    def add_field(
        entity_id: str,
        field_path: str,
        value: Any,
        *,
        unit: str | None = None,
        source: Any = None,
        reviewed: bool = False,
        entered_by: str = "deterministic_pdf_adapter",
    ) -> None:
        if value is None:
            return
        source_ids = evidence_ids(source)
        fields.append({
            "id": _stable_id(source_hash, "field", f"{entity_id}:{field_path}"),
            "entity_id": entity_id,
            "field_path": field_path,
            "value": value,
            "unit": unit,
            "status": "approved" if reviewed else "extracted",
            "confidence": source.get("confidence") if isinstance(source, dict) else None,
            "source_evidence_ids": source_ids,
            "entered_by": entered_by,
            "revision": 1,
        })

    building_ids: dict[str, str] = {}
    buildings: list[dict[str, Any]] = []
    for index, row in enumerate(model.get("buildings") or [], 1):
        source_key = str(row.get("id") or row.get("name") or index)
        record_id = _stable_id(source_hash, "building", source_key)
        building_ids[source_key] = record_id
        building_ids[str(row.get("name") or source_key)] = record_id
        buildings.append({"id": record_id, "project_id": project_id, "name": row.get("name"), "raw_payload": row})

    space_ids: dict[str, str] = {}
    spaces: list[dict[str, Any]] = []
    space_extensions: list[dict[str, Any]] = []
    for index, row in enumerate(model.get("rooms") or [], 1):
        key = str(row.get("id") or row.get("name") or index)
        record_id = _stable_id(source_hash, "space", key)
        space_ids[key] = record_id
        review = row.get("review_basis") if isinstance(row.get("review_basis"), dict) else {}
        reviewed = bool(row.get("reviewed"))
        entered_by = str(review.get("owner") or "deterministic_pdf_adapter")
        building_ref = str(row.get("building") or "")
        spaces.append({
            "id": record_id,
            "project_id": project_id,
            "building_id": building_ids.get(building_ref),
            "level_id": None,
            "legacy_room_id": None,
            "name": row.get("name"),
            "space_number": None,
            "usage_type": None,
            "ceiling_height_cm": float(row["height_m"]) * 100 if row.get("height_m") is not None else None,
            "geometry_id": None,
            "source": "pdf_reviewed_candidate",
            "source_confidence": None,
            "notes": review.get("basis"),
            "status": "active",
        })
        space_extensions.append({
            "space_id": record_id,
            "area_m2": row.get("area_m2"),
            "volume_m3": row.get("volume_m3"),
            "temperature_c": row.get("temperature_c"),
            "review_basis": review or None,
        })
        for path, value, unit in (
            ("name", row.get("name"), None),
            ("area", row.get("area_m2"), "m2"),
            ("height", row.get("height_m"), "m"),
            ("volume", row.get("volume_m3"), "m3"),
            ("temperature", row.get("temperature_c"), "degC"),
        ):
            add_field(record_id, path, value, unit=unit, source=review, reviewed=reviewed, entered_by=entered_by)

    assembly_ids: dict[str, str] = {}
    assemblies: list[dict[str, Any]] = []
    for index, row in enumerate(model.get("structures") or [], 1):
        key = str(row.get("name") or index)
        record_id = _stable_id(source_hash, "assembly", key)
        assembly_ids[key] = record_id
        element_type = _element_type(str(row.get("type") or key))
        role = _element_role(str(row.get("type") or key), element_type)
        assemblies.append({
            "id": record_id,
            "project_id": project_id,
            "legacy_panel_id": None,
            "name": row.get("name"),
            "element_type": element_type,
            "role": role,
            "u_value": row.get("u_effective"),
            "source": "pdf_reviewed_candidate",
            "raw_payload": row,
            "status": "active",
        })
        for path, value, unit in (
            ("name", row.get("name"), None),
            ("element_type", element_type, None),
            ("u_layer", row.get("u_layer"), "W/m2K"),
            ("u_value", row.get("u_effective"), "W/m2K"),
        ):
            add_field(record_id, path, value, unit=unit, source=row.get("source"), reviewed=bool(row.get("reviewed")))

    materials: list[dict[str, Any]] = []
    material_ids: dict[str, str] = {}
    assembly_layers: list[dict[str, Any]] = []
    for index, row in enumerate(model.get("layers") or [], 1):
        assembly_id = assembly_ids.get(str(row.get("structure") or ""))
        if assembly_id is None:
            raise ValueError(f"layer {index} references an unknown structure")
        catalog_key = str(row.get("catalog_material_id") or "")
        material_id = None
        if catalog_key:
            material_id = material_ids.get(catalog_key)
            if material_id is None:
                material_id = _stable_id(source_hash, "material", catalog_key)
                material_ids[catalog_key] = material_id
                materials.append({
                    "id": material_id,
                    "name": row.get("catalog_material_name") or row.get("name"),
                    "density": row.get("density_kgm3"),
                    "thermal_conductivity": row.get("lambda_wmk"),
                    "heat_capacity": row.get("heat_capacity_kjkgk"),
                    "vapor_resistance_factor": None,
                    "source": "winwatt_catalog_review",
                    "status": "active",
                })
        sequence = int(row.get("sequence") or index)
        record_id = _stable_id(source_hash, "assembly_layer", f"{assembly_id}:{sequence}")
        assembly_layers.append({
            "id": record_id,
            "assembly_id": assembly_id,
            "material_id": material_id,
            "layer_order": sequence,
            "name": row.get("name"),
            "thickness_cm": row.get("thickness_cm"),
            "density": row.get("density_kgm3"),
            "thermal_conductivity": row.get("lambda_wmk"),
            "heat_capacity": row.get("heat_capacity_kjkgk"),
            "raw_payload": row,
        })
        for path, value, unit in (
            ("name", row.get("name"), None),
            ("thickness", row.get("thickness_cm"), "cm"),
            ("density", row.get("density_kgm3"), "kg/m3"),
            ("thermal_conductivity", row.get("lambda_wmk"), "W/mK"),
            ("heat_capacity", row.get("heat_capacity_kjkgk"), "kJ/kgK"),
        ):
            add_field(record_id, path, value, unit=unit, source=row.get("source"), reviewed=bool(row.get("reviewed")))

    elements: list[dict[str, Any]] = []
    space_elements: list[dict[str, Any]] = []
    opening_without_host = 0
    for index, row in enumerate(model.get("boundaries") or [], 1):
        space_id = space_ids.get(str(row.get("room") or ""))
        assembly_id = assembly_ids.get(str(row.get("structure") or ""))
        if space_id is None or assembly_id is None:
            raise ValueError(f"boundary {index} has an unresolved room or structure reference")
        source_type = str(row.get("winwatt_type") or row.get("structure") or "")
        element_type = _element_type(source_type)
        role = _element_role(source_type, element_type)
        record_id = _stable_id(source_hash, "element", f"{space_id}:{index}:{row.get('name')}")
        if role == "opening":
            opening_without_host += 1
        elements.append({
            "id": record_id,
            "project_id": project_id,
            "building_id": next((space["building_id"] for space in spaces if space["id"] == space_id), None),
            "level_id": None,
            "legacy_wall_id": None,
            "legacy_opening_id": None,
            "legacy_boundary_id": None,
            "legacy_panel_id": None,
            "name": row.get("name"),
            "element_type": element_type,
            "role": role,
            "geometry_id": None,
            "assembly_id": assembly_id,
            "host_element_id": None,
            "length_cm": float(row["x_m"]) * 100 if row.get("x_m") is not None else None,
            "height_cm": float(row["y_m"]) * 100 if row.get("y_m") is not None else None,
            "width_cm": None,
            "area_m2": row.get("area_m2"),
            "orientation_deg": row.get("azimuth_deg"),
            "source": "pdf_reviewed_candidate",
            "source_confidence": None,
            "raw_payload": row,
            "status": "active",
        })
        space_elements.append({
            "id": _stable_id(source_hash, "space_element", f"{space_id}:{record_id}"),
            "space_id": space_id,
            "element_id": record_id,
            "relation_role": "contains_opening" if role == "opening" else "bounds",
            "boundary_order": index,
        })
        for path, value, unit in (
            ("name", row.get("name"), None),
            ("area", row.get("area_m2"), "m2"),
            ("length", row.get("x_m"), "m"),
            ("height", row.get("y_m"), "m"),
            ("orientation", row.get("azimuth_deg"), "deg"),
            ("heat_loss", row.get("heat_loss_wk"), "W/K"),
        ):
            add_field(record_id, path, value, unit=unit, source=row.get("source"), reviewed=True)

    systems_extension: list[dict[str, Any]] = []
    for index, row in enumerate(model.get("systems") or [], 1):
        record_id = _stable_id(source_hash, "system", f"{index}:{row.get('name')}:{row.get('type')}")
        systems_extension.append({"id": record_id, "project_id": project_id, **row})
        for key, value in row.items():
            if key in {"source", "reviewed", "status"} or isinstance(value, (dict, list)):
                continue
            add_field(record_id, key, value, source=row.get("source"), reviewed=bool(row.get("reviewed")))

    gaps = [
        {
            "code": "systems_not_in_magyar_mentor_core",
            "count": len(systems_extension),
            "handling": "preserved in systems_extension pending shared core system tables",
        },
        {
            "code": "space_energy_metrics_not_in_core_spaces",
            "count": len(space_extensions),
            "handling": "preserved in space_metrics_extension and ETAI field values",
        },
        {
            "code": "source_entities_have_no_stable_uuid",
            "count": len(spaces) + len(assemblies) + len(assembly_layers) + len(elements),
            "handling": "deterministic transfer UUIDs derived from PDF hash and source keys",
        },
    ]
    if not any(row.get("geometry_id") for row in spaces + elements):
        gaps.append({
            "code": "no_plan_geometry_in_source_pdf",
            "count": len(spaces) + len(elements),
            "handling": "no core_geometries records invented",
        })
    if opening_without_host:
        gaps.append({
            "code": "opening_host_element_unresolved",
            "count": opening_without_host,
            "handling": "host_element_id remains null",
        })

    handoff = {
        "schema": SCHEMA,
        "source_model": {
            "schema": model.get("schema"),
            "sha256": _digest(model),
            "source_pdf_sha256": source_hash,
        },
        "target_contracts": {
            "persistence": MAGYAR_MENTOR_PROFILE,
            "domain": ETAI_PROFILE,
            "persistence_mode": "portable_snapshot_requires_target_project_binding",
        },
        "project": {"id": project_id, **project},
        "core_records": {
            "core_geometries": [],
            "core_spaces": spaces,
            "core_materials": materials,
            "core_assemblies": assemblies,
            "core_assembly_layers": assembly_layers,
            "core_elements": elements,
            "core_space_elements": space_elements,
        },
        "extensions": {
            "buildings": buildings,
            "space_metrics": space_extensions,
            "systems": systems_extension,
        },
        "etai": {"evidence": evidence, "field_values": fields},
        "coverage": {
            "status": "review_required" if gaps else "complete",
            "source_counts": {
                "buildings": len(model.get("buildings") or []),
                "rooms": len(model.get("rooms") or []),
                "structures": len(model.get("structures") or []),
                "layers": len(model.get("layers") or []),
                "boundaries": len(model.get("boundaries") or []),
                "systems": len(model.get("systems") or []),
            },
            "mapped_counts": {
                "core_spaces": len(spaces),
                "core_materials": len(materials),
                "core_assemblies": len(assemblies),
                "core_assembly_layers": len(assembly_layers),
                "core_elements": len(elements),
                "core_space_elements": len(space_elements),
                "etai_evidence": len(evidence),
                "etai_field_values": len(fields),
                "systems_extension": len(systems_extension),
            },
            "gaps": gaps,
            "engineering_values_inferred": False,
        },
    }
    return handoff


def write_core_handoff(model_path: Path, output_dir: Path) -> dict[str, Any]:
    model_path = model_path.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    model = json.loads(model_path.read_text(encoding="utf-8"))
    handoff = build_core_handoff(model)
    handoff_path = output_dir / "canonical_core_handoff.json"
    report_path = output_dir / "coverage_report.json"
    handoff_path.write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "status": handoff["coverage"]["status"],
        "source_model": str(model_path),
        "source_model_sha256": handoff["source_model"]["sha256"],
        "handoff": str(handoff_path),
        "handoff_sha256": hashlib.sha256(handoff_path.read_bytes()).hexdigest(),
        "target_contracts": handoff["target_contracts"],
        **handoff["coverage"],
        "llm_used": False,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
