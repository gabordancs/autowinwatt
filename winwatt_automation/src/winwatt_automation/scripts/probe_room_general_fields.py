"""Capture the editable controls of a fresh sandbox room's General tab."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from winwatt_automation.runtime_mapping.room_deep_explorer import open_sandbox_room


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    room = open_sandbox_room(project_path=str(args.project.resolve()), room_name="MVP field probe")
    room.capture_as_image().save(args.output_dir / "room_general.png")
    controls = []
    for item in room.descendants():
        info = item.element_info
        if info.control_type not in {"Edit", "ComboBox", "Text", "CheckBox", "TabItem"}:
            continue
        rect = item.rectangle()
        controls.append({"type": info.control_type, "name": item.window_text(), "id": info.automation_id,
                         "class": info.class_name, "rect": [rect.left, rect.top, rect.right, rect.bottom]})
    (args.output_dir / "controls.json").write_text(json.dumps(controls, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
