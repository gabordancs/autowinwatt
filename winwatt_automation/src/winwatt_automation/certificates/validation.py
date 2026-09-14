"""Readback validation for native WinWatt certificate projects."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

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
    actual_by_type: dict[str, float] = defaultdict(float)
    actual_by_azimuth: dict[str, float] = defaultdict(float)
    actual_loss = 0.0
    boundary_count = 0
    for room in rooms:
        for boundary in room.findall("Boundary"):
            boundary_count += 1
            area = _number(boundary.findtext("A"))
            kind = _CODE_TO_SOURCE_TYPE.get(boundary.findtext("Type") or "", boundary.findtext("Type") or "unknown")
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
        "mechanics_included": False,
    }
    return report


def write_validation_report(model_path: Path, readback_xml: Path, target: Path) -> dict[str, Any]:
    report = validate_native_readback(model_path, readback_xml)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
