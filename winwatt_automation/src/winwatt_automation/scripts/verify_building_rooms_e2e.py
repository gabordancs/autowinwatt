"""Fresh-session UI readback for one building and its external-wall rooms."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.runtime_mapping.room_deep_explorer import _activate_rooms_catalog_fast, open_sandbox_buildings, open_sandbox_room
from winwatt_automation.scripts.create_building_with_rooms import read_external_wall_x


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--building", required=True)
    parser.add_argument("--room", action="append", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    buildings = open_sandbox_buildings(project_path=str(project))
    building_names = sorted({item.window_text().strip() for item in buildings.descendants(control_type="ListItem") if item.window_text().strip()})
    building_ok = any(name.casefold() == args.building.casefold() for name in building_names)
    _activate_rooms_catalog_fast(get_main_window())
    room_names = sorted({item.window_text().strip() for item in get_main_window().descendants(control_type="ListItem") if item.window_text().strip()})
    rooms = []
    for name in args.room:
        detail = open_sandbox_room(project_path=str(project), room_name=name)
        x = read_external_wall_x(detail)
        rooms.append({"name": name, "present": any(item.casefold() == name.casefold() for item in room_names), "external_wall_x_m": x, "x_matches": abs(x - 1.0) < 0.0001})
    success = building_ok and all(item["present"] and item["x_matches"] for item in rooms)
    result = {"success": success, "project": str(project), "building": {"expected": args.building, "actual": building_names, "present": building_ok}, "rooms": rooms}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
