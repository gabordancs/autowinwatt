"""Create a disposable one-building Délceg model and native import XML."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from winwatt_automation.certificates.native_xml import compile_native_xml


BUILDING_NAME = "DELCEG56 - Egy épület"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-model", required=True, type=Path)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    model = json.loads(args.source_model.resolve(strict=True).read_text(encoding="utf-8"))
    model["buildings"] = [{"name": BUILDING_NAME, "address": model["project"].get("address", "")}]
    for room in model["rooms"]:
        room["building"] = BUILDING_NAME
    # Keep the known wall-geometry issues visible in review metadata, while
    # allowing a disposable native import that proves the reassignment.
    model["project"]["require_wall_xy"] = False
    model["project"]["status"] = "single_building_reassignment_review_required"
    model.setdefault("review_notes", []).append(
        "Mind a 29 helyiség a DELCEG56 - Egy épület rekordhoz van rendelve; "
        "a régi és új rész megkülönböztetése a helyiség A/B előtagjával marad meg."
    )
    model_path = output / "delceg_single_building_model.json"
    model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = compile_native_xml(
        model_path,
        args.template.resolve(strict=True),
        output / "delceg_single_building_import.xml",
    )
    result.update({
        "model": str(model_path),
        "building_name": BUILDING_NAME,
        "heated_area_m2": round(sum(float(room["area_m2"]) for room in model["rooms"]), 2),
    })
    (output / "build_report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
