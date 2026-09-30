"""Deterministic release gates for reviewed WinWatt certificate models."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .geometry import is_vertical_wall, xy_area
from .layer_audit import audit_layers
from .validation import validate_native_readback


GateStatus = Literal["passed", "review_required", "failed"]
PreflightScope = Literal["envelope", "g5_calculation", "full_certificate"]
_RANK = {"passed": 0, "review_required": 1, "failed": 2}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check(check_id: str, status: GateStatus, summary: str, issues: list[str] | None = None) -> dict[str, Any]:
    return {"check_id": check_id, "status": status, "summary": summary, "issues": issues or []}


def _unique(values: list[str], label: str) -> list[str]:
    seen: set[str] = set()
    return [f"duplicate {label}: {value}" for value in values if value in seen or seen.add(value)]


def validate_model_contract(model: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    project = model.get("project") or {}
    issues = []
    for key in ("name", "heated_area_m2", "heated_volume_m3"):
        if project.get(key) in (None, ""):
            issues.append(f"missing project.{key}")
    for key in ("heated_area_m2", "heated_volume_m3"):
        try:
            if float(project.get(key, 0)) <= 0:
                issues.append(f"project.{key} must be positive")
        except (TypeError, ValueError):
            issues.append(f"project.{key} must be numeric")
    checks.append(_check(
        "model.project", "failed" if issues else "passed",
        "Project identity and heated totals are present.", issues,
    ))

    rooms = list(model.get("rooms") or [])
    structures = list(model.get("structures") or [])
    boundaries = list(model.get("boundaries") or [])
    room_names = [str(item.get("name") or "") for item in rooms]
    structure_names = [str(item.get("name") or "") for item in structures]
    reference_issues = _unique(room_names, "room name") + _unique(structure_names, "structure name")
    if not rooms:
        reference_issues.append("model has no rooms")
    if not structures:
        reference_issues.append("model has no structures")
    room_set, structure_set = set(room_names), set(structure_names)
    for item in boundaries:
        name = str(item.get("name") or "<unnamed boundary>")
        if item.get("room") not in room_set:
            reference_issues.append(f"{name}: unknown room {item.get('room')!r}")
        if item.get("structure") not in structure_set:
            reference_issues.append(f"{name}: unknown structure {item.get('structure')!r}")
        try:
            if float(item.get("area_m2", 0)) <= 0:
                reference_issues.append(f"{name}: area_m2 must be positive")
        except (TypeError, ValueError):
            reference_issues.append(f"{name}: area_m2 must be numeric")
    checks.append(_check(
        "model.references", "failed" if reference_issues else "passed",
        "Rooms, structures and boundary references are internally consistent.", reference_issues,
    ))

    geometry_failed: list[str] = []
    geometry_review: list[str] = []
    strict = bool(project.get("require_wall_xy"))
    for boundary in boundaries:
        if not is_vertical_wall(boundary):
            continue
        name = str(boundary.get("name") or "<unnamed wall>")
        try:
            geometry = xy_area(boundary)
        except (TypeError, ValueError) as exc:
            geometry_failed.append(str(exc))
            continue
        if geometry is None:
            (geometry_failed if strict else geometry_review).append(
                f"{name}: missing X length and Y height"
            )
    geometry_status: GateStatus = "failed" if geometry_failed else (
        "review_required" if geometry_review else "passed"
    )
    checks.append(_check(
        "model.wall_geometry", geometry_status,
        "Vertical wall X/Y/A geometry follows the shared contract.",
        geometry_failed + geometry_review,
    ))

    total_area = sum(float(item.get("area_m2") or 0) for item in rooms)
    total_volume = sum(float(item.get("volume_m3") or (
        float(item.get("area_m2") or 0) * float(item.get("height_m") or 0)
    )) for item in rooms)
    total_issues = []
    if project.get("heated_area_m2") is not None and not math.isclose(
        total_area, float(project["heated_area_m2"]), abs_tol=0.02
    ):
        total_issues.append(f"room area sum {total_area:.6f} != project {float(project['heated_area_m2']):.6f}")
    if project.get("heated_volume_m3") is not None and not math.isclose(
        total_volume, float(project["heated_volume_m3"]), abs_tol=0.02
    ):
        total_issues.append(f"room volume sum {total_volume:.6f} != project {float(project['heated_volume_m3']):.6f}")
    checks.append(_check(
        "model.heated_totals", "failed" if total_issues else "passed",
        "Room totals agree with project heated area and volume.", total_issues,
    ))
    return checks


def _difference_issues(report: dict[str, Any], tolerance: float) -> list[str]:
    issues: list[str] = []

    def inspect(prefix: str, value: Any) -> None:
        if isinstance(value, dict) and {"expected", "actual", "absolute"}.issubset(value):
            if abs(float(value["absolute"])) > tolerance:
                issues.append(
                    f"{prefix}: expected {value['expected']}, actual {value['actual']}, "
                    f"absolute {value['absolute']}"
                )
            return
        if isinstance(value, dict):
            for key, child in value.items():
                if key not in {"wall_xy_issues"}:
                    inspect(f"{prefix}.{key}" if prefix else key, child)

    for key in (
        "totals", "surface_by_source_type_m2", "surface_by_azimuth_deg_m2",
        "room_conditions", "opening_glass_ratio_percent", "wall_xy_geometry",
    ):
        inspect(key, report.get(key, {}))
    issues.extend(str(item) for item in report.get("wall_xy_issues", []))
    return issues


def validate_readback_gate(
    *, model: dict[str, Any], report: dict[str, Any], tolerance: float,
) -> dict[str, Any]:
    expected_counts = {
        "buildings": len(model.get("buildings") or [model.get("project", {})]),
        "rooms": len(model.get("rooms") or []),
        "structures": len(model.get("structures") or []),
        "boundaries": len(model.get("boundaries") or []),
        "layer_rows": len(model.get("layers") or []),
    }
    issues = [
        f"counts.{key}: expected {expected}, actual {report.get('counts', {}).get(key)}"
        for key, expected in expected_counts.items()
        if report.get("counts", {}).get(key) != expected
    ]
    issues.extend(_difference_issues(report, tolerance))
    return _check(
        "winwatt.readback", "failed" if issues else "passed",
        "Reopened native XML agrees with the reviewed source model.", issues,
    )


def validate_g5_systems(model: dict[str, Any]) -> dict[str, Any]:
    """Require reviewed building-system inputs before WinWatt calculation."""
    systems = list(model.get("systems") or [])
    issues: list[str] = []
    if not systems:
        issues.append("reviewed systems are missing")
    building_refs: set[str] = set()
    for index, item in enumerate(systems, start=1):
        if not isinstance(item, dict):
            issues.append(f"system {index}: object expected")
            continue
        label = str(item.get("name") or item.get("type") or f"system {index}")
        reviewed = item.get("reviewed") is True or str(item.get("review_status") or item.get("status") or "").casefold() in {
            "approved", "reviewed", "passed", "jóváhagyva", "ellenőrzött",
        }
        if not reviewed:
            issues.append(f"{label}: human system review is missing")
        meaningful = any(
            item.get(key) not in (None, "", [], {})
            for key in ("type", "heating", "heat_generator", "generator", "selections", "components")
        )
        if not meaningful:
            issues.append(f"{label}: system selection is empty")
        reference = item.get("building_id") or item.get("building") or item.get("building_name")
        if reference not in (None, ""):
            building_refs.add(str(reference))

    buildings = list(model.get("buildings") or [])
    expected_refs = {
        str(item.get("id") or item.get("name")) if isinstance(item, dict) else str(item)
        for item in buildings
        if (not isinstance(item, dict)) or item.get("id") or item.get("name")
    }
    if len(expected_refs) > 1 and not building_refs:
        issues.append("systems are not assigned to buildings")
    elif building_refs and expected_refs:
        missing = sorted(expected_refs.difference(building_refs))
        if missing:
            issues.append(f"buildings without reviewed systems: {', '.join(missing)}")
    return _check(
        "g5.systems_review", "review_required" if issues else "passed",
        "Building-service systems are populated and carry human review evidence.", issues,
    )


def run_preflight(
    *, model_path: Path, output_dir: Path, readback_xml: Path | None = None,
    catalog_xml: Path | None = None, scope: PreflightScope = "full_certificate",
    tolerance: float = 0.02,
) -> dict[str, Any]:
    model_path = model_path.resolve(strict=True)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    model = json.loads(model_path.read_text(encoding="utf-8"))
    checks = validate_model_contract(model)
    artifacts: dict[str, str] = {}

    layers = list(model.get("layers") or [])
    if catalog_xml is not None:
        catalog_xml = catalog_xml.resolve(strict=True)
        audit_path = output_dir / "layer_audit.json"
        audit = audit_layers(model_path, catalog_xml, audit_path)
        unresolved = int(audit.get("summary", {}).get("review", 0)) + int(audit.get("summary", {}).get("new", 0))
        checks.append(_check(
            "materials.catalog", "review_required" if unresolved else "passed",
            "Layer materials were matched against the local WinWatt catalogue.",
            [f"{unresolved} layer material decisions require review"] if unresolved else [],
        ))
        artifacts["layer_audit"] = str(audit_path)
    elif layers:
        checks.append(_check(
            "materials.catalog", "review_required",
            "Layers exist but no local material catalogue was supplied.",
            [f"{len(layers)} layers are not catalogue-audited"],
        ))
    else:
        checks.append(_check(
            "materials.catalog", "passed",
            "The reviewed model contains no explicit layer rows to catalogue-audit.",
        ))

    if readback_xml is not None:
        readback_xml = readback_xml.resolve(strict=True)
        validation = validate_native_readback(model_path, readback_xml)
        validation_path = output_dir / "readback_validation.json"
        validation_path.write_text(
            json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        checks.append(validate_readback_gate(model=model, report=validation, tolerance=tolerance))
        artifacts["readback_validation"] = str(validation_path)
    else:
        checks.append(_check(
            "winwatt.readback", "review_required",
            "No reopened WinWatt native XML was supplied.",
            ["save/reopen readback validation is missing"],
        ))

    systems = list(model.get("systems") or [])
    results = model.get("calculation_results") or {}
    if scope in {"g5_calculation", "full_certificate"}:
        checks.append(validate_g5_systems(model))
    if scope == "full_certificate":
        checks.append(_check(
            "certificate.calculation", "passed" if results else "review_required",
            "WinWatt calculation results are attached to the reviewed model.",
            [] if results else ["calculation results are missing"],
        ))

    overall: GateStatus = max((item["status"] for item in checks), key=_RANK.__getitem__)
    g5_check_ids = {
        "model.project", "model.references", "model.wall_geometry", "model.heated_totals",
        "materials.catalog", "winwatt.readback", "g5.systems_review",
    }
    g5_checks = [item for item in checks if item["check_id"] in g5_check_ids]
    g5_ready = (
        scope in {"g5_calculation", "full_certificate"}
        and any(item["check_id"] == "g5.systems_review" for item in g5_checks)
        and all(item["status"] == "passed" for item in g5_checks)
    )
    readiness = {
        "geometry_ready": all(item["status"] == "passed" for item in checks if item["check_id"].startswith("model.")),
        "materials_ready": next(item["status"] for item in checks if item["check_id"] == "materials.catalog") == "passed",
        "xml_readback_ready": next(item["status"] for item in checks if item["check_id"] == "winwatt.readback") == "passed",
        "systems_ready": bool(systems),
        "calculation_ready": bool(results),
        "g5_calculation_input_ready": g5_ready,
        "engineer_review_required": overall != "passed" or scope == "full_certificate",
    }
    report = {
        "schema_version": 1,
        "tool": "winwatt.certificate.preflight",
        "tool_version": "1.1.0",
        "status": overall,
        "scope": scope,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": str(model_path),
        "model_sha256": _sha256(model_path),
        "readback_xml": str(readback_xml) if readback_xml else None,
        "readback_xml_sha256": _sha256(readback_xml) if readback_xml else None,
        "catalog_xml": str(catalog_xml) if catalog_xml else None,
        "catalog_xml_sha256": _sha256(catalog_xml) if catalog_xml else None,
        "tolerance": tolerance,
        "checks": checks,
        "next_actions": [
            {"check_id": item["check_id"], "status": item["status"], "issues": item["issues"]}
            for item in checks if item["status"] != "passed"
        ],
        "readiness": readiness,
        "artifacts": artifacts,
        "llm_used": False,
    }
    (output_dir / "preflight_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report
