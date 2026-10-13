"""Verify reviewed native envelope data after WinWatt save/reopen/export."""
from __future__ import annotations

import argparse
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path


FLOAT_FIELDS = ("x", "y", "A", "U")
TEXT_FIELDS = ("Name", "Type", "Compass", "Gradient")


def name(node: ET.Element) -> str:
    return node.findtext("ItemHeader/ItemName") or ""


def one(nodes: list[ET.Element], description: str) -> ET.Element:
    if len(nodes) != 1:
        raise ValueError(f"expected one {description}, found {len(nodes)}")
    return nodes[0]


def numeric(value: str | None) -> float:
    return float((value or "nan").replace(",", "."))


def close(left: str | None, right: str | None) -> bool:
    # Native WinWatt readback stores several geometry fields with four or five
    # decimal places. This tolerance accepts only that serialization rounding.
    return math.isclose(numeric(left), numeric(right), rel_tol=0.0, abs_tol=5e-5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", required=True, type=Path)
    parser.add_argument("--actual", required=True, type=Path)
    parser.add_argument("--building", required=True)
    parser.add_argument("--room", required=True)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    expected = ET.parse(args.expected.resolve(strict=True)).getroot()
    actual = ET.parse(args.actual.resolve(strict=True)).getroot()

    expected_panels = {name(node): node for node in expected.findall("WinWatt32Panel")}
    actual_panels = {name(node): node for node in actual.findall("WinWatt32Panel")}
    structure_checks = []
    for panel_name, wanted in expected_panels.items():
        got = actual_panels.get(panel_name)
        wanted_layers = wanted.findall("PanelLayer")
        got_layers = got.findall("PanelLayer") if got is not None else []
        layers_ok = len(wanted_layers) == len(got_layers)
        for wanted_layer, got_layer in zip(wanted_layers, got_layers):
            layers_ok = layers_ok and wanted_layer.findtext("LayerName") == got_layer.findtext("LayerName")
            layers_ok = layers_ok and close(wanted_layer.findtext("Thickness"), got_layer.findtext("Thickness"))
        structure_checks.append({
            "name": panel_name,
            "passed": got is not None and wanted.get("Type") == got.get("Type") and layers_ok,
            "layers": len(got_layers),
        })

    expected_room = one([n for n in expected.findall("WinWatt32Room") if name(n) == args.room], "expected room")
    actual_room = one([n for n in actual.findall("WinWatt32Room") if name(n) == args.room], "actual room")
    expected_boundaries = expected_room.findall("Boundary")
    actual_boundaries = actual_room.findall("Boundary")
    boundary_checks = []
    unused_actual = list(actual_boundaries)
    for wanted in expected_boundaries:
        wanted_names = [node.text or "" for node in wanted.findall("Name")]
        boundary_name = wanted_names[0]
        structure_name = wanted_names[-1]
        wanted_types = [node.text for node in wanted.findall("Type")]
        wanted_x = [node.text for node in wanted.findall("x")][-1]
        wanted_y = [node.text for node in wanted.findall("y")][-1]
        wanted_area = [node.text for node in wanted.findall("A")][-1]
        got = next((
            node for node in unused_actual
            if (node.findall("Name")[-1].text or "") == structure_name
            and node.findall("Type")[-1].text == wanted_types[-1]
            and close(node.findall("x")[-1].text, wanted_x)
            and close(node.findall("y")[-1].text, wanted_y)
            and close(node.findall("A")[-1].text, wanted_area)
        ), None)
        passed = got is not None
        differences = []
        if got is not None:
            unused_actual.remove(got)
            for field in ("Compass", "Gradient"):
                wanted_value = wanted.findall(field)[-1].text
                got_nodes = got.findall(field)
                got_value = got_nodes[-1].text if got_nodes else None
                if wanted_value != got_value:
                    differences.append({"field": field, "expected": wanted_value, "actual": got_value})
            for field in FLOAT_FIELDS:
                wanted_value = wanted.findall(field)[-1].text
                got_value = got.findall(field)[-1].text
                if not close(wanted_value, got_value):
                    differences.append({"field": field, "expected": wanted_value, "actual": got_value})
            passed = passed and not differences
        boundary_checks.append({"name": boundary_name, "structure": structure_name, "passed": bool(passed), "differences": differences})

    actual_building = one([n for n in actual.findall("WinWatt32Building") if name(n) == args.building], "actual building")
    heated = one([n for n in actual_building.findall("ThermicZone") if n.get("Type") == "0"], "heated ThermicZone")
    room_values_passed = close(expected_room.findtext("Area"), actual_room.findtext("Area")) and close(
        expected_room.findtext("Height"), actual_room.findtext("Height")
    )
    passed = all((
        len(expected_panels) == len(actual_panels),
        bool(structure_checks) and all(item["passed"] for item in structure_checks),
        len(expected_boundaries) == len(actual_boundaries),
        bool(boundary_checks) and all(item["passed"] for item in boundary_checks),
        room_values_passed,
        heated.get("Name") == args.room,
    ))
    report = {
        "schema_version": 1,
        "expected": str(args.expected.resolve()),
        "actual": str(args.actual.resolve()),
        "building": args.building,
        "room": args.room,
        "structures": len(actual_panels),
        "layers": sum(len(node.findall("PanelLayer")) for node in actual_panels.values()),
        "boundaries": len(actual_boundaries),
        "room_area_m2": numeric(actual_room.findtext("Area")),
        "room_height_m": numeric(actual_room.findtext("Height")),
        "heated_zone_name": heated.get("Name"),
        "structure_checks": structure_checks,
        "boundary_checks": boundary_checks,
        "llm_used": False,
        "status": "passed" if passed else "failed",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
