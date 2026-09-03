"""Authorized, recoverable WinWatt state-space exploration.

The explorer is deliberately split between *observation* and *execution*.
It enumerates every native menu node (including the last child of a submenu),
opens each top-level popup to obtain visual/geometry evidence, and navigates
the reversible tabs of a room detail form.  It never invokes an unknown leaf
command: menu leaves can save, delete, import, start a calculation or leave
the application.  Such leaves are retained as explicit exploration frontiers
for a later, separately authorized workflow.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pywinauto import Application, Desktop

from winwatt_automation.live_ui.app_connector import (
    ensure_main_window_foreground_before_click,
    get_main_window,
)
from winwatt_automation.live_ui.menu_helpers import open_top_menu_and_capture_popup_state
from winwatt_automation.live_ui.native_menu import enumerate_native_menu
from winwatt_automation.runtime_mapping.mdi_state_model import (
    ROOMS_TITLE,
    activate_rooms_catalog,
    capture_active_mdi_state,
)
from winwatt_automation.runtime_mapping.safety import classify_safety


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "runtime_maps" / "authorized_explorer_9_60"
DEFAULT_ROOM_NAME = "AutoWinWatt teszt helyiség"
OUTER_ROOM_TABS = (
    "Általános adatok",
    "Téli hőszükséglet",
    "Nyári hőterhelés",
    "Radiátorok",
    "Felületfűtés-hűtés",
    "Fan-coilok",
)
INNER_ROOM_TABS = (
    "Határoló szerkezetek",
    "Radiátor választék",
    "Felületfűtés-hűtés választék",
    "Fan-coil választék",
)
INTERESTING_CONTROL_TYPES = {
    "Edit", "Button", "ComboBox", "List", "ListItem", "CheckBox", "RadioButton",
    "Tab", "TabItem", "DataGrid", "Table", "Tree", "TreeItem",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_") or "unnamed"


def _project_relative(path: Path) -> str:
    """Return a portable project-relative artifact path for absolute or relative input."""
    return str(path.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")


def _rect(control: Any) -> dict[str, int] | None:
    try:
        rect = control.rectangle()
        return {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom}
    except Exception:
        return None


def _visible_controls(window: Any) -> list[dict[str, Any]]:
    """Capture affordances, not editable values, from the active room surface."""
    controls: list[dict[str, Any]] = []
    for control in window.descendants():
        element = control.element_info
        control_type = str(getattr(element, "control_type", "") or "")
        if control_type not in INTERESTING_CONTROL_TYPES:
            continue
        try:
            if not control.is_visible():
                continue
        except Exception:
            continue
        try:
            enabled = bool(control.is_enabled())
        except Exception:
            enabled = None
        controls.append({
            "control_type": control_type,
            "class_name": str(getattr(element, "class_name", "") or ""),
            "name": str(getattr(element, "name", "") or ""),
            "automation_id": str(getattr(element, "automation_id", "") or ""),
            "enabled": enabled,
            "rectangle": _rect(control),
        })
    return controls


def menu_leaf_frontier(native_menu: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten every executable leaf and classify it without invoking it."""
    leaves: list[dict[str, Any]] = []

    def visit(node: dict[str, Any], path: list[str]) -> None:
        caption = str(node.get("caption") or "")
        label = caption if node.get("caption_reliable") else f"command:{node.get('command_id')}"
        current = [*path, label]
        children = list(node.get("children") or [])
        if children:
            for child in children:
                visit(child, current)
            return
        leaves.append({
            "path": current,
            "command_id": node.get("command_id"),
            "enabled": bool(node.get("enabled")),
            "safety": classify_safety(current),
            "execution": "catalog_only_unknown_leaf",
        })

    for top in native_menu.get("items") or []:
        visit(top, [])
    return leaves


def map_top_menu_popups(*, output_dir: Path, checkpoint_path: Path | None = None) -> list[dict[str, Any]]:
    """Click only top-level menu headers and snapshot their popup possibilities."""
    native = enumerate_native_menu()
    result: list[dict[str, Any]] = []
    for top in native.get("items") or []:
        caption = str(top.get("caption") or "")
        if not caption or not top.get("caption_reliable"):
            continue
        try:
            popup = open_top_menu_and_capture_popup_state(caption)
            result.append({
                "top_menu": caption,
                "popup_open": bool(popup.get("popup_open")),
                "status": popup.get("status"),
                "rows": list(popup.get("rows") or []),
                "execution": "top_menu_header_only",
            })
        except Exception as exc:
            result.append({"top_menu": caption, "error": str(exc), "execution": "top_menu_header_only"})
        if checkpoint_path is not None:
            checkpoint_path.write_text(json.dumps({"top_menu_popups": result}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    get_main_window().type_keys("{ESC}")
    return result


def _open_room_detail(room_name: str) -> Any:
    """Select the named room and invoke only the known Elem -> Módosít route."""
    main = get_main_window()
    ensure_main_window_foreground_before_click(action_label="create_room_probe")
    room = next(item for item in main.descendants(control_type="ListItem") if item.window_text().strip() == room_name)
    room.click_input()
    native = Application(backend="win32").connect(process=int(main.process_id())).window(handle=int(main.handle))
    element_menu = next(item for item in native.menu().items() if item.text().replace("&", "").strip() == "Elem")
    element_menu.click()
    time.sleep(0.2)
    items = element_menu.sub_menu().items()
    if len(items) < 2 or not items[1].is_enabled():
        raise RuntimeError("Elem -> Módosít route is unavailable for the selected room")
    items[1].click()
    time.sleep(0.7)
    dialogs = [
        window for window in Desktop(backend="uia").windows(top_level_only=True)
        if window.is_visible() and window.class_name() == "TRoomModifyForm"
    ]
    if not dialogs:
        raise RuntimeError("Room detail form did not open")
    return dialogs[-1]


def map_room_surfaces(*, room_name: str, output_dir: Path) -> dict[str, Any]:
    """Navigate every reversible tab in one named room and save a control map."""
    if room_name != DEFAULT_ROOM_NAME:
        # The caller must deliberately name any non-test room.
        raise ValueError("Only the explicit test-room default is accepted by this explorer run")
    room = _open_room_detail(room_name)
    room_dir = output_dir / "room_detail"
    room_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for group, names in (("outer", OUTER_ROOM_TABS), ("inner", INNER_ROOM_TABS)):
        for index, name in enumerate(names):
            room = Desktop(backend="uia").window(handle=int(room.handle))
            tab = next(item for item in room.descendants(control_type="TabItem") if item.window_text() == name)
            tab.click_input()
            time.sleep(0.25)
            image_path = room_dir / f"{group}_{index:02d}_{_slug(name)}.png"
            room.capture_as_image().save(image_path)
            controls = _visible_controls(room)
            records.append({
                "group": group,
                "tab": name,
                "screenshot": _project_relative(image_path),
                "controls": controls,
                "control_counts": dict(Counter(item["control_type"] for item in controls)),
            })
    # Restore a predictable, non-editing surface.  Do not press OK/Elvet here:
    # the caller may inspect the room after a mapping run.
    general = next(item for item in room.descendants(control_type="TabItem") if item.window_text() == OUTER_ROOM_TABS[0])
    general.click_input()
    structure_button = next(item for item in room.descendants(control_type="Button") if item.window_text() == "Szerkezetek...")
    return {
        "room_title": room.window_text(),
        "room_class": room.class_name(),
        "tabs": records,
        "structure_button": {
            "name": "Szerkezetek...", "enabled": bool(structure_button.is_enabled()),
            "rectangle": _rect(structure_button), "execution": "identified_only_not_invoked",
        },
    }


def run_authorized_exploration(*, output_dir: Path = DEFAULT_OUTPUT_DIR, room_name: str = DEFAULT_ROOM_NAME) -> dict[str, Any]:
    """Run the rooms-first, non-destructive state-space discovery pass."""
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "authorized_exploration.checkpoint.json"
    rooms = activate_rooms_catalog()
    before = capture_active_mdi_state()
    native = enumerate_native_menu()
    result = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "authorization": {
            "scope": "menus, room tabs, visible controls and recoverable views",
            "leaf_execution": "disabled_fail_closed",
            "blocked_actions": "save/delete/import/export/close/exit and unknown leaves",
        },
        "rooms_activation": rooms,
        "rooms_state": before,
        "native_menu": native,
        "menu_leaf_frontier": menu_leaf_frontier(native),
        "top_menu_popups": [],
        "room_surfaces": None,
    }
    checkpoint_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["top_menu_popups"] = map_top_menu_popups(output_dir=output_dir, checkpoint_path=checkpoint_path)
    checkpoint_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["room_surfaces"] = map_room_surfaces(room_name=room_name, output_dir=output_dir)
    result_path = output_dir / "authorized_exploration.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checkpoint_path.unlink(missing_ok=True)
    return result
