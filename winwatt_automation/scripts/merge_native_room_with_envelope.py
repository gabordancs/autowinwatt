"""Merge reviewed envelope records into a native WinWatt room/zone export."""
from __future__ import annotations

import argparse
import copy
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def item_id(node: ET.Element) -> ET.Element:
    value = node.find("ItemHeader/ID")
    if value is None:
        raise ValueError(f"missing ItemHeader/ID on {node.tag}")
    return value


def item_name(node: ET.Element) -> str:
    return node.findtext("ItemHeader/ItemName") or ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", required=True, type=Path)
    parser.add_argument("--envelope", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--room", required=True)
    parser.add_argument("--building", required=True)
    args = parser.parse_args()

    native_tree = ET.parse(args.native.resolve(strict=True))
    envelope_tree = ET.parse(args.envelope.resolve(strict=True))
    native_root = native_tree.getroot()
    envelope_root = envelope_tree.getroot()

    native_buildings = [n for n in native_root.findall("WinWatt32Building") if item_name(n) == args.building]
    native_rooms = [n for n in native_root.findall("WinWatt32Room") if item_name(n) == args.room]
    envelope_rooms = [n for n in envelope_root.findall("WinWatt32Room") if item_name(n) == args.room]
    panels = envelope_root.findall("WinWatt32Panel")
    if len(native_buildings) != 1 or len(native_rooms) != 1 or len(envelope_rooms) != 1:
        raise ValueError("expected exactly one native building, native room and envelope room")
    if not panels:
        raise ValueError("envelope contains no structures")

    root = copy.deepcopy(native_root)
    for child in list(root):
        if child.tag in {"WinWatt32Panel", "WinWatt32Building", "WinWatt32Room"}:
            root.remove(child)

    building = copy.deepcopy(native_buildings[0])
    room = copy.deepcopy(native_rooms[0])
    source_room = envelope_rooms[0]
    for boundary in list(room.findall("Boundary")):
        room.remove(boundary)
    for boundary in source_room.findall("Boundary"):
        room.append(copy.deepcopy(boundary))

    # Preserve the native WinWatt-created identity relationship. Panels use
    # the remaining global IDs; boundary engineering fields are copied byte
    # for byte from the reviewed envelope XML.
    building_id = int(item_id(building).text or "0")
    room_id = int(item_id(room).text or "0")
    room.find("BuildingRefID").text = str(building_id)
    occupied = {building_id, room_id}
    next_id = 1
    for panel in panels:
        cloned = copy.deepcopy(panel)
        while next_id in occupied:
            next_id += 1
        item_id(cloned).text = str(next_id)
        occupied.add(next_id)
        next_id += 1
        root.append(cloned)

    # The UI-visible heated zone is ThermicZone Type=0. Retain its native
    # attributes and set only the source-proven zone name.
    heated = [n for n in building.findall("ThermicZone") if n.get("Type") == "0"]
    if len(heated) != 1:
        raise ValueError("native building has no unique heated ThermicZone")
    heated[0].set("Name", args.room)
    # Keep one ETZone address/document carrier selectable for native-import
    # roundtrip verification without changing its native child schema.
    et_zones = building.findall("ETZone")
    if len(et_zones) != 1:
        raise ValueError("native building has no unique ETZone")
    et_zones[0].set("Name", args.room)

    root.append(building)
    root.append(room)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    native_tree._setroot(root)
    ET.indent(native_tree, space="  ")
    native_tree.write(args.output, encoding="utf-8", xml_declaration=True)
    report = {
        "schema_version": 1,
        "native": str(args.native.resolve()),
        "envelope": str(args.envelope.resolve()),
        "output": str(args.output.resolve()),
        "building": args.building,
        "room": args.room,
        "building_id": building_id,
        "room_id": room_id,
        "structures": len(panels),
        "boundaries": len(room.findall("Boundary")),
        "llm_used": False,
        "status": "passed",
    }
    report_path = args.output.with_suffix(args.output.suffix + ".report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
