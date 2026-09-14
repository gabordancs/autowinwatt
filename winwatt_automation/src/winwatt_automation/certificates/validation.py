"""Readback validation for native WinWatt certificate projects."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

from .native_xml import _explicit_glass_ratio

_CODE_TO_SOURCE_TYPE = {"0": "külső fal", "3": "talajon fekvő padló", "5": "külső tető", "10": "tetőablak", "12": "külső ajtó/kapu"}


def _number(value: str | None) -> float:
    try:
        return float((value or "0").replace(",", "."))
    except ValueError:
        return 0.0


def _diff(expected: float, actual: float) -> dict[str, float]:
    absolute = actual - expected
    return {"expected": round(expected, 6), "actual": round(actual, 6), "absolute": round(absolute, 6),
            "relative_percent": round(100 * absolute / expected, 6) if expected else 0.0}


def validate_native_readback(model_path: Path, readback_xml: Path) -> dict[str, Any]:
    """Compare reviewed source geometry with a native XML export after reopen."""
    model = json.loads(model_path.read_text(encoding="utf-8"))
    root = ET.parse(readback_xml).getroot()
    rooms = root.findall("WinWatt32Room")
    panels = root.findall("WinWatt32Panel")
    buildings = root.findall("WinWatt32Building")
    expected_layers = len(model.get("layers", []))
    actual_layers = sum(len(panel.findall("PanelLayer")) for panel in panels)
    # WinWatt's native ``Type`` code is not sufficiently expressive for a
    # source comparison: in this WinWatt version code 10 is used for both
    # some ordinary windows and rooflights.  The generated Boundary/Name is
    # preserved on export, so use it as the authoritative source mapping and
    # only fall back to the native type code for unknown/imported elements.
    source_types_by_name: dict[str, set[str]] = defaultdict(set)
    for boundary in model.get("boundaries", []):
        name = str(boundary.get("name") or "").strip()
        source_type = str(boundary.get("winwatt_type") or "unknown")
        if name:
            source_types_by_name[name].add(source_type)

    actual_by_type: dict[str, float] = defaultdict(float)
    actual_by_azimuth: dict[str, float] = defaultdict(float)
    actual_loss = 0.0
    boundary_count = 0
    actual_room_conditions: dict[str, dict[str, float]] = {}
    actual_glass_ratios = {
        (panel.findtext("ItemHeader/ItemName") or "").strip(): _number(panel.findtext("GlassRatio"))
        for panel in panels
    }
    for room in rooms:
        room_name = (room.findtext("ItemHeader/ItemName") or "").strip()
        actual_room_conditions[room_name] = {
            "winter_temperature_c": _number(room.findtext("Heating/Temp")),
            "summer_temperature_c": _number(room.findtext("Cooling/Temp")),
            "air_change_h": _number(room.findtext("Heating/Filtration/AirChangeFact")),
        }
        for boundary in room.findall("Boundary"):
            boundary_count += 1
            area = _number(boundary.findtext("A"))
            name = (boundary.findtext("Name") or "").strip()
            mapped = source_types_by_name.get(name, set())
            kind = next(iter(mapped)) if len(mapped) == 1 else _CODE_TO_SOURCE_TYPE.get(
                boundary.findtext("Type") or "", boundary.findtext("Type") or "unknown"
            )
            # Do not infer orientation from the source name here: the report
            # must expose legacy WinWatt fields which were not persisted after
            # import/reopen (notably Compass on this version's roof type).
            azimuth = str(round(_number(boundary.findtext("Compass"))))
            actual_by_type[kind] += area
            actual_by_azimuth[azimuth] += area
            actual_loss += area * _number(boundary.findtext("U"))
    expected_by_type: dict[str, float] = defaultdict(float)
    expected_by_azimuth: dict[str, float] = defaultdict(float)
    expected_loss = 0.0
    for boundary in model.get("boundaries", []):
        area = float(boundary["area_m2"])
        expected_by_type[boundary["winwatt_type"]] += area
        expected_by_azimuth[str(round(float(boundary.get("azimuth_deg", 0))))] += area
        expected_loss += float(boundary.get("heat_loss_wk") or 0.0)
    source_area = float(model["project"]["heated_area_m2"])
    source_volume = float(model["project"]["heated_volume_m3"])
    room_conditions: dict[str, dict[str, dict[str, float]]] = {}
    for source_room in model.get("rooms", []):
        name = str(source_room.get("name") or "").strip()
        actual = actual_room_conditions.get(name, {})
        expected_winter = source_room.get("temperature_c")
        expected_air_change = source_room.get("air_change_h")
        if expected_winter is not None or expected_air_change is not None:
            room_conditions[name] = {}
            if expected_winter is not None:
                room_conditions[name]["winter_temperature_c"] = _diff(float(expected_winter), actual.get("winter_temperature_c", 0.0))
            if expected_air_change is not None:
                room_conditions[name]["air_change_h"] = _diff(float(expected_air_change), actual.get("air_change_h", 0.0))
    opening_glass_ratios = {
        str(structure["name"]): _diff(float(ratio), actual_glass_ratios.get(str(structure["name"]), 0.0))
        for structure in model.get("structures", [])
        if (ratio := _explicit_glass_ratio(structure)) is not None
    }
    report = {
        "source_model": str(model_path), "readback_xml": str(readback_xml),
        "counts": {"buildings": len(buildings), "zones": sum(len(building.findall("ETZone")) for building in buildings), "rooms": len(rooms), "structures": len(panels), "boundaries": boundary_count,
                   "layer_rows": actual_layers, "expected_layer_rows": expected_layers},
        "totals": {
            "heated_area_m2": _diff(source_area, sum(_number(room.findtext("Area")) for room in rooms)),
            "heated_volume_m3": _diff(source_volume, sum(_number(room.findtext("CalculatedVolume")) for room in rooms)),
            "transmission_wk": _diff(expected_loss, actual_loss),
        },
        "surface_by_source_type_m2": {key: _diff(value, actual_by_type.get(key, 0.0)) for key, value in sorted(expected_by_type.items())},
        "surface_by_azimuth_deg_m2": {key: _diff(value, actual_by_azimuth.get(key, 0.0)) for key, value in sorted(expected_by_azimuth.items())},
        "room_conditions": room_conditions,
        "opening_glass_ratio_percent": opening_glass_ratios,
        "mechanics_included": False,
    }
    return report


def write_validation_report(model_path: Path, readback_xml: Path, target: Path) -> dict[str, Any]:
    report = validate_native_readback(model_path, readback_xml)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
