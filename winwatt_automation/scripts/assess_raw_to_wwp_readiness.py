#!/usr/bin/env python
"""Assess how far non-WWP/non-XML source files can build a WWP without AI.

The corpus manifest may contain WWP/XML references, but this program excludes
them from extraction.  They are listed only as withheld ground truth.  All
decisions are deterministic and the report records that no AI and no WinWatt
UI execution took place.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INPUT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".dwg"}
WITHHELD_EXTENSIONS = {".wwp", ".xml"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _probe_pdf(path: Path) -> dict[str, Any]:
    from winwatt_automation.certificates.dimension_chains import extract_pdf_dimension_chains
    from winwatt_automation.certificates.local_extract import (
        candidate_material_lines,
        extract_known_values,
        extract_pdf_pages,
    )

    pages = extract_pdf_pages(path)
    values = extract_known_values(pages)
    try:
        dimensions = extract_pdf_dimension_chains(path)
        dimension_payload = [item.json() for item in dimensions]
    except RuntimeError as exc:
        # The WinWatt and workspace Python installations intentionally have
        # different dependencies. Use the already installed 64-bit PyMuPDF
        # interpreter for vector geometry, while text extraction stays in the
        # workspace environment. No network or AI service is involved.
        if "PyMuPDF" not in str(exc):
            raise
        dimension_payload = _external_dimension_probe(path)
    return {
        "page_count": len(pages),
        "text_character_count": sum(len(page) for page in pages),
        "pages_with_text": sum(bool(page.strip()) for page in pages),
        "known_values": [item.model_dump(mode="json") for item in values],
        "material_candidate_lines": candidate_material_lines(pages),
        "dimension_evidence": dimension_payload,
    }


def _external_dimension_probe(path: Path) -> list[dict[str, Any]]:
    candidates = [Path(r"C:\Python311\python.exe")]
    for python in candidates:
        if not python.exists():
            continue
        result = subprocess.run(
            [str(python), str(Path(__file__).resolve()), "--probe-dimensions", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=45,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    raise RuntimeError("No local Python with PyMuPDF could probe vector dimensions")


def _probe_dimensions_without_package_import(path: Path) -> list[dict[str, Any]]:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "winwatt_automation"
        / "certificates"
        / "dimension_chains.py"
    )
    spec = importlib.util.spec_from_file_location("winwatt_dimension_chains_standalone", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load dimension extractor: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return [item.json() for item in module.extract_pdf_dimension_chains(path)]


def _probe_pdf_bounded(path: Path, timeout_seconds: int) -> dict[str, Any]:
    command = [sys.executable, str(Path(__file__).resolve()), "--probe-pdf", str(path)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "timeout_seconds": timeout_seconds}
    if result.returncode:
        return {
            "status": "error",
            "returncode": result.returncode,
            "error": (result.stderr or result.stdout)[-2000:],
        }
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {"status": "error", "error": f"invalid probe JSON: {exc}"}
    payload["status"] = "completed"
    return payload


def _case_assessment(case: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    allowed: list[dict[str, Any]] = []
    withheld: list[dict[str, Any]] = []
    known_values: dict[str, list[dict[str, Any]]] = {}
    dimension_count = 0
    high_confidence_dimension_count = 0
    material_line_count = 0
    role_names: list[str] = []

    for item in case["files"]:
        path = Path(item["copy_path"])
        extension = path.suffix.lower()
        record: dict[str, Any] = {
            "role": item["role"],
            "path": str(path),
            "extension": extension,
            "sha256": sha256(path),
            "manifest_sha256_matches": sha256(path) == item["sha256"],
        }
        if extension in WITHHELD_EXTENSIONS:
            record["reason"] = "withheld_ground_truth_not_used_as_generation_input"
            withheld.append(record)
            continue
        if extension not in INPUT_EXTENSIONS:
            record["reason"] = "unsupported_input_extension"
            allowed.append(record)
            continue

        role_names.append(item["role"])
        if extension == ".pdf":
            record["probe"] = _probe_pdf_bounded(path, timeout_seconds)
            probe = record["probe"]
            if probe.get("status") == "completed":
                for value in probe["known_values"]:
                    known_values.setdefault(value["key"], []).append(
                        {"path": str(path), "value": value["value"], "evidence": value["evidence"]}
                    )
                dimension_count += len(probe["dimension_evidence"])
                high_confidence_dimension_count += sum(
                    evidence["confidence"] >= 0.8 and evidence["extension_count"] >= 2
                    for evidence in probe["dimension_evidence"]
                )
                material_line_count += len(probe["material_candidate_lines"])
        elif extension in {".jpg", ".jpeg", ".png"}:
            record["probe"] = {
                "status": "available_as_visual_evidence",
                "semantic_extraction": "not_implemented_without_AI",
            }
        elif extension == ".dwg":
            record["probe"] = {
                "status": "unsupported_by_current_local_pipeline",
                "required_adapter": "deterministic_DWG_to_structured_geometry_or_vector_PDF",
            }
        allowed.append(record)

    pdfs = [item for item in allowed if item["extension"] == ".pdf"]
    photos = [item for item in allowed if item["extension"] in {".jpg", ".jpeg", ".png"}]
    dwgs = [item for item in allowed if item["extension"] == ".dwg"]
    pdf_errors = [item for item in pdfs if item.get("probe", {}).get("status") != "completed"]

    domain_checks = {
        "administrative_identity": {
            "status": "missing",
            "reason": "No deterministic parser maps these source files to required administrative fields.",
        },
        "building_aggregate_values": {
            "status": "partial" if known_values else "missing",
            "evidence_keys": sorted(known_values),
        },
        "room_names_and_areas": {
            "status": "missing",
            "reason": "Plan text/dimensions are not yet associated with closed room contours.",
        },
        "room_boundaries_and_orientation": {
            "status": "partial" if high_confidence_dimension_count else "missing",
            "dimension_evidence_count": dimension_count,
            "high_confidence_dimension_count": high_confidence_dimension_count,
            "reason": "Dimensions remain unassigned to rooms, wall IDs, heights and azimuths.",
        },
        "layered_structures": {
            "status": "partial" if material_line_count else "missing",
            "candidate_line_count": material_line_count,
            "reason": "Candidate prose is not a complete ordered layer build-up with validated properties.",
        },
        "openings": {
            "status": "missing",
            "reason": "No deterministic opening geometry/type/property extraction exists for these inputs.",
        },
        "building_systems": {
            "status": "evidence_only" if any(role.startswith("photo_") for role in role_names) else "missing",
            "photo_count": len(photos),
            "reason": "Photos can be retained as evidence; technical system parameters are not extracted without AI/manual entry.",
        },
        "renovation_recommendations": {
            "status": "missing",
            "reason": "No deterministic recommendation parser/model exists for these raw inputs.",
        },
    }
    complete_domains = sum(value["status"] == "complete" for value in domain_checks.values())
    partial_domains = sum(value["status"] in {"partial", "evidence_only"} for value in domain_checks.values())
    return {
        "case_id": case["case_id"],
        "policy": {
            "ai_used": False,
            "winwatt_started": False,
            "wwp_xml_inputs_excluded": True,
            "fabricated_defaults_allowed": False,
        },
        "input_summary": {
            "allowed_file_count": len(allowed),
            "pdf_count": len(pdfs),
            "photo_count": len(photos),
            "dwg_count": len(dwgs),
            "withheld_reference_count": len(withheld),
            "pdf_probe_error_count": len(pdf_errors),
        },
        "extracted": {
            "known_values": known_values,
            "dimension_evidence_count": dimension_count,
            "high_confidence_dimension_count": high_confidence_dimension_count,
            "material_candidate_line_count": material_line_count,
        },
        "wwp_domain_checks": domain_checks,
        "readiness": {
            "complete_domain_count": complete_domains,
            "partial_or_evidence_domain_count": partial_domains,
            "required_domain_count": len(domain_checks),
            "structured_model_complete": False,
            "native_xml_compilable": False,
            "wwp_autonomously_creatable": False,
            "blocking_reason": "A reviewed explicit room/boundary/structure/opening/system model cannot yet be formed from the allowed inputs.",
        },
        "allowed_inputs": allowed,
        "withheld_references": withheld,
    }


def assess(corpus_root: Path, output: Path, timeout_seconds: int) -> dict[str, Any]:
    manifest = json.loads((corpus_root / "manifest.json").read_text(encoding="utf-8"))
    cases = [_case_assessment(case, timeout_seconds) for case in manifest["cases"]]
    completed_pdfs = sum(
        item.get("probe", {}).get("status") == "completed"
        for case in cases for item in case["allowed_inputs"] if item["extension"] == ".pdf"
    )
    report = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "corpus_root": str(corpus_root.resolve()),
        "method": {
            "ai_used": False,
            "network_used": False,
            "winwatt_started": False,
            "wwp_xml_used_for_generation": False,
            "pdf_probe_timeout_seconds": timeout_seconds,
        },
        "aggregate": {
            "case_count": len(cases),
            "pdf_probe_completed_count": completed_pdfs,
            "autonomous_wwp_success_count": sum(case["readiness"]["wwp_autonomously_creatable"] for case in cases),
            "structured_model_complete_count": sum(case["readiness"]["structured_model_complete"] for case in cases),
            "conclusion": "Current deterministic pipeline can prepare evidence, but cannot autonomously produce a complete WWP from these raw inputs.",
        },
        "cases": cases,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus_root", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pdf-timeout", type=int, default=45)
    parser.add_argument("--probe-pdf", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--probe-dimensions", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.probe_dimensions:
        print(json.dumps(_probe_dimensions_without_package_import(args.probe_dimensions), ensure_ascii=False))
        return 0
    if args.probe_pdf:
        print(json.dumps(_probe_pdf(args.probe_pdf), ensure_ascii=False))
        return 0
    if not args.corpus_root:
        parser.error("corpus_root is required")
    output = args.output or args.corpus_root / "raw_to_wwp_assessment.json"
    report = assess(args.corpus_root.resolve(), output.resolve(), args.pdf_timeout)
    print(json.dumps({"output": str(output.resolve()), "aggregate": report["aggregate"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
