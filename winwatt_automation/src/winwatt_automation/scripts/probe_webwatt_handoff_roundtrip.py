"""Import a reviewed WebWatt layer handoff on a disposable WWP and verify readback."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from winwatt_automation.certificates.native_xml import compile_native_xml
from winwatt_automation.certificates.webwatt_handoff import load_webwatt_handoff
from winwatt_automation.services.winwatt_service import WinWattService
from winwatt_automation.services.xml_native_service import NativeXmlService
from winwatt_automation.version_profile import require_profile


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_layers(path: Path) -> dict[str, list[dict[str, str | None]]]:
    result: dict[str, list[dict[str, str | None]]] = {}
    for panel in ET.parse(path).getroot().findall("WinWatt32Panel"):
        name = panel.findtext("ItemHeader/ItemName")
        if name:
            result[name] = [{key: layer.findtext(key) for key in ("LayerName", "Thickness", "ThermalCond", "Density", "HeatCapacity")} for layer in panel.findall("PanelLayer")]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--template-xml", required=True, type=Path)
    parser.add_argument("--handoff", required=True, type=Path)
    parser.add_argument("--catalog-xml", required=True, type=Path)
    args = parser.parse_args()
    if struct.calcsize("P") * 8 != 32:
        parser.error("requires 32-bit Python")
    profile = require_profile(args.profile.resolve(strict=True)); os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    source = args.source.resolve(strict=True); template = args.template_xml.resolve(strict=True)
    handoff = args.handoff.resolve(strict=True); catalog = args.catalog_xml.resolve(strict=True); output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"output must be new: {output}")
    output.mkdir(parents=True)
    source_before = digest(source)
    report: dict[str, object] = {"schema_version": 1, "operation": "webwatt.review_handoff.roundtrip", "profile_id": profile["profile_id"], "source": str(source), "source_sha256": source_before, "handoff": str(handoff), "handoff_sha256": digest(handoff), "catalog_sha256": digest(catalog), "llm_used": False, "started_at": datetime.now(timezone.utc).isoformat(), "status": "failed"}
    winwatt = WinWattService()
    phase = "load_handoff"
    try:
        package, fragment = load_webwatt_handoff(handoff, catalog)
        phase = "compile_import_xml"
        model = {"project": {"name": f"WebWatt review {package.project_id}", "address": "reviewed sandbox"}, "buildings": [{"name": "WebWatt review building", "address": "reviewed sandbox"}], "rooms": [{"name": "WebWatt review room", "building": "WebWatt review building", "area_m2": 10.0, "height_m": 2.7}], "structures": fragment["structures"], "layers": fragment["layers"], "boundaries": [{"room": "WebWatt review room", "name": f"Boundary {index}", "structure": item["name"], "winwatt_type": "külső fal", "area_m2": 10.0, "u_effective": 0.35, "azimuth_deg": 0} for index, item in enumerate(fragment["structures"], 1)]}
        model_path = output / "reviewed_model.json"; model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        import_xml = output / "reviewed_import.xml"; compile_native_xml(model_path, template, import_xml)
        phase = "open_source"
        winwatt.open_project(source)
        phase = "create_empty_project"
        project = winwatt.create_empty_project(output / "sandbox" / "reviewed.wwp"); empty_hash = digest(project)
        phase = "import_xml"
        import_evidence = NativeXmlService().import_xml(import_xml)
        phase = "save_project"
        winwatt.save_project()
        phase = "close_after_save"
        winwatt.close_project_gracefully()
        phase = "reopen_saved_project"
        winwatt.open_project(project)
        phase = "export_readback"
        readback_path = output / "reopen_readback.xml"; export_evidence = NativeXmlService().export_xml(readback_path); actual = read_layers(readback_path)
        phase = "verify_layers"
        expected = {(layer["structure"], layer["sequence"]): layer for layer in fragment["layers"]}
        checks = []
        for (structure, sequence), layer in expected.items():
            rows = actual.get(structure, []); row = rows[sequence - 1] if len(rows) >= sequence else None
            expected_thickness = float(layer["thickness_cm"]) / 100.0
            checks.append({"structure": structure, "sequence": sequence, "passed": bool(row and row["LayerName"] == layer["name"] and abs(float(str(row["Thickness"]).replace(",", ".")) - expected_thickness) < 0.000001), "actual": row})
        report.update({"project": str(project), "model": str(model_path), "import_evidence": import_evidence.model_dump(mode="json"), "export_evidence": export_evidence.model_dump(mode="json"), "checks": checks, "roundtrip_passed": bool(checks) and all(item["passed"] for item in checks), "copy_changed": digest(project) != empty_hash})
    except Exception as exc:
        report["failed_phase"] = phase
        report["error"] = repr(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        try: winwatt.close_project_gracefully()
        except Exception: pass
    report["source_unchanged"] = digest(source) == source_before; report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["status"] = "passed" if all((report.get("roundtrip_passed"), report.get("copy_changed"), report.get("source_unchanged"))) else "failed"
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__": raise SystemExit(main())
