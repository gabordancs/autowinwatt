"""Capture a Tools-menu dialog without invoking any of its controls.

The script opens one already-classified high-risk Tools command, records the
visible dialog's control tree, takes a screenshot, then cancels it with Esc.
It intentionally never selects a file, edits a value, or presses an accept
button.  This makes dialog discovery reproducible without changing the
currently open WinWatt project.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from pywinauto import Application
from pywinauto.controls.menuwrapper import MenuItemNotEnabled

from winwatt_automation.live_ui.app_connector import (
    ensure_main_window_foreground_before_click,
    prepare_main_window_for_menu_interaction,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TOOLS_ROOT_ID = 54
ACTION_LABELS = {
    55: "safe_tools_change_ceiling_probe",
    56: "safe_tools_temperature_change_probe",
    57: "safe_tools_filtration_probe",
    58: "safe_tools_next_probe",
    59: "safe_tools_next_probe_2",
    60: "safe_tools_next_probe_3",
    61: "safe_tools_next_probe_4",
    62: "safe_tools_next_probe_5",
    71: "safe_tools_next_probe_6",
    72: "safe_tools_next_probe_7",
    73: "safe_tools_next_probe_8",
    74: "safe_tools_next_probe_9",
    75: "safe_tools_next_probe_10",
    76: "safe_tools_next_probe_11",
    77: "safe_tools_next_probe_12",
    79: "safe_tools_next_probe_13",
}
VALUE_BEARING_CLASSES = {"Edit", "ListBox", "ListView", "TreeView", "ComboBox"}


def _visible_windows(app: Application) -> list[tuple[int, str, str]]:
    windows: list[tuple[int, str, str]] = []
    for window in app.windows():
        try:
            if window.is_visible():
                windows.append((int(window.handle), window.friendly_class_name(), window.window_text()))
        except Exception:
            continue
    return windows


def _control_record(control: Any, index: int) -> dict[str, Any]:
    friendly_class = control.friendly_class_name()
    record: dict[str, Any] = {
        "index": index,
        "friendly_class": friendly_class,
        "class_name": control.class_name(),
        "is_enabled": bool(control.is_enabled()),
        "is_visible": bool(control.is_visible()),
    }
    # Current values can contain project data.  Only static/button captions are
    # retained; editable and data-bearing controls are represented structurally.
    if friendly_class not in VALUE_BEARING_CLASSES:
        text = control.window_text()
        if text:
            record["text"] = text
    return record


def capture(command_id: int) -> dict[str, Any]:
    if command_id not in ACTION_LABELS:
        raise ValueError(f"No approved non-mutating probe action is registered for command {command_id}.")

    prepare_main_window_for_menu_interaction()
    main = ensure_main_window_foreground_before_click(
        action_label=ACTION_LABELS[command_id], allow_dialog=True
    )
    app = Application(backend="win32").connect(process=int(main.process_id()))
    before = set(_visible_windows(app))
    native_main = app.window(handle=main.handle)
    tools_root = next(item for item in native_main.menu().items() if int(item.item_id()) == TOOLS_ROOT_ID)
    tools_root.click()
    time.sleep(0.15)

    try:
        next(item for item in tools_root.sub_menu().items() if int(item.item_id()) == command_id).click()
    except MenuItemNotEnabled:
        map_dir = PROJECT_ROOT / "data" / "runtime_maps" / "high_risk_dialogs_9_60"
        map_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "command_id": command_id,
            "result": "disabled_in_current_project",
            "dialog": None,
            "control_count": 0,
            "controls": [],
            "screenshot": None,
            "main_enabled_after": bool(main.is_enabled()),
        }
        output_path = map_dir / f"{command_id}_disabled.json"
        output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        record["output"] = str(output_path)
        return record

    time.sleep(0.8)
    new_windows = [
        item
        for item in _visible_windows(app)
        if item not in before and item[1] not in {"TApplication", "TMainForm"}
    ]
    if len(new_windows) != 1:
        raise RuntimeError(f"Expected exactly one dialog for {command_id}, observed {new_windows!r}")

    handle, friendly_class, title = new_windows[0]
    dialog = app.window(handle=handle)
    controls = [_control_record(control, index) for index, control in enumerate(dialog.descendants())]

    snapshot_dir = PROJECT_ROOT / "data" / "snapshots" / "high_risk_dialogs_9_60"
    map_dir = PROJECT_ROOT / "data" / "runtime_maps" / "high_risk_dialogs_9_60"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    map_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = snapshot_dir / f"{command_id}_{friendly_class}.png"
    dialog.capture_as_image().save(screenshot_path)

    # Esc is the only interaction with the dialog.  No data-bearing control is touched.
    dialog.type_keys("{ESC}")
    time.sleep(0.5)
    record = {
        "command_id": command_id,
        "result": "opened_mapped_and_cancelled",
        "dialog": {"friendly_class": friendly_class, "title": title},
        "control_count": len(controls),
        "controls": controls,
        "screenshot": str(screenshot_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "main_enabled_after": bool(main.is_enabled()),
    }
    output_path = map_dir / f"{command_id}_{friendly_class}.json"
    output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    record["output"] = str(output_path)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command_id", type=int)
    args = parser.parse_args()
    print(json.dumps(capture(args.command_id), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
