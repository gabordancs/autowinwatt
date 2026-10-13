"""Combine native XML and WinWatt UI evidence for one OENY pilot WWP."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zone-report", required=True, type=Path)
    parser.add_argument("--envelope-report", required=True, type=Path)
    parser.add_argument("--roof-ui-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    zone = load(args.zone_report)
    envelope = load(args.envelope_report)
    roof = load(args.roof_ui_report)

    failed_boundaries = [item for item in envelope["boundary_checks"] if not item["passed"]]
    roof_xml_gap = (
        len(failed_boundaries) == 1
        and failed_boundaries[0]["name"] == "Tető ÉK"
        and failed_boundaries[0]["differences"] == [
            {"field": "Compass", "expected": "45", "actual": None},
            {"field": "Gradient", "expected": "10", "actual": None},
        ]
    )
    controls = {int(item["control_id"]): item for item in roof.get("controls", [])}
    roof_ui_passed = (
        roof.get("status") == "passed"
        and roof.get("source_unchanged") is True
        and controls.get(3344782, {}).get("text") == "45° (ÉK)"
        and controls.get(68192, {}).get("text") == "10°"
        and controls.get(3344782, {}).get("enabled") is False
        and controls.get(68192, {}).get("enabled") is False
    )
    passed = all((
        zone.get("status") == "passed",
        zone.get("area_roundtrip_passed") is True,
        zone.get("expected_area_m2") == 32.8,
        zone.get("reopened_zone_name") == "F1",
        envelope.get("structures") == 6,
        envelope.get("layers") == 14,
        envelope.get("boundaries") == 11,
        envelope.get("room_area_m2") == 32.8,
        envelope.get("room_height_m") == 2.7,
        all(item["passed"] for item in envelope["structure_checks"]),
        all(item["passed"] for item in envelope["boundary_checks"] if item["name"] != "Tető ÉK"),
        roof_xml_gap,
        roof_ui_passed,
    ))
    report = {
        "schema_version": 1,
        "status": "passed" if passed else "failed",
        "project": zone.get("project"),
        "profile_id": zone.get("profile_id"),
        "room": "F1",
        "area_m2": zone.get("expected_area_m2"),
        "height_m": envelope.get("room_height_m"),
        "structures": envelope.get("structures"),
        "layers": envelope.get("layers"),
        "boundaries": envelope.get("boundaries"),
        "roof": {
            "name": "Tető ÉK",
            "azimuth": "45° (ÉK)",
            "inclination": "10°",
            "native_ui_passed": roof_ui_passed,
            "xml_export_omits_orientation": roof_xml_gap,
        },
        "evidence": {
            "zone_report": str(args.zone_report.resolve()),
            "envelope_report": str(args.envelope_report.resolve()),
            "roof_ui_report": str(args.roof_ui_report.resolve()),
        },
        "llm_used": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
