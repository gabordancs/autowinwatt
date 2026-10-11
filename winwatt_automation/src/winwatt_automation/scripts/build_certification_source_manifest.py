"""Build a deterministic manifest for the canonical certification sources."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

SOURCE_DEFINITIONS: dict[str, tuple[str, str]] = {
    "9_2023. (V. 25.) ÉKM rendelet.pdf": ("legal.energy_performance_decree_9_2023", "authoritative"),
    "176_2008. (VI. 30.) Korm. rendelet.pdf": ("legal.certification_decree", "authoritative"),
    "ÉKM rendelet 1. függelék.pdf": ("method.ekm_appendix_1", "authoritative"),
    "ÉKM rendelet 2. függelék.pdf": ("reference.ekm_appendix_2", "authoritative"),
    "Alkalmazott_Epuletenergetika.pdf": ("guide.applied_building_energy", "guide"),
    "anyagok.xml": ("catalog.winwatt_materials", "catalog"),
    "hőtermelők.xlsx": ("catalog.heat_generators", "catalog"),
    "Meteo.pdf": ("reference.hourly_climate", "reference"),
    "ww_global_solar_gsi-export-2026-04-01_21-48-51.csv": ("reference.global_solar_gsi", "reference"),
    "tanúsítvány/dokumentacio-v3.0.12035/README.md": ("certificate.v3_0_12035.readme", "guide"),
    "tanúsítvány/dokumentacio-v3.0.12035/docs/dictionary.md": ("certificate.v3_0_12035.dictionary", "authoritative"),
    "tanúsítvány/dokumentacio-v3.0.12035/docs/differentByVersions.md": ("certificate.v3_0_12035.version_differences", "guide"),
    "tanúsítvány/dokumentacio-v3.0.12035/docs/validationRules.md": ("certificate.v3_0_12035.validation_rules", "authoritative"),
    "tanúsítvány/dokumentacio-v3.0.12035/docs/validtationRules.md": ("certificate.v3_0_12035.validation_rules_legacy", "reference"),
    "tanúsítvány/dokumentacio-v3.0.12035/test/system/data/xml/general_cert.xml": ("certificate.v3_0_12035.sample_xml", "example"),
    "tanúsítvány/dokumentacio-v3.0.12035/test/system/data/json/general_cert.json": ("certificate.v3_0_12035.sample_json", "example"),
    "tanúsítvány/dokumentacio-v3.0.12035/test/system/data/json/functional_unit_full_data.json": ("certificate.v3_0_12035.full_test_json", "example"),
}

SOURCE_ORIGINS = {
    "9_2023. (V. 25.) ÉKM rendelet.pdf": "https://net.jogtar.hu/getpdf?docid=A2300009.EKO",
}

MEDIA_TYPES = {
    ".md": "text/markdown", ".json": "application/json", ".xml": "text/xml",
    ".csv": "text/csv", ".yml": "application/yaml", ".yaml": "application/yaml",
    ".pdf": "application/pdf", ".png": "image/png",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _normalise(path: str) -> str:
    return path.replace("\\", "/")


def _pdf_metadata(path: Path) -> dict[str, object]:
    # Read the root/branch page-tree counts without a third-party PDF runtime.
    # Some simple generated PDFs omit a visible /Pages count; for those files
    # the uncompressed page-dictionary count is the stable fallback.
    data = path.read_bytes()
    count_after = re.findall(
        rb"/Type\s*/Pages\b(?:(?!endobj).){0,2000}?/Count\s+(\d+)", data, re.DOTALL
    )
    count_before = re.findall(
        rb"/Count\s+(\d+)(?:(?!endobj).){0,2000}?/Type\s*/Pages\b", data, re.DOTALL
    )
    tree_counts = [int(value) for value in count_after + count_before]
    page_count = max(tree_counts) if tree_counts else len(re.findall(rb"/Type\s*/Page\b", data))
    return {"page_count": page_count}


def _xml_metadata(path: Path) -> dict[str, object]:
    root = ElementTree.parse(path).getroot()
    return {"root_element": root.tag, "direct_child_count": len(root)}


def _xlsx_metadata(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        sheets = [node.attrib["name"] for node in root.findall("m:sheets/m:sheet", namespace)]
        image_count = sum(name.startswith("xl/media/") for name in archive.namelist())
    return {"sheets": sheets, "embedded_image_count": image_count}


def _metadata(path: Path) -> dict[str, object]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdf_metadata(path)
    if suffix == ".xml":
        return _xml_metadata(path)
    if suffix == ".xlsx":
        return _xlsx_metadata(path)
    if suffix in {".md", ".csv", ".json"}:
        return {"line_count": len(path.read_text(encoding="utf-8-sig").splitlines())}
    return {}


def _generated_source_id(relative_path: str) -> str:
    stem = Path(relative_path).with_suffix("").as_posix().lower()
    stem = re.sub(r"[^a-z0-9]+", ".", stem).strip(".")
    digest = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:10]
    return f"support.{stem or 'file'}.{digest}"


def build_manifest(source_root: Path) -> dict[str, object]:
    sources: list[dict[str, object]] = []
    discovered = {
        _normalise(str(path.relative_to(source_root)))
        for path in source_root.rglob("*") if path.is_file()
    }
    definitions = dict(SOURCE_DEFINITIONS)
    for relative_path in sorted(discovered - set(definitions)):
        definitions[relative_path] = (_generated_source_id(relative_path), "support")
    missing = set(definitions) - discovered
    if missing:
        raise FileNotFoundError(f"required certification sources are missing: {sorted(missing)}")

    for relative_path, (source_id, role) in definitions.items():
        path = source_root / Path(relative_path)
        if not path.is_file():
            raise FileNotFoundError(f"required certification source is missing: {path}")
        metadata = _metadata(path)
        if relative_path in SOURCE_ORIGINS:
            metadata["origin_url"] = SOURCE_ORIGINS[relative_path]
        sources.append({
            "source_id": source_id,
            "relative_path": _normalise(relative_path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
            "media_type": MEDIA_TYPES.get(path.suffix.lower(), mimetypes.guess_type(path.name)[0] or "application/octet-stream"),
            "role": role,
            "metadata": metadata,
        })
    sources.sort(key=lambda item: str(item["source_id"]))
    content_hash = hashlib.sha256(
        json.dumps(sources, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "schema_version": 1,
        "manifest_id": f"hungarian_energy_certification_sources_{content_hash}",
        "source_root": "energetika",
        "sources": sources,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.source_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"manifest_id": manifest["manifest_id"], "sources": len(manifest["sources"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
