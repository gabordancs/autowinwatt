"""Immutable-source manifest and measurement-ready Délceg fixture inventory."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from .adapters import import_workbook


def sha256_file(path: Path) -> str:
    digest=sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024),b""): digest.update(block)
    return digest.hexdigest()


def build_fixture_manifest(workbook: Path, pdf_root: Path, target: Path) -> dict:
    candidates=import_workbook(workbook)
    source_pdfs=[]
    for path in sorted(pdf_root.glob("*.pdf")):
        source_pdfs.append({"path":str(path.resolve()),"sha256":sha256_file(path),"bytes":path.stat().st_size})
    manifest={"fixture":"delceg-e2e-001","fixture_status":"needs_human_approved_geometry","source_workbook":{"path":str(workbook.resolve()),"sha256":sha256_file(workbook)},"source_pdfs":source_pdfs,"candidate_inventory":{"total":len(candidates),"by_entity_type":{kind:sum(c.entity_type==kind for c in candidates) for kind in sorted({c.entity_type for c in candidates})},"with_missing_evidence_location":sum(c.evidence.location_status=="missing_evidence_location" for c in candidates)},"required_approved_assets":["room polygons", "wall centerlines/bands", "opening associations", "dimension anchors", "thermal-zone states", "roof planes"]}
    target.parent.mkdir(parents=True,exist_ok=True); target.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return manifest
