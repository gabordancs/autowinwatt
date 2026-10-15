"""Readback validation for native WinWatt certificate projects."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

from .native_xml import _explicit_glass_ratio
from .geometry import is_vertical_wall, wall_geometry_issues, xy_area

_CODE_TO_SOURCE_TYPE = {"0": "külső fal", "3": "talajon fekvő padló", "5": "külső tető", "10": "tetőablak", "12": "külső ajtó/kapu"}
_SYSTEM_TAGS = {
    "heating": "WinWatt32HeatingSystemItem",
    "hot_water": "WinWatt32WaterHeatingSystemItem",
    "water_heating": "WinWatt32WaterHeatingSystemItem",
    "cooling": "WinWatt32CoolingSystemItem",
    "airing": "WinWatt32AiringSystemItem",
    "lighting": "WinWatt32LightingSystemItem",
}


def _number(value: str | None) -> float:
    try:
        return float((value or "0").replace(",", "."))
    except ValueError:
        return 0.0


def _diff(expected: float, actual: float) -> dict[str, float]:
    absolute = actual - expected
    return {"expected": round(expected, 6), "actual": round(actual, 6), "absolute": round(absolute, 6),
            "relative_percent": round(100 * absolute / expected, 6) if expected else 0.0}


def _text_comparison(expected: Any, actual: Any) -> dict[str, Any]:
    expected_text = str(expected or "").strip()
    actual_text = str(actual or "").strip()
    return {
        "expected": expected_text,
        "actual": actual_text,
        "equal": expected_text.casefold() == actual_text.casefold(),
    }


def _printed_number_diff(expected: int | float, actual: float) -> dict[str, float]:
    """Compare with the precision retained by the source-model number.

    PDF values parsed as integers are printed to whole units.  Preserve the
    raw native value for audit, but compare its rounded display value so a
    native 926.6 kWh/a correctly agrees with a printed 927 kWh/a.
    """
    compared_actual = float(round(actual)) if isinstance(expected, int) else actual
    result = _diff(float(expected), compared_actual)
    result["raw_actual"] = round(actual, 6)
    return result


def _system_readback(model: dict[str, Any], buildings: list[ET.Element]) -> dict[str, Any]:
    """Expose source-to-native system fields without inventing mappings.

    WinWatt stores system records below each building's EPBD node.  The
    comparison deliberately keeps catalogue labels and numeric calculation
    results separate: a name roundtrip is not evidence that annual energy
    results also agree with the source PDF.
    """
    expected_systems = [item for item in model.get("systems", []) if isinstance(item, dict)]
    native_by_type: dict[str, list[ET.Element]] = {
        system_type: [
            item
            for building in buildings
            for item in building.findall(f"EPBD/{tag}")
        ]
        for system_type, tag in _SYSTEM_TAGS.items()
    }
    # Synonyms point to the same native tag; retain one canonical count.
    counts = {
        key: len(native_by_type[key])
        for key in ("heating", "hot_water", "cooling", "airing", "lighting")
    }
    items: list[dict[str, Any]] = []
    for source in expected_systems:
        system_type = str(source.get("type") or "").strip()
        candidates = native_by_type.get(system_type, [])
        expected_name = str(source.get("name") or "").strip()
        native = next(
            (item for item in candidates if (item.findtext("Name") or "").strip() == expected_name),
            candidates[0] if len(candidates) == 1 else None,
        )
        comparison: dict[str, Any] = {
            "type": system_type,
            "name": _text_comparison(expected_name, native.findtext("Name") if native is not None else ""),
            "present": native is not None,
        }
        if native is not None:
            comparison["served_area_m2"] = _diff(
                float(source.get("served_area_m2") or 0.0), _number(native.findtext("SystemArea"))
            )
            comparison["carrier"] = _text_comparison(
                source.get("carrier"), native.findtext("StokerItem/EnergySourceTypeDescription")
            )
            if source.get("generator_performance_factor") is not None:
                comparison["generator_performance_factor"] = _diff(
                    float(source["generator_performance_factor"]), _number(native.findtext("StokerItem/Ck"))
                )
            comparison["native_generator"] = (native.findtext("StokerItem/CkDescription") or "").strip()
            consumption = native.find("EnergyConsumptions/ConsumptionTableItem")
            if source.get("final_energy_kwh_a") is not None:
                comparison["final_energy_kwh_a"] = _printed_number_diff(
                    source["final_energy_kwh_a"],
                    _number(consumption.get("Consumption") if consumption is not None else None),
                )
            if system_type == "heating" and source.get("net_heat_kwh_a") is not None:
                # ElementTree has no parent axis; all matching items are below
                # one of the supplied EPBD elements, so read the building value.
                actual = next(
                    (_number(building.findtext("EPBD/HeatingEnergy")) for building in buildings
                     if native in building.findall("EPBD/WinWatt32HeatingSystemItem")),
                    0.0,
                )
                comparison["net_heat_kwh_a"] = _printed_number_diff(source["net_heat_kwh_a"], actual)
            if system_type in {"hot_water", "water_heating"}:
                if source.get("net_demand_kwh_m2a") is not None:
                    comparison["net_demand_kwh_m2a"] = _diff(
                        float(source["net_demand_kwh_m2a"]), _number(native.findtext("qHMV"))
                    )
                if source.get("storage_loss_percent") is not None:
                    comparison["storage_loss_percent"] = _diff(
                        float(source["storage_loss_percent"]), _number(native.findtext("qft"))
                    )
                comparison["native_storage"] = (native.findtext("qftDescription") or "").strip()
                comparison["native_distribution"] = (native.findtext("qfvDescription") or "").strip()
                comparison["native_auxiliary"] = (native.findtext("EcDescription") or "").strip()
        items.append(comparison)
    return {
        "expected_count": len(expected_systems),
        "native_counts": counts,
        "items": items,
    }


def validate_native_readback(model_path: Path, readback_xml: Path) -> dict[str, Any]:
    """Compare reviewed source geometry with a native XML export after reopen."""
    model = json.loads(model_path.read_text(encoding="utf-8"))
    root = ET.parse(readback_xml).getroot()
    rooms = root.findall("WinWatt32Room")
    panels = root.findall("WinWatt32Panel")
    buildings = root.findall("WinWatt32Building")
    expected_layers = len(model.get("layers", []))
    actual_layers = sum(len(panel.findall("PanelLayer")) for panel in panels)
    # WinWatt normalizes Boundary/Name to the referenced construction name on
    # native import (for example ``Külső fal ÉK`` becomes ``Külső fal``).  Keep
    # per-room source rows and pair them by the explicit construction
    # reference plus area.  This survives the normalization without inferring
    # a source type from a lossy numeric native code.
    source_boundaries_by_room: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source_boundary in model.get("boundaries", []):
        source_boundaries_by_room[str(source_boundary.get("room") or "")].append(source_boundary)

    actual_by_type: dict[str, float] = defaultdict(float)
    actual_by_azimuth: dict[str, float] = defaultdict(float)
    actual_loss = 0.0
    boundary_count = 0
    actual_room_conditions: dict[str, dict[str, float]] = {}
    actual_xy: dict[str, dict[str, float]] = {}
    actual_glass_ratios = {
        (panel.findtext("ItemHeader/ItemName") or "").strip(): _number(panel.findtext("GlassRatio"))
        for panel in panels
    }
    for room in rooms:
        room_name = (room.findtext("ItemHeader/ItemName") or "").strip()
        unmatched = list(source_boundaries_by_room.get(room_name, []))
        actual_room_conditions[room_name] = {
            "winter_temperature_c": _number(room.findtext("Heating/Temp")),
            "summer_temperature_c": _number(room.findtext("Cooling/Temp")),
            "air_change_h": _number(room.findtext("Heating/Filtration/AirChangeFact")),
        }
        for boundary in room.findall("Boundary"):
            boundary_count += 1
            area = _number(boundary.findtext("A"))
            construction_name = (boundary.findtext("Name") or "").strip()
            candidates = [
                item for item in unmatched
                if construction_name in {
                    str(item.get("structure") or "").strip(),
                    str(item.get("name") or "").strip(),
                }
                and abs(float(item.get("area_m2") or 0.0) - area) <= 5e-4
            ]
            source_boundary = candidates[0] if candidates else None
            if source_boundary is not None:
                unmatched.remove(source_boundary)
                source_name = str(source_boundary.get("name") or construction_name)
                kind = str(source_boundary.get("winwatt_type") or "unknown")
            else:
                source_name = construction_name
                kind = _CODE_TO_SOURCE_TYPE.get(
                    boundary.findtext("Type") or "", boundary.findtext("Type") or "unknown"
                )
            actual_xy[source_name] = {"x_m": _number(boundary.findtext("x")), "y_m": _number(boundary.findtext("y")), "area_m2": area}
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
    wall_xy = {}
    for boundary in model.get("boundaries", []):
        if not is_vertical_wall(boundary):
            continue
        name = str(boundary.get("name") or "")
        geometry = xy_area(boundary)
        if geometry is None:
            wall_xy[name] = {"status": "unresolved", "reason": "missing source X length and Y height"}
            continue
        x, y, area = geometry
        actual = actual_xy.get(name, {})
        wall_xy[name] = {
            "status": "verified" if actual else "missing_after_import",
            "x_m": _diff(x, actual.get("x_m", 0.0)),
            "y_m": _diff(y, actual.get("y_m", 0.0)),
            "area_m2": _diff(area, actual.get("area_m2", 0.0)),
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
        "wall_xy_geometry": wall_xy,
        "wall_xy_issues": wall_geometry_issues(model),
        "system_readback": _system_readback(model, buildings),
        "mechanics_included": bool(model.get("systems")) or any(
            building.find("EPBD/WinWatt32HeatingSystemItem") is not None
            or building.find("EPBD/WinWatt32WaterHeatingSystemItem") is not None
            or building.find("EPBD/WinWatt32CoolingSystemItem") is not None
            or building.find("EPBD/WinWatt32AiringSystemItem") is not None
            or building.find("EPBD/WinWatt32LightingSystemItem") is not None
            for building in buildings
        ),
    }
    return report


def write_validation_report(model_path: Path, readback_xml: Path, target: Path) -> dict[str, Any]:
    report = validate_native_readback(model_path, readback_xml)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
