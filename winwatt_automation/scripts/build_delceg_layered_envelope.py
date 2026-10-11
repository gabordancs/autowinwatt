"""Build the Délceg 56 envelope with plan-backed material layers.

Only layers with an explicit thickness on É-03 are included.  The reviewed
effective U-values remain authoritative until a material-catalog review is
completed.  The output is always a new WWP and is verified after reopen by a
native XML export.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import xml.etree.ElementTree as ET
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from winwatt_automation.certificates.native_xml import compile_native_xml
from winwatt_automation.services.winwatt_service import WinWattService
from winwatt_automation.services.xml_native_service import NativeXmlService
from winwatt_automation.version_profile import require_profile


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def layer(structure: str, sequence: int, name: str, thickness_cm: float,
          density: float, conductivity: float, heat_capacity: float) -> dict:
    return {
        "structure": structure,
        "sequence": sequence,
        "name": name,
        "thickness_cm": thickness_cm,
        "density_kgm3": density,
        "lambda_wmk": conductivity,
        "heat_capacity_kjkgk": heat_capacity,
        "source": "É03_TERVEZETT METSZETEK_végl.pdf, RÉTEGRENDEK",
    }


PLAN_LAYERS = [
    layer("B R5 új külső fal - tervrétegrend", 1, "AUSTROTHERM AT H80 homlokzati hőszigetelés", 20, 80, 0.039, 1.45),
    layer("B R5 új külső fal - tervrétegrend", 2, "Porotherm 38 vázkerámia falazat (terven 30 cm)", 30, 800, 0.16, 0.84),
    layer("B R1B új tető - tervrétegrend", 1, "PIR hőszigetelés, lépcsős ütközőhézaggal", 25, 32, 0.022, 1.40),
    layer("B R1B új tető - tervrétegrend", 2, "Horonyeresztékes gyalult deszkaburkolat", 2.5, 500, 0.13, 1.60),
    layer("B R7 ferde tető - tervrétegrend", 1, "Kőzetgyapot hőszigetelés", 25, 40, 0.039, 1.03),
    layer("B R6 tetőterasz - tervrétegrend", 1, "WPC burkolat", 2, 1100, 0.23, 1.50),
    layer("B R6 tetőterasz - tervrétegrend", 2, "Bazaltzúzalék ágyazóréteg", 3, 1800, 1.70, 0.84),
    layer("B R6 tetőterasz - tervrétegrend", 3, "PUR hőszigetelés", 15, 35, 0.026, 1.40),
    layer("B R6 tetőterasz - tervrétegrend", 4, "Lejtést adó beton (2-5 cm, átlag)", 3.5, 2200, 1.40, 0.84),
    layer("B R14 talajon fekvő padló - tervrétegrend", 1, "Szigetelést védő beton", 5, 2200, 1.40, 0.84),
    layer("B R14 talajon fekvő padló - tervrétegrend", 2, "VILLAS VILLAVERDE WS-FLL modifikált bitumenes vastaglemez", 0.45, 1100, 0.17, 1.00),
    layer("B R14 talajon fekvő padló - tervrétegrend", 3, "VILLAS E-G 45 F/K SBS modifikált bitumenes vastaglemez", 0.40, 1100, 0.17, 1.00),
    layer("B R14 talajon fekvő padló - tervrétegrend", 4, "Monolit vasbeton lemezalap", 25, 2400, 2.30, 0.84),
    layer("B R14 talajon fekvő padló - tervrétegrend", 5, "Kavicsfeltöltés", 25, 1800, 0.70, 0.84),
    layer("B R15 pincefal - tervrétegrend", 1, "XPS hőszigetelés", 20, 35, 0.035, 1.45),
    layer("B R15 pincefal - tervrétegrend", 2, "Zsalukő falazat", 30, 1800, 1.15, 0.84),
    layer("B R16 meglévő pincefal - tervrétegrend", 1, "Meglévő zsalukő falazat", 25, 1800, 1.15, 0.84),
]


def readback_structures(path: Path, expected: dict[str, list[dict]]) -> tuple[dict, bool]:
    found: dict[str, dict] = {}
    for panel in ET.parse(path).getroot().findall("WinWatt32Panel"):
        name = panel.findtext("ItemHeader/ItemName") or ""
        if name not in expected:
            continue
        rows = [{child.tag: child.text for child in list(item)} for item in panel.findall("PanelLayer")]
        found[name] = {"layered": panel.attrib.get("Layered"), "layers": rows}
    ok = set(found) == set(expected)
    for name, planned in expected.items():
        actual = found.get(name, {})
        rows = actual.get("layers", [])
        ok = ok and actual.get("layered") == "Yes" and len(rows) == len(planned)
        for wanted, got in zip(planned, rows):
            ok = ok and got.get("LayerName") == wanted["name"]
            ok = ok and abs(float((got.get("Thickness") or "nan").replace(",", ".")) - wanted["thickness_cm"] / 100) < 1e-6
    return found, bool(ok)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--template-xml", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if struct.calcsize("P") * 8 != 32:
        parser.error("requires 32-bit Python")
    profile = require_profile(args.profile.resolve(strict=True))
    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"output must be new: {output}")
    output.mkdir(parents=True)
    source_before = sha256(source)
    report = {
        "schema_version": 1,
        "profile_id": profile["profile_id"],
        "source": str(source),
        "source_sha256": source_before,
        "plan_source": "É03_TERVEZETT METSZETEK_végl.pdf",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "failed",
        "llm_used": False,
    }
    winwatt = WinWattService()
    try:
        model = json.loads(args.model.resolve(strict=True).read_text(encoding="utf-8"))
        model = deepcopy(model)
        # This pass changes structure definitions only.  Preserve legacy
        # aggregate wall areas via the compiler's area x 1 fallback; detailed
        # wall X/Y reconstruction remains a separate, explicit review gate.
        model["project"]["require_wall_xy"] = False
        one_building = "Délceg utca 56 - egy tanúsítási egység"
        model["project"]["name"] = one_building
        model["buildings"] = [{"name": one_building, "address": "1162 Budapest, Délceg utca 56."}]
        for room in model["rooms"]:
            room["building"] = one_building
        model["layers"] = PLAN_LAYERS
        model_path = output / "delceg_layered_model.json"
        model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        import_xml = output / "delceg_layered_import.xml"
        compile_result = compile_native_xml(model_path, args.template_xml.resolve(strict=True), import_xml)
        winwatt.open_project(source)
        project = winwatt.create_empty_project(output / "Delceg_56_egy_epulet_reteges_hatarolok.wwp")
        empty_hash = sha256(project)
        import_evidence = NativeXmlService().import_xml(import_xml)
        winwatt.save_project()
        winwatt.close_project_gracefully()
        winwatt.open_project(project)
        readback = output / "reopen_readback.xml"
        export_evidence = NativeXmlService().export_xml(readback)
        expected: dict[str, list[dict]] = {}
        for item in PLAN_LAYERS:
            expected.setdefault(item["structure"], []).append(item)
        found, roundtrip = readback_structures(readback, expected)
        report.update({
            "project": str(project),
            "project_sha256": sha256(project),
            "compile": compile_result,
            "import_evidence": import_evidence.model_dump(mode="json"),
            "export_evidence": export_evidence.model_dump(mode="json"),
            "layered_structure_count": len(found),
            "layer_count": sum(len(item["layers"]) for item in found.values()),
            "readback": found,
            "roundtrip_passed": roundtrip,
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
    report["status"] = "passed" if all((report.get("roundtrip_passed"), report.get("copy_changed"), report["source_unchanged"])) else "failed"
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
