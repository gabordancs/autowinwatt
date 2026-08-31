"""Create one sandbox building, three rooms, and one external wall per room.

The workflow intentionally uses a caller-created disposable ``.wwp`` file.
It is an executable verification of the previously mapped creation routes,
not a mutation of a user's working project.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pywinauto import Application, keyboard

from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.runtime_mapping.room_deep_explorer import (
    _active_window,
    _room_list_item,
    open_sandbox_building,
    open_sandbox_room,
)


def _wait_window(process_id: int, classes: set[str], timeout: float = 8.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            window = _active_window(process_id)
            if window.class_name() in classes:
                return window
        except Exception:
            pass
        time.sleep(0.15)
    observed = _active_window(process_id)
    raise RuntimeError(f"Expected one of {sorted(classes)!r}, got {observed.class_name()!r}")


def _find_visible(window: Any, control_type: str, name: str) -> Any:
    for item in window.descendants(control_type=control_type):
        if item.is_visible() and item.is_enabled() and item.window_text().strip() == name:
            return item
    raise LookupError(f"Missing enabled {control_type} {name!r} in {window.class_name()}")


def _plain(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()


def _select_external_wall_in_library(selector: Any) -> None:
    """Select ``Külső fal`` through the native list-view selection model.

    The Delphi list exposes its rows to UIA, but a UIA click leaves its native
    selected-index unset, and therefore keeps ``Felvesz...`` disabled.
    """
    process_id = int(selector.process_id())
    native = Application(backend="win32").connect(process=process_id).window(handle=int(selector.handle))
    libraries = [
        item for item in native.descendants()
        if item.class_name() == "TListViewWithHeader" and item.rectangle().top > 500
    ]
    if len(libraries) != 1:
        raise RuntimeError(f"Expected one lower construction library, found {len(libraries)}")
    library = libraries[0]
    rows = sorted(
        [item for item in selector.descendants(control_type="ListItem") if item.is_visible() and item.rectangle().top >= library.rectangle().top],
        key=lambda item: item.rectangle().top,
    )
    index = next((pos for pos, item in enumerate(rows) if _plain(item.window_text()) == "kulso fal"), None)
    if index is None:
        raise RuntimeError("Külső fal is not present in the selected construction library")
    row_height = max(1, (rows[1].rectangle().top - rows[0].rectangle().top) if len(rows) > 1 else 24)
    library.click_input(coords=(30, index * row_height + row_height // 2))
    time.sleep(0.25)
    selected = ctypes.windll.user32.SendMessageW(int(library.handle), 0x100C, -1, 2)
    if selected != index:
        raise RuntimeError(f"Native construction selection failed: expected row {index}, got {selected}")


def _save_project() -> None:
    """Commit the catalog changes to the disposable project file."""
    main = get_main_window()
    main.set_focus()
    keyboard.send_keys("^s")
    time.sleep(0.6)


def add_external_wall(room: Any) -> dict[str, str]:
    """Add the previously verified ``Külső fal`` boundary and commit it."""
    process_id = int(room.process_id())
    _find_visible(room, "Button", "Szerkezetek...").click_input()
    selector = _wait_window(process_id, {"TSelectBoundarisForm"})

    # The catalog tree determines which construction list is displayed.
    _find_visible(selector, "TreeItem", "Szerkezetek").click_input()
    time.sleep(0.2)
    _find_visible(selector, "TreeItem", "Határoló szerkezetek").click_input()
    time.sleep(0.3)
    _select_external_wall_in_library(selector)
    _find_visible(selector, "Button", "Felvesz...").click_input()

    detail = _wait_window(process_id, {"TWallBoundaryModifyForm", "TBoundaryModifyForm"})
    boundary_form = detail.class_name()
    detail.set_focus()
    keyboard.send_keys("{ENTER}")
    # The detail form closes back to the selector.  Confirm the selector and
    # finally the room editor, so the new row is committed to the project.
    selector = _wait_window(process_id, {"TSelectBoundarisForm"})
    _find_visible(selector, "Button", "OK").click_input()
    room = _wait_window(process_id, {"TRoomModifyForm"})
    room.set_focus()
    keyboard.send_keys("{ENTER}")
    _save_project()
    return {"room_form": room.class_name(), "boundary_form": boundary_form}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--building-name", default="Automation demo building")
    parser.add_argument("--room-prefix", default="Automation demo room")
    args = parser.parse_args()
    project = args.project.resolve()
    if "full_authorized_sandbox" not in {part.casefold() for part in project.parts}:
        parser.error("project must be in an explicitly created full_authorized_sandbox directory")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    building = open_sandbox_building(project_path=str(project), building_name=args.building_name)
    building.set_focus()
    keyboard.send_keys("{ENTER}")
    _save_project()
    result: dict[str, Any] = {
        "project": str(project), "building": args.building_name,
        "started_at": datetime.now(timezone.utc).isoformat(), "rooms": [],
    }
    for index in range(1, 4):
        room_name = f"{args.room_prefix} {index}"
        room = open_sandbox_room(project_path=str(project), room_name=room_name)
        boundary = add_external_wall(room)
        result["rooms"].append({"name": room_name, "boundary": "Külső fal", **boundary})
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
