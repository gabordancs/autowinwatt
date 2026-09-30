"""Network-independent WebWatt certificate intake with a durable manifest."""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from winwatt_automation.certificates import CertificateBuildInput, CertificateProjectBuilder


MANIFEST_NAME = "intake_manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def xml_summary(source: Path, destination: Path) -> dict[str, Any]:
    root = ET.parse(source).getroot()
    counts: dict[str, int] = {}
    for node in root.iter():
        name = node.tag.rsplit("}", 1)[-1]
        counts[name] = counts.get(name, 0) + 1
    payload = {
        "source": source.name,
        "source_sha256": sha256(source),
        "root": root.tag,
        "element_counts": dict(sorted(counts.items())),
        "next_step": "XML structure was indexed locally. Import or WWP generation remains a separate human-approved action.",
        "llm_used": False,
        "winwatt_started": False,
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _artifact_rows(output_dir: Path) -> list[dict[str, Any]]:
    return [
        {"name": path.name, "path": str(path), "sha256": sha256(path), "size": path.stat().st_size}
        for path in sorted(output_dir.glob("*.json")) if path.name != MANIFEST_NAME
    ]


def process_local_intake(
    *, source: Path, output_dir: Path, catalog_xml: Path | None = None,
) -> dict[str, Any]:
    source = source.resolve(strict=True)
    output_dir = output_dir.resolve()
    manifest_path = output_dir / MANIFEST_NAME
    source_hash = sha256(source)
    if manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("source", {}).get("sha256") != source_hash:
            raise ValueError("existing intake manifest belongs to different source bytes")
        missing = [item["path"] for item in existing.get("artifacts", []) if not Path(item["path"]).is_file()]
        if missing:
            raise ValueError(f"cached intake is incomplete; missing artifacts: {missing}")
        existing["cache_hit"] = True
        return existing
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"non-empty intake output has no manifest: {output_dir}")

    suffix = source.suffix.lower()
    if suffix == ".pdf":
        if catalog_xml is None or not catalog_xml.is_file():
            raise ValueError("PDF intake needs a local WinWatt material catalogue XML")
        result = CertificateProjectBuilder().build(CertificateBuildInput(
            certificate_pdf=source, output_dir=output_dir, catalog_xml=catalog_xml,
            allow_llm=False, execute_winwatt=False,
        ))
        summary = {
            "kind": "pdf", "deterministic_values": len(result.deterministic_values),
            "material_decisions": len(result.material_decisions),
            "unresolved": len(result.unresolved), "llm_used": result.llm_used,
        }
    elif suffix == ".xml":
        output_dir.mkdir(parents=True, exist_ok=True)
        xml_summary(source, output_dir / "xml_intake_summary.json")
        summary = {"kind": "xml", "llm_used": False}
    else:
        raise ValueError("only .pdf and .xml source files are supported")

    manifest = {
        "schema_version": 1,
        "workflow": "webwatt.certificate_intake.local",
        "status": "review_required",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(source), "name": source.name, "sha256": source_hash, "size": source.stat().st_size},
        "catalog": ({"path": str(catalog_xml.resolve()), "sha256": sha256(catalog_xml.resolve())}
                    if catalog_xml is not None else None),
        "summary": summary,
        "artifacts": _artifact_rows(output_dir),
        "review_required": True,
        "winwatt_started": False,
        "llm_used": False,
        "cache_hit": False,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest
