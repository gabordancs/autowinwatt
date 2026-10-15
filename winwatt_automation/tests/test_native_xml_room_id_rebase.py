import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from winwatt_automation.certificates.native_xml import (
    _remove_template_system_items,
    rebase_room_area_ids,
)


def _project(room_ids: tuple[str, ...], refs: tuple[str, ...]) -> ET.ElementTree:
    root = ET.Element("WinWatt32Project")
    for index, room_id in enumerate(room_ids):
        room = ET.SubElement(root, "WinWatt32Room")
        header = ET.SubElement(room, "ItemHeader")
        ET.SubElement(header, "ItemName").text = f"Room {index}"
        ET.SubElement(header, "ItemPath").text = "Building\\Floor\\"
        ET.SubElement(header, "ID").text = room_id
    building = ET.SubElement(root, "WinWatt32Building")
    zone = ET.SubElement(building, "ETZone", {"Name": "Zone"})
    for room_id in refs:
        ET.SubElement(zone, "RoomAreaItem", {"ID": room_id, "Area": "1"})
    return ET.ElementTree(root)


def test_rebase_room_area_ids_uses_stable_room_identity(tmp_path: Path) -> None:
    source, readback, target = tmp_path / "source.xml", tmp_path / "readback.xml", tmp_path / "target.xml"
    _project(("176", "179"), ("179", "176")).write(source, encoding="utf-8")
    _project(("10", "11"), ("179", "176")).write(readback, encoding="utf-8")

    report = rebase_room_area_ids(source, readback, target)

    refs = [node.attrib["ID"] for node in ET.parse(target).getroot().iter("RoomAreaItem")]
    assert refs == ["11", "10"]
    assert report == {
        "source": str(source), "readback": str(readback), "target": str(target),
        "rooms": 2, "references": 2, "changed_references": 2,
    }


def test_rebase_room_area_ids_rejects_unknown_reference(tmp_path: Path) -> None:
    source, readback, target = tmp_path / "source.xml", tmp_path / "readback.xml", tmp_path / "target.xml"
    _project(("176",), ("999",)).write(source, encoding="utf-8")
    _project(("10",), ("999",)).write(readback, encoding="utf-8")

    with pytest.raises(ValueError, match="Unresolved RoomAreaItem IDs"):
        rebase_room_area_ids(source, readback, target)
    assert not target.exists()


def test_remove_template_system_items_keeps_epbd_calculation_fields() -> None:
    building = ET.fromstring(
        """
        <WinWatt32Building>
          <EPBD>
            <CalcMode>2023</CalcMode>
            <WinWatt32HeatingSystemItem><SystemArea>32.8</SystemArea></WinWatt32HeatingSystemItem>
            <WinWatt32WaterHeatingSystemItem />
            <WinWatt32CoolingSystemItem />
          </EPBD>
        </WinWatt32Building>
        """
    )

    assert _remove_template_system_items(building) == 3
    assert building.findtext("EPBD/CalcMode") == "2023"
    assert building.findall("EPBD/WinWatt32HeatingSystemItem") == []
    assert building.findall("EPBD/WinWatt32WaterHeatingSystemItem") == []
    assert building.findall("EPBD/WinWatt32CoolingSystemItem") == []
