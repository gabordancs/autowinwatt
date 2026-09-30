"""Create one layered structure by native XML and prove WinWatt readback."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from winwatt_automation.certificates.native_xml import compile_native_xml
from winwatt_automation.services.winwatt_service import WinWattService
from winwatt_automation.services.xml_native_service import NativeXmlService
from winwatt_automation.version_profile import require_profile


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_structure(path: Path, name: str) -> dict[str, object] | None:
    for panel in ET.parse(path).getroot().findall("WinWatt32Panel"):
        if panel.findtext("ItemHeader/ItemName") != name:
            continue
        return {
            "name": name, "layered": panel.attrib.get("Layered"),
            "layers": [
                {child.tag: child.text for child in list(layer)}
                for layer in panel.findall("PanelLayer")
            ],
        }
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--template-xml", required=True, type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--layer-name", default="AUTO mineral wool")
    parser.add_argument("--thickness-cm", type=float, default=10.0)
    args = parser.parse_args()
    if struct.calcsize("P") * 8 != 32:
        parser.error("requires 32-bit Python")
    profile = require_profile(args.profile.resolve(strict=True))
    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    source = args.source.resolve(strict=True)
    template = args.template_xml.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"output must be new: {output}")
    output.mkdir(parents=True)
    source_before = sha256(source)
    report: dict[str, object] = {
        "schema_version": 1, "tool_id": "winwatt.building.structure.layered.create_roundtrip",
        "profile_id": profile["profile_id"], "source": str(source),
        "source_sha256": source_before, "template_xml": str(template),
        "name": args.name, "layer_name": args.layer_name, "llm_used": False,
        "started_at": datetime.now(timezone.utc).isoformat(), "status": "failed",
    }
    winwatt = WinWattService()
    try:
        model = {
            "project": {"name": "AUTO layered structure proof", "address": "sandbox"},
            "buildings": [{"name": "AUTO proof building", "address": "sandbox"}],
            "rooms": [{"name": "AUTO proof room", "building": "AUTO proof building", "area_m2": 10.0, "height_m": 2.7}],
            "structures": [{"name": args.name, "type": "külső fal", "u_layer": 0.35}],
            "layers": [{"structure": args.name, "sequence": 1, "name": args.layer_name,
                        "thickness_cm": args.thickness_cm, "density_kgm3": 40,
                        "lambda_wmk": 0.04, "heat_capacity_kjkgk": 1.0}],
            "boundaries": [{"room": "AUTO proof room", "name": "AUTO proof wall",
                            "structure": args.name, "winwatt_type": "külső fal",
                            "area_m2": 10.0, "u_effective": 0.35, "azimuth_deg": 0}],
        }
        model_path = output / "model.json"
        model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        import_xml = output / "layered_import.xml"
        compile_result = compile_native_xml(model_path, template, import_xml)
        winwatt.open_project(source)
        project = winwatt.create_empty_project(output / "sandbox" / "layered.wwp")
        empty_hash = sha256(project)
        import_evidence = NativeXmlService().import_xml(import_xml)
        winwatt.save_project()
        winwatt.close_project_gracefully()
        winwatt.open_project(project)
        readback = output / "reopen_readback.xml"
        export_evidence = NativeXmlService().export_xml(readback)
        actual = read_structure(readback, args.name)
        expected_thickness = args.thickness_cm / 100.0
        layer = (actual or {}).get("layers", [{}])[0] if (actual or {}).get("layers") else {}
        thickness = float(str(layer.get("Thickness", "nan")).replace(",", "."))
        roundtrip = bool(
            actual and actual.get("layered") == "Yes" and len(actual.get("layers", [])) == 1
            and layer.get("LayerName") == args.layer_name
            and abs(thickness - expected_thickness) < 0.000001
        )
        report.update({
            "project": str(project), "compile": compile_result,
            "import_evidence": import_evidence.model_dump(mode="json"),
            "export_evidence": export_evidence.model_dump(mode="json"),
            "readback": actual, "roundtrip_passed": roundtrip,
            "copy_changed": sha256(project) != empty_hash,
        })
    except Exception as exc:
        report["error"] = repr(exc)
    finally:
        try:
            winwatt.close_project_gracefully()
        except Exception:
            pass
    report["source_unchanged"] = sha256(source) == source_before
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["status"] = "passed" if all((
        report.get("roundtrip_passed"), report.get("source_unchanged"), report.get("copy_changed"),
    )) else "failed"
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
