"""Deterministic local intake for OENY UploadRequest reconstruction jobs."""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader

from .geometry import is_vertical_wall


SCHEMA = "autowinwatt-oeny-reconstruction/v1"
PARSER_VERSION = "2026.10.15.1"
SUPPORTED_PROFILE_VERSION = "9.60"
VERSION_RE = re.compile(r"WinWatt(?:\s+gólya)?\s+([0-9]+\.[0-9]+)(?:\s+\(([^)]+)\))?", re.I)
NUMBER_RE = r"([+-]?[0-9][0-9 .]*(?:[,.][0-9]+)?)"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _child(parent: ET.Element | None, name: str) -> ET.Element | None:
    if parent is None:
        return None
    return next((item for item in parent if _local(item.tag) == name), None)


def _path(root: ET.Element, names: Iterable[str]) -> ET.Element | None:
    current: ET.Element | None = root
    for name in names:
        current = _child(current, name)
        if current is None:
            return None
    return current


def _text(root: ET.Element, path: str) -> str | None:
    node = _path(root, path.split("/"))
    if node is None:
        return None
    value = (node.text or "").strip()
    return value or None


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    normalized = value.replace(" ", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _evidence(value: Any, xml_path: str, *, status: str = "exact") -> dict[str, Any]:
    return {
        "value": value,
        "source": {"kind": "xml", "path": xml_path},
        "status": status,
        "confidence": 1.0 if status == "exact" else 0.95,
    }


def _element_to_data(element: ET.Element) -> Any:
    children = list(element)
    if not children:
        return (element.text or "").strip()
    grouped: dict[str, list[Any]] = {}
    for child in children:
        grouped.setdefault(_local(child.tag), []).append(_element_to_data(child))
    return {
        key: values[0] if len(values) == 1 else values
        for key, values in grouped.items()
    }


def _extract_embedded_pdf(root: ET.Element) -> bytes:
    nodes = [node for node in root.iter() if _local(node.tag) == "CalculationsPdfFileContent"]
    if len(nodes) != 1:
        raise ValueError(f"expected one CalculationsPdfFileContent, found {len(nodes)}")
    encoded = "".join((nodes[0].text or "").split())
    if not encoded:
        raise ValueError("CalculationsPdfFileContent is empty")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("CalculationsPdfFileContent is not strict Base64") from exc
    if not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-4096:]:
        raise ValueError("decoded CalculationsPdfFileContent is not a complete PDF")
    return raw


def _find_pdf_value(
    pages: list[str], pattern: str, *, source_kind: str = "embedded_pdf"
) -> dict[str, Any] | None:
    expression = re.compile(pattern, re.I)
    for page_number, page in enumerate(pages, 1):
        compact = " ".join(page.split())
        match = expression.search(compact)
        if not match:
            continue
        return {
            "value": _number(match.group(1)),
            "source": {
                "kind": source_kind,
                "page": page_number,
                "excerpt": match.group(0),
            },
            "status": "exact",
            "confidence": 0.99,
        }
    return None


def _find_calculation_zone_totals(
    pages: list[str], *, source_kind: str
) -> dict[str, dict[str, Any]] | None:
    """Read the first printed calculation-zone row without using certificate XML."""
    number = r"([+-]?\d+(?:[,.]\d+)?)"
    expression = re.compile(
        r"(F\d+)\s+(\S+)\s+" + number + r"\s*m[²2]\s+" + number
        + r"\s+" + number + r"\s+" + number,
        re.I,
    )
    for page_number, page in enumerate(pages, 1):
        compact = " ".join(page.split())
        heading = compact.find("Számítási zónák:")
        if heading < 0:
            continue
        match = expression.search(compact, heading)
        if not match:
            continue
        source = {
            "kind": source_kind,
            "page": page_number,
            "excerpt": match.group(0),
        }
        return {
            "zone_name": {"value": match.group(1), "source": source, "status": "exact", "confidence": 0.99},
            "useful_floor_area_m2": {
                "value": _number(match.group(5)), "source": source, "status": "exact", "confidence": 0.99,
            },
            "conditioned_volume_m3": {
                "value": _number(match.group(6)), "source": source, "status": "exact", "confidence": 0.99,
            },
        }
    return None


def _pdf_summary(
    raw: bytes, *, source_kind: str = "embedded_pdf"
) -> tuple[dict[str, Any], list[str]]:
    reader = PdfReader(io.BytesIO(raw))
    pages = [(page.extract_text() or "").replace("\x00", " ") for page in reader.pages]
    joined = "\n".join(pages)
    version_match = VERSION_RE.search(joined)
    normalized_lines = {
        line.strip().rstrip(":").casefold()
        for page in pages
        for line in page.splitlines()
        if line.strip()
    }
    headings = [
        label for label in (
            "Szerkezet típusok",
            "Határoló szerkezetek",
            "Használati feltételek szerinti zónák",
            "Hőegyensúly szerinti zónák",
            "Számítási zónák",
            "Fűtési rendszer",
            "Melegvíz-termelő rendszer",
            "Hűtési rendszer",
            "Légtechnikai rendszer",
            "Világítási rendszer",
            "Épülettechnikai rendszerek értékelése",
        ) if label.casefold() in normalized_lines
    ]
    structure_types = re.findall(r"(?m)^Típusa:\s*([^\r\n]+)", joined)
    layer_blocks = len(re.findall(r"Rétegek\s+kívülről\s+befelé", joined, re.I))
    metadata = {str(key): str(value) for key, value in (reader.metadata or {}).items()}
    zone_totals = _find_calculation_zone_totals(pages, source_kind=source_kind)
    values = {
        "useful_floor_area_m2": _find_pdf_value(
            pages, rf"Hasznos\s+alapterület\s*:\s*{NUMBER_RE}\s*m[²2]",
            source_kind=source_kind,
        ),
        "conditioned_volume_m3": zone_totals["conditioned_volume_m3"] if zone_totals else None,
        "summaries_energy_rating_kwh_m2a": _find_pdf_value(
            pages, rf"Összesített\s+energetikai\s+jellemző\s*:\s*{NUMBER_RE}\s*kWh/m[²2]a",
            source_kind=source_kind,
        ),
        "co2_kg_m2a": _find_pdf_value(
            pages, rf"Fajlagos\s+sz[ée]n(?:-)?dioxid\s+kibocsátás\s*:\s*{NUMBER_RE}\s*kg/m[²2]a",
            source_kind=source_kind,
        ),
        "area_volume_ratio_m2_m3": _find_pdf_value(
            pages, rf"felület-térfogat\s+aránya\s*:\s*{NUMBER_RE}\s*m[²2]/m[³3]",
            source_kind=source_kind,
        ),
        "heat_loss_factor_w_m3k": _find_pdf_value(
            pages, rf"Fajlagos\s+hőveszteségtényező\s*:\s*{NUMBER_RE}\s*W/m[³3]K",
            source_kind=source_kind,
        ),
    }
    if values["useful_floor_area_m2"] is None and zone_totals:
        values["useful_floor_area_m2"] = zone_totals["useful_floor_area_m2"]
    summary = {
        "sha256": _sha256_bytes(raw),
        "size_bytes": len(raw),
        "pages": len(pages),
        "text_chars": sum(len(page) for page in pages),
        "metadata": metadata,
        "software_version": version_match.group(1) if version_match else None,
        "software_date": version_match.group(2) if version_match else None,
        "headings": headings,
        "structure_type_mentions": structure_types,
        "layer_blocks": layer_blocks,
        "values": values,
        "calculation_zone": zone_totals,
    }
    return summary, pages


def _line_number(block: str, label: str) -> float | None:
    match = re.search(rf"(?mi)^{re.escape(label)}\s*:\s*{NUMBER_RE}", block)
    return _number(match.group(1)) if match else None


def _average_area_perimeter(block: str) -> tuple[float | None, float | None]:
    """Read the two ISO 13370 operands printed on one WinWatt report line."""
    match = re.search(
        rf"Átlaghoz\s+alkalmazott\s+terület\s+{NUMBER_RE}\s*m2,\s*kerület\s+{NUMBER_RE}\s*m",
        block,
        re.I,
    )
    if not match:
        return None, None
    return _number(match.group(1)), _number(match.group(2))


def extract_structure_records(
    pages: list[str], *, source_kind: str = "embedded_pdf"
) -> list[dict[str, Any]]:
    """Extract printed structure definitions without inventing room allocation."""
    rows: list[dict[str, Any]] = []
    pattern = re.compile(r"(?m)^([^\r\n:]{1,120})\r?\nTípusa:\s*([^\r\n]+)")
    for page_number, page in enumerate(pages, 1):
        matches = list(pattern.finditer(page))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(page)
            block = page[match.start():end]
            name = match.group(1).strip()
            structure_type = match.group(2).strip()
            is_opening = any(token in structure_type.casefold() for token in ("ablak", "ajtó", "nyílászáró"))
            u_layer = _line_number(block, "Rétegtervi hőátbocsátási tényező")
            if u_layer is None:
                u_layer = _line_number(block, "Átlagos rétegtervi hőátb. tényező")
            u_effective = _line_number(block, "Eredő hőátbocsátási tényező")
            if u_effective is None:
                u_effective = _line_number(block, "Hőátbocsátási tényező")
            iso_area, iso_perimeter = _average_area_perimeter(block)
            rows.append({
                "name": name,
                "type": structure_type,
                "x_m": _line_number(block, "x méret") if is_opening else None,
                "y_m": _line_number(block, "y méret") if is_opening else None,
                "u_layer": u_layer,
                "u_effective": u_effective,
                "iso_area_m2": iso_area,
                "iso_perimeter_m": iso_perimeter,
                "wall_floor_psi_w_mk": _line_number(block, "Fal-padló csatlakozási hőhíd"),
                "linear_transmittance_w_mk": _line_number(block, "Vonalmenti hőátbocsátási tényező"),
                "floor_level_m": _line_number(block, "Padlószint magassága"),
                "earth_lambda_w_mk": _line_number(block, "Talaj hővezetési tény."),
                "base_width_m": _line_number(block, "Alap szélesség"),
                "floor_u_value": _line_number(block, "Padló rétegtervi hőátb. tény."),
                "rse_m2k_w": _line_number(block, "Hőátadási ellenállás kívül"),
                "rsi_m2k_w": _line_number(block, "Hőátadási ellenállás belül"),
                "u_modifier_percent": _line_number(block, "Hőátbocsátási tényezőt módosító tag"),
                "specific_mass_kg_m2": _line_number(block, "Fajlagos tömeg"),
                "specific_heat_mass_kg_m2": _line_number(block, "Fajlagos hőtároló tömeg"),
                "specific_heat_capacity_kj_m2k": _line_number(block, "Fajlagos hőkapacitás"),
                "glazing_ratio_percent": _line_number(block, "Üvegezési arány"),
                "glazing_g": _line_number(block, "Üvegezés g értéke"),
                "source": {
                    "kind": source_kind,
                    "page": page_number,
                    "excerpt": block[:1200],
                },
                "status": "exact_printed_values",
                "room_allocation": "unresolved",
            })
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        unique.setdefault((row["name"], row["type"]), row)
    return list(unique.values())


def extract_system_records(
    pages: list[str], *, source_kind: str = "embedded_pdf"
) -> list[dict[str, Any]]:
    labels = {
        "Fűtési rendszer": "heating",
        "Melegvíz-termelő rendszer": "hot_water",
        "Hűtési rendszer": "cooling",
        "Légtechnikai rendszer": "airing",
        "Világítási rendszer": "lighting",
    }
    exact_lines = [
        (page_number, line.strip().rstrip(":"))
        for page_number, page in enumerate(pages, 1)
        for line in page.splitlines()
    ]
    rows = []
    for label, system_type in labels.items():
        pages_found = [number for number, line in exact_lines if line.casefold() == label.casefold()]
        if pages_found:
            rows.append({
                "name": label,
                "type": system_type,
                "reviewed": False,
                "source": {"kind": source_kind, "page": pages_found[0], "heading": label},
                "status": "detected_requires_parameter_review",
            })
    return rows


def build_pdf_reconstruction_spec(
    pdf_path: Path, *, certificate_id: str | None = None
) -> dict[str, Any]:
    """Build a construction specification whose only source is a PDF file.

    A source certificate XML is intentionally not accepted here.  It belongs
    only to the later validation/diff stage after WinWatt has produced a new
    certificate XML.
    """
    pdf_path = pdf_path.resolve(strict=True)
    raw_pdf = pdf_path.read_bytes()
    if not raw_pdf.startswith(b"%PDF-") or b"%%EOF" not in raw_pdf[-4096:]:
        raise ValueError("source PDF is not a complete PDF")
    pdf, pages = _pdf_summary(raw_pdf, source_kind="pdf")
    structure_records = extract_structure_records(pages, source_kind="pdf")
    system_records = extract_system_records(pages, source_kind="pdf")
    resolved_certificate_id = certificate_id or (pdf_path.stem if pdf_path.stem.isdigit() else None)
    required = ("useful_floor_area_m2", "conditioned_volume_m3")
    missing = [key for key in required if not pdf["values"].get(key)]
    exact_version = pdf["software_version"] == SUPPORTED_PROFILE_VERSION
    blockers: list[dict[str, Any]] = []
    if missing:
        blockers.append({"code": "missing_pdf_construction_values", "fields": missing})
    if not exact_version:
        blockers.append({
            "code": "source_version_not_installed_profile",
            "source_version": pdf["software_version"],
            "installed_profile_version": SUPPORTED_PROFILE_VERSION,
            "effect": "byte-identical PDF and calculation identity are not assumed",
        })
    return {
        "schema": "autowinwatt-pdf-reconstruction/v1",
        "parser_version": PARSER_VERSION,
        "status": "review_required",
        "certificate_id": resolved_certificate_id,
        "input_policy": {
            "construction_input": "pdf_only",
            "reference_xml_role": "post_export_validation_only",
            "xml_values_allowed_during_build": False,
        },
        "source": {
            "pdf": {
                "path": str(pdf_path), "sha256": pdf["sha256"],
                "size_bytes": pdf["size_bytes"], "pages": pdf["pages"],
            }
        },
        "engine": {
            "source_version": pdf["software_version"],
            "installed_profile_version": SUPPORTED_PROFILE_VERSION,
            "mode": "version_exact_reconstruction" if exact_version else "current_engine_reconstruction",
        },
        "fields": pdf["values"],
        "pdf_values": pdf["values"],
        "calculation_zone": pdf["calculation_zone"],
        "structure_records": structure_records,
        "system_records": system_records,
        "inventory": {
            "pdf_headings": pdf["headings"],
            "pdf_structure_type_mentions": pdf["structure_type_mentions"],
            "pdf_layer_blocks": pdf["layer_blocks"],
        },
        "blockers": blockers,
        "release": {
            "review_required": True,
            "winwatt_ready": False,
            "reason": "PDF-only intake; every construction field must retain PDF provenance",
        },
        "execution": {"llm_used": False, "winwatt_started": False},
    }


def _model_draft(spec: dict[str, Any], structures: list[dict[str, Any]], systems: list[dict[str, Any]]) -> dict[str, Any]:
    fields = spec["fields"]
    return {
        "schema": "autowinwatt-reviewed-certificate-model/draft-v1",
        "project": {
            "name": f"OENY_{spec['certificate_id'] or 'UNKNOWN'}",
            "heated_area_m2": fields["useful_floor_area_m2"]["value"],
            "heated_volume_m3": fields["conditioned_volume_m3"]["value"],
            "require_wall_xy": True,
        },
        "rooms": [],
        "structures": [
            {
                "name": row["name"],
                "type": row["type"],
                "u_effective": row["u_effective"],
                "source": row["source"],
                "reviewed": False,
            }
            for row in structures
        ],
        "layers": [],
        "boundaries": [],
        "systems": systems,
        "reconstruction": {
            "source_xml_sha256": spec["source"]["xml"]["sha256"],
            "source_pdf_sha256": spec["source"]["embedded_pdf"]["sha256"],
            "parser_version": spec["parser_version"],
            "status": "draft",
            "unresolved": [
                "room geometry and room count are not present in the certificate XML",
                "printed envelope rows are not yet allocated to native WinWatt room boundaries",
                "layer rows and catalogue identifiers require structured parsing/review",
                "all detected system parameters require field-level parsing and professional review",
            ],
        },
    }


def build_one_zone_candidate(
    spec: dict[str, Any], decisions: dict[str, Any]
) -> dict[str, Any]:
    """Build a traceable one-zone candidate from explicit human decisions.

    The function deliberately does not infer wall X/Y geometry.  Catalogue
    mappings are copied only from explicit, traceable human approvals.
    """
    if decisions.get("schema") != "autowinwatt-oeny-reconstruction-decisions/v1":
        raise ValueError("unsupported reconstruction decisions schema")
    if spec.get("input_policy", {}).get("construction_input") != "pdf_only":
        raise ValueError("construction spec must declare pdf_only input policy")
    if decisions.get("input_policy", {}).get("construction_input") != "pdf_only":
        raise ValueError("construction decisions must declare pdf_only input policy")

    def reject_non_pdf_sources(value: Any, path: str = "decisions") -> None:
        if isinstance(value, dict):
            source = value.get("source")
            if isinstance(source, dict) and source.get("kind") not in (None, "pdf"):
                raise ValueError(
                    f"{path}.source must have direct PDF provenance, got {source.get('kind')!r}"
                )
            for key, child in value.items():
                reject_non_pdf_sources(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                reject_non_pdf_sources(child, f"{path}[{index}]")

    reject_non_pdf_sources(decisions)
    if str(decisions.get("certificate_id")) != str(spec.get("certificate_id")):
        raise ValueError("decision certificate_id does not match reconstruction spec")
    if decisions.get("room_count_decision", {}).get("accepted") is not True:
        raise ValueError("one-zone room-count decision is not accepted")

    fields = spec["fields"]
    for key in ("useful_floor_area_m2", "conditioned_volume_m3"):
        field = fields.get(key) or {}
        if field.get("source", {}).get("kind") != "pdf":
            raise ValueError(f"construction field {key} must have direct PDF provenance")
        if field.get("value") is None:
            raise ValueError(f"construction field {key} is missing from the PDF")
    area = float(fields["useful_floor_area_m2"]["value"])
    volume = float(fields["conditioned_volume_m3"]["value"])
    room_name = str(decisions.get("room_name") or "F1").strip()
    if not room_name:
        raise ValueError("room_name must not be empty")
    height = volume / area
    wall_geometry_decision = decisions.get("wall_geometry_decision") or {}
    derive_wall_xy = wall_geometry_decision.get("accepted") is True

    structures = [
        {
            "name": row["name"],
            "type": row["type"],
            "u_layer": row.get("u_layer"),
            "u_effective": row.get("u_effective"),
            "iso_area_m2": row.get("iso_area_m2"),
            "iso_perimeter_m": row.get("iso_perimeter_m"),
            "wall_floor_psi_w_mk": row.get("wall_floor_psi_w_mk"),
            "linear_transmittance_w_mk": row.get("linear_transmittance_w_mk"),
            "floor_level_m": row.get("floor_level_m"),
            "earth_lambda_w_mk": row.get("earth_lambda_w_mk"),
            "base_width_m": row.get("base_width_m"),
            "floor_u_value": row.get("floor_u_value"),
            "rse_m2k_w": row.get("rse_m2k_w"),
            "rsi_m2k_w": row.get("rsi_m2k_w"),
            "u_modifier_percent": row.get("u_modifier_percent"),
            "specific_mass_kg_m2": row.get("specific_mass_kg_m2"),
            "specific_heat_mass_kg_m2": row.get("specific_heat_mass_kg_m2"),
            "specific_heat_capacity_kj_m2k": row.get("specific_heat_capacity_kj_m2k"),
            "source": row["source"],
            "reviewed": False,
        }
        for row in spec.get("structure_records", [])
    ]
    structure_names = {row["name"] for row in structures}
    boundaries = []
    for index, source in enumerate(decisions.get("boundaries") or [], 1):
        structure = str(source.get("structure") or "")
        if structure not in structure_names:
            raise ValueError(f"boundary {index} references unknown structure: {structure!r}")
        boundary = dict(source)
        boundary["room"] = room_name
        boundary.setdefault("name", f"{structure} {index}")
        boundary.setdefault("source", {"kind": "embedded_pdf", "page": 4})
        boundary.setdefault("geometry_status", "printed_area_only")
        if derive_wall_xy and is_vertical_wall(boundary):
            printed_area = float(boundary["area_m2"])
            if printed_area <= 0:
                raise ValueError(f"boundary {index} area must be positive")
            boundary["y_m"] = height
            boundary["x_m"] = printed_area / height
            boundary["geometry_status"] = (
                "calculation_equivalent_xy_from_exact_area_and_effective_height"
            )
            boundary["geometry_derivation"] = {
                "authoritative_value": "area_m2",
                "area_m2": printed_area,
                "effective_height_m": height,
                "effective_height_formula": "conditioned_volume_m3 / useful_floor_area_m2",
                "x_formula": "area_m2 / effective_height_m",
                "not_as_built_measurement": True,
                "human_decision": wall_geometry_decision,
            }
        boundaries.append(boundary)

    approval_rows = decisions.get("material_approvals") or []
    approvals: dict[tuple[str, int], dict[str, Any]] = {}
    for approval_index, approval in enumerate(approval_rows, 1):
        key = (str(approval.get("structure") or ""), int(approval.get("sequence") or 0))
        if not key[0] or key[1] <= 0:
            raise ValueError(f"material approval {approval_index} has an invalid layer key")
        if key in approvals:
            raise ValueError(f"duplicate material approval for {key[0]} / {key[1]}")
        if approval.get("approved") is not True:
            raise ValueError(f"material approval {approval_index} is not approved")
        approvals[key] = dict(approval)

    layers = []
    for index, source in enumerate(decisions.get("layers") or [], 1):
        structure = str(source.get("structure") or "")
        if structure not in structure_names:
            raise ValueError(f"layer {index} references unknown structure: {structure!r}")
        layer = dict(source)
        layer.setdefault("source", {"kind": "embedded_pdf"})
        approval = approvals.pop((structure, int(layer.get("sequence") or 0)), None)
        if approval is not None:
            if str(approval.get("source_name") or "") != str(layer.get("name") or ""):
                raise ValueError(
                    f"material approval source name does not match {structure} / {layer.get('sequence')}"
                )
            layer["catalog_material_id"] = str(approval["catalog_material_id"])
            layer["catalog_material_name"] = str(approval["catalog_material_name"])
            layer["material_approval"] = approval
            layer["reviewed"] = True
            layer["review_status"] = "approved"
        else:
            layer.setdefault("reviewed", False)
        layers.append(layer)
    if approvals:
        orphaned = ", ".join(f"{key[0]} / {key[1]}" for key in sorted(approvals))
        raise ValueError(f"material approvals reference missing layers: {orphaned}")

    systems = [dict(row) for row in decisions.get("systems") or spec.get("system_records", [])]
    return {
        "schema": "autowinwatt-reviewed-certificate-model/candidate-v1",
        "project": {
            "name": f"OENY_{spec['certificate_id']}",
            "address": decisions.get("address"),
            "source": spec["source"]["pdf"]["path"],
            "heated_area_m2": area,
            "heated_volume_m3": volume,
            "require_wall_xy": derive_wall_xy,
        },
        "buildings": [{"id": "B1", "name": decisions.get("building_name") or "Tanúsított épület"}],
        "rooms": [{
            "name": room_name,
            "building": "B1",
            "area_m2": area,
            "height_m": height,
            "volume_m3": volume,
            "temperature_c": float(decisions.get("temperature_c", 20.0)),
            "reviewed": True,
            "review_basis": decisions["room_count_decision"],
        }],
        "structures": structures,
        "layers": layers,
        "boundaries": boundaries,
        "systems": systems,
        "reconstruction": {
            "source_pdf_sha256": spec["source"]["pdf"]["sha256"],
            "reference_xml_role": "post_export_validation_only",
            "parser_version": spec["parser_version"],
            "status": "review_required",
            "mode": spec["engine"]["mode"],
            "unresolved": (
                ([] if derive_wall_xy else [
                    "vertical boundary X/Y dimensions are not printed; only exact areas are retained",
                ]) + [
                    "non-approved layer names and properties still require WinWatt catalogue audit",
                    "gas-convector creation is not a verified executable WinWatt tool",
                    "system parameter mapping requires professional review",
                    "source WinWatt version differs from the installed engine",
                ]
            ),
        },
    }


def _xml_sections(root: ET.Element) -> dict[str, Any]:
    excluded = {"CalculationsPdfFileContent", "Photos"}
    return {
        _local(child.tag): _element_to_data(child)
        for child in root if _local(child.tag) not in excluded
    }


def _photo_inventory(root: ET.Element) -> list[dict[str, Any]]:
    parent = _path(root, ["Photos"])
    if parent is None:
        return []
    rows: list[dict[str, Any]] = []
    for index, photo in enumerate((item for item in parent if _local(item.tag) == "Photo"), 1):
        category = _text(photo, "Category")
        note = _text(photo, "Note")
        encoded = "".join((_text(photo, "Content") or "").split())
        try:
            raw = base64.b64decode(encoded, validate=True) if encoded else b""
            decode_error = None
        except (binascii.Error, ValueError) as exc:
            raw = b""
            decode_error = repr(exc)
        rows.append({
            "index": index,
            "category": category,
            "note": note,
            "size_bytes": len(raw),
            "sha256": _sha256_bytes(raw) if raw else None,
            "signature_hex": raw[:12].hex() if raw else None,
            "base64_valid": decode_error is None and bool(raw),
            "decode_error": decode_error,
        })
    return rows


def _count_direct(root: ET.Element, section: str, item: str) -> int:
    parent = _path(root, [section])
    if parent is None:
        return 0
    return sum(1 for child in list(parent) if _local(child.tag) == item)


def build_reconstruction_spec(xml_path: Path) -> tuple[dict[str, Any], bytes]:
    xml_path = xml_path.resolve(strict=True)
    raw_xml = xml_path.read_bytes()
    root = ET.fromstring(raw_xml)
    if _local(root.tag) != "UploadRequest":
        raise ValueError(f"expected UploadRequest root, got {_local(root.tag)}")
    embedded_pdf = _extract_embedded_pdf(root)
    pdf, pages = _pdf_summary(embedded_pdf)
    structure_records = extract_structure_records(pages)
    system_records = extract_system_records(pages)

    software_full = _text(root, "CertifierDetails/SoftwareAndVersion")
    software_match = VERSION_RE.search(software_full or "")
    source_version = software_match.group(1) if software_match else pdf["software_version"]
    certificate_id = xml_path.stem if xml_path.stem.isdigit() else None
    structures = _count_direct(root, "BoundaryAndOpeningStructures", "BoundaryAndOpeningStructure")
    photo_inventory = _photo_inventory(root)
    photos = len(photo_inventory)

    fields = {
        "client_name": _evidence(_text(root, "BuildingData/ClientName"), "BuildingData/ClientName"),
        "topographical_number": _evidence(
            _text(root, "BuildingData/TopographicalNumber"), "BuildingData/TopographicalNumber"
        ),
        "building_purpose": _evidence(
            _text(root, "BuildingData/BuildingPurpose"), "BuildingData/BuildingPurpose"
        ),
        "year_of_construction": _evidence(
            _number(_text(root, "BuildingData/YearOfConstruct")), "BuildingData/YearOfConstruct"
        ),
        "useful_floor_area_m2": _evidence(
            _number(_text(root, "BuildingData/UsefulFloorArea")), "BuildingData/UsefulFloorArea"
        ),
        "conditioned_volume_m3": _evidence(
            _number(_text(root, "BuildingData/ConditionedVolume")), "BuildingData/ConditionedVolume"
        ),
        "area_volume_ratio_m2_m3": _evidence(
            _number(_text(root, "BuildingData/BuildingAreaToVolumeRatio")),
            "BuildingData/BuildingAreaToVolumeRatio",
        ),
        "summaries_energy_rating_kwh_m2a": _evidence(
            _number(_text(root, "EfficiencyCategories/CurrentValues/SummariesEnergyRating/Value")),
            "EfficiencyCategories/CurrentValues/SummariesEnergyRating/Value",
        ),
        "co2_kg_m2a": _evidence(
            _number(_text(root, "EfficiencyCategories/CurrentValues/Co2/Value")),
            "EfficiencyCategories/CurrentValues/Co2/Value",
        ),
        "heat_loss_factor_w_m3k": _evidence(
            _number(_text(root, "EfficiencyCategories/CurrentValues/HeatLossFactor/Value")),
            "EfficiencyCategories/CurrentValues/HeatLossFactor/Value",
        ),
    }
    conflicts: list[dict[str, Any]] = []
    for key, pdf_value in pdf["values"].items():
        xml_value = fields.get(key, {}).get("value")
        if pdf_value is None or xml_value is None:
            continue
        difference = abs(float(xml_value) - float(pdf_value["value"]))
        tolerance = 0.011 if key != "area_volume_ratio_m2_m3" else 0.011
        if difference > tolerance:
            conflicts.append({
                "field": key,
                "xml_value": xml_value,
                "pdf_value": pdf_value["value"],
                "difference": difference,
                "tolerance": tolerance,
            })

    exact_version = source_version == SUPPORTED_PROFILE_VERSION
    blockers = []
    if not exact_version:
        blockers.append({
            "code": "source_version_not_installed_profile",
            "source_version": source_version,
            "installed_profile_version": SUPPORTED_PROFILE_VERSION,
            "effect": "byte-identical PDF and calculation identity are not assumed",
        })
    if conflicts:
        blockers.append({"code": "xml_pdf_numeric_conflict", "count": len(conflicts)})

    complexity_score = (
        structures * 3
        + pdf["layer_blocks"] * 2
        + len(pdf["headings"])
        + max(0, pdf["pages"] - 5)
        + (4 if "Hűtési rendszer" in pdf["headings"] else 0)
        + (4 if "Légtechnikai rendszer" in pdf["headings"] else 0)
    )
    spec = {
        "schema": SCHEMA,
        "parser_version": PARSER_VERSION,
        "status": "review_required",
        "certificate_id": certificate_id,
        "source": {
            "xml": {"path": str(xml_path), "sha256": _sha256_bytes(raw_xml), "size_bytes": len(raw_xml)},
            "embedded_pdf": {key: pdf[key] for key in ("sha256", "size_bytes", "pages")},
        },
        "engine": {
            "source_software": software_full,
            "source_version": source_version,
            "installed_profile_version": SUPPORTED_PROFILE_VERSION,
            "mode": "version_exact_reconstruction" if exact_version else "current_engine_reconstruction",
        },
        "inventory": {
            "boundary_and_opening_structure_groups": structures,
            "photos": photos,
            "pdf_headings": pdf["headings"],
            "pdf_structure_type_mentions": pdf["structure_type_mentions"],
            "pdf_layer_blocks": pdf["layer_blocks"],
            "complexity_score": complexity_score,
        },
        "fields": fields,
        "pdf_values": pdf["values"],
        "structure_records": structure_records,
        "system_records": system_records,
        "photos": photo_inventory,
        "xml_sections": _xml_sections(root),
        "conflicts": conflicts,
        "blockers": blockers,
        "release": {
            "review_required": True,
            "winwatt_ready": False,
            "reason": "intake only; geometry, materials, systems and roundtrip are not yet reviewed",
        },
        "execution": {"llm_used": False, "winwatt_started": False},
    }
    spec["model_draft"] = _model_draft(spec, structure_records, system_records)
    return spec, embedded_pdf


@dataclass(frozen=True)
class IntakeResult:
    certificate_id: str
    output_dir: Path
    status: str
    cache_hit: bool
    complexity_score: int


def write_reconstruction_intake(xml_path: Path, output_root: Path) -> IntakeResult:
    xml_path = xml_path.resolve(strict=True)
    certificate_id = xml_path.stem
    output_dir = output_root.resolve() / certificate_id
    spec_path = output_dir / "reconstruction_spec.json"
    source_hash = sha256_file(xml_path)
    if spec_path.is_file():
        existing = json.loads(spec_path.read_text(encoding="utf-8"))
        if existing.get("source", {}).get("xml", {}).get("sha256") != source_hash:
            raise ValueError(f"cached intake source hash mismatch: {certificate_id}")
        if existing.get("schema") == SCHEMA and existing.get("parser_version") == PARSER_VERSION:
            pdf_path = output_dir / "source_calculation.pdf"
            if not pdf_path.is_file() or sha256_file(pdf_path) != existing["source"]["embedded_pdf"]["sha256"]:
                raise ValueError(f"cached intake PDF is missing or changed: {certificate_id}")
            return IntakeResult(
                certificate_id=certificate_id,
                output_dir=output_dir,
                status=existing["status"],
                cache_hit=True,
                complexity_score=int(existing["inventory"]["complexity_score"]),
            )

    if output_dir.exists() and any(output_dir.iterdir()) and not spec_path.is_file():
        raise FileExistsError(f"non-empty intake output has no valid specification: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    spec, embedded_pdf = build_reconstruction_spec(xml_path)
    pdf_path = output_dir / "source_calculation.pdf"
    pdf_path.write_bytes(embedded_pdf)
    spec["artifacts"] = {
        "source_calculation_pdf": {
            "path": str(pdf_path),
            "sha256": _sha256_bytes(embedded_pdf),
            "size_bytes": len(embedded_pdf),
        }
    }
    model_path = output_dir / "model_draft.json"
    model_path.write_text(
        json.dumps(spec["model_draft"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    spec["artifacts"]["model_draft"] = {
        "path": str(model_path),
        "sha256": sha256_file(model_path),
        "size_bytes": model_path.stat().st_size,
    }
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return IntakeResult(
        certificate_id=certificate_id,
        output_dir=output_dir,
        status=spec["status"],
        cache_hit=False,
        complexity_score=int(spec["inventory"]["complexity_score"]),
    )
